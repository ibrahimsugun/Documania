"""Yapay zekâ talimat metinleri: sayfa analizi talimatı ve disiplin kuralları (03.4), tür açıklaması
talimatı (11.3.1) ve profil fotoğrafı kontrolü talimatı (11.7.1)."""

from app.ai.prompts.page_analysis import (
    CATALOG_SLOT,
    PageAnalysisInstructions,
    PromptTemplateError,
    build_page_analysis_instructions,
    load_page_analysis_template,
)
from app.ai.prompts.photo_check import load_photo_check_instructions
from app.ai.prompts.type_description import load_type_description_instructions

__all__ = [
    "CATALOG_SLOT",
    "PageAnalysisInstructions",
    "PromptTemplateError",
    "build_page_analysis_instructions",
    "load_page_analysis_template",
    "load_photo_check_instructions",
    "load_type_description_instructions",
]
