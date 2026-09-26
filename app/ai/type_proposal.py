"""Tür taslağı sözleşmesi — PRD 11.5.5 (PLAN §C85 "Sözleşme").

Katalog dışı bir aday türün (04.6.1) örnek sayfalarından yapay zekâya ürettirilen **tam katalog
kaydı taslağı**: Belge türü formunun (§8.6, 11.1.2) doldurulacak bütün alanları. Taslak İK'ya onay
formunda önerilir; kendiliğinden kataloğa girmez (tm 113 saklar, tm 114 formu doldurur).

Taslak türü anlatır, belgeyi değil: örnekteki kişiye ait hiçbir değer (ad, numara, tarih) taslağın
metinlerine girmez (R3, CONVENTIONS §6). Ölçü tür açıklamasıdır (`app.ai.type_description`, 11.3.1):

- Her anahtar yanıtta bulunur (eksik anahtar varsayılanla doldurulmaz); tanımsız anahtar
  reddedilir; tipler zorlanmaz. Yanıt düzeltilmez: uymayan yanıt `TypeProposalError` ile bütün
  olarak reddedilir.
- `country` ISO 3166-1 alfa-2'dir (katalogdaki gibi, `app.catalog.schema.CountryCode`).
- `required_fields` en çok `MAX_REQUIRED_FIELDS` katalog alan adıdır (`FieldName`), tekrarsız;
  `acceptance_criteria` en çok `MAX_ACCEPTANCE_CRITERIA` kısa Türkçe maddedir.
- `appearance` tür açıklamasının kendisidir (`TypeDescription`; katalogda `prompt_description`
  metnine `app.catalog.describe.format_description` çevirir). Yeri yazılan alan
  (`field_locations`) taslağın zorunlu alanlarından biri olmalıdır.
- `name` ve `file_label` dosya adına çevrilebilmelidir (K8; katalog kaydının `file_label`
  kuralı).

Alanlar arası katalog tutarlılığı (Direkt Belge'de dönüşüm yok, yüz yapısından türeyen sayfa
aralığı — `CatalogEntry.consistency_problems`) burada denetlenmez: dosya türü ve yüz yapısını
gözlenen örnekler ezer (tm 113), formu kuran adım her alanı `build_entry` ile sınar ve tutmayan
alanı boş bırakır (tm 114). Tek tutarsız alan yüzünden bütün taslak kaybolmaz.

Hata mesajlarına yanıttaki değer konmaz: örnek belge üzerindeki kişisel değer yanıta sızmışsa loga
ve ekrana taşınmaz (CONVENTIONS §6).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.ai.type_description import TypeDescription
from app.catalog.schema import (
    Conversion,
    CountryCode,
    FieldName,
    FileType,
    FrontBackLayout,
    OutputFormat,
    PageRange,
    Sides,
)
from app.storage import SlugError, slugify

MAX_REQUIRED_FIELDS = 10
"""En çok kaç zorunlu alan önerilir."""

MAX_ACCEPTANCE_CRITERIA = 5
"""En çok kaç kabul kriteri önerilir."""

STANDARD_FIELDS = (
    "surname",
    "given_names",
    "date_of_birth",
    "document_number",
    "nationality",
    "expiry_date",
    "issue_date",
    "place_of_birth",
    "personal_number",
    "issuing_authority",
)
"""Talimattaki standart alan sözlüğü: MRZ alanları (`app.matching.mrz.MRZ_FIELDS`) ve sık basılı
dört alan. Sözlük dışı ad yalnız gerekiyorsa yazılır; sözleşme adı `FieldName` biçimiyle sınar."""

TypeName = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80)
]
FileLabel = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=40)
]
Summary = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)
]
Criterion = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120)
]


def _unique[T](values: tuple[T, ...]) -> tuple[T, ...]:
    # Mesaj tekrarlanan değeri yazmaz (modül belgesi).
    if len(set(values)) != len(values):
        raise ValueError("listede tekrar olmamalı")
    return values


def _unique_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    _unique(tuple(value.casefold() for value in values))
    return values


def _makes_file_name(value: str) -> str:
    # K8: ad ve etiket dosya ve klasör adına girer; ad üretemeyen metin geçersiz.
    try:
        slugify(value, "-")
    except SlugError:
        raise ValueError("dosya adına çevrilemiyor") from None
    return value


class TypeProposalError(ValueError):
    """Model yanıtı tür taslağı şemasına uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Tür taslağı yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems))


class TypeProposal(BaseModel):
    """Aday türün örneklerinden üretilen tam katalog kaydı taslağı (11.5.5).

    Alanlar `CatalogEntry`'ninkilerdir (§8.6); `slug`, `photo_rules` ve `active` taslakta yoktur
    (slug addan ya da önerilen tür kaydından türer, tm 114). `appearance` `prompt_description`'ın
    yapılandırılmış hâlidir.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Annotated[TypeName, AfterValidator(_makes_file_name)]
    file_label: Annotated[FileLabel, AfterValidator(_makes_file_name)]
    country: CountryCode | None
    description: Summary
    expected_file_types: Annotated[
        tuple[FileType, ...], Field(min_length=1), AfterValidator(_unique)
    ]
    expected_pages: PageRange | None
    sides: Sides
    front_back_layouts: Annotated[tuple[FrontBackLayout, ...], AfterValidator(_unique)]
    direct: StrictBool
    analyze: StrictBool
    allowed_conversions: Annotated[tuple[Conversion, ...], AfterValidator(_unique)]
    output_format: OutputFormat
    required_fields: Annotated[
        tuple[FieldName, ...], Field(max_length=MAX_REQUIRED_FIELDS), AfterValidator(_unique)
    ]
    acceptance_criteria: Annotated[
        tuple[Criterion, ...],
        Field(max_length=MAX_ACCEPTANCE_CRITERIA),
        AfterValidator(_unique_texts),
    ]
    appearance: TypeDescription

    @model_validator(mode="after")
    def _locations_are_required_fields(self) -> TypeProposal:
        required = set(self.required_fields)
        if any(item.field not in required for item in self.appearance.field_locations):
            raise ValueError(
                "appearance.field_locations: yalnız required_fields'taki alanların yeri yazılır"
            )
        return self


def validate_type_proposal(data: object) -> TypeProposal:
    """Model yanıtını (JSON metni veya çözülmüş nesne) tür taslağı şemasına göre doğrular; uymayan
    yanıt `TypeProposalError` fırlatır."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    try:
        if isinstance(data, str | bytes | bytearray):
            return TypeProposal.model_validate_json(data)
        return TypeProposal.model_validate(data)
    except ValidationError as exc:
        raise TypeProposalError(_describe(exc)) from None


def _describe(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(part) for part in error["loc"]) or "yanıt"
        problems.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return problems
