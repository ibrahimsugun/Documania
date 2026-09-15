"""04.6.1 — katalog dışı belgenin önerdiği tür aday tür olarak kaydedilir; aynı ad tek kayda iner,
görülmeler sayılır, aynı sayfa iki kez sayılmaz ve durum yeniden görülmede değişmez."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Base,
    CandidateDocumentType,
    CandidateTypeStatus,
    Upload,
    normalize_candidate_type_name,
    record_candidate_type_sighting,
)
from app.db.session import create_db_engine, create_session_factory

CONCURRENT_CALLS = 20
FIRST_UPLOAD = "u_20260915_0001"
SECOND_UPLOAD = "u_20260915_0002"


def _uploads(session: Session) -> None:
    session.add_all(
        [Upload(id=FIRST_UPLOAD, channel="web"), Upload(id=SECOND_UPLOAD, channel="web")]
    )
    session.flush()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Peruvian Diploma", "peruvian diploma"),
        ("  PERUVIAN\tdiploma \n", "peruvian diploma"),
        ("German  Residence   Permit", "german residence permit"),
        ("Straße Ausweis", "strasse ausweis"),
    ],
)
def test_normalized_name_ignores_case_and_whitespace(name: str, expected: str) -> None:
    assert normalize_candidate_type_name(name) == expected


@pytest.mark.parametrize("name", ["", "   ", "\n\t"])
def test_blank_candidate_type_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        normalize_candidate_type_name(name)


def test_first_sighting_creates_a_pending_candidate_type(session: Session) -> None:
    _uploads(session)

    sighting = record_candidate_type_sighting(
        session, proposed_name=" Peruvian  Diploma ", upload_id=FIRST_UPLOAD, page_id=11
    )

    assert (sighting.created, sighting.counted) == (True, True)
    session.commit()
    stored = session.scalars(select(CandidateDocumentType)).one()
    assert stored is sighting.candidate_type
    assert stored.proposed_name == "Peruvian Diploma"
    assert stored.normalized_name == "peruvian diploma"
    assert stored.first_seen_upload_id == FIRST_UPLOAD
    assert stored.sample_page_ids == [11]
    assert stored.seen_count == 1
    assert stored.status == CandidateTypeStatus.PENDING
    assert stored.description is None


def test_same_name_in_another_spelling_counts_on_the_same_record(session: Session) -> None:
    _uploads(session)
    record_candidate_type_sighting(
        session, proposed_name="Peruvian Diploma", upload_id=FIRST_UPLOAD, page_id=11
    )

    sighting = record_candidate_type_sighting(
        session, proposed_name="PERUVIAN   diploma", upload_id=SECOND_UPLOAD, page_id=42
    )

    assert (sighting.created, sighting.counted) == (False, True)
    session.commit()
    session.expire_all()
    stored = session.scalars(select(CandidateDocumentType)).one()
    assert stored.proposed_name == "Peruvian Diploma"
    assert stored.first_seen_upload_id == FIRST_UPLOAD
    assert stored.sample_page_ids == [11, 42]
    assert stored.seen_count == 2


def test_the_same_page_is_counted_only_once(session: Session) -> None:
    _uploads(session)
    record_candidate_type_sighting(
        session, proposed_name="Peruvian Diploma", upload_id=FIRST_UPLOAD, page_id=11
    )
    session.commit()

    again = record_candidate_type_sighting(
        session, proposed_name="peruvian diploma", upload_id=FIRST_UPLOAD, page_id=11
    )

    assert (again.created, again.counted) == (False, False)
    session.commit()
    session.expire_all()
    stored = session.scalars(select(CandidateDocumentType)).one()
    assert (stored.sample_page_ids, stored.seen_count) == ([11], 1)


def test_different_names_are_separate_candidate_types(session: Session) -> None:
    _uploads(session)

    diploma = record_candidate_type_sighting(
        session, proposed_name="Peruvian Diploma", upload_id=FIRST_UPLOAD, page_id=11
    )
    certificate = record_candidate_type_sighting(
        session, proposed_name="Peruvian Certificate", upload_id=FIRST_UPLOAD, page_id=11
    )

    assert diploma.created and certificate.created
    assert diploma.candidate_type.id != certificate.candidate_type.id
    names = session.scalars(
        select(CandidateDocumentType.normalized_name).order_by(CandidateDocumentType.id)
    ).all()
    assert names == ["peruvian diploma", "peruvian certificate"]


@pytest.mark.parametrize("status", [CandidateTypeStatus.REJECTED, CandidateTypeStatus.APPROVED])
def test_seeing_a_decided_candidate_type_again_keeps_its_status(
    session: Session, status: CandidateTypeStatus
) -> None:
    # 11.5.4: reddedilen aday yeniden görülünce listeye (pending) geri düşmez.
    _uploads(session)
    first = record_candidate_type_sighting(
        session, proposed_name="Peruvian Diploma", upload_id=FIRST_UPLOAD, page_id=11
    )
    first.candidate_type.status = status.value
    session.commit()

    again = record_candidate_type_sighting(
        session, proposed_name="Peruvian Diploma", upload_id=SECOND_UPLOAD, page_id=42
    )

    session.commit()
    session.expire_all()
    assert again.counted
    stored = session.scalars(select(CandidateDocumentType)).one()
    assert (stored.status, stored.seen_count) == (status.value, 2)


def _record_concurrently(factory: sessionmaker[Session]) -> list[bool]:
    barrier = threading.Barrier(CONCURRENT_CALLS)

    def record_one(page_id: int) -> bool:
        barrier.wait()
        name = "Peruvian Diploma" if page_id % 2 else "PERUVIAN DIPLOMA"
        with factory() as session, session.begin():
            sighting = record_candidate_type_sighting(
                session, proposed_name=name, upload_id=FIRST_UPLOAD, page_id=page_id
            )
            return sighting.created

    with ThreadPoolExecutor(max_workers=CONCURRENT_CALLS) as pool:
        futures = [pool.submit(record_one, page_id) for page_id in range(1, CONCURRENT_CALLS + 1)]
        return [future.result() for future in futures]


def _assert_one_record_counting_every_sighting(created: list[bool], engine: Engine) -> None:
    assert created.count(True) == 1
    with create_session_factory(engine)() as session:
        stored = session.scalars(select(CandidateDocumentType)).one()
        assert sorted(stored.sample_page_ids) == list(range(1, CONCURRENT_CALLS + 1))
        assert stored.seen_count == CONCURRENT_CALLS


def _prepare(engine: Engine) -> sessionmaker[Session]:
    factory = create_session_factory(engine)
    with factory() as session, session.begin():
        session.add(Upload(id=FIRST_UPLOAD, channel="web"))
    return factory


def test_concurrent_sightings_on_sqlite_share_one_record(engine: Engine) -> None:
    created = _record_concurrently(_prepare(engine))

    _assert_one_record_counting_every_sighting(created, engine)


def test_concurrent_sightings_on_postgresql_share_one_record(postgres_url: str) -> None:
    engine = create_db_engine(postgres_url, pool_size=CONCURRENT_CALLS, max_overflow=0)
    try:
        Base.metadata.create_all(engine)
        created = _record_concurrently(_prepare(engine))

        _assert_one_record_counting_every_sighting(created, engine)
    finally:
        engine.dispose()
