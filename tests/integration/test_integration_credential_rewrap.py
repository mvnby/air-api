"""Exercise the real PostgreSQL locks and rollback used by credential rewrap."""
import json

import pytest
from sqlmodel import select

from core.config import settings
from models import AnalyticsConnection, DocumentDriveConnection
from services.analytics_connection_contracts import AnalyticsCredentialCipher
from services.document_drive_contracts import DocumentDriveCredentialCipher
from services.integration_credential_rotation_service import IntegrationCredentialRotationService


async def seed_credentials(db, monkeypatch):
    legacy = 'synthetic-legacy-auth-key-for-rewrap'
    monkeypatch.setattr(settings, 'SECRET_KEY', legacy)
    monkeypatch.setattr(settings, 'INTEGRATION_CREDENTIAL_KEYRING_JSON', '')
    analytics = AnalyticsConnection(
        tenant_id=1, storefront_id=1, provider='yandex_metrika',
        encrypted_credentials=AnalyticsCredentialCipher.encrypt(
            {'oauth_token': 'synthetic-token'}, tenant_id=1, storefront_id=1, provider='yandex_metrika'),
        credentials_fingerprint=AnalyticsCredentialCipher.fingerprint('synthetic-token'),
    )
    drive = DocumentDriveConnection(
        tenant_id=1, provider='google_drive', status='disabled', connection_key='synthetic-connection',
        encrypted_credentials=DocumentDriveCredentialCipher.encrypt(
            {'refresh_token': 'synthetic-refresh'}, tenant_id=1, provider='google_drive'),
        credentials_fingerprint=DocumentDriveCredentialCipher.fingerprint({'refresh_token': 'synthetic-refresh'}),
    )
    db.add_all([analytics, drive])
    await db.commit()
    monkeypatch.setattr(settings, 'INTEGRATION_CREDENTIAL_KEYRING_JSON', json.dumps({
        'active_key_id': 'v1', 'write_mode': 'active',
        'keys': {'v1': 'synthetic-integration-master-key-0001'}, 'legacy_secret_keys': [legacy],
    }))
    return analytics, drive


@pytest.mark.asyncio
async def test_real_postgres_rewrap_and_contract_reads(db, monkeypatch):
    analytics, drive = await seed_credentials(db, monkeypatch)
    plan = await IntegrationCredentialRotationService.plan(db)
    assert plan['counts']['legacy'] == 2
    result = await IntegrationCredentialRotationService.execute(db, plan_token=plan['plan_token'])
    await db.commit()
    assert result['rewrapped'] == 2
    payload = json.loads(settings.INTEGRATION_CREDENTIAL_KEYRING_JSON)
    payload['legacy_secret_keys'] = []
    monkeypatch.setattr(settings, 'INTEGRATION_CREDENTIAL_KEYRING_JSON', json.dumps(payload))
    assert (await IntegrationCredentialRotationService.plan(db))['complete'] is True
    assert AnalyticsCredentialCipher.decrypt(analytics.encrypted_credentials,
        tenant_id=1, storefront_id=1, provider='yandex_metrika')['oauth_token'] == 'synthetic-token'
    assert DocumentDriveCredentialCipher.decrypt(drive.encrypted_credentials,
        tenant_id=1, provider='google_drive')['refresh_token'] == 'synthetic-refresh'


@pytest.mark.asyncio
async def test_failure_halfway_rolls_back_both_domains(db, monkeypatch):
    analytics, drive = await seed_credentials(db, monkeypatch)
    original = (analytics.encrypted_credentials, drive.encrypted_credentials)
    plan = await IntegrationCredentialRotationService.plan(db)
    rewrap = IntegrationCredentialRotationService._rewrap_record

    def fail_drive(record):
        if isinstance(record.row, DocumentDriveConnection):
            raise RuntimeError('synthetic failure')
        rewrap(record)

    monkeypatch.setattr(IntegrationCredentialRotationService, '_rewrap_record', staticmethod(fail_drive))
    with pytest.raises(RuntimeError, match='synthetic failure'):
        await IntegrationCredentialRotationService.execute(db, plan_token=plan['plan_token'])
    await db.rollback()
    saved_analytics = (await db.execute(select(AnalyticsConnection))).scalar_one()
    saved_drive = (await db.execute(select(DocumentDriveConnection))).scalar_one()
    assert (saved_analytics.encrypted_credentials, saved_drive.encrypted_credentials) == original
