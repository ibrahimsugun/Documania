"""Belge Türleri'nde arama (PRD 11.1.8, PLAN.md §D133): `q` türün adında, dosya etiketinde ve
slug'ında harf büyüklüğü/aksan/Türkçe i-İ duyarsız alt dize olarak aranır, ülke süzgeciyle AND
birleşir; arama ülke gibi bağlantılarda, toplu işlemde ve yönlendirmelerde korunur, yalnız okur."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Event, KnownDocumentType
from app.web.auth import SESSION_COOKIE
from app.web.routers.catalog import _search_key
from tests.web.flash import flashed


def _data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "slug": "sample_card",
        "name": "Sample Card",
        "file_label": "Sample Card",
        "country": "RS",
        "expected_file_types": ["pdf"],
        "pages_min": "1",
        "pages_max": "1",
        "sides": "single",
        "allowed_conversions": ["merge"],
        "output_format": "pdf",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def _create(client: TestClient, slug: str, name: str, label: str, country: str | None) -> None:
    response = client.post(
        "/document-types",
        data=_data(slug=slug, name=name, file_label=label, country=country),
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


@pytest.fixture
def catalog(client: TestClient) -> None:
    """Sentetik katalog: adında, etiketinde ya da slug'ında "geçiş" geçen üç tür ve ilgisizler."""
    _create(client, "transit_tr", "Geçiş Belgesi", "Gecis Belgesi", "TR")
    _create(client, "border_ru", "Sınır Kartı", "Geçiş Kartı", "RU")
    _create(client, "gecis_izni", "Izin Formu", "Izin Formu", None)
    _create(client, "ikamet_tr", "İkamet İzni", "Ikamet Izni", "TR")
    _create(client, "cafe_card", "Café Kartı", "Cafe Karti", None)


def _names(html: str) -> list[str]:
    results = html.split('<div id="catalog-results">', 1)[1]
    return re.findall(r'<td><a href="[^"]*" title="[^"]*">([^<]*)</a></td>', results)


def test_the_search_key_folds_case_accents_and_turkish_i() -> None:
    assert _search_key("GEÇİŞ") == _search_key("geçiş") == _search_key("gecis") == "gecis"
    assert _search_key("IŞIK") == _search_key("ışık") == _search_key("Işık") == "isik"
    assert _search_key("İkamet") == _search_key("ikamet") == "ikamet"
    assert _search_key("Café") == "cafe"
    assert _search_key("ise-giris_belge") == _search_key("ise giris  belge") == "ise giris belge"
    assert _search_key(" -- ") == ""


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param("geçiş", ["Geçiş Belgesi", "Izin Formu", "Sınır Kartı"], id="ad-etiket-slug"),
        pytest.param("GEÇİŞ", ["Geçiş Belgesi", "Izin Formu", "Sınır Kartı"], id="buyuk-harf"),
        pytest.param("gecis", ["Geçiş Belgesi", "Izin Formu", "Sınır Kartı"], id="aksansiz"),
        pytest.param("IKAMET", ["İkamet İzni"], id="noktasiz-I"),
        pytest.param("ıkamet", ["İkamet İzni"], id="noktasiz-kucuk-i"),
        pytest.param("izni", ["İkamet İzni", "Izin Formu"], id="slug-alt-cizgi"),
        pytest.param("CAFE", ["Café Kartı"], id="e-aksan"),
        pytest.param("  sınır  ", ["Sınır Kartı"], id="bosluk-atilir"),
        pytest.param("", None, id="bos-arama-suzmez"),
        pytest.param("--", None, id="yalniz-noktalama-suzmez"),
    ],
)
def test_search_matches_name_label_and_slug_ignoring_case_accents_and_turkish_i(
    client: TestClient, catalog: None, query: str, expected: list[str] | None
) -> None:
    page = client.get("/document-types", params={"q": query})

    assert page.status_code == 200
    names = _names(page.text)
    if expected is None:
        assert len(names) == 5
    else:
        assert sorted(names) == sorted(expected)
        assert f"{len(expected)} tür gösteriliyor (toplam 5)" in page.text


