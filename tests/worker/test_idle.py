"""11.5.5, 11.9.3 — işçinin boş-zaman işleri çerçevesi (`app.worker.idle`, `app.worker.runner`;
PLAN.md §C85): yükleme işi önce, kuyruk boşken en çok bir birim; koşullu sahiplenme, deneme sınırı,
süresi dolan sahiplenmenin geri alınması; sağlayıcı çağrısı sırasında açık oturum yok; maliyet.

Yapay zekâ canlı çağrılmaz: boş-zaman testleri kendi sahte sağlayıcısını kurar (kayıtlı sağlayıcı
tek sıralı kayıt kullanır). Tüketen tablo yalnız bu testlerin tablosudur (bu görev tablo açmaz).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, String, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.ai import PROVIDER_FACTORIES
from app.ai.usage import TokenUsage, report_usage
from app.config import ModelPrice, Settings, load_settings
from app.db.models import Event, utcnow
from app.events import (
    USAGE_BY_MODEL_DATA_KEY,
    USAGE_DATA_KEY,
    EventType,
    record_event,
    usage_event_data,
)
from app.storage import DataLayout
from app.web.routers import metrics
from app.worker import (
    IdleClaimMixin,
    IdleContext,
    IdleJob,
    IdleTable,
    Worker,
    create_worker,
    run_idle_unit,
)
from app.worker import runner as worker_runner

SETTINGS = Settings(
    _env_file=None, database_url="sqlite://", worker_lease_seconds=60, worker_max_attempts=3
)
SECRET = "Ekaterina Ornekova 00 0000001"


class _Base(DeclarativeBase):
    pass


class Chore(IdleClaimMixin, _Base):
    """Sentetik tüketen tablo: `status` `None` iken iş bekler."""

    __tablename__ = "idle_test_chores"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(16))
    result: Mapped[str | None] = mapped_column(String(128))


CHORES = IdleTable(Chore, pending=lambda: Chore.status.is_(None), failed={"status": "failed"})


class FakeProvider:
    """Sahte sağlayıcı: çağrı anında açık veritabanı oturumu olmadığını denetler."""

    name = "sahte"
    model = "sahte-model"

    def __init__(self, engine: Engine, database: Path, *, fail: Exception | None = None) -> None:
        self._engine = engine
        self._database = database
        self._fail = fail
        self.calls: list[str] = []
        self.pool_checked_out: list[int] = []
        self.write_lock_free: list[bool] = []

    def summarize(self, source: str) -> str:
        self.calls.append(source)
        self.pool_checked_out.append(self._engine.pool.checkedout())
        self.write_lock_free.append(_write_lock_free(self._database))
        report_usage(120, 30)
        if self._fail is not None:
            raise self._fail
        return f"özet:{source}"


def _write_lock_free(database: Path) -> bool:
    """Başka bir bağlantı SQLite yazma kilidini hemen alabiliyor mu (kimse tutmuyor mu)?"""
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


@pytest.fixture
def chores(engine: Engine) -> None:
    _Base.metadata.create_all(engine)


def _add(session_factory: sessionmaker[Session], *sources: str) -> list[int]:
    with session_factory() as session:
        rows = [Chore(source=source) for source in sources]
        session.add_all(rows)
        session.commit()
        return [row.id for row in rows]


def _chore(session_factory: sessionmaker[Session], chore_id: int) -> Chore:
    with session_factory() as session:
        return session.get_one(Chore, chore_id)


def _context(
    session_factory: sessionmaker[Session], layout: DataLayout, provider: FakeProvider
) -> IdleContext:
    return IdleContext(session_factory, layout, SETTINGS, provider)  # type: ignore[arg-type]


def _write(session: Session, row: Chore, result: str, meter: object) -> None:
    row.status = "done"
    row.result = result
    record_event(
        session,
        EventType.CANDIDATE_TYPE_PROPOSED,
        message="boş-zaman testi",
        data=usage_event_data(provider="sahte", model="sahte-model", meter=meter),  # type: ignore[arg-type]
    )


class SummarizeJob:
    """Sentetik boş-zaman işi: bekleyen bir satırın kaynağını sağlayıcıya özetletir."""

    name = "ozet"

    def __init__(self) -> None:
        self.failures: list[tuple[int, bool, int]] = []

    def run_one(self, context: IdleContext) -> bool:
        def failed(session: Session, row: Chore, meter: object, final: bool) -> None:
            self.failures.append((row.id, final, meter.calls))  # type: ignore[attr-defined]

        return run_idle_unit(
            context,
            CHORES,
            name=self.name,
            read=lambda session, row: row.source,
            call=lambda provider, source: provider.summarize(source),  # type: ignore[attr-defined]
            write=_write,
            failed=failed,
        )


# --- birim: oku → oturumu kapat → sağlayıcı → koşullu yaz ------------------------------------


@pytest.mark.usefixtures("chores")
def test_a_unit_reads_calls_the_provider_without_an_open_session_and_writes(
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    database: Path,
) -> None:
    (chore_id,) = _add(session_factory, "kaynak-1")
    provider = FakeProvider(engine, database)

    assert SummarizeJob().run_one(_context(session_factory, layout, provider)) is True

    assert provider.calls == ["kaynak-1"]
    assert provider.pool_checked_out == [0]
    assert provider.write_lock_free == [True]
    row = _chore(session_factory, chore_id)
    assert (row.status, row.result) == ("done", "özet:kaynak-1")
    assert (row.idle_claimed_by, row.idle_claim_expires_at, row.idle_attempts) == (None, None, 1)


@pytest.mark.usefixtures("chores")
def test_a_unit_without_pending_rows_does_nothing(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    provider = FakeProvider(engine, database)

    assert SummarizeJob().run_one(_context(session_factory, layout, provider)) is False
    assert provider.calls == []


@pytest.mark.usefixtures("chores")
def test_a_failing_call_releases_the_row_and_fails_it_for_good_after_max_attempts(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    (chore_id,) = _add(session_factory, "kaynak-1")
    provider = FakeProvider(engine, database, fail=RuntimeError(SECRET))
    job = SummarizeJob()
    context = _context(session_factory, layout, provider)

    for attempt in (1, 2):
        with pytest.raises(RuntimeError):
            job.run_one(context)
        row = _chore(session_factory, chore_id)
        assert (row.status, row.idle_claimed_by, row.idle_attempts) == (None, None, attempt)
    with pytest.raises(RuntimeError):
        job.run_one(context)

    row = _chore(session_factory, chore_id)
    assert (row.status, row.idle_claimed_by, row.idle_attempts) == ("failed", None, 3)
    assert job.failures == [(chore_id, False, 1), (chore_id, False, 1), (chore_id, True, 1)]
    # Kalıcı başarısız satır bir daha denenmez.
    assert job.run_one(context) is False
    assert len(provider.calls) == 3


@pytest.mark.usefixtures("chores")
def test_a_failing_read_counts_as_an_attempt_and_skips_the_provider(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    (chore_id,) = _add(session_factory, "kaynak-1")
    provider = FakeProvider(engine, database)

    def broken_read(session: Session, row: Chore) -> str:
        raise ValueError(SECRET)

    with pytest.raises(ValueError):
        run_idle_unit(
            _context(session_factory, layout, provider),
            CHORES,
            name="bozuk",
            read=broken_read,
            call=lambda provider, source: source,
            write=_write,
        )

    assert provider.calls == []
    row = _chore(session_factory, chore_id)
    assert (row.status, row.idle_claimed_by, row.idle_attempts) == (None, None, 1)


@pytest.mark.usefixtures("chores")
def test_a_unit_whose_row_was_taken_over_during_the_call_writes_nothing(
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (chore_id,) = _add(session_factory, "kaynak-1")
    provider = FakeProvider(engine, database)

    def call(provider: FakeProvider, source: str) -> str:
        # Sahiplenmenin süresi dolar ve başka bir işleyici satırı alır.
        with session_factory() as session:
            session.execute(update(Chore).values(idle_claimed_by="baskasi"))
            session.commit()
        return provider.summarize(source)

    with caplog.at_level(logging.WARNING):
        worked = run_idle_unit(
            _context(session_factory, layout, provider),
            CHORES,
            name="ozet",
            read=lambda session, row: row.source,
            call=call,
            write=_write,
        )

    assert worked is True
    row = _chore(session_factory, chore_id)
    assert (row.status, row.result, row.idle_claimed_by) == (None, None, "baskasi")
    assert f"kayıt {chore_id} başka bir işleyiciye geçti" in caplog.text
    with session_factory() as session:
        assert session.scalars(select(Event)).all() == []


# --- sahiplenme ------------------------------------------------------------------------------


@pytest.mark.usefixtures("chores")
def test_two_workers_cannot_claim_the_same_row(session_factory: sessionmaker[Session]) -> None:
    first, second = _add(session_factory, "kaynak-1", "kaynak-2")

    with session_factory() as session:
        a = CHORES.claim(session, token="a", lease_seconds=60, max_attempts=3)
        b = CHORES.claim(session, token="b", lease_seconds=60, max_attempts=3)
        c = CHORES.claim(session, token="c", lease_seconds=60, max_attempts=3)
        session.commit()

    assert a is not None and b is not None
    assert (a.row_id, b.row_id, c) == (first, second, None)
    with session_factory() as session:
        assert CHORES.owned(session, a) is not None
        assert CHORES.owned(session, b) is not None


@pytest.mark.usefixtures("chores")
def test_the_claim_is_a_conditional_update(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Satırı seçtikten sonra başkası alırsa güncelleme koşulu bunu görür ve hiçbir şey almaz."""
    (chore_id,) = _add(session_factory, "kaynak-1")

    with session_factory() as session:
        select_rows = session.scalars

        def racing_scalars(*args: object, **kwargs: object) -> _Rows:
            rows = list(select_rows(*args, **kwargs))  # type: ignore[arg-type]
            # Seçimle güncelleme arasında başka bir işleyici satırı alır.
            session.execute(
                update(Chore).values(
                    idle_claimed_by="a",
                    idle_claim_expires_at=utcnow() + timedelta(seconds=60),
                    idle_attempts=1,
                )
            )
            return _Rows(rows)

        monkeypatch.setattr(session, "scalars", racing_scalars)
        assert CHORES.claim(session, token="b", lease_seconds=60, max_attempts=3) is None
        session.commit()

    row = _chore(session_factory, chore_id)
    assert (row.idle_claimed_by, row.idle_attempts) == ("a", 1)


