"""Yapay zekâ talimat metinleri: sayfa analizi talimatı ve disiplin kuralları (03.4), tür açıklaması
talimatı (11.3.1), tür taslağı talimatı (11.5.5), eğitim sınıflandırması talimatı (11.9.3), profil
fotoğrafı kontrolü talimatı (11.7.1) ve Telegram belge isteği okuma talimatı (12.3.1)."""

from app.ai.prompts.document_query import load_document_query_instructions
from app.ai.prompts.page_analysis import (
    CATALOG_SLOT,
    PageAnalysisInstructions,
    PromptTemplateError,
    build_page_analysis_instructions,
    load_page_analysis_template,
)
from app.ai.prompts.photo_check import load_photo_check_instructions
from app.ai.prompts.profile_answer import load_profile_answer_instructions
from app.ai.prompts.training_classification import (
    DOC_KINDS_SLOT,
    TrainingClassificationInstructions,
    build_training_classification_instructions,
    load_training_classification_template,
)
from app.ai.prompts.type_description import load_type_description_instructions
from app.ai.prompts.type_proposal import load_type_proposal_instructions

__all__ = [
    "CATALOG_SLOT",
    "DOC_KINDS_SLOT",
    "PageAnalysisInstructions",
    "PromptTemplateError",
    "TrainingClassificationInstructions",
    "build_page_analysis_instructions",
    "build_training_classification_instructions",
    "load_document_query_instructions",
    "load_page_analysis_template",
    "load_photo_check_instructions",
    "load_profile_answer_instructions",
    "load_training_classification_template",
    "load_type_description_instructions",
    "load_type_proposal_instructions",
]
