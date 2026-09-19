"""Tür açıklaması sistem talimatı — PRD 11.3.1.

Talimat metni aynı dizindeki `type_description.md`'dir: yapay zekâya bir belge türünün örnek
sayfalarından yapılandırılmış açıklama (`app.ai.type_description.TypeDescription`) yazdırır. Üç
kural taşır: türü anlat kişiyi değil (örnekteki kişisel değer açıklamaya girmez), kısa yaz (açıklama
katalog metninin token bütçesini paylaşır, 11.4.2), serbest metin Türkçe ve basılı başlık aslıyla.

Metin sabittir, yuvası yoktur: türe özgü bilgiler (ad, ülke, yüz yapısı, zorunlu alanlar,
görüntülerin sırası) isteğin kullanıcı metnindedir (`app.catalog.describe`).
"""

from __future__ import annotations

from importlib import resources

PROMPT_RESOURCE = "type_description.md"


def load_type_description_instructions() -> str:
    """Paketle gelen tür açıklaması talimatının metni."""
    return resources.files(__package__).joinpath(PROMPT_RESOURCE).read_text(encoding="utf-8")
