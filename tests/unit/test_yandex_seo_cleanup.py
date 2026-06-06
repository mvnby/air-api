import csv

from scripts.seo.generate_legacy_server_rules import _render_apache, _render_nginx
from scripts.seo.yandex_duplicate_cleanup import generate_report


def _write_export(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Count", "LastAccess", "Url", "Value"])
        writer.writeheader()
        writer.writerows(rows)


def test_yandex_duplicate_cleanup_generates_reviewable_artifacts(tmp_path):
    title_csv = tmp_path / "title.csv"
    description_csv = tmp_path / "description.csv"
    output_dir = tmp_path / "seo"

    _write_export(
        title_csv,
        [
            {"Count": "14", "LastAccess": "", "Url": "", "Value": "Товар не найден!"},
            {"Count": "", "LastAccess": "2026-01-16", "Url": "/split/mhi/mhi-zmx/mhi-25zmx", "Value": ""},
            {
                "Count": "",
                "LastAccess": "2020-08-05",
                "Url": "/index.php?_route_=split/haier/lightera/",
                "Value": "",
            },
        ],
    )
    _write_export(
        description_csv,
        [
            {
                "Count": "655",
                "LastAccess": "",
                "Url": "",
                "Value": "Кондиционеры в Витебске. Продажа, монтаж, обслуживание",
            },
            {
                "Count": "",
                "LastAccess": "2026-05-30",
                "Url": "/product/split-sistema-haier-tundra/",
                "Value": "",
            },
            {"Count": "", "LastAccess": "2026-01-31", "Url": "/success/", "Value": ""},
            {"Count": "", "LastAccess": "2025-11-30", "Url": "/m-hisence", "Value": ""},
        ],
    )

    rows = generate_report(title_csv, description_csv, output_dir, "https://mvn.by")
    by_url = {row["url"]: row for row in rows}

    assert by_url["/split/mhi/mhi-zmx/mhi-25zmx"]["expected_http_or_indexing_state"] == "410"
    assert by_url["/index.php?_route_=split/haier/lightera/"]["target_url"] == "/split/haier/lightera/"
    assert by_url["/index.php?_route_=split/haier/lightera/"]["expected_http_or_indexing_state"] == "301"
    assert by_url["/product/split-sistema-haier-tundra/"]["classification"] == "current_product_page"
    assert "generate_unique_meta_description" in by_url["/product/split-sistema-haier-tundra/"]["recommended_action"]
    assert by_url["/success/"]["expected_http_or_indexing_state"] == "noindex; excluded from sitemap"
    assert by_url["/m-hisence"]["expected_http_or_indexing_state"] == "410"

    assert (output_dir / "yandex_url_action_matrix.csv").exists()
    assert "https://mvn.by/split/mhi/mhi-zmx/mhi-25zmx" in (output_dir / "yandex_dead_urls.txt").read_text()
    assert "https://mvn.by/product/split-sistema-haier-tundra/" in (output_dir / "yandex_indexnow_urls.txt").read_text()


def test_legacy_server_rules_are_exact_and_do_not_add_broad_clean_param_rules():
    apache = _render_apache()
    nginx = _render_nginx()

    assert "Clean-param:" not in apache
    assert "Clean-param:" not in nginx
    assert "product_id=294" in apache
    assert '"/split?product_id=294"' in nginx
    assert "/index.php?_route_=split/haier/haier-home/" in nginx
    assert "m\\-hisence" in apache
