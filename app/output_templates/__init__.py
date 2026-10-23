"""Hazır şablonlar (FR-MOD-15; 15.1.1, 15.1.4): İK'nın çalışanlar için çıktı alacağı belge
kalıplarının deposu — yükleme, liste, arşiv ve geri alma.

Ayrıntı `app.output_templates.service`'tedir.
"""

from app.output_templates.service import (
    DESCRIPTION_MAX_LENGTH,
    NAME_MAX_LENGTH,
    DuplicateTemplateError,
    TemplateFormError,
    TemplateNameTakenError,
    TemplateNotFoundError,
    TemplateSummary,
    create_template,
    field_count,
    get_template,
    list_templates,
    normalize_template_name,
    set_template_archived,
    status_counts,
    template_file_label,
)

__all__ = [
    "DESCRIPTION_MAX_LENGTH",
    "NAME_MAX_LENGTH",
    "DuplicateTemplateError",
    "TemplateFormError",
    "TemplateNameTakenError",
    "TemplateNotFoundError",
    "TemplateSummary",
    "create_template",
    "field_count",
    "get_template",
    "list_templates",
    "normalize_template_name",
    "set_template_archived",
    "status_counts",
    "template_file_label",
]
