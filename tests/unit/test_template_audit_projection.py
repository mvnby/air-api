from modules.documents.application.template_audit import occurrence_page


def test_occurrences_are_bounded_and_continue_inside_one_long_block():
    phrase = "Одинаковая оговорка."
    text = ("контекст " + phrase + " окончание.\n") * 250
    blocks = [
        {
            "block_id": "same-block",
            "part": "word/document.xml",
            "location": "/document/body/p[1]",
            "original_text": text,
        }
    ]
    pages = [occurrence_page(blocks, phrase, page) for page in (1, 2, 3)]
    assert [len(page["occurrences"]) for page in pages] == [100, 100, 50]
    assert [page["occurrences_next_page"] for page in pages] == [2, 3, None]
    assert all(page["occurrences_total"] == 250 for page in pages)
    matches = [entry for page in pages for entry in page["occurrences"]]
    assert len({entry["match_offset"] for entry in matches}) == 250
    assert all(
        len(entry["text"]) <= 820 and entry["block_id"] == "same-block"
        for entry in matches
    )
    assert all(
        text[entry["match_offset"] : entry["match_offset"] + entry["matched_length"]]
        == phrase
        for entry in matches
    )


def test_legal_basis_change_preserves_decision_but_marks_it_outdated():
    from types import SimpleNamespace
    from modules.documents.application.template_audit import decision_is_current

    report = SimpleNamespace(
        source_hash="source", context_hash="context", legal_sources_hash="law-current"
    )
    history = [
        {
            "source_hash": "source",
            "context_hash": "context",
            "legal_sources_hash": "law-current",
            "proposed_text": "old wording",
            "applicability": "company",
            "to": "accepted",
        }
    ]
    finding = {
        "status": "accepted",
        "proposed_text": "old wording",
        "applicability": "company",
        "decision_history": history,
    }
    assert decision_is_current(finding, report) is True
    report.legal_sources_hash = "law-new-edition"
    assert decision_is_current(finding, report) is False
    assert finding["status"] == "accepted" and finding["decision_history"] == history
