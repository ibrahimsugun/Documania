"""06.6.1, 06.6.2 — planı yeniden çalıştırma ve yeniden analiz (K9, K18, S18).

Uygulayıcı (07.x) henüz yok; testler `PlanExecutor` sözleşmesine uyan sahte bir uygulayıcı
kullanır: `hazir` öğenin kaynak dosyasını çalışanın `Hazir/` klasörüne olduğu gibi kopyalar ve
plan öğesi başına idempotenttir (07.8.1). Sayfalar gerçek render adımlarından ve kayıtlı yanıtla
analizden geçer; sağlayıcı canlı çağrılmaz.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import build_page_analysis_instructions
from app.ai.provider import AnalysisProvider
from app.ai.recording_provider import RecordingProvider
from app.catalog import import_catalog, load_seed_catalog
from app.config import Settings
from app.db.models import (
    CandidateDocumentType,
    Document,
    DocumentStatus,
    Employee,
    Event,
    Page,
    Plan,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.events import EventType
from app.matching.match import EmployeeAction, MatchedBy
from app.pipeline.analyze import analyze_upload
from app.pipeline.orchestrate import (
    NoPlanError,
    current_plan,
    reanalyze_upload,
    rerun_plan,
)
from app.pipeline.plan import (
    Operation,
    PlanDocument,
    PlanIntegrityError,
    PlanItem,
    Route,
    create_plan,
    read_plan,
)
from app.pipeline.render import (
    extract_upload_file_text,
    mark_upload_file_blank_pages,
    render_upload_file,
)
from app.storage import DataLayout, write_sequenced, write_to_inbox
from tests.fixtures.gen import make_text_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "tests" / "fixtures" / "ai" / "recordings"
CATALOG = load_seed_catalog()
UPLOAD_ID = "u_20260915_0001"
READY_NAME = "Test_Ornekova-Passport.pdf"
PERSONAL_VALUES = ("ORNEKOVA", "Ornekova", "Орнекова", "0000001", "1990-01-01")


@dataclass
class _Executor:
    """`PlanExecutor` sözleşmesine uyan, plan öğesi başına idempotent sahte uygulayıcı."""

    calls: list[tuple[int, str, PlanDocument]] = field(default_factory=list)
    fail: bool = False

    def __call__(
        self, session: Session, layout: DataLayout, plan: Plan, document: PlanDocument
    ) -> None:
        self.calls.append((plan.id, plan.plan_hash, document))
        if self.fail:
            raise RuntimeError("uygulayıcı durdu")
        applied = {
            reference["item_id"]
            for output in session.scalars(select(Document).where(Document.plan_id == plan.id))
            for reference in output.source_refs_json
        }
        for item in document.items:
            if item.route is Route.READY and item.item_id not in applied:
                self._copy(session, layout, plan, item)

    @staticmethod
    def _copy(session: Session, layout: DataLayout, plan: Plan, item: PlanItem) -> None:
        # Yalnız bu testlerin tek dosyalık `passthrough` öğesi: kaynak bayt bayt kopyalanır.
        assert item.operation is Operation.PASSTHROUGH
        assert item.target_name is not None and item.target_format is not None
        assert item.employee.employee_id is not None and item.document_type_slug is not None
        (source,) = item.sources
        owner = session.get_one(Employee, item.employee.employee_id)
        original = session.get_one(UploadFile, source.file_id)
        stem = item.target_name.removesuffix(f".{item.target_format.value}")
        stored = write_sequenced(
            layout.ready_dir(owner.folder_name),
            stem,
            item.target_format.value,
            layout.resolve(original.stored_path).read_bytes(),
        )
        session.add(
            Document(
                employee_id=owner.id,
                type_slug=item.document_type_slug,
                path=stored.path.relative_to(layout.root).as_posix(),
                format=item.target_format.value,
                sequence_no=stored.sequence_no,
                plan_id=plan.id,
                source_refs_json=[{"item_id": item.item_id, **source.model_dump(mode="json")}],
            )
        )
        session.flush()


def _recording(directory: str = "russian_passport") -> RecordingProvider:
    return RecordingProvider.from_directory(RECORDINGS / directory)


def _passport_upload(session: Session, layout: DataLayout) -> Upload:
    """Tek sayfalık sentetik pasaport PDF'i: gerçek render ve `russian_passport` kaydıyla analiz."""
    import_catalog(session, CATALOG)
    upload = Upload(id=UPLOAD_ID, channel="web", status=UploadStatus.ANALYZING.value)
    session.add(upload)
    stored = write_to_inbox(layout, upload.id, "pasaport.pdf", make_text_pdf_bytes(["PASAPORT"]))
    upload_file = UploadFile(
        upload=upload,
        original_name="pasaport.pdf",
        stored_path=stored.path.relative_to(layout.root).as_posix(),
        sha256=stored.sha256,
        mime="application/pdf",
    )
    session.add(upload_file)
    session.flush()
    settings = Settings(_env_file=None, database_url="sqlite://")
    render_upload_file(session, layout, settings, upload_file)
    extract_upload_file_text(session, layout, upload_file)
    mark_upload_file_blank_pages(session, layout, upload_file)
    analyze_upload(
        session,
        layout,
        upload,
        provider=_recording(),
        instructions=build_page_analysis_instructions(CATALOG),
    )
    return upload