def test_search_and_country_filter_combine(client: TestClient, catalog: None) -> None:
    page = client.get("/document-types?country=TR&q=gecis")

    # TR + genel türler içinde: RU'daki "Geçiş Kartı" etiketli tür dışarıda kalır.
    assert sorted(_names(page.text)) == ["Geçiş Belgesi", "Izin Formu"]
    assert "2 tür gösteriliyor (toplam 5)" in page.text
    # Ülke seçeneklerinin sayıları aramadan etkilenmez.
    assert ">Türkiye (2)</option>" in page.text
    assert ">Rusya (1)</option>" in page.text


def test_the_form_has_a_labelled_search_field_a_button_and_keeps_htmx(
    client: TestClient, catalog: None
) -> None:
    page = client.get("/document-types?q=ge%C3%A7i%C5%9F").text

    form = re.search(r'<form class="search country-filter".*?</form>', page, re.S)
    assert form is not None
    html = form.group(0)
    assert 'hx-get="/document-types"' in html
    assert 'hx-select="#catalog-results"' in html
    assert 'hx-push-url="true"' in html
    assert '<label for="type-q">Tür ara</label>' in html
    assert '<input type="search" id="type-q" name="q" value="geçiş" maxlength="100"' in html
    assert '<button type="submit">Ara</button>' in html
    assert html.index('name="country"') < html.index('name="q"')  # ülke seçiminin yanında


def test_clear_link_appears_only_with_a_search_and_keeps_the_country(
    client: TestClient, catalog: None
) -> None:
    assert 'id="clear-search"' not in client.get("/document-types?country=TR").text

    page = client.get("/document-types?country=TR&q=gecis").text

    assert '<a href="/document-types?country=TR" id="clear-search">Temizle</a>' in page
    archived = client.get("/document-types?archived=1&q=x").text
    assert '<a href="/document-types?archived=1" id="clear-search">Temizle</a>' in archived


def test_no_match_says_so(client: TestClient, catalog: None) -> None:
    page = client.get("/document-types?q=pasaport").text

    assert "0 tür gösteriliyor (toplam 5)" in page
    assert "Eşleşen tür yok." in page
    assert "Bu süzgeçte tür yok." not in page
    assert '<table class="catalog catalog-types">' not in page


def test_a_query_longer_than_100_characters_is_refused(client: TestClient, catalog: None) -> None:
    assert client.get("/document-types", params={"q": "a" * 100}).status_code == 200
    assert client.get("/document-types", params={"q": "a" * 101}).status_code == 422
    for path in ("/document-types/transit_tr", "/document-types/new"):
        assert client.get(path, params={"q": "a" * 101}).status_code == 422
    refused = client.post(
        "/document-types/transit_tr/deactivate", data={"q": "a" * 101}, follow_redirects=False
    )
    assert refused.status_code == 422


def test_links_and_hidden_fields_carry_the_search(client: TestClient, catalog: None) -> None:
    page = client.get("/document-types?country=TR&q=gecis").text

    assert 'href="/document-types/new?country=TR&amp;q=gecis"' in page
    assert 'href="/document-types/transit_tr?country=TR&amp;q=gecis"' in page
    assert 'href="/document-types/transit_tr/archive/confirm?country=TR&amp;q=gecis"' in page
    assert 'href="/document-types?archived=1&amp;country=TR&amp;q=gecis"' in page
    # Toplu işlem formu + iki satırın pasifleştir formu.
    assert page.count('<input type="hidden" name="q" value="gecis">') == 3
    assert '<input type="hidden" name="q"' not in client.get("/document-types").text


