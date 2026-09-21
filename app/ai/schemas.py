"""Sayfa analizi sözleşmesi — PRD §8.4 (03.1.1–03.1.4).

Yapay zekâ sağlayıcısının her sayfa için döndürdüğü yanıt bu şemaya uymak zorundadır; uymayan
yanıt `PageAnalysisError` ile bütün olarak reddedilir. Yanıt düzeltilmez, eksik alan tahminle
doldurulmaz. Kurallar:

- §8.4'teki her anahtar yanıtta bulunur (eksik anahtar varsayılanla doldurulmaz); tanımsız anahtar
  reddedilir; tipler zorlanmaz (`"false"` bool, `"0"` sayı değildir). Okunmayan değer `null`dır.
- `language` ISO 639-1 kodu, `script` `latin` · `cyrillic` · `arabic` · `other`; küme dışı değer
  reddedilir. Sayfada dili/alfabesi belirlenecek metin yoksa ikisi de `null` olabilir (03.1.2).
- `document_type_slug` analizde kullanılan katalogda bir slug veya `null`; `candidate_type_name`
  yalnız slug `null` iken dolar.
- `person.other_names` ikinci ad, baba adı gibi ek isimleri ayrı taşır — `given_names`'e karışmaz
  ve çalışan kaydının `other_names` sütununa gider (03.1.3, `PagePerson.employee_fields`).
- `person.contact` belgede açıkça yazılı telefon, e-posta ve adrestir; yazılı olmayan `null`dır
  (03.1.4). Alan adları `employee_contacts.kind` değerleriyle aynıdır (§8.1).
- `fields` okumaları: `legible: true` ise `value` doludur, `legible: false` ise `null`dır —
  okunamayan alanın değeri taşınmaz (K1).

Veritabanından geri okunan `pages.analysis_json` katalog verilmeden `PageAnalysis.model_validate`
ile okunur: katalog analizden sonra değişmiş olabilir, slug denetimi yalnız yanıt kabulündedir.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable
from datetime import date
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from app.catalog.schema import FieldName, ShortText, Slug, Text

# ISO 639-1'in iki harfli dil kodları (183; kaldırılmış `bh`, `iw`, `in`, `ji`, `mo`, `sh` yok).
ISO_639_1_CODES: frozenset[str] = frozenset(
    """
    aa ab ae af ak am an ar as av ay az ba be bg bi bm bn bo br bs ca ce ch co cr cs cu cv cy
    da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht
    hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky
    la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny
    oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss
    st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo
    za zh zu
    """.split()
)

# 03.1.3 — kişiden çalışan kaydına (`employees`, §8.1) taşınan alanlar; sütun adları birebir aynı.
EMPLOYEE_FIELDS = (
    "surname",
    "given_names",
    "other_names",
    "original_script_name",
    "date_of_birth",
    "nationality",
)

_KNOWN_SLUGS = "known_slugs"
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class PageAnalysisError(ValueError):
    """Model yanıtı §8.4 şemasına uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            "Sayfa analizi yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems)
        )


class Script(enum.StrEnum):
    """Sayfadaki yazının alfabesi (03.1.2); küme kapalıdır."""

    LATIN = "latin"
    CYRILLIC = "cyrillic"
    ARABIC = "arabic"
    OTHER = "other"


class Side(enum.StrEnum):
    """Sayfanın belge içindeki yüzü; `front_back` türlerde ön/arka eşleşmesine girer (04.1.2).

    `front_and_back`: `front_back` türde aynı kartın iki yüzü tek sayfada; sayfada başka kişinin
    ya da başka belgenin yüzü de varsa `unknown`. Yapay zekâ yalnız gördüğünü söyler; türün bu
    düzeni kabul edip etmediğine kod karar verir (`check_sides`, PLAN.md §C78).
    """

    FRONT = "front"
    BACK = "back"
    FRONT_AND_BACK = "front_and_back"
    SINGLE = "single"
    UNKNOWN = "unknown"


def _iso_639_1(value: str) -> str:
    if value not in ISO_639_1_CODES:
        raise ValueError("ISO 639-1 dil kodu olmalı (küçük harfli iki harf, ör. tr, ru, sr)")
    return value


def _iso_date(value: object) -> object:
    # Yalnız `YYYY-AA-GG`: gevşek `date` Unix zaman damgasını ve `19900412`'yi de kabul ederdi.
    if type(value) is date:
        return value
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("takvimde geçerli bir ISO 8601 tarihi (YYYY-AA-GG) olmalı")


