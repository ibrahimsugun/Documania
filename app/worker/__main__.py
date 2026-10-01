"""Standalone persistent queue worker (PRD 13.5.2)."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from types import FrameType

from app.catalog import load_catalog_on_startup
from app.config import get_settings
from app.db.schema_check import SchemaVersionError, ensure_schema_current
from app.storage import prepare_data_dir
from app.worker.runner import create_worker

logger = logging.getLogger(__name__)


def main() -> int:
    """Boot one queue worker and wait for a graceful signal-driven shutdown."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    try:
        # 13.5.3: göç koşulmamış (ya da kodun bilmediği ileri) şemayla kuyruk işlenmez.
        ensure_schema_current(settings)
    except SchemaVersionError as exc:
        print(exc, file=sys.stderr)
        return 1
    layout = prepare_data_dir(settings.data_dir)
    # 00.6.2: analiz kataloğu tablodan okur; tablo boşsa işçi başlamadan tohum yüklenir.
    load_catalog_on_startup(settings.database_url, layout)
    worker = create_worker(settings, layout)
    shutdown_requested = threading.Event()

    def request_shutdown(signum: int, _frame: FrameType | None) -> None:
        logger.info("Worker shutdown requested (signal %s)", signum)
        shutdown_requested.set()
        worker.request_stop()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    worker.start(paused=True)
    # Keep the queue loop gated until shutdown signals from startup have been reconciled.
    if shutdown_requested.is_set():
        worker.request_stop()
    worker.resume()
    try:
        worker.wait()
    except KeyboardInterrupt:
        worker.request_stop()
        worker.wait()
    finally:
        # wait() above allows the current leased job to finish before closing its DB engine.
        worker.stop(timeout=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
