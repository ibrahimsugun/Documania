"""Sağlayıcı testleri için §8.4'e uyan sentetik yanıt ve sayfa isteği (gerçek kişi yok)."""

from __future__ import annotations

from typing import Any

from app.ai import PageAnalysisRequest, PageImage
from app.catalog import load_seed_catalog
from tests.fixtures.gen import make_half_filled_image_bytes

SLUGS = load_seed_catalog().slugs()

# Kişisel veri gibi görünen ama uydurma değerler; hata mesajlarında geçmediği denetlenir.
SYNTHETIC_SURNAME = "ORNEKOVA"
SYNTHETIC_DOCUMENT_NUMBER = "00 0000001"


def analysis_payload(**top: Any) -> dict[str, Any]:
    """Her çağrıda yeni bir sözlük; `top` üst düzey anahtarları değiştirir."""
    data: dict[str, Any] = {
        "page_index": 0,
        "is_blank": False,
        "is_readable": True,
        "language": "ru",
        "script": "cyrillic",
        "document_type_slug": "russian_passport",
        "candidate_type_name": None,
        "side": "single",
        "continues_previous_page": False,
        "person": {
            "surname": SYNTHETIC_SURNAME,
            "given_names": "TEST",
            "other_names": None,
            "original_script_name": "Орнекова Тест",
            "date_of_birth": "1990-01-01",
            "nationality": "RUS",
            "document_number": SYNTHETIC_DOCUMENT_NUMBER,
            "mrz_lines": None,
            "contact": {"phone": None, "email": None, "address": None},
        },
        "fields": {
            "surname": {"value": SYNTHETIC_SURNAME, "legible": True},
            "expiry_date": {"value": None, "legible": False},
        },
        "notes": None,
    }
    data.update(top)
    return data


def page_request(
    *,
    page_index: int = 0,
    fmt: str = "JPEG",
    instructions: str = "Sistem talimatı (test).",
    prompt: str = "Sayfa 1 (test).",
    known_slugs: tuple[str, ...] = SLUGS,
) -> PageAnalysisRequest:
    return PageAnalysisRequest(
        page_index=page_index,
        image=PageImage(make_half_filled_image_bytes(fmt)),
        instructions=instructions,
        prompt=prompt,
        known_slugs=known_slugs,
    )
