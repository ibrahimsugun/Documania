"""Harita yollarının güvenli çözümü (PRD 11.9.5, PLAN.md §C87 "Yol güvenliği").

Eğitim modunun toplu taraması bir CSV haritasındaki yolları okur. Harita dışarıdan gelir; yolu bu
modül çözer (MASTER-PROMPT §4 yol kuralı) ve yalnız izinli kökün (`DATA_DIR` ya da isteğe bağlı
koleksiyon kökü) altındaki dosyayı gösterir:

- **Yalnız göreli yol.** Windows ve Linux (Docker) yazımı aynı kuralla ele alınır: ters eğik çizgi
  ayraçtır. Mutlak yol (`/…`), sürücü harfi (`C:…`, `C:\\…`), UNC (`\\\\sunucu\\pay`, `//…`), `..`
  parçası ve `:` taşıyan parça (Windows'ta sürücüye ya da veri akışına döner) reddedilir. Boş ve `.`
  parçaları yok sayılır.
- **Kökte kalır.** Göreli yol kökün altında birleştirilip sembolik bağlar izlenerek çözülür;
  çözülen yol kökün dışına çıkıyorsa (kökten kaçan sembolik bağ ya da bağlantı noktası) reddedilir.
- **Klasör satırı.** Klasörün yalnız kendi içindeki (özyinelemesiz) PDF/JPEG/PNG uzantılı düz
  dosyaları alınır; sembolik bağlar, gizli dosyalar ve yarım yazmalar alınmaz.

Modül hiçbir şey yazmaz; yalnız yolu çözer ve dizini listeler. Dosyanın var olup olmadığına çağıran
bakar ("dosya yok" gerekçesi).
"""

from __future__ import annotations

import enum
import os
import re
from pathlib import Path

from app.storage.atomic import is_partial_write

MAP_FILE_SUFFIXES = frozenset({".pdf", ".jpg", ".jpeg", ".png"})
"""Klasör satırında alınan uzantılar (büyük/küçük harf duyarsız)."""

REFERENCE_MAX_LENGTH = 1024
"""Göreli yolun en çok uzunluğu (`training_items.source_ref`)."""

_DRIVE = re.compile(r"[A-Za-z]:")


class UnsafePathReason(enum.StrEnum):
    """Harita yolunun reddedilme nedeni."""

    ABSOLUTE = "absolute"
    DRIVE = "drive"
    UNC = "unc"
    PARENT = "parent"
    ESCAPE = "escape"
    INVALID = "invalid"


UNSAFE_PATH_LABELS: dict[UnsafePathReason, str] = {
    UnsafePathReason.ABSOLUTE: "mutlak yol",
    UnsafePathReason.DRIVE: "sürücü harfi",
    UnsafePathReason.UNC: "UNC yolu",
    UnsafePathReason.PARENT: "`..` parçası",
    UnsafePathReason.ESCAPE: "kökün dışına çıkıyor",
    UnsafePathReason.INVALID: "geçersiz yol",
}


class UnsafePathError(ValueError):
    """Haritadaki yol izinli kökün altında göreli bir yol değil; hiçbir şey okunmaz."""

    def __init__(self, reason: UnsafePathReason) -> None:
        super().__init__(UNSAFE_PATH_LABELS[reason])
        self.reason = reason


def normalize_reference(value: str) -> str:
    """Haritadaki yolu köke göreli POSIX biçimine çevirir (`a/b/c.jpg`); güvensizse
    `UnsafePathError`. Diske bakmaz."""
    text = value.strip()
    if not text or "\x00" in text:
        raise UnsafePathError(UnsafePathReason.INVALID)
    posix = text.replace("\\", "/")
    if posix.startswith("//"):
        raise UnsafePathError(UnsafePathReason.UNC)
    if posix.startswith("/"):
        raise UnsafePathError(UnsafePathReason.ABSOLUTE)
    if _DRIVE.match(posix):
        raise UnsafePathError(UnsafePathReason.DRIVE)
    parts = [part for part in posix.split("/") if part not in ("", ".")]
    if not parts:
        raise UnsafePathError(UnsafePathReason.INVALID)
    if ".." in parts:
        raise UnsafePathError(UnsafePathReason.PARENT)
    if any(":" in part for part in parts):
        raise UnsafePathError(UnsafePathReason.DRIVE)
    normalized = "/".join(parts)
    if len(normalized) > REFERENCE_MAX_LENGTH:
        raise UnsafePathError(UnsafePathReason.INVALID)
    return normalized


class ReferenceResolver:
    """Bir kökün altında göreli yolları çözer; kökün kendisi bir kez çözülür (çok satırlı
    haritada her satırda yeniden çözülmesin)."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def __call__(self, reference: str) -> Path:
        """Göreli yolu kökün altında çözer (sembolik bağlar izlenir) ve çözülen yolu döner; yol
        güvensizse ya da çözülünce kökün dışına çıkıyorsa `UnsafePathError`. Yolun var olması
        gerekmez."""
        parts = normalize_reference(reference).split("/")
        try:
            resolved = self.root.joinpath(*parts).resolve()
        except (OSError, RuntimeError):  # çözülemeyen bağ döngüsü
            raise UnsafePathError(UnsafePathReason.ESCAPE) from None
        if resolved == self.root or not resolved.is_relative_to(self.root):
            raise UnsafePathError(UnsafePathReason.ESCAPE)
        return resolved


def resolve_reference(root: Path, reference: str) -> Path:
    """Tek bir göreli yolu `root` altında çözer (`ReferenceResolver`)."""
    return ReferenceResolver(root)(reference)


def list_map_folder(directory: Path) -> list[Path]:
    """Klasördeki PDF/JPEG/PNG uzantılı düz dosyalar, ad sırasıyla (özyinelemesiz; sembolik bağ,
    gizli dosya ve yarım yazma alınmaz). Klasör yoksa boş."""
    try:
        with os.scandir(directory) as scanned:
            entries = sorted(scanned, key=lambda entry: entry.name.casefold())
    except (FileNotFoundError, NotADirectoryError):
        return []
    return [
        directory / entry.name
        for entry in entries
        if not entry.name.startswith(".")
        and not is_partial_write(entry.name)
        and Path(entry.name).suffix.casefold() in MAP_FILE_SUFFIXES
        and entry.is_file(follow_symlinks=False)
    ]
