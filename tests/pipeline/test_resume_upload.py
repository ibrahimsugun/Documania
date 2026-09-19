"""13.3.1 — orkestrasyonun sürdürme yolu ve geçiş kancası: `resume_upload`, `checkpoint`,
`ProcessingWithdrawn`, `fail_upload`.

Uçtan uca yeniden başlatma senaryoları `tests/worker/test_restart.py`'dedir; burada orkestrasyonun
kendi sözleşmesi sınanır. Partiler `test_process_upload.py`'deki gibi kurulur (Inbox + commit
edilmiş `received` parti), analiz kayıtlı yanıttandır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session

from app.ai.recording_provider import RecordingProvider
from app.db.models import Event, Page, Plan, Upload, UploadStatus
from app.events import EventType
from app.pipeline import orchestrate
from app.pipeline.orchestrate import (
    ProcessedUpload,
    ProcessingWithdrawn,
    UploadTransitionError,
    current_plan,
    fail_upload,
    process_upload,
    resume_upload,
)
from app.storage import DataLayout
from tests.pipeline.test_process_upload import (
    CHAIN,
    SETTINGS,
    _NoAnalysis,
    _passport_pdf,
    _received_upload,
    _recording,
    catalog,  # noqa: F401 — fikstür
)


class _Crash(BaseException):
    """Sürecin ölümü: orkestrasyon yakalamaz, o anki işlem commit edilmez."""


class _Recorder:
    """Geçiş kancası: çağrıldığı durumları ve o ana kadar commit edilmiş işlem sayısını tutar."""

    def __init__(self, engine: Engine, *, withdraw_at: UploadStatus | None = None) -> None:
        self.calls: list[tuple[UploadStatus, int]] = []
        self.withdraw_at = withdraw_at
        self._commits = 0
        event.listen(engine, "commit", self._count)

    def _count(self, _connection: object) -> None:
        self._commits += 1

    def __call__(self, session: Session, status: UploadStatus) -> None:
        self.calls.append((status, self._commits))
        if status is self.withdraw_at:
            raise ProcessingWithdrawn("iş başka işleyiciye geçti")

    @property
    def statuses(self) -> list[UploadStatus]:
        return [status for status, _commits in self.calls]


def _crash_in(monkeypatch: pytest.MonkeyPatch, step: str) -> None:
    real = getattr(orchestrate, step)

    def crash(*args: Any, **kwargs: Any) -> Any:
        real(*args, **kwargs)
        raise _Crash

    monkeypatch.setattr(orchestrate, step, crash)


def _types(session: Session) -> list[str]:
    return list(session.scalars(select(Event.type).order_by(Event.id)))


# --- geçiş kancası -------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_the_checkpoint_runs_inside_every_transition_before_its_commit(
    session: Session, layout: DataLayout, engine: Engine
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    recorder = _Recorder(engine)

    result = process_upload(
        session, layout, upload, settings=SETTINGS, provider=_recording(), checkpoint=recorder
    )

    assert result.status == UploadStatus.DONE
    assert recorder.statuses == [*CHAIN, UploadStatus.DONE]
    # Kanca her seferinde geçişin commit'inden önce çalıştı: k. çağrıda k−1 commit görülmüş.
    first = recorder.calls[0][1]
    assert [commits - first for _status, commits in recorder.calls] == [0, 1, 2, 3, 4]


@pytest.mark.usefixtures("catalog")
def test_the_failure_record_also_goes_through_the_checkpoint(
    session: Session, layout: DataLayout, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))

    def broken_plan(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("plan kurulamadı")

    monkeypatch.setattr(orchestrate, "create_plan", broken_plan)
    recorder = _Recorder(engine)

    result = process_upload(
        session, layout, upload, settings=SETTINGS, provider=_recording(), checkpoint=recorder
    )

    assert result.status == UploadStatus.FAILED
    assert recorder.statuses == [*CHAIN[:3], UploadStatus.FAILED]


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize(
    ("withdraw_at", "left_at"),
    [
        (UploadStatus.RENDERING, UploadStatus.RECEIVED),
        (UploadStatus.PLANNING, UploadStatus.ANALYZING),
        (UploadStatus.DONE, UploadStatus.EXECUTING),
    ],
)
def test_a_withdrawn_batch_keeps_its_last_committed_state_and_is_not_failed(
    session: Session,
    layout: DataLayout,
    engine: Engine,
    withdraw_at: UploadStatus,
    left_at: UploadStatus,
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    before = _types(session)

    with pytest.raises(ProcessingWithdrawn):
        process_upload(
            session,
            layout,
            upload,
            settings=SETTINGS,
            provider=_recording(),
            checkpoint=_Recorder(engine, withdraw_at=withdraw_at),
        )

    assert not session.in_transaction()  # geri çekilen işlem kilidi tutmaz
    session.expire_all()
    assert session.get_one(Upload, upload.id).status == left_at
    types = _types(session)
    assert EventType.PIPELINE_FAILED not in types
    if withdraw_at is UploadStatus.RENDERING:
        assert types == before
    if withdraw_at is UploadStatus.PLANNING:
        # Analiz adımının işi geri alındı: sayfalar analizsiz, olayı yok.
        assert list(session.scalars(select(Page.analysis_status))) == ["pending", "pending"]
        assert EventType.PAGE_ANALYZED not in types
    if withdraw_at is UploadStatus.DONE:
        # Plan `executing` geçişiyle kalıcı; yürütmenin işi geri alındı.
        assert session.scalars(select(Plan)).one().executed_at is None
        assert EventType.OUTPUT_SAVED not in types


@pytest.mark.usefixtures("catalog")
def test_a_withdrawn_failure_record_is_not_written(
    session: Session, layout: DataLayout, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))

    def broken_plan(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("plan kurulamadı")

    monkeypatch.setattr(orchestrate, "create_plan", broken_plan)

    with pytest.raises(ProcessingWithdrawn):
        process_upload(
            session,
            layout,
            upload,
            settings=SETTINGS,
            provider=_recording(),
            checkpoint=_Recorder(engine, withdraw_at=UploadStatus.FAILED),
        )

    session.expire_all()
    assert session.get_one(Upload, upload.id).status == UploadStatus.PLANNING
    assert EventType.PIPELINE_FAILED not in _types(session)


# --- sürdürme -----------------------------------------------------------------------------


@pytest.mark.usefixtures("catalog")
def test_resuming_a_received_batch_processes_it_from_the_start(
    session: Session, layout: DataLayout, engine: Engine
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    recorder = _Recorder(engine)

    result = resume_upload(
        session, layout, upload, settings=SETTINGS, provider=_recording(), checkpoint=recorder
    )

    assert result == ProcessedUpload(UploadStatus.DONE, current_plan(session, upload))
    assert recorder.statuses == [*CHAIN, UploadStatus.DONE]


@pytest.mark.usefixtures("catalog")
@pytest.mark.parametrize(
    ("step", "stopped_at", "transitions"),
    [
        ("render_upload_file", UploadStatus.RENDERING, CHAIN[1:]),
        ("analyze_upload", UploadStatus.ANALYZING, CHAIN[2:]),
        ("create_plan", UploadStatus.PLANNING, CHAIN[3:]),
        ("execute_plan", UploadStatus.EXECUTING, []),
    ],
)
def test_resuming_continues_from_the_stage_where_the_process_died(
    session: Session,
    layout: DataLayout,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    stopped_at: UploadStatus,
    transitions: list[UploadStatus],
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    with monkeypatch.context() as dying:
        _crash_in(dying, step)
        with pytest.raises(_Crash):
            process_upload(session, layout, upload, settings=SETTINGS, provider=_recording())
    session.rollback()
    assert session.get_one(Upload, upload.id).status == stopped_at
    recorder = _Recorder(engine)
    analyzed = stopped_at in {UploadStatus.PLANNING, UploadStatus.EXECUTING}

    result = resume_upload(
        session,
        layout,
        upload,
        settings=SETTINGS,
        # Analizi commit edilmiş parti yapay zekâya sorulmaz (`_NoAnalysis` her isteği düşürür).
        provider=_NoAnalysis() if analyzed else _recording(),
        checkpoint=recorder,
    )

    assert result.status == UploadStatus.DONE
    assert recorder.statuses == [*transitions, UploadStatus.DONE]
    assert [plan.version for plan in session.scalars(select(Plan))] == [1]
    assert _types(session).count(EventType.OUTPUT_SAVED) == 1


@pytest.mark.usefixtures("catalog")
def test_a_resumed_batch_whose_analysis_had_a_failed_page_ends_partial(
    session: Session, layout: DataLayout, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Analiz (başarısız sayfasıyla) commit edildi, süreç planlamada öldü; sonuç sayfalardan okunur.
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    broken = tmp_path / "bozuk-kayit"
    broken.mkdir()
    (broken / "0.json").write_text('{"page_index": 0}', encoding="utf-8")
    with monkeypatch.context() as dying:
        _crash_in(dying, "create_plan")
        with pytest.raises(_Crash):
            process_upload(
                session,
                layout,
                upload,
                settings=SETTINGS,
                provider=RecordingProvider.from_directory(broken),
            )
    session.rollback()

    result = resume_upload(session, layout, upload, settings=SETTINGS, provider=_NoAnalysis())

    assert result.status == UploadStatus.PARTIAL
    assert session.get_one(Upload, upload.id).status == UploadStatus.PARTIAL


@pytest.mark.parametrize("status", [UploadStatus.DONE, UploadStatus.PARTIAL, UploadStatus.FAILED])
def test_a_batch_in_a_final_state_is_not_resumed(
    session: Session, layout: DataLayout, status: UploadStatus
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    upload.status = status.value
    session.commit()

    with pytest.raises(UploadTransitionError, match=f"'{status}' durumunda"):
        resume_upload(session, layout, upload, settings=SETTINGS, provider=_NoAnalysis())

    assert not session.in_transaction()
    assert session.get_one(Upload, upload.id).status == status
    assert EventType.PIPELINE_FAILED not in _types(session)


# --- dışarıdan başarısız yapma ------------------------------------------------------------


def test_failing_a_batch_from_outside_records_where_it_stopped(
    session: Session, layout: DataLayout
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    upload.status = UploadStatus.PLANNING.value
    session.commit()

    stage = fail_upload(session, upload, RuntimeError("dış hata metni loga girmez"))

    assert stage is UploadStatus.PLANNING
    assert upload.status == UploadStatus.FAILED
    (failed,) = session.scalars(select(Event).where(Event.type == EventType.PIPELINE_FAILED))
    assert failed.message is None  # dış kütüphanenin metni yazılmaz
    assert failed.data_json == {
        "stage": "planning",
        "error": "builtins.RuntimeError",
        "traceback": [],
    }


def test_a_finished_batch_cannot_be_failed_from_outside(
    session: Session, layout: DataLayout
) -> None:
    upload = _received_upload(session, layout, ("pasaport.pdf", _passport_pdf()))
    upload.status = UploadStatus.DONE.value
    session.commit()

    with pytest.raises(UploadTransitionError):
        fail_upload(session, upload, RuntimeError("x"))
