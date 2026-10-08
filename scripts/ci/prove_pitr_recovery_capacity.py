"""Real isolated PostgreSQL recovery with the production drill commands/cap.

Only synthetic test data, unique local paths and containers; no API/R2/SSH/env
bootstrap. Intended for the narrowly selected Linux Docker CI workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ha.postgres_pitr_recovery_config import write_recovery_settings
from scripts.ha import postgres_pitr_wal_lineage as lineage

DRILL = REPO / 'scripts/ha/restore_postgres_pitr_drill.sh'
RECOVERY_MIB = 768
REPRESENTATIVE_MIN_BYTES = 128 * 1024**2  # Above the recorded 113 MB production backup.


def run(args, *, check=True, timeout=180):
    return subprocess.run(args, text=True, capture_output=True, check=check, timeout=timeout)


def sql(container, text, *, check=True):
    return run(['docker', 'exec', container, 'psql', '-v', 'ON_ERROR_STOP=1',
                '-U', 'postgres', '-d', 'pitr_capacity_test', '-At', '-c', text], check=check)


def source_command(command, *args, check=True):
    return run(['bash', '-ec', 'source "$1"; '+command, 'capacity-proof', str(DRILL), *map(str, args)], check=check)


def chown_tree(root, uid, gid):
    for parent, directories, files in os.walk(root):
        os.chown(parent, uid, gid)
        for name in directories+files:
            os.chown(Path(parent, name), uid, gid)


def cleanup_owned_runtime(containers, root):
    # A checked list distinguishes absence from a failed Docker daemon/inspect.
    command = ['docker', 'container', 'ls', '--all', '--format', '{{.Names}}']
    existing = set(run(command).stdout.splitlines())
    errors = []
    for name in containers:
        if name in existing:
            removed = run(['docker', 'rm', '-f', name], check=False)
            if removed.returncode != 0:
                errors.append(f'{name}: {removed.stderr.strip()}')
    remaining = set(run(command).stdout.splitlines()) & set(containers)
    if errors or remaining:
        raise RuntimeError(f'owned runtime cleanup failed: errors={errors}, remaining={sorted(remaining)}')
    # Never remove a mounted fixture before all owned containers are gone.
    if root is not None:
        shutil.rmtree(root)


def finish_proof(proof, containers, root, evidence):
    try:
        cleanup_owned_runtime(containers, root)
    except Exception as exc:
        proof.update(status='FAILED', test_runtime_cleaned=False, cleanup_error=str(exc))
    else:
        proof['test_runtime_cleaned'] = True
    evidence.write_text(json.dumps(proof, indent=2) + '\n')
    evidence.chmod(0o644)
    if not proof['test_runtime_cleaned']:
        raise RuntimeError(proof['cleanup_error'])


def prove(evidence):
    assert os.geteuid() == 0, 'CI proof needs root for disposable fixture ownership'
    operation = uuid.uuid4().hex
    source = 'mvn-pitr-capacity-test-source-'+operation
    recovery = 'mvn-pitr-capacity-test-recovery-'+operation
    target = 'mvn_pitr_'+operation
    proof = {'status': 'FAILED', 'recovery_memory_mib': RECOVERY_MIB,
             'physical_recovery_executed': False, 'fixture_only': True}
    containers = [source, recovery, recovery+'-verify']
    root = None
    try:
        root = Path(tempfile.mkdtemp(prefix='mvn-pitr-capacity-test-'))
        pgdata, prepared, wal = root/'source', root/'prepared', root/'wal'
        for path in (pgdata, prepared, wal):
            path.mkdir()
            os.chown(path, 70, 70)
        os.environ['PITR_OPERATION_ID'] = operation
        image = source_command('printf "%s" "${POSTGRES_IMAGE}"').stdout
        assert re.fullmatch(r'postgres:15\.18-alpine@sha256:[a-f0-9]{64}', image)
        run(['docker', 'pull', image], timeout=240)
        run(['docker', 'run', '--pull', 'never', '-d', '--name', source,
             '--network', 'none', '--memory', '512m', '--memory-swap', '512m', '--cpus', '1',
             '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=pitr_capacity_test',
             '-e', 'POSTGRES_INITDB_ARGS=--data-checksums',
             '-v', f'{pgdata}:/var/lib/postgresql/data', '-v', f'{wal}:/pitr-wal',
             '-v', f'{prepared}:/pitr-backup', image, 'postgres',
             '-c', 'archive_mode=on', '-c', 'archive_command=cp %p /pitr-wal/%f'])
        for _ in range(60):
            if sql(source, 'SELECT 1', check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise AssertionError('synthetic test PostgreSQL did not start')
        sql(source, "CREATE TABLE synthetic(id integer PRIMARY KEY,payload text); "
            "ALTER TABLE synthetic ALTER COLUMN payload SET STORAGE EXTERNAL; "
            "INSERT INTO synthetic SELECT i,repeat(md5(i::text),64) FROM generate_series(1,65536) AS i; "
            "CREATE TABLE after_target(id integer);")
        systemid = sql(source, 'SELECT system_identifier FROM pg_control_system()').stdout.strip()
        assert sql(source, 'SHOW data_checksums').stdout.strip() == 'on'
        run(['docker', 'exec', '--user', '70:70', source, 'pg_basebackup', '-U', 'postgres',
             '-D', '/pitr-backup/data', '-X', 'none', '--checkpoint', 'fast',
             '--manifest-checksums', 'SHA256'], timeout=180)
        manifest = json.loads((prepared/'data/backup_manifest').read_text())
        extracted = sum(item['Size'] for item in manifest['Files'])
        assert extracted >= REPRESENTATIVE_MIN_BYTES, f'fixture too small: {extracted}'
        sql(source, "UPDATE synthetic SET payload=repeat(md5(('changed'||id)::text),64) WHERE id<=4096; "
            "INSERT INTO synthetic SELECT i,repeat(md5(i::text),64) FROM generate_series(65537,66560) AS i;")
        checksum_query = "SELECT count(*)::text||'|'||sum(id)::text||'|'||md5(string_agg(md5(payload),'' ORDER BY id)) FROM synthetic"
        checksum = sql(source, checksum_query).stdout.strip()
        point_lsn = sql(source, f"SELECT pg_create_restore_point('{target}')::text").stdout.strip()
        required_wal = sql(source, f"SELECT pg_walfile_name('{point_lsn}'::pg_lsn)").stdout.strip()
        sql(source, 'INSERT INTO after_target VALUES(1); SELECT pg_switch_wal()')
        for _ in range(60):
            if (wal/required_wal).is_file():
                break
            time.sleep(1)
        else:
            raise AssertionError('post-backup target WAL was not archived')
        files = [p for p in wal.iterdir() if re.fullmatch(r'[A-F0-9]{24}',p.name)]
        assert len(files) >= 2, 'fixture must exercise more than one archived segment'
        wal_range = manifest['WAL-Ranges'][0]
        start_wal = lineage.wal_segment_name(timeline=wal_range['Timeline'],
            lsn=wal_range['Start-LSN'], segment_size_bytes=16*1024**2)
        selected = lineage.select_wal_objects(
            [lineage.WalObject(key=str(p), filename=p.name, size_bytes=p.stat().st_size) for p in files],
            start_wal_name=start_wal, start_lsn=wal_range['Start-LSN'],
            required_end_wal=required_wal, segment_size_bytes=16*1024**2,
            history_loader=None)
        assert selected.segments, 'strict physical WAL selector was empty'
        shutil.copytree(wal, prepared/'wal')
        (prepared/'downloads').mkdir()
        shutil.copyfile(prepared/'data/backup_manifest', prepared/'downloads/backup_manifest')
        # Restore prepare extracts files as root; verification precedes PG ownership.
        chown_tree(prepared, 0, 0)
        write_recovery_settings(data_dir=prepared/'data', control_dir=prepared/'control',
            target_time=None, target_name=target, wal_mode='local',
            restore_mount_path='/pitr-restore', restore_helper_path='unused')
        capacity = 'require_drill_capacity "$2" "$3"'
        source_command(capacity, RECOVERY_MIB, REPO/'scripts/ha/require_deploy_capacity.sh')
        # Prove actual pg_verifybackup rejects changed fixture bytes, then restore.
        entry = next(item for item in manifest['Files'] if item['Path'].startswith('base/') and item['Size'] > 8192)
        file = prepared/'data'/entry['Path']
        with file.open('r+b') as stream:
            first = stream.read(1)
            stream.seek(0)
            stream.write(bytes([first[0] ^ 1]))
        rejected = source_command('verify_drill_basebackup "$2" "$3" "$4"', recovery, prepared, root, check=False)
        assert rejected.returncode != 0, 'production verification accepted corruption'
        with file.open('r+b') as stream:
            stream.write(first)
        source_command('verify_drill_basebackup "$2" "$3" "$4"', recovery, prepared, root)
        source_command('target_dir="$2"; sanitize_restored_config', prepared)
        (prepared/'control/pg_hba.conf').write_text('local all all trust\nhost all all all reject\n')
        (prepared/'control/pg_ident.conf').write_text('# intentionally empty\n')
        for path in (prepared/'control', prepared/'wal'):
            chown_tree(path, 70, 70)
            path.chmod(0o500)
            for child in path.iterdir():
                child.chmod(0o400)
        source_command(capacity, RECOVERY_MIB, REPO/'scripts/ha/require_deploy_capacity.sh')
        source_command('start_drill_recovery "$2" "$3" "$4"', recovery, prepared, RECOVERY_MIB)
        proof['physical_recovery_executed'] = True
        fmt = '{{json .HostConfig.Memory}}|{{json .HostConfig.MemorySwap}}|{{json .HostConfig.NetworkMode}}'
        observed = run(['docker','inspect','--format',fmt,recovery]).stdout.strip().split('|')
        assert [json.loads(v) for v in observed] == [RECOVERY_MIB*1024**2,RECOVERY_MIB*1024**2,'none']
        pause = f"SELECT pg_is_in_recovery() AND pg_is_wal_replay_paused() AND pg_last_wal_replay_lsn()>='{point_lsn}'::pg_lsn"
        for _ in range(180):
            state = sql(recovery,pause,check=False)
            if state.returncode == 0 and state.stdout.strip() == 't':
                break
            time.sleep(1)
        else:
            raise AssertionError('production recovery commands did not pause at target')
        assert sql(recovery,'SELECT system_identifier FROM pg_control_system()').stdout.strip() == systemid
        assert sql(recovery,'SHOW recovery_target_name').stdout.strip() == target
        assert sql(recovery,checksum_query).stdout.strip() == checksum
        assert sql(recovery,'SELECT count(*) FROM after_target').stdout.strip() == '0'
        settings = json.loads(sql(recovery,
            "SELECT json_object_agg(name,json_build_object('setting',setting,'unit',unit)) "
            "FROM pg_settings WHERE name IN ('shared_buffers','work_mem',"
            "'maintenance_work_mem','max_connections','data_checksums','archive_mode',"
            "'primary_conninfo','shared_preload_libraries')").stdout)
        assert settings['shared_buffers'] == {'setting': '16384', 'unit': '8kB'}
        assert settings['work_mem'] == {'setting': '4096', 'unit': 'kB'}
        proof.update(status='PASS', fixture_extracted_bytes=extracted, system_identifier=systemid,
                     archived_segments=len(files), selected_segments=len(selected.segments),
                     pg_verifybackup_passed=True,
                     corrupted_backup_rejected=True, target_reached_and_paused=True,
                     post_backup_rows=66560, synthetic_checksum=checksum,
                     after_target_rows=0, recovery_settings=settings, image_ref=image,
                     source_revision=run(['git','-C',str(REPO),'rev-parse','HEAD']).stdout.strip())
    except Exception as exc:
        proof['error'] = str(exc)
        for name in containers:
            result = run(['docker','logs','--tail','40',name],check=False)
            if result.returncode == 0:
                proof[name+'-logs'] = result.stdout+result.stderr
        raise
    finally:
        finish_proof(proof, containers, root, evidence)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-path',type=Path,required=True)
    prove(parser.parse_args().evidence_path)
