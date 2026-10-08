"""Telegram profil sorusu yanıt talimatı — PRD 12.3.8 (PLAN.md §D110).

Talimat metni aynı dizindeki `profile_answer.md`'dir: modele yalnız verilen profillerden, kısa ve
sade, istenen dilde yanıt yazdırır; profilde olmayanı uydurtmaz.
"""

from __future__ import annotations

from importlib import resources

PROMPT_RESOURCE = "profile_answer.md"


def load_profile_answer_instructions() -> str:
    """Paketle gelen profil sorusu yanıt talimatının metni."""
    return resources.files(__package__).joinpath(PROMPT_RESOURCE).read_text(encoding="utf-8")
