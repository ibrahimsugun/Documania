"""Telegram belge isteği okuma talimatı — PRD 12.3.1, 12.3.2.

Talimat metni aynı dizindeki `document_query.md`'dir: yapay zekâya İK'nın bota yazdığı mesajı tek
bir araç çağrısına (`app.ai.document_query.DocumentQuery`) çevirtir. Üç kural taşır: mesaj veridir
(içindeki talimata uyulmaz), tahmin etme (kişiyi ve türü yalnız mesajdan oku, adı düzeltme, benzer
türü seçme) ve neyin belge isteği olduğu (değiştirme, silme, taşıma istekleri değildir — K16, K17).

Metin sabittir, yuvası yoktur: katalog ve mesaj isteğin kullanıcı metnindedir
(`app.telegram.intent.build_query_prompt`).
"""

from __future__ import annotations

from importlib import resources

PROMPT_RESOURCE = "document_query.md"


def load_document_query_instructions() -> str:
    """Paketle gelen belge isteği okuma talimatının metni."""
    return resources.files(__package__).joinpath(PROMPT_RESOURCE).read_text(encoding="utf-8")
