"""10.4.1, 10.4.2 — çalışan listesi (ad, orijinal yazım, uyruk, belge sayısı, durum) ve arama (ad,
alias, orijinal yazım, belge numarası, belge türü); 10.5.7 — durum süzgeci (Aktif varsayılan, Pasif,
Hepsi) ve sayaçları.

Veri sentetiktir (çalışanlar, alias'lar, numaralar, belgeler doğrudan satır olarak yazılır); gerçek
kimlik belgesi ya da yapay zekâ çağrısı yoktur. Sayfa yalnız okur: sınamalar HTTP katmanından
(`TestClient`) ve arama çekirdeğinden (`list_employees`) yapılır.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    KnownDocumentType,
)
from app.matching.names import normalize_name
from app.web.auth import get_current_user
from app.web.routers.employees import MAX_TERMS, PAGE_SIZE, list_employees

PASSPORT = "russian_passport"
RESIDENCE = "residence_permit"
NO_MATCH_TEXT = "eşleşen çalışan yok"


def _catalog(session: Session) -> None:
    for slug, name, label in (
        (PASSPORT, "Rus Pasaportu", "Pasaport"),
        (RESIDENCE, "İkamet İzni", "Ikamet-Izni"),
    ):
        session.add(
            KnownDocumentType(
                slug=slug,
                name=name,
                file_label=label,
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
    session.flush()


def _employee(
    session: Session,
    number: int,
    given_names: str,
    surname: str,
    *,
    original: str | None = None,
    other_names: str | None = None,
    nationality: str | None = "RUS",
    status: str = "active",
    aliases: Sequence[str] = (),
    numbers: Sequence[str] = (),
    documents: Sequence[tuple[str, str]] = (),
) -> Employee:
    """`documents`: `(tür slug'ı, durum)` çiftleri."""
    employee_id = f"E{number:04d}"
    employee = Employee(
        id=employee_id,
        folder_name=f"{given_names}_{surname}_{employee_id}",
        given_names=given_names,
        surname=surname,
        other_names=other_names,
        original_script_name=original,
        nationality=nationality,
        status=status,
    )
    session.add(employee)
    session.flush()
    for raw in aliases:
        session.add(
            EmployeeAlias(
                employee_id=employee_id, raw_name=raw, normalized_name=normalize_name(raw)
            )
        )
    for value in numbers:
        session.add(EmployeeIdentifier(employee_id=employee_id, kind=PASSPORT, value=value))
    for index, (slug, document_status) in enumerate(documents, start=1):
        session.add(
            Document(
                employee_id=employee_id,
                type_slug=slug,
                path=f"Employees/{employee.folder_name}/Hazir/{slug}-{index}.pdf",
                format="pdf",
                sequence_no=index,
                source_refs_json=[],
                status=document_status,
            )
        )
    session.flush()
    return employee


ACTIVE = DocumentStatus.ACTIVE.value
SUPERSEDED = DocumentStatus.SUPERSEDED.value
ARCHIVED = DocumentStatus.ARCHIVED.value


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    """Dört çalışan: Kiril yazımlı Rus, Türk (aksanlı), iki eski sürüm/arşiv belgeli Gürcü ve
    belgesiz, pasif biri (10.5.7: varsayılan listede görünmez)."""
    with session_factory() as session:
        _catalog(session)
        _employee(
            session,
            1,
            "Dmitry",
            "Vasiliev",
            original="Васильев Дмитрий",
            other_names="Ivanovich",
            aliases=["Dmitry Vasiliev", "Васильев Дмитрий"],
            numbers=["711234567"],
            documents=[(PASSPORT, ACTIVE), (RESIDENCE, ACTIVE)],
        )
        _employee(
            session,
            2,
            "Şükrü",
            "Öztürk",
            nationality="TUR",
            aliases=["Şükrü Öztürk", "Sukru Ozturk"],
            numbers=["AB123456"],
            documents=[(PASSPORT, ACTIVE)],
        )
        _employee(
            session,
            3,
            "Nino",
            "Beridze",
            nationality="GEO",
            aliases=["Nino Beridze"],
            numbers=["GE998877"],
            documents=[(PASSPORT, SUPERSEDED), (RESIDENCE, ARCHIVED), (RESIDENCE, ACTIVE)],
        )
        _employee(
            session,
            4,
            "Anna",
            "Zeta",
            nationality=None,
            status="inactive",
            aliases=["Anna Zeta"],
        )
        session.commit()


def _rows(html: str) -> list[list[str]]:
    """Tablo gövdesinin her satırının hücre metinleri (bağlantı etiketleri atılmış)."""
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return [
        [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in re.findall(r"<td>(.*?)</td>", row, re.S)
        ]
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S)
    ]


def _ids(client: TestClient, query: str = "", **params: object) -> list[str]:
    response = client.get("/employees", params={"q": query, **params})
    assert response.status_code == 200
    if NO_MATCH_TEXT in response.text or "<tbody>" not in response.text:
        return []
    # Sıra ayrı sınanır (`test_list_is_sorted_...`): SQLite ASCII dışı harfleri küçültemez, bu
    # yüzden burada kümeler karşılaştırılır.
    return sorted(row[0] for row in _rows(response.text))


# --- 10.4.1: liste -----------------------------------------------------------------------------


@pytest.mark.usefixtures("seeded")
def test_list_shows_name_original_writing_nationality_document_count_and_status(
    client: TestClient,
) -> None:
    response = client.get("/employees")

    assert response.status_code == 200
    header = re.findall(r"<th>(.*?)</th>", response.text)
    assert header == ["No", "Ad", "Orijinal yazım", "Uyruk", "Belge sayısı", "Paket", "Durum"]
    rows = {row[0]: row for row in _rows(response.text)}
    assert rows["E0001"] == [
        "E0001",
        "Dmitry Vasiliev",
        "Васильев Дмитрий",
        "RUS",
        "2",
        "—",
        "Aktif",
    ]
    assert rows["E0002"] == ["E0002", "Şükrü Öztürk", "—", "TUR", "1", "—", "Aktif"]
    # Belge sayısı yalnız etkin belgedir: eski sürüm ve arşive taşınan sayılmaz.
    assert rows["E0003"][4] == "1"
    # 10.5.7: pasif çalışan varsayılan (Aktif) listede yoktur.
    assert "E0004" not in rows
    # "Hepsi"nde belgesiz, uyruksuz ve pasif çalışan da listelenir; durumu "Pasif" (tm 127'ye dek
    # tanınmayan durum ham görünüyordu); paketi olmayan çalışanın paket hücresi "—" (14.3.1).
    everyone = {row[0]: row for row in _rows(client.get("/employees?status=all").text)}
    assert everyone["E0004"] == ["E0004", "Anna Zeta", "—", "—", "0", "—", "Pasif"]


def test_list_is_sorted_by_surname_then_given_name_ignoring_case(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _employee(session, 1, "Zed", "charlie")
        _employee(session, 2, "Zed", "Bravo")
        _employee(session, 3, "Anna", "Bravo")
        _employee(session, 4, "Anna", "bravo")  # aynı ad-soyad: numara belirler
        session.commit()

    response = client.get("/employees")

    # Küçük/büyük harf sıralamayı bozmaz: bravo < Bravo değil, hepsi "bravo".
    assert [row[0] for row in _rows(response.text)] == ["E0003", "E0004", "E0002", "E0001"]


def test_empty_directory_says_so(client: TestClient) -> None:
    response = client.get("/employees")

    assert response.status_code == 200
    assert "Henüz çalışan yok." in response.text
    assert "<table" not in response.text


def test_full_page_has_the_menu_the_search_box_and_the_active_entry(client: TestClient) -> None:
    response = client.get("/employees")

    assert '<a href="/employees" class="active" aria-current="page">Çalışanlar</a>' in response.text
    assert 'name="q"' in response.text
    assert 'id="employee-results"' in response.text


def test_names_are_escaped(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _employee(session, 1, "<script>alert(1)</script>", "X")
        session.commit()

    page = client.get("/employees", params={"q": '"><img src=x>'})
    listed = client.get("/employees")

    assert "<img src=x>" not in page.text
    assert "&#34;&gt;&lt;img src=x&gt;" in page.text
    assert "<script>alert(1)</script>" not in listed.text
    assert "&lt;script&gt;" in listed.text


# --- 10.4.2: arama -----------------------------------------------------------------------------


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    "query",
    [
        "dmitry",  # ad
        "DMITRY",  # büyük/küçük harf
        "vasil",  # soyadın parçası
        "Vasiliev Dmitry",  # sıra fark etmez
        "dmitry vasiliev",
        "ivanovich",  # diğer isimler
    ],
)
def test_search_by_name(client: TestClient, query: str) -> None:
    assert _ids(client, query) == ["E0001"]


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    "query",
    [
        "Sukru Ozturk",  # alias (Latin)
        "sukru",
        "ŞÜKRÜ",  # aksan ve büyük harf
        "ozturk sukru",
    ],
)
def test_search_by_alias_ignores_case_and_accents(client: TestClient, query: str) -> None:
    assert _ids(client, query) == ["E0002"]


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    "query",
    [
        "Васильев",  # orijinal yazım, aynen
        "ВАСИЛЬЕВ",  # büyük harf: SQLite `lower` Kiril'i indirmez, alias anahtarı bulur
        "дмитрий",
    ],
)
def test_search_by_original_writing(client: TestClient, query: str) -> None:
    assert _ids(client, query) == ["E0001"]


@pytest.mark.usefixtures("seeded")
def test_search_by_original_writing_finds_the_latin_spelling_and_the_other_way_round(
    client: TestClient,
) -> None:
    # Alias anahtarı yazı sistemini eşitler: Kiril terim Latin yazımlı çalışanı da bulur.
    assert _ids(client, "Дмитрий Vasiliev") == ["E0001"]
    assert _ids(client, "vasilyev") == []  # yazım farkı yok sayılmaz


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("711234567", ["E0001"]),  # tam numara
        ("1234", ["E0001", "E0002"]),  # parça: "711234567" ve "AB123456"
        ("ab 123-456", ["E0002"]),  # boşluk, tire ve küçük harf farkı
        ("ab.123/456", ["E0002"]),
        ("GE998877", ["E0003"]),
        ("GE-99 88.77", ["E0003"]),  # aranan metin de saklıyla aynı biçime indirilir
    ],
)
def test_search_by_document_number(client: TestClient, query: str, expected: list[str]) -> None:
    assert _ids(client, query) == expected


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("pasaport", ["E0001", "E0002"]),  # E0003'ün pasaportu eski sürüm: sayılmaz
        ("Rus Pasaportu", ["E0001", "E0002"]),  # tür adı
        ("russian_passport", ["E0001", "E0002"]),  # slug
        ("ikamet", ["E0001", "E0003"]),  # Türkçe İ: SQL değil katlamayla eşleşir
        ("İKAMET İZNİ", ["E0001", "E0003"]),
        ("Ikamet-Izni", ["E0001", "E0003"]),  # dosya etiketi
    ],
)
def test_search_by_document_type_uses_active_documents(
    client: TestClient, query: str, expected: list[str]
) -> None:
    assert _ids(client, query) == expected


@pytest.mark.usefixtures("seeded")
def test_archived_and_superseded_documents_do_not_make_an_employee_match_a_type(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _employee(
            session,
            5,
            "Eski",
            "Belge",
            documents=[(PASSPORT, SUPERSEDED), (PASSPORT, ARCHIVED)],
        )
        session.commit()

    assert "E0005" not in _ids(client, "pasaport")


def test_type_with_an_unreadable_name_is_still_found_by_its_other_labels(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(
            KnownDocumentType(
                slug="diploma",
                name="***",  # noktalama: karşılaştırılabilir kelime yok
                file_label="Diploma",
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
        session.flush()
        _employee(session, 1, "Ada", "Mezun", documents=[("diploma", ACTIVE)])
        _employee(session, 2, "Bora", "Mezunolmayan")
        session.commit()

    assert _ids(client, "diploma") == ["E0001"]


@pytest.mark.usefixtures("seeded")
def test_every_term_must_match_some_field(client: TestClient) -> None:
    assert _ids(client, "dmitry pasaport") == ["E0001"]
    assert _ids(client, "dmitry 711234567 ikamet") == ["E0001"]
    assert _ids(client, "dmitry 998877") == []  # numara başka çalışanın
    assert _ids(client, "nino pasaport") == []  # Nino'nun pasaportu eski sürüm


@pytest.mark.usefixtures("seeded")
def test_blank_query_lists_everyone(client: TestClient) -> None:
    # Varsayılan süzgeç etkin çalışanlardır (10.5.7); "Hepsi" pasifi de sayar.
    assert len(_ids(client, "")) == 3
    assert len(_ids(client, "   ")) == 3
    assert len(_ids(client, "", status="all")) == 4


# --- 10.5.7: durum süzgeci ---------------------------------------------------------------------


def _status_options(html: str) -> list[tuple[str, str, bool]]:
    select_html = html.split('<select id="employee-status" name="status">', 1)[1].split(
        "</select>", 1
    )[0]
    return [
        (value, re.sub(r"\s+", " ", label).strip(), bool(selected))
        for value, selected, label in re.findall(
            r'<option value="([^"]+)"( selected)?>(.*?)</option>', select_html, re.S
        )
    ]


@pytest.mark.usefixtures("seeded")
def test_status_filter_defaults_to_active_and_counts_each_choice(client: TestClient) -> None:
    page = client.get("/employees")

    assert _status_options(page.text) == [
        ("active", "Aktif (3)", True),
        ("inactive", "Pasif (1)", False),
        ("all", "Hepsi (4)", False),
    ]
    assert _ids(client, "", status="inactive") == ["E0004"]
    assert sorted(_ids(client, "", status="all")) == ["E0001", "E0002", "E0003", "E0004"]
    assert "yalnız pasif çalışanlar" in client.get("/employees?status=inactive").text
    # Pasif satırın durumu rozettir; metin yine "Pasif".
    assert '<span class="status-badge status-passive">Pasif</span>' in (
        client.get("/employees?status=inactive").text
    )


@pytest.mark.usefixtures("seeded")
def test_status_filter_combines_with_the_search_and_its_counts_follow_the_search(
    client: TestClient,
) -> None:
    page = client.get("/employees", params={"q": "anna", "status": "inactive"})

    assert _ids(client, "anna") == []  # pasif, varsayılanda görünmez
    assert _ids(client, "anna", status="inactive") == ["E0004"]
    assert _status_options(page.text) == [
        ("active", "Aktif (0)", False),
        ("inactive", "Pasif (1)", True),
        ("all", "Hepsi (1)", False),
    ]


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize("value", ["", "merged", "pending", "ALL"])
def test_unknown_status_filter_falls_back_to_active(client: TestClient, value: str) -> None:
    assert sorted(_ids(client, "", status=value)) == ["E0001", "E0002", "E0003"]


def test_merged_employee_shows_only_under_all(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # 10.5.9 (tm 129) birleştirilen çalışanı `merged` yapar; o yalnız "Hepsi"nde görünür.
    with session_factory() as session:
        _employee(session, 1, "Kalan", "Kayit")
        _employee(session, 2, "Birlesen", "Kayit", status="merged")
        session.commit()

    assert _ids(client) == ["E0001"]
    assert _ids(client, "", status="inactive") == []
    everyone = {row[0]: row for row in _rows(client.get("/employees?status=all").text)}
    assert everyone["E0002"][-1] == "Birleşti"


def test_status_filter_is_kept_in_the_page_links(
    session_factory: sessionmaker[Session], crowd: int
) -> None:
    with session_factory() as session:
        for employee in session.scalars(select(Employee)):
            employee.status = "inactive"
        session.flush()
        middle = list_employees(session, "kalabalik", 2, status_filter="inactive")
        first = list_employees(session, "", 1, status_filter="inactive")
        active = list_employees(session, "", 1)
        session.rollback()

    assert (middle.total, middle.page) == (crowd, 2)
    assert middle.previous_url == "/employees?q=kalabalik&status=inactive"
    assert first.next_url == "/employees?status=inactive&page=2"
    assert active.total == 0
    assert [option.url for option in first.status_options] == [
        "/employees",
        "/employees?status=inactive",
        "/employees?status=all",
    ]


def test_search_statuses_replace_the_filter_and_draw_no_choices(
    session_factory: sessionmaker[Session],
) -> None:
    # Atama ve taşıma aramaları etkin ve pasif çalışanı birlikte arar (10.7.2, 10.8.2).
    with session_factory() as session:
        _employee(session, 1, "Anna", "Etkin")
        _employee(session, 2, "Anna", "Pasif", status="inactive")
        _employee(session, 3, "Anna", "Birlesen", status="merged")
        listing = list_employees(
            session, "anna", statuses=frozenset({"active", "inactive"}), status_filter="all"
        )
        session.rollback()

    assert sorted(row.id for row in listing.rows) == ["E0001", "E0002"]
    assert [row.status_label for row in sorted(listing.rows, key=lambda row: row.id)] == [
        "Aktif",
        "Pasif",
    ]
    assert listing.status_options == []


@pytest.mark.usefixtures("seeded")
def test_no_match_says_so_and_echoes_the_query(client: TestClient) -> None:
    response = client.get("/employees", params={"q": "yokboyle"})

    assert response.status_code == 200
    assert "“yokboyle” ile eşleşen çalışan yok." in response.text
    assert "<table" not in response.text


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize("query", ["%", "_", "\\", "%%%"])
def test_wildcards_are_literal(client: TestClient, query: str) -> None:
    assert _ids(client, query) == []


@pytest.mark.usefixtures("seeded")
@pytest.mark.parametrize("query", ["-", "...", "/ /", "'"])
def test_punctuation_only_queries_do_not_fail(client: TestClient, query: str) -> None:
    assert client.get("/employees", params={"q": query}).status_code == 200


@pytest.mark.usefixtures("seeded")
def test_terms_beyond_the_limit_are_ignored(client: TestClient) -> None:
    query = "dmitry " + " ".join(["dmitry"] * (MAX_TERMS - 1)) + " yokboyle"

    assert _ids(client, query) == ["E0001"]


@pytest.mark.usefixtures("seeded")
def test_query_length_is_capped(client: TestClient) -> None:
    assert client.get("/employees", params={"q": "a" * 101}).status_code == 422
    assert client.get("/employees", params={"q": "a" * 100}).status_code == 200


# --- sayfalama ---------------------------------------------------------------------------------


@pytest.fixture
def crowd(session_factory: sessionmaker[Session]) -> int:
    total = PAGE_SIZE + 5
    with session_factory() as session:
        for number in range(1, total + 1):
            _employee(session, number, f"Ad{number:03d}", f"Kalabalik{number:03d}")
        session.commit()
    return total


@pytest.mark.usefixtures("crowd")
def test_list_is_paged(client: TestClient) -> None:
    first = client.get("/employees")
    second = client.get("/employees", params={"page": 2})

    assert len(_rows(first.text)) == PAGE_SIZE
    assert len(_rows(second.text)) == 5
    assert "30 çalışan" in first.text
    assert "Sayfa 1 / 2" in first.text
    assert 'href="/employees?page=2" rel="next"' in first.text
    assert 'rel="prev"' not in first.text
    assert 'href="/employees" rel="prev"' in second.text
    assert 'rel="next"' not in second.text
    # Sayfalar örtüşmez ve hepsini kapsar.
    assert {r[0] for r in _rows(first.text)} | {r[0] for r in _rows(second.text)} == {
        f"E{n:04d}" for n in range(1, 31)
    }


@pytest.mark.usefixtures("crowd")
def test_paging_keeps_the_query(client: TestClient) -> None:
    response = client.get("/employees", params={"q": "kalabalik"})

    assert 'href="/employees?q=kalabalik&amp;page=2" rel="next"' in response.text
    assert "30 çalışan bulundu" in response.text


@pytest.mark.usefixtures("crowd")
def test_page_beyond_the_last_shows_the_last_page(client: TestClient) -> None:
    response = client.get("/employees", params={"page": 99})

    assert len(_rows(response.text)) == 5
    assert "Sayfa 2 / 2" in response.text


@pytest.mark.usefixtures("crowd")
@pytest.mark.parametrize("page", ["0", "-1", "abc"])
def test_invalid_page_is_refused(client: TestClient, page: str) -> None:
    assert client.get("/employees", params={"page": page}).status_code == 422


@pytest.mark.usefixtures("crowd")
def test_single_page_has_no_pager(client: TestClient) -> None:
    assert "pager" not in client.get("/employees", params={"q": "Kalabalik001"}).text


# --- HTMX parçası ------------------------------------------------------------------------------


@pytest.mark.usefixtures("seeded")
def test_htmx_request_gets_only_the_results_fragment(client: TestClient) -> None:
    response = client.get("/employees", params={"q": "dmitry"}, headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "<html" not in response.text and 'class="topbar"' not in response.text
    assert _rows(response.text) == [
        ["E0001", "Dmitry Vasiliev", "Васильев Дмитрий", "RUS", "2", "—", "Aktif"]
    ]


@pytest.mark.usefixtures("seeded")
def test_history_restore_gets_the_full_page(client: TestClient) -> None:
    response = client.get(
        "/employees",
        params={"q": "dmitry"},
        headers={"HX-Request": "true", "HX-History-Restore-Request": "true"},
    )

    assert "<html" in response.text
    assert 'value="dmitry"' in response.text


@pytest.mark.usefixtures("seeded")
def test_response_varies_on_htmx_header(client: TestClient) -> None:
    plain = client.get("/employees")
    htmx = client.get("/employees", headers={"HX-Request": "true"})

    assert plain.headers["vary"] == htmx.headers["vary"] == "HX-Request"


@pytest.mark.usefixtures("seeded")
def test_search_box_keeps_the_query_and_refreshes_the_results_with_htmx(
    client: TestClient,
) -> None:
    response = client.get("/employees", params={"q": "ozturk"})

    assert 'value="ozturk"' in response.text
    assert 'hx-get="/employees"' in response.text
    assert 'hx-target="#employee-results"' in response.text
    assert 'hx-push-url="true"' in response.text


# --- çekirdek ----------------------------------------------------------------------------------


def test_list_employees_reports_totals_and_neighbouring_pages(
    session_factory: sessionmaker[Session], crowd: int
) -> None:
    with session_factory() as session:
        middle = list_employees(session, "  kalabalik   ", 2)
        first = list_employees(session, "", 1)
        empty = list_employees(session, "yokboyle", 3)

    assert (middle.total, middle.page, middle.page_count) == (crowd, 2, 2)
    assert middle.query == "kalabalik"  # boşluklar sadeleşir
    assert middle.previous_url == "/employees?q=kalabalik"
    assert middle.next_url is None
    assert first.previous_url is None and first.next_url == "/employees?page=2"
    assert (empty.total, empty.page, empty.page_count, empty.rows) == (0, 1, 1, [])


@pytest.mark.usefixtures("seeded")
def test_search_is_read_only(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    def snapshot() -> list[tuple[object, ...]]:
        with session_factory() as session:
            return [
                *session.execute(
                    select(Employee.id, Employee.given_names, Employee.surname, Employee.status)
                ).all(),
                *session.execute(select(Document.id, Document.status, Document.path)).all(),
                *session.execute(select(EmployeeAlias.id, EmployeeAlias.raw_name)).all(),
            ]

    before = snapshot()
    client.get("/employees", params={"q": "dmitry pasaport"})

    assert snapshot() == before


# --- oturum ------------------------------------------------------------------------------------


def test_employees_page_needs_a_session(app: FastAPI) -> None:
    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    response = anonymous.get("/employees?q=ivan&page=2", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
