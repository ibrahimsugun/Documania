"""Botun sade dili: yasak sözcükler ve biçim denetimi (PRD 12.1.9; PLAN.md §D98).

Botun okuru teknik bilgisi olmayan bir İK çalışanıdır: siz diliyle, günlük sözcükle, kısa cümle.
Bot metinleri bu modüldeki kurallardan geçer; kuralların kendisi de yalnız buradadır (testler
`problems`'ı her bot metnine ve üretilen örnek mesajlara uygular).

- **Yasak sözcükler** (`FORBIDDEN_WORDS`, dil başına): parti, kuyruk, kuyruk adları, aşama, yapay
  zekâ, sağlayıcı, işleyici, katalog, eşik, plan ve karşılıkları; büyüklük birimleri (MB/KB/GB).
- **Yasak biçimler**: uuid biçimli dizgi, `E` + rakam çalışan numarası, `%`, hata/istisna adı.
- **Biçim sınırı** (§D98 b): liste (`• ` ile başlayan satır) dışında en çok `MAX_LINES` satır,
  listede en çok `MAX_ITEMS` öğe. Boş satır sayılmaz.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType

MAX_LINES = 4
MAX_ITEMS = 5
BULLET = "• "

_COMMON = ("unknown", "unreadable", "unresolved", "MB", "KB", "GB")
FORBIDDEN_WORDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "tr": (
            "parti",
            "partisi",
            "kuyruk",
            "kuyruğa",
            "kuyrukta",
            "kuyruklar",
            "aşama",
            "yapay zekâ",
            "yapay zeka",
            "sağlayıcı",
            "işleyici",
            "katalog",
            "katalogdaki",
            "eşik",
            "eşiğ",
            "plan",
            *_COMMON,
        ),
        "en": (
            "batch",
            "queue",
            "queued",
            "stage",
            "AI",
            "provider",
            "worker",
            "catalog",
            "catalogue",
            "threshold",
            "plan",
            *_COMMON,
        ),
        "sr": (
            "serija",
            "seriju",
            "seriji",
            "red",
            "redu",
            "redovi",
            "faza",
            "AI",
            "veštačka inteligencija",
            "dobavljač",
            "obrađivač",
            "proces",
            "katalog",
            "katalogu",
            "prag",
            "plan",
            *_COMMON,
        ),
    }
)

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_EMPLOYEE_NUMBER = re.compile(r"(?<![A-Za-z0-9])E\d+")
_UPLOAD_ID = re.compile(r"\bu_\d{8}_\d+\b")
_EXCEPTION = re.compile(r"\b[A-Z][A-Za-z]*(Error|Exception)\b")


# Türkçe ve İngilizcede yasak sözcük ekiyle de yakalanır (kökle başlayan sözcük: "sağlayıcısı",
# "batches"); Sırpçada çekimli biçimler listededir ve sözcük tam eşleşir ("red", "redovno"yu
# yakalamasın).
_PREFIX_LANGUAGES = frozenset({"tr", "en"})


def _word(word: str, *, prefix: bool) -> re.Pattern[str]:
    # Sözcük sınırı Türkçe/Sırpça harfleri de harf sayar; büyüklük birimleri ve "AI" büyük
    # harfle ve tam sözcük olarak aranır (küçük "ai" başka sözcüğün parçası olabilir).
    upper = word.isupper()
    flags = 0 if upper else re.IGNORECASE
    end = "" if prefix and not upper else r"(?![^\W\d_])"
    return re.compile(rf"(?<![^\W\d_]){re.escape(word)}{end}", flags)


_PATTERNS: Mapping[str, tuple[tuple[str, re.Pattern[str]], ...]] = MappingProxyType(
    {
        language: tuple((word, _word(word, prefix=language in _PREFIX_LANGUAGES)) for word in words)
        for language, words in FORBIDDEN_WORDS.items()
    }
)


def forbidden_words(text: str, language: str) -> list[str]:
    """Metinde geçen yasak sözcükler (`language` dilinin listesi)."""
    return [word for word, pattern in _PATTERNS[language] if pattern.search(text)]


def problems(text: str, language: str) -> list[str]:
    """Metnin sade dil kurallarına uymayan yanları; boş liste = uygun."""
    found = [f"yasak sözcük: {word}" for word in forbidden_words(text, language)]
    if _UUID.search(text) or _UPLOAD_ID.search(text):
        found.append("parti numarası")
    if _EMPLOYEE_NUMBER.search(text):
        found.append("çalışan numarası")
    if "%" in text:
        found.append("yüzde işareti")
    if _EXCEPTION.search(text):
        found.append("hata adı")
    lines = [line for line in text.splitlines() if line.strip()]
    items = [line for line in lines if line.startswith(BULLET)]
    if len(lines) - len(items) > MAX_LINES:
        found.append(f"liste dışı {len(lines) - len(items)} satır (en çok {MAX_LINES})")
    if len(items) > MAX_ITEMS:
        found.append(f"listede {len(items)} öğe (en çok {MAX_ITEMS})")
    return found


__all__ = ["BULLET", "FORBIDDEN_WORDS", "MAX_ITEMS", "MAX_LINES", "forbidden_words", "problems"]
