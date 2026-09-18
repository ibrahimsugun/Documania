"""Bütünlük ve atomik yazma (PRD 00.4.4); sıra ekiyle çakışmasız yayın (00.4.3).

Her yazma aynı dizinde gizli bir geçici dosyaya yapılır (`.belgeee-<rastgele>.part`), SHA-256
yazarken hesaplanır, veri diske zorlanır (`fsync`) ve ancak sonra hedef ada yayınlanır:

- **Yeni dosya** (`write_file`, `copy_file`, `write_sequenced`, `write_unique`): sabit bağ
  (`os.link`) ile. Hedef ad varsa `os.link` `FileExistsError` verir ve bu denetim atomiktir — aynı
  adı seçen iki yazardan biri kazanır, diğeri üzerine yazmaz. Orijinaller ve kopyaları (K10) ve
  çıktı belgeleri (K18: eski çıktı yeniden adlandırılmaz) yalnız bu yolla yazılır.
- **Yeniden üretilen dosya** (`replace_file`): `os.replace` ile. Yalnız sistemin baştan
  ürettiği türev dosyalar içindir (`profil.md`, `reason.json`, katalog dışa aktarımı).

Sonuç: hedef adda ya eksiksiz dosya vardır ya hiç dosya yoktur. Yazma süreç içinde kesilirse
(istisna, `KeyboardInterrupt`) geçici dosya da silinir. Süreç dışarıdan öldürülürse geride
yalnız gizli geçici dosya kalır; açılışta `remove_partial_writes` onu temizler.

`find_sequenced` `write_sequenced`'ın bir gövdeyle yayınlamış olabileceği aynı içerikli dosyaları
bulur: uygulayıcı, işlemi geri alınmış bir uygulamadan kalan çıktıyı ikinci kez yazmaz (07.8.1).
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
from pathlib import Path, PurePath

from app.storage.naming import normalize_extension, sequenced_stem

CHUNK_SIZE = 1024 * 1024
# Açılış temizliği yalnız bu kadar süredir dokunulmamış geçici dosyayı siler; aynı veri
# dizinini kullanan başka bir süreç (bot, işçi) o anda yazıyor olabilir.
PARTIAL_WRITE_MAX_AGE = timedelta(hours=1)

_TEMP_PREFIX = ".belgeee-"
_TEMP_SUFFIX = ".part"
_TEMP_NAME = re.compile(r"\.belgeee-[0-9a-f]{32}\.part")
# K8 sıra eki: `-2`, `-3`… — `-1` ve baştaki sıfır (`-02`) `write_sequenced`'ın ürettiği ad değil.
_SEQUENCE_NUMBER = re.compile(r"[2-9]|[1-9][0-9]+")

type Content = bytes | Iterable[bytes]


class ContentMismatchError(RuntimeError):
    """Yazılan içeriğin SHA-256'sı beklenenle eşleşmiyor; hiçbir şey yayınlanmadı."""


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


def write_sequenced(
    directory: Path,
    stem: str,
    extension: str,
    content: Content,
    *,
    expected_sha256: str | None = None,
) -> StoredFile:
    """`stem.ext` boşsa ona, doluysa ilk boş `stem-2.ext`, `stem-3.ext`… adına yazar (K8).

    Aynı gövdeyi taşıyan dosya uzantısı farklı olsa da aynı türden belge sayılır
    (`Passport.jpeg` varken gelen `.png` → `Passport-2.png`). Karşılaştırma harf büyüklüğüne
    duyarsızdır; davranış Windows ve Linux'ta aynıdır. Diskte arada boş kalmış bir ek varsa
    (ör. arşive taşınmış belge) ilk boş ek kullanılır. Seçilen ek `sequence_no` olarak döner.

    `expected_sha256` verilmişse içerik yayından önce onunla karşılaştırılır; tutmazsa hiçbir şey
    yayınlanmaz: `ContentMismatchError`.
    """
    extension = normalize_extension(extension)
    sequenced_stem(stem, 1)  # gövdeyi yazmadan önce doğrula
    temp, sha256, size = _write_temp(directory, content)
    try:
        _check_expected_sha256(sha256, expected_sha256)
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


