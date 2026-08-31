from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from num2words import num2words


def money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def quantity(value: Decimal) -> str:
    return format(value.normalize(), "f")


def number_in_words(value: Decimal) -> str:
    return str(num2words(value, lang="ru"))


def amount_in_words(amount: Decimal) -> str:
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rubles = int(rounded)
    kopecks = int((rounded - rubles) * 100)
    ruble_word = _plural(
        rubles, "белорусский рубль", "белорусских рубля", "белорусских рублей"
    )
    kopeck_word = _plural(kopecks, "копейка", "копейки", "копеек")
    return (
        f"{num2words(rubles, lang='ru')} {ruble_word} {kopecks:02d} {kopeck_word}"
    ).capitalize()


def _plural(value: int, one: str, few: str, many: str) -> str:
    if value % 100 in {11, 12, 13, 14}:
        return many
    if value % 10 == 1:
        return one
    if value % 10 in {2, 3, 4}:
        return few
    return many
