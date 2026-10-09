"""09.2.1, 09.2.2, 09.2.3 — parti durum makinesi, uçtan uca orkestrasyon ve hata dayanıklılığı.

Partiler yükleme uç noktasının yazdığı gibi kurulur (Inbox + `upload_files`, tekrar SHA-256 ile
işaretli, commit edilmiş `received` parti); sayfalar gerçek render adımlarından, kayıtlı yanıtla
analizden (sağlayıcı canlı çağrılmaz), gerçek planlayıcı ve uygulayıcıdan geçer. Belgeler
`tests/fixtures/gen.py`'nin sentetik belgeleridir.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from app.ai.provider import AnalysisProvider, PageAnalysisRequest
from app.ai.recording_provider import RecordingProvider
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    Document,
    DocumentStatus,
    Employee,
    Event,
    Page,
    Plan,
    QueueItem,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.events import EventType
from app.pipeline import orchestrate
from app.pipeline.orchestrate import (
    UPLOAD_TRANSITIONS,
    ProcessedUpload,
    UploadTransitionError,
    check_transition,
    current_plan,
    plan_executor,
    process_upload,
    reanalyze_upload,
    rerun_plan,
)
from app.pipeline.plan import Operation, Route, read_plan
from app.storage import DataLayout, find_original_by_sha256, sha256_bytes, write_to_inbox
from tests.fixtures.gen import (
    A4,
    make_docx_bytes,
    make_half_filled_image_bytes,
    make_sized_pdf_bytes,
    make_text_pdf_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
SETTINGS = Settings(_env_file=None, database_url="sqlite://")
FOLDER = "Test_Ornekova_E0001"
PASSPORT_NAME = "Test_Ornekova-Passport.pdf"
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "Орнекова", "0000001", "1990-01-01")
CHAIN = [
    UploadStatus.RENDERING,
    UploadStatus.ANALYZING,
    UploadStatus.PLANNING,
    UploadStatus.EXECUTING,
]


class _NoAnalysis(AnalysisProvider):
    """Sayfa analizi beklenmeyen partiler için: her istek testi düşürür."""

    name = "hicbiri"

    def __init__(self) -> None:
        super().__init__(model="hicbiri")

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("bu partide yapay zekâ çağrılmamalı")


class _Unexpected(RuntimeError):
    """Dış kütüphane hatası yerine: metni kişisel değer taşıyabilir, loga yazılmamalı."""


def _recording(directory: str = "russian_passport") -> RecordingProvider:
    return RecordingProvider.from_directory(RECORDINGS / directory)


def _received_upload(
    session: Session,
    layout: DataLayout,
    *files: tuple[str, bytes],
    upload_id: str = "u_20260918_0001",
    context_employee_id: str | None = None,
) -> Upload:
    """Yükleme uç noktasının bıraktığı parti: Inbox'ta dosyalar, `received`, commit edilmiş."""
    upload = Upload(id=upload_id, channel="web", context_employee_id=context_employee_id)
    session.add(upload)
    session.flush()
    for name, content in files:
        stored = write_to_inbox(layout, upload_id, name, content)
        original = find_original_by_sha256(session, stored.sha256)
        session.add(
            UploadFile(
                upload=upload,
                original_name=name,
                stored_path=layout.relative(stored.path),
                sha256=stored.sha256,
                mime="application/octet-stream",
                is_duplicate_of=None if original is None else original.id,
            )
        )
        session.flush()
    session.commit()
    return upload


@pytest.fixture
def catalog(session: Session) -> None:
    import_catalog(session, CATALOG)
    session.commit()


@pytest.fixture
def committed(session: Session, engine: Engine) -> Iterator[list[str]]:
    """Veritabanına commit edilen her işlemde partinin durumu — geçişlerin dışarıdan görünen sırası.

    Motorun `commit` olayı yalnız gerçek COMMIT'te gelir (SAVEPOINT bırakmada gelmez).
    """
    seen: list[str] = []

    def _on_commit(_connection: object) -> None:
        for instance in session.identity_map.values():
            if isinstance(instance, Upload):
                seen.append(instance.status)

    event.listen(engine, "commit", _on_commit)
    yield seen
    event.remove(engine, "commit", _on_commit)


