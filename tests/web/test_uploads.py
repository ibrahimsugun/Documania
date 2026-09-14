"""01.1.1, 01.1.2, 01.3.1, 01.6.1 — çoklu dosya yükleme, bağlam çalışanı, boyut/sayfa
sınırı, parti durumu sorgulama."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import Employee, Event, Page, Upload, UploadFile
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


def test_duplicate_content_in_second_upload_is_flagged(
    client: TestClient, layout: DataLayout, session_factory: sessionmaker[Session]
) -> None:
    """S2 — aynı dosya ikinci kez yükleniyor: tekrar tespit edilir, ikinci kopya reddedilmez."""
    content = b"%PDF-1.4 pasaport"
    first_upload_id = client.post("/api/uploads", files=_files(("pasaport.pdf", content))).json()[
        "upload_id"
    ]
    second_response = client.post("/api/uploads", files=_files(("pasaport-2.pdf", content)))

    assert second_response.status_code == 201
    second_upload_id = second_response.json()["upload_id"]

    with session_factory() as session:
        first_file = session.scalar(
            select(UploadFile).where(UploadFile.upload_id == first_upload_id)
        )
        second_file = session.scalar(
            select(UploadFile).where(UploadFile.upload_id == second_upload_id)
        )
        assert first_file is not None
        assert second_file is not None
        assert first_file.is_duplicate_of is None
        assert second_file.is_duplicate_of == first_file.id

        first_events = session.scalars(
            select(Event).where(Event.upload_id == first_upload_id)
        ).all()
        second_events = session.scalars(
            select(Event).where(Event.upload_id == second_upload_id)
        ).all()
        assert [event.type for event in first_events] == ["FILE_UPLOADED"]
        assert [event.type for event in second_events] == ["FILE_DUPLICATE"]
        assert second_events[0].data_json == {"duplicate_of_file_id": first_file.id}

    # Orijinal dosya değişmeden Inbox'a yazılmaya devam eder (K10) — tekrar reddedilmez.
    second_inbox = layout.upload_inbox_dir(second_upload_id)
    assert (second_inbox / "pasaport-2.pdf").read_bytes() == content


def test_third_identical_upload_points_to_first_not_second(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Zincirlenme yok: art arda gelen tekrarların hepsi kök (ilk) dosyaya bağlanır."""
    content = b"ucuncu tekrar testi"
    first_upload_id = client.post("/api/uploads", files=_files(("a.pdf", content))).json()[
        "upload_id"
    ]
    client.post("/api/uploads", files=_files(("b.pdf", content)))
    third_upload_id = client.post("/api/uploads", files=_files(("c.pdf", content))).json()[
        "upload_id"
    ]

    with session_factory() as session:
        first_file = session.scalar(
            select(UploadFile).where(UploadFile.upload_id == first_upload_id)
        )
        third_file = session.scalar(
            select(UploadFile).where(UploadFile.upload_id == third_upload_id)
        )
        assert first_file is not None
        assert third_file is not None
        assert third_file.is_duplicate_of == first_file.id


def test_get_upload_status_returns_status_files_and_progress(client: TestClient) -> None:
    upload_id = client.post(
        "/api/uploads",
        files=_files(("pasaport.pdf", b"%PDF-1.4 test"), ("foto.jpg", b"\xff\xd8\xff test")),
    ).json()["upload_id"]

    response = client.get(f"/api/uploads/{upload_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["upload_id"] == upload_id
    assert body["status"] == "received"
    assert [f["original_name"] for f in body["files"]] == ["pasaport.pdf", "foto.jpg"]
    assert body["files"][0]["sha256"] == sha256_bytes(b"%PDF-1.4 test")
    assert body["files"][0]["mime"] == "application/octet-stream"
    assert body["files"][0]["is_duplicate"] is False
    assert body["progress"] == {"total_files": 2, "rendered_files": 0}


def test_get_upload_status_marks_duplicate_files(client: TestClient) -> None:
    content = b"tekrar iceren dosya"
    first_upload_id = client.post("/api/uploads", files=_files(("a.pdf", content))).json()[
        "upload_id"
    ]
    second_upload_id = client.post("/api/uploads", files=_files(("b.pdf", content))).json()[
        "upload_id"
    ]

    response = client.get(f"/api/uploads/{second_upload_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["files"][0]["is_duplicate"] is True

    first_response = client.get(f"/api/uploads/{first_upload_id}")
    assert first_response.json()["files"][0]["is_duplicate"] is False


def test_get_upload_status_counts_rendered_files_via_pages(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    upload_id = client.post(
        "/api/uploads",
        files=_files(("a.pdf", b"%PDF-1.4 a"), ("b.pdf", b"%PDF-1.4 b")),
    ).json()["upload_id"]

    with session_factory() as session:
        files = session.scalars(
            select(UploadFile).where(UploadFile.upload_id == upload_id).order_by(UploadFile.id)
        ).all()
        session.add(Page(file_id=files[0].id, index=0))
        session.commit()

    response = client.get(f"/api/uploads/{upload_id}")

    assert response.json()["progress"] == {"total_files": 2, "rendered_files": 1}


def test_get_upload_status_404_for_unknown_upload(client: TestClient) -> None:
    response = client.get("/api/uploads/u_yoktur")

    assert response.status_code == 404
