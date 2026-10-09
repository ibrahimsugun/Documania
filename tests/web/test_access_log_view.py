"""13.4.1 — erişim logu görünümü: çalışan bazında kim, ne zaman baktı görülebilir.

Kayıtlar gerçek yoldan (`GET .../file`, `.../download`) ve bot yolunun yazdığı biçimde
(`record_access(channel=telegram)`) oluşur; sayfalar `TestClient` ile çizilir. 10.1.9: erişim logu
yalnız root'a açıktır; bu dosyada oturumdaki kullanıcı root'tur (İK ve Kullanıcı'nın 404'ü
`tests/web/test_roles.py`'de). Veri sentetiktir
(`tests/fixtures/gen.py`); gerçek kimlik belgesi, yapay zekâ ya da ağ çağrısı yoktur.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AccessAction,
    AccessChannel,
    AccessLog,
    Document,
    Employee,
    KnownDocumentType,
    User,
)
from app.storage import DataLayout
from app.web.access import record_access
from app.web.auth import PanelUser, get_current_user
from app.web.routers.access_log import PAGE_SIZE
from tests.fixtures.gen import make_pdf_bytes
from tests.web.conftest import SIGNED_IN

BASE = datetime(2026, 9, 1, 8, 30, 0, tzinfo=UTC)
ANNA = PanelUser(id=2, username="anna-ik", role="hr")
ROOT = PanelUser(id=SIGNED_IN.id, username=SIGNED_IN.username, role="root")


@pytest.fixture(autouse=True)
def _signed_in_as_root(app: FastAPI, session_factory: sessionmaker[Session]) -> None:
    """10.1.9: erişim logunu yalnız root açar; oturumdaki test kullanıcısı root olur."""
    with session_factory() as session:
        session.get_one(User, ROOT.id).role = "root"
        session.commit()
    app.dependency_overrides[get_current_user] = lambda: ROOT


def _rows(html: str, table_index: int = 0) -> list[list[str]]:
    """`table_index`'inci `access-log` tablosunun gövde satırları, hücre metniyle."""
    tables = re.findall(r'<table class="access-log">(.*?)</table>', html, re.S)
    body = re.search(r"<tbody>(.*?)</tbody>", tables[table_index], re.S).group(1)
    return [
        [
            re.sub(r"<[^>]+>", "", cell).strip()
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        ]
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S)
    ]


def _employee(session: Session, layout: DataLayout, number: int, name: str) -> tuple[str, int]:
    """Çalışanı ve bir pasaport belgesini yazar; (çalışan kimliği, belge kimliği) döner."""
    employee_id = f"E{number:04d}"
    given, surname = name.split()
    employee = Employee(
        id=employee_id,
        folder_name=f"{given}_{surname}_{employee_id}",
        given_names=given,
        surname=surname,
    )
    session.add(employee)
    path = (
        layout.ensure_employee_tree(employee.folder_name)
        / "Hazir"
        / f"{given}_{surname}-Pasaport.pdf"
    )
    path.write_bytes(make_pdf_bytes(1))
    document = Document(
        employee_id=employee_id,
        type_slug="russian_passport",
        path=layout.relative(path),
        format="pdf",
        sequence_no=1,
        source_refs_json=[],
        status="active",
    )
    session.add(document)
    session.flush()
    return employee_id, document.id


@pytest.fixture
def world(session_factory: sessionmaker[Session], layout: DataLayout) -> dict[str, int | str]:
    """İki çalışan (Dmitry E0001, Olga E0002), ikinci bir panel kullanıcısı (anna-ik) ve katalog."""
    with session_factory() as session:
        session.add(
            KnownDocumentType(
                slug="russian_passport",
                name="Rus Pasaportu",
                file_label="Pasaport",
                sides="single",
                direct=True,
                analyze=True,
                output_format="pdf",
            )
        )
        session.add(User(id=ANNA.id, username=ANNA.username, password_hash="yok", role="hr"))
        _, dmitry_doc = _employee(session, layout, 1, "Dmitry Vasiliev")
        _, olga_doc = _employee(session, layout, 2, "Olga Petrova")
        session.commit()
    return {"dmitry_doc": dmitry_doc, "olga_doc": olga_doc}


def _log(
    session_factory: sessionmaker[Session],
    document_id: int,
    *,
    user_id: int,
    at: datetime,
    action: AccessAction = AccessAction.VIEW,
    channel: AccessChannel = AccessChannel.WEB,
) -> None:
    """Bir erişimi gerçek yazıcıyla (`record_access`) yazar, zamanını sabitler."""
    with session_factory() as session:
        entry = record_access(
            session, user_id=user_id, document_id=document_id, action=action, channel=channel
        )
        entry.ts = at
        session.commit()