def _executed_upload(
    session: Session, layout: DataLayout, executor: _Executor
) -> tuple[Upload, Plan]:
    """Partinin ilk planını üretip uygular ve commit eder (09.2'nin ilk işleyişi yerine)."""
    upload = _passport_upload(session, layout)
    plan = create_plan(session, layout, upload, catalog=CATALOG, model="recording")
    executor(session, layout, plan, read_plan(plan))
    session.commit()
    return upload, plan


def _events(session: Session, event_type: EventType | None = None) -> list[Event]:
    query = select(Event).order_by(Event.id)
    if event_type is not None:
        query = query.where(Event.type == event_type)
    return list(session.scalars(query))


def _count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _documents(session: Session) -> list[Document]:
    return list(session.scalars(select(Document).order_by(Document.id)))


def _ready_files(layout: DataLayout) -> list[str]:
    return sorted(path.name for path in layout.ready_dir("Test_Ornekova_E0001").iterdir())


def _analyses(session: Session) -> list[Any]:
    return [copy.deepcopy(page.analysis_json) for page in session.scalars(select(Page))]


def _assert_no_personal_values(events: list[Event]) -> None:
    logged = json.dumps([[event.data_json, event.message] for event in events], ensure_ascii=False)
    for value in PERSONAL_VALUES:
        assert value not in logged


