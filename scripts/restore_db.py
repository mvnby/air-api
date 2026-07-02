#!/usr/bin/env python3
"""
Database Restore Script
=======================
Downloads the latest SQL dump from Google Drive and restores it to the local database.
Uses the project's Google Drive API credentials (token.json).

Usage (inside Docker container):
    python scripts/restore_db.py                    # Restore latest backup
    python scripts/restore_db.py --list             # List available backups
    python scripts/restore_db.py --file <filename>  # Restore specific backup
    python scripts/restore_db.py --with-media       # Also restore media files

Can also be run via docker compose:
    docker compose exec app python scripts/restore_db.py
"""

import os
import sys
import argparse
import subprocess
import tempfile
import logging
from io import BytesIO

# Add project root to path so we can import google_service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Google Drive backup folder ID
BACKUP_FOLDER_ID = '1jhl2Mp__fqcVlZMzR5lOgWo8JuIUWsNy'
SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_FILE = 'token.json'

# Database settings from environment
DB_USER = os.environ.get('POSTGRES_USER', 'mvnadmin')
DB_PASS = os.environ.get('POSTGRES_PASSWORD', 'securepass')
DB_HOST = os.environ.get('POSTGRES_SERVER', 'db')
DB_PORT = os.environ.get('POSTGRES_PORT', '5432')
DB_NAME = os.environ.get('POSTGRES_DB', 'air_conditioners')

PLAIN_SQL_DUMP_SETTINGS_TO_STRIP = {
    'transaction_timeout',
}


def sanitize_plain_sql_dump(dump_path):
    """Remove pg_dump client-version SET commands unsupported by older servers."""
    if not dump_path.endswith('.sql') or not os.path.exists(dump_path):
        return False

    changed = False
    temp_path = f"{dump_path}.sanitized"
    with open(dump_path, 'r', encoding='utf-8', errors='replace') as source, open(
        temp_path,
        'w',
        encoding='utf-8',
    ) as dest:
        for line in source:
            stripped = line.strip()
            if stripped.startswith('SET ') and stripped.endswith(';'):
                setting_name = stripped[4:].split('=', 1)[0].strip()
                if setting_name in PLAIN_SQL_DUMP_SETTINGS_TO_STRIP:
                    changed = True
                    continue
            dest.write(line)

    if changed:
        os.replace(temp_path, dump_path)
    else:
        os.remove(temp_path)
    return changed


def get_credentials():
    """Load Google API credentials from token.json."""
    if not os.path.exists(TOKEN_FILE):
        logger.error(f"❌ Token file '{TOKEN_FILE}' not found!")
        logger.error("   Run the app and authenticate via /admin/google-auth first.")
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
        else:
            logger.error("❌ Google credentials are invalid or expired.")
            logger.error("   Re-authenticate via /admin/google-auth")
            sys.exit(1)
    return creds


def list_backups(creds, file_type='sql'):
    """List available backups in Google Drive folder."""
    drive = build('drive', 'v3', credentials=creds)

    prefix = 'backup_air_conditioners_' if file_type == 'sql' else 'media_backup_'
    query = f"'{BACKUP_FOLDER_ID}' in parents and trashed = false and name contains '{prefix}'"

    results = drive.files().list(
        q=query,
        pageSize=20,
        fields="files(id, name, size, createdTime)",
        orderBy="createdTime desc"
    ).execute()

    return results.get('files', [])


def download_file(creds, file_id, dest_path):
    """Download a file from Google Drive to a local path."""
    drive = build('drive', 'v3', credentials=creds)

    request = drive.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"\r   ⬇️  Downloading... {pct}%", end='', flush=True)
        print()  # newline after progress