def _events(session: Session, event_type: EventType | None = None) -> list[Event]:
    query = select(Event).order_by(Event.id)
    if event_type is not None:
        query = query.where(Event.type == event_type)
    return list(session.scalars(query))


def _count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir()) if directory.exists() else []


def _assert_no_personal_values(events: list[Event]) -> None:
    logged = json.dumps([[row.data_json, row.message] for row in events], ensure_ascii=False)
    for value in PERSONAL_VALUES:
        assert value not in logged


def _passport_pdf() -> bytes:
    # Birinci sayfa pasaport (kayıtlı yanıt), ikinci sayfa boş (02.4.1: analize gitmez).
    return make_text_pdf_bytes(["PASAPORT", None])


# --- 09.2.1 durum makinesi ---------------------------------------------------------------------


def test_the_state_machine_is_the_prd_chain_and_any_unfinished_state_may_fail() -> None:
    # 10.3.6, 10.3.7 (tm 168): bitmemiş her durum iptal de edilebilir; `cancelled` son durumdur.
    stop = {UploadStatus.FAILED, UploadStatus.CANCELLED}
    assert dict(UPLOAD_TRANSITIONS) == {
        UploadStatus.RECEIVED: {UploadStatus.RENDERING, *stop},
        UploadStatus.RENDERING: {UploadStatus.ANALYZING, *stop},
        UploadStatus.ANALYZING: {UploadStatus.PLANNING, *stop},
        UploadStatus.PLANNING: {UploadStatus.EXECUTING, *stop},
        UploadStatus.EXECUTING: {UploadStatus.DONE, UploadStatus.PARTIAL, *stop},
        UploadStatus.DONE: set(),
        UploadStatus.PARTIAL: set(),
        UploadStatus.FAILED: set(),
        UploadStatus.CANCELLED: set(),
    }
    assert set(UPLOAD_TRANSITIONS) == set(UploadStatus)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (UploadStatus.RECEIVED, UploadStatus.ANALYZING),  # adım atlanmaz
        (UploadStatus.PLANNING, UploadStatus.RENDERING),  # geri dönülmez
        (UploadStatus.ANALYZING, UploadStatus.PARTIAL),  # sonuç yürütmeden sonra yazılır
        (UploadStatus.DONE, UploadStatus.FAILED),  # son durumdan çıkış yok
        (UploadStatus.FAILED, UploadStatus.RENDERING),
        (UploadStatus.PARTIAL, UploadStatus.DONE),
    ],
)
def test_transitions_outside_the_chain_are_refused(
    current: UploadStatus, target: UploadStatus
) -> None:
    with pytest.raises(UploadTransitionError, match=f"'{current}' durumundan '{target}'"):
        check_transition(current, target)


def test_transitions_on_the_chain_are_allowed() -> None:
    for current, target in zip(
        [UploadStatus.RECEIVED, *CHAIN], [*CHAIN, UploadStatus.DONE], strict=True
    ):
        check_transition(current, target)
        check_transition(current, UploadStatus.FAILED)
    check_transition(UploadStatus.EXECUTING, UploadStatus.PARTIAL)


