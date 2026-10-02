"""Derlenmiş çeviri kataloglarının yüklenmesi (PRD 10.10.3; PLAN.md §D92 e).

Kataloglar paket verisidir: `app/i18n/locales/<dil>/LC_MESSAGES/messages.mo`. Çalışma zamanında
derleme yapılmaz; `.mo` dosyası `python -m app.i18n compile` ile üretilip depoya girer. Her dilin
kataloğu süreç başına bir kez okunur. Kaynak dil (Türkçe) kataloksuzdur: metin msgid'in kendisidir.
"""

from __future__ import annotations

import gettext
import io
from functools import cache
from pathlib import Path

from app.i18n.languages import SOURCE_LANGUAGE, is_supported

DOMAIN = "messages"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"


def po_path(code: str, locales_dir: Path = LOCALES_DIR) -> Path:
    return locales_dir / code / "LC_MESSAGES" / f"{DOMAIN}.po"


def mo_path(code: str, locales_dir: Path = LOCALES_DIR) -> Path:
    return locales_dir / code / "LC_MESSAGES" / f"{DOMAIN}.mo"


@cache
def load_translations(code: str) -> gettext.NullTranslations:
    """`code` dilinin kataloğu. Kataloğu olması gereken dilin `.mo` dosyası yoksa hata verir:
    sessizce Türkçeye düşmek paketleme hatasını gizlerdi."""
    if not is_supported(code):
        raise ValueError(f"desteklenmeyen dil: {code!r}")
    if code == SOURCE_LANGUAGE:
        return gettext.NullTranslations()
    return gettext.GNUTranslations(io.BytesIO(mo_path(code).read_bytes()))