class _Rows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def first(self) -> object | None:
        return self._rows[0] if self._rows else None


@pytest.mark.usefixtures("chores")
def test_an_expired_claim_is_taken_back_and_the_old_owner_loses_it(
    session_factory: sessionmaker[Session],
) -> None:
    (chore_id,) = _add(session_factory, "kaynak-1")
    with session_factory() as session:
        old = CHORES.claim(session, token="a", lease_seconds=60, max_attempts=3)
        assert CHORES.claim(session, token="b", lease_seconds=60, max_attempts=3) is None
        session.commit()
    assert old is not None

    later = utcnow() + timedelta(seconds=61)
    with session_factory() as session:
        new = CHORES.claim(session, token="b", lease_seconds=60, max_attempts=3, now=later)
        session.commit()

    assert new is not None and new.row_id == chore_id
    with session_factory() as session:
        assert CHORES.owned(session, old) is None
        owned = CHORES.owned(session, new)
        assert owned is not None and owned.idle_attempts == 2


@pytest.mark.usefixtures("chores")
def test_an_expired_claim_out_of_attempts_is_failed_and_never_retried(
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (chore_id,) = _add(session_factory, "kaynak-1")
    with session_factory() as session:
        session.execute(
            update(Chore).values(
                idle_claimed_by="olen",
                idle_claim_expires_at=utcnow() - timedelta(seconds=1),
                idle_attempts=3,
            )
        )
        session.commit()
    provider = FakeProvider(engine, database)

    with caplog.at_level(logging.ERROR):
        assert SummarizeJob().run_one(_context(session_factory, layout, provider)) is False

    assert provider.calls == []
    row = _chore(session_factory, chore_id)
    assert (row.status, row.idle_claimed_by, row.idle_claim_expires_at) == ("failed", None, None)
    assert f"kayıt {chore_id} bırakıldı" in caplog.text


@pytest.mark.usefixtures("chores")
def test_a_live_claim_out_of_attempts_is_left_to_its_owner(
    session_factory: sessionmaker[Session],
) -> None:
    (chore_id,) = _add(session_factory, "kaynak-1")
    with session_factory() as session:
        session.execute(
            update(Chore).values(
                idle_claimed_by="calisan",
                idle_claim_expires_at=utcnow() + timedelta(seconds=60),
                idle_attempts=3,
            )
        )
        session.commit()

    with session_factory() as session:
        assert CHORES.abandon_exhausted(session, max_attempts=3) == []
        session.commit()

    row = _chore(session_factory, chore_id)
    assert (row.status, row.idle_claimed_by) == (None, "calisan")


# --- işleyici döngüsü ------------------------------------------------------------------------


class RecordingJob:
    """Her çağrıyı kaydeden sahte iş; `results` sırayla döner (bitince `False`)."""

    def __init__(self, name: str, log: list[str], results: list[bool | Exception]) -> None:
        self.name = name
        self._log = log
        self._results = results

    def run_one(self, context: IdleContext) -> bool:
        self._log.append(self.name)
        result = self._results.pop(0) if self._results else False
        if isinstance(result, Exception):
            raise result
        return result


def _worker(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    jobs: list[IdleJob],
    *,
    provider: object = object(),
) -> Worker:
    return Worker(
        session_factory,
        layout,
        settings=SETTINGS.model_copy(update={"worker_poll_seconds": 0.01}),
        provider=provider,  # type: ignore[arg-type]
        idle_jobs=jobs,
    )


def test_a_worker_built_directly_has_no_idle_jobs(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    worker = Worker(session_factory, layout, settings=SETTINGS, provider=None)  # type: ignore[arg-type]

    assert worker.idle_jobs == ()
    assert worker.run_idle_once() is False


def test_idle_jobs_satisfy_the_protocol() -> None:
    assert isinstance(SummarizeJob(), IdleJob)
    assert isinstance(RecordingJob("x", [], []), IdleJob)


def test_upload_work_always_comes_first_and_at_most_one_idle_unit_runs_per_turn(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []
    scans = iter([True, True, False, False, False, True, False])
    done = threading.Event()

    def run_once(self: Worker) -> bool:
        try:
            worked = next(scans)
        except StopIteration:
            done.set()
            self.request_stop()
            return False
        log.append(f"scan:{worked}")
        return worked

    monkeypatch.setattr(Worker, "run_once", run_once)
    first = RecordingJob("a", log, [True, True, True, True])
    second = RecordingJob("b", log, [True, True, True, True])
    worker = _worker(session_factory, layout, [first, second])
    monkeypatch.setattr(worker, "_watch_alerts", lambda: None)

    worker.start()
    try:
        assert done.wait(10)
    finally:
        worker.stop()

    assert log == [
        "scan:True",
        "scan:True",
        "scan:False",
        "a",
        "scan:False",
        "b",
        "scan:False",
        "a",
        "scan:True",
        "scan:False",
        "b",
    ]


def test_an_idle_job_without_work_passes_the_turn_to_the_next_job(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    log: list[str] = []
    worker = _worker(
        session_factory,
        layout,
        [RecordingJob("a", log, [False, False]), RecordingJob("b", log, [True, False])],
    )

    assert worker.run_idle_once() is True
    assert worker.run_idle_once() is False  # a boş, b boş: tur boşa biter
    assert log == ["a", "b", "a", "b"]


def test_a_failing_idle_unit_does_not_stop_the_loop_and_logs_only_its_type(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    log: list[str] = []
    second_round = threading.Event()

    class _Job(RecordingJob):
        def run_one(self, context: IdleContext) -> bool:
            if len(log) >= 1:
                second_round.set()
            return super().run_one(context)

    monkeypatch.setattr(Worker, "run_once", lambda self: False)
    worker = _worker(session_factory, layout, [_Job("a", log, [RuntimeError(SECRET), False])])
    monkeypatch.setattr(worker, "_watch_alerts", lambda: None)

    with caplog.at_level(logging.ERROR):
        worker.start()
        try:
            assert second_round.wait(10)
        finally:
            worker.stop()

    assert "Boş-zaman işi a başarısız (RuntimeError)" in caplog.text
    assert "Ornekova" not in caplog.text


def test_idle_jobs_do_not_run_without_a_provider(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    log: list[str] = []
    worker = _worker(session_factory, layout, [RecordingJob("a", log, [True])], provider=None)

    assert worker.run_idle_once() is False
    assert log == []


def test_idle_jobs_do_not_run_after_a_failing_queue_scan_or_a_stop_request(
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []
    scanned = threading.Event()

    def failing_scan(self: Worker) -> bool:
        scanned.set()
        self.request_stop()
        raise RuntimeError(SECRET)

    monkeypatch.setattr(Worker, "run_once", failing_scan)
    worker = _worker(session_factory, layout, [RecordingJob("a", log, [True])])
    monkeypatch.setattr(worker, "_watch_alerts", lambda: None)

    worker.start()
    assert scanned.wait(10)
    assert worker.wait(10)
    assert log == []

    worker.request_stop()
    assert worker.run_idle_once() is False
    assert log == []


@pytest.fixture
def provider_settings(
    database_url: str, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Settings]:
    monkeypatch.setitem(PROVIDER_FACTORIES, "sahte", lambda settings: object())
    yield load_settings(
        _env_file=None, database_url=database_url, data_dir=layout.root, ai_provider="sahte"
    )


def test_create_worker_hands_the_idle_jobs_to_the_worker(
    provider_settings: Settings, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = RecordingJob("a", [], [])
    monkeypatch.setattr(worker_runner, "default_idle_jobs", lambda settings: (job,))

    default = create_worker(provider_settings, layout)
    explicit = create_worker(provider_settings, layout, idle_jobs=[])
    try:
        assert default.idle_jobs == (job,)
        assert explicit.idle_jobs == ()
    finally:
        default.stop()
        explicit.stop()


# --- maliyet ---------------------------------------------------------------------------------


def test_usage_event_data_carries_usage_only_when_a_response_came() -> None:
    from app.ai.usage import UsageMeter

    silent = UsageMeter()
    assert usage_event_data(provider="sahte", model="m", meter=silent) == {
        "provider": "sahte",
        "model": "m",
    }

    meter = UsageMeter()
    meter.add(TokenUsage(100, 20))
    meter.add(TokenUsage(50, 10))
    data = usage_event_data(
        provider="sahte",
        model="ana",
        meter=meter,
        by_model={"ucuz": TokenUsage(100, 20), "ana": TokenUsage(50, 10)},
    )
    assert data[USAGE_DATA_KEY] == {"input_tokens": 150, "output_tokens": 30}
    assert data[USAGE_BY_MODEL_DATA_KEY] == {
        "ucuz": {"input_tokens": 100, "output_tokens": 20},
        "ana": {"input_tokens": 50, "output_tokens": 10},
    }


@pytest.mark.usefixtures("chores")
def test_idle_unit_usage_enters_the_cost_view_once_its_event_type_is_listed(
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add(session_factory, "kaynak-1")
    provider = FakeProvider(engine, database)
    assert SummarizeJob().run_one(_context(session_factory, layout, provider)) is True
    prices = {"sahte-model": ModelPrice(input_per_mtok=Decimal(1), output_per_mtok=Decimal(2))}

    with session_factory() as session:
        before = metrics.build_overview(session, prices)
    monkeypatch.setattr(
        metrics,
        "USAGE_EVENT_TYPES",
        (*metrics.USAGE_EVENT_TYPES, EventType.CANDIDATE_TYPE_PROPOSED),
    )
    with session_factory() as session:
        after = metrics.build_overview(session, prices)

    assert before.total.analyses == 0
    assert after.total.analyses == 1
    assert (after.total.input_tokens, after.total.output_tokens) == ("120", "30")
    assert after.total.models == "sahte-model"
    assert after.total.cost == "0.0002 USD"
    assert after.batches == ()  # parti kalemi değildir; toplam ve ayda görünür
    assert len(after.months) == 1