def restore_sql(dump_path):
    """Restore a SQL dump into the local PostgreSQL database."""
    if sanitize_plain_sql_dump(dump_path):
        logger.info("🧹 Removed client-version-only SET commands from SQL dump.")

    env = os.environ.copy()
    env['PGPASSWORD'] = DB_PASS

    logger.info(f"🗑️  Dropping and recreating database '{DB_NAME}'...")

    # Drop all connections and recreate
    drop_cmd = [
        'psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER, '-d', 'postgres', '-c',
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{DB_NAME}' AND pid <> pg_backend_pid();"
    ]
    subprocess.run(drop_cmd, env=env, capture_output=True)

    drop_db = ['dropdb', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER, '--if-exists', DB_NAME]
    result = subprocess.run(drop_db, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"   ⚠️  dropdb warning: {result.stderr.strip()}")

    create_db = ['createdb', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER, DB_NAME]
    result = subprocess.run(create_db, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"   ❌ createdb failed: {result.stderr.strip()}")
        return False

    logger.info(f"📥 Restoring dump from '{os.path.basename(dump_path)}'...")
    restore_cmd = ['psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER, '-d', DB_NAME, '-f', dump_path]
    result = subprocess.run(restore_cmd, env=env, capture_output=True, text=True)

    if result.returncode != 0:
        # psql may return warnings that aren't fatal
        stderr = result.stderr.strip()
        if 'ERROR' in stderr:
            logger.error(f"   ❌ Restore errors:\n{stderr}")
            return False
        elif stderr:
            logger.warning(f"   ⚠️  Restore warnings (non-fatal):\n{stderr}")

    logger.info("✅ Database restored successfully!")
    return True


def restore_media(media_path):
    """Extract media archive to the media directory."""
    media_dir = os.environ.get('MEDIA_DIR', '/app/media')
    os.makedirs(media_dir, exist_ok=True)

    logger.info(f"📦 Extracting media archive to '{media_dir}'...")
    result = subprocess.run(
        ['tar', 'xzf', media_path, '-C', media_dir, '--strip-components=1'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # try without --strip-components
        result = subprocess.run(
            ['tar', 'xzf', media_path, '-C', media_dir],
            capture_output=True, text=True
        )

    if result.returncode != 0:
        logger.error(f"   ❌ Media extraction failed: {result.stderr}")
        return False

    logger.info("✅ Media files restored successfully!")
    return True


def run_alembic_upgrade():
    """Run alembic upgrade head to apply any pending migrations."""
    logger.info("🔄 Running Alembic migrations...")
    result = subprocess.run(
        ['alembic', 'upgrade', 'head'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error(f"   ❌ Alembic upgrade failed:\n{result.stderr}")
        return False
    logger.info(f"   {result.stdout.strip()}")
    logger.info("✅ Migrations applied successfully!")
    return True


def main():
    parser = argparse.ArgumentParser(description='Restore database from Google Drive backup')
    parser.add_argument('--list', action='store_true', help='List available backups')
    parser.add_argument('--file', type=str, help='Restore specific backup by filename')
    parser.add_argument('--with-media', action='store_true', help='Also restore media files')
    parser.add_argument('--skip-migrations', action='store_true', help='Skip Alembic migrations after restore')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    args = parser.parse_args()

    logger.info("🔑 Authenticating with Google Drive API...")
    creds = get_credentials()
    logger.info("   ✅ Authenticated!")

    # List mode
    if args.list:
        logger.info("\n📋 Available SQL backups:")
        for f in list_backups(creds, 'sql'):
            size_kb = int(f.get('size', 0)) // 1024 if f.get('size') else '?'
            logger.info(f"   📄 {f['name']}  ({size_kb} KB)  [{f.get('createdTime', '')}]")

        logger.info("\n📋 Available media backups:")
        for f in list_backups(creds, 'media'):
            size_mb = int(f.get('size', 0)) // (1024*1024) if f.get('size') else '?'
            logger.info(f"   📦 {f['name']}  ({size_mb} MB)  [{f.get('createdTime', '')}]")
        return

    # Find the backup to restore
    sql_files = list_backups(creds, 'sql')
    if not sql_files:
        logger.error("❌ No SQL backups found in Google Drive!")
        sys.exit(1)

    if args.file:
        target = next((f for f in sql_files if f['name'] == args.file), None)
        if not target:
            logger.error(f"❌ Backup '{args.file}' not found!")
            logger.info("Available backups:")
            for f in sql_files:
                logger.info(f"   {f['name']}")
            sys.exit(1)
    else:
        target = sql_files[0]  # Latest

    logger.info(f"\n📋 Will restore: {target['name']}")
    logger.info(f"   Target DB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

    if not args.yes:
        confirm = input("\n⚠️  This will DROP the current database! Continue? [y/N]: ")
        if confirm.lower() not in ('y', 'yes'):
            logger.info("Cancelled.")
            return

    # Download SQL dump
    with tempfile.NamedTemporaryFile(suffix='.sql', delete=False) as tmp:
        tmp_sql_path = tmp.name

    try:
        logger.info(f"\n📥 Downloading SQL dump...")
        download_file(creds, target['id'], tmp_sql_path)

        # Restore database
        if not restore_sql(tmp_sql_path):
            sys.exit(1)

        # Run Alembic migrations
        if not args.skip_migrations:
            if not run_alembic_upgrade():
                logger.warning("⚠️  Migrations failed, but database was restored.")
                logger.warning("   Run 'alembic upgrade head' manually to fix.")
    finally:
        os.unlink(tmp_sql_path)

    # Media restore
    if args.with_media:
        media_files = list_backups(creds, 'media')
        if media_files:
            # Find matching media backup (same timestamp)
            target_ts = target['name'].replace('backup_air_conditioners_', '').replace('.sql', '')
            media_target = next(
                (f for f in media_files if target_ts in f['name']),
                media_files[0]
            )

            with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp:
                tmp_media_path = tmp.name

            try:
                logger.info(f"\n📥 Downloading media archive ({media_target['name']})...")
                download_file(creds, media_target['id'], tmp_media_path)
                restore_media(tmp_media_path)
            finally:
                os.unlink(tmp_media_path)

    logger.info("\n🎉 Restore complete!")
    logger.info("   Restart the app to apply changes: docker compose restart app")


if __name__ == '__main__':
    main()
