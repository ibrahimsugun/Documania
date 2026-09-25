"""Immutable data shared by the operation modules and executor."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.db.models import Document
from app.pipeline.plan import Operation
from app.storage import ReceivedCopy, StoredFile


@dataclass(frozen=True, slots=True)
class ExecutedItem:
    """`execute_ready_item` sonucu: çıktı belgesi satırı, yayınlanan çıktı ve kaynakların Alinan
    kopyaları (`sources` sırasıyla).

    Öğe bu planla daha önce uygulanmışsa (07.8.1) `document` o uygulamanın satırıdır, `output`
    `None` ve `received` boştur: bu çağrı diske dokunmadı.
    """

    document: Document
    output: StoredFile | None
    received: tuple[ReceivedCopy, ...]

    @property
    def applied(self) -> bool:
        """Öğe bu çağrıda uygulandı; `False` ise önceki uygulamanın çıktısı döndü."""
        return self.output is not None


@dataclass(frozen=True, slots=True)
class MergeSource:
    """merge'ün tek kaynağı: dosya ve ondan alınan sayfalar (`PlanSource.pages`).

    Sayfalar 0 tabanlı, artan ve tekrarsızdır; JPEG/PNG kaynağın tek sayfası `0`'dır.
    """

    path: Path
    pages: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ItemDecision:
    """Öğenin uygulanacak kararı: sahibi, belge türü, fiziksel işlemi ve sıra eksiz K8 hedef adı.

    `hazir` öğede planın kendisidir; kuyruk öğesinde insanın atamasıdır (08.2.1).
    """

    employee_id: str
    document_type_slug: str
    operation: Operation
    target_name: str


@dataclass(frozen=True, slots=True)
class _ItemSource:
    """Öğenin doğrulanmış tek kaynağı: Inbox yolu, alınan sayfalar ve yüklemede kaydedilen hash."""

    path: Path
    pages: tuple[int, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class _ReadyOutput:
    """Yayınlanacak çıktı: K8 gövdesi, gerçek uzantısı, içeriği ve içeriğin SHA-256'sı ile boyu.

    `expected_sha256` doluysa içerik akıştır ve yayından önce o hash'le karşılaştırılır
    (`passthrough`).
    """

    stem: str
    extension: str
    content: bytes | Iterator[bytes]
    sha256: str
    size: int
    expected_sha256: str | None = None
