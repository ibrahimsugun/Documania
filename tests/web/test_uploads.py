"""01.1.1, 01.1.2, 01.3.1, 01.6.1, 06.6.1, 06.6.2 — çoklu dosya yükleme, bağlam çalışanı,
boyut/sayfa sınırı, parti durumu sorgulama, planı yeniden çalıştırma ve yeniden analiz."""

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai import PROVIDER_FACTORIES, AnalysisProvider, build_page_analysis_instructions
from app.ai.recording_provider import RecordingProvider
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings, get_settings
from app.db.models import Document, DocumentStatus, Employee, Event, Page, Plan, Upload, UploadFile
from app.events import EventType
from app.pipeline.analyze import analyze_upload
from app.pipeline.plan import PlanDocument, create_plan, read_plan
from app.pipeline.render import render_upload_file
from app.storage import DataLayout, sha256_bytes
from app.web.routers.uploads import get_analysis_provider, get_layout, get_plan_executor
from tests.fixtures.gen import make_pdf_bytes, make_text_pdf_bytes


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


def test_get_upload_status_reflects_rendered_pdf_pages(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    """02.1.1 — yüklenen PDF render edilince durum sorgusu sayfa sayısını ve ilerlemeyi görür."""
    upload_id = client.post(
        "/api/uploads",
        files=_files(("tarama.pdf", make_pdf_bytes(2)), ("foto.jpg", b"\xff\xd8\xff test")),
    ).json()["upload_id"]

    with session_factory() as session:
        pdf = session.scalars(
            select(UploadFile).where(
                UploadFile.upload_id == upload_id, UploadFile.original_name == "tarama.pdf"
            )
        ).one()
        render_upload_file(session, layout, Settings(database_url="sqlite://"), pdf)
        session.commit()

    body = client.get(f"/api/uploads/{upload_id}").json()

    assert body["progress"] == {"total_files": 2, "rendered_files": 1}
    assert {file["original_name"]: file["page_count"] for file in body["files"]} == {
        "tarama.pdf": 2,
        "foto.jpg": None,
    }


def test_get_upload_status_404_for_unknown_upload(client: TestClient) -> None:
    response = client.get("/api/uploads/u_yoktur")

    assert response.status_code == 404


# --- 06.6.1, 06.6.2 — planı yeniden çalıştırma ve yeniden analiz --------------------------------

RECORDINGS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()


@dataclass
class _Executor:
    """`PlanExecutor` yerine: uygulanan planı kaydeder, çıktı üretmez (07.x henüz yok)."""

    calls: list[tuple[int, str]] = field(default_factory=list)
    fail: bool = False

    def __call__(
        self, session: Session, layout: DataLayout, plan: Plan, document: PlanDocument
    ) -> None:
        assert document == read_plan(plan)
        self.calls.append((plan.id, plan.plan_hash))
        if self.fail:
            raise RuntimeError("uygulayıcı durdu")


def _recording() -> RecordingProvider:
    return RecordingProvider.from_directory(RECORDINGS / "russian_passport")


def _planned_upload(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> tuple[str, int]:
    """Yüklenen sentetik pasaport render edilir, kayıtlı yanıtla analiz edilir, planı dondurulur."""
    upload_id = client.post(
        "/api/uploads", files=_files(("pasaport.pdf", make_text_pdf_bytes(["PASAPORT"])))
    ).json()["upload_id"]
    with session_factory() as session:
        import_catalog(session, CATALOG)
        upload = session.get_one(Upload, upload_id)
        render_upload_file(session, layout, Settings(database_url="sqlite://"), upload.files[0])
        analyze_upload(
            session,
            layout,
            upload,
            provider=_recording(),
            instructions=build_page_analysis_instructions(CATALOG),
        )
        plan = create_plan(session, layout, upload, catalog=CATALOG, model="recording")
        session.commit()
        return upload_id, plan.id


def _count_rows(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _event_types(session: Session, upload_id: str) -> list[str]:
    return list(
        session.scalars(select(Event.type).where(Event.upload_id == upload_id).order_by(Event.id))
    )


def test_rerun_applies_the_current_plan_without_building_an_ai_provider(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    upload_id, plan_id = _planned_upload(client, session_factory, layout)
    executor = _Executor()
    providers: list[AnalysisProvider] = []

    def _provider() -> AnalysisProvider:
        providers.append(_recording())
        return providers[-1]

    app.dependency_overrides[get_plan_executor] = lambda: executor
    app.dependency_overrides[get_analysis_provider] = _provider

    response = client.post(f"/api/uploads/{upload_id}/rerun")

    assert response.status_code == 200
    with session_factory() as session:
        plan = session.get_one(Plan, plan_id)
        assert response.json() == {
            "upload_id": upload_id,
            "plan_id": plan_id,
            "version": 1,
            "plan_hash": plan.plan_hash,
        }
        assert executor.calls == [(plan_id, plan.plan_hash)]
        assert providers == []
        assert plan.executed_at is not None
        assert _count_rows(session, Plan) == 1
        types = _event_types(session, upload_id)
        assert types[-1] == EventType.PLAN_RERUN
        assert types.count(EventType.PAGE_ANALYZED) == 1


def test_rerun_and_reanalysis_of_an_unknown_upload_are_404(
    app: FastAPI, client: TestClient
) -> None:
    app.dependency_overrides[get_plan_executor] = _Executor
    app.dependency_overrides[get_analysis_provider] = _recording

    for action in ("rerun", "reanalyze"):
        assert client.post(f"/api/uploads/u_yoktur/{action}").status_code == 404


def test_rerun_and_reanalysis_without_a_plan_are_409_and_call_nothing(
    app: FastAPI, client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    upload_id = client.post("/api/uploads", files=_files(("a.pdf", b"%PDF-1.4 a"))).json()[
        "upload_id"
    ]
    executor, provider = _Executor(), _recording()
    app.dependency_overrides[get_plan_executor] = lambda: executor
    app.dependency_overrides[get_analysis_provider] = lambda: provider

    for action in ("rerun", "reanalyze"):
        response = client.post(f"/api/uploads/{upload_id}/{action}")
        assert response.status_code == 409
        assert response.json()["detail"].startswith(f"Partinin planı yok (parti {upload_id})")

    assert (executor.calls, provider.requests) == ([], [])
    with session_factory() as session:
        assert _event_types(session, upload_id) == [EventType.FILE_UPLOADED]


def test_rerun_of_a_changed_plan_is_409_and_commits_nothing(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    upload_id, plan_id = _planned_upload(client, session_factory, layout)
    with session_factory() as session:
        plan = session.get_one(Plan, plan_id)
        changed = copy.deepcopy(plan.json)
        changed["items"][0]["target_name"] = "Baska_Kisi-Passport.pdf"
        plan.json = changed
        session.commit()
    executor = _Executor()
    app.dependency_overrides[get_plan_executor] = lambda: executor

    response = client.post(f"/api/uploads/{upload_id}/rerun")

    assert response.status_code == 409
    assert "hash'i kaydıyla uyuşmuyor" in response.json()["detail"]
    assert "Baska" not in response.json()["detail"]
    assert executor.calls == []
    with session_factory() as session:
        assert EventType.PLAN_RERUN not in _event_types(session, upload_id)
        assert session.get_one(Plan, plan_id).executed_at is None


def test_rerun_applies_the_plan_with_the_application_executor(
    client: TestClient, session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    # 09.2: `get_plan_executor` uygulamanın uygulayıcısıdır — çıktı, köken, Alinan ve profil.md.
    upload_id, plan_id = _planned_upload(client, session_factory, layout)
    folder = layout.employee_dir("Test_Ornekova_E0001")

    first = client.post(f"/api/uploads/{upload_id}/rerun")
    second = client.post(f"/api/uploads/{upload_id}/rerun")

    assert (first.status_code, second.status_code) == (200, 200)
    assert sorted(path.name for path in (folder / "Hazir").iterdir()) == [
        "Test_Ornekova-Passport.pdf"
    ]
    assert (folder / "profil.md").is_file()
    with session_factory() as session:
        (output,) = session.scalars(select(Document)).all()
        assert (output.plan_id, output.source_refs_json) == (
            plan_id,
            [{"file_id": 1, "pages": [0]}],
        )
        types = _event_types(session, upload_id)
        assert types.count(EventType.OUTPUT_SAVED) == 1
        assert types.count(EventType.OUTPUT_SKIPPED) == 1
        assert session.get_one(Plan, plan_id).executed_at is not None


@pytest.mark.parametrize("action", ["rerun", "reanalyze"])
def test_an_item_that_cannot_be_executed_is_409_and_commits_nothing(
    action: str,
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    # K10: Inbox'taki kaynak yüklemeden sonra değişmişse öğe yürütülmez, belge tahmin edilmez.
    upload_id, _ = _planned_upload(client, session_factory, layout)
    provider = _recording()
    app.dependency_overrides[get_analysis_provider] = lambda: provider
    with session_factory() as session:
        before = _event_types(session, upload_id)
        stored = layout.resolve(session.get_one(Upload, upload_id).files[0].stored_path)
    stored.write_bytes(make_text_pdf_bytes(["DEGISMIS"]))

    response = client.post(f"/api/uploads/{upload_id}/{action}")

    assert response.status_code == 409
    assert "SHA-256" in response.json()["detail"]
    with session_factory() as session:
        assert _event_types(session, upload_id) == before
        assert _count_rows(session, Plan) == 1
        assert _count_rows(session, Document) == 0


def test_failed_rerun_commits_nothing(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    upload_id, plan_id = _planned_upload(client, session_factory, layout)
    app.dependency_overrides[get_plan_executor] = lambda: _Executor(fail=True)

    with pytest.raises(RuntimeError, match="uygulayıcı durdu"):
        client.post(f"/api/uploads/{upload_id}/rerun")

    with session_factory() as session:
        assert EventType.PLAN_RERUN not in _event_types(session, upload_id)
        assert session.get_one(Plan, plan_id).executed_at is None


def test_reanalysis_opens_the_next_version_and_marks_old_outputs_as_old_version(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
) -> None:
    upload_id, plan_id = _planned_upload(client, session_factory, layout)
    old_path = "Employees/Test_Ornekova_E0001/Hazir/Test_Ornekova-Passport.pdf"
    with session_factory() as session:
        old = Document(
            employee_id="E0001",
            type_slug="russian_passport",
            path=old_path,
            format="pdf",
            plan_id=plan_id,
            source_refs_json=[{"item_id": "i1", "file_id": 1, "pages": [0]}],
        )
        session.add(old)
        session.commit()
        old_id = old.id
    executor, provider = _Executor(), _recording()
    app.dependency_overrides[get_plan_executor] = lambda: executor
    app.dependency_overrides[get_analysis_provider] = lambda: provider

    response = client.post(f"/api/uploads/{upload_id}/reanalyze")

    assert response.status_code == 200
    assert len(provider.requests) == 1
    with session_factory() as session:
        first = session.get_one(Plan, plan_id)
        second = session.scalars(select(Plan).where(Plan.version == 2)).one()
        assert response.json() == {
            "upload_id": upload_id,
            "plan_id": second.id,
            "version": 2,
            "plan_hash": second.plan_hash,
            "previous_plan_id": plan_id,
            "previous_version": 1,
            "superseded_document_ids": [old_id],
        }
        assert executor.calls == [(second.id, second.plan_hash)]
        assert (first.executed_at, second.executed_at is not None) == (None, True)
        stored = session.get_one(Document, old_id)
        assert (stored.status, stored.path) == (DocumentStatus.SUPERSEDED, old_path)
        types = _event_types(session, upload_id)
        assert types[-2:] == [EventType.PLAN_CREATED, EventType.PLAN_REANALYZED]
        assert types.count(EventType.PAGE_ANALYZED) == 2


def test_analysis_provider_dependency_builds_the_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _recording()
    monkeypatch.setitem(PROVIDER_FACTORIES, "kayitli", lambda settings: provider)

    def settings(**changes: Any) -> Settings:
        return Settings(_env_file=None, database_url="sqlite://", **changes)

    assert get_analysis_provider(settings(ai_provider="kayitli")) is provider
    for changes, message in (
        ({"ai_provider": "yok"}, "Bilinmeyen AI_PROVIDER 'yok'"),
        ({"ai_provider": "anthropic"}, "ANTHROPIC_API_KEY tanımlı olmalı"),
    ):
        with pytest.raises(HTTPException) as raised:
            get_analysis_provider(settings(**changes))
        assert raised.value.status_code == 503
        assert message in str(raised.value.detail)
