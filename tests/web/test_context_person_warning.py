"""10.5.5 — profilden yüklemede kişi denetiminin uyarısı: bağlam çalışanına ait görünmeyen belge
profile eklenmez, yükleme sonucunda, parti detayında ve profil sayfasında büyük kırmızı kutu çıkar;
her satırda belge türü, belgede okunan ad ↔ profil adı ve kuyruk öğesinin bağlantısı. Profil
sayfasındaki kutu kuyruk öğesi çözülene kadar kalır (PLAN.md §C83).

Senaryo sentetiktir: profil sayfasının yükleme formundan (10.5.3) başka bir kayıtlı çalışanın
pasaportu yüklenir; parti gerçek boru hattından geçer (`process_upload`, kayıtlı yanıt sağlayıcısı).
Yapay zekâ canlı çağrılmaz, gerçek kişi/belge yok (CONVENTIONS §6).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import (
    Document,
    Employee,
    EmployeeAlias,
    EmployeeIdentifier,
    Event,
    Plan,
    QueueItem,
    Upload,
)
from app.db.session import get_session_factory
from app.matching.match import PersonKey, normalize_document_number
from app.matching.names import normalize_name, transliterate_name
from app.pipeline.route import assign_queue_item
from app.storage import DataLayout
from app.web.context_person import WARNING_TITLE, _document_name
from app.worker import Worker
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    SyntheticPage,
    make_document_pdf_bytes,
    make_docx_bytes,
    passport_page,
    recorded_provider,
)

SETTINGS = Settings(_env_file=None, database_url="sqlite://")
PASSPORT_NUMBER = "00 0000001"
CONTEXT, OWNER = "E0001", "E0002"
ONE_FOREIGN = WARNING_TITLE.format(count=1)
READ_NAME = "TEST ORNEKOVA (Орнекова Тест)"


def _passport() -> SyntheticPage:
    return passport_page(
        PERSON_ORNEKOVA, document_number=PASSPORT_NUMBER, expiry_date=date(2030, 1, 1)
    )


@pytest.fixture
def registered(session_factory: sessionmaker[Session], layout: DataLayout) -> None:
    """Katalog tohumu ve iki sentetik çalışan: bağlam çalışanı Ana Prueba, pasaportun sahibi Test
    Ornekova (numarası kayıtlı)."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        for employee_id, given, surname, born, number in (
            (CONTEXT, "Ana", "Prueba", date(1995, 3, 15), None),
            (OWNER, "Test", "Ornekova", date(1990, 1, 1), PASSPORT_NUMBER),
        ):
            folder = f"{given}_{surname}_{employee_id}"
            employee = Employee(
                id=employee_id,
                folder_name=folder,
                given_names=given,
                surname=surname,
                date_of_birth=born,
            )
            session.add(employee)
            name = f"{given} {surname}"
            session.add(
                EmployeeAlias(
                    employee=employee, raw_name=name, normalized_name=normalize_name(name)
                )
            )
            if number is not None:
                value = normalize_document_number(number)
                session.add(
                    EmployeeIdentifier(employee=employee, kind="russian_passport", value=value)
                )
            layout.ensure_employee_tree(folder)
        session.commit()