def test_actions_keep_the_search_in_the_redirect(
    client: TestClient, catalog: None, session_factory: sessionmaker[Session]
) -> None:
    single = client.post(
        "/document-types/transit_tr/deactivate",
        data={"country": "TR", "q": "geçiş"},
        follow_redirects=False,
    )
    assert single.headers["location"] == "/document-types?country=TR&q=ge%C3%A7i%C5%9F"
    assert flashed(single) == ("catalog.deactivated", {"slug": "transit_tr"})

    bulk = client.post(
        "/document-types/bulk",
        data={"action": "activate", "slugs": ["transit_tr"], "q": "gecis"},
        follow_redirects=False,
    )
    assert bulk.headers["location"] == "/document-types?q=gecis"
    none = client.post(
        "/document-types/bulk",
        data={"action": "activate", "q": "gecis"},
        follow_redirects=False,
    )
    assert none.headers["location"] == "/document-types?q=gecis"


def test_the_type_form_returns_to_the_same_search(client: TestClient, catalog: None) -> None:
    page = client.get("/document-types/transit_tr?country=TR&q=gecis").text

    assert '<input type="hidden" name="list_q" value="gecis">' in page
    assert page.count('href="/document-types?country=TR&amp;q=gecis"') == 2  # geri ve "Vazgeç"

    saved = client.post(
        "/document-types/transit_tr",
        data=_data(
            slug="transit_tr",
            name="Geçiş Belgesi",
            file_label="Gecis Belgesi",
            country="TR",
            list_country="TR",
            list_q="gecis",
        ),
        follow_redirects=False,
    )
    assert saved.headers["location"] == "/document-types?country=TR&q=gecis"
    created = client.post(
        "/document-types",
        data=_data(slug="new_one", name="New One", file_label="New One", list_q="new"),
        follow_redirects=False,
    )
    assert created.headers["location"] == "/document-types?q=new"


def test_the_archive_flow_and_the_archive_view_keep_the_search(
    client: TestClient, catalog: None
) -> None:
    client.cookies.set(SESSION_COOKIE, "oturum-bir")
    first = client.get("/document-types/transit_tr/archive/confirm?q=gecis").text
    assert '<input type="hidden" name="q" value="gecis">' in first
    assert 'href="/document-types?q=gecis"' in first  # geri ve "Vazgeç"
    prepared = client.post("/document-types/transit_tr/archive/prepare", data={"q": "gecis"}).text
    token = re.search(r'name="confirmation" value="([^"]+)"', prepared)
    assert token is not None
    done = client.post(
        "/document-types/transit_tr/archive",
        data={"q": "gecis", "confirmation": token.group(1)},
        follow_redirects=False,
    )
    assert done.headers["location"] == "/document-types?q=gecis"

    archived = client.get("/document-types?archived=1&q=GE%C3%87%C4%B0%C5%9E").text
    assert _names(archived) == ["Geçiş Belgesi"]
    assert '<input type="hidden" name="q" value="GEÇİŞ">' in archived  # "Geri al" formu
    assert "Eşleşen tür yok." in client.get("/document-types?archived=1&q=ikamet").text
    restored = client.post(
        "/document-types/transit_tr/restore", data={"q": "gecis"}, follow_redirects=False
    )
    assert restored.headers["location"] == "/document-types?q=gecis"


def test_searching_changes_nothing(
    client: TestClient, catalog: None, session_factory: sessionmaker[Session]
) -> None:
    def snapshot() -> tuple[int, list[tuple[str, str, bool]]]:
        with session_factory() as session:
            events = session.scalar(select(func.count()).select_from(Event)) or 0
            rows = [
                (row.slug, row.name, row.active)
                for row in session.scalars(
                    select(KnownDocumentType).order_by(KnownDocumentType.slug)
                )
            ]
        return events, rows

    before = snapshot()
    first = client.get("/document-types").text
    for query in ("gecis", "İZİN", "yok-boyle-tur"):
        client.get("/document-types", params={"q": query, "country": "TR"})
        client.get("/document-types", params={"q": query, "archived": "1"})

    assert snapshot() == before
    # Token göstergesi (11.4.3) aramadan bağımsızdır.
    budget = re.search(r'id="catalog-budget">.*?</p>', first, re.S)
    assert budget is not None
    assert budget.group(0) in client.get("/document-types?q=pasaport").text
