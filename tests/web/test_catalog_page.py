"""11.1.1, 11.1.2, 11.1.3 — Belge Türleri ekranı: tür oluşturma, düzenleme ve pasifleştirme panelden
yapılır; Direkt türde dönüşüm listesi boş, `front_back` türde sayfa aralığı 2 olmalıdır; kabul
kriteri maddeleri eklenip çıkarılır ve değişiklik bir sonraki analizde geçerli olur. 11.1.4 —
tabloda slug sütunu yok, Durum hücresi yumuşak renkli rozetle metni de yazar.

Yalnız `TestClient`: tarayıcıda çizim görülmedi."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.prompts.page_analysis import build_page_analysis_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import (
    CATALOG_TOKEN_BUDGET,
    TOKENS_PER_TYPE,
    TypeNotFoundError,
    compile_catalog,
    export_catalog,
    import_catalog,
    load_seed_catalog,
    validate_catalog,
)
from app.config import Settings, get_settings
from app.db.models import KnownDocumentType, Upload, UploadFile
from app.pipeline.orchestrate import process_upload
from app.storage import DataLayout, find_original_by_sha256, write_to_inbox
from app.web.routers.catalog import BUDGET_UNAVAILABLE
from tests.fixtures.gen import make_text_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
SETTINGS = Settings(_env_file=None, database_url="sqlite://")
TEMPLATES = ROOT / "app" / "web" / "templates"

EDGE = "Kimlik sayfası tam görünür olmalı, kenarlar kesilmemiş"
MRZ = "MRZ iki satırı da okunabilir olmalı"


def _data(**overrides: Any) -> dict[str, Any]:
    """Tür formunun gönderdiği alanlar; `None` verilen alan hiç gönderilmez (işaretsiz kutu)."""
    data: dict[str, Any] = {
        "slug": "sample_card",
        "name": "Sample Card",
        "file_label": "Sample Card",
        "country": "RS",
        "description": "",
        "expected_file_types": ["pdf", "jpeg"],
        "pages_min": "1",
        "pages_max": "2",
        "sides": "single",
        "analyze": "on",
        "required_fields": "surname, document_number",
        "allowed_conversions": ["merge", "wrap_image"],
        "output_format": "pdf",
        "acceptance_criteria": ["Kenarlar görünür", "Yüz net"],
        "prompt_description": "",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def _rows(session_factory: sessionmaker[Session]) -> dict[str, KnownDocumentType]:
    with session_factory() as session:
        rows = {row.slug: row for row in session.scalars(select(KnownDocumentType))}
        session.expunge_all()
    return rows


def _create(client: TestClient, **overrides: Any) -> None:
    response = client.post("/document-types", data=_data(**overrides), follow_redirects=False)
    assert response.status_code == 303, response.text


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()


# --- 11.1.1: liste --------------------------------------------------------------------------------


ACTIVE_BADGE = '<span class="status-badge status-active">Etkin</span>'
PASSIVE_BADGE = '<span class="status-badge status-passive">Pasif</span>'
PANEL_CSS = ROOT / "app" / "web" / "static" / "panel.css"


def _types_table(html: str) -> str:
    found = re.search(r'<table class="catalog catalog-types">.*?</table>', html, re.S)
    assert found is not None
    return found.group(0)


def test_list_shows_every_type_with_its_state(client: TestClient, seeded: None) -> None:
    page = client.get("/document-types")

    assert page.status_code == 200
    assert "<title>Belge Türleri · belgeee</title>" in page.text
    assert 'href="/document-types/new"' in page.text
    assert "Tutarsız kayıt" not in page.text
    # 11.1.4: slug sütunu yok; slug ad bağlantısının adresinde ve `title`'ında durur.
    table = _types_table(page.text)
    assert "Slug" not in table
    assert "<code>" not in table
    assert table.count("<th>") == 9
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table.split("<tbody>")[1], re.S)
    entries = load_seed_catalog()
    assert len(rows) == len(entries)
    assert all(row.count("<td") == 9 for row in rows)
    for entry in entries:
        link = f'<a href="/document-types/{entry.slug}" title="{entry.slug}">{entry.name}</a>'
        assert link in table
    assert table.count(ACTIVE_BADGE) == len(entries)
    assert "status-passive" not in table


def test_the_type_page_still_shows_the_slug_the_list_hides(
    client: TestClient, seeded: None
) -> None:
    for entry in load_seed_catalog():
        page = client.get(f"/document-types/{entry.slug}")

        assert page.status_code == 200
        assert f"<code>{entry.slug}</code>" in page.text


def _contrast(foreground: str, background: str) -> float:
    """WCAG 2 kontrast oranı; renkler `#rrggbb`."""

    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize(
    ("rule", "color", "background"),
    [
        pytest.param("status-active", "--success", "--success-soft", id="etkin-yesilimsi"),
        pytest.param("status-passive", "--danger", "--danger-soft", id="pasif-kirmizimsi"),
    ],
)
def test_status_badges_are_soft_toned_and_their_text_stays_readable(
    rule: str, color: str, background: str
) -> None:
    css = PANEL_CSS.read_text(encoding="utf-8")
    body = re.search(rf"\.{rule}\s*\{{([^}}]*)\}}", css)
    assert body is not None, rule
    assert re.search(rf"(?<![-\w])color:\s*var\({color}\)", body.group(1))
    assert re.search(rf"background:\s*var\({background}\)", body.group(1))

    values = {
        name: re.findall(rf"{name}:\s*(#[0-9a-f]{{6}});", css) for name in (color, background)
    }
    assert all(len(found) == 1 for found in values.values()), values  # tek tanım, :root'ta
    assert _contrast(values[color][0], values[background][0]) >= 4.5


def test_the_type_table_widths_are_laid_out_for_its_nine_columns() -> None:
    css = PANEL_CSS.read_text(encoding="utf-8")

    widths = re.findall(r"\.catalog-types th:nth-child\((\d+)\) \{ width: (\d+)%; \}", css)

    assert [int(column) for column, _ in widths] == list(range(1, 10))
    assert sum(int(width) for _, width in widths) == 100


def test_empty_catalog_says_so_and_still_offers_a_new_type(client: TestClient) -> None:
    page = client.get("/document-types")

    assert page.status_code == 200
    assert "Katalogda henüz tür yok." in page.text
    assert 'href="/document-types/new"' in page.text


def test_passive_types_stay_in_the_list_marked_passive(client: TestClient) -> None:
    _create(client)
    client.post("/document-types/sample_card/deactivate")

    page = client.get("/document-types")

    table = _types_table(page.text)
    assert "<code>sample_card</code>" not in table
    assert 'title="sample_card"' in table
    assert 'class="type-passive"' in table
    assert PASSIVE_BADGE in table
    assert "status-active" not in table
    assert 'action="/document-types/sample_card/activate"' in table
    assert "/deactivate" not in page.text


def test_inconsistent_stored_type_is_flagged_and_listed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)
    with session_factory() as session:
        session.get_one(KnownDocumentType, "sample_card").direct = True  # dönüşümler dolu kaldı
        session.commit()

    page = client.get("/document-types")

    assert page.status_code == 200
    assert "Tutarsız kayıt" in page.text
    assert "allowed_conversions boş olmalı" in page.text
    # Durum rozeti ile tutarsızlık rozeti aynı hücrede yan yana (11.1.4).
    status = re.search(
        r'<td class="cell-nowrap">\s*(<span class="status-badge.*?)</td>', page.text, re.S
    )
    assert status is not None
    assert status.group(1).startswith(ACTIVE_BADGE)
    assert '<span class="badge badge-missing"' in status.group(1)


def test_notice_names_the_type_and_ignores_unknown_notices(client: TestClient) -> None:
    _create(client, name="<b>Kart</b>")

    page = client.get("/document-types?notice=created&slug=sample_card")
    assert "&lt;b&gt;Kart&lt;/b&gt;: Tür oluşturuldu." in page.text
    assert "<b>Kart</b>" not in page.text

    other = client.get("/document-types?notice=%3Cscript%3E&slug=sample_card")
    assert 'role="status"' not in other.text
    assert client.get("/document-types?notice=" + "x" * 33).status_code == 422


# --- 11.1.5: ülke süzgeci ---------------------------------------------------------------------


def _country_catalog(client: TestClient) -> None:
    """Sentetik katalog: TR (2), RU (1), ülkesiz (2)."""
    _create(client, slug="tr_one", name="TR One", file_label="TR One", country="TR")
    _create(client, slug="tr_two", name="TR Two", file_label="TR Two", country="TR")
    _create(client, slug="ru_one", name="RU One", file_label="RU One", country="RU")
    _create(client, slug="none_one", name="None One", file_label="None One", country=None)
    _create(client, slug="none_two", name="None Two", file_label="None Two", country=None)


def _row_names(table: str) -> list[str]:
    return re.findall(r'<a href="[^"]*" title="[^"]*">([^<]*)</a>', table)


ALL_NAMES = ["None One", "None Two", "RU One", "TR One", "TR Two"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param("?country=TR", ["None One", "None Two", "TR One", "TR Two"], id="tr-ve-genel"),
        pytest.param("?country=general", ["None One", "None Two"], id="yalniz-genel"),
        pytest.param("?country=all", ALL_NAMES, id="hepsi"),
        pytest.param("", ALL_NAMES, id="parametresiz"),
        pytest.param("?country=xyz", ALL_NAMES, id="gecersiz-deger"),
        pytest.param("?country=xx", ["None One", "None Two"], id="katalogda-olmayan-iso2-kod"),
        pytest.param(
            "?country=tr", ["None One", "None Two", "TR One", "TR Two"], id="kucuk-harf-kod"
        ),
    ],
)
def test_country_filter_shows_the_selected_country_plus_the_countryless_types(
    client: TestClient, query: str, expected: list[str]
) -> None:
    _country_catalog(client)

    page = client.get(f"/document-types{query}")

    table = _types_table(page.text)
    assert _row_names(table) == expected


def test_country_filter_options_are_labeled_with_counts_and_the_selection_is_marked(
    client: TestClient,
) -> None:
    _country_catalog(client)

    page = client.get("/document-types?country=TR")

    assert '<option value="all">Hepsi (5)</option>' in page.text
    assert '<option value="general">Genel — ülkesiz (2)</option>' in page.text
    assert '<option value="RU">RU (1)</option>' in page.text
    assert '<option value="TR" selected>TR (2)</option>' in page.text


def test_the_count_line_shows_the_filtered_and_the_total_count(client: TestClient) -> None:
    _country_catalog(client)

    page = client.get("/document-types?country=TR")

    assert "4 tür gösteriliyor (toplam 5)" in page.text
    assert "5 tür gösteriliyor (toplam 5)" in client.get("/document-types").text


def test_a_filter_matching_nothing_shows_the_empty_state(client: TestClient) -> None:
    empty = client.get("/document-types")
    assert "0 tür gösteriliyor (toplam 0)" in empty.text
    assert "Katalogda henüz tür yok." in empty.text

    _create(client, country="TR")

    page = client.get("/document-types?country=general")

    assert "0 tür gösteriliyor (toplam 1)" in page.text
    assert '<table class="catalog catalog-types">' not in page.text
    assert "Bu süzgeçte tür yok." in page.text
    assert "Katalogda henüz tür yok." not in page.text


def test_a_legacy_empty_country_counts_as_general(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _country_catalog(client)
    with session_factory() as session:
        row = session.get(KnownDocumentType, "ru_one")
        assert row is not None
        row.country = ""
        session.commit()

    general = client.get("/document-types?country=general")
    tr = client.get("/document-types?country=TR")

    assert _row_names(_types_table(general.text)) == ["None One", "None Two", "RU One"]
    assert _row_names(_types_table(tr.text)) == [
        "None One",
        "None Two",
        "RU One",
        "TR One",
        "TR Two",
    ]
    assert '<option value="general" selected>Genel — ülkesiz (3)</option>' in general.text
    assert '<option value="RU"' not in general.text
    assert '<option value=""' not in general.text


def test_the_filter_value_is_bounded_and_the_hidden_fields_follow_the_selection(
    client: TestClient,
) -> None:
    _country_catalog(client)

    assert client.get("/document-types?country=" + "x" * 9).status_code == 422
    assert (
        client.post(
            "/document-types/tr_one/deactivate", data={"country": "x" * 9}, follow_redirects=False
        ).status_code
        == 422
    )
    filtered = client.get("/document-types?country=RU")
    unfiltered = client.get("/document-types")

    assert filtered.text.count('<input type="hidden" name="country" value="RU">') == 3
    assert 'name="country" value=' not in unfiltered.text.split('<table class="catalog')[1]
    assert 'href="/document-types/new?country=RU"' in filtered.text
    assert 'href="/document-types/new"' in unfiltered.text


def test_deactivating_with_a_filter_keeps_it_in_the_redirect_and_the_notice(
    client: TestClient,
) -> None:
    _country_catalog(client)

    response = client.post(
        "/document-types/tr_one/deactivate", data={"country": "TR"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert (
        response.headers["location"] == "/document-types?notice=deactivated&slug=tr_one&country=TR"
    )
    page = client.get(response.headers["location"])
    assert "TR One: Tür pasifleştirildi" in page.text
    assert '<option value="TR" selected>TR (2)</option>' in page.text
    row_links = re.findall(r'href="(/document-types/tr_one\?country=TR)"', page.text)
    assert len(row_links) == 2  # ad bağlantısı ve "Düzenle"


def test_activating_without_a_filter_does_not_add_one_to_the_redirect(
    client: TestClient,
) -> None:
    _create(client)
    client.post("/document-types/sample_card/deactivate")

    response = client.post("/document-types/sample_card/activate", follow_redirects=False)

    assert response.headers["location"] == "/document-types?notice=activated&slug=sample_card"


def test_activating_with_an_invalid_filter_falls_back_to_all(client: TestClient) -> None:
    _create(client)
    client.post("/document-types/sample_card/deactivate")

    response = client.post(
        "/document-types/sample_card/activate", data={"country": "T1"}, follow_redirects=False
    )

    assert response.headers["location"] == "/document-types?notice=activated&slug=sample_card"


def test_editing_from_a_filtered_list_returns_to_the_same_filter(client: TestClient) -> None:
    _country_catalog(client)

    page = client.get("/document-types/tr_one?country=tr")

    assert page.status_code == 200
    assert '<input type="hidden" name="list_country" value="TR">' in page.text
    assert page.text.count('href="/document-types?country=TR"') == 2  # geri ve "Vazgeç"

    response = client.post(
        "/document-types/tr_one",
        data=_data(name="TR One", file_label="TR One", country="TR", list_country="TR"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/document-types?notice=updated&slug=tr_one&country=TR"
    listed = client.get(response.headers["location"])
    assert "TR One: Tür güncellendi." in listed.text
    assert '<option value="TR" selected>TR (2)</option>' in listed.text


def test_a_rejected_edit_keeps_the_filter_in_the_redrawn_form(client: TestClient) -> None:
    _country_catalog(client)

    response = client.post(
        "/document-types/tr_one",
        data=_data(name="", file_label="TR One", country="TR", list_country="TR"),
    )

    assert response.status_code == 422
    assert '<input type="hidden" name="list_country" value="TR">' in response.text
    assert 'href="/document-types?country=TR"' in response.text


def test_creating_from_a_filtered_list_returns_to_the_same_filter(client: TestClient) -> None:
    _country_catalog(client)

    page = client.get("/document-types/new?country=general")

    assert '<input type="hidden" name="list_country" value="general">' in page.text
    assert 'href="/document-types?country=general"' in page.text

    response = client.post(
        "/document-types",
        data=_data(
            slug="none_three",
            name="None Three",
            file_label="None Three",
            country=None,
            list_country="general",
        ),
        follow_redirects=False,
    )

    assert response.headers["location"] == (
        "/document-types?notice=created&slug=none_three&country=general"
    )
    listed = client.get(response.headers["location"])
    assert "None Three: Tür oluşturuldu." in listed.text
    assert _row_names(_types_table(listed.text)) == ["None One", "None Three", "None Two"]


def test_the_form_without_a_filter_carries_no_hidden_filter_field(client: TestClient) -> None:
    _create(client)

    page = client.get("/document-types/sample_card")
    new_page = client.get("/document-types/new")

    for html in (page.text, new_page.text):
        assert 'name="list_country"' not in html
        assert '<p class="back"><a href="/document-types">' in html
    response = client.post("/document-types/sample_card", data=_data(), follow_redirects=False)
    assert response.headers["location"] == "/document-types?notice=updated&slug=sample_card"


# --- 11.1.1: oluşturma ----------------------------------------------------------------------------


def test_new_type_form_offers_every_catalog_field(client: TestClient) -> None:
    page = client.get("/document-types/new")

    assert page.status_code == 200
    for name in (
        "slug",
        "name",
        "file_label",
        "country",
        "description",
        "expected_file_types",
        "pages_min",
        "pages_max",
        "sides",
        "direct",
        "analyze",
        "required_fields",
        "allowed_conversions",
        "output_format",
        "acceptance_criteria",
        "prompt_description",
    ):
        assert f'name="{name}"' in page.text, name
    assert '<form class="type-form" method="post" action="/document-types">' in page.text
    # Belge içeriği ya da etkinlik formdan değişmez.
    assert 'name="active"' not in page.text
    assert 'name="photo_rules"' not in page.text


def test_creating_a_type_stores_it_and_returns_to_the_list(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        "/document-types",
        data=_data(country="rs", pages_min="1", pages_max="2", direct=None),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/document-types?notice=created&slug=sample_card"
    row = _rows(session_factory)["sample_card"]
    assert (row.name, row.file_label, row.country) == ("Sample Card", "Sample Card", "RS")
    assert row.expected_file_types == ["pdf", "jpeg"]
    assert (row.expected_pages_min, row.expected_pages_max) == (1, 2)
    assert (row.sides, row.direct, row.analyze, row.active) == ("single", False, True, True)
    assert row.required_fields == ["surname", "document_number"]
    assert row.allowed_conversions == ["merge", "wrap_image"]
    assert row.acceptance_criteria == ["Kenarlar görünür", "Yüz net"]
    assert row.photo_rules is None
    with session_factory() as session:
        assert export_catalog(session).slugs() == ("sample_card",)
    assert "Tür oluşturuldu." in client.get(response.headers["location"]).text


def test_a_direct_type_without_conversions_is_created(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client, direct="on", allowed_conversions=None)

    row = _rows(session_factory)["sample_card"]
    assert (row.direct, row.allowed_conversions) == (True, [])


@pytest.mark.parametrize(
    ("layouts", "pages"),
    [
        pytest.param(["separate"], (2, 2), id="ayri-sayfalar"),
        pytest.param(["combined"], (1, 1), id="tek-sayfa"),
        pytest.param(["separate", "combined"], (1, 2), id="ikisi"),
    ],
)
def test_a_front_back_type_is_created_with_its_layouts_and_the_derived_range(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layouts: list[str],
    pages: tuple[int, int],
) -> None:
    # 11.1.2: sayfa aralığı elle girilmez; formda yazan 5–9 yok sayılır, düzenlerden hesaplanır.
    _create(client, sides="front_back", front_back_layouts=layouts, pages_min="5", pages_max="9")

    row = _rows(session_factory)["sample_card"]
    assert (row.sides, row.front_back_layouts) == ("front_back", layouts)
    assert (row.expected_pages_min, row.expected_pages_max) == pages


# --- 11.1.2: form doğrulaması ---------------------------------------------------------------------


def test_direct_type_with_conversions_is_refused_and_nothing_is_stored(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        "/document-types", data=_data(direct="on", allowed_conversions=["merge"])
    )

    assert response.status_code == 422
    assert "Tür kaydedilmedi" in response.text
    assert "Direkt Belge (direct: true) türünde allowed_conversions boş olmalı" in response.text
    assert _rows(session_factory) == {}
    # Girilen değerler kaybolmaz.
    assert 'value="sample_card"' in response.text
    assert re.search(r'name="direct"\s+checked', response.text)
    assert re.search(r'value="merge"\s+checked', response.text)
    assert 'value="Kenarlar görünür"' in response.text


@pytest.mark.parametrize(("low", "high"), [("2", "2"), ("1", "2"), ("", "")])
def test_front_back_type_without_a_layout_is_refused(
    client: TestClient, session_factory: sessionmaker[Session], low: str, high: str
) -> None:
    response = client.post(
        "/document-types",
        data=_data(sides="front_back", pages_min=low, pages_max=high),
    )

    assert response.status_code == 422
    assert "en az bir kabul edilen düzen" in response.text
    assert _rows(session_factory) == {}


def test_single_sided_type_with_a_layout_is_refused_and_the_choice_is_kept(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = client.post("/document-types", data=_data(front_back_layouts=["combined"]))

    assert response.status_code == 422
    assert "tek yüzlü (sides: single) türde kabul edilen düzen seçilmez" in response.text
    assert re.search(r'name="front_back_layouts" value="combined"\s+checked', response.text)
    assert not re.search(r'name="front_back_layouts" value="separate"\s+checked', response.text)
    assert _rows(session_factory) == {}


def test_every_broken_field_is_reported_together(client: TestClient) -> None:
    response = client.post(
        "/document-types",
        data=_data(
            slug="Bad Slug",
            name=" ",
            expected_file_types=None,
            pages_min="x",
            required_fields="Surname",
            output_format="png",
        ),
    )

    assert response.status_code == 422
    for message in (
        "küçük harfle başlamalı",
        "boş olamaz",
        "en az bir seçim yapılmalı",
        "sayfa sayıları tam sayı olmalı",
        "geçersiz alan adı &#39;Surname&#39;",
        "geçersiz seçim",
    ):
        assert message in response.text, message
    assert response.text.count('class="field-error"') == 6


def test_duplicate_slug_is_a_conflict_and_the_stored_type_is_kept(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    response = client.post("/document-types", data=_data(name="Başkası"))

    assert response.status_code == 409
    assert "zaten var" in response.text
    assert _rows(session_factory)["sample_card"].name == "Sample Card"


def test_the_address_of_the_new_type_form_cannot_be_a_slug(client: TestClient) -> None:
    response = client.post("/document-types", data=_data(slug="new"))

    assert response.status_code == 422
    assert "ayrılmış bir ad" in response.text


def test_rejected_form_escapes_what_was_typed(client: TestClient) -> None:
    response = client.post(
        "/document-types",
        data=_data(
            name='"><script>alert(1)</script>',
            acceptance_criteria=['"><img src=x onerror=alert(1)>'],
            direct="on",
        ),
    )

    assert response.status_code == 422
    assert "<script>alert(1)</script>" not in response.text
    assert "<img src=x" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


# --- 11.1.1: düzenleme ----------------------------------------------------------------------------


def test_edit_form_is_filled_from_the_stored_type(client: TestClient) -> None:
    _create(
        client,
        sides="front_back",
        front_back_layouts=["separate"],
        description="Açıklama",
        prompt_description="Analizciye not",
    )

    page = client.get("/document-types/sample_card")

    assert page.status_code == 200
    assert (
        '<form class="type-form" method="post" action="/document-types/sample_card">' in page.text
    )
    assert "<code>sample_card</code>" in page.text  # slug değişmez: alan değil, metin
    assert 'name="slug"' not in page.text
    assert 'value="Sample Card"' in page.text
    assert 'value="Açıklama"' in page.text
    assert 'value="surname, document_number"' in page.text
    assert 'value="Analizciye not"' in page.text
    assert 'name="pages_min" value="2"' in page.text
    assert '<option value="front_back" selected>' in page.text
    assert re.search(r'name="front_back_layouts" value="separate"\s+checked', page.text)
    assert not re.search(r'name="front_back_layouts" value="combined"\s+checked', page.text)
    assert re.search(r'value="merge"\s+checked', page.text)
    assert not re.search(r'name="direct"\s+checked', page.text)
    assert 'value="Kenarlar görünür"' in page.text and 'value="Yüz net"' in page.text


def test_unknown_type_is_a_404_on_every_route(client: TestClient) -> None:
    assert client.get("/document-types/nope").status_code == 404
    assert client.post("/document-types/nope", data=_data(slug="nope")).status_code == 404
    assert client.post("/document-types/nope/deactivate").status_code == 404
    assert client.post("/document-types/nope/activate").status_code == 404


def test_updating_a_type_writes_the_form_and_keeps_the_slug_from_the_address(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    response = client.post(
        "/document-types/sample_card",
        data=_data(
            slug="baska_slug",
            name="Yeni Ad",
            pages_min="1",
            pages_max="3",
            allowed_conversions=["render_image"],
            required_fields="surname",
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/document-types?notice=updated&slug=sample_card"
    rows = _rows(session_factory)
    assert set(rows) == {"sample_card"}
    row = rows["sample_card"]
    assert (row.name, row.expected_pages_max, row.required_fields) == ("Yeni Ad", 3, ["surname"])
    assert row.allowed_conversions == ["render_image"]
    assert (
        "bir sonraki analizden itibaren geçerlidir" in client.get(response.headers["location"]).text
    )


def test_a_type_that_disappears_while_saving_is_a_404_and_nothing_is_kept(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(client)

    def vanished(_session: Session, _entry: object) -> bool:
        raise TypeNotFoundError("sample_card")

    monkeypatch.setattr("app.web.routers.catalog.update_type", vanished)

    assert client.post("/document-types/sample_card", data=_data()).status_code == 404


def test_updating_leaves_activity_and_photo_rules_to_their_own_actions(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)
    client.post("/document-types/sample_card/deactivate")
    with session_factory() as session:
        session.get_one(KnownDocumentType, "sample_card").photo_rules = {"face_visible": True}
        session.commit()

    # Form bu alanları taşımaz; gönderilse de okunmaz.
    client.post(
        "/document-types/sample_card",
        data=_data(name="Ad", active="on", photo_rules='{"face_visible": false}'),
    )

    row = _rows(session_factory)["sample_card"]
    assert (row.name, row.active, row.photo_rules) == ("Ad", False, {"face_visible": True})


def test_an_invalid_update_changes_nothing_and_redraws_the_form(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    response = client.post(
        "/document-types/sample_card",
        data=_data(name="Değişmesin", direct="on", allowed_conversions=["merge"]),
    )

    assert response.status_code == 422
    assert "allowed_conversions boş olmalı" in response.text
    assert 'value="Değişmesin"' in response.text
    assert _rows(session_factory)["sample_card"].name == "Sample Card"


def test_a_stored_type_that_breaks_the_catalog_rules_opens_and_is_fixed_by_saving(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)
    with session_factory() as session:
        session.get_one(KnownDocumentType, "sample_card").direct = True
        session.commit()
    with session_factory() as session, pytest.raises(Exception, match="allowed_conversions"):
        export_catalog(session)  # analiz kataloğu bu satır yüzünden okunamıyor

    page = client.get("/document-types/sample_card")

    assert page.status_code == 200
    assert "Kayıtlı tür şu an katalog kurallarına uymuyor" in page.text
    assert "allowed_conversions boş olmalı" in page.text
    client.post("/document-types/sample_card", data=_data(direct="on", allowed_conversions=None))
    with session_factory() as session:
        assert export_catalog(session).get("sample_card").allowed_conversions == ()  # type: ignore[union-attr]


# --- 11.1.1: pasifleştirme ------------------------------------------------------------------------


def test_deactivating_keeps_the_type_and_takes_it_out_of_the_analysis(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    response = client.post("/document-types/sample_card/deactivate", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/document-types?notice=deactivated&slug=sample_card"
    assert _rows(session_factory)["sample_card"].active is False
    with session_factory() as session:
        catalog = export_catalog(session)
        assert catalog.get("sample_card") is not None  # silinmedi
        assert "sample_card" not in build_page_analysis_instructions(catalog).known_slugs
    assert "yeni belgelere atanmaz" in client.get(response.headers["location"]).text


def test_a_passive_type_can_be_activated_again(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)
    client.post("/document-types/sample_card/deactivate")

    response = client.post("/document-types/sample_card/activate", follow_redirects=False)

    assert response.headers["location"] == "/document-types?notice=activated&slug=sample_card"
    assert _rows(session_factory)["sample_card"].active is True
    with session_factory() as session:
        catalog = export_catalog(session)
        assert "sample_card" in build_page_analysis_instructions(catalog).known_slugs


def test_deactivating_twice_is_harmless(client: TestClient) -> None:
    _create(client)

    first = client.post("/document-types/sample_card/deactivate", follow_redirects=False)
    second = client.post("/document-types/sample_card/deactivate", follow_redirects=False)

    assert first.status_code == second.status_code == 303


def test_there_is_no_way_to_delete_a_type(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    for method in ("DELETE", "PUT", "PATCH"):
        assert client.request(method, "/document-types/sample_card").status_code == 405
    paths = app.openapi()["paths"]
    assert [path for path in paths if path.startswith("/document-types") and "delete" in path] == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(KnownDocumentType)) == 1


def test_catalog_forms_carry_no_multiline_text_field_and_post_to_plain_paths() -> None:
    # 10.9.1 kilidi şablonlarda çok satırlı metin alanına ve hesaplanmış `action` yoluna izin
    # vermez.
    for name in ("catalog.html", "catalog_form.html", "catalog_criteria.html"):
        html = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "<textarea" not in html, name
        assert 'action="{{' not in html, name


# --- 11.1.3: kabul kriteri maddeleri --------------------------------------------------------------


def test_the_form_ends_the_criteria_with_a_blank_row_for_adding_without_scripts(
    client: TestClient,
) -> None:
    _create(client)

    page = client.get("/document-types/sample_card")

    rows = re.findall(r'name="acceptance_criteria" value="([^"]*)"', page.text)
    assert rows == ["Kenarlar görünür", "Yüz net", ""]
    assert 'hx-post="/document-types/criteria/add"' in page.text
    assert page.text.count('hx-post="/document-types/criteria/remove"') == 3


def test_add_returns_the_list_with_one_more_blank_row_and_saves_nothing(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    response = client.post(
        "/document-types/criteria/add", data={"acceptance_criteria": ["Bir", "İki"]}
    )

    assert response.status_code == 200
    assert response.text.lstrip().startswith('<div id="criteria">')
    assert re.findall(r'name="acceptance_criteria" value="([^"]*)"', response.text) == [
        "Bir",
        "İki",
        "",
    ]
    assert _rows(session_factory)["sample_card"].acceptance_criteria == [
        "Kenarlar görünür",
        "Yüz net",
    ]


def test_add_to_an_empty_list_gives_one_blank_row(client: TestClient) -> None:
    response = client.post("/document-types/criteria/add")

    assert re.findall(r'name="acceptance_criteria" value="([^"]*)"', response.text) == [""]


def test_remove_drops_the_chosen_row_only(client: TestClient) -> None:
    response = client.post(
        "/document-types/criteria/remove",
        data={"index": "1", "acceptance_criteria": ["Bir", "İki", "Üç"]},
    )

    assert re.findall(r'name="acceptance_criteria" value="([^"]*)"', response.text) == [
        "Bir",
        "Üç",
    ]
    # Kalan satırların çıkarma düğmeleri yeni sıraya göre numaralanır.
    assert re.findall(r"hx-vals='\{\"index\": (\d+)\}'", response.text) == ["0", "1"]


def test_remove_outside_the_list_changes_nothing_and_a_negative_index_is_refused(
    client: TestClient,
) -> None:
    kept = client.post(
        "/document-types/criteria/remove", data={"index": "9", "acceptance_criteria": ["Bir"]}
    )

    assert re.findall(r'name="acceptance_criteria" value="([^"]*)"', kept.text) == ["Bir"]
    refused = client.post(
        "/document-types/criteria/remove", data={"index": "-1", "acceptance_criteria": ["Bir"]}
    )
    assert refused.status_code == 422


def test_criteria_fragment_escapes_the_text(client: TestClient) -> None:
    response = client.post(
        "/document-types/criteria/add", data={"acceptance_criteria": ['"><script>x</script>']}
    )

    assert "<script>" not in response.text
    assert "&#34;&gt;&lt;script&gt;x&lt;/script&gt;" in response.text


def test_saving_adds_and_removes_criteria_and_drops_blank_rows(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client, acceptance_criteria=["Bir", "İki", "Üç"])

    client.post(
        "/document-types/sample_card",
        data=_data(acceptance_criteria=["Bir", "", "Üç", "Dört", "   "]),
    )

    assert _rows(session_factory)["sample_card"].acceptance_criteria == ["Bir", "Üç", "Dört"]


def test_all_criteria_can_be_removed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)

    client.post("/document-types/sample_card", data=_data(acceptance_criteria=None))

    assert _rows(session_factory)["sample_card"].acceptance_criteria == []
    with session_factory() as session:
        assert export_catalog(session).get("sample_card").acceptance_criteria == ()  # type: ignore[union-attr]


def _section(instructions: str, slug: str) -> str:
    """Talimatın `slug` türüne ayrılmış bölümü (tohumda birkaç tür aynı maddeyi taşır)."""
    start = instructions.index(f"### `{slug}`")
    end = instructions.find("\n### ", start + 1)
    return instructions[start : end if end != -1 else None]


def _passport_batch(session: Session, layout: DataLayout) -> Upload:
    upload = Upload(id="u_20260918_0001", channel="web")
    session.add(upload)
    session.flush()
    content = make_text_pdf_bytes(["PASAPORT"])
    stored = write_to_inbox(layout, upload.id, "pasaport.pdf", content)
    original = find_original_by_sha256(session, stored.sha256)
    session.add(
        UploadFile(
            upload=upload,
            original_name="pasaport.pdf",
            stored_path=layout.relative(stored.path),
            sha256=stored.sha256,
            mime="application/pdf",
            is_duplicate_of=None if original is None else original.id,
        )
    )
    session.commit()
    return upload


def test_an_edit_reaches_the_next_analysis_and_only_that_one(
    client: TestClient,
    seeded: None,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    with session_factory() as session:
        before = build_page_analysis_instructions(export_catalog(session)).text
    assert EDGE in before and MRZ in before

    # Pasaportun kabul kriterlerinden biri çıkarılır, bir yenisi eklenir (panelden).
    passport = client.get("/document-types/russian_passport")
    assert f'value="{EDGE}"' in passport.text
    response = client.post(
        "/document-types/russian_passport",
        data=_data(
            slug="russian_passport",
            name="Russian Passport",
            file_label="Passport",
            country="RU",
            pages_min="1",
            pages_max="1",
            direct="on",
            allowed_conversions=None,
            output_format="keep",
            required_fields="surname, given_names, date_of_birth, document_number, expiry_date",
            acceptance_criteria=[MRZ, "Fotoğraf parlamasız olmalı"],
        ),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text

    with session_factory() as session:
        provider = RecordingProvider.from_directory(RECORDINGS / "russian_passport")
        upload = _passport_batch(session, layout)
        process_upload(session, layout, upload, settings=SETTINGS, provider=provider)

    (request,) = provider.requests
    passport_section = _section(request.instructions, "russian_passport")
    assert "Fotoğraf parlamasız olmalı" in passport_section
    assert MRZ in passport_section
    assert EDGE not in passport_section  # çıkarılan madde bu analize girmedi
    # Aynı maddeyi taşıyan öbür türlere dokunulmadı; önceki analizin talimatı da olduğu gibi.
    assert EDGE in request.instructions
    assert EDGE in _section(before, "russian_passport")


# --- 11.4.3: katalog bütçesi görünür ------------------------------------------------------------


def _budget_line(html: str) -> str:
    found = re.search(r'<p class="catalog-budget" id="catalog-budget">(.*?)</p>', html, re.S)
    assert found is not None
    return re.sub(r"<[^>]+>", "", found.group(1))


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _configure_budget(app: FastAPI, budget: int | None) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", catalog_token_budget=budget
    )


def _many_types(session_factory: sessionmaker[Session], count: int, *, active: bool = True) -> None:
    records = [
        {
            **_data(),
            "slug": f"bulk_type_{index:03d}",
            "name": f"Bulk Type {index:03d}",
            "file_label": f"Bulk Type {index:03d}",
            "expected_file_types": ["pdf", "jpeg"],
            "expected_pages": {"min": 1, "max": 2},
            "required_fields": ["surname", "document_number"],
            "allowed_conversions": ["merge", "wrap_image"],
            "acceptance_criteria": ["Kenarlar görünür"],
            "prompt_description": "Üstte arma, solda fotoğraf, altta makine okunur bölge.",
            "direct": False,
            "analyze": True,
            "active": active,
        }
        for index in range(count)
    ]
    for record in records:
        for key in ("pages_min", "pages_max", "description"):
            record.pop(key, None)
    with session_factory() as session:
        import_catalog(session, validate_catalog(records))
        session.commit()


def test_list_shows_the_active_types_and_the_estimated_tokens_of_the_catalog_text(
    client: TestClient, seeded: None, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        stored = export_catalog(session)
    expected = compile_catalog(stored, token_budget=CATALOG_TOKEN_BUDGET)

    page = client.get("/document-types")

    assert page.status_code == 200
    line = _budget_line(page.text)
    assert f"Aktif tür: {len(expected.known_slugs)} ·" in line
    assert f"≈ {_thousands(expected.estimated_tokens)} token, tahmini" in line
    assert f"bütçe {_thousands(CATALOG_TOKEN_BUDGET)}, tür sayısıyla ölçekli" in line
    assert expected.shortened_slugs == ()
    assert 'id="catalog-budget-warning"' not in page.text


def test_the_budget_line_does_not_change_with_the_country_filter(
    client: TestClient, seeded: None
) -> None:
    unfiltered = _budget_line(client.get("/document-types").text)

    assert _budget_line(client.get("/document-types?country=general").text) == unfiltered
    assert _budget_line(client.get("/document-types?country=RU").text) == unfiltered


def test_budget_scales_with_the_active_types_and_passive_ones_do_not_count(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _many_types(session_factory, 60)
    with session_factory() as session:
        for index in range(10):
            session.get_one(KnownDocumentType, f"bulk_type_{index:03d}").active = False
        session.commit()

    page = client.get("/document-types")

    line = _budget_line(page.text)
    assert "Aktif tür: 50 ·" in line
    assert f"bütçe {_thousands(50 * TOKENS_PER_TYPE)}, tür sayısıyla ölçekli" in line
    assert 'id="catalog-budget-warning"' not in page.text


def test_shortened_descriptions_are_warned_and_linked_to_their_types(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _many_types(session_factory, 30)
    _configure_budget(app, 1200)
    with session_factory() as session:
        expected = compile_catalog(export_catalog(session), token_budget=1200)
    assert expected.shortened_slugs

    page = client.get("/document-types")

    assert page.status_code == 200
    assert "bütçe 1.200, CATALOG_TOKEN_BUDGET ayarından" in _budget_line(page.text)
    warning = re.search(r'<div class="notice catalog-budget-warning".*?</div>', page.text, re.S)
    assert warning is not None
    box = warning.group(0)
    assert f"{len(expected.shortened_slugs)} türün tanımı kesiliyor — küme büyük." in box
    for slug in expected.shortened_slugs:
        assert f'<a href="/document-types/{slug}">' in box
        # Uyarı listesi slug'ı gösterir; tablo göstermez (11.1.4).
        assert f"<code>{slug}</code>" in box
        assert f"<code>{slug}</code>" not in _types_table(page.text)
    if expected.over_budget:
        assert "Tanımlar kısaltıldığı hâlde metin bütçeyi aşıyor." in box


def test_showing_the_budget_logs_no_warning(
    client: TestClient,
    app: FastAPI,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _many_types(session_factory, 30)
    _configure_budget(app, 1200)
    caplog.set_level(logging.WARNING, logger="app.catalog.prompt_builder")

    client.get("/document-types")

    assert caplog.records == []


def test_inconsistent_catalog_says_the_text_cannot_be_measured(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _create(client)
    with session_factory() as session:
        session.get_one(KnownDocumentType, "sample_card").direct = True
        session.commit()

    page = client.get("/document-types")

    assert page.status_code == 200
    assert BUDGET_UNAVAILABLE in page.text
    assert 'class="catalog-budget"' not in page.text


def test_empty_catalog_shows_no_active_types(client: TestClient) -> None:
    page = client.get("/document-types")

    assert "Aktif tür: 0 ·" in _budget_line(page.text)
