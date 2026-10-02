"""10.2.1, 10.2.2 — yükleme sayfası (sürükle-bırak çoklu yükleme, isteğe bağlı çalışan) ve
partinin canlı yenilenen ilerleme görünümü.

Sayfa `POST /api/uploads`'ın işlevini kullanır; boyut/sayfa sınırı, Inbox'a yazma ve tekrar
tespiti orada sınanır (`test_uploads.py`), burada yalnız sayfanın bunlara bağlandığı doğrulanır.
Yapay zekâ canlı çağrılmaz: uçtan uca testte sağlayıcı kayıtlı yanıtlardan kurulur.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import Employee, Event, JobStatus, Upload, UploadFile, UploadJob, UploadStatus
from app.db.session import get_session_factory
from app.events import EventType
from app.storage import DataLayout
from app.web.routers.upload_page import FINAL_STATUSES, STATUS_LABELS
from app.worker import Worker
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    make_document_pdf_bytes,
    make_pdf_bytes,
    passport_page,
    recorded_provider,
)

POLLING = 'hx-trigger="every 2s"'


def _files(*items: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, content, "application/octet-stream")) for name, content in items]


class _UploadIds:
    """Test helper exposing created upload IDs without executing the queue job."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    @property
    def upload_ids(self) -> list[str]:
        with self.session_factory() as session:
            return list(session.scalars(select(Upload.id).order_by(Upload.id)))


@pytest.fixture
def uploads(session_factory: sessionmaker[Session]) -> _UploadIds:
    return _UploadIds(session_factory)


def _employee(session_factory: sessionmaker[Session], number: int, given: str, surname: str) -> str:
    employee_id = f"E{number:04d}"
    with session_factory() as session:
        session.add(
            Employee(
                id=employee_id,
                folder_name=f"{given}_{surname}_{employee_id}",
                given_names=given,
                surname=surname,
            )
        )
        session.commit()
    return employee_id


def _upload_count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(Upload)) or 0


def _set_status(session_factory: sessionmaker[Session], upload_id: str, status: str) -> None:
    with session_factory() as session:
        session.get_one(Upload, upload_id).status = status
        session.commit()


# --- 10.2.1: sayfa -----------------------------------------------------------------------------


def test_page_offers_a_multi_file_drop_zone_and_loads_its_scripts(client: TestClient) -> None:
    page = client.get("/upload")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<title>Yükle · Documania</title>" in page.text
    assert "<h1>Yükle</h1>" in page.text
    assert 'id="dropzone"' in page.text
    assert re.search(r'<input id="files" name="files" type="file" multiple\b', page.text)
    assert 'hx-post="/upload"' in page.text
    assert 'hx-encoding="multipart/form-data"' in page.text
    assert 'src="/static/htmx.min.js"' in page.text
    assert 'src="/static/upload.js"' in page.text
    assert 'id="upload-result"' in page.text


def test_page_scripts_are_served_without_a_session(app: FastAPI) -> None:
    from app.web.auth import get_current_user

    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    htmx = anonymous.get("/static/htmx.min.js")
    script = anonymous.get("/static/upload.js")

    assert htmx.status_code == 200
    assert "htmx" in htmx.text[:200] + htmx.text[-200:]
    assert script.status_code == 200
    # Sürükle-bırak: bırakılan dosyalar dosya alanına aktarılır.
    assert '"drop"' in script.text
    assert "dataTransfer.files" in script.text
    assert "input.files = merged.files" in script.text


