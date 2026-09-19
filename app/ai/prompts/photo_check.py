"""Profil fotoğrafı kontrolü sistem talimatı — PRD 11.7.1, 11.7.2.

Talimat metni aynı dizindeki `photo_check.md`'dir: yapay zekâya fotoğraf türündeki bir sayfanın
görüntüsünü katalogda açık olan kurallara göre değerlendirtir (`app.ai.photo_check.PhotoCheck`).
Üç kural taşır: yalnız değerlendir, değiştirme ve kişiyi anlatma (11.7.2, CONVENTIONS §6); emin
olmadığın kurala `unsure` yaz, tahmin etme; kısa yaz.

Metin sabittir, yuvası yoktur: değerlendirilecek kurallar isteğin kullanıcı metnindedir
(`app.pipeline.analyze.build_photo_check_prompt`).
"""

from __future__ import annotations

from importlib import resources

PROMPT_RESOURCE = "photo_check.md"


def load_photo_check_instructions() -> str:
    """Paketle gelen fotoğraf kontrolü talimatının metni."""
    return resources.files(__package__).joinpath(PROMPT_RESOURCE).read_text(encoding="utf-8")
