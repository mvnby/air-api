"""Expose explicit installation phrases without guessing room/product mappings."""

import re

from schemas_belzakupki_enrichment import SourceInstallationFact


_INSTALLATION = re.compile(r"\b(?:трасс\w*|коммуникац\w*|кабинет\w*|помещен\w*|комнат\w*|креплен\w*|электропитан\w*|питан\w*|кабел\w*)\b", re.I)


def installation_facts(enrichment: dict) -> list[SourceInstallationFact]:
    facts: list[SourceInstallationFact] = []
    seen: set[str] = set()
    for field in ("equipment_details", "work_summary"):
        text = str(enrichment.get(field) or "")[:10000]
        for segment in re.split(r"[;\n]+|(?<!\d)\.\s+", text):
            cleaned = " ".join(segment.split()).strip(" .")
            if not cleaned or not _INSTALLATION.search(cleaned) or cleaned.casefold() in seen:
                continue
            excerpts = [cleaned] if len(cleaned) <= 700 else [
                "…" + cleaned[max(0, match.start() - 80):min(len(cleaned), match.end() + 180)].strip() + "…"
                for match in _INSTALLATION.finditer(cleaned)
            ]
            for excerpt in excerpts:
                if excerpt.casefold() in seen:
                    continue
                seen.add(excerpt.casefold())
                facts.append(SourceInstallationFact(text=excerpt, source=f"reviewed_{field}", is_excerpt=len(cleaned) > 700))
                if len(facts) == 12:
                    return facts
    return facts
