"""13.3.1 — kalıcı işçi kuyruğu: iş kaydı, alma, kira, bitirme, geri koyma ve vazgeçme
(`app.worker.queue`)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Event, JobStatus, Upload, UploadJob, UploadStatus
from app.db.session import create_db_engine, create_session_factory
from app.events import EventType
from app.pipeline.orchestrate import ProcessingWithdrawn
from app.worker import (
    Claim,
    LeaseLostError,
    abandon_exhausted,
    claim_next,
    claim_upload,
    enqueue_upload,
    finish_claim,
    new_claim_token,
    release_claim,
    renew_claim,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
LEASE = 60
MAX_ATTEMPTS = 3
FIRST = "u_20260919_001"
SECOND = "u_20260919_002"
THIRD = "u_20260919_003"
CONCURRENT_CALLS = 8


def _batch(session: Session, upload_id: str, status: UploadStatus = UploadStatus.RECEIVED) -> None:
    session.add(Upload(id=upload_id, channel="web", status=status.value))
    session.flush()
    enqueue_upload(session, upload_id, now=NOW)


def _job(session: Session, upload_id: str) -> UploadJob:
    return session.scalars(
        select(UploadJob)
        .where(UploadJob.upload_id == upload_id)
        .execution_options(populate_existing=True)
    ).one()


def _claim_next(session: Session, token: str, now: datetime) -> Claim | None:
    return claim_next(session, token=token, lease_seconds=LEASE, max_attempts=MAX_ATTEMPTS, now=now)


def _expired(seconds: int = LEASE + 1) -> datetime:
    return NOW + timedelta(seconds=seconds)


# --- kuyruğa girme --------------------------------------------------------------------------


def test_an_enqueued_job_waits_in_the_queue(session: Session) -> None:
    _batch(session, FIRST)

    job = _job(session, FIRST)
    assert (job.status, job.attempts, job.claimed_by, job.lease_expires_at) == (
        JobStatus.QUEUED,
        0,
        None,
        None,
    )
    assert (job.enqueued_at, job.claimed_at, job.finished_at) == (NOW, None, None)


def test_a_batch_has_one_job(session: Session) -> None:
    _batch(session, FIRST)

    with pytest.raises(IntegrityError):
        enqueue_upload(session, FIRST)


def test_a_job_needs_its_batch(session: Session) -> None:
    with pytest.raises(IntegrityError):
        enqueue_upload(session, "u_yok")


# --- alma ----------------------------------------------------------------------------------


def test_claiming_a_waiting_job_takes_it_under_a_lease(session: Session) -> None:
    _batch(session, FIRST)

    claim = claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)

    assert claim == Claim(FIRST, "a")
    job = _job(session, FIRST)
    assert (job.status, job.attempts, job.claimed_by) == (JobStatus.RUNNING, 1, "a")
    assert (job.claimed_at, job.lease_expires_at) == (NOW, NOW + timedelta(seconds=LEASE))


def test_a_job_is_taken_only_once(session: Session) -> None:
    _batch(session, FIRST)
    claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)

    assert claim_upload(session, FIRST, token="b", lease_seconds=LEASE, now=NOW) is None
    assert _claim_next(session, "b", NOW + timedelta(seconds=LEASE - 1)) is None
    assert _job(session, FIRST).claimed_by == "a"


def test_claiming_a_batch_without_a_waiting_job_takes_nothing(session: Session) -> None:
    session.add(Upload(id=FIRST, channel="web"))  # işi olmayan parti (göçten önce bitmiş gibi)
    session.flush()

    assert claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW) is None
    assert claim_upload(session, "u_yok", token="a", lease_seconds=LEASE, now=NOW) is None


def test_the_next_job_is_the_oldest_waiting_one(session: Session) -> None:
    for upload_id in (FIRST, SECOND, THIRD):
        _batch(session, upload_id)

    taken = [_claim_next(session, token, NOW) for token in ("a", "b", "c", "d")]

    assert taken == [Claim(FIRST, "a"), Claim(SECOND, "b"), Claim(THIRD, "c"), None]


def test_a_job_whose_lease_ran_out_is_taken_again(session: Session) -> None:
    _batch(session, FIRST)
    claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)

    later = _expired()
    claim = _claim_next(session, "b", later)

    assert claim == Claim(FIRST, "b")
    job = _job(session, FIRST)
    assert (job.status, job.attempts, job.claimed_by) == (JobStatus.RUNNING, 2, "b")
    assert (job.claimed_at, job.lease_expires_at) == (later, later + timedelta(seconds=LEASE))
    # Eski işleyici artık partiye yazamaz.
    with pytest.raises(LeaseLostError):
        renew_claim(session, Claim(FIRST, "a"), lease_seconds=LEASE, now=later)


def test_a_live_lease_is_respected_to_the_last_second(session: Session) -> None:
    _batch(session, FIRST)
    claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)

    assert _claim_next(session, "b", NOW + timedelta(seconds=LEASE)) is None


def test_a_job_that_ran_out_its_attempts_is_not_taken_again(session: Session) -> None:
    _batch(session, FIRST)
    moment = NOW
    for token in ("a", "b", "c"):
        assert _claim_next(session, token, moment) == Claim(FIRST, token)
        moment += timedelta(seconds=LEASE + 1)

    assert _claim_next(session, "d", moment) is None
    assert _job(session, FIRST).attempts == MAX_ATTEMPTS


@pytest.mark.parametrize("status", [JobStatus.FINISHED, JobStatus.ABANDONED])
def test_ended_jobs_are_never_taken(session: Session, status: JobStatus) -> None:
    _batch(session, FIRST)
    job = _job(session, FIRST)
    job.status = status.value
    job.lease_expires_at = NOW
    session.flush()

    assert _claim_next(session, "a", _expired(3600)) is None


# --- kira ----------------------------------------------------------------------------------


def test_renewing_extends_the_lease(session: Session) -> None:
    _batch(session, FIRST)
    claim = claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)
    assert claim is not None

    renew_claim(session, claim, lease_seconds=LEASE, now=NOW + timedelta(seconds=30))

    assert _job(session, FIRST).lease_expires_at == NOW + timedelta(seconds=30 + LEASE)


def test_a_lease_that_ran_out_is_still_the_owner_s_while_nobody_took_it(session: Session) -> None:
    # SQLite'ta uzun analiz boyunca kalp atışı yazamaz; kira dolsa da iş sahibinindir.
    _batch(session, FIRST)
    claim = claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)
    assert claim is not None

    renew_claim(session, claim, lease_seconds=LEASE, now=_expired(300))

    assert _job(session, FIRST).lease_expires_at == _expired(300 + LEASE)
    assert _claim_next(session, "b", _expired(301)) is None


@pytest.mark.parametrize("change", ["taken_over", "finished", "released", "abandoned"])
def test_only_the_owner_renews_or_finishes(session: Session, change: str) -> None:
    _batch(session, FIRST)
    claim = claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)
    assert claim is not None
    if change == "taken_over":
        assert _claim_next(session, "b", _expired()) is not None
    elif change == "finished":
        finish_claim(session, claim, now=NOW)
    elif change == "released":
        release_claim(session, claim)
    else:
        _job(session, FIRST).status = JobStatus.ABANDONED.value
        session.flush()

    with pytest.raises(LeaseLostError, match=FIRST):
        renew_claim(session, claim, lease_seconds=LEASE, now=NOW)
    with pytest.raises(LeaseLostError):
        finish_claim(session, claim, now=NOW)
    with pytest.raises(LeaseLostError):
        release_claim(session, claim)


def test_losing_the_lease_withdraws_the_batch_from_the_pipeline() -> None:
    assert issubclass(LeaseLostError, ProcessingWithdrawn)


def test_ownership_is_read_from_the_database_not_from_the_session(
    session_factory: sessionmaker[Session],
) -> None:
    # Commit nesneleri eskitmez: sahibin oturumunda kalan eski kopya "hâlâ benim" dememeli.
    with session_factory() as owner:
        _batch(owner, FIRST)
        claim = claim_upload(owner, FIRST, token="a", lease_seconds=LEASE, now=NOW)
        assert claim is not None
        held = _job(owner, FIRST)  # iş oturumda yüklü ve tutuluyor
        owner.commit()
        with session_factory() as other:
            assert _claim_next(other, "b", _expired()) is not None
            other.commit()

        with pytest.raises(LeaseLostError):
            renew_claim(owner, claim, lease_seconds=LEASE, now=_expired())
        assert held.claimed_by == "b"


# --- bitirme ve geri koyma ----------------------------------------------------------------


def test_finishing_ends_the_job(session: Session) -> None:
    _batch(session, FIRST)
    claim = claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)
    assert claim is not None

    finish_claim(session, claim, now=NOW + timedelta(seconds=5))

    job = _job(session, FIRST)
    assert (job.status, job.finished_at, job.lease_expires_at, job.claimed_by) == (
        JobStatus.FINISHED,
        NOW + timedelta(seconds=5),
        None,
        "a",
    )
    assert _claim_next(session, "b", _expired(3600)) is None


def test_releasing_puts_the_job_back_in_the_queue(session: Session) -> None:
    _batch(session, FIRST)
    claim = claim_upload(session, FIRST, token="a", lease_seconds=LEASE, now=NOW)
    assert claim is not None

    release_claim(session, claim)

    job = _job(session, FIRST)
    assert (job.status, job.claimed_by, job.lease_expires_at, job.attempts) == (
        JobStatus.QUEUED,
        None,
        None,
        1,
    )
    assert _claim_next(session, "b", NOW) == Claim(FIRST, "b")
    assert _job(session, FIRST).attempts == 2


# --- vazgeçme ------------------------------------------------------------------------------


def _exhaust(session: Session, upload_id: str) -> datetime:
    """İşi en çok deneme kadar alıp her seferinde kirasını doldurur; dolduğu anı döner."""
    moment = NOW
    for attempt in range(MAX_ATTEMPTS):
        assert _claim_next(session, f"t{attempt}", moment) is not None
        moment += timedelta(seconds=LEASE + 1)
    return moment


def test_a_batch_whose_worker_kept_dying_is_given_up_where_it_stopped(session: Session) -> None:
    _batch(session, FIRST, UploadStatus.ANALYZING)
    moment = _exhaust(session, FIRST)

    abandoned = abandon_exhausted(session, max_attempts=MAX_ATTEMPTS, now=moment)

    assert abandoned == [FIRST]
    job = _job(session, FIRST)
    assert (job.status, job.finished_at, job.lease_expires_at) == (
        JobStatus.ABANDONED,
        moment,
        None,
    )
    assert session.get_one(Upload, FIRST).status == UploadStatus.FAILED
    (failed,) = session.scalars(select(Event).where(Event.type == EventType.PIPELINE_FAILED))
    assert failed.upload_id == FIRST
    assert failed.data_json == {
        "stage": "analyzing",
        "error": "app.worker.queue.JobAbandonedError",
        "traceback": [],
    }
    assert failed.message is not None and f"{MAX_ATTEMPTS} kez yarıda kaldı" in failed.message
    assert _claim_next(session, "z", moment) is None


def test_live_and_retryable_jobs_are_not_given_up(session: Session) -> None:
    _batch(session, FIRST)
    _batch(session, SECOND)
    moment = _exhaust(session, FIRST)
    # İlk iş son denemesinde ve kirası sürüyor; ikincinin kirası doldu ama denemesi kaldı.
    moment -= timedelta(seconds=2)
    assert claim_upload(session, SECOND, token="x", lease_seconds=1, now=NOW) is not None

    assert abandon_exhausted(session, max_attempts=MAX_ATTEMPTS, now=moment) == []
    assert _job(session, FIRST).status == JobStatus.RUNNING
    assert _job(session, SECOND).status == JobStatus.RUNNING


@pytest.mark.parametrize("status", [UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED])
def test_giving_up_a_job_whose_batch_already_ended_only_finishes_it(
    session: Session, status: UploadStatus
) -> None:
    _batch(session, FIRST)
    moment = _exhaust(session, FIRST)
    session.get_one(Upload, FIRST).status = status.value
    session.flush()

    assert abandon_exhausted(session, max_attempts=MAX_ATTEMPTS, now=moment) == []

    assert _job(session, FIRST).status == JobStatus.FINISHED
    assert session.get_one(Upload, FIRST).status == status
    assert list(session.scalars(select(Event))) == []


# --- kimlik ve eşzamanlılık --------------------------------------------------------------


def test_claim_tokens_are_unique_and_fit_their_column() -> None:
    tokens = {new_claim_token() for _ in range(100)}

    assert len(tokens) == 100
    assert all(len(token) <= 128 for token in tokens)
    assert all(token.count(":") >= 2 for token in tokens)


def _claim_concurrently(factory: sessionmaker[Session]) -> list[Claim | None]:
    barrier = threading.Barrier(CONCURRENT_CALLS)

    def take(index: int) -> Claim | None:
        barrier.wait()
        with factory() as session, session.begin():
            return _claim_next(session, f"isci-{index}", NOW)

    with ThreadPoolExecutor(max_workers=CONCURRENT_CALLS) as pool:
        return list(pool.map(take, range(CONCURRENT_CALLS)))


def _prepare(engine: Engine, jobs: int) -> sessionmaker[Session]:
    factory = create_session_factory(engine)
    with factory() as session, session.begin():
        for index in range(jobs):
            _batch(session, f"u_20260919_{index + 1:03d}")
    return factory


def _assert_each_job_taken_once(claims: list[Claim | None], factory: sessionmaker[Session]) -> None:
    taken = [claim for claim in claims if claim is not None]
    assert len(taken) == CONCURRENT_CALLS // 2
    assert len({claim.upload_id for claim in taken}) == len(taken)
    with factory() as session:
        jobs = list(session.scalars(select(UploadJob)))
        assert all(job.attempts == 1 and job.status == JobStatus.RUNNING for job in jobs)
        assert {(job.upload_id, job.claimed_by) for job in jobs} == {
            (claim.upload_id, claim.token) for claim in taken
        }


def test_concurrent_workers_on_sqlite_take_each_job_once(engine: Engine) -> None:
    factory = _prepare(engine, CONCURRENT_CALLS // 2)

    _assert_each_job_taken_once(_claim_concurrently(factory), factory)


def test_concurrent_workers_on_postgresql_take_each_job_once(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url, pool_size=CONCURRENT_CALLS, max_overflow=0)
    try:
        Base.metadata.create_all(engine)
        factory = _prepare(engine, CONCURRENT_CALLS // 2)

        _assert_each_job_taken_once(_claim_concurrently(factory), factory)
    finally:
        engine.dispose()
