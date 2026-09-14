"""01.1.1 — `u_yyyymmdd_0001` biçiminde artan, güne göre sıfırlanan upload_id üretici."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Upload, allocate_upload_id, format_upload_id
from app.db.session import create_db_engine, create_session_factory

CONCURRENT_CALLS = 50
DAY = date(2026, 9, 5)


def _upload(upload_id: str) -> Upload:
    return Upload(id=upload_id, channel="web")


@pytest.mark.parametrize(
    ("day", "sequence", "expected"),
    [
        (DAY, 1, "u_20260905_0001"),
        (DAY, 42, "u_20260905_0042"),
        (DAY, 9999, "u_20260905_9999"),
        (DAY, 10000, "u_20260905_10000"),
        (date(2026, 1, 1), 1, "u_20260101_0001"),
    ],
)
def test_format_upload_id(day: date, sequence: int, expected: str) -> None:
    assert format_upload_id(day, sequence) == expected


def test_format_rejects_non_positive_sequence() -> None:
    with pytest.raises(ValueError):
        format_upload_id(DAY, 0)


def test_first_upload_of_day_is_0001(session: Session) -> None:
    assert allocate_upload_id(session, today=DAY) == "u_20260905_0001"


def test_ids_increase_after_committed_uploads(session: Session) -> None:
    for _ in range(3):
        session.add(_upload(allocate_upload_id(session, today=DAY)))
        session.commit()

    assert allocate_upload_id(session, today=DAY) == "u_20260905_0004"


def test_sequence_resets_on_a_new_day(session: Session) -> None:
    session.add(_upload(allocate_upload_id(session, today=DAY)))
    session.commit()

    assert allocate_upload_id(session, today=date(2026, 9, 6)) == "u_20260906_0001"


def test_unflushed_upload_in_same_transaction_is_counted(session: Session) -> None:
    session.add(_upload(allocate_upload_id(session, today=DAY)))

    assert allocate_upload_id(session, today=DAY) == "u_20260905_0002"


def test_rolled_back_upload_id_is_not_skipped(session: Session) -> None:
    session.add(_upload(allocate_upload_id(session, today=DAY)))
    session.rollback()

    assert allocate_upload_id(session, today=DAY) == "u_20260905_0001"


def _allocate_concurrently(factory: sessionmaker[Session]) -> list[str]:
    barrier = threading.Barrier(CONCURRENT_CALLS)

    def create_one() -> str:
        barrier.wait()
        with factory() as session, session.begin():
            upload_id = allocate_upload_id(session, today=DAY)
            session.add(_upload(upload_id))
        return upload_id

    with ThreadPoolExecutor(max_workers=CONCURRENT_CALLS) as pool:
        futures = [pool.submit(create_one) for _ in range(CONCURRENT_CALLS)]
        return [future.result() for future in futures]


def _assert_no_collision(ids: list[str], engine: Engine) -> None:
    expected = [format_upload_id(DAY, n) for n in range(1, CONCURRENT_CALLS + 1)]
    assert sorted(ids, key=lambda upload_id: int(upload_id.rsplit("_", 1)[1])) == expected
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Upload)) == CONCURRENT_CALLS


def test_50_concurrent_calls_on_sqlite_do_not_collide(engine: Engine) -> None:
    ids = _allocate_concurrently(create_session_factory(engine))

    _assert_no_collision(ids, engine)


def test_50_concurrent_calls_on_postgresql_do_not_collide(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url, pool_size=CONCURRENT_CALLS, max_overflow=0)
    try:
        Base.metadata.create_all(engine)
        ids = _allocate_concurrently(create_session_factory(engine))

        _assert_no_collision(ids, engine)
    finally:
        engine.dispose()