LanguageCode = Annotated[
    str,
    StringConstraints(strict=True),
    AfterValidator(_iso_639_1),
    WithJsonSchema({"type": "string", "enum": sorted(ISO_639_1_CODES)}),
]
IsoDate = Annotated[date, BeforeValidator(_iso_date)]
# ICAO 9303 uyruk kodu: üç harf (`RUS`), Almanya için tek harf (`D`).
NationalityCode = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z]{1,3}$")]
# `employee_identifiers.value` sütunu 128 karakterdir (§8.1).
DocumentNumber = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)
]
# MRZ satırı olduğu gibi taşınır; biçim ve karakter kümesi 05.3'ün işidir (§20.1).
MrzLine = Annotated[str, StringConstraints(strict=True, min_length=1)]


class PageContact(BaseModel):
    """Belgede açıkça yazılı iletişim bilgisi (03.1.4); yazılı değilse `null`, çıkarım yapılmaz."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phone: Text | None
    email: Text | None
    address: Text | None


class PagePerson(BaseModel):
    """Sayfadan okunan kişi; okunmayan alan `null`, ek isimler `other_names`'te ayrı (03.1.3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    surname: ShortText | None
    given_names: ShortText | None
    other_names: ShortText | None
    original_script_name: ShortText | None
    date_of_birth: IsoDate | None
    nationality: NationalityCode | None
    document_number: DocumentNumber | None
    mrz_lines: Annotated[tuple[MrzLine, ...], Field(min_length=1)] | None
    contact: PageContact

    def employee_fields(self) -> dict[str, str | date | None]:
        """Çalışan kaydına taşınan alanlar; anahtarlar `employees` sütun adlarıdır."""
        return {name: getattr(self, name) for name in EMPLOYEE_FIELDS}


class FieldReading(BaseModel):
    """Tek alanın okuması (K1): okunaklı alanın değeri vardır, okunamayanın değeri taşınmaz."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: Text | None
    legible: StrictBool

    @model_validator(mode="after")
    def _value_matches_legibility(self) -> FieldReading:
        if self.legible and self.value is None:
            raise ValueError("legible: true olan alanın value'su dolu olmalı")
        if not self.legible and self.value is not None:
            raise ValueError(
                "legible: false olan alanın value'su null olmalı; okunamayan değer tahmin edilmez"
            )
        return self


class PageAnalysis(BaseModel):
    """Tek sayfanın analiz yanıtı (§8.4). Yanıt kabulü `validate_page_analysis` ile yapılır."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_index: Annotated[StrictInt, Field(ge=0)]
    is_blank: StrictBool
    is_readable: StrictBool
    language: LanguageCode | None
    script: Script | None
    document_type_slug: Slug | None
    candidate_type_name: ShortText | None
    side: Side
    continues_previous_page: StrictBool
    person: PagePerson
    fields: dict[FieldName, FieldReading]
    notes: Text | None

    @field_validator("document_type_slug")
    @classmethod
    def _slug_in_catalog(cls, value: str | None, info: ValidationInfo) -> str | None:
        known = (info.context or {}).get(_KNOWN_SLUGS)
        if value is not None and known is not None and value not in known:
            raise ValueError(
                f"'{value}' katalogda yok; katalog dışı tür için slug null, "
                "candidate_type_name dolu olmalı"
            )
        return value

    @model_validator(mode="after")
    def _candidate_only_without_slug(self) -> PageAnalysis:
        if self.document_type_slug is not None and self.candidate_type_name is not None:
            raise ValueError("candidate_type_name yalnız document_type_slug null iken dolar")
        return self


def validate_page_analysis(data: object, *, known_slugs: Iterable[str]) -> PageAnalysis:
    """Model yanıtını (JSON metni veya çözülmüş nesne) §8.4'e göre doğrular.

    `known_slugs` analizde kullanılan kataloğun slug'larıdır; katalogda olmayan
    `document_type_slug` reddedilir. Uymayan yanıt `PageAnalysisError` fırlatır.
    """
    context = {_KNOWN_SLUGS: frozenset(known_slugs)}
    if isinstance(data, BaseModel):
        # Hazır örnek pydantic tarafından yeniden doğrulanmaz; katalog denetimi atlanmasın.
        data = data.model_dump(mode="json")
    try:
        if isinstance(data, str | bytes | bytearray):
            return PageAnalysis.model_validate_json(data, context=context)
        return PageAnalysis.model_validate(data, context=context)
    except ValidationError as exc:
        raise PageAnalysisError(_describe(exc)) from None


def _describe(exc: ValidationError) -> list[str]:
    # Gelen değer (`input`) mesaja konmaz: yanıt ad, doğum tarihi, belge numarası taşır
    # (CONVENTIONS §6).
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(part) for part in error["loc"]) or "yanıt"
        problems.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return problems
