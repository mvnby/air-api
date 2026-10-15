import pytest

from services.postal_address_service import normalize_postal_address


@pytest.mark.parametrize('address', [
    'д. Боровляны, Минская область, Минский район, д. 83, оф. 27',
    'Беларусь, 223053, Минская область, Минский район, д. Боровляны, д. 83, оф. 27',
    'Минский район; д. Боровляны; д. 83; оф. 27; Минская область',
    'Минская область Минский район д. Боровляны д. 83 оф. 27',
    'область Минская, район Минский, д. Боровляны, д. 83, оф. 27',
])
def test_rural_address_order_is_independent_of_source_order(address):
    result = normalize_postal_address(address, '223053')
    assert result.delivery_lines == ['д. 83, оф. 27']
    assert result.postal_line == '223053, д. Боровляны'
    assert result.area_lines == (['район Минский', 'область Минская'] if address.startswith('область') else ['Минский район', 'Минская область'])
    assert result.country == 'Республика Беларусь'
    assert result.warnings == []


@pytest.mark.parametrize('address,street,locality', [
    ('211343, г. Витебск, ул. Фестивальная, 46', 'ул. Фестивальная, 46', 'г. Витебск'),
    ('г. Минск, ул. Ленина, д. 1/А, корп. 2, кв. 12', 'ул. Ленина, д. 1/А, корп. 2, кв. 12', 'г. Минск'),
    ('Минск ул. Ленина д. 1', 'ул. Ленина, д. 1', 'Минск'),
    ('д. 1, ул. Ленина, г. Минск', 'ул. Ленина, д. 1', 'г. Минск'),
    ('Рэспубліка Беларусь, в. Сноў, вул. Мірашнічэнкі, д. 1', 'вул. Мірашнічэнкі, д. 1', 'в. Сноў'),
    ('г. Минск, а/я 140', 'а/я 140', 'г. Минск'),
])
def test_streets_premises_and_locality_are_preserved(address, street, locality):
    result = normalize_postal_address(address, '211343')
    assert result.delivery_lines == [street]
    assert result.postal_line == f'211343, {locality}'


def test_village_without_post_office_keeps_both_settlements():
    result = normalize_postal_address('д. Прости, д. 318, п/о Островки, Несвижский р-н, Минская обл.', '222612')
    assert result.delivery_lines == ['д. Прости, д. 318']
    assert result.postal_line == '222612, п/о Островки'
    assert result.area_lines == ['Несвижский р-н', 'Минская обл.']
    assert not result.warnings


def test_ambiguous_unlabelled_parts_survive_with_review_hint():
    result = normalize_postal_address('Фестивальная, 46, Витебск', '211343')
    assert result.delivery_lines == ['Фестивальная, 46, Витебск']
    assert result.postal_line == '211343'
    assert result.warnings


def test_unlabelled_street_is_not_mistaken_for_a_settlement():
    result = normalize_postal_address('Фестивальная, 46', '211343')
    assert result.delivery_lines == ['Фестивальная, 46']
    assert result.postal_line == '211343'
    assert result.warnings


def test_conflicting_postcode_is_never_silently_discarded():
    result = normalize_postal_address('220030, г. Минск, ул. Ленина, 1', '220004')
    assert '220030' in ', '.join(result.delivery_lines)
    assert any('отличается' in warning for warning in result.warnings)


def test_multiple_settlements_are_not_guessed_or_lost():
    result = normalize_postal_address('г. Минск, д. Боровляны, ул. Полевая, д. 1', '223053')
    assert result.delivery_lines == ['ул. Полевая, д. 1', 'г. Минск', 'д. Боровляны']
    assert result.postal_line == '223053'
    assert result.warnings
