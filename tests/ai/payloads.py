"""Sağlayıcı testleri için §8.4'e, tür açıklaması (11.3.1), tür taslağı (11.5.5), eğitim
sınıflandırması (11.9.3), fotoğraf kontrolü (11.7.1) ve belge isteği (12.3.1) şemalarına uyan
sentetik yanıt ve istek (gerçek kişi yok)."""

from __future__ import annotations

from typing import Any

from app.ai import (
    DocumentQueryRequest,
    PageAnalysisRequest,
    PageImage,
    PhotoCheckRequest,
    TrainingClassificationRequest,
    TypeDescriptionRequest,
    TypeProposalRequest,
)
from app.catalog import load_seed_catalog
from app.training.known_types import build_known_types
from tests.fixtures.gen import make_half_filled_image_bytes

SLUGS = load_seed_catalog().slugs()
DOC_KINDS = build_known_types(load_seed_catalog()).doc_kinds
"""Önerilen tür kaydının `kaynak_tur` sözlüğü (eğitim sınıflandırmasının kapalı kümesi)."""

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
        "accepted_photo": None,
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


def proposal_payload(**top: Any) -> dict[str, Any]:
    """Tür taslağı şemasına (11.5.5) uyan sentetik yanıt: ön ve arka yüzlü bir oturma izni kartı.
    Her çağrıda yeni bir sözlük; `top` üst düzey anahtarları değiştirir."""
    data: dict[str, Any] = {
        "name": "Montenegrin Residence Permit",
        "file_label": "Residence Permit",
        "country": "ME",
        "description": "Karadağ'da yabancılara verilen oturma izni kartı; ön ve arka yüzlü.",
        "expected_file_types": ["jpeg", "png"],
        "expected_pages": {"min": 1, "max": 2},
        "sides": "front_back",
        "front_back_layouts": ["separate", "combined"],
        "direct": False,
        "analyze": True,
        "allowed_conversions": ["merge", "wrap_image"],
        "output_format": "pdf",
        "required_fields": [
            "surname",
            "given_names",
            "date_of_birth",
            "document_number",
            "expiry_date",
        ],
        "acceptance_criteria": [
            "Kartın iki yüzü de tam görünür olmalı, kenarlar kesilmemiş",
            "Arka yüzdeki MRZ üç satırı da okunabilir olmalı",
        ],
        "appearance": description_payload(
            layout="Kart, yatay; ön yüzde fotoğraf solda, etiketli satırlar sağda",
            headings=["DOZVOLA ZA BORAVAK"],
            languages=["sr", "en"],
            scripts=["latin"],
            field_locations=[
                {"field": "surname", "location": "ön yüzde fotoğrafın sağında, ilk satır"},
                {"field": "document_number", "location": "ön yüzün sağ üst köşesi"},
            ],
            mrz={"line_count": 3, "location": "arka yüzün altında"},
            side_differences="Ön yüzde fotoğraf ve kişisel alanlar; arka yüzde MRZ",
        ),
    }
    data.update(top)
    return data


def proposal_request(
    *,
    images: int = 1,
    instructions: str = "Tür taslağı talimatı (test).",
    prompt: str = "Aday tür: Montenegrin Residence Permit (test).",
) -> TypeProposalRequest:
    # Her görüntü ayrı boyutta: baytlar farklıdır, sıra testte görünür.
    return TypeProposalRequest(
        images=tuple(
            PageImage(
                make_half_filled_image_bytes("PNG" if index % 2 else "JPEG", (200 + index, 100))
            )
            for index in range(images)
        ),
        instructions=instructions,
        prompt=prompt,
    )


def training_payload(**top: Any) -> dict[str, Any]:
    """Eğitim sınıflandırması şemasına (11.9.3) uyan sentetik yanıt: katalog dışı bir Arnavutluk
    pasaportu. Her çağrıda yeni bir sözlük; `top` üst düzey anahtarları değiştirir."""
    data: dict[str, Any] = {
        "catalog_slug": None,
        "country_iso3": "ALB",
        "doc_kind": "pasaport",
        "proposed_name": "Albanian Passport",
        "side": "single",
        "notes": "Başlıkta ülke adı ve pasaport yazıyor; MRZ belge kodu P.",
    }
    data.update(top)
    return data


def training_request(
    *,
    images: int = 1,
    instructions: str = "Eğitim sınıflandırması talimatı (test).",
    prompt: str = "Dosya türü: JPEG (test).",
    known_slugs: tuple[str, ...] = SLUGS,
    doc_kinds: frozenset[str] = DOC_KINDS,
) -> TrainingClassificationRequest:
    # Her görüntü ayrı boyutta: baytlar farklıdır, sıra testte görünür.
    return TrainingClassificationRequest(
        images=tuple(
            PageImage(
                make_half_filled_image_bytes("PNG" if index % 2 else "JPEG", (220 + index, 110))
            )
            for index in range(images)
        ),
        instructions=instructions,
        prompt=prompt,
        known_slugs=known_slugs,
        doc_kinds=doc_kinds,
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


# Kurgusal kişi adı; hata mesajlarında ve loglarda geçmediği denetlenir.
SYNTHETIC_REQUESTED_PERSON = "Ornekova Test"


def query_payload(
    *people: str,
    kind: str | None = "ehliyet",
    types: tuple[str, ...] = ("serbian_driving_license",),
    intent: str = "find_documents",
) -> dict[str, Any]:
    """Belge isteği şemasına (12.3.1) uyan sentetik yanıt; kişi verilmezse
    `SYNTHETIC_REQUESTED_PERSON`. Her çağrıda yeni bir sözlük."""
    return {
        "intent": intent,
        "people": list(people or (SYNTHETIC_REQUESTED_PERSON,)),
        "documents": [] if kind is None else [{"kind": kind, "types": list(types)}],
        "group": None,
        "group_ids": [],
        "language": "tr",
    }


def other_payload() -> dict[str, Any]:
    """Belge isteği olmayan mesajın yanıtı."""
    return {
        "intent": "other",
        "people": [],
        "documents": [],
        "group": None,
        "group_ids": [],
        "language": None,
    }


def query_request(
    *,
    instructions: str = "Belge isteği talimatı (test).",
    prompt: str = "<katalog>…</katalog>\n<mesaj>Ornekova'nın ehliyetini göster</mesaj>",
    known_slugs: tuple[str, ...] = SLUGS,
) -> DocumentQueryRequest:
    return DocumentQueryRequest(instructions=instructions, prompt=prompt, known_slugs=known_slugs)
