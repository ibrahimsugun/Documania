"""Alinan kopyası — kaynak dosyanın çalışan klasörüne tekil kopyası (PRD 07.7.2, K10).

Yüklenen orijinal Inbox'ta değişmeden kalır; belgesi çözülünce (çıktısı çalışanın `Hazir/`'ına
yazılınca) aynı baytlar çalışanın `Alinan/` klasörüne kopyalanır. Kopya Inbox'taki adını korur; o ad
başka bir içerikle doluysa `ad-2.uzantı` alır (`write_unique`) — hiçbir dosyanın üzerine yazılmaz.

**Aynı hash tekrar kopyalanmaz.** Kopyalamadan önce klasör içerikten taranır: aynı SHA-256'yı
taşıyan dosya varsa — adı ne olursa olsun — yeni kopya yazılmaz, var olan döner. Doğruluk kaynağı
diskin kendisidir (sıra ekinin diskte seçilmesi gibi, 00.4.3); yalnız boyu tutan dosyalar
hash'lenir, yayınlanmamış geçici dosyalar sayılmaz. Tarama ile yayın arasına aynı klasöre yazan
başka bir işlemin girmemesi çağıranın kilididir (07.7 uygulayıcısı).

Beklenen hash, yüklemede kaydedilen `upload_files.sha256`'dır: kopya yayından önce onunla
karşılaştırılır, tutmazsa hiçbir şey yayınlanmaz (`ContentMismatchError`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.storage.atomic import (
    StoredFile,
    is_partial_write,
    iter_file_chunks,
    sha256_file,
    write_unique,
)
from app.storage.layout import DataLayout


@dataclass(frozen=True, slots=True)
class ReceivedCopy:
    """`copy_to_received` sonucu.

    `copied`: bu çağrıda yeni kopya yazıldı. `False` ise aynı içerik klasörde zaten vardı ve
    `stored` o dosyadır.
    """

    stored: StoredFile
    copied: bool


def copy_to_received(
    layout: DataLayout, folder_name: str, source: Path, *, sha256: str
) -> ReceivedCopy:
    """`source`'u çalışanın `Alinan/` klasörüne kopyalar; aynı `sha256` orada varsa kopyalamaz."""
    directory = layout.received_dir(folder_name)
    directory.mkdir(parents=True, exist_ok=True)
    size = source.stat().st_size
    existing = _same_content(directory, sha256=sha256, size=size)
    if existing is not None:
        return ReceivedCopy(StoredFile(existing, sha256, size), copied=False)
    stored = write_unique(directory, source.name, iter_file_chunks(source), expected_sha256=sha256)
    return ReceivedCopy(stored, copied=True)


def _same_content(directory: Path, *, sha256: str, size: int) -> Path | None:
    with os.scandir(directory) as entries:
        candidates = sorted(
            Path(entry.path)
            for entry in entries
            if entry.is_file(follow_symlinks=False)
            and not is_partial_write(entry.name)
            and entry.stat(follow_symlinks=False).st_size == size
        )
    return next((path for path in candidates if sha256_file(path) == sha256), None)
