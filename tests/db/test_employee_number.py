"""00.3.3 — `E0001` biçiminde artan, tekil; eşzamanlı 50 çağrıda çakışma yok."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Employee, allocate_employee_number, format_employee_number
from app.db.session import create_db_engine, create_session_factory

CONCURRENT_CALLS = 50


def _employee(number: str) -> Employee:
    return Employee(
        id=number, folder_name=f"Test_Kisi_{number}", given_names="Test", surname="Kisi"
    )


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [(1, "E0001"), (42, "E0042"), (9999, "E9999"), (10000, "E10000")],
)
def test_format_employee_number(sequence: int, expected: str) -> None:
    assert format_employee_number(sequence) == expected


def test_format_rejects_non_positive_sequence() -> None:
    with pytest.raises(ValueError):
        format_employee_number(0)


def test_first_number_is_e0001(session: Session) -> None:
    assert allocate_employee_number(session) == "E0001"


def test_numbers_increase_after_committed_employees(session: Session) -> None:
    for _ in range(3):
        session.add(_employee(allocate_employee_number(session)))
        session.commit()

    assert allocate_employee_number(session) == "E0004"


def test_numbers_compare_numerically_past_e9999(session: Session) -> None:
    session.add_all([_employee("E9999"), _employee("E10000")])
    session.commit()

    assert allocate_employee_number(session) == "E10001"


def test_unflushed_employee_in_same_transaction_is_counted(session: Session) -> None:
    session.add(_employee(allocate_employee_number(session)))

    assert allocate_employee_number(session) == "E0002"


def test_rolled_back_number_is_not_skipped(session: Session) -> None:
    session.add(_employee(allocate_employee_number(session)))
    session.rollback()

    assert allocate_employee_number(session) == "E0001"


def _allocate_concurrently(factory: sessionmaker[Session]) -> list[str]:
    barrier = threading.Barrier(CONCURRENT_CALLS)

    def create_one() -> str:
        barrier.wait()
        with factory() as session, session.begin():
            number = allocate_employee_number(session)
            session.add(_employee(number))
        return number

    with ThreadPoolExecutor(max_workers=CONCURRENT_CALLS) as pool:
        futures = [pool.submit(create_one) for _ in range(CONCURRENT_CALLS)]
        return [future.result() for future in futures]


def _assert_no_collision(numbers: list[str], engine: Engine) -> None:
    expected = [format_employee_number(n) for n in range(1, CONCURRENT_CALLS + 1)]
    assert sorted(numbers, key=lambda number: int(number[1:])) == expected
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Employee)) == CONCURRENT_CALLS


def test_50_concurrent_calls_on_sqlite_do_not_collide(engine: Engine) -> None:
    numbers = _allocate_concurrently(create_session_factory(engine))

    _assert_no_collision(numbers, engine)


def test_50_concurrent_calls_on_postgresql_do_not_collide(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url, pool_size=CONCURRENT_CALLS, max_overflow=0)
    try:
        Base.metadata.create_all(engine)
        numbers = _allocate_concurrently(create_session_factory(engine))

        _assert_no_collision(numbers, engine)
    finally:
        engine.dispose()
