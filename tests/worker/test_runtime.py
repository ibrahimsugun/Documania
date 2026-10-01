"""13.5.2 — standalone worker process bootstrap and signal shutdown."""

from __future__ import annotations

import signal
from pathlib import Path
from typing import Any

from app.config import Settings
from app.storage import DataLayout
from app.worker import __main__ as worker_entrypoint


def test_worker_entrypoint_bootstraps_and_requests_graceful_shutdown(
    monkeypatch: Any, tmp_path: Path
) -> None:
    settings = Settings(_env_file=None, database_url="sqlite://", data_dir=tmp_path)
    layout = DataLayout(tmp_path)
    events: list[str] = []
    handlers: dict[signal.Signals, Any] = {}

    class FakeWorker:
        stopping = False

        def start(self, *, paused: bool = False) -> None:
            assert paused
            events.append("start")
            self.stopping = False
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        def resume(self) -> None:
            events.append("resume")

        def request_stop(self) -> None:
            if not self.stopping:
                events.append("request_stop")
            self.stopping = True

        def wait(self) -> bool:
            events.append("wait")
            return True

        def stop(self, timeout: float = 5.0) -> None:
            assert timeout == 0
            events.append("stop")

    worker = FakeWorker()

    monkeypatch.setattr(worker_entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(
        worker_entrypoint,
        "ensure_schema_current",
        lambda resolved_settings: events.append("schema") or "0022",
    )
    monkeypatch.setattr(
        worker_entrypoint,
        "prepare_data_dir",
        lambda data_dir: events.append("prepare") or layout,
    )
    monkeypatch.setattr(
        worker_entrypoint,
        "load_catalog_on_startup",
        lambda database_url, resolved_layout: events.append("seed") or None,
    )
    monkeypatch.setattr(
        worker_entrypoint,
        "create_worker",
        lambda resolved_settings, resolved_layout: events.append("build") or worker,
    )
    monkeypatch.setattr(
        worker_entrypoint.signal,
        "signal",
        lambda signum, handler: handlers.__setitem__(signum, handler),
    )

    result = worker_entrypoint.main()

    assert result == 0
    # 13.5.3: şema denetimi her şeyden önce (veri dizini ve katalog tohumu dahil).
    assert events == [
        "schema",
        "prepare",
        "seed",
        "build",
        "start",
        "request_stop",
        "resume",
        "wait",
        "stop",
    ]


def test_sigterm_during_startup_is_not_lost_when_start_clears_stop(
    monkeypatch: Any, tmp_path: Path
) -> None:
    settings = Settings(_env_file=None, database_url="sqlite://", data_dir=tmp_path)
    layout = DataLayout(tmp_path)
    events: list[str] = []

    class FakeWorker:
        stopping = False

        def start(self, *, paused: bool = False) -> None:
            assert paused
            events.append("start")
            self.stopping = False  # Worker.start clears the event to permit a new run.

        def resume(self) -> None:
            events.append("resume")

        def request_stop(self) -> None:
            events.append("request_stop")
            self.stopping = True

        def wait(self) -> bool:
            assert self.stopping, "a shutdown delivered before start must be re-applied"
            events.append("wait")
            return True

        def stop(self, timeout: float = 5.0) -> None:
            assert timeout == 0
            events.append("stop")

    worker = FakeWorker()
    monkeypatch.setattr(worker_entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(
        worker_entrypoint,
        "ensure_schema_current",
        lambda resolved_settings: events.append("schema") or "0022",
    )
    monkeypatch.setattr(
        worker_entrypoint,
        "prepare_data_dir",
        lambda data_dir: events.append("prepare") or layout,
    )
    monkeypatch.setattr(
        worker_entrypoint,
        "load_catalog_on_startup",
        lambda database_url, resolved_layout: events.append("seed") or None,
    )
    monkeypatch.setattr(
        worker_entrypoint,
        "create_worker",
        lambda resolved_settings, resolved_layout: events.append("build") or worker,
    )

    def install_handler(signum: signal.Signals, handler: Any) -> None:
        if signum is signal.SIGTERM:
            handler(signal.SIGTERM, None)  # arrives after registration, before worker.start()

    monkeypatch.setattr(worker_entrypoint.signal, "signal", install_handler)

    assert worker_entrypoint.main() == 0
    assert events == [
        "schema",
        "prepare",
        "seed",
        "build",
        "request_stop",
        "start",
        "request_stop",
        "resume",
        "wait",
        "stop",
    ]
