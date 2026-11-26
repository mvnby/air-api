"""Prepare bounded, attributable text from selected tender originals."""

from schemas_connector_tender_review import AnalyzedTenderFile
from schemas_tender_document_reader import TenderDocumentFragment as ReadFragment, TenderDocumentReadResult
from schemas_tender_qualification import TenderDocumentFragment
from services.belzakupki_source_analysis import MAX_TENDER_TEXT_CHARS
from services.tender_document_reader import fragment_location
from services.tender_qualification import MAX_FRAGMENTS


def _bounded_parts(parts: list[ReadFragment], chars: int, fragments: int) -> list[ReadFragment]:
    members: dict[str | None, list[ReadFragment]] = {}
    for part in parts:
        members.setdefault(part.archive_member, []).append(part)
    selected = []
    for left, group in zip(range(len(members), 0, -1), members.values()):
        group_chars = chars // left
        group_fragments = fragments // left
        for part in group:
            if group_fragments == 0:
                break
            size = len(part.text)
            if size > group_chars:
                continue
            selected.append(part)
            chars -= size
            fragments -= 1
            group_chars -= size
            group_fragments -= 1
    return selected


class TenderOriginalEvidence:
    def __init__(self, selected_count: int = 1) -> None:
        self.documents: list[AnalyzedTenderFile] = []
        self.fragments: list[TenderDocumentFragment] = []
        self._text_chars = 0
        self._selected_count = selected_count

    def add_timeout(self, document_id: str, filename: str | None) -> None:
        self.documents.append(AnalyzedTenderFile(
            document_id=document_id, filename=filename, status="timeout",
            diagnostics=["Истекло время чтения выбранных оригиналов. Проверьте этот файл отдельно."],
        ))

    def add(self, original: TenderDocumentReadResult, filename: str | None) -> None:
        remaining = max(1, self._selected_count - len(self.documents))
        file = AnalyzedTenderFile(
            document_id=original.document_id, filename=original.filename or filename, status=original.status,
            sha256=original.sha256, diagnostics=original.diagnostics.copy(), origin=original.origin,
        )
        self.documents.append(file)
        if original.origin == "saved_original":
            file.diagnostics.append("Прочитана сохранённая копия. Актуальность у источника не подтверждена.")
        parts = [part for part in original.fragments if part.ocr_reliable is not False]
        selected = _bounded_parts(
            parts, (MAX_TENDER_TEXT_CHARS - self._text_chars) // remaining,
            (MAX_FRAGMENTS - len(self.fragments)) // remaining,
        )
        if len(selected) < len(parts):
            file.status = "over_analysis_limit"
            file.diagnostics.append(
                f"В лимит анализа вошло {len(selected)} из {len(parts)} читаемых фрагментов. Проверьте остальное в оригинале."
            )
        for part in selected:
            self._text_chars += len(part.text)
            self.fragments.append(TenderDocumentFragment(
                document_id=original.document_id, filename=(file.filename or "Оригинал")[:500],
                text=part.text, location=fragment_location(part), document_sha256=original.sha256,
                partial=file.status != "complete" or original.origin == "saved_original",
            ))

    @property
    def all_documents_complete(self) -> bool:
        return bool(self.documents) and all(
            file.status == "complete" and file.origin == "source" for file in self.documents
        )
