"""Profil fotoğrafı görsel kontrolü sözleşmesi — PRD 11.7.1.

Fotoğraf türündeki (11.6.1, `PHOTO_RULE_TYPES`) bir sayfanın katalogda açık olan kurallara göre
değerlendirmesi. Her kural üç sonuçtan birini alır: `pass` (uyuyor), `fail` (açıkça uymuyor) ya da
`unsure` (görüntüden karar verilemiyor). `fail` fotoğrafı Unresolved'a gönderir, `unsure` yalnız
nottur — hüküm planındır (`app.pipeline.plan`).

Aynı şema iki yerde kullanılır:

- **Yapay zekânın yanıtı** (`validate_photo_check`): istekte sorulan kuralların her biri tam bir
  kez yanıtlanır, sorulmayan kural yanıtlanmaz. Asgari çözünürlük yapay zekâya sorulmaz; sistem
  piksel boyutunu kendisi ölçer (`app.pipeline.analyze`).
- **Sayfaya saklanan kontrol** (`pages.photo_check_json`): yanıta ölçülen kural eklenir, kurallar
  katalog sırasıyla durur.

Kurallar sayfa analizi sözleşmesiyle (§8.4, `app.ai.schemas`) aynı ölçüdedir: her anahtar yanıtta
bulunur, tanımsız anahtar reddedilir, tip zorlanmaz, yanıt düzeltilmez (`PhotoCheckError`). Not
kısadır ve kişiye ait değer taşımaz; hata mesajına yanıttaki değer konmaz (CONVENTIONS §6).
"""

from __future__ import annotations

import enum
from collections.abc import Collection
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

RuleId = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
Note = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)
]


class PhotoRuleResult(enum.StrEnum):
    """Bir kuralın değerlendirmesi (11.7.1)."""

    PASS = "pass"
    FAIL = "fail"
    UNSURE = "unsure"


class PhotoCheckError(ValueError):
    """Fotoğraf kontrolü yanıtı şemaya uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            "Fotoğraf kontrolü yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems)
        )


class PhotoRuleVerdict(BaseModel):
    """Tek kuralın sonucu; `rule` katalogdaki kural kimliğidir (`face_visible`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: RuleId
    result: PhotoRuleResult
    note: Note | None


class PhotoCheck(BaseModel):
    """Fotoğrafın kurallara göre değerlendirmesi; her kural bir kez."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rules: Annotated[tuple[PhotoRuleVerdict, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _one_verdict_per_rule(self) -> PhotoCheck:
        names = [verdict.rule for verdict in self.rules]
        if len(set(names)) != len(names):
            raise ValueError("rules: her kural bir kez yazılır")
        return self

    def verdict(self, rule: str) -> PhotoRuleVerdict | None:
        """`rule`'un sonucu; kural değerlendirilmediyse `None`."""
        return next((verdict for verdict in self.rules if verdict.rule == rule), None)


def validate_photo_check(data: object, *, rules: Collection[str]) -> PhotoCheck:
    """Model yanıtını (JSON metni veya çözülmüş nesne) şemaya ve sorulan kurallara göre doğrular.

    `rules` istekte sorulan kural kimlikleridir: her biri yanıtta tam bir kez bulunmalı, başka kural
    bulunmamalı. Uymayan yanıt `PhotoCheckError` fırlatır.
    """
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    try:
        if isinstance(data, str | bytes | bytearray):
            check = PhotoCheck.model_validate_json(data)
        else:
            check = PhotoCheck.model_validate(data)
    except ValidationError as exc:
        raise PhotoCheckError(_describe(exc)) from None
    asked = set(rules)
    answered = {verdict.rule for verdict in check.rules}
    problems: list[str] = []
    missing = [rule for rule in rules if rule not in answered]
    if missing:
        problems.append(f"rules: sorulan kural yanıtta yok: {', '.join(missing)}")
    extra = len(answered - asked)
    if extra:
        # Sorulmayan kural kimliği yanıttan gelir; mesaja konmaz, yalnız sayısı yazılır.
        problems.append(f"rules: sorulmayan {extra} kural yanıtlandı")
    if problems:
        raise PhotoCheckError(problems)
    return check


def _describe(exc: ValidationError) -> list[str]:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        where = ".".join(str(part) for part in error["loc"]) or "yanıt"
        problems.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return problems
