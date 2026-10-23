"""15.1.2 — hazır şablon incelemesi işçide: kuyruğa alma, kayıtlı yanıtla harita sürümü
(`map_hash`), şemaya uymayan yanıt, sağlayıcı yok, sağlayıcı hatasının denemeleri ve arşiv
(PLAN.md §D123 c). Yapay zekâ canlı çağrılmaz; şablon sentetiktir."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.provider import AnalysisProvider, PageAnalysisRequest, ProviderConnectionError
from app.ai.recording_provider import RecordingProvider
from app.config import Settings
from app.db.models import Event, OutputTemplate, OutputTemplateMap
from app.events import EventType
from app.output_templates.examine import (
    TEMPLATE_EXAMINATIONS,
    TemplateArchivedError,
    TemplateExaminationJob,
    map_hash,
    request_examination,
)
from app.storage import DataLayout
from app.worker import IdleContext
from tests.fixtures.gen import make_half_filled_image_bytes

SETTINGS = Settings(
    _env_file=None, database_url="sqlite://", worker_lease_seconds=60, worker_max_attempts=2
)
MAPS = Path(__file__).resolve().parents[1] / "fixtures" / "ai" / "template_maps"


class FailingProvider(AnalysisProvider):
    """Şablon incelemesinde bağlantı hatası veren sahte sağlayıcı (yeniden denenmez)."""

    name = "sahte"

    def __init__(self) -> None:
        super().__init__(model="sahte-model")
        self.calls = 0

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        raise AssertionError("sayfa analizi istenmedi")

    def _request_template_map(self, request: object) -> object:
        self.calls += 1
        raise ProviderConnectionError("ağ yok — ad ve numara taşımaz")


def _template(session_factory: sessionmaker[Session], layout: DataLayout, *, pages: int = 2) -> int:
    with session_factory() as session:
        template = OutputTemplate(
            name="Ugovor o radu",
            normalized_name="ugovor_o_radu",
            file_label="Ugovor-o-radu",
            sha256="ab" * 32,
            page_count=pages,
            status="draft",
            uploaded_by="ik",
        )
        session.add(template)
        session.flush()
        request_examination(session, template, provider_available=True)
        session.commit()
        template_id = template.id
    for index in range(pages):
        path = layout.template_page_image_path(template_id, index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(make_half_filled_image_bytes("JPEG", (60 + index, 80)))
    return template_id


def _run(
    session_factory: sessionmaker[Session], layout: DataLayout, provider: AnalysisProvider
) -> bool:
    return TemplateExaminationJob().run_one(
        IdleContext(session_factory, layout, SETTINGS, provider)
    )


def _events(session: Session) -> list[Event]:
    query = select(Event).where(Event.type == EventType.TEMPLATE_EXAMINED.value)
    return list(session.scalars(query.order_by(Event.id)))


def test_the_job_freezes_the_recorded_map_as_a_new_version_and_keeps_the_draft(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(session_factory, layout)
    provider = RecordingProvider.from_directory(MAPS / "contract", model="model-x")

    assert _run(session_factory, layout, provider) is True
    assert _run(session_factory, layout, provider) is False  # kuyruk boş

    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        (row,) = session.scalars(select(OutputTemplateMap))
        assert (template.status, template.examine_requested_at, template.examine_error) == (
            "draft",
            None,
            None,
        )
        assert (row.version, row.model, row.approved_at) == (1, "model-x", None)
        assert (row.json["template_id"], row.json["version"], row.json["pages"]) == (
            template_id,
            1,
            2,
        )
        assert row.map_hash == map_hash(row.json)
        (event,) = _events(session)
        assert event.actor == "system"
        assert event.data_json["field_count"] == 6
        assert event.data_json["error"] is None
        assert event.data_json["model"] == "model-x"

        # Yeniden inceleme yeni sürüm açar, eskisi kalır.
        request_examination(session, template, provider_available=True)
        session.commit()
    _run(session_factory, layout, RecordingProvider.from_directory(MAPS / "contract"))
    with session_factory() as session:
        versions = session.scalars(select(OutputTemplateMap.version).order_by("version"))
        assert list(versions) == [1, 2]


def test_a_non_conforming_response_is_not_retried_and_shows_its_reason(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(session_factory, layout, pages=1)

    _run(session_factory, layout, RecordingProvider.from_directory(MAPS / "invalid"))

    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        assert (template.examine_error, template.examine_requested_at) == (
            "invalid_response",
            None,
        )
        assert session.scalars(select(OutputTemplateMap)).all() == []
        assert _events(session)[0].data_json["error"] == "invalid_response"


def test_without_a_provider_the_template_is_not_queued(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        template = OutputTemplate(
            name="Form",
            normalized_name="form",
            file_label="Form",
            sha256="cd" * 32,
            page_count=1,
            status="draft",
            uploaded_by="ik",
        )
        session.add(template)
        session.flush()

        assert request_examination(session, template, provider_available=False) is False
        assert (template.examine_error, template.examine_requested_at) == (
            "provider_unavailable",
            None,
        )
        (event,) = _events(session)
        assert event.data_json == {
            "template_id": template.id,
            "model": None,
            "field_count": 0,
            "error": "provider_unavailable",
        }
        template.status = "archived"
        with pytest.raises(TemplateArchivedError):
            request_examination(session, template, provider_available=True)


def test_provider_errors_are_retried_then_fail_with_the_type_only(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(session_factory, layout, pages=1)
    provider = FailingProvider()

    for _ in range(SETTINGS.worker_max_attempts):
        with pytest.raises(ProviderConnectionError):
            _run(session_factory, layout, provider)
    assert _run(session_factory, layout, provider) is False

    assert provider.calls == SETTINGS.worker_max_attempts
    with session_factory() as session:
        template = session.get_one(OutputTemplate, template_id)
        assert (template.examine_error, template.examine_requested_at) == ("provider_error", None)
        events = _events(session)
        assert [event.data_json["final"] for event in events] == [False, True]
        assert {event.data_json["error_type"] for event in events} == {"ProviderConnectionError"}
        assert "ağ yok" not in str([event.data_json for event in events])


def test_an_archived_template_waits_in_the_queue(
    session_factory: sessionmaker[Session], layout: DataLayout
) -> None:
    template_id = _template(session_factory, layout, pages=1)
    with session_factory() as session:
        session.get_one(OutputTemplate, template_id).status = "archived"
        session.commit()

    assert _run(session_factory, layout, FailingProvider()) is False
    assert TEMPLATE_EXAMINATIONS.failed["examine_error"] == "provider_error"
