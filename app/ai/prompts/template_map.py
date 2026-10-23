"""Şablon inceleme sistem talimatı — PRD 15.1.2 (PLAN.md §D123 c).

Talimat metni aynı dizindeki `template_map.md`'dir: yapay zekâya hazır şablonun bütün sayfa
görüntülerinden alan haritası (`app.ai.schemas.TemplateFieldMap`, §8.7) yazdırır. Kurallar: sabit
metni okuyup yeniden üretme; yalnız gerçekten boş bırakılmış yeri `text`/`date` alanı say; imza,
kaşe/mühür, logo, fotoğraf ve çerçeveyi `kind` ile işaretle, onlara `source` verme (emin değilsen
`signature`); boşluğu §8.7 `source` listesine bağla, emin değilsen `unassigned`; `label_text`
dışında belgeden metin taşıma; `notes` İngilizce (10.10.6).

Metin sabittir, yuvası yoktur: şablona özgü bilgiler (sayfa sayısı, görüntülerin sırası) isteğin
kullanıcı metnindedir (`app.output_templates.examine.build_map_prompt`).
"""

from __future__ import annotations

from importlib import resources

PROMPT_RESOURCE = "template_map.md"


def load_template_map_instructions() -> str:
    """Paketle gelen şablon inceleme talimatının metni."""
    return resources.files(__package__).joinpath(PROMPT_RESOURCE).read_text(encoding="utf-8")
