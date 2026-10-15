import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.unit.alembic_chain_test_support import assert_revision_in_single_head_chain


def test_branding_migration_keeps_existing_issuers_and_has_one_head():
    scripts = ScriptDirectory.from_config(Config('alembic.ini'))
    assert_revision_in_single_head_chain(scripts, 't1155env01')
    spec = importlib.util.spec_from_file_location('issuer_envelope_migration', Path('alembic/versions/t1155env01_add_issuer_envelope_branding.py'))
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///:memory:')
    try:
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE document_legal_entity (id INTEGER PRIMARY KEY, display_name TEXT NOT NULL)'))
            connection.execute(text("INSERT INTO document_legal_entity VALUES (1, 'Компания')"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            assert connection.execute(text('SELECT display_name, envelope_branding FROM document_legal_entity')).one() == ('Компания', '{}')
            migration.downgrade()
            assert 'envelope_branding' not in {item['name'] for item in inspect(connection).get_columns('document_legal_entity')}
            assert connection.execute(text('SELECT display_name FROM document_legal_entity')).scalar() == 'Компания'
    finally:
        engine.dispose()
