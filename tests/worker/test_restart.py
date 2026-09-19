"""13.3.1 kabul — uygulama yeniden başlayınca yarım kalan parti kaybolmaz.

Parti yükleme çekirdeğiyle (`store_upload`) açılır: dosyalar Inbox'ta, işi kuyrukta. Süreç ölümü
iki yolla taklit edilir:

- Aynı süreçte `_Crash` (`BaseException`): orkestrasyon yalnız `Exception` yakalar, ölüm anındaki
  işlem commit edilmeden oturum kapanır; veritabanında sürecin öldüğü andaki commit edilmiş durum
  kalır. Her aşama için ayrı ölüm noktası vardır.
- Gerçek bir alt süreç, analizin ortasında (yazma kilidi elindeyken, commit edilmemiş sayfa
  analiziyle) `os._exit` ile ölür.

"Yeniden başlatma" yeni bir motor, yeni bir sağlayıcı ve yeni bir işleyicidir (`Worker`); ölen
işleyicinin kirası kuyruğun saati ileri alınarak doldurulur. Yapay zekâ canlı çağrılmaz: sağlayıcı
kayıtlı yanıtlardan kurulur, belgeler sentetiktir (`tests/fixtures/gen.py`).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.recording_provider import RecordingProvider
from app.config import Settings
from app.db.models import (
    Document,
    Event,
    JobStatus,
    Page,
    Plan,
    Upload,
    UploadJob,
    UploadStatus,
    utcnow,
)
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType
from app.pipeline import orchestrate
from app.storage import DataLayout
from app.web.routers.uploads import IncomingFile, store_upload
from app.worker import Worker, claim_upload, run_claimed_upload
from app.worker import queue as worker_queue
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    SyntheticPage,
    make_document_pdf_bytes,
    passport_page,
    recorded_provider,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LEASE = 60
SETTINGS = Settings(
    _env_file=None, database_url="sqlite://", worker_lease_seconds=LEASE, worker_max_attempts=3
)
ORNEKOVA = passport_page(
    PERSON_ORNEKOVA, document_number="00 0000001", expiry_date=date(2030, 1, 1)
)
SIDOROV = passport_page(PERSON_SIDOROV, document_number="00 0000002", expiry_date=date(2031, 1, 1))
ORNEKOVA_FOLDER = "Test_Ornekova_E0001"
PASSPORT_NAME = "Test_Ornekova-Passport.pdf"
DEAD_TOKEN = "olen-surec"


class _Crash(BaseException):
    """Sürecin ölümü: orkestrasyon yakalamaz, o anki işlem commit edilmez."""


def _crash_after(function: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        function(*args, **kwargs)  # adımın işi yazılır (flush) ama commit edilmez
        raise _Crash

    return wrapper


# Her aşamanın ortası: adımın işi yapılmış, geçiş commit edilmemiş.
CRASH_POINTS = {
    UploadStatus.RENDERING: "render_upload_file",
    UploadStatus.ANALYZING: "analyze_upload",
    UploadStatus.PLANNING: "create_plan",
    UploadStatus.EXECUTING: "execute_plan",
}


class _Clock:
    """Kuyruğun saati: `pass_lease` ölen işleyicinin kirasını doldurur."""

    def __init__(self) -> None:
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return utcnow() + self.offset

    def pass_lease(self) -> None:
        self.offset += timedelta(seconds=LEASE + 1)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    queue_clock = _Clock()
    monkeypatch.setattr(worker_queue, "utcnow", queue_clock)
    return queue_clock


def _store_batch(
    session_factory: sessionmaker[Session], layout: DataLayout, *files: tuple[str, bytes]
) -> str:
    with session_factory() as session:
        return store_upload(
            session,
            layout,
            SETTINGS,
            [IncomingFile(name, content, "application/pdf") for name, content in files],
            channel="web",
        )


def _passport_batch(session_factory: sessionmaker[Session], layout: DataLayout) -> str:
    return _store_batch(
        session_factory, layout, ("pasaport.pdf", make_document_pdf_bytes([ORNEKOVA]))
    )


def _provider(directory: Path, *files: list[SyntheticPage]) -> RecordingProvider:
    return recorded_provider(directory, *files)


def _job(session: Session, upload_id: str) -> UploadJob:
    return session.scalars(select(UploadJob).where(UploadJob.upload_id == upload_id)).one()


def _count(session: Session, event_type: EventType) -> int:
    return session.scalar(select(func.count()).where(Event.type == event_type)) or 0


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir()) if directory.exists() else []


def _restart(database_url: str, layout: DataLayout, provider: RecordingProvider) -> Worker:
    """Yeniden açılan uygulamanın işleyicisi: yeni motor, yeni sağlayıcı."""
    engine = create_db_engine(database_url)
    return Worker(
        create_session_factory(engine), layout, settings=SETTINGS, provider=provider, engine=engine
    )


def _assert_passport_delivered_once(session: Session, layout: DataLayout, upload_id: str) -> None:
    """Parti kesintisiz işlenmiş gibi biter: tek plan, tek çıktı, `-2` eki yok, olaylar bir kez."""
    upload = session.get_one(Upload, upload_id)
    assert upload.status == UploadStatus.DONE
    assert [plan.version for plan in upload.plans] == [1]
    (document,) = session.scalars(select(Document)).all()
    assert (document.employee_id, document.status) == ("E0001", "active")
    employee = layout.employee_dir(ORNEKOVA_FOLDER)
    assert _names(employee / "Hazir") == [PASSPORT_NAME]
    assert _names(employee / "Alinan") == ["pasaport.pdf"]
    for event_type in (
        EventType.PAGE_RENDERED,
        EventType.PAGE_ANALYZED,
        EventType.PLAN_CREATED,
        EventType.OUTPUT_SAVED,
    ):
        assert _count(session, event_type) == 1, event_type
    assert _count(session, EventType.PIPELINE_FAILED) == 0


# --- kabul: her aşamada kesilen parti -------------------------------------------------------


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize("stage", list(CRASH_POINTS))
def test_a_batch_cut_off_mid_stage_is_resumed_where_it_stopped_after_a_restart(
    stage: UploadStatus,
    database_url: str,
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: _Clock,
) -> None:
    upload_id = _passport_batch(session_factory, layout)
    with session_factory() as session:
        claim = claim_upload(session, upload_id, token=DEAD_TOKEN, lease_seconds=LEASE)
        session.commit()
    assert claim is not None
    step = CRASH_POINTS[stage]
    with monkeypatch.context() as dying:
        dying.setattr(orchestrate, step, _crash_after(getattr(orchestrate, step)))
        with pytest.raises(_Crash):
            run_claimed_upload(
                session_factory,
                layout,
                claim,
                settings=SETTINGS,
                provider=_provider(tmp_path / "ilk", [ORNEKOVA]),
            )
    engine.dispose()  # süreç gitti

    # Ölüm anında: parti durduğu aşamada, önceki aşamaların işi kalıcı, iş ölen işleyicide.
    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == stage
        job = _job(session, upload_id)
        assert (job.status, job.claimed_by, job.attempts) == (JobStatus.RUNNING, DEAD_TOKEN, 1)
        committed_plans = [(plan.id, plan.plan_hash) for plan in session.scalars(select(Plan))]
        assert bool(committed_plans) is (stage is UploadStatus.EXECUTING)

    clock.pass_lease()
    provider = _provider(tmp_path / "yeniden", [ORNEKOVA])
    worker = _restart(database_url, layout, provider)
    try:
        assert worker.run_once() is True
    finally:
        worker.stop()

    with session_factory() as session:
        _assert_passport_delivered_once(session, layout, upload_id)
        job = _job(session, upload_id)
        assert (job.status, job.attempts, job.lease_expires_at) == (JobStatus.FINISHED, 2, None)
        assert job.claimed_by != DEAD_TOKEN
        if stage is UploadStatus.EXECUTING:
            # K9: commit edilmiş plan olduğu gibi uygulandı, yeniden üretilmedi.
            assert [(plan.id, plan.plan_hash) for plan in session.scalars(select(Plan))] == (
                committed_plans
            )
    # Analizi commit edilmiş parti yapay zekâya yeniden sorulmaz; kesilen analiz baştan yapılır.
    expected_requests = 1 if stage in {UploadStatus.RENDERING, UploadStatus.ANALYZING} else 0
    assert len(provider.requests) == expected_requests


@pytest.mark.usefixtures("catalog")
def test_a_batch_that_never_started_is_processed_after_a_restart(
    database_url: str,
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    # Parti alındı, yanıt gitti, arka plan işi başlamadan süreç durdu: iş kuyrukta bekliyor.
    upload_id = _passport_batch(session_factory, layout)
    engine.dispose()

    worker = _restart(database_url, layout, _provider(tmp_path / "kayit", [ORNEKOVA]))
    try:
        assert worker.run_once() is True
        assert worker.run_once() is False  # kuyruk boşaldı
    finally:
        worker.stop()

    with session_factory() as session:
        _assert_passport_delivered_once(session, layout, upload_id)
        assert _job(session, upload_id).attempts == 1


@pytest.mark.usefixtures("catalog")
def test_a_live_worker_s_batch_is_not_taken_by_a_restarted_one(
    database_url: str,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
) -> None:
    # Başka bir süreç (ör. Telegram botu) partiyi işliyor ve kirası sürüyor.
    upload_id = _passport_batch(session_factory, layout)
    with session_factory() as session:
        assert claim_upload(session, upload_id, token="canli", lease_seconds=LEASE) is not None
        session.commit()

    worker = _restart(database_url, layout, _provider(tmp_path / "kayit", [ORNEKOVA]))
    try:
        assert worker.run_once() is False
    finally:
        worker.stop()

    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == UploadStatus.RECEIVED
        assert _job(session, upload_id).claimed_by == "canli"


@pytest.mark.usefixtures("catalog")
def test_a_batch_survives_repeated_restarts_until_it_is_done(
    database_url: str,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: _Clock,
) -> None:
    upload_id = _passport_batch(session_factory, layout)
    for attempt, step in enumerate(("analyze_upload", "execute_plan")):
        worker = _restart(database_url, layout, _provider(tmp_path / f"olen-{attempt}", [ORNEKOVA]))
        with monkeypatch.context() as dying:
            dying.setattr(orchestrate, step, _crash_after(getattr(orchestrate, step)))
            with pytest.raises(_Crash):
                worker.run_once()
        worker.stop()
        clock.pass_lease()

    provider = _provider(tmp_path / "son", [ORNEKOVA])
    worker = _restart(database_url, layout, provider)
    try:
        assert worker.run_once() is True
    finally:
        worker.stop()

    with session_factory() as session:
        _assert_passport_delivered_once(session, layout, upload_id)
        job = _job(session, upload_id)
        assert (job.status, job.attempts) == (JobStatus.FINISHED, 3)
    assert provider.requests == []  # ikinci ölümde analiz ve plan zaten commit edilmişti


@pytest.mark.usefixtures("catalog")
def test_a_batch_that_kills_its_worker_every_time_is_given_up_as_failed(
    database_url: str,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: _Clock,
) -> None:
    upload_id = _passport_batch(session_factory, layout)
    with monkeypatch.context() as dying:
        dying.setattr(orchestrate, "analyze_upload", _crash_after(orchestrate.analyze_upload))
        for attempt in range(SETTINGS.worker_max_attempts):
            worker = _restart(
                database_url, layout, _provider(tmp_path / f"olen-{attempt}", [ORNEKOVA])
            )
            with pytest.raises(_Crash):
                worker.run_once()
            worker.stop()
            clock.pass_lease()

    worker = _restart(database_url, layout, _provider(tmp_path / "son", [ORNEKOVA]))
    try:
        assert worker.run_once() is False  # vazgeçildi; alınacak iş kalmadı
    finally:
        worker.stop()

    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        assert upload.status == UploadStatus.FAILED
        job = _job(session, upload_id)
        assert (job.status, job.attempts) == (JobStatus.ABANDONED, SETTINGS.worker_max_attempts)
        (failed,) = session.scalars(select(Event).where(Event.type == EventType.PIPELINE_FAILED))
        assert failed.data_json is not None
        assert failed.data_json["stage"] == UploadStatus.ANALYZING
        assert failed.data_json["error"] == "app.worker.queue.JobAbandonedError"
        # Dosya Inbox'ta olduğu gibi duruyor (K10); İK partiyi panelden görür.
        assert layout.resolve(upload.files[0].stored_path).read_bytes() == (
            make_document_pdf_bytes([ORNEKOVA])
        )


# --- gerçek süreç ölümü --------------------------------------------------------------------

_DYING_WORKER = textwrap.dedent(
    """
    import os
    import sys
    from pathlib import Path

    from app.ai.recording_provider import RecordingProvider
    from app.config import Settings
    from app.db.session import create_db_engine, create_session_factory
    from app.storage import DataLayout
    from app.worker import claim_and_run


    class DyingProvider(RecordingProvider):
        # Birinci dosyanın analizi yazıldı (commit edilmedi); ikinci istekte süreç ölür.
        def _request_analysis(self, request):
            if self.requests:
                os._exit(3)
            return super()._request_analysis(request)


    database_url, data_dir, recordings, upload_id = sys.argv[1:5]
    settings = Settings(_env_file=None, database_url=database_url, worker_lease_seconds=60)
    factory = create_session_factory(create_db_engine(database_url))
    claim_and_run(
        factory,
        DataLayout(Path(data_dir)),
        upload_id,
        settings=settings,
        provider=DyingProvider.from_directory(Path(recordings)),
    )
    """
)


@pytest.mark.usefixtures("catalog")
def test_a_worker_process_killed_mid_analysis_loses_nothing(
    database_url: str,
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    tmp_path: Path,
    clock: _Clock,
) -> None:
    upload_id = _store_batch(
        session_factory,
        layout,
        ("pasaport.pdf", make_document_pdf_bytes([ORNEKOVA])),
        ("ikinci.pdf", make_document_pdf_bytes([SIDOROV])),
    )
    recordings = tmp_path / "kayit"
    _provider(recordings, [ORNEKOVA], [SIDOROV])
    engine.dispose()

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _DYING_WORKER,
            database_url,
            str(layout.root),
            str(recordings),
            upload_id,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 3, result.stderr

    # Ölen işlem geri alındı: parti `analyzing`'de, sayfalar render edilmiş ama analizsiz.
    with session_factory() as session:
        assert session.get_one(Upload, upload_id).status == UploadStatus.ANALYZING
        statuses = list(session.scalars(select(Page.analysis_status).order_by(Page.id)))
        assert statuses == ["pending", "pending"]
        assert _count(session, EventType.PAGE_ANALYZED) == 0
        job = _job(session, upload_id)
        assert (job.status, job.attempts) == (JobStatus.RUNNING, 1)

    clock.pass_lease()
    provider = RecordingProvider.from_directory(recordings)
    worker = _restart(database_url, layout, provider)
    try:
        assert worker.run_once() is True
    finally:
        worker.stop()

    with session_factory() as session:
        upload = session.get_one(Upload, upload_id)
        assert upload.status == UploadStatus.DONE
        assert [plan.version for plan in upload.plans] == [1]
        employees = sorted(document.employee_id for document in session.scalars(select(Document)))
        assert employees == ["E0001", "E0002"]
        assert _count(session, EventType.PAGE_ANALYZED) == 2
        assert _job(session, upload_id).status == JobStatus.FINISHED
    assert len(provider.requests) == 2
