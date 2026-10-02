"""Profil alanları formu — kuyruktan profil oluşturma (10.7.3) ve çalışan profilini düzenleme
(10.5.6, PLAN.md §C90-a) aynı altı alanı aynı kuralla okur.

Form yalnız çalışan kaydının alanlarını taşır: ad, soyad, diğer isimler, orijinal yazım, doğum
tarihi, uyruk (`PROFILE_FIELDS`). Başka form alanı okunmaz; belge içeriği (sayfalar, tür, okumalar)
bu formla gönderilemez (K17). Değerler kırpılır, uyruk büyük harfe çevrilir, boş isteğe bağlı alan
`None`'dır; denetim `check_profile_fields`'tır (05.2.2 Latin kuralı, K8 klasör adı) ve doğum tarihi
`YYYY-AA-GG` biçimindedir. Hata iletileri kişisel değer taşımaz.

Etiketler, yardım metinleri ve hata iletileri kaynak dildedir (`N_`); şablon gösterirken çevirir
(`translate`, 10.10.3).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, Form

from app.i18n import N_
from app.matching.match import (
    DATE_OF_BIRTH,
    GIVEN_NAMES,
    NATIONALITY,
    ORIGINAL_SCRIPT_NAME,
    OTHER_NAMES,
    PROFILE_FIELDS,
    PROFILE_TEXT_MAX_LENGTH,
    SURNAME,
    ProfileFields,
    check_profile_fields,
)

INVALID_PROFILE = N_("Profil alanları geçersiz; düzeltip yeniden gönderin.")
BAD_DATE = N_("YYYY-AA-GG biçiminde bir tarih olmalı")
PROFILE_LABELS = {
    GIVEN_NAMES: N_("Ad"),
    SURNAME: N_("Soyad"),
    OTHER_NAMES: N_("Diğer isimler"),
    ORIGINAL_SCRIPT_NAME: N_("Orijinal yazım"),
    DATE_OF_BIRTH: N_("Doğum tarihi"),
    NATIONALITY: N_("Vatandaşlık"),
}
# 05.2.2: ad, soyad ve diğer isimler yalnız Latin harfi taşır; Latin yazımı belgede olmayan
# öneride ad ve soyad boş gelir, İK yazar.
_LATIN_HINT = N_("Latin harfleriyle (belgedeki Latin yazım ya da MRZ; aksanlı harf olur)")
PROFILE_HINTS = {
    GIVEN_NAMES: _LATIN_HINT,
    SURNAME: _LATIN_HINT,
    OTHER_NAMES: _LATIN_HINT,
    ORIGINAL_SCRIPT_NAME: N_("İsmin belgede basılı hâli, birebir (Latin de olabilir)"),
    NATIONALITY: N_("ICAO kodu (ör. RUS, SRB, D)"),
}
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@dataclass(frozen=True, slots=True)
class ProfileFieldView:
    """Formun bir alanı. Form yalnız çalışan kaydının altı alanını taşır; belgenin içeriği
    (sayfalar, tür, okumalar) formda yoktur (K17)."""

    name: str
    label: str
    value: str
    input_type: str
    required: bool
    maxlength: int
    hint: str | None


class ProfileFormError(Exception):
    """Formun alanları geçersiz: alan adı → sorun (kişisel değer yok)."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__(INVALID_PROFILE)
        self.errors = errors

    def field_errors(self) -> list[tuple[str, str]]:
        """(etiket, sorun) çiftleri, `PROFILE_FIELDS` sırasıyla."""
        return [
            (PROFILE_LABELS[name], self.errors[name])
            for name in PROFILE_FIELDS
            if name in self.errors
        ]


def profile_form(
    given_names: Annotated[str, Form()] = "",
    surname: Annotated[str, Form()] = "",
    other_names: Annotated[str, Form()] = "",
    original_script_name: Annotated[str, Form()] = "",
    date_of_birth: Annotated[str, Form()] = "",
    nationality: Annotated[str, Form()] = "",
) -> dict[str, str]:
    """Formun profil alanları, kırpılmış (`PROFILE_FIELDS` anahtarlı). Başka form alanı okunmaz:
    tür, sayfa ya da belge içeriği bu akışla gönderilemez (K17)."""
    return {
        GIVEN_NAMES: given_names.strip(),
        SURNAME: surname.strip(),
        OTHER_NAMES: other_names.strip(),
        ORIGINAL_SCRIPT_NAME: original_script_name.strip(),
        DATE_OF_BIRTH: date_of_birth.strip(),
        NATIONALITY: nationality.strip().upper(),
    }


ProfileValues = Annotated[dict[str, str], Depends(profile_form)]


def parse_profile(values: dict[str, str]) -> ProfileFields:
    """Formun değerlerinden profil; geçersizse `ProfileFormError` (`check_profile_fields` + tarih
    biçimi). Boş isteğe bağlı alan `None`'dır."""
    errors: dict[str, str] = {}
    born: date | None = None
    text = values[DATE_OF_BIRTH]
    if text:
        try:
            if not _ISO_DATE.fullmatch(text):
                raise ValueError(text)
            born = date.fromisoformat(text)
        except ValueError:
            errors[DATE_OF_BIRTH] = BAD_DATE
    fields = ProfileFields(
        given_names=values[GIVEN_NAMES],
        surname=values[SURNAME],
        other_names=values[OTHER_NAMES] or None,
        original_script_name=values[ORIGINAL_SCRIPT_NAME] or None,
        date_of_birth=born,
        nationality=values[NATIONALITY] or None,
    )
    errors = {**check_profile_fields(fields), **errors}
    if errors:
        raise ProfileFormError(errors)
    return fields


def profile_values(fields: ProfileFields) -> dict[str, str]:
    """Formun gizli alanlarına taşınan değerler (`PROFILE_FIELDS` anahtarlı; boş alan boş metin)."""
    return {name: value or "" for name, value in fields.values().items()}


def profile_digest(fields: ProfileFields) -> str:
    """Alan değerlerinin SHA-256 özeti: onay belirtecinin hedefine girer, değerlerin kendisi
    girmez. Hazırlıktan sonra bir alan değişirse belirteç geçmez."""
    canonical = json.dumps(fields.values(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def profile_form_fields(values: dict[str, str]) -> list[ProfileFieldView]:
    """Formun alanları `values` ile dolu (`PROFILE_FIELDS` sırasıyla)."""
    return [
        ProfileFieldView(
            name=name,
            label=PROFILE_LABELS[name],
            value=values[name],
            input_type="date" if name == DATE_OF_BIRTH else "text",
            required=name in (GIVEN_NAMES, SURNAME),
            maxlength=3 if name == NATIONALITY else PROFILE_TEXT_MAX_LENGTH,
            hint=PROFILE_HINTS.get(name),
        )
        for name in PROFILE_FIELDS
    ]


def profile_text(name: str, value: str | None) -> str:
    """Özet satırındaki değer: boş alan "—", doğum tarihi `GG.AA.YYYY`."""
    if value is None or value == "":
        return "—"
    if name == DATE_OF_BIRTH:
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    return value
