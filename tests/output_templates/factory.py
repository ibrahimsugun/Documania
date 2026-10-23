"""Hazır şablon testlerinin ortak kurulumu: onaylı haritalı, `ready` sentetik şablon (15.2).

Şablon yükleme ve inceleme (15.1.1–15.1.3) kendi testlerindedir; burada satır, dosya ve onaylı
harita sürümü doğrudan yazılır."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.ai.schemas import TemplateField, TemplateFieldMap
from app.db.models import OutputTemplate, OutputTemplateStatus, utcnow
from app.output_templates import normalize_template_name, template_file_label
from app.output_templates.examine import store_map
from app.storage import DataLayout
from app.storage.atomic import sha256_bytes
from tests.fixtures.gen import make_text_pdf_bytes

NAME = TemplateField(
    field_id="f1",
    page=0,
    box=(0.3, 0.1, 0.9, 0.14),
    kind="text",
    label_text="Ime i prezime",
    source="full_name",
    font_size=11,
    max_chars=40,
)
BIRTH = TemplateField(
    field_id="f2",
    page=0,
    box=(0.3, 0.2, 0.6, 0.24),
    kind="date",
    label_text="Datum rodjenja",
    source="date_of_birth",
    font_size=11,
    max_chars=10,
)
MOTHER = TemplateField(
    field_id="f3",
    page=0,
    box=(0.3, 0.3, 0.9, 0.34),
    kind="text",
    label_text="Ime majke",
    source="mother_name",
    font_size=11,
    max_chars=40,
)
SKIPPED = TemplateField(
    field_id="f4",
    page=0,
    box=(0.3, 0.4, 0.9, 0.44),
    kind="text",
    label_text="Napomena",
    source="unassigned",
    font_size=11,
    max_chars=40,
)
SIGNATURE = TemplateField(field_id="f5", page=0, box=(0.6, 0.8, 0.9, 0.9), kind="signature")
FIELDS = (NAME, BIRTH, MOTHER, SKIPPED, SIGNATURE)
FIXED_TEXT = "UGOVOR O RADU"


def ready_template(
    session: Session,
    layout: DataLayout,
    fields: Sequence[TemplateField] = FIELDS,
    *,
    pdf: bytes | None = None,
    name: str = "Work contract",
) -> OutputTemplate:
    content = pdf or make_text_pdf_bytes([FIXED_TEXT])
    template = OutputTemplate(
        name=name,
        normalized_name=normalize_template_name(name),
        file_label=template_file_label(name),
        sha256=sha256_bytes(content),
        page_count=1,
        status=OutputTemplateStatus.READY.value,
        uploaded_by="ik",
    )
    session.add(template)
    session.flush()
    path = layout.template_original_path(template.id)
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    template.file_path = layout.relative(path)
    row = store_map(session, template, TemplateFieldMap(fields=tuple(fields), notes=""), model="m")
    row.approved_at = utcnow()
    row.approved_by = "ik"
    session.flush()
    return template