# --- 09.2.2 uçtan uca orkestrasyon ------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_one_call_takes_the_upload_from_received_to_done(
    session: Session, layout: DataLayout, committed: list[str]
) -> None:
    passport = _passport_pdf()
    upload = _received_upload(
        session, layout, ("pasaport.pdf", passport), ("cv.docx", make_docx_bytes())
    )
    committed.clear()
    provider = _recording()

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=provider)

    # Durum makinesi: her geçiş sırayla commit edildi, son durum `done`.
    plan = current_plan(session, upload)
    assert plan is not None
    assert result == ProcessedUpload(UploadStatus.DONE, plan)
    assert committed == [*CHAIN, UploadStatus.DONE]
    assert upload.status == UploadStatus.DONE
    # Yalnız pasaport sayfası analize gitti; boş sayfa ve Word dosyası gitmedi.
    assert len(provider.requests) == 1
    assert (plan.version, plan.model, plan.executed_at is not None) == (1, provider.model, True)

    # Plan: pasaport çıktısı, boş sayfa atlanır, bağlamsız Word dosyası Unresolved'a gider.
    items = read_plan(plan).items
    assert [(item.item_id, item.route, item.operation) for item in items] == [
        ("i1", Route.READY, Operation.EXTRACT),
        ("i2", Route.SKIP, None),
        ("i3", Route.UNRESOLVED, None),
    ]
    (output,) = session.scalars(select(Document)).all()
    assert (output.employee_id, output.plan_id, output.status) == ("E0001", plan.id, "active")
    assert output.source_refs_json == [{"file_id": 1, "pages": [0]}]
    employee = layout.employee_dir(FOLDER)
    assert _names(employee / "Hazir") == [PASSPORT_NAME]
    assert _names(employee / "Alinan") == ["pasaport.pdf"]
    assert (employee / "profil.md").read_text(encoding="utf-8").count(PASSPORT_NAME) == 1
    (queued,) = session.scalars(select(QueueItem)).all()
    assert (queued.kind, queued.plan_id, queued.plan_item_id) == ("unresolved", plan.id, "i3")
    assert _names(layout.queue_dir("unresolved", upload.id)) == ["cv.docx", "reason.json"]

    # Olay zinciri adım sırasıyla; atlanan öğenin izi belgesiz OUTPUT_SKIPPED.
    events = _events(session)
    first = {
        kind: min(row.id for row in events if row.type == kind)
        for kind in {row.type for row in events}
    }
    assert (
        first[EventType.PAGE_RENDERED]
        < first[EventType.PAGE_BLANK]
        < first[EventType.PAGE_ANALYZED]
        < first[EventType.PLAN_CREATED]
        < first[EventType.PAGE_EXTRACTED]
        < first[EventType.OUTPUT_SAVED]
        < first[EventType.OUTPUT_SKIPPED]
        < first[EventType.QUEUED_UNRESOLVED]
    )
    assert all(row.upload_id == upload.id for row in events)
    (skipped,) = _events(session, EventType.OUTPUT_SKIPPED)
    assert (skipped.file_id, skipped.page_index, skipped.document_id) == (1, 1, None)
    assert skipped.message is not None and skipped.message.startswith(
        "Boş sayfa (dosya 1, sayfa 2)"
    )
    assert skipped.data_json == {
        "item_id": "i2",
        "plan_id": plan.id,
        "route": "skip",
        "sources": [{"file_id": 1, "pages": [1]}],
    }
    assert _events(session, EventType.PIPELINE_FAILED) == []
    _assert_no_personal_values(events)
    # K10: Inbox'taki orijinal değişmedi.
    assert layout.resolve(upload.files[0].stored_path).read_bytes() == passport


