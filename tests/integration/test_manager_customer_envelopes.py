from io import BytesIO

import pytest
from pypdf import PdfReader

from core.config import settings
from models import Customer
from models.tenancy import Tenant


PARTY = {'name': 'ООО Тест', 'address': 'г. Минск, ул. Ленина, д. 1', 'postal_code': '220030'}
PAYLOAD = {'format': 'DL', 'sender': PARTY, 'recipient': PARTY}


@pytest.mark.asyncio
async def test_envelope_pdf_is_private_and_does_not_edit_customer(async_client, db):
    customer = Customer(tenant_id=1, name='Клиент', phone='+375291111112', legal_address='Сохранённый адрес')
    db.add(customer)
    await db.commit()
    url = f'/api/manager/customers/{customer.id}/envelope-pdf'
    assert (await async_client.post(url, json=PAYLOAD)).status_code == 401
    preview_url = f'/api/manager/customers/{customer.id}/envelope-preview'
    assert (await async_client.post(preview_url, json=PAYLOAD)).status_code == 401
    postcode_url = f'/api/manager/customers/{customer.id}/envelope-postcodes'
    assert (await async_client.post(postcode_url, json={'address': 'Минск, Ленина'})).status_code == 401
    login = await async_client.post('/login/access-token', data={
        'username': settings.ADMIN_USERNAME, 'password': settings.ADMIN_PASSWORD,
    })
    headers = {'Authorization': f'Bearer {login.json()["access_token"]}'}
    response = await async_client.post(url, json=PAYLOAD, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    assert 'attachment;' in response.headers['content-disposition']
    assert len(PdfReader(BytesIO(response.content)).pages) == 1
    preview = await async_client.post(preview_url, json=PAYLOAD, headers=headers)
    assert preview.status_code == 200
    assert preview.json()['recipient']['postal_line'] == '220030, г. Минск'
    await db.refresh(customer)
    assert customer.legal_address == 'Сохранённый адрес'
    assert customer.name == 'Клиент'

    invalid = {**PAYLOAD, 'recipient': {**PARTY, 'postal_code': ''}}
    assert (await async_client.post(url, json=invalid, headers=headers)).status_code == 422

    other = Tenant(slug='envelope-other', display_name='Другая компания')
    db.add(other)
    await db.flush()
    foreign = Customer(tenant_id=other.id, name='Чужой клиент', phone='123')
    db.add(foreign)
    await db.commit()
    for customer_id in (foreign.id, 999999999):
        hidden = await async_client.post(f'/api/manager/customers/{customer_id}/envelope-pdf', json=PAYLOAD, headers=headers)
        assert hidden.status_code == 404, hidden.text
        preview = await async_client.post(f'/api/manager/customers/{customer_id}/envelope-preview', json=PAYLOAD, headers=headers)
        assert preview.status_code == 404, preview.text
        lookup = await async_client.post(f'/api/manager/customers/{customer_id}/envelope-postcodes', json={'address': 'Минск, Ленина'}, headers=headers)
        assert lookup.status_code == 404, lookup.text
