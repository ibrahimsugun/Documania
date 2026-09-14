"""01.1.1, 01.1.2, 01.3.1 — çoklu dosya yükleme, bağlam çalışanı, boyut/sayfa sınırı."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import Employee, Event, Upload, UploadFile
from app.storage import DataLayout, sha256_bytes
from app.web.routers.uploads import get_layout
from tests.fixtures.gen import make_pdf_bytes


def test_get_layout_uses_settings_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./unused.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert get_layout().root == tmp_path
    finally:
        get_settings.cache_clear()


def _files(*items: tuple[str, bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, content, "application/octet-stream")) for name, content in items]


def test_upload_accepts_multiple_files_and_returns_upload_id(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        "/api/uploads",
        files=_files(("pasaport.pdf", b"%PDF-1.4 test"), ("foto.jpg", b"\xff\xd8\xff test")),
    )

    assert response.status_code == 201
    upload_id = response.json()["upload_id"]
    assert upload_id.startswith("u_")

    with session_factory() as session:
        upload = session.get(Upload, upload_id)
        assert upload is not None
        assert upload.channel == "web"
        assert upload.context_employee_id is None

        files = session.scalars(
            select(UploadFile).where(UploadFile.upload_id == upload_id).order_by(UploadFile.id)
        ).all()
        assert [f.original_name for f in files] == ["pasaport.pdf", "foto.jpg"]
        assert files[0].sha256 == sha256_bytes(b"%PDF-1.4 test")
        assert files[0].stored_path == f"Inbox/{upload_id}/pasaport.pdf"
        assert files[0].mime == "application/octet-stream"

        events = session.scalars(
            select(Event).where(Event.upload_id == upload_id).order_by(Event.id)
        ).all()
        assert [event.type for event in events] == ["FILE_UPLOADED", "FILE_UPLOADED"]
        assert [event.file_id for event in events] == [files[0].id, files[1].id]

    inbox = layout.upload_inbox_dir(upload_id)
    assert (inbox / "pasaport.pdf").read_bytes() == b"%PDF-1.4 test"
    assert (inbox / "foto.jpg").read_bytes() == b"\xff\xd8\xff test"


def test_second_upload_same_day_gets_next_sequence(client: TestClient) -> None:
    first = client.post("/api/uploads", files=_files(("a.pdf", b"1"))).json()["upload_id"]
    second = client.post("/api/uploads", files=_files(("b.pdf", b"2"))).json()["upload_id"]

    assert first != second
    assert first.rsplit("_", 1)[0] == second.rsplit("_", 1)[0]


def test_context_employee_id_is_stored_on_upload(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(
            Employee(id="E0001", folder_name="Test_Kisi_E0001", given_names="Test", surname="Kisi")
        )
        session.commit()

    response = client.post(
        "/api/uploads",
        data={"context_employee_id": "E0001"},
        files=_files(("a.pdf", b"1")),
    )

    assert response.status_code == 201
    upload_id = response.json()["upload_id"]
    with session_factory() as session:
        upload = session.get(Upload, upload_id)
        assert upload is not None
        assert upload.context_employee_id == "E0001"


def test_unknown_context_employee_id_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/uploads",
        data={"context_employee_id": "E9999"},
        files=_files(("a.pdf", b"1")),
    )

    assert response.status_code == 404


def test_no_files_is_rejected(client: TestClient) -> None:
    # FastAPI, çok parçalı istekte `files` alanı hiç yoksa (`File(...)` zorunlu) kendi
    # 422 doğrulamasını üretir; uç nokta bu durum için ayrı bir kontrol eklemez.
    response = client.post("/api/uploads", files=[])

    assert response.status_code == 422


def test_duplicate_filename_in_same_batch_returns_400(client: TestClient) -> None:
    response = client.post("/api/uploads", files=_files(("a.pdf", b"1"), ("a.pdf", b"2")))

    assert response.status_code == 400


def test_path_traversal_filename_is_rejected(client: TestClient) -> None:
    response = client.post("/api/uploads", files=_files(("../evil.pdf", b"1")))

    assert response.status_code == 400


def test_no_files_does_not_create_upload_row(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client.post("/api/uploads", files=[])

    with session_factory() as session:
        assert session.scalar(select(Upload)) is None


def _with_settings(app: FastAPI, **overrides: object) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="sqlite://", **overrides)


def test_oversized_file_is_rejected_and_told_to_split(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _with_settings(app, max_upload_file_size_bytes=10)

    response = client.post("/api/uploads", files=_files(("buyuk.pdf", b"0123456789A")))

    assert response.status_code == 400
    assert "böl" in response.json()["detail"].lower()
    with session_factory() as session:
        assert session.scalar(select(Upload)) is None


def test_file_at_exact_size_limit_is_accepted(app: FastAPI, client: TestClient) -> None:
    _with_settings(app, max_upload_file_size_bytes=10)

    response = client.post("/api/uploads", files=_files(("tam.pdf", b"0123456789")))

    assert response.status_code == 201


def test_pdf_over_page_limit_is_rejected_and_told_to_split(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _with_settings(app, max_upload_pdf_pages=2)

    response = client.post("/api/uploads", files=_files(("cok-sayfali.pdf", make_pdf_bytes(3))))

    assert response.status_code == 400
    assert "böl" in response.json()["detail"].lower()
    with session_factory() as session:
        assert session.scalar(select(Upload)) is None


def test_pdf_at_exact_page_limit_is_accepted(app: FastAPI, client: TestClient) -> None:
    _with_settings(app, max_upload_pdf_pages=2)

    response = client.post("/api/uploads", files=_files(("iki-sayfali.pdf", make_pdf_bytes(2))))

    assert response.status_code == 201


def test_non_pdf_content_is_not_page_checked(app: FastAPI, client: TestClient) -> None:
    _with_settings(app, max_upload_pdf_pages=1)

    response = client.post("/api/uploads", files=_files(("foto.jpg", b"\xff\xd8\xff test bytes")))

    assert response.status_code == 201