def _forbid_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bundan sonra yapay zekâ sağlayıcısına giden her istek testi düşürür."""

    def _refuse(self: AnalysisProvider, request: object) -> object:
        raise AssertionError("yeniden çalıştırma yapay zekâ çağırmamalı")

    monkeypatch.setattr(AnalysisProvider, "_request_analysis_with_retry", _refuse)


# --- 06.6.1 yeniden çalıştırma ---------------------------------------------------------------


def test_the_current_plan_is_the_highest_version(session: Session, layout: DataLayout) -> None:
    upload = _passport_upload(session, layout)
    assert current_plan(session, upload) is None

    first = create_plan(session, layout, upload, catalog=CATALOG)
    second = create_plan(session, layout, upload, catalog=CATALOG)

    assert (first.version, second.version) == (1, 2)
    assert current_plan(session, upload) is second


def test_rerun_applies_the_frozen_current_plan_without_analysis_or_planning(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = _Executor()
    upload, plan = _executed_upload(session, layout, executor)
    _forbid_ai(monkeypatch)
    frozen = (copy.deepcopy(plan.json), plan.plan_hash)
    before = (
        [event.id for event in _events(session)],
        _count(session, Plan),
        _count(session, Employee),
        _count(session, CandidateDocumentType),
        _analyses(session),
    )

    run = rerun_plan(session, layout, upload, executor=executor)

    assert run.plan is plan
    assert run.document == read_plan(plan)
    assert executor.calls[-1] == (plan.id, frozen[1], read_plan(plan))
    assert (plan.json, plan.plan_hash) == frozen
    assert (_count(session, Plan), _count(session, Employee)) == before[1:3]
    assert _count(session, CandidateDocumentType) == before[3]
    assert _analyses(session) == before[4]
    added = [event for event in _events(session) if event.id not in before[0]]
    assert [(event.type, event.upload_id, event.message) for event in added] == [
        (EventType.PLAN_RERUN, upload.id, None)
    ]
    assert added[0].data_json == {
        "plan_id": plan.id,
        "version": 1,
        "plan_hash": plan.plan_hash,
    }
    assert plan.executed_at is not None and plan.executed_at.tzinfo is UTC


def test_s18_rerun_gives_the_same_outputs_and_no_second_file(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    # S18: mevcut plandan yeniden çalıştırma — aynı çıktılar, sağlayıcı çağrılmaz, ikinci dosya yok.
    executor = _Executor()
    upload, plan = _executed_upload(session, layout, executor)
    (item,) = read_plan(plan).items
    assert (item.route, item.target_name) == (Route.READY, READY_NAME)
    _forbid_ai(monkeypatch)
    original = layout.resolve(upload.files[0].stored_path).read_bytes()
    outputs = [(output.id, output.path, output.sequence_no) for output in _documents(session)]
    assert _ready_files(layout) == [READY_NAME]

    rerun_plan(session, layout, upload, executor=executor)
    rerun_plan(session, layout, upload, executor=executor)
    session.commit()

    assert [call[:2] for call in executor.calls] == [(plan.id, plan.plan_hash)] * 3
    assert [(output.id, output.path, output.sequence_no) for output in _documents(session)] == (
        outputs
    )
    assert _ready_files(layout) == [READY_NAME]
    assert layout.resolve(outputs[0][1]).read_bytes() == original
    assert len(_events(session, EventType.PLAN_RERUN)) == 2
    assert _count(session, Plan) == 1


def test_rerun_runs_the_latest_version(session: Session, layout: DataLayout) -> None:
    upload = _passport_upload(session, layout)
    create_plan(session, layout, upload, catalog=CATALOG)
    latest = create_plan(session, layout, upload, catalog=CATALOG)
    executor = _Executor()

    run = rerun_plan(session, layout, upload, executor=executor)

    assert run.plan is latest
    assert [call[:2] for call in executor.calls] == [(latest.id, latest.plan_hash)]


def test_rerun_without_a_plan_is_refused_without_a_trace(
    session: Session, layout: DataLayout
) -> None:
    upload = _passport_upload(session, layout)
    before = len(_events(session))
    executor = _Executor()

    with pytest.raises(NoPlanError, match=f"Partinin planı yok \\(parti {UPLOAD_ID}\\)"):
        rerun_plan(session, layout, upload, executor=executor)

    assert executor.calls == []
    assert len(_events(session)) == before


def test_changed_plan_is_not_rerun(session: Session, layout: DataLayout) -> None:
    upload = _passport_upload(session, layout)
    plan = create_plan(session, layout, upload, catalog=CATALOG)
    changed = copy.deepcopy(plan.json)
    changed["items"][0]["target_name"] = "Baska_Kisi-Passport.pdf"
    plan.json = changed
    executor = _Executor()

    with pytest.raises(PlanIntegrityError, match="hash'i kaydıyla uyuşmuyor"):
        rerun_plan(session, layout, upload, executor=executor)

    assert executor.calls == []
    assert _events(session, EventType.PLAN_RERUN) == []
    assert plan.executed_at is None


def test_rerun_leaves_the_transaction_to_the_caller(session: Session, layout: DataLayout) -> None:
    executor = _Executor()
    upload, plan = _executed_upload(session, layout, executor)

    with pytest.raises(RuntimeError, match="uygulayıcı durdu"):
        rerun_plan(session, layout, upload, executor=_Executor(fail=True))
    assert plan.executed_at is None

    rerun_plan(session, layout, upload, executor=executor)
    session.rollback()

    assert _events(session, EventType.PLAN_RERUN) == []
    assert session.get_one(Plan, plan.id).executed_at is None


# --- 06.6.2 yeniden analiz -------------------------------------------------------------------


def test_reanalysis_opens_the_next_version_and_marks_old_outputs_as_old_version(
    session: Session, layout: DataLayout
) -> None:
    executor = _Executor()
    upload, first = _executed_upload(session, layout, executor)
    frozen = (copy.deepcopy(first.json), first.plan_hash, first.version)
    (old,) = _documents(session)
    old_path, old_bytes = old.path, layout.resolve(old.path).read_bytes()
    provider = _recording()

    reanalysis = reanalyze_upload(
        session, layout, upload, provider=provider, catalog=CATALOG, executor=executor
    )
    session.commit()

    # Sayfa sağlayıcıya yeniden gönderildi, analizden bir sonraki sürüm açıldı ve uygulandı.
    assert len(provider.requests) == 1
    second = reanalysis.plan
    assert (second.version, second.model, second.upload_id) == (2, provider.model, upload.id)
    assert reanalysis.previous_plan is first
    assert reanalysis.document == read_plan(second)
    assert reanalysis.analysis.is_partial is False
    assert current_plan(session, upload) is second
    assert executor.calls[-1][:2] == (second.id, second.plan_hash)
    assert second.executed_at is not None
    # Eski plan değişmez; eski çıktı silinmez, yeniden adlandırılmaz, "eski sürüm" işaretlenir.
    assert (first.json, first.plan_hash, first.version) == frozen
    assert reanalysis.superseded_document_ids == (old.id,)
    assert (old.status, old.path, old.plan_id) == (DocumentStatus.SUPERSEDED, old_path, first.id)
    assert layout.resolve(old_path).read_bytes() == old_bytes
    outputs = _documents(session)
    assert [(output.plan_id, output.status, output.sequence_no) for output in outputs] == [
        (first.id, DocumentStatus.SUPERSEDED, 1),
        (second.id, DocumentStatus.ACTIVE, 2),
    ]
    assert _ready_files(layout) == ["Test_Ornekova-Passport-2.pdf", READY_NAME]
    # Planın açtığı çalışan yeni sürümde numarasından bulunur; ikinci çalışan açılmaz.
    (item,) = reanalysis.document.items
    assert (item.employee.action, item.employee.employee_id, item.employee.matched_by) == (
        EmployeeAction.MATCH,
        "E0001",
        MatchedBy.DOCUMENT_NUMBER,
    )
    assert _count(session, Employee) == 1

    events = _events(session)
    types = [event.type for event in events]
    (reanalyzed,) = _events(session, EventType.PLAN_REANALYZED)
    created = [event for event in events if event.type == EventType.PLAN_CREATED]
    analyzed = [event for event in events if event.type == EventType.PAGE_ANALYZED]
    assert analyzed[-1].id < created[-1].id < reanalyzed.id
    assert types.count(EventType.PLAN_CREATED) == 2
    assert (reanalyzed.upload_id, reanalyzed.message) == (upload.id, None)
    assert reanalyzed.data_json == {
        "plan_id": second.id,
        "version": 2,
        "plan_hash": second.plan_hash,
        "model": provider.model,
        "previous_plan_id": first.id,
        "previous_version": 1,
        "pages": {"analyzed": 1, "failed": 0, "skipped": 0},
        "superseded_document_ids": [old.id],
    }
    _assert_no_personal_values([reanalyzed])

    # Yeniden analizden sonra yeniden çalıştırma yeni sürümü uygular, ikinci kopya üretmez.
    rerun_plan(session, layout, upload, executor=executor)
    assert executor.calls[-1][:2] == (second.id, second.plan_hash)
    assert len(_documents(session)) == 2
    assert _ready_files(layout) == ["Test_Ornekova-Passport-2.pdf", READY_NAME]


def test_reanalysis_marks_only_active_outputs_of_the_older_versions_of_the_upload(
    session: Session, layout: DataLayout
) -> None:
    upload = _passport_upload(session, layout)
    first = create_plan(session, layout, upload, catalog=CATALOG)
    second = create_plan(session, layout, upload, catalog=CATALOG)
    other = Upload(id="u_20260915_0002", channel="web")
    other_plan = Plan(upload=other, version=1, json={}, plan_hash="0" * 64)
    session.add_all([other, other_plan])
    session.flush()

    def output(plan_id: int | None, status: DocumentStatus = DocumentStatus.ACTIVE) -> Document:
        return Document(
            employee_id="E0001",
            type_slug="russian_passport",
            path=f"Employees/Test_Ornekova_E0001/Hazir/belge-{plan_id}-{status.value}.pdf",
            format="pdf",
            plan_id=plan_id,
            source_refs_json=[],
            status=status.value,
        )

    outputs = [
        output(first.id),
        output(first.id, DocumentStatus.SUPERSEDED),
        output(second.id),
        output(None),
        output(other_plan.id),
    ]
    session.add_all(outputs)
    session.flush()

    reanalysis = reanalyze_upload(
        session, layout, upload, provider=_recording(), catalog=CATALOG, executor=_Executor()
    )

    assert reanalysis.plan.version == 3
    assert reanalysis.previous_plan is second
    assert reanalysis.superseded_document_ids == (outputs[0].id, outputs[2].id)
    assert [document.status for document in outputs] == [
        DocumentStatus.SUPERSEDED,
        DocumentStatus.SUPERSEDED,
        DocumentStatus.SUPERSEDED,
        DocumentStatus.ACTIVE,
        DocumentStatus.ACTIVE,
    ]
    assert [document.path for document in outputs] == [
        document.path for document in _documents(session)[:5]
    ]


def test_reanalysis_with_a_failed_page_still_opens_the_version(
    session: Session, layout: DataLayout, tmp_path: Path
) -> None:
    # Yeniden analizin sonucu bağlayıcıdır: sayfa bu kez analiz edilemezse yeni sürüm onu kuyruğa
    # gönderir ve eski çıktı yine "eski sürüm" olur (K18); kısmi başarı partide görünür (03.7.2).
    executor = _Executor()
    upload, first = _executed_upload(session, layout, executor)
    broken = tmp_path / "bozuk-kayit"
    broken.mkdir()
    (broken / "0.json").write_text('{"page_index": 0}', encoding="utf-8")

    reanalysis = reanalyze_upload(
        session,
        layout,
        upload,
        provider=RecordingProvider.from_directory(broken),
        catalog=CATALOG,
        executor=executor,
    )

    (item,) = reanalysis.document.items
    assert (item.route, item.document_type_slug, item.operation) == (Route.UNRESOLVED, None, None)
    assert reanalysis.analysis.is_partial is True
    assert upload.status == UploadStatus.PARTIAL
    (old,) = _documents(session)
    assert (old.plan_id, old.status) == (first.id, DocumentStatus.SUPERSEDED)
    (reanalyzed,) = _events(session, EventType.PLAN_REANALYZED)
    assert reanalyzed.data_json is not None
    assert reanalyzed.data_json["pages"] == {"analyzed": 0, "failed": 1, "skipped": 0}


def test_reanalysis_without_a_plan_calls_no_provider(session: Session, layout: DataLayout) -> None:
    upload = _passport_upload(session, layout)
    analyses, before = _analyses(session), len(_events(session))
    provider = _recording()
    executor = _Executor()

    with pytest.raises(NoPlanError, match="Partinin planı yok"):
        reanalyze_upload(
            session, layout, upload, provider=provider, catalog=CATALOG, executor=executor
        )

    assert (provider.requests, executor.calls) == ([], [])
    assert _analyses(session) == analyses
    assert len(_events(session)) == before
    assert _count(session, Plan) == 0
