"""11.5.5 — aday tür incelemesi işçinin boş-zaman işi olarak (`app.catalog.propose`
`CandidateExaminationJob`, `app.worker.idle`; PLAN.md §C85): kuyruk boşken incelenmemiş bekleyen
aday incelenir, karara bağlanmış aday incelenmez, hata deneme sayacını artırır ve sınırda aday
`failed` olur, olay kullanımı taşır ve maliyet görünümünde sayılır.

Yapay zekâ canlı çağrılmaz: sağlayıcı testin kendi sahte sağlayıcısıdır (kayıtlı sağlayıcı tek
sıralı kayıt kullanır; burada ayrıca çağrı anındaki oturum durumu ölçülür). Kişi ve belgeler
sentetiktir (CONVENTIONS §6).
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import AnalysisProvider, PageAnalysisRequest, TypeProposalRequest
from app.ai.type_proposal import TypeProposalError
from app.ai.usage import report_usage
from app.catalog.propose import (
    CANDIDATE_EXAMINATIONS,
    ERROR_REASON,
    JOB_NAME,
    CandidateExaminationJob,
)
from app.config import ModelPrice, Settings
from app.db.models import (
    CandidateDocumentType,
    CandidateTypeStatus,
    Event,
    Page,
    QueueItem,
    Upload,
    UploadFile,
    decide_candidate_type,
    record_candidate_type_sighting,
)
from app.events import USAGE_DATA_KEY, EventType
from app.storage import DataLayout
from app.web.routers import metrics
from app.worker import IdleContext, IdleJob, Worker, create_worker, default_idle_jobs
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    document_page,
    make_half_filled_image_bytes,
    make_pdf_bytes,
)

SETTINGS = Settings(
    _env_file=None, database_url="sqlite://", worker_lease_seconds=60, worker_max_attempts=3
)
ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "tests" / "fixtures" / "ai" / "type_proposals" / "residence_permit" / "0.json"
NAME = "Montenegrin Residence Permit"
UPLOAD = "u_20260926_0001"


class ProposalProvider(AnalysisProvider):
    """Sahte sağlayıcı: tür taslağı döner (ya da şemaya uymayan yanıt), kullanım bildirir ve çağrı
    anında açık veritabanı oturumu olup olmadığını ölçer."""

    name = "sahte"

    def __init__(self, engine: Engine, database: Path, response: object) -> None:
        super().__init__(model="sahte-model")
        self._engine = engine
        self._database = database
        self._response = response
        self.requests: list[TypeProposalRequest] = []
        self.pool_checked_out: list[int] = []
        self.write_lock_free: list[bool] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmemeli")

    def _request_type_proposal(self, request: TypeProposalRequest) -> object:
        self.requests.append(request)
        self.pool_checked_out.append(self._engine.pool.checkedout())
        self.write_lock_free.append(_write_lock_free(self._database))
        report_usage(1200, 400)
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


def _response() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    return data


def _provider(engine: Engine, database: Path, response: object | None = None) -> ProposalProvider:
    return ProposalProvider(engine, database, _response() if response is None else response)


def _candidate(session_factory: sessionmaker[Session], layout: DataLayout, name: str = NAME) -> int:
    """Ön ve arka yüzlü iki sayfalık PDF'te görülen aday; sayfaların analiz görüntüleri var."""
    with session_factory() as session:
        upload_id = f"{UPLOAD[:-1]}{len(session.scalars(select(Upload)).all()) + 1}"
        session.add(Upload(id=upload_id, channel="web"))
        stored = f"Inbox/{upload_id}/kart.pdf"
        path = layout.resolve(stored)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(make_pdf_bytes(2))
        upload_file = UploadFile(
            upload_id=upload_id,
            original_name="kart.pdf",
            stored_path=stored,
            sha256="0" * 64,
            mime="application/pdf",
        )
        session.add(upload_file)
        session.flush()
        pages = []
        for index, side in enumerate(("front", "back")):
            image = layout.page_image_path(upload_file.id, index)
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(make_half_filled_image_bytes("JPEG"))
            analysis = document_page(
                None,
                title="DOZVOLA ZA BORAVAK",
                person=PERSON_ORNEKOVA,
                shows=("surname", "given_names"),
                side=side,
                candidate_type_name=name,
            ).analysis(index)
            pages.append(
                Page(
                    file=upload_file,
                    index=index,
                    image_path=image.relative_to(layout.root).as_posix(),
                    analysis_json=analysis,
                )
            )
        session.add_all(pages)
        session.flush()
        session.add(
            QueueItem(
                upload_id=upload_id,
                plan_item_id="i1",
                kind="unknown",
                reason="katalog dışı",
                payload_json={"sources": [{"file_id": upload_file.id, "pages": [0, 1]}]},
            )
        )
        candidate = record_candidate_type_sighting(
            session, proposed_name=name, upload_id=upload_id, page_id=pages[0].id
        ).candidate_type
        session.commit()
        return candidate.id