def test_employee_choice_is_optional_and_lists_every_employee(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    first = _employee(session_factory, 1, "Ada", "Örnek")
    second = _employee(session_factory, 2, "Bora", "Deneme")

    page = client.get("/upload")

    select_html = re.search(r'<select id="context_employee_id".*?</select>', page.text, re.S)
    assert select_html is not None
    options = re.findall(r'<option value="([^"]*)">([^<]*)</option>', select_html.group(0))
    assert options[0][0] == ""  # boş seçenek: çalışan belirtme
    assert options[1:] == [
        (first, f"{first} — Ada Örnek"),
        (second, f"{second} — Bora Deneme"),
    ]
    assert "required" not in select_html.group(0)


def test_page_without_employees_still_offers_the_empty_choice(client: TestClient) -> None:
    page = client.get("/upload")

    assert page.text.count("<option") == 1


# --- 10.2.1: yükleme ---------------------------------------------------------------------------


def test_submitting_several_files_creates_one_batch_and_queues_it_for_the_worker(
    client: TestClient,
    layout: DataLayout,
    session_factory: sessionmaker[Session],
    uploads: _UploadIds,
) -> None:
    response = client.post(
        "/upload",
        files=_files(("pasaport.pdf", b"%PDF-1.4 test"), ("foto.jpg", b"\xff\xd8\xff test")),
        data={"context_employee_id": ""},
    )

    assert response.status_code == 201
    with session_factory() as session:
        upload = session.scalars(select(Upload)).one()
        assert (upload.channel, upload.context_employee_id) == ("web", None)
        names = [file.original_name for file in upload.files]
        assert names == ["pasaport.pdf", "foto.jpg"]
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload.id)).one()
        assert (job.status, job.attempts) == (JobStatus.QUEUED, 0)
    inbox = layout.upload_inbox_dir(upload.id)
    assert (inbox / "pasaport.pdf").read_bytes() == b"%PDF-1.4 test"
    assert (inbox / "foto.jpg").read_bytes() == b"\xff\xd8\xff test"

    # Yanıt HTMX parçasıdır (tam sayfa değil) ve partiyi izlemeye başlar.
    assert "<html" not in response.text
    assert f"Parti {upload.id}" in response.text
    assert "pasaport.pdf" in response.text and "foto.jpg" in response.text
    assert "Alındı" in response.text
    assert f'hx-get="/upload/{upload.id}/progress"' in response.text
    assert POLLING in response.text


def test_chosen_employee_becomes_the_batch_context(
    client: TestClient, session_factory: sessionmaker[Session], uploads: _UploadIds
) -> None:
    employee_id = _employee(session_factory, 1, "Ada", "Örnek")

    response = client.post(
        "/upload",
        files=_files(("cv.pdf", b"%PDF-1.4 cv")),
        data={"context_employee_id": employee_id},
    )

    assert response.status_code == 201
    with session_factory() as session:
        assert session.scalars(select(Upload)).one().context_employee_id == employee_id


def test_unknown_employee_is_rejected_and_nothing_is_stored(
    client: TestClient,
    layout: DataLayout,
    session_factory: sessionmaker[Session],
    uploads: _UploadIds,
) -> None:
    response = client.post(
        "/upload", files=_files(("cv.pdf", b"%PDF-1.4 cv")), data={"context_employee_id": "E9999"}
    )

    assert response.status_code == 404
    assert 'role="alert"' in response.text and "context_employee_id bulunamadı." in response.text
    assert _upload_count(session_factory) == 0
    assert not any(layout.inbox.iterdir())


@pytest.mark.parametrize("files", [None, [("files", ("", b"", "application/octet-stream"))]])
def test_submitting_without_a_chosen_file_says_so(
    client: TestClient,
    session_factory: sessionmaker[Session],
    uploads: _UploadIds,
    files: list[tuple[str, tuple[str, bytes, str]]] | None,
) -> None:
    # Tarayıcı dosya seçilmemişken adı boş tek bir parça gönderir.
    response = client.post("/upload", files=files, data={"context_employee_id": ""})

    assert response.status_code == 400
    assert "Yüklenecek dosya seçilmedi." in response.text
    assert _upload_count(session_factory) == 0


def test_upload_limits_of_the_api_apply_to_the_page(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    uploads: _UploadIds,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite://", max_upload_file_size_bytes=10
    )

    response = client.post("/upload", files=_files(("buyuk.pdf", b"%PDF-1.4 " + b"x" * 50)))

    assert response.status_code == 400
    assert "buyuk.pdf" in response.text and "bölüp tekrar yükleyin" in response.text
    assert _upload_count(session_factory) == 0


def test_a_file_name_the_inbox_cannot_hold_is_shown_as_a_message_not_a_500(
    client: TestClient,
    layout: DataLayout,
    session_factory: sessionmaker[Session],
    uploads: _UploadIds,
) -> None:
    response = client.post("/upload", files=_files(("a<b>.pdf", make_pdf_bytes(1))))

    assert response.status_code == 400
    # Ad kullanıcıdan gelir: mesaj HTML'e kaçırılarak gösterilir.
    assert 'role="alert"' in response.text and "Geçersiz dosya adı" in response.text
    assert "a&lt;b&gt;.pdf" in response.text and "a<b>.pdf" not in response.text
    assert _upload_count(session_factory) == 0
    assert not any(layout.inbox.iterdir())


def test_an_unsupported_file_is_shown_as_a_message_and_nothing_is_stored(
    client: TestClient,
    layout: DataLayout,
    session_factory: sessionmaker[Session],
    uploads: _UploadIds,
) -> None:
    # Tarayıcının `accept=` süzgeci yalnız istemci tarafındadır; sunucu içeriğe bakıp reddeder.
    response = client.post(
        "/upload",
        files=_files(
            ("cv.pdf", make_pdf_bytes(1)), ("notlar.txt", b"Duz metin. Toplanti notlari.")
        ),
    )

    assert response.status_code == 400
    assert 'role="alert"' in response.text
    assert "Desteklenmeyen dosya türü" in response.text and "notlar.txt" in response.text
    assert "cv.pdf" not in response.text
    assert _upload_count(session_factory) == 0
    assert not any(layout.inbox.iterdir())