@pytest.mark.usefixtures("catalog")
def test_the_status_of_each_stage_is_visible_from_outside_while_it_runs(
    session: Session, layout: DataLayout, engine: Engine
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    database = engine.url.database
    assert database is not None
    seen: list[str] = []

    class _Observing(RecordingProvider):
        def _request_analysis(self, request: PageAnalysisRequest) -> object:
            # Ayrı bağlantı yalnız commit edilmiş durumu görür (GET /api/uploads/{id} gibi).
            with sqlite3.connect(database) as reader:
                (status,) = reader.execute("SELECT status FROM uploads").fetchone()
            seen.append(status)
            return super()._request_analysis(request)

    provider = _Observing.from_directory(RECORDINGS / "russian_passport")

    process_upload(session, layout, upload, settings=SETTINGS, provider=provider)

    assert seen == [UploadStatus.ANALYZING]
    with sqlite3.connect(database) as reader:
        assert reader.execute("SELECT status FROM uploads").fetchone() == ("done",)


@pytest.mark.usefixtures("catalog")
def test_a_failed_page_analysis_ends_the_upload_as_partial(
    session: Session, layout: DataLayout, committed: list[str], tmp_path: Path
) -> None:
    # 03.7.2: analizi yapılamayan sayfa partiyi durdurmaz; plan onu Unresolved'a gönderir ve parti
    # yürütmeden sonra `partial` olur (analizin erken yazdığı `partial` commit edilmez).
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    broken = tmp_path / "bozuk-kayit"
    broken.mkdir()
    (broken / "0.json").write_text('{"page_index": 0}', encoding="utf-8")
    committed.clear()

    result = process_upload(
        session,
        layout,
        upload,
        settings=SETTINGS,
        provider=RecordingProvider.from_directory(broken),
    )

    assert result.status == UploadStatus.PARTIAL
    assert committed == [*CHAIN, UploadStatus.PARTIAL]
    assert result.plan is not None
    assert [(item.route, item.operation) for item in read_plan(result.plan).items] == [
        (Route.UNRESOLVED, None),
        (Route.SKIP, None),
    ]
    assert len(_events(session, EventType.PAGE_ANALYSIS_FAILED)) == 1
    assert _count(session, Document) == 0
    assert _names(layout.queue_dir("unresolved", upload.id)) == ["pasaport.pdf", "reason.json"]


@pytest.mark.usefixtures("catalog")
def test_front_and_back_images_are_rendered_and_merged_s5(
    session: Session, layout: DataLayout
) -> None:
    upload = _received_upload(
        session,
        layout,
        ("on.jpg", make_half_filled_image_bytes("JPEG")),
        ("arka.jpg", make_half_filled_image_bytes("JPEG", (100, 200))),
    )

    result = process_upload(
        session, layout, upload, settings=SETTINGS, provider=_recording("s5_front_back_images")
    )

    assert result.status == UploadStatus.DONE
    assert [file.page_count for file in upload.files] == [1, 1]
    assert result.plan is not None
    (item,) = read_plan(result.plan).items
    assert (item.route, item.operation) == (Route.READY, Operation.MERGE)
    (output,) = session.scalars(select(Document)).all()
    assert output.source_refs_json == [
        {"file_id": 1, "pages": [0]},
        {"file_id": 2, "pages": [0]},
    ]
    assert len(_events(session, EventType.PAGES_MERGED)) == 1
    assert layout.resolve(output.path).name == "Ivan_Sidorov-Driving-License.pdf"


@pytest.mark.usefixtures("catalog")
def test_a_duplicate_upload_is_skipped_without_analysis_s2(
    session: Session, layout: DataLayout
) -> None:
    passport = make_text_pdf_bytes(["PASAPORT"])
    first = _received_upload(session, layout, ("pasaport.pdf", passport))
    process_upload(session, layout, first, settings=SETTINGS, provider=_recording())
    second = _received_upload(
        session, layout, ("pasaport-yine.pdf", passport), upload_id="u_20260918_0002"
    )

    result = process_upload(session, layout, second, settings=SETTINGS, provider=_NoAnalysis())

    assert result.status == UploadStatus.DONE
    (duplicate,) = second.files
    assert (duplicate.is_duplicate_of, duplicate.page_count, duplicate.pages) == (1, None, [])
    assert result.plan is not None
    (item,) = read_plan(result.plan).items
    assert item.route is Route.SKIP
    assert _count(session, Document) == 1
    assert _names(layout.ready_dir(FOLDER)) == [PASSPORT_NAME]
    skipped = [
        row for row in _events(session, EventType.OUTPUT_SKIPPED) if row.upload_id == second.id
    ]
    assert [(row.document_id, row.data_json and row.data_json["route"]) for row in skipped] == [
        (None, "skip")
    ]
    assert skipped[0].message is not None and "Tekrar yükleme (01.4.1)" in skipped[0].message


@pytest.mark.usefixtures("catalog")
def test_files_that_cannot_be_rendered_go_to_unresolved_without_failing_the_upload(
    session: Session, layout: DataLayout, committed: list[str]
) -> None:
    upload = _received_upload(
        session,
        layout,
        ("parolali.pdf", make_sized_pdf_bytes([A4], password="gizli")),
        ("bozuk.jpg", b"\xff\xd8\xff" + b"bozuk goruntu"),
        ("bilinmeyen.txt", b"duz metin"),
    )
    committed.clear()

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=_NoAnalysis())

    assert result.status == UploadStatus.DONE
    assert committed == [*CHAIN, UploadStatus.DONE]
    assert [(file.page_count, file.pages) for file in upload.files] == [(None, [])] * 3
    assert _count(session, Page) == 0
    assert result.plan is not None
    items = read_plan(result.plan).items
    assert [item.route for item in items] == [Route.UNRESOLVED] * 3
    assert all("İşlenemeyen dosya" in (item.route_reason or "") for item in items)
    assert len(_events(session, EventType.QUEUED_UNRESOLVED)) == 3
    assert _events(session, EventType.PIPELINE_FAILED) == []


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize("status", [UploadStatus.RENDERING, UploadStatus.DONE, UploadStatus.FAILED])
def test_only_a_received_upload_is_processed(
    session: Session, layout: DataLayout, status: UploadStatus
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    upload.status = status.value
    session.commit()
    before = len(_events(session))

    with pytest.raises(UploadTransitionError, match=f"'{status}' durumundan 'rendering'"):
        process_upload(session, layout, upload, settings=SETTINGS, provider=_NoAnalysis())

    assert session.get_one(Upload, upload.id).status == status
    assert len(_events(session)) == before
    assert _count(session, Page) == 0


@pytest.mark.usefixtures("catalog")
def test_a_processed_upload_is_not_processed_again(session: Session, layout: DataLayout) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    process_upload(session, layout, upload, settings=SETTINGS, provider=_recording())
    before = (len(_events(session)), _count(session, Plan), _count(session, Document))

    with pytest.raises(UploadTransitionError):
        process_upload(session, layout, upload, settings=SETTINGS, provider=_NoAnalysis())

    assert (len(_events(session)), _count(session, Plan), _count(session, Document)) == before


# --- 09.2.3 hata dayanıklılığı -----------------------------------------------------------------


def _raising_after(function: Callable[..., Any]) -> Callable[..., Any]:
    """`function` işini yapar, sonra beklenmeyen bir hatayla durur (metni kişisel değer taşır)."""

    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        function(*args, **kwargs)
        raise _Unexpected("beklenmeyen durum: ORNEKOVA 0000001")

    return _wrapper


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize(
    ("stage", "step"),
    [
        (UploadStatus.RENDERING, "render_upload_file"),
        (UploadStatus.ANALYZING, "analyze_upload"),
        (UploadStatus.PLANNING, "create_plan"),
        (UploadStatus.EXECUTING, "execute_ready_item"),
    ],
)
def test_an_unexpected_error_fails_the_upload_keeps_the_inbox_and_is_logged(
    session: Session,
    layout: DataLayout,
    committed: list[str],
    monkeypatch: pytest.MonkeyPatch,
    stage: UploadStatus,
    step: str,
) -> None:
    passport = _passport_pdf()
    upload = _received_upload(session, layout, ("pasaport.pdf", passport))
    inbox = layout.upload_inbox_dir(upload.id)
    monkeypatch.setattr(orchestrate, step, _raising_after(getattr(orchestrate, step)))
    committed.clear()

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=_recording())

    # Parti durduğu adımdan `failed`'a geçti; önceki geçişler commit edilmiş kaldı.
    reached = CHAIN[: CHAIN.index(stage) + 1]
    assert committed == [*reached, UploadStatus.FAILED]
    plan = current_plan(session, upload)
    assert result == ProcessedUpload(UploadStatus.FAILED, plan, failed_stage=stage)
    assert session.get_one(Upload, upload.id).status == UploadStatus.FAILED
    # Dosyalar Inbox'ta olduğu gibi kaldı (K10).
    assert _names(inbox) == ["pasaport.pdf"]
    assert (inbox / "pasaport.pdf").read_bytes() == passport
    assert sha256_bytes(passport) == upload.files[0].sha256
    # Hata loglandı: durduğu adım, hata türü, değer taşımayan çağrı yığını; dış hata metni yok.
    (failed,) = _events(session, EventType.PIPELINE_FAILED)
    assert (failed.upload_id, failed.message, failed.actor) == (upload.id, None, "system")
    assert failed.data_json is not None
    assert failed.data_json["stage"] == stage.value
    assert failed.data_json["error"] == f"{__name__}._Unexpected"
    assert failed.data_json["traceback"][-1].startswith("test_process_upload.py:")
    assert any(frame.endswith(" _process_stages") for frame in failed.data_json["traceback"])
    _assert_no_personal_values(_events(session))
    # Durduğu adımın veritabanı işi geri alındı; öncekilerin işi kaldı.
    pages = list(session.scalars(select(Page).order_by(Page.index)))
    assert [page.analysis_status for page in pages] == {
        UploadStatus.RENDERING: [],
        UploadStatus.ANALYZING: ["pending", "pending"],
        UploadStatus.PLANNING: ["done", "skipped"],
        UploadStatus.EXECUTING: ["done", "skipped"],
    }[stage]
    assert (plan is not None) is (stage is UploadStatus.EXECUTING)
    assert _count(session, Employee) == (1 if stage is UploadStatus.EXECUTING else 0)
    assert _count(session, Document) == 0
    assert _events(session, EventType.OUTPUT_SAVED) == []