def _row(session_factory: sessionmaker[Session], candidate_id: int) -> CandidateDocumentType:
    with session_factory() as session:
        row = session.get_one(CandidateDocumentType, candidate_id)
        session.expunge(row)
    return row


def _events(session_factory: sessionmaker[Session]) -> list[dict[str, Any]]:
    with session_factory() as session:
        return [
            event.data_json or {}
            for event in session.scalars(
                select(Event)
                .where(Event.type == EventType.CANDIDATE_TYPE_EXAMINED.value)
                .order_by(Event.id)
            )
        ]


def _context(
    session_factory: sessionmaker[Session], layout: DataLayout, provider: AnalysisProvider
) -> IdleContext:
    return IdleContext(session_factory, layout, SETTINGS, provider)


def test_an_empty_queue_lets_the_worker_examine_a_pending_candidate_without_an_open_session(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    candidate_id = _candidate(session_factory, layout)
    provider = _provider(engine, database)
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS,
        provider=provider,
        idle_jobs=[CandidateExaminationJob()],
    )

    assert worker.run_once() is False  # yükleme kuyruğu boş
    assert worker.run_idle_once() is True

    (request,) = provider.requests
    assert len(request.images) == 2  # ilk sayfa ve arka yüz
    assert provider.pool_checked_out == [0]
    assert provider.write_lock_free == [True]
    row = _row(session_factory, candidate_id)
    assert row.proposal_status == "ready"
    assert row.status == CandidateTypeStatus.PENDING.value  # kendiliğinden onay yok (K16)
    assert (row.idle_claimed_by, row.idle_claim_expires_at, row.idle_attempts) == (None, None, 1)
    assert row.proposal_json is not None
    assert row.proposal_json["evidence"]["sides"] == ["front", "back"]
    assert row.proposal_json["proposal"]["sides"] == "front_back"
    assert row.description == row.proposal_json["proposal"]["description"]
    assert _events(session_factory) == [
        {
            "candidate_type_id": candidate_id,
            "result": "ready",
            "pages": 2,
            "provider": "sahte",
            "model": "sahte-model",
            USAGE_DATA_KEY: {"input_tokens": 1200, "output_tokens": 400},
        }
    ]
    # İncelenmiş aday bir daha incelenmez.
    assert worker.run_idle_once() is False
    assert len(provider.requests) == 1