def test_duplicate_file_names_in_one_batch_are_rejected(
    client: TestClient, session_factory: sessionmaker[Session], uploads: _UploadIds
) -> None:
    response = client.post(
        "/upload", files=_files(("a.pdf", b"%PDF-1.4 1"), ("a.pdf", b"%PDF-1.4 2"))
    )

    assert response.status_code == 400
    assert "aynı adda birden çok dosya" in response.text
    assert _upload_count(session_factory) == 0


def test_repeated_file_is_marked_as_duplicate_in_the_view(
    client: TestClient, uploads: _UploadIds
) -> None:
    content = b"%PDF-1.4 ayni"
    client.post("/upload", files=_files(("ilk.pdf", content)))

    response = client.post("/upload", files=_files(("ikinci.pdf", content)))

    assert response.status_code == 201
    assert "Daha önce yüklenmiş" in response.text


def test_upload_app_does_not_need_provider_and_leaves_job_queued(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # HTTP alım servisi provider kurmaz; eksik AI anahtarı işin alınmasını engellemez.
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="sqlite://", ai_provider="anthropic"
    )

    response = client.post("/upload", files=_files(("cv.pdf", b"%PDF-1.4 cv")))

    assert response.status_code == 201
    assert POLLING in response.text
    assert "Yapay zekâ sağlayıcısı kurulamadığı için" not in response.text
    with session_factory() as session:
        upload = session.scalars(select(Upload)).one()
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload.id)).one()
        assert upload.status == UploadStatus.RECEIVED
        assert (job.status, job.attempts) == (JobStatus.QUEUED, 0)


def test_file_names_are_escaped_in_the_view(client: TestClient, uploads: _UploadIds) -> None:
    response = client.post("/upload", files=_files(("a&b.pdf", b"%PDF-1.4 x")))

    assert response.status_code == 201
    assert "a&b.pdf" not in response.text
    assert "a&amp;b.pdf" in response.text


# --- 10.2.2: canlı ilerleme --------------------------------------------------------------------


@pytest.mark.parametrize("status", list(UploadStatus))
def test_progress_refreshes_itself_until_the_batch_reaches_a_final_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
    uploads: _UploadIds,
    status: UploadStatus,
) -> None:
    created = client.post("/upload", files=_files(("cv.pdf", b"%PDF-1.4 cv")))
    upload_id = uploads.upload_ids[0]
    assert created.status_code == 201
    _set_status(session_factory, upload_id, status.value)

    response = client.get(f"/upload/{upload_id}/progress")

    assert response.status_code == 200
    assert "<html" not in response.text
    assert STATUS_LABELS[status] in response.text
    assert f'class="status status-{status.value}"' in response.text
    assert (POLLING in response.text) == (status not in FINAL_STATUSES)
    if status not in FINAL_STATUSES:
        assert f'hx-get="/upload/{upload_id}/progress"' in response.text
        assert 'hx-swap="outerHTML"' in response.text


def test_progress_steps_follow_the_pipeline(
    client: TestClient, session_factory: sessionmaker[Session], uploads: _UploadIds
) -> None:
    client.post("/upload", files=_files(("cv.pdf", b"%PDF-1.4 cv")))
    upload_id = uploads.upload_ids[0]

    def steps(status: UploadStatus) -> list[tuple[str, str]]:
        _set_status(session_factory, upload_id, status.value)
        html = client.get(f"/upload/{upload_id}/progress").text
        return re.findall(r'<li class="step step-(\w+)"[^>]*>([^<]+)</li>', html)

    labels = [
        "Alındı",
        "Sayfalar hazırlanıyor",
        "Analiz ediliyor",
        "Plan hazırlanıyor",
        "Plan uygulanıyor",
    ]
    assert steps(UploadStatus.RECEIVED) == list(
        zip(["current", "todo", "todo", "todo", "todo"], labels, strict=True)
    )
    assert steps(UploadStatus.ANALYZING) == list(
        zip(["done", "done", "current", "todo", "todo"], labels, strict=True)
    )
    assert steps(UploadStatus.DONE) == list(zip(["done"] * 5, labels, strict=True))
    assert steps(UploadStatus.PARTIAL) == list(zip(["done"] * 5, labels, strict=True))
    assert steps(UploadStatus.FAILED) == list(zip(["todo"] * 5, labels, strict=True))


