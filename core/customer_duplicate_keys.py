"""PostgreSQL candidate keys; Python remains the final duplicate authority."""

from sqlalchemy import String, case, func, literal_column
from sqlalchemy.sql.expression import Grouping


# Python str.strip() whitespace, including legacy imported non-breaking spaces.
STRIP_CHARACTERS = "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
NON_ASCII_PATTERN = r"[^\u0001-\u007f]"


def _constant(value: str):
    # Constants must remain literals in prepared queries to match index expressions.
    return literal_column("'" + value.replace("'", "''") + "'", type_=String())


def stripped_key(column):
    return func.btrim(column, _constant(STRIP_CHARACTERS))


def phone_candidate_key(column):
    digits = func.regexp_replace(
        column, _constant("[^0-9]"), _constant(""), _constant("g")
    )
    length = func.length(digits)
    one, three, nine, ten, eleven, twelve = map(
        literal_column, ("1", "3", "9", "10", "11", "12")
    )
    return Grouping(
        case(
            (
                digits.like(_constant("375%")) & (length >= twelve),
                func.substr(digits, one, twelve),
            ),
            (
                digits.like(_constant("80%")) & (length >= eleven),
                _constant("375") + func.substr(digits, three, nine),
            ),
            (
                digits.like(_constant("0%")) & (length >= ten),
                _constant("375") + func.substr(digits, literal_column("2"), nine),
            ),
            (length == nine, _constant("375") + digits),
            else_=digits,
        )
    )


def email_candidate_key(column):
    # Kelvin sign is the only non-ASCII character whose Python lowercase is ASCII.
    # Other Unicode addresses use the conservative partial-index path below.
    return func.lower(
        func.translate(stripped_key(column), _constant("K"), _constant("K")).collate(
            "C"
        )
    )


def non_ascii_contact(column):
    return column.op("~")(_constant(NON_ASCII_PATTERN))
