"""Prepare bounded, attributable text from selected tender originals."""

from schemas_connector_tender_review import AnalyzedTenderFile
from schemas_tender_document_reader import TenderDocumentReadResult
from schemas_tender_qualification import TenderDocumentFragment
from services.belzakupki_source_analysis import MAX_TENDER_TEXT_CHARS
from services.tender_document_reader import fragment_location
from services.tender_qualification import MAX_FRAGMENTS


class TenderOriginalEvidence:
    def __init__(self) -> None:
        self.documents: list[AnalyzedTenderFile] = []
        self.fragments: list[TenderDocumentFragment] = []
        self._text_chars = 0

    def add_timeout(self, document_id: str, filename: str | None) -> None:
        self.documents.append(AnalyzedTenderFile(
            document_id=document_id, filename=filename, status="timeout",
            diagnostics=["Истекло время чтения выбранных оригиналов. Проверьте этот файл отдельно."],
        ))

    def add(self, original: TenderDocumentReadResult, filename: str | None) -> None:
        file = AnalyzedTenderFile(
            document_id=original.document_id, filename=original.filename or filename, status=original.status,
            sha256=original.sha256, diagnostics=original.diagnostics.copy(), origin=original.origin,
        )
        self.documents.append(file)
        if original.origin == "saved_original":
            file.diagnostics.append("Прочитана сохранённая копия. Актуальность у источника не подтверждена.")
        parts = [part for part in original.fragments if part.ocr_reliable is not False]
        start = len(self.fragments)
        for part in parts:
            if len(self.fragments) == MAX_FRAGMENTS or self._text_chars + len(part.text) > MAX_TENDER_TEXT_CHARS:
                file.status = "over_analysis_limit"
                checked = len(self.fragments) - start
                file.diagnostics.append(
                    f"В лимит анализа вошло {checked} из {len(parts)} читаемых фрагментов. Проверьте остальное в оригинале."
                )
                break
            self._text_chars += len(part.text)
            self.fragments.append(TenderDocumentFragment(
                document_id=original.document_id, filename=(file.filename or "Оригинал")[:500],
                text=part.text, location=fragment_location(part), document_sha256=original.sha256,
                partial=original.status != "complete" or original.origin == "saved_original",
            ))

    @property
    def all_documents_complete(self) -> bool:
        return bool(self.documents) and all(
            file.status == "complete" and file.origin == "source" for file in self.documents
        )