@pytest.fixture
def process(
    app: FastAPI,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> Callable[..., None]:
    """Bir sonraki isteğin sayfalarını hazırlar; ayrı test worker'ını açıkça çalıştırır."""
    files: list[list[SyntheticPage]] = []
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    app.dependency_overrides[get_session_factory] = lambda: session_factory

    def run_worker(*value: list[SyntheticPage]) -> None:
        if value:
            files[:] = value
            return
        provider = recorded_provider(tmp_path / "worker", *files)
        worker = Worker(session_factory, layout, settings=SETTINGS, provider=provider)
        assert worker.run_once() is True

    return run_worker


def _upload_from_profile(
    client: TestClient,
    process: Callable[..., None],
    employee_id: str | None,
    name: str = "pasaport.pdf",
    content: bytes | None = None,
) -> tuple[str, str]:
    """Profilin yükleme formuyla (bağlamsız yüklemede yükleme sayfasıyla) gönderir; parti
    kimliğini ve yükleme sonucunun parçasını döner."""
    pages = [_passport()]
    process(pages)
    response = client.post(
        "/upload",
        files=[("files", (name, content or make_document_pdf_bytes(pages), "application/pdf"))],
        data={"context_employee_id": employee_id or ""},
    )
    assert response.status_code == 201, response.text
    process()  # enqueue işleminden sonra kuyruk tüketicisi ayrı adımda çalışır
    match = re.search(r"<h2>Parti ([A-Za-z0-9_-]+)</h2>", response.text)
    assert match is not None, response.text
    return match.group(1), response.text


def _warning(html: str) -> str | None:
    """Sayfadaki uyarı kutusu; yoksa `None`."""
    match = re.search(r'<section class="context-warning".*?</section>', html, re.S)
    return None if match is None else match.group(0)


def _queue_item(session_factory: sessionmaker[Session], upload_id: str) -> QueueItem:
    with session_factory() as session:
        return session.scalars(select(QueueItem).where(QueueItem.upload_id == upload_id)).one()


# --- senaryo: profilden başka kişinin pasaportu yüklenir ------------------------------------------


def test_passport_of_someone_else_uploaded_from_a_profile_is_warned_about_everywhere(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    registered: None,
    process: Callable[..., None],
) -> None:
    upload_id, result = _upload_from_profile(client, process, CONTEXT)
    queued = _queue_item(session_factory, upload_id)

    # Belge profile de sahibine de uygulanmadı: çıktı yok, öğe Unresolved'da.
    with session_factory() as session:
        assert session.scalars(select(Document)).all() == []
        assert session.get_one(Upload, upload_id).status == "done"
    assert queued.kind == "unresolved"
    assert queued.reason.startswith("Profilden yüklenen belge bu profile ait görünmüyor")

    # 10.2.2: gönderim anında parti sürüyordu, uyarı son durumu bekler; yenilenen ilerleme
    # görünümü parti bitince uyarıyı taşır.
    assert _warning(result) is None
    box = _warning(client.get(f"/upload/{upload_id}/progress").text)
    assert box is not None
    assert 'role="alert"' in box and ONE_FOREIGN in box
    assert "<td>Russian Passport</td>" in box
    assert f"<td>{READ_NAME}</td>" in box
    assert "<td>Ana Prueba</td>" in box
    assert f'<a href="/queues/{queued.id}">Öğe {queued.id}</a>' in box

    # 10.3.1: parti detayı.
    detail = _warning(client.get(f"/uploads/{upload_id}").text)
    assert detail is not None and ONE_FOREIGN in detail and READ_NAME in detail

    # 10.5.1: bağlam çalışanının profili uyarır; pasaportun sahibinin profili uyarmaz.
    profile = _warning(client.get(f"/employees/{CONTEXT}").text)
    assert profile is not None
    assert ONE_FOREIGN in profile and f'href="/queues/{queued.id}"' in profile
    assert _warning(client.get(f"/employees/{OWNER}").text) is None

    # Okunan ad ve profil adı yalnız görünümde: gerekçeye ve loga yazılmadı.
    with session_factory() as session:
        logged = [
            f"{event.message} {event.data_json}"
            for event in session.scalars(select(Event).where(Event.upload_id == upload_id))
        ]
    assert logged
    assert not [line for line in logged if "ORNEKOVA" in line or "Prueba" in line]
    assert "ORNEKOVA" not in queued.reason and "Prueba" not in queued.reason


def test_profile_warning_stays_until_the_queue_item_is_resolved(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    registered: None,
    process: Callable[..., None],
) -> None:
    upload_id, _ = _upload_from_profile(client, process, CONTEXT)
    queued = _queue_item(session_factory, upload_id)
    assert _warning(client.get(f"/employees/{CONTEXT}").text) is not None

    # İK kuyruktan pasaportu sahibine atar (08.2.1).
    with session_factory() as session:
        assign_queue_item(
            session,
            layout,
            queued.id,
            OWNER,
            actor="test-yonetici",
            render_image_dpi=100,
            render_image_jpeg_quality=90,
        )
        session.commit()

    assert _warning(client.get(f"/employees/{CONTEXT}").text) is None
    # Parti görünümü olanı söylemeye devam eder, öğeyi çözülmüş gösterir.
    detail = _warning(client.get(f"/uploads/{upload_id}").text)
    assert detail is not None and f"Öğe {queued.id}</a> · çözüldü" in detail


def test_profile_warning_counts_only_the_unresolved_items_of_an_upload(
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    registered: None,
    process: Callable[..., None],
) -> None:
    # Aynı partide iki başka kişinin pasaportu: biri (numarası kayıtlı) sahibine atanınca profil
    # kutusu yalnız bekleyeni sayar; parti görünümü ikisini de gösterir.
    ornekova = [_passport()]
    sidorov = [
        passport_page(PERSON_SIDOROV, document_number="00 0000002", expiry_date=date(2030, 1, 1))
    ]
    process(ornekova, sidorov)
    response = client.post(
        "/upload",
        files=[
            ("files", (name, make_document_pdf_bytes(pages), "application/pdf"))
            for name, pages in (("pasaport-1.pdf", ornekova), ("pasaport-2.pdf", sidorov))
        ],
        data={"context_employee_id": CONTEXT},
    )
    assert response.status_code == 201, response.text
    process()
    with session_factory() as session:
        upload_id = session.scalars(select(Upload.id)).one()
        first, second = session.scalars(select(QueueItem).order_by(QueueItem.id)).all()
    before = _warning(client.get(f"/employees/{CONTEXT}").text)
    assert before is not None and WARNING_TITLE.format(count=2) in before

    with session_factory() as session:
        assign_queue_item(
            session,
            layout,
            first.id,
            OWNER,
            actor="test-yonetici",
            render_image_dpi=100,
            render_image_jpeg_quality=90,
        )
        session.commit()

    after = _warning(client.get(f"/employees/{CONTEXT}").text)
    assert after is not None and ONE_FOREIGN in after
    assert f'href="/queues/{second.id}"' in after and f'href="/queues/{first.id}"' not in after
    assert "IVAN SIDOROV" in after and "ORNEKOVA" not in after
    detail = _warning(client.get(f"/uploads/{upload_id}").text)
    assert detail is not None and WARNING_TITLE.format(count=2) in detail


@pytest.mark.parametrize("context", [None, OWNER], ids=["baglamsiz-yukleme", "kendi-profilinden"])
def test_no_warning_without_a_context_or_for_the_context_employees_own_passport(
    client: TestClient,
    session_factory: sessionmaker[Session],
    registered: None,
    process: Callable[..., None],
    context: str | None,
) -> None:
    # Pasaport sahibine gider (satır 1); uyarı yok.
    upload_id, _ = _upload_from_profile(client, process, context)

    with session_factory() as session:
        (document,) = session.scalars(select(Document)).all()
        assert document.employee_id == OWNER
    assert _warning(client.get(f"/upload/{upload_id}/progress").text) is None
    assert _warning(client.get(f"/uploads/{upload_id}").text) is None
    assert _warning(client.get(f"/employees/{CONTEXT}").text) is None
    assert _warning(client.get(f"/employees/{OWNER}").text) is None


def test_word_attachment_from_a_profile_is_not_checked(
    client: TestClient,
    session_factory: sessionmaker[Session],
    registered: None,
    process: Callable[..., None],
) -> None:
    # 04.7.1 değişmez: ek analiz edilmez, bağlam çalışanına Hazir gider.
    upload_id, _ = _upload_from_profile(
        client, process, CONTEXT, name="ozgecmis.docx", content=make_docx_bytes()
    )

    with session_factory() as session:
        (document,) = session.scalars(select(Document)).all()
        assert document.employee_id == CONTEXT
    assert _warning(client.get(f"/upload/{upload_id}/progress").text) is None
    assert _warning(client.get(f"/uploads/{upload_id}").text) is None


def test_a_plan_that_cannot_be_verified_draws_no_warning(
    client: TestClient,
    session_factory: sessionmaker[Session],
    registered: None,
    process: Callable[..., None],
) -> None:
    # Saklanan plan dondurulduktan sonra değişmiş (K9): parti sayfası nedeni gösterir, kutu
    # çizilmez.
    upload_id, _ = _upload_from_profile(client, process, CONTEXT)
    with session_factory() as session:
        plan = session.scalars(select(Plan).where(Plan.upload_id == upload_id)).one()
        plan.json = {**plan.json, "model": "degismis"}
        session.commit()

    page = client.get(f"/uploads/{upload_id}").text

    assert "uyuşmuyor" in page
    assert _warning(page) is None
    assert _warning(client.get(f"/employees/{CONTEXT}").text) is None


# --- belgede okunan adın gösterimi ----------------------------------------------------------------


def _key(**names: str | None) -> PersonKey:
    original = names.pop("original", None)
    return PersonKey(
        (),
        None,
        None,
        None if original is None else transliterate_name(original),
        None,
        True,
        (),
        **names,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("key", "shown"),
    [
        (_key(surname="ORNEKOVA", given_names="TEST", original="Орнекова Тест"), READ_NAME),
        (_key(surname="ORNEKOVA", given_names="TEST"), "TEST ORNEKOVA"),
        # Latin yazımı olmayan ad (05.2.2): yalnız orijinal yazım.
        (_key(surname="محمد", given_names=None), "محمد"),
        (_key(original="Орнекова Тест"), "Орнекова Тест"),
        (_key(), "—"),
    ],
    ids=["latin-ve-orijinal", "latin", "arap", "yalniz-orijinal", "okunmadi"],
)
def test_the_read_name_is_latin_first_with_the_original_beside_it(
    key: PersonKey, shown: str
) -> None:
    assert _document_name(key) == shown