def test_empty_log_says_nothing_was_viewed(client: TestClient, world: dict[str, int | str]) -> None:
    response = client.get("/access-log")

    assert response.status_code == 200
    assert "Henüz hiçbir belgeye bakılmadı." in response.text
    assert "<table" not in response.text


def test_overview_lists_viewed_employees_newest_access_first(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    _log(session_factory, int(world["dmitry_doc"]), user_id=SIGNED_IN.id, at=BASE)
    _log(session_factory, int(world["dmitry_doc"]), user_id=ANNA.id, at=BASE + timedelta(hours=1))
    _log(session_factory, int(world["olga_doc"]), user_id=ANNA.id, at=BASE + timedelta(hours=2))

    rows = _rows(client.get("/access-log").text)

    assert rows == [
        ["Olga Petrova E0002", "1", "1", "01.09.2026 10:30:00 UTC"],
        ["Dmitry Vasiliev E0001", "2", "2", "01.09.2026 09:30:00 UTC"],
    ]


def test_employee_never_viewed_is_not_listed(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    _log(session_factory, int(world["dmitry_doc"]), user_id=SIGNED_IN.id, at=BASE)

    page = client.get("/access-log").text

    assert "Dmitry Vasiliev" in page
    assert "Olga Petrova" not in page


def test_overview_links_to_the_employee_log(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    _log(session_factory, int(world["dmitry_doc"]), user_id=SIGNED_IN.id, at=BASE)

    assert 'href="/access-log/employees/E0001"' in client.get("/access-log").text


def test_employee_log_shows_who_looked_when_and_how(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    doc = int(world["dmitry_doc"])
    _log(session_factory, doc, user_id=SIGNED_IN.id, at=BASE)
    _log(
        session_factory,
        doc,
        user_id=ANNA.id,
        at=BASE + timedelta(hours=1),
        action=AccessAction.DOWNLOAD,
        channel=AccessChannel.TELEGRAM,
    )

    page = client.get("/access-log/employees/E0001").text

    assert "<h1>Dmitry Vasiliev</h1>" in page
    assert _rows(page, 1) == [
        [
            "01.09.2026 09:30:00 UTC",
            "anna-ik",
            "Rus Pasaportu · Dmitry_Vasiliev-Pasaport.pdf",
            "İndirdi",
            "Telegram",
        ],
        [
            "01.09.2026 08:30:00 UTC",
            "test-yonetici",
            "Rus Pasaportu · Dmitry_Vasiliev-Pasaport.pdf",
            "Açtı",
            "Panel",
        ],
    ]


def test_employee_log_summarises_each_viewer(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    doc = int(world["dmitry_doc"])
    _log(session_factory, doc, user_id=SIGNED_IN.id, at=BASE)
    _log(session_factory, doc, user_id=SIGNED_IN.id, at=BASE + timedelta(minutes=5))
    _log(
        session_factory,
        doc,
        user_id=SIGNED_IN.id,
        at=BASE + timedelta(minutes=9),
        action=AccessAction.DOWNLOAD,
    )
    _log(session_factory, doc, user_id=ANNA.id, at=BASE + timedelta(days=1))

    assert _rows(client.get("/access-log/employees/E0001").text, 0) == [
        ["anna-ik", "1", "0", "02.09.2026 08:30:00 UTC"],
        ["test-yonetici", "2", "1", "01.09.2026 08:39:00 UTC"],
    ]


def test_employee_log_shows_only_that_employees_documents(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    _log(session_factory, int(world["dmitry_doc"]), user_id=SIGNED_IN.id, at=BASE)
    _log(session_factory, int(world["olga_doc"]), user_id=ANNA.id, at=BASE)

    page = client.get("/access-log/employees/E0001").text

    assert "Olga_Petrova" not in page
    assert "anna-ik" not in page
    assert "1 erişim" in page


def test_employee_without_access_says_so(client: TestClient, world: dict[str, int | str]) -> None:
    response = client.get("/access-log/employees/E0002")

    assert response.status_code == 200
    assert "Bu çalışanın belgelerine henüz bakılmadı." in response.text
    assert "<table" not in response.text


def test_unknown_employee_is_a_404_page(client: TestClient, world: dict[str, int | str]) -> None:
    response = client.get("/access-log/employees/E9999")

    assert response.status_code == 404
    assert "Çalışan bulunamadı." in response.text


def test_real_panel_opening_and_download_show_up_in_the_log(
    client: TestClient, world: dict[str, int | str]
) -> None:
    """Uçtan uca: panelde açma ve indirme log satırı yazar, görünüm onu gösterir."""
    doc = int(world["dmitry_doc"])
    assert client.get(f"/employees/E0001/documents/{doc}/file").status_code == 200
    assert client.get(f"/employees/E0001/documents/{doc}/download").status_code == 200

    rows = _rows(client.get("/access-log/employees/E0001").text, 1)

    assert sorted((row[1], row[3], row[4]) for row in rows) == [
        ("test-yonetici", "Açtı", "Panel"),
        ("test-yonetici", "İndirdi", "Panel"),
    ]


def test_moved_document_history_follows_the_current_owner(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    doc = int(world["dmitry_doc"])
    _log(session_factory, doc, user_id=SIGNED_IN.id, at=BASE)
    with session_factory() as session:
        session.get_one(Document, doc).employee_id = "E0002"
        session.commit()

    assert (
        "Bu çalışanın belgelerine henüz bakılmadı."
        in client.get("/access-log/employees/E0001").text
    )
    assert _rows(client.get("/access-log/employees/E0002").text, 1)[0][1] == "test-yonetici"


def test_entries_are_paged(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    doc = int(world["dmitry_doc"])
    for minute in range(PAGE_SIZE + 3):
        _log(session_factory, doc, user_id=SIGNED_IN.id, at=BASE + timedelta(minutes=minute))

    first = client.get("/access-log/employees/E0001")
    second = client.get("/access-log/employees/E0001?page=2")

    assert len(_rows(first.text, 1)) == PAGE_SIZE
    assert 'href="/access-log/employees/E0001?page=2"' in first.text
    assert "← Önceki" not in first.text
    # Sayfalar en yeniden eskiye gider: ikinci sayfada en eski üç erişim kalır.
    oldest = _rows(second.text, 1)
    assert [row[0] for row in oldest] == [
        "01.09.2026 08:32:00 UTC",
        "01.09.2026 08:31:00 UTC",
        "01.09.2026 08:30:00 UTC",
    ]
    assert 'href="/access-log/employees/E0001"' in second.text
    assert "Sonraki →" not in second.text
    # Kullanıcı özeti sayfadan bağımsızdır: hepsini sayar.
    assert _rows(second.text, 0)[0][1] == str(PAGE_SIZE + 3)


def test_overview_is_paged(
    client: TestClient,
    world: dict[str, int | str],
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    extra = 3
    with session_factory() as session:
        for number in range(3, PAGE_SIZE + extra + 3):
            _, doc = _employee(session, layout, number, f"Kisi{number} Deneme")
            record_access(session, user_id=SIGNED_IN.id, document_id=doc, action=AccessAction.VIEW)
        session.commit()

    first = client.get("/access-log")
    second = client.get("/access-log?page=2")

    assert len(_rows(first.text)) == PAGE_SIZE
    assert f"Sayfa 1 / 2 · {PAGE_SIZE + extra} çalışan" in first.text
    assert 'href="/access-log?page=2"' in first.text
    assert len(_rows(second.text)) == extra
    assert 'href="/access-log"' in second.text
    assert "Sonraki →" not in second.text


def test_page_beyond_the_end_shows_the_last_page(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    _log(session_factory, int(world["dmitry_doc"]), user_id=SIGNED_IN.id, at=BASE)

    response = client.get("/access-log/employees/E0001?page=99")

    assert response.status_code == 200
    assert "Sayfa 1 / 1" in response.text
    assert client.get("/access-log?page=0").status_code == 422


def test_topbar_and_profile_link_to_the_log(
    client: TestClient, world: dict[str, int | str], app: FastAPI
) -> None:
    other = client.get("/queues")
    assert '<a class="tool-link" href="/access-log">Erişim logu</a>' in other.text

    log = client.get("/access-log")
    assert (
        '<a class="tool-link active" href="/access-log" aria-current="page">Erişim logu</a>'
        in log.text
    )
    # Ana menü altı bölümdür (10.1.1); erişim logu menüde değil, oturumun yanındadır.
    assert "/access-log" not in re.search(r'<nav class="menu".*?</nav>', log.text, re.S).group(0)

    assert 'href="/access-log/employees/E0001"' in client.get("/employees/E0001").text


def test_pages_only_read(
    client: TestClient, world: dict[str, int | str], session_factory: sessionmaker[Session]
) -> None:
    _log(session_factory, int(world["dmitry_doc"]), user_id=SIGNED_IN.id, at=BASE)
    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(AccessLog))

    for path in ("/access-log", "/access-log/employees/E0001", "/access-log/employees/E9999"):
        assert client.get(path).status_code in (200, 404)

    with session_factory() as session:
        # Logu görüntülemek belgeye erişim sayılmaz: yeni satır yazılmaz.
        assert session.scalar(select(func.count()).select_from(AccessLog)) == before


def test_log_can_only_be_read_not_changed(app: FastAPI) -> None:
    """Erişim logunu değiştirecek bir yol yoktur: görünümün yolları yalnız GET'tir."""
    operations = {
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        if path.startswith("/access-log")
        for method in methods
    }

    assert operations == {
        ("GET", "/access-log"),
        ("GET", "/access-log/employees/{employee_id}"),
    }
