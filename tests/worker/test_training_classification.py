"""11.9.3 — eğitim sınıflandırması işçinin boş-zaman işi olarak (`app.training.classification`
`TrainingClassificationJob`, `app.worker.idle`; PLAN.md §C86 "Yapay zekâ yolu"): kuyruk boşken
`ai_pending` öğe sınıflandırılır, yükleme işi önce gelir, sağlayıcı ayarsızsa öğe bekler, hata
deneme sayacını artırır ve sınırda öğe "Yerleştirilemedi"ye düşer, olay kullanımı taşır ve maliyet
görünümünde yalnız yapay zekâ adımı sayılır.

Yapay zekâ canlı çağrılmaz: sağlayıcı testin sahte sağlayıcısıdır ya da tek sıralı kayıtlı yanıttır.
Kişi ve belgeler sentetiktir (CONVENTIONS §6).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import AnalysisProvider, PageAnalysisRequest, TrainingClassificationRequest
from app.ai.recording_provider import RecordingProvider
from app.ai.usage import report_usage
from app.catalog.propose import CandidateExaminationJob
from app.config import ModelPrice, Settings
from app.db.models import (
    Event,
    JobStatus,
    TrainingItem,
    TrainingItemStatus,
    TrainingMethod,
    TrainingRun,
    TrainingRunKind,
    Upload,
    UploadJob,
    UploadStatus,
    utcnow,
)
from app.events import (
    AI_STEP_EVENT_TYPES,
    USAGE_DATA_KEY,
    EventType,
    is_ai_call_event,
)
from app.storage import DataLayout
from app.training import (
    create_run,
    load_known_types,
    place_example,
    stage_and_recognize,
    stage_file,
)
from app.training.classification import (
    ABANDONED_NOTE,
    ERROR_NOTE,
    JOB_NAME,
    TRAINING_CLASSIFICATIONS,
    TrainingClassificationJob,
)
from app.training.map_scan import TrainingMapJob
from app.web.routers import metrics
from app.web.routers.uploads import IncomingFile, store_upload
from app.worker import IdleContext, IdleJob, Worker, create_worker, default_idle_jobs
from tests.ai.payloads import training_payload
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    batch_responses,
    make_document_pdf_bytes,
    make_half_filled_image_bytes,
    passport_page,
    write_recordings,
)

SETTINGS = Settings(
    _env_file=None, database_url="sqlite://", worker_lease_seconds=60, worker_max_attempts=3
)
MODEL = "sahte-model"
LIMIT = 1024 * 1024
SECRET = "ORNEKOVA"


class Classifier(AnalysisProvider):
    """Sahte sağlayıcı: sınıflandırma yanıtı döner (ya da şemaya uymayan yanıt), kullanım bildirir
    ve çağrı anında açık veritabanı oturumu olup olmadığını ölçer."""

    name = "sahte"

    def __init__(self, engine: Engine, database: Path, response: object | None = None) -> None:
        super().__init__(model=MODEL)
        self._engine = engine
        self._database = database
        self._response = training_payload() if response is None else response
        self.requests: list[TrainingClassificationRequest] = []
        self.pool_checked_out: list[int] = []
        self.write_lock_free: list[bool] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_training_classification(self, request: TrainingClassificationRequest) -> object:
        self.requests.append(request)
        self.pool_checked_out.append(self._engine.pool.checkedout())
        self.write_lock_free.append(_write_lock_free(self._database))
        report_usage(800, 200)
        return self._response


def _write_lock_free(database: Path) -> bool:
    connection = sqlite3.connect(database, timeout=0, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("ROLLBACK")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "worker-test.db"


def _items(session_factory: sessionmaker[Session], layout: DataLayout, count: int = 1) -> list[int]:
    """Mekanik tanınmayan `count` öğe (ipucusuz görüntü dosyaları) tek çalıştırmada."""
    with session_factory() as session:
        known = load_known_types(session)
        run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        items = [
            stage_and_recognize(
                session,
                layout,
                known,
                run,
                f"belge-{index}.jpg",
                make_half_filled_image_bytes("JPEG", (200 + index, 100)),
                max_bytes=LIMIT,
                inventory=None,
            )
            for index in range(count)
        ]
        assert {item.status for item in items} == {TrainingItemStatus.AI_PENDING}
        session.commit()
        return [item.id for item in items]


def _item(session_factory: sessionmaker[Session], item_id: int) -> TrainingItem:
    with session_factory() as session:
        item = session.get_one(TrainingItem, item_id)
        session.expunge(item)
    return item


def _run_of(session_factory: sessionmaker[Session], item_id: int) -> TrainingRun:
    with session_factory() as session:
        run = session.get_one(TrainingItem, item_id).run
        session.expunge(run)
    return run


def _unplaced_events(session_factory: sessionmaker[Session]) -> list[dict[str, Any]]:
    with session_factory() as session:
        return [
            event.data_json or {}
            for event in session.scalars(
                select(Event)
                .where(Event.type == EventType.TRAINING_ITEM_UNPLACED.value)
                .order_by(Event.id)
            )
        ]


def _context(
    session_factory: sessionmaker[Session], layout: DataLayout, provider: AnalysisProvider | None
) -> IdleContext:
    return IdleContext(session_factory, layout, SETTINGS, provider)  # type: ignore[arg-type]


def _wait_until(condition: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "koşul zamanında gerçekleşmedi"
        time.sleep(0.02)


# --- birim -----------------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_an_empty_queue_lets_the_worker_classify_a_pending_item_without_an_open_session(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    (item_id,) = _items(session_factory, layout)
    provider = Classifier(engine, database)
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS,
        provider=provider,
        idle_jobs=[TrainingClassificationJob()],
    )

    assert worker.run_idle_once() is True

    item = _item(session_factory, item_id)
    assert (item.status, item.method, item.result_slug) == ("placed", "ai", "albanian_passport")
    assert item.note == (
        "AI kararı: `albanian_passport` (ülke ve tür ALB/pasaport, model sahte-model)"
    )
    assert (item.idle_claimed_by, item.idle_claim_expires_at, item.idle_attempts) == (
        None,
        None,
        1,
    )
    assert provider.pool_checked_out == [0]
    assert provider.write_lock_free == [True]
    assert _run_of(session_factory, item_id).status == "done"
    assert worker.run_idle_once() is False  # iş kalmadı


@pytest.mark.usefixtures("catalog")
def test_only_items_waiting_for_the_ai_are_taken(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    ids = _items(session_factory, layout, 4)
    with session_factory() as session:
        for item_id, status in zip(ids, ("placed", "unplaced", "conflict", "failed"), strict=True):
            session.execute(
                update(TrainingItem).where(TrainingItem.id == item_id).values(status=status)
            )
        run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        queued = stage_file(
            session,
            layout,
            run,
            "bekleyen.jpg",
            make_half_filled_image_bytes("PNG"),
            max_bytes=LIMIT,
        )
        session.commit()
        assert queued.status == TrainingItemStatus.QUEUED
    provider = Classifier(engine, database)

    assert TrainingClassificationJob().run_one(_context(session_factory, layout, provider)) is False
    assert provider.requests == []


@pytest.mark.usefixtures("catalog")
def test_items_are_classified_one_per_unit_in_order(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    first, second = _items(session_factory, layout, 2)
    provider = Classifier(engine, database)
    job = TrainingClassificationJob()
    context = _context(session_factory, layout, provider)

    assert job.run_one(context) is True
    assert (_item(session_factory, first).status, _item(session_factory, second).status) == (
        "placed",
        "ai_pending",
    )
    assert _run_of(session_factory, first).status == "running"
    assert job.run_one(context) is True
    assert _item(session_factory, second).status == "placed"
    assert _run_of(session_factory, first).counts_json == {"placed": 2}
    assert job.run_one(context) is False
    assert len(provider.requests) == 2


@pytest.mark.usefixtures("catalog")
def test_a_failing_classification_counts_attempts_and_waits_unplaced_at_the_limit(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    (item_id,) = _items(session_factory, layout)
    provider = Classifier(engine, database, {"surname": SECRET})
    job = TrainingClassificationJob()
    context = _context(session_factory, layout, provider)

    for attempt in (1, 2):
        with pytest.raises(Exception, match="Eğitim sınıflandırması yanıtı reddedildi"):
            job.run_one(context)
        item = _item(session_factory, item_id)
        assert (item.status, item.idle_attempts, item.idle_claimed_by) == (
            "ai_pending",
            attempt,
            None,
        )
    with pytest.raises(Exception, match="reddedildi"):
        job.run_one(context)

    item = _item(session_factory, item_id)
    assert (item.status, item.method, item.idle_attempts) == ("unplaced", "ai", 3)
    assert item.note == ERROR_NOTE.format(error="TrainingClassificationError")
    assert _run_of(session_factory, item_id).status == "done"
    events = _unplaced_events(session_factory)
    assert [event["status"] for event in events] == ["ai_pending", "ai_pending", "unplaced"]
    for event in events:
        assert event["error"] == "TrainingClassificationError"
        assert event[USAGE_DATA_KEY] == {"input_tokens": 800, "output_tokens": 200}
        assert SECRET not in str(event)
    assert job.run_one(context) is False
    assert len(provider.requests) == 3


@pytest.mark.usefixtures("catalog")
def test_the_worker_logs_only_the_error_type_of_a_failing_classification(
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _items(session_factory, layout)
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS,
        provider=Classifier(engine, database, {"surname": SECRET}),
        idle_jobs=[TrainingClassificationJob()],
    )

    assert worker.run_idle_once() is False

    assert f"Boş-zaman işi {JOB_NAME} başarısız (TrainingClassificationError)" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.usefixtures("catalog")
def test_an_abandoned_item_out_of_attempts_waits_unplaced_and_its_run_is_recounted(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    (item_id,) = _items(session_factory, layout)
    with session_factory() as session:
        session.execute(
            update(TrainingItem)
            .where(TrainingItem.id == item_id)
            .values(
                idle_claimed_by="olen-isleyici",
                idle_claim_expires_at=utcnow() - timedelta(seconds=1),
                idle_attempts=SETTINGS.worker_max_attempts,
            )
        )
        session.commit()
    provider = Classifier(engine, database)

    assert TrainingClassificationJob().run_one(_context(session_factory, layout, provider)) is False

    item = _item(session_factory, item_id)
    assert (item.status, item.method, item.note, item.idle_claimed_by) == (
        "unplaced",
        "ai",
        ABANDONED_NOTE,
        None,
    )
    assert provider.requests == []
    run = _run_of(session_factory, item_id)
    assert (run.status, run.counts_json) == ("done", {"unplaced": 1})
    (event,) = _unplaced_events(session_factory)
    assert event["status"] == "unplaced"
    assert "provider" not in event  # ölçülmemiş: maliyet görünümünde sayılmaz
    with session_factory() as session:
        assert metrics.build_overview(session, {}).total.analyses == 0


@pytest.mark.usefixtures("catalog")
def test_without_a_provider_the_items_wait(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    (item_id,) = _items(session_factory, layout)
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS,
        provider=None,
        idle_jobs=[TrainingClassificationJob()],
    )

    assert worker.run_idle_once() is False
    assert _item(session_factory, item_id).status == "ai_pending"
    assert _item(session_factory, item_id).idle_attempts == 0


@pytest.mark.usefixtures("catalog")
def test_upload_work_comes_before_the_classification(
    session_factory: sessionmaker[Session], layout: DataLayout, tmp_path: Path
) -> None:
    # Tek sıralı kayıtlı sağlayıcı: önce partinin sayfa analizi, sonra eğitim sınıflandırması.
    # Sınıflandırma önce koşsaydı sayfa analizinin kaydını alır ve ikisi de reddedilirdi.
    passport = passport_page(
        PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
    )
    (item_id,) = _items(session_factory, layout)
    with session_factory() as session:
        upload_id = store_upload(
            session,
            layout,
            SETTINGS,
            [IncomingFile("pasaport.pdf", make_document_pdf_bytes([passport]), "application/pdf")],
            channel="web",
        )
    provider = RecordingProvider.from_directory(
        write_recordings(tmp_path / "kayit", [*batch_responses([passport]), training_payload()])
    )
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS.model_copy(update={"worker_poll_seconds": 0.02}),
        provider=provider,
        idle_jobs=[TrainingClassificationJob()],
    )

    worker.start()
    try:
        _wait_until(lambda: _item(session_factory, item_id).status != "ai_pending")
    finally:
        worker.stop()

    with session_factory() as session:
        job = session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()
        assert job.status == JobStatus.FINISHED
        assert session.get_one(Upload, upload_id).status == UploadStatus.DONE
    assert _item(session_factory, item_id).status == "placed"
    assert (len(provider.requests), len(provider.training_requests)) == (1, 1)


def test_the_idle_job_is_left_idle_while_the_thread_runs_uploads(
    session_factory: sessionmaker[Session], layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Döngü: tarama iş bulduğu sürece boş-zaman işi koşmaz (§C85 çerçevesi, eğitim işiyle).
    calls: list[str] = []
    scans = iter([True, True, False])
    done = threading.Event()

    def run_once(self: Worker) -> bool:
        try:
            worked = next(scans)
        except StopIteration:
            done.set()
            self.request_stop()
            return False
        calls.append(f"tarama:{worked}")
        return worked

    class _Job(TrainingClassificationJob):
        def run_one(self, context: IdleContext) -> bool:
            calls.append("egitim")
            return False

    monkeypatch.setattr(Worker, "run_once", run_once)
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS.model_copy(update={"worker_poll_seconds": 0.01}),
        provider=object(),  # type: ignore[arg-type]
        idle_jobs=[_Job()],
    )
    monkeypatch.setattr(worker, "_watch_alerts", lambda: None)

    worker.start()
    try:
        assert done.wait(10)
    finally:
        worker.stop()

    assert calls[:4] == ["tarama:True", "tarama:True", "tarama:False", "egitim"]


# --- maliyet ---------------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_only_the_ai_step_enters_the_cost_view(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    (item_id,) = _items(session_factory, layout)
    assert (
        TrainingClassificationJob().run_one(
            _context(session_factory, layout, Classifier(engine, database))
        )
        is True
    )
    with session_factory() as session:
        # Mekanik ve İK yerleştirmesi aynı olay türünü yazar ama yapay zekâ çağrısı değildir.
        known = load_known_types(session)
        run = create_run(session, kind=TrainingRunKind.UPLOAD, created_by="ik")
        other = stage_file(
            session, layout, run, "elle.png", make_half_filled_image_bytes("PNG"), max_bytes=LIMIT
        )
        place_example(
            session, layout, known, other, "work_permit", method=TrainingMethod.MANUAL, actor="ik"
        )
        session.commit()
    prices = {MODEL: ModelPrice(input_per_mtok=Decimal(1), output_per_mtok=Decimal(2))}

    with session_factory() as session:
        placed = session.scalars(
            select(Event).where(Event.type == EventType.TRAINING_EXAMPLE_PLACED.value)
        ).all()
        overview = metrics.build_overview(session, prices)

    assert len(placed) == 2
    assert EventType.TRAINING_EXAMPLE_PLACED in metrics.USAGE_EVENT_TYPES
    assert EventType.TRAINING_ITEM_UNPLACED in metrics.USAGE_EVENT_TYPES
    assert overview.total.analyses == 1
    assert overview.total.unmetered == 0
    assert (overview.total.input_tokens, overview.total.output_tokens) == ("800", "200")
    assert overview.total.cost == "0.0012 USD"
    assert overview.batches == ()  # parti kalemi değildir
    assert len(overview.months) == 1
    assert _item(session_factory, item_id).status == "placed"


def test_ai_step_event_types_count_only_with_a_provider() -> None:
    assert set(AI_STEP_EVENT_TYPES) == {
        EventType.TRAINING_EXAMPLE_PLACED,
        EventType.TRAINING_ITEM_UNPLACED,
    }
    for event_type in AI_STEP_EVENT_TYPES:
        assert is_ai_call_event(event_type.value, {"provider": "sahte", "model": MODEL})
        assert not is_ai_call_event(event_type.value, {"method": "mechanical"})
        assert not is_ai_call_event(event_type.value, None)
    # Öteki türler ölçülmemiş olsa da çağrıdır ("ölçülmemiş" sütunu).
    assert is_ai_call_event(EventType.PAGE_ANALYZED.value, {})
    assert is_ai_call_event(EventType.CANDIDATE_TYPE_EXAMINED.value, None)


# --- kayıt -----------------------------------------------------------------------------------


def test_the_training_classification_is_a_default_idle_job(
    layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Üçüncü iş toplu taramanın mekanik adımıdır (11.9.5, `tests/worker/test_map_scan.py`).
    jobs = default_idle_jobs(SETTINGS)

    assert [type(job) for job in jobs] == [
        CandidateExaminationJob,
        TrainingClassificationJob,
        TrainingMapJob,
    ]
    job = jobs[1]
    assert isinstance(job, IdleJob)
    assert job.name == JOB_NAME
    assert TRAINING_CLASSIFICATIONS.failed == {"status": "unplaced"}
    assert TRAINING_CLASSIFICATIONS.abandoned is not None
    monkeypatch.setattr("app.worker.runner.create_provider", lambda settings: object())
    worker = create_worker(SETTINGS, layout)
    try:
        assert [type(each) for each in worker.idle_jobs] == [
            CandidateExaminationJob,
            TrainingClassificationJob,
            TrainingMapJob,
        ]
    finally:
        worker.stop()
