"""Telegram belge isteğinin okunması sözleşmesi — PRD 12.3.1, 12.3.2.

İK'nın bota yazdığı serbest metin ("Ahmet Çakar'ın ehliyetini göster") yapay zekâya bir kez
verilir; yanıt bu şemadadır ve isteğin karşılığı olan **tek araç çağrısıdır** (`QueryIntent`):

- `find_documents` — bir çalışanın belgesini bul ve gönder. `people` belgesi istenen kişiler,
  mesajda yazıldığı gibi ama çekim ekleri atılmış ("Ahmet Çakar"; çalışan numarası yazılmışsa o da,
  "E0001"); `document_kind` istenen belgenin mesajdaki adı ("ehliyet"; tür söylenmediyse `null`);
  `document_types` o ada karşılık gelen katalog türleri (slug; karşılığı yoksa boş).
- `other` — mesaj belge isteği değil (selam, soru, belgeyi değiştirme ya da silme isteği…); öteki
  alanlar boştur.

Yapay zekâ veritabanını görmez: kişiyi ve türü yalnız mesajdan okur, türü istekteki katalog
listesiyle eşler. Çalışanı aramak, sonuç birden çoksa seçim sormak ve belgeyi göndermek
deterministik koddur (`app.telegram.intent`); bu yanıt yalnız aramanın girdisidir.

Kurallar öteki sözleşmelerle aynı ölçüdedir: her anahtar yanıtta bulunur, tanımsız anahtar
reddedilir, tip zorlanmaz, yanıt düzeltilmez (`DocumentQueryError`). Tutarsız yanıt da reddedilir —
`other` yanıtında kişi ya da tür, tür adı olmadan tür, tekrarlanan ya da katalog dışı slug: yanlış
okunmuş bir isteğe göre belge aranmaz. Yanıt mesajdan gelen adları taşır; hata mesajına yanıttaki
değer konmaz (CONVENTIONS §6).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

MAX_PEOPLE = 10
"""Bir yanıttaki en çok kişi sayısı; sistem zaten tek kişilik isteği yürütür."""

PersonText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)
]
KindText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
]
Slug = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]


class QueryIntent(enum.StrEnum):
    """Mesajın karşılığı olan araç (12.3.1)."""

    FIND_DOCUMENTS = "find_documents"
    OTHER = "other"


class DocumentQueryError(ValueError):
    """Belge isteği yanıtı şemaya uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            "Belge isteği yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems)
        )


class DocumentQuery(BaseModel):
    """İK mesajının araç çağrısı: kimin, hangi tür belgesi istendi ya da mesaj istek değil."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: QueryIntent
    people: Annotated[tuple[PersonText, ...], Field(max_length=MAX_PEOPLE)]
    document_kind: KindText | None
    document_types: tuple[Slug, ...]

    @model_validator(mode="after")
    def _consistent(self) -> DocumentQuery:
        if len(set(self.document_types)) != len(self.document_types):
            raise ValueError("document_types: her tür bir kez yazılır")
        if self.document_kind is None and self.document_types:
            raise ValueError("document_types: document_kind null iken tür yazılmaz")
        if self.intent is QueryIntent.OTHER and (
            self.people or self.document_kind is not None or self.document_types
        ):
            raise ValueError(
                "intent: 'other' yanıtında people, document_kind ve document_types boş"
            )
        return self


def validate_document_query(data: object, *, known_slugs: Iterable[str]) -> DocumentQuery:
    """Model yanıtını (JSON metni veya çözülmüş nesne) şemaya göre doğrular.

    `known_slugs` istekte verilen kataloğun slug'larıdır; `document_types`'taki her slug bunlardan
    biri olmalı. Uymayan yanıt `DocumentQueryError` fırlatır.
    """
    if isinstance(data, BaseModel):
        # Hazır örnek pydantic tarafından yeniden doğrulanmaz; katalog denetimi atlanmasın.
        data = data.model_dump(mode="json")
    try:
        if isinstance(data, str | bytes | bytearray):
            query = DocumentQuery.model_validate_json(data)
        else:
            query = DocumentQuery.model_validate(data)
    except ValidationError as exc:
        raise DocumentQueryError(_describe(exc)) from None
    known = frozenset(known_slugs)
    unknown = sum(1 for slug in query.document_types if slug not in known)
    if unknown:
        # Slug yanıttan gelir ve mesajdaki bir adı taşıyabilir; mesaja yalnız sayısı yazılır.
        raise DocumentQueryError([f"document_types: katalogda olmayan {unknown} tür"])
    return query


def _describe(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(part) for part in error["loc"]) or "yanıt"
        problems.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return problems
