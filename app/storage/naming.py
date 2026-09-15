"""Klasör ve çıktı dosyası adları — K8 (PRD 00.4.2, 00.4.3).

- Çalışan klasörü: `Ad_Soyad_E0001`. İsim kelimeleri `_` ile, her kelime büyük harfle başlar;
  E numarası sistemin verdiği kalıcı numaradır (`app.db.models.allocate_employee_number`).
- Çıktı dosyası: `Ad_Soyad-Belge-Turu.pdf`. `-` yalnız isim ile tür etiketi arasında ve tür
  etiketinin kelimeleri arasında geçer; isimdeki tire `_` olur, böylece ad ayrışabilir kalır.
- Aynı türden ikinci belge `-2`, üçüncüsü `-3` eki alır. Hangi ekin boş olduğuna diskte
  bakılır ve üzerine yazmadan yayınlanır: `app.storage.atomic.write_sequenced`.

Bu modül diske dokunmaz; yalnız ad üretir.
"""

from __future__ import annotations

import re

from app.storage.slug import slugify

# Dosya sistemi bileşeni 255 bayt ve `employees.folder_name` 255 karakterle sınırlı; isim ve
# etiket parçaları sıra eki ve uzantıya yer kalacak şekilde kısaltılır.
NAME_SLUG_MAX_LENGTH = 64
LABEL_SLUG_MAX_LENGTH = 64

_EMPLOYEE_NUMBER = re.compile(r"E[0-9]{4,}")
_STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_EXTENSION = re.compile(r"[a-z0-9]{1,10}")


def person_slug(given_names: str, surname: str) -> str:
    """`Ad_Soyad` — ad(lar) sonra soyad; `DMITRII VASILEV → Dmitrii_Vasilev`."""
    return slugify(
        f"{given_names} {surname}", "_", capitalize=True, max_length=NAME_SLUG_MAX_LENGTH
    )


def employee_folder_name(given_names: str, surname: str, employee_number: str) -> str:
    """`Ad_Soyad_E0001` (K8)."""
    if not _EMPLOYEE_NUMBER.fullmatch(employee_number):
        raise ValueError(f"Geçersiz çalışan numarası: {employee_number!r} (beklenen: E0001)")
    return f"{person_slug(given_names, surname)}_{employee_number}"


def document_stem(given_names: str, surname: str, file_label: str) -> str:
    """`Ad_Soyad-Residence-Card` — uzantısız, sıra eksiz çıktı adı (K8)."""
    label = slugify(file_label, "-", max_length=LABEL_SLUG_MAX_LENGTH)
    return f"{person_slug(given_names, surname)}-{label}"


def normalize_extension(extension: str) -> str:
    """`.PDF → pdf`; uzantı yalnız küçük harf ve rakamdır."""
    normalized = extension.removeprefix(".").lower()
    if not _EXTENSION.fullmatch(normalized):
        raise ValueError(f"Geçersiz dosya uzantısı: {extension!r}")
    return normalized


def sequenced_stem(stem: str, sequence_no: int) -> str:
    """Birinci belge eksiz, sonrakiler `-2`, `-3`… (K8)."""
    if not _STEM.fullmatch(stem):
        raise ValueError(f"Geçersiz dosya adı gövdesi: {stem!r}")
    if sequence_no < 1:
        raise ValueError(f"Sıra numarası 1 veya büyük olmalı: {sequence_no}")
    return stem if sequence_no == 1 else f"{stem}-{sequence_no}"


def sequenced_filename(stem: str, sequence_no: int, extension: str) -> str:
    """`Ad_Soyad-Passport.pdf`, `Ad_Soyad-Passport-2.pdf`…"""
    return f"{sequenced_stem(stem, sequence_no)}.{normalize_extension(extension)}"


def split_document_filename(name: str) -> tuple[str, str]:
    """Sıra eksiz K8 adını gövde ve uzantıya ayırır: `Ad_Soyad-Passport.pdf → (…-Passport, pdf)`.

    Planın `target_name`'idir; gövde ya da uzantı K8 kalıbına uymuyorsa `ValueError`.
    """
    stem, dot, extension = name.rpartition(".")
    if not dot:
        raise ValueError(f"Dosya adında uzantı yok: {name!r}")
    return sequenced_stem(stem, 1), normalize_extension(extension)
