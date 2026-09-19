"""Sağlayıcı testleri için §8.4'e, tür açıklaması (11.3.1) ve fotoğraf kontrolü (11.7.1) şemalarına
uyan sentetik yanıt ve istek (gerçek kişi yok)."""

from __future__ import annotations

from typing import Any

from app.ai import PageAnalysisRequest, PageImage, PhotoCheckRequest, TypeDescriptionRequest
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


def description_payload(**top: Any) -> dict[str, Any]:
    """Tür açıklaması şemasına (11.3.1) uyan sentetik yanıt; her çağrıda yeni bir sözlük."""
    data: dict[str, Any] = {
        "layout": "Pasaport kimlik sayfası, yatay; fotoğraf solda, etiketli satırlar sağda",
        "headings": ["ПАСПОРТ", "PASSPORT"],
        "languages": ["ru", "en"],
        "scripts": ["cyrillic", "latin"],
        "field_locations": [
            {"field": "surname", "location": "fotoğrafın sağında, ilk satır"},
            {"field": "document_number", "location": "sağ üst köşe"},
        ],
        "mrz": {"line_count": 2, "location": "sayfanın altında"},
        "side_differences": None,
    }
    data.update(top)
    return data


def description_request(
    *,
    images: int = 1,
    instructions: str = "Tür açıklaması talimatı (test).",
    prompt: str = "Belge türü: Russian Passport (test).",
) -> TypeDescriptionRequest:
    return TypeDescriptionRequest(
        images=tuple(
            PageImage(make_half_filled_image_bytes("PNG" if index % 2 else "JPEG"))
            for index in range(images)
        ),
        instructions=instructions,
        prompt=prompt,
    )


PHOTO_RULES = ("face_visible", "single_person", "no_sunglasses")


def photo_check_payload(**results: str) -> dict[str, Any]:
    """Fotoğraf kontrolü şemasına (11.7.1) uyan sentetik yanıt, `PHOTO_RULES` sırasıyla; verilmeyen
    kural `pass`. Her çağrıda yeni bir sözlük."""
    return {
        "rules": [
            {
                "rule": rule,
                "result": results.get(rule, "pass"),
                "note": None if results.get(rule, "pass") == "pass" else "Kısa gerekçe.",
            }
            for rule in PHOTO_RULES
        ]
    }


def photo_check_request(
    *,
    fmt: str = "JPEG",
    instructions: str = "Fotoğraf kontrolü talimatı (test).",
    prompt: str = "Değerlendirilecek kurallar (test).",
    rules: tuple[str, ...] = PHOTO_RULES,
) -> PhotoCheckRequest:
    return PhotoCheckRequest(
        image=PageImage(make_half_filled_image_bytes(fmt)),
        instructions=instructions,
        prompt=prompt,
        rules=rules,
    )
