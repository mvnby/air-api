"""Conservative Belarus postal line ordering; never geocode or invent missing parts."""

import re

from pydantic import BaseModel, Field


class PostalAddressLines(BaseModel):
    delivery_lines: list[str] = Field(default_factory=list)
    postal_line: str
    area_lines: list[str] = Field(default_factory=list)
    country: str = "Республика Беларусь"
    warnings: list[str] = Field(default_factory=list)


_LOCALITY = re.compile(
    r"^(?:г\.|город\b|д\.(?=\s*[^\W\d_])|деревня\b|аг\.|а/г\b|агрогородок\b|"
    r"г\.?\s*п\.|р\.?\s*п\.|п\.|пос[её]лок\b|в\.|в[её]ска\b|м\.|горад\b)", re.I,
)
_STREET = re.compile(
    r"^(?:ул\.|улица\b|вул\.|вуліца\b|пр-т\b|проспект\b|просп\.|пер\.|переулок\b|"
    r"зав\.|ш\.|шоссе\b|наб\.|набережная\b|пл\.|площадь\b|туп\.|проезд\b|"
    r"тр-т\b|тракт\b|б-р\b|бульвар\b|мкр\.|микрорайон\b)", re.I,
)
_PREMISES = re.compile(r"^(?:\d|д\.|дом\b|корп\.|корпус\b|к\.|кв\.|квартира\b|оф\.|офис\b|каб\.|комн\.|пом\.|строение\b|стр\.|а/я\b|до востребования\b)", re.I)
_REGION = re.compile(r"\b(?:область|области|обл\.?|вобласць|вобл\.?)$|^(?:обл\.|область)\s", re.I)
_DISTRICT = re.compile(r"\b(?:район|района|р-н|р-на|ра[её]н|р-н\.)$|^(?:р-н|район)\s", re.I)
_POST_OFFICE = re.compile(r"^(?:п/о\b|о/с\b|опс\b|почтовое отделение\b)", re.I)
_COUNTRY = re.compile(r"^(?:(?:республика|рэспубліка)\s+)?(?:беларусь|белоруссия|belarus)$", re.I)
_POSTCODE = re.compile(r"(?<!\d)\d{6}(?!\d)")


def normalize_postal_address(address: str, postal_code: str) -> PostalAddressLines:
    """Specific → general. Uncertain fragments survive verbatim with a review hint."""
    warnings: list[str] = []
    codes = _POSTCODE.findall(address)
    if any(code != postal_code for code in codes):
        warnings.append("Индекс в адресе отличается от отдельного поля. Проверьте оба значения.")
    # Only remove the confirmed postcode; never silently discard a conflicting one.
    text = re.sub(rf"(?<!\d){re.escape(postal_code)}(?!\d)", "", address) if postal_code else address
    # Also accept pasted one-line addresses without commas before explicit units.
    text = re.sub(
        r"\s+(?=(?:г\.|д\.|аг\.|а/г\b|ул\.|вул\.|пр-т\b|пер\.|кв\.|оф\.|корп\.|п/о\b)\s*)",
        ", ", text, flags=re.I,
    )
    text = re.sub(r"([^\W\d_][\w-]*\s+(?:область|район|обл\.|р-н))\s+(?=[^,;\s])", r"\1, ", text, flags=re.I)
    parts = [" ".join(part.split()).strip() for part in re.split(r"[,;\n]+", text)]
    streets: list[str] = []
    premises: list[str] = []
    unknown: list[str] = []
    localities: list[str] = []
    offices: list[str] = []
    districts: list[str] = []
    regions: list[str] = []
    for part in filter(None, parts):
        if _COUNTRY.fullmatch(part):
            continue
        if _REGION.search(part):
            regions.append(part)
        elif _DISTRICT.search(part):
            districts.append(part)
        elif _POST_OFFICE.match(part):
            offices.append(part)
        elif _LOCALITY.match(part):
            localities.append(part)
        elif _STREET.match(part):
            streets.append(part)
        elif _PREMISES.match(part):
            premises.append(part)
        else:
            unknown.append(part)

    # A single unlabelled place ("Минск") is common. Multiple bare names cannot
    # safely distinguish a street from a settlement: retain them and ask for prefixes.
    if not localities and streets and len(unknown) == 1 and re.fullmatch(r"[^\W\d_][^\d,;]*", unknown[0]):
        localities.append(unknown.pop())
        warnings.append(f"Проверьте населённый пункт «{localities[0]}»: в исходном адресе не указан тип («г.», «д.» или «аг.»).")
    locality = ""
    delivery: list[str] = []
    if len(offices) == 1:
        locality = offices[0]
        delivery.extend(localities)  # village without its own delivery post office
    elif len(localities) == 1 and not offices:
        locality = localities[0]
    else:
        delivery.extend([*localities, *offices])
        warnings.append("Не удалось однозначно выделить населённый пункт. Уточните его с префиксом «г.», «д.» или «аг.», отделяя части адреса запятыми.")
    if unknown:
        warnings.append("Проверьте нераспознанные части адреса: " + "; ".join(unknown) + ". Для улицы используйте «ул.», для дома — «д.».")
    street_line = ", ".join([*streets, *premises]) if streets else ", ".join(
        part for part in parts if part in premises or part in unknown
    )
    if len(offices) == 1 and not streets and localities:
        street_line = ", ".join([*localities, street_line]) if street_line else ", ".join(localities)
        delivery = []
    return PostalAddressLines(
        delivery_lines=[line for line in [street_line, *delivery, *(unknown if streets else [])] if line],
        postal_line=", ".join(filter(None, [postal_code, locality])),
        area_lines=[*districts, *regions],
        warnings=warnings,
    )
