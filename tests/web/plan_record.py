"""PLAN.md §C/§D maddelerini okuyan testlerin ortak yardımcısı (CONVENTIONS §1.2, §3).

Eski maddeler `scripts/arsiv-dondur.mjs` ile `docs/archive/plan-kanit/` altına taşınır; metni karar
kaydına bağlı testler maddeyi önce canlı PLAN.md'de, yoksa arşivde arar. `plan_record("D58")`
maddenin boşlukları teke indirilmiş metnini döner.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "PLAN.md"
ARCHIVE = ROOT / "docs" / "archive" / "plan-kanit"


def plan_record(code: str) -> str:
    start = f"- **{code} —"
    for path in [PLAN, *sorted(ARCHIVE.glob("*.md"), reverse=True)]:
        text = path.read_text(encoding="utf-8")
        begin = text.find(start)
        if begin == -1:
            continue
        end = text.find("\n- **", begin + len(start))
        return " ".join(text[begin : end if end != -1 else len(text)].split())
    raise AssertionError(f"PLAN maddesi bulunamadı: {code}")
