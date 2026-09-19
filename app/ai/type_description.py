"""Tür açıklaması sözleşmesi — PRD 11.3.1.

Bir belge türünün örneklerinden (11.2.1) yapay zekâya ürettirilen **yapılandırılmış** açıklama.
Açıklama türü tanır, kişiyi değil: belgenin düzeni, üzerinde basılı başlıklar, diller ve alfabeler,
alanların sayfadaki yeri, MRZ'nin varlığı ve ön/arka yüz farkı; fotoğraf türünde (11.8.1) ayrıca
şirketin kabul ettiği fotoğrafın tanımı (`accepted_photo`). Katalogda metin olarak
(`prompt_description`, §8.6) saklanır; metne çeviren `app.catalog.describe`'dır.

Kurallar sayfa analizi sözleşmesiyle (§8.4, `app.ai.schemas`) aynı ölçüdedir:

- Her anahtar yanıtta bulunur (eksik anahtar varsayılanla doldurulmaz); tanımsız anahtar
  reddedilir; tipler zorlanmaz. Yanıt düzeltilmez: uymayan yanıt `TypeDescriptionError` ile bütün
  olarak reddedilir.
- Dil ISO 639-1 kodu, alfabe `latin` · `cyrillic` · `arabic` · `other`; listelerde tekrar yoktur.
- Metinler kısadır (üst sınırlar alanlarda): açıklama her analiz talimatına girer ve katalog
  metninin token bütçesini (11.4.2) paylaşır.
- `mrz` belgede MRZ yoksa `null`dır; `side_differences` tek yüzlü belgede `null`dır;
  `accepted_photo` fotoğraf türü olmayan belgede `null`dır (denetimi istek bağlamını bilen
  `app.catalog.describe` yapar).

Hata mesajlarına yanıttaki değer konmaz: örnek belge üzerindeki kişisel değer (ad, numara) yanıta
sızmışsa loga ve ekrana taşınmaz (CONVENTIONS §6).
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.ai.schemas import LanguageCode, Script
from app.catalog.schema import FieldName

MAX_HEADINGS = 4
"""En çok kaç ayırt edici başlık yazılır."""

MAX_FIELD_LOCATIONS = 12
"""En çok kaç alanın yeri yazılır."""

Summary = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)
]
Heading = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=60)
]
Location = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80)
]


def _unique[T: Hashable](values: tuple[T, ...]) -> tuple[T, ...]:
    if len(set(values)) != len(values):
        raise ValueError("listede tekrar olmamalı")
    return values


def _unique_headings(values: tuple[str, ...]) -> tuple[str, ...]:
    _unique(tuple(value.casefold() for value in values))
    return values


class TypeDescriptionError(ValueError):
    """Model yanıtı tür açıklaması şemasına uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            "Tür açıklaması yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems)
        )


class FieldLocation(BaseModel):
    """Bir alanın sayfadaki yeri; `field` katalogdaki alan adıdır (`surname`, `document_number`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FieldName
    location: Location


class MrzDescription(BaseModel):
    """Belgedeki MRZ: satır sayısı (TD1 üç satır, TD2/TD3 iki satır) ve yeri."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    line_count: Annotated[StrictInt, Field(ge=2, le=3)]
    location: Location


class TypeDescription(BaseModel):
    """Örneklerden üretilen yapılandırılmış tür açıklaması (11.3.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layout: Summary
    headings: Annotated[
        tuple[Heading, ...], Field(max_length=MAX_HEADINGS), AfterValidator(_unique_headings)
    ]
    languages: Annotated[tuple[LanguageCode, ...], AfterValidator(_unique)]
    scripts: Annotated[tuple[Script, ...], AfterValidator(_unique)]
    field_locations: Annotated[tuple[FieldLocation, ...], Field(max_length=MAX_FIELD_LOCATIONS)]
    mrz: MrzDescription | None
    side_differences: Summary | None
    # 11.8.1: kabul edilen fotoğrafların ortak görünüşü (çerçeve, arka plan, ışık); fotoğraf
    # türü olmayan belgede `null`.
    accepted_photo: Summary | None

    @model_validator(mode="after")
    def _one_location_per_field(self) -> TypeDescription:
        names = [item.field for item in self.field_locations]
        if len(set(names)) != len(names):
            raise ValueError("field_locations: her alan bir kez yazılır")
        return self


def validate_type_description(data: object) -> TypeDescription:
    """Model yanıtını (JSON metni veya çözülmüş nesne) tür açıklaması şemasına göre doğrular;
    uymayan yanıt `TypeDescriptionError` fırlatır."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    try:
        if isinstance(data, str | bytes | bytearray):
            return TypeDescription.model_validate_json(data)
        return TypeDescription.model_validate(data)
    except ValidationError as exc:
        raise TypeDescriptionError(_describe(exc)) from None


def _describe(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(part) for part in error["loc"]) or "yanıt"
        problems.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return problems
