"""Telegram mesajının okunması sözleşmesi — PRD 12.3.1, 12.3.2, 12.3.4–12.3.7, 12.1.12.

İK'nın bota yazdığı serbest metin ("Ahmet Çakar'ın ehliyetini göster") yapay zekâya bir kez
verilir; yanıt bu şemadadır ve isteğin karşılığı olan **tek araç çağrısıdır** (`QueryIntent`):

- `find_documents` — çalışanın belgesini bul ve gönder ("göster", "var mı", "yüklemiş mi").
  `documents` istenen türlerdir: her öğe bir türün mesajdaki adı (`kind`, "ehliyet") ve ona
  karşılık gelen katalog türleri (`types`, slug; karşılığı yoksa boş). Tür söylenmediyse boş liste.
  "Ehliyet ve CV" iki öğedir (12.3.4).
- `employee_info` — çalışanın bilgisini sor ("kaç yaşında", "hangi belgeleri var") (12.3.6).
- `missing_documents` — çalışanın bir süreç için eksik belgelerini sor (12.3.7). `group` sürecin
  mesajdaki adı ("adres kaydı"; söylenmediyse `null`), `group_ids` ona karşılık gelen belge
  grupları (istemdeki listeden; karşılığı yoksa boş).
- `other` — mesaj bunlardan biri değil (selam, belgeyi değiştirme ya da silme isteği…).

`people` mesajda adı geçen kişilerdir, çekim ekleri atılmış ("Ahmet Çakar"; çalışan numarası
yazılmışsa o da, "E0001"). Kişi yazılmamışsa boştur; sistem o zaman aynı sohbetteki önceki kişiyi
kullanır (12.3.5) — yapay zekâ kişi uydurmaz. `language` mesajın yazıldığı dildir (`tr`, `en`,
`sr`; anlaşılamazsa `null`); bot o dilde yanıt verir (12.1.12).

Yapay zekâ veritabanını görmez: kişiyi, türü ve süreci yalnız mesajdan okur, türü ve grubu
istekteki listelerle eşler. Çalışanı aramak, seçim sormak, belgeyi göndermek ve özet yazmak
deterministik koddur (`app.telegram.intent`); bu yanıt yalnız aramanın girdisidir.

Kurallar öteki sözleşmelerle aynı ölçüdedir: her anahtar yanıtta bulunur, tanımsız anahtar
reddedilir, tip zorlanmaz, yanıt düzeltilmez (`DocumentQueryError`). Tutarsız yanıt da reddedilir —
niyetin taşımadığı alan dolu, tekrarlanan tür adı, slug ya da grup, katalog ya da grup listesi
dışı değer: yanlış okunmuş bir isteğe göre belge aranmaz. Yanıt mesajdan gelen adları taşır; hata
mesajına yanıttaki değer konmaz (CONVENTIONS §6).
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
MAX_DOCUMENT_KINDS = 5
"""Tek mesajda istenen en çok belge türü (12.3.4; botun liste sınırı, `app.telegram.plain`)."""

PersonText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)
]
KindText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
]
Slug = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
GroupId = Annotated[int, Field(strict=True, ge=1)]


class QueryIntent(enum.StrEnum):
    """Mesajın karşılığı olan araç (12.3.1, 12.3.6, 12.3.7)."""

    FIND_DOCUMENTS = "find_documents"
    EMPLOYEE_INFO = "employee_info"
    MISSING_DOCUMENTS = "missing_documents"
    OTHER = "other"


class ReplyLanguage(enum.StrEnum):
    """Mesajın yazıldığı dil (12.1.12); botun desteklediği arayüz dilleri."""

    TR = "tr"
    EN = "en"
    SR = "sr"


class DocumentQueryError(ValueError):
    """Belge isteği yanıtı şemaya uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            "Belge isteği yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems)
        )


class RequestedKind(BaseModel):
    """İstenen bir belge türü: mesajdaki adı ve katalogdaki karşılıkları (12.3.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: KindText
    types: tuple[Slug, ...]

    @model_validator(mode="after")
    def _unique(self) -> RequestedKind:
        if len(set(self.types)) != len(self.types):
            raise ValueError("types: her tür bir kez yazılır")
        return self


class DocumentQuery(BaseModel):
    """İK mesajının araç çağrısı: kimin, ne istendi, mesaj hangi dilde."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: QueryIntent
    people: Annotated[tuple[PersonText, ...], Field(max_length=MAX_PEOPLE)]
    documents: Annotated[tuple[RequestedKind, ...], Field(max_length=MAX_DOCUMENT_KINDS)]
    group: KindText | None
    group_ids: tuple[GroupId, ...]
    language: ReplyLanguage | None

    @model_validator(mode="after")
    def _consistent(self) -> DocumentQuery:
        kinds = [item.kind.casefold() for item in self.documents]
        if len(set(kinds)) != len(kinds):
            raise ValueError("documents: her tür adı bir kez yazılır")
        if len(set(self.group_ids)) != len(self.group_ids):
            raise ValueError("group_ids: her grup bir kez yazılır")
        if self.group is None and self.group_ids:
            raise ValueError("group_ids: group null iken grup yazılmaz")
        if self.intent is not QueryIntent.FIND_DOCUMENTS and self.documents:
            raise ValueError("documents: yalnız 'find_documents' yanıtında dolu")
        if self.intent is not QueryIntent.MISSING_DOCUMENTS and self.group is not None:
            raise ValueError("group: yalnız 'missing_documents' yanıtında dolu")
        if self.intent is QueryIntent.OTHER and self.people:
            raise ValueError("people: 'other' yanıtında boş")
        return self

    @property
    def document_types(self) -> tuple[str, ...]:
        """İstenen bütün katalog türleri, ilk görülme sırasıyla."""
        return tuple(dict.fromkeys(slug for item in self.documents for slug in item.types))


def validate_document_query(
    data: object, *, known_slugs: Iterable[str], known_groups: Iterable[int] = ()
) -> DocumentQuery:
    """Model yanıtını (JSON metni veya çözülmüş nesne) şemaya göre doğrular.

    `known_slugs` istekte verilen kataloğun slug'larıdır; `documents`'taki her slug bunlardan biri
    olmalı. `known_groups` istekteki belge gruplarının kimlikleridir; `group_ids` bunlardan olmalı.
    Uymayan yanıt `DocumentQueryError` fırlatır.
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
    problems: list[str] = []
    known = frozenset(known_slugs)
    unknown = sum(1 for item in query.documents for slug in item.types if slug not in known)
    if unknown:
        # Slug yanıttan gelir ve mesajdaki bir adı taşıyabilir; mesaja yalnız sayısı yazılır.
        problems.append(f"documents: katalogda olmayan {unknown} tür")
    groups = frozenset(known_groups)
    stray = sum(1 for group_id in query.group_ids if group_id not in groups)
    if stray:
        problems.append(f"group_ids: listede olmayan {stray} grup")
    if problems:
        raise DocumentQueryError(problems)
    return query


def _describe(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(part) for part in error["loc"]) or "yanıt"
        problems.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return problems