@pytest.mark.usefixtures("catalog")
def test_the_application_s_own_error_message_is_logged(
    session: Session, layout: DataLayout
) -> None:
    # K10: Inbox yüklemeden sonra değişmişse uygulayıcı belgeyi tahmin etmez; parti durur, hata
    # metni (kişisel değer taşımayan uygulama hatası) loglanır, dosyaya dokunulmaz.
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    changed = make_text_pdf_bytes(["PASAPORT", None, None])
    layout.resolve(upload.files[0].stored_path).write_bytes(changed)

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=_recording())

    assert (result.status, result.failed_stage) == (UploadStatus.FAILED, UploadStatus.EXECUTING)
    (failed,) = _events(session, EventType.PIPELINE_FAILED)
    assert failed.message == (
        "i1 öğesinin sources[0] kaynağı yüklemede kaydedilen SHA-256'yı taşımıyor (K10)"
    )
    assert failed.data_json is not None
    assert failed.data_json["error"] == "app.pipeline.execute.SourceIntegrityError"
    assert layout.resolve(upload.files[0].stored_path).read_bytes() == changed
    assert _count(session, Document) == 0


@pytest.mark.usefixtures("catalog")
def test_an_upload_stopped_while_executing_is_recovered_by_rerunning_its_plan(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Plan `executing`'e geçişle commit edildi; geri alınan yürütmenin diskte kalan çıktısı yeniden
    # çalıştırmada benimsenir (07.8.1), ikinci dosya (`-2`) yazılmaz.
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    real = orchestrate.execute_ready_item
    monkeypatch.setattr(orchestrate, "execute_ready_item", _raising_after(real))
    result = process_upload(session, layout, upload, settings=SETTINGS, provider=_recording())
    assert result.plan is not None
    assert _names(layout.ready_dir(FOLDER)) == [PASSPORT_NAME]
    assert _count(session, Document) == 0
    monkeypatch.setattr(orchestrate, "execute_ready_item", real)

    rerun_plan(session, layout, upload, executor=plan_executor(SETTINGS))
    session.commit()

    (output,) = session.scalars(select(Document)).all()
    assert (output.plan_id, layout.resolve(output.path).name) == (result.plan.id, PASSPORT_NAME)
    assert _names(layout.ready_dir(FOLDER)) == [PASSPORT_NAME]
    assert (layout.employee_dir(FOLDER) / "profil.md").is_file()
    # Yeniden çalıştırma parti durumuna dokunmaz (06.6.1).
    assert upload.status == UploadStatus.FAILED


# --- uygulayıcı ---------------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_reanalysis_with_the_application_executor_refreshes_the_profile_of_old_outputs(
    session: Session, layout: DataLayout
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", make_text_pdf_bytes(["PASAPORT"])))
    process_upload(session, layout, upload, settings=SETTINGS, provider=_recording())
    profile = layout.profile_path(FOLDER)
    profile.unlink()

    reanalysis = reanalyze_upload(
        session,
        layout,
        upload,
        provider=_recording(),
        catalog=CATALOG,
        executor=plan_executor(SETTINGS),
    )
    session.commit()

    outputs = list(session.scalars(select(Document).order_by(Document.id)))
    assert [(row.plan_id, row.status) for row in outputs] == [
        (reanalysis.previous_plan.id, DocumentStatus.SUPERSEDED),
        (reanalysis.plan.id, DocumentStatus.ACTIVE),
    ]
    assert _names(layout.ready_dir(FOLDER)) == ["Test_Ornekova-Passport-2.pdf", PASSPORT_NAME]
    text = profile.read_text(encoding="utf-8")
    assert "Test_Ornekova-Passport-2.pdf" in text and "superseded" in text


@pytest.mark.usefixtures("catalog")
def test_the_executor_writes_no_profile_for_an_upload_without_outputs(
    session: Session, layout: DataLayout
) -> None:
    upload = _received_upload(session, layout, ("cv.docx", make_docx_bytes()))

    result = process_upload(session, layout, upload, settings=SETTINGS, provider=_NoAnalysis())

    assert result.status == UploadStatus.DONE
    assert _count(session, Document) == 0
    assert not (layout.root / "Employees").exists() or _names(layout.root / "Employees") == []
