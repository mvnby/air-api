from services.documents.base import BaseDocumentStrategy
from services.google_service import GoogleDocsService


def _doc(text: str) -> dict:
    return {
        "body": {
            "content": [
                {
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 1 + len(text),
                                "textRun": {"content": text},
                            }
                        ]
                    }
                }
            ]
        }
    }


def _delete_ranges(requests: list[dict]) -> list[tuple[int, int]]:
    return [
        (
            item["deleteContentRange"]["range"]["startIndex"],
            item["deleteContentRange"]["range"]["endIndex"],
        )
        for item in requests
    ]


def _apply_delete_requests(text: str, requests: list[dict]) -> str:
    for start, end in _delete_ranges(requests):
        text = text[: start - 1] + text[end - 1 :]
    return text


def test_google_doc_condition_removes_falsey_block():
    text = "A\n{{#if additional_conditions}}\nB {{additional_conditions}}\n{{/if}}\nC\n"

    requests = GoogleDocsService._build_conditional_block_requests(
        _doc(text),
        {"{{additional_conditions}}": ""},
    )

    assert _delete_ranges(requests) == [(3, 69)]


def test_google_doc_condition_keeps_truthy_body_and_removes_markers():
    text = "A\n{{#if additional_conditions}}\nB {{additional_conditions}}\n{{/if}}\nC\n"

    requests = GoogleDocsService._build_conditional_block_requests(
        _doc(text),
        {"{{additional_conditions}}": "Оплата после монтажа"},
    )

    assert _delete_ranges(requests) == [(61, 69), (3, 33)]


def test_google_doc_condition_removes_empty_inline_conditional_paragraph():
    text = "A\n{{#if additional_conditions}}{{additional_conditions}}{{/if}}\nC\n"

    requests = GoogleDocsService._build_conditional_block_requests(
        _doc(text),
        {"{{additional_conditions}}": ""},
    )

    assert _apply_delete_requests(text, requests) == "A\nC\n"


def test_google_doc_condition_keeps_placeholder_in_inline_conditional_paragraph():
    text = "A\n{{#if additional_conditions}}{{additional_conditions}}{{/if}}\nC\n"

    requests = GoogleDocsService._build_conditional_block_requests(
        _doc(text),
        {"{{additional_conditions}}": "Предоплата 200%"},
    )

    assert _apply_delete_requests(text, requests) == "A\n{{additional_conditions}}\nC\n"


def test_template_truthiness_ignores_blank_strings_and_empty_collections():
    assert GoogleDocsService._is_truthy_template_value("  ") is False
    assert GoogleDocsService._is_truthy_template_value([]) is False
    assert GoogleDocsService._is_truthy_template_value(["условие"]) is True


def test_additional_conditions_formatter_keeps_contract_lines_without_manual_numbering():
    assert BaseDocumentStrategy._format_additional_conditions(None) == ""
    assert BaseDocumentStrategy._format_additional_conditions("  Оплата после монтажа  ") == "Оплата после монтажа"
    assert (
        BaseDocumentStrategy._format_additional_conditions("- Монтаж в будний день\n2. Доступ к объекту")
        == "Монтаж в будний день\nДоступ к объекту"
    )