def test_progress_counts_rendered_files_and_shows_page_counts(
    client: TestClient, session_factory: sessionmaker[Session], uploads: _UploadIds
) -> None:
    client.post("/upload", files=_files(("a.pdf", b"%PDF-1.4 a"), ("b.pdf", b"%PDF-1.4 b")))
    upload_id = uploads.upload_ids[0]

    before = client.get(f"/upload/{upload_id}/progress").text
    assert "Sayfaları hazırlanan dosya: 0 / 2" in before
    assert "<td>—</td>" in before

    with session_factory() as session:
        file = session.scalars(select(UploadFile).order_by(UploadFile.id)).first()
        assert file is not None
        file.page_count = 3
        session.commit()

    after = client.get(f"/upload/{upload_id}/progress").text
    assert "<td>3</td>" in after


def test_file_counter_skips_duplicates_and_disappears_when_the_batch_is_final(
    client: TestClient, session_factory: sessionmaker[Session], uploads: _UploadIds
) -> None:
    client.post("/upload", files=_files(("ilk.pdf", b"%PDF-1.4 ayni")))
    client.post(
        "/upload", files=_files(("kopya.pdf", b"%PDF-1.4 ayni"), ("yeni.pdf", b"%PDF-1.4 y"))
    )
    upload_id = uploads.upload_ids[1]

    running = client.get(f"/upload/{upload_id}/progress").text
    assert "Sayfaları hazırlanan dosya: 0 / 1" in running  # tekrar dosyası işlenmez
    assert "Daha önce yüklenmiş" in running

    _set_status(session_factory, upload_id, UploadStatus.DONE.value)
    final = client.get(f"/upload/{upload_id}/progress").text
    assert "Sayfaları hazırlanan dosya" not in final


def test_progress_of_an_unknown_batch_is_a_404_fragment(client: TestClient) -> None:
    response = client.get("/upload/u_yok/progress")

    assert response.status_code == 404
    assert "Parti bulunamadı." in response.text
    assert POLLING not in response.text


def test_page_and_progress_need_a_session(app: FastAPI) -> None:
    from app.web.auth import get_current_user

    del app.dependency_overrides[get_current_user]
    anonymous = TestClient(app)

    for method, path in (
        ("GET", "/upload"),
        ("POST", "/upload"),
        ("GET", "/upload/u_1/progress"),
    ):
        response = anonymous.request(method, path, follow_redirects=False)
        assert response.status_code == 303, (method, path)
        assert response.headers["location"].startswith("/login"), (method, path)


# --- 10.2.2: arka plan işleyicisi --------------------------------------------------------------


@pytest.fixture
def recorded_processing(
    app: FastAPI,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> Worker:
    """Ayrı kuyruk servisinin test worker'ı; HTTP isteği kendi başına işi tüketmez."""
    with session_factory() as session:
        import_catalog(session, load_seed_catalog())
        session.commit()
    provider = recorded_provider(
        tmp_path / "kayit",
        [
            passport_page(
                PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
            )
        ],
    )
    settings = Settings(_env_file=None, database_url="sqlite://", ai_provider="anthropic")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    return Worker(session_factory, layout, settings=settings, provider=provider)


def test_uploaded_batch_waits_for_worker_then_reaches_done(
    client: TestClient,
    session_factory: sessionmaker[Session],
    recorded_processing: Worker,
) -> None:
    pdf = make_document_pdf_bytes(
        [passport_page(PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1))]
    )

    response = client.post("/upload", files=_files(("pasaport.pdf", pdf)))

    assert response.status_code == 201
    assert "Alındı" in response.text and POLLING in response.text
    upload_match = re.search(r"Parti (u_\w+)", response.text)
    assert upload_match is not None
    upload_id = upload_match.group(1)
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        assert upload.status == UploadStatus.RECEIVED
        assert (job.status, job.attempts) == (JobStatus.QUEUED, 0)

    # Yalnız açıkça çalıştırılan worker işi alır; web isteği tamamlandıktan sonra işlem sürer.
    assert recorded_processing.run_once() is True
    poll = client.get(f"/upload/{upload_id}/progress")
    assert poll.status_code == 200
    assert "Tamamlandı" in poll.text
    assert POLLING not in poll.text
    assert "<td>1</td>" in poll.text
    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        assert upload.status == UploadStatus.DONE
        types = set(session.scalars(select(Event.type).where(Event.upload_id == upload.id)))
        assert {EventType.FILE_UPLOADED, EventType.PLAN_CREATED, EventType.OUTPUT_SAVED} <= types
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        assert (job.upload_id, job.status, job.attempts) == (upload.id, JobStatus.FINISHED, 1)
