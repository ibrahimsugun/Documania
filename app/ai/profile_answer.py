"""Telegram'da profil sorusunun yanıtı sözleşmesi — PRD 12.3.8 (PLAN.md §D110).

İK bota bir ya da birkaç çalışan hakkında soru sorar ("Mehmet ile Ayşe'den hangisi daha yaşlı?",
"Mehmet'in pasaportunun bitiş tarihi ne?"). Kişileri sistem deterministik bulur (`app.telegram
.intent`); yapay zekâya yalnız o kişilerin `profil.md` içeriği (`app.profiles.render_profile`) ve
soru gider. Model yalnız bu profillerden yanıt verir, uydurmaz; yanıt tek alanlı bir araç
çağrısıdır (`answer`). Kurallar öteki sözleşmelerle aynıdır: her anahtar bulunur, tanımsız anahtar
reddedilir, tip zorlanmaz (`ProfileAnswerError`); hata mesajına yanıttaki değer konmaz.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

MAX_ANSWER_LENGTH = 1500
"""Yanıtın en çok karakteri; bot mesajı kısa olmalı (12.1.9)."""
MAX_COMPARED_PEOPLE = 5
"""Bir soruda profili verilen en çok kişi."""

AnswerText = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=MAX_ANSWER_LENGTH
    ),
]


class ProfileAnswerError(ValueError):
    """Profil yanıtı şemaya uymadı; `problems` her ihlal için bir satır taşır."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Profil yanıtı reddedildi:\n" + "\n".join(f"- {p}" for p in problems))


class ProfileAnswer(BaseModel):
    """Profillerden yazılmış kısa yanıt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: AnswerText


def validate_profile_answer(data: object) -> ProfileAnswer:
    """Model yanıtını (JSON metni veya çözülmüş nesne) doğrular; uymazsa `ProfileAnswerError`."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    try:
        if isinstance(data, str | bytes | bytearray):
            return ProfileAnswer.model_validate_json(data)
        return ProfileAnswer.model_validate(data)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(part) for part in error['loc']) or 'yanıt'}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False, include_context=False)
        ]
        raise ProfileAnswerError(problems) from None