def find_sequenced(
    directory: Path, stem: str, extension: str, *, sha256: str, size: int
) -> list[StoredFile]:
    """`write_sequenced(directory, stem, extension, …)`'in yayınlamış olabileceği ve içeriği
    `sha256` olan dosyalar, sıra numarasına göre artan (07.8.1).

    Ad tam olarak `stem.ext` ya da `stem-N.ext`'tir (N ≥ 2, eksiz; K8) — `write_sequenced`'ın
    ürettiği biçim, harf büyüklüğü dahil. Yalnız boyu tutan dosyalar hash'lenir; yayınlanmamış
    geçici dosyalar ve dizinler sayılmaz. Dizin yoksa boş liste.
    """
    extension = normalize_extension(extension)
    sequenced_stem(stem, 1)  # gövdeyi doğrula
    try:
        with os.scandir(directory) as entries:
            candidates = sorted(
                (sequence_no, Path(entry.path))
                for entry in entries
                if (sequence_no := _sequence_no(entry.name, stem, extension)) is not None
                and entry.is_file(follow_symlinks=False)
                and entry.stat(follow_symlinks=False).st_size == size
            )
    except FileNotFoundError:
        return []
    return [
        StoredFile(path, sha256, size, sequence_no)
        for sequence_no, path in candidates
        if sha256_file(path) == sha256
    ]


def write_unique(
    directory: Path, name: str, content: Content, *, expected_sha256: str | None = None
) -> StoredFile:
    """`name` boşsa ona, doluysa ilk boş `gövde-2.uzantı`, `gövde-3.uzantı`… adına yazar.

    K8 kalıbına uymayan adlar içindir (Alinan kopyası orijinal adını korur, 07.7.2): `name` tek
    bir yol parçasıdır; ek son uzantının önüne girer (`tarama.pdf` → `tarama-2.pdf`, uzantısız
    `tarama` → `tarama-2`). `write_sequenced`'ın aksine uzantısı farklı ad dolu sayılmaz; ad
    karşılaştırması harf büyüklüğüne duyarsızdır. Seçilen ek `sequence_no` olarak döner.

    `expected_sha256` verilmişse yazılan içerik yayından önce onunla karşılaştırılır; tutmazsa
    geçici dosya silinir, hiçbir şey yayınlanmaz: `ContentMismatchError`.
    """
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"Geçersiz dosya adı: {name!r}")
    suffix = PurePath(name).suffix
    stem = name.removesuffix(suffix)
    temp, sha256, size = _write_temp(directory, content)
    try:
        _check_expected_sha256(sha256, expected_sha256)
        taken = _names_in_use(directory)
        sequence_no = 0
        while True:
            sequence_no += 1
            candidate = name if sequence_no == 1 else f"{stem}-{sequence_no}{suffix}"
            if candidate.casefold() in taken:
                continue
            target = directory / candidate
            try:
                os.link(temp, target)
            except FileExistsError:
                continue  # aynı adı eşzamanlı başka bir yazar aldı
            _fsync_directory(directory)
            return StoredFile(target, sha256, size, sequence_no)
    finally:
        temp.unlink(missing_ok=True)


def is_partial_write(name: str) -> bool:
    """Ad, yayınlanmamış (yazılmakta ya da öldürülmüş) bir geçici dosyanın adı mı."""
    return _TEMP_NAME.fullmatch(name) is not None


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
            if not is_partial_write(name):
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


def _check_expected_sha256(sha256: str, expected_sha256: str | None) -> None:
    if expected_sha256 is not None and sha256 != expected_sha256:
        raise ContentMismatchError(
            f"Yazılan içeriğin SHA-256'sı beklenenle eşleşmiyor: beklenen {expected_sha256}, "
            f"yazılan {sha256}"
        )


def _names_in_use(directory: Path) -> set[str]:
    with os.scandir(directory) as entries:
        return {entry.name.casefold() for entry in entries}


def _sequence_no(name: str, stem: str, extension: str) -> int | None:
    """`name` `sequenced_filename(stem, n, extension)` ise `n`, değilse `None`."""
    name_stem = name.removesuffix(f".{extension}")
    if name_stem == name:
        return None
    if name_stem == stem:
        return 1
    if not name_stem.startswith(f"{stem}-"):
        return None
    number = name_stem[len(stem) + 1 :]
    if _SEQUENCE_NUMBER.fullmatch(number) is None:
        return None
    return int(number)


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
