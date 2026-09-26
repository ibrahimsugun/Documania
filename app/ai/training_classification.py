"""Eğitim sınıflandırması sözleşmesi — PRD 11.9.3 (PLAN.md §C86 "Yapay zekâ yolu").

Eğitim modunda mekanik tanınmayan (11.9.2) bir belgenin ilk sayfası (PDF'te ilk iki sayfası) yapay
zekâya gösterilir; yanıt bu şemadadır ve yalnız **belgenin türünü** anlatır:

- `catalog_slug` — belge istemdeki katalog türlerinden biriyse onun slug'ı; değilse `null`.
- `country_iso3` — belgeyi veren ülke: ISO 3166-1 alfa-3 (Kosova `XKX`) ya da önerilen tür
  kaydının bölge kodları (`REGION_CODES`: AB `EU`, uluslararası `INT`, KKTC `KKTC`); bilinmiyorsa
  `null`.
- `doc_kind` — belgenin türü, önerilen tür kaydının kapalı `kaynak_tur` sözlüğünden (`pasaport`,
  `kimlik_karti`, `ehliyet` …; istekte verilir); sözlükte karşılığı yoksa `null`.
- `proposed_name` — belgenin İngilizce tür adı, "<Ülke sıfatı> <Tür>" ("Albanian Passport");
  bilinmiyorsa `null`.
- `side` — görülen yüz (`app.ai.schemas.Side`).
- `notes` — kısa gerekçe (en çok `MAX_NOTES_LENGTH` karakter, boş olabilir).

Kişisel alan yoktur ve istenmez: sınıflandırma kimin belgesi olduğunu değil, hangi tür belge
olduğunu söyler. Sayfa analizi (`app.ai.schemas.PageAnalysis`, §8.4) burada kullanılmaz — katalog
dışı slug'ı reddeder ve kişisel değer döndürür; eğitim yolu ise katalog dışındaki hazır önerilen
türleri de tanır ve hiçbir kişisel değer okumaz (§C86 kapsam sınırı).

Kurallar öteki sözleşmelerle aynı ölçüdedir: her anahtar yanıtta bulunur, tanımsız anahtar
reddedilir, tip zorlanmaz, yanıt düzeltilmez (`TrainingClassificationError`). İstemdeki katalog
dışında bir `catalog_slug` ya da sözlük dışında bir `doc_kind` da reddedilir. Bu yanıttan türe
yerleştirme deterministik koddur (`app.training.classification`); yanıt yalnız girdisidir.

Hata mesajlarına yanıttaki değer konmaz (CONVENTIONS §6).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from app.ai.schemas import Side

MAX_NOTES_LENGTH = 200
"""`notes`'un en çok karakter sayısı."""

MAX_PROPOSED_NAME_LENGTH = 80
"""`proposed_name`'in en çok karakter sayısı (önerilen tür kaydının en uzun adı 44 karakterdir)."""

REGION_CODES = ("EU", "INT", "KKTC")
"""ISO 3166-1 alfa-3 olmayan ülke kodları: önerilen tür kaydı AB belgelerini `EU`, uluslararası
belgeleri `INT`, KKTC belgelerini `KKTC` ile yazar."""

Slug = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
CountryIso3 = Annotated[
    str, StringConstraints(strict=True, pattern=rf"^(?:[A-Z]{{3}}|{'|'.join(REGION_CODES)})$")
]
DocKind = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
]
ProposedName = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=MAX_PROPOSED_NAME_LENGTH
    ),
]
Notes = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, max_length=MAX_NOTES_LENGTH)
]


class TrainingClassificationError(ValueError):
    """Eğitim sınıflandırması yanıtı şemaya uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            "Eğitim sınıflandırması yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems)
        )


class TrainingClassification(BaseModel):
    """Eğitim öğesinin türü hakkında yapay zekânın yanıtı (11.9.3); kişisel alan taşımaz."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_slug: Slug | None
    country_iso3: CountryIso3 | None
    doc_kind: DocKind | None
    proposed_name: ProposedName | None
    side: Side
    notes: Notes


def validate_training_classification(
    data: object, *, known_slugs: Iterable[str], doc_kinds: Iterable[str]
) -> TrainingClassification:
    """Model yanıtını (JSON metni veya çözülmüş nesne) şemaya göre doğrular.

    `known_slugs` istemdeki katalog türlerinin slug'larıdır: `catalog_slug` bunlardan biri olmalı.
    `doc_kinds` istemdeki tür sözlüğüdür: `doc_kind` bunlardan biri olmalı. Uymayan yanıt
    `TrainingClassificationError` fırlatır.
    """
    if isinstance(data, BaseModel):
        # Hazır örnek pydantic'te yeniden doğrulanmaz; katalog ve sözlük denetimi atlanmasın.
        data = data.model_dump(mode="json")
    try:
        if isinstance(data, str | bytes | bytearray):
            classification = TrainingClassification.model_validate_json(data)
        else:
            classification = TrainingClassification.model_validate(data)
    except ValidationError as exc:
        raise TrainingClassificationError(_describe(exc)) from None
    problems = []
    if classification.catalog_slug is not None and classification.catalog_slug not in frozenset(
        known_slugs
    ):
        # Slug yanıttan gelir; mesaja değeri yazılmaz.
        problems.append("catalog_slug: istemdeki katalogda olmayan tür")
    if classification.doc_kind is not None and classification.doc_kind not in frozenset(doc_kinds):
        problems.append("doc_kind: tür sözlüğünde olmayan değer")
    if problems:
        raise TrainingClassificationError(problems)
    return classification


def _describe(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(part) for part in error["loc"]) or "yanıt"
        problems.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return problems
