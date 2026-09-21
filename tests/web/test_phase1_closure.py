"""PRD §5.2 — Faz 1 kapanış ölçütünün ilk maddesi tek yolculukta: "İK bir belgeyi yükleyip,
kuyruğu çözüp, profilde görüp yeni sekmede açabiliyor."

Parçalar ayrı dosyalarda sınanır (yükleme `test_upload_page.py`, atama `test_queue_assign.py`,
profil ve dosya sunumu `test_profile.py`); burada zincir baştan sona yalnız panelin HTTP yolundan
kurulur. Kurulum yalnız katalog tohumu ve İK'nın kayıtlı çalışanıdır; sonrasında veritabanına
yazılmaz, her kimlik (parti, kuyruk öğesi, belge) bir önceki yanıttan okunur. Yapay zekâ canlı
çağrılmaz: sağlayıcı `tests/fixtures/gen.py`'nin sentetik sayfasının kayıtlı yanıtını okur. Gerçek
kimlik belgesi yoktur (CONVENTIONS §6).

Çalışma izninde doğum tarihi yoktur ve numarası çalışanın kaydında yoktur: belge yalnız isimden
eşleşir ve Unresolved'a gider (§20.2.2 satır 5). İK onu iki aşamalı onayla (K16) çalışana atar.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.ai import PROVIDER_FACTORIES
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import Employee, EmployeeAlias, allocate_employee_number
from app.db.session import get_session_factory
from app.matching.names import normalize_name
from app.storage import DataLayout, employee_folder_name
from app.web.auth import SESSION_COOKIE
from tests.fixtures.gen import (
    PERSON_SIDOROV,
    make_document_pdf_bytes,
    recorded_provider,
    work_permit_page,
)
from tests.web.conftest import SESSION, SIGNED_IN

PERMIT = work_permit_page(
    PERSON_SIDOROV, document_number="WP-0000042", expiry_date=date(2027, 3, 31)
)
EMPLOYEE_NAME = "Ivan Sidorov"
POLLING = 'hx-trigger="every 2s"'
# §20.6 — birebir.
FIRST_TEXT = f"Bu belgeyi {EMPLOYEE_NAME} çalışanına atamak üzeresiniz. Emin misiniz?"
SECOND_TEXT = "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?"


@pytest.fixture
def employee(session_factory: sessionmaker[Session], layout: DataLayout) -> Employee:
    """Kurulum: tohum kataloğu ve İK'nın kayıtlı çalışanı (belge numarası kayıtlı değil)."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        employee_id = allocate_employee_number(session)
        row = Employee(
            id=employee_id,
            folder_name=employee_folder_name("Ivan", "Sidorov", employee_id),
            given_names="Ivan",
            surname="Sidorov",
            date_of_birth=PERSON_SIDOROV.date_of_birth,
            nationality=PERSON_SIDOROV.nationality,
        )
        session.add(row)
        session.add(
            EmployeeAlias(
                employee=row, raw_name=EMPLOYEE_NAME, normalized_name=normalize_name(EMPLOYEE_NAME)
            )
        )
        session.commit()
        session.expunge(row)
    layout.ensure_employee_tree(row.folder_name)
    return row


@pytest.fixture
def recorded_processing(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> None:
    """Gerçek arka plan işleyicisi (`get_upload_processor`); `AI_PROVIDER=kayitli` sağlayıcısı
    çalışma izninin kayıtlı yanıtını okur."""
    provider = recorded_provider(tmp_path / "kayit", [PERMIT])
    monkeypatch.setitem(PROVIDER_FACTORIES, "kayitli", lambda settings: provider)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", ai_provider="kayitli"
    )
    app.dependency_overrides[get_session_factory] = lambda: session_factory


def _one(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.S)
    assert match is not None, (pattern, html)
    return match.group(1)


def _token(html: str) -> str:
    return _one(r'name="confirmation" value="([^"]+)"', html)


