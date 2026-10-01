"""Eski süreç uyarısı: diskteki kod açılıştan sonra değişti mi (PRD 13.5.3 — PLAN.md §D77).

`--reload`'suz çalışan panel Python kodunu açılıştaki hâliyle bellekte tutar, Jinja şablonlarını ise
her istekte diskten okur. Kod güncellenip süreç yeniden başlatılmazsa yeni şablon eski kodun
vermediği değişkeni bekler ve sayfa 500 verir. Panel açılışta `app/` altındaki `.py` dosyalarının ve
`templates/` dizinlerindeki dosyaların parmak izini (göreli yol + mtime + boyut özeti) alır; panel
isteğinde en çok `RECHECK_SECONDS`'te bir yeniden hesaplar. Farklıysa `base.html` her sayfanın
üstünde yeniden başlatma uyarısı gösterir. Hesaplama hata verirse uyarı gösterilmez, sayfa 500'e
düşmez.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[1]
RECHECK_SECONDS = 30.0
SHORT_LENGTH = 12


def _watched_files(root: Path) -> list[Path]:
    files = list(root.rglob("*.py"))  # `.pyc` bayt kodu eşleşmez
    files += [
        path
        for templates in root.rglob("templates")
        if templates.is_dir()
        for path in templates.rglob("*")
        if path.is_file()
    ]
    return sorted(set(files))


def fingerprint(root: Path) -> str:
    """`root` altındaki izlenen dosyaların yol + mtime + boyut özeti (SHA-256, onaltılık)."""
    digest = hashlib.sha256()
    for path in _watched_files(root):
        stat = path.stat()
        relative = path.relative_to(root).as_posix()
        digest.update(f"{relative}\0{stat.st_mtime_ns}\0{stat.st_size}\n".encode())
    return digest.hexdigest()


class CodeWatch:
    """Açılıştaki parmak izini tutar; diskteki kodun değişip değişmediğini söyler."""

    def __init__(
        self,
        root: Path = APP_ROOT,
        *,
        recheck_seconds: float = RECHECK_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._root = root
        self._recheck_seconds = recheck_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self.startup = fingerprint(root)
        self._checked_at = clock()
        self._stale = False

    @property
    def short(self) -> str:
        """Açılıştaki parmak izinin kısa hâli (`/health`'teki `code`)."""
        return self.startup[:SHORT_LENGTH]

    def is_stale(self) -> bool:
        """Diskteki kod açılıştakinden farklı mı; en çok `recheck_seconds`'te bir hesaplanır.

        Bir kez farklı bulunan süreç yeniden başlatılana kadar eski sayılır (dosya eski hâline
        dönse bile bellekteki kodun hangi hâl olduğu bilinmez).
        """
        with self._lock:
            if self._stale:
                return True
            now = self._clock()
            if now - self._checked_at < self._recheck_seconds:
                return False
            self._checked_at = now
            try:
                self._stale = fingerprint(self._root) != self.startup
            except OSError:
                logger.warning("Kod parmak izi hesaplanamadı; eski süreç uyarısı atlandı.")
                return False
            return self._stale