def test_decided_candidates_are_not_examined(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    approved = _candidate(session_factory, layout, "Approved Card")
    rejected = _candidate(session_factory, layout, "Rejected Card")
    with session_factory() as session:
        assert decide_candidate_type(session, approved, CandidateTypeStatus.APPROVED)
        assert decide_candidate_type(session, rejected, CandidateTypeStatus.REJECTED)
        session.commit()
    provider = _provider(engine, database)

    assert CandidateExaminationJob().run_one(_context(session_factory, layout, provider)) is False

    assert provider.requests == []
    assert _row(session_factory, approved).proposal_status is None
    assert _row(session_factory, rejected).proposal_status is None
    assert _events(session_factory) == []


def test_candidates_are_examined_one_per_unit_in_order(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    first = _candidate(session_factory, layout, "First Card")
    second = _candidate(session_factory, layout, "Second Card")
    job = CandidateExaminationJob()
    provider = _provider(engine, database)

    assert job.run_one(_context(session_factory, layout, provider)) is True
    assert (
        _row(session_factory, first).proposal_status,
        _row(session_factory, second).proposal_status,
    ) == ("ready", None)
    assert job.run_one(_context(session_factory, layout, provider)) is True
    assert _row(session_factory, second).proposal_status == "ready"
    assert job.run_one(_context(session_factory, layout, provider)) is False


def test_a_failing_examination_counts_attempts_and_fails_permanently_at_the_limit(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    candidate_id = _candidate(session_factory, layout)
    provider = _provider(engine, database, {"name": "şemaya uymayan yanıt"})
    job = CandidateExaminationJob()
    context = _context(session_factory, layout, provider)

    for attempt in (1, 2):
        with pytest.raises(TypeProposalError):
            job.run_one(context)
        row = _row(session_factory, candidate_id)
        assert (row.proposal_status, row.idle_attempts, row.idle_claimed_by) == (
            None,
            attempt,
            None,
        )
        assert row.proposal_json is None
    with pytest.raises(TypeProposalError):
        job.run_one(context)

    row = _row(session_factory, candidate_id)
    assert (row.proposal_status, row.idle_attempts) == ("failed", 3)
    assert row.proposal_json == {
        "proposal": None,
        "reason": ERROR_REASON,
        "evidence": None,
        "model": "sahte-model",
        "pages": None,
    }
    assert row.proposal_generated_at is not None
    assert row.description is None
    events = _events(session_factory)
    assert [(event["result"], event["error"]) for event in events] == [
        ("error", "TypeProposalError"),
        ("error", "TypeProposalError"),
        ("failed", "TypeProposalError"),
    ]
    assert all(
        event[USAGE_DATA_KEY] == {"input_tokens": 1200, "output_tokens": 400} for event in events
    )
    # Kalıcı başarısız aday bir daha denenmez.
    assert job.run_one(context) is False
    assert len(provider.requests) == 3


def test_the_worker_logs_only_the_error_type_of_a_failing_examination(
    engine: Engine,
    session_factory: sessionmaker[Session],
    layout: DataLayout,
    database: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _candidate(session_factory, layout)
    provider = _provider(engine, database, {"name": "ORNEKOVA"})
    worker = Worker(
        session_factory,
        layout,
        settings=SETTINGS,
        provider=provider,
        idle_jobs=[CandidateExaminationJob()],
    )

    assert worker.run_idle_once() is False

    assert f"Boş-zaman işi {JOB_NAME} başarısız (TypeProposalError)" in caplog.text
    assert "ORNEKOVA" not in caplog.text


def test_the_examination_event_enters_the_cost_view(
    engine: Engine, session_factory: sessionmaker[Session], layout: DataLayout, database: Path
) -> None:
    _candidate(session_factory, layout)
    provider = _provider(engine, database)
    assert CandidateExaminationJob().run_one(_context(session_factory, layout, provider)) is True
    prices = {"sahte-model": ModelPrice(input_per_mtok=Decimal(1), output_per_mtok=Decimal(2))}

    with session_factory() as session:
        overview = metrics.build_overview(session, prices)

    assert EventType.CANDIDATE_TYPE_EXAMINED in metrics.USAGE_EVENT_TYPES
    assert overview.total.analyses == 1
    assert (overview.total.input_tokens, overview.total.output_tokens) == ("1.200", "400")
    assert overview.total.cost == "0.0020 USD"
    assert overview.batches == ()  # parti kalemi değildir
    assert len(overview.months) == 1


def test_the_candidate_examination_is_a_default_idle_job(
    layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # İlk iş aday incelemesidir; eğitim sınıflandırması (11.9.3) ikinci iştir
    # (`tests/worker/test_training_classification.py`).
    job, *_ = default_idle_jobs(SETTINGS)

    assert isinstance(job, CandidateExaminationJob)
    assert isinstance(job, IdleJob)
    assert job.name == JOB_NAME
    assert CANDIDATE_EXAMINATIONS.failed == {"proposal_status": "failed"}
    monkeypatch.setattr("app.worker.runner.create_provider", lambda settings: object())
    worker = create_worker(SETTINGS, layout)
    try:
        assert type(worker.idle_jobs[0]) is CandidateExaminationJob
    finally:
        worker.stop()