def test_hr_uploads_resolves_the_queue_sees_the_document_on_the_profile_and_opens_it_in_a_new_tab(
    client: TestClient,
    layout: DataLayout,
    employee: Employee,
    recorded_processing: None,
) -> None:
    client.cookies.set(SESSION_COOKIE, SESSION)  # onay belirteci oturum çerezine bağlıdır
    pdf = make_document_pdf_bytes([PERMIT])

    # 1) Yükle: panelin yükleme sayfası, arka planda kayıtlı yanıtlı sağlayıcıyla işlenir.
    assert 'hx-post="/upload"' in client.get("/upload").text
    uploaded = client.post(
        "/upload", files=[("files", ("izin.pdf", pdf, "application/octet-stream"))]
    )
    assert uploaded.status_code == 201, uploaded.text
    upload_id = _one(r"Parti (u_\w+)", uploaded.text)
    progress = client.get(f"/upload/{upload_id}/progress")
    assert progress.status_code == 200
    assert "Tamamlandı" in progress.text  # kuyruğa düşen belge partiyi kısmi yapmaz
    assert POLLING not in progress.text  # parti son durumda: yenileme durdu

    # 2) Kuyruk: belge Unresolved sekmesinde bekler, satırı öğe detayına gider.
    listing = client.get("/queues", params={"tab": "unresolved"}).text
    assert 'title="Bekleyen öğe">1</span>' in listing
    item_url = _one(r'<td><a href="(/queues/\d+)">', listing)
    assert f'<a href="/uploads/{upload_id}">' in listing
    detail = client.get(item_url).text
    assert f'hx-get="{item_url}/assign/employees"' in detail

    # 3) Kuyruğu çöz: çalışanı ara, seç, iki onayı ver (K16; belirteç yanıttan okunur).
    found = client.get(f"{item_url}/assign/employees", params={"q": "sidorov"}).text
    assert "1 çalışan bulundu" in found
    confirm_url = _one(r'hx-get="([^"]+/assign/confirm\?employee_id=[^"]+)"', found)
    assert confirm_url == f"{item_url}/assign/confirm?employee_id={employee.id}"
    first = client.get(confirm_url).text
    assert f'<p class="confirm-text" role="alert">{FIRST_TEXT}</p>' in first
    assert f'hx-post="{item_url}/assign/prepare"' in first
    second = client.post(f"{item_url}/assign/prepare", data={"employee_id": employee.id})
    assert second.status_code == 200, second.text
    assert f'<p class="confirm-text" role="alert">{SECOND_TEXT}</p>' in second.text
    assigned = client.post(
        f"{item_url}/assign",
        data={"employee_id": employee.id, "confirmation": _token(second.text)},
    )
    assert assigned.status_code == 200, assigned.text
    file_name = _one(
        rf"Öğe {EMPLOYEE_NAME} \({employee.id}\) çalışanına atandı: ([^<]+?)\. ", assigned.text
    )
    assert file_name.endswith(".pdf")

    # Kuyruk boşaldı; öğe çözüldü ve olay kullanıcı adıyla yazıldı.
    listing = client.get("/queues", params={"tab": "unresolved"}).text
    assert 'title="Bekleyen öğe">0</span>' in listing
    detail = client.get(item_url).text
    assert "<dt>Durum</dt><dd>Çözülen</dd>" in detail
    assert "MANUAL_ASSIGN" in detail and SIGNED_IN.username in detail

    # 4) Profilde gör: belge çalışanın belge listesinde, bağlantısı yeni sekmede açar.
    profile = client.get(f"/employees/{employee.id}")
    assert profile.status_code == 200
    documents = profile.text.split('<section class="profile-documents">', 1)[1]
    documents = documents.split("</section>", 1)[0]
    assert '<span class="count">1</span>' in documents
    link = re.search(
        rf'<a href="(/employees/{employee.id}/documents/\d+/file)" target="_blank" '
        rf'rel="noopener">{re.escape(file_name)}</a>',
        documents,
    )
    assert link is not None, documents

    # 5) Yeni sekmede aç: dosya satır içi sunulur, baytları Hazir'daki dosyanın ve yüklenenin aynı.
    opened = client.get(link.group(1))
    assert opened.status_code == 200
    assert opened.headers["content-type"] == "application/pdf"
    assert opened.headers["content-disposition"].startswith("inline")
    assert f'filename="{file_name}"' in opened.headers["content-disposition"]
    ready = layout.ready_dir(employee.folder_name) / file_name
    assert opened.content == ready.read_bytes()
    assert opened.content == pdf  # tek sayfalı tek belge olduğu gibi taşındı (K11, K17)
