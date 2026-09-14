"""Bütünlük ve atomik yazma (PRD 00.4.4); sıra ekiyle çakışmasız yayın (00.4.3).

Her yazma aynı dizinde gizli bir geçici dosyaya yapılır (`.belgeee-<rastgele>.part`), SHA-256
yazarken hesaplanır, veri diske zorlanır (`fsync`) ve ancak sonra hedef ada yayınlanır:

- **Yeni dosya** (`write_file`, `copy_file`, `write_sequenced`): sabit bağ (`os.link`) ile.
  Hedef ad varsa `os.link` `FileExistsError` verir ve bu denetim atomiktir — aynı adı seçen
  iki yazardan biri kazanır, diğeri üzerine yazmaz. Orijinaller (K10) ve çıktı belgeleri
  (K18: eski çıktı yeniden adlandırılmaz) yalnız bu yolla yazılır.
- **Yeniden üretilen dosya** (`replace_file`): `os.replace` ile. Yalnız sistemin baştan
  ürettiği türev dosyalar içindir (`profil.md`, `reason.json`, katalog dışa aktarımı).

Sonuç: hedef adda ya eksiksiz dosya vardır ya hiç dosya yoktur. Yazma süreç içinde kesilirse
(istisna, `KeyboardInterrupt`) geçici dosya da silinir. Süreç dışarıdan öldürülürse geride
yalnız gizli geçici dosya kalır; açılışta `remove_partial_writes` onu temizler.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from app.storage.naming import normalize_extension, sequenced_stem

CHUNK_SIZE = 1024 * 1024
# Açılış temizliği yalnız bu kadar süredir dokunulmamış geçici dosyayı siler; aynı veri
# dizinini kullanan başka bir süreç (bot, işçi) o anda yazıyor olabilir.
PARTIAL_WRITE_MAX_AGE = timedelta(hours=1)

_TEMP_PREFIX = ".belgeee-"
_TEMP_SUFFIX = ".part"
_TEMP_NAME = re.compile(r"\.belgeee-[0-9a-f]{32}\.part")

type Content = bytes | Iterable[bytes]


@dataclass(frozen=True)
class StoredFile:
    """Yayınlanmış dosya: yol, içeriğin SHA-256'sı (hex), bayt boyu ve sıra numarası."""

    path: Path
    sha256: str
    size: int
    sequence_no: int = 1


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    for chunk in iter_file_chunks(path):
        digest.update(chunk)
    return digest.hexdigest()


def iter_file_chunks(path: Path, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            yield chunk


def write_file(path: Path, content: Content) -> StoredFile:
    """Yeni dosya yazar; hedef varsa `FileExistsError` — mevcut dosyanın üzerine yazılmaz."""
    temp, sha256, size = _write_temp(path.parent, content)
    try:
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    _fsync_directory(path.parent)
    return StoredFile(path, sha256, size)


def copy_file(source: Path, destination: Path) -> StoredFile:
    """Kaynağı bayt bayt yeni bir dosyaya kopyalar (K10: Inbox → Alinan)."""
    return write_file(destination, iter_file_chunks(source))


def write_sequenced(directory: Path, stem: str, extension: str, content: Content) -> StoredFile:
    """`stem.ext` boşsa ona, doluysa ilk boş `stem-2.ext`, `stem-3.ext`… adına yazar (K8).

    Aynı gövdeyi taşıyan dosya uzantısı farklı olsa da aynı türden belge sayılır
    (`Passport.jpeg` varken gelen `.png` → `Passport-2.png`). Karşılaştırma harf büyüklüğüne
    duyarsızdır; davranış Windows ve Linux'ta aynıdır. Diskte arada boş kalmış bir ek varsa
    (ör. arşive taşınmış belge) ilk boş ek kullanılır. Seçilen ek `sequence_no` olarak döner.
    """
    extension = normalize_extension(extension)
    sequenced_stem(stem, 1)  # gövdeyi yazmadan önce doğrula
    temp, sha256, size = _write_temp(directory, content)
    try:
        taken = _stems_in_use(directory)
        sequence_no = 0
        while True:
            sequence_no += 1
            candidate = sequenced_stem(stem, sequence_no)
            if candidate.casefold() in taken:
                continue
            target = directory / f"{candidate}.{extension}"
            try:
                os.link(temp, target)
            except FileExistsError:
                continue  # aynı adı eşzamanlı başka bir yazar aldı
            _fsync_directory(directory)
            return StoredFile(target, sha256, size, sequence_no)
    finally:
        temp.unlink(missing_ok=True)


def replace_file(path: Path, content: Content) -> StoredFile:
    """Dosyayı atomik olarak yeniden üretir; okuyan her an eski ya da yeni tam içeriği görür."""
    temp, sha256, size = _write_temp(path.parent, content)
    try:
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_directory(path.parent)
    return StoredFile(path, sha256, size)


def remove_partial_writes(root: Path, older_than: timedelta = PARTIAL_WRITE_MAX_AGE) -> list[Path]:
    """Öldürülmüş süreçlerden kalan geçici dosyaları siler; silinenleri döndürür."""
    cutoff = time.time() - older_than.total_seconds()
    removed: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not _TEMP_NAME.fullmatch(name):
                continue
            path = Path(dirpath, name)
            try:
                if path.stat().st_mtime <= cutoff:
                    path.unlink()
                    removed.append(path)
            except (FileNotFoundError, PermissionError):
                # Bu arada yayınlanıp silindi ya da (Windows) hâlâ açık — yazan süreç sahibidir.
                continue
    return removed


def _write_temp(directory: Path, content: Content) -> tuple[Path, str, int]:
    if isinstance(content, str):
        raise TypeError("İçerik bayt olmalı, metin değil")
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / f"{_TEMP_PREFIX}{secrets.token_hex(16)}{_TEMP_SUFFIX}"
    digest = hashlib.sha256()
    size = 0
    chunks = (content,) if isinstance(content, bytes | bytearray) else content
    try:
        with open(temp, "xb") as handle:
            for chunk in chunks:
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return temp, digest.hexdigest(), size


def _stems_in_use(directory: Path) -> set[str]:
    with os.scandir(directory) as entries:
        return {
            entry.name.rsplit(".", 1)[0].casefold()
            for entry in entries
            if not entry.name.startswith(".")
        }


def _fsync_directory(directory: Path) -> None:
    """Yeni ad girişini diske zorlar; Windows dizin tanıtıcısı açmaya izin vermez."""
    if os.name == "nt":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
