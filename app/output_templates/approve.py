"""Alan haritası önizlemesi ve onayı — PRD 15.1.3 (PLAN.md §D123 c, m).

İK haritanın son sürümünü sayfa görüntüsünün üstünde görür, `text`/`date` kutularının bağlı alanını
değiştirir ya da "boş bırak" (`unassigned`) yapar ve onaylar. Kutu çizme/taşıma yoktur: kutu,
sayfa, tür ve etiket haritadan değişmeden geçer; yalnız `source` değişir.

- **Doğrulama (`approve_map`).** Her doldurulabilir kutunun atanması gelir ve §8.7 `source`
  listesindendir; imza/kaşe/logo/fotoğraf/çerçeve kutusuna atama gönderilemez, haritada olmayan
  kutuya da. Kural dışı atama `MapAssignmentError` (422). En az bir kutu bir profil alanına bağlı
  değilse `NothingBoundError` (422).
- **Sürüm.** Onay yalnız son sürüme yapılır (`StaleMapError`: arada yeni inceleme gelmiş, 409).
  Atama değiştiyse değişmiş harita `store_map` ile **yeni sürüm** olarak yazılır (`map_hash`
  yeniden hesaplanır, `model` kutuları öneren modeldir) ve o sürüm onaylanır; değişmediyse son
  sürüm yerinde onaylanır (aynı içerik aynı özeti taşır). Eski sürüm silinmez (§D61: düzenleme ve
  yeniden inceleme geri alır). Zaten onaylı sürüm değişmeden gelirse hiçbir şey yazılmaz.
- **Şablon `ready` olur**; olay `TEMPLATE_MAP_APPROVED` kullanıcı adıyla: `template_id`,
  `version`, `field_count` (doldurulabilir kutu), `bound_count` (profil alanına bağlı kutu),
  `changed_count`, `based_on` (düzenlenen sürüm). Atanan alan adları kişisel değer değildir ama
  olaya da yazılmaz; sürüm JSON'u onları taşır.
- **Üretimin haritası (`approved_map`)** onay almış en yüksek sürümdür; onaysız yeni sürüm (yeniden
  inceleme) onaylanana dek onun yerini almaz.

Hiçbir fonksiyon commit etmez. Şablon dosyasına ve görüntülerine dokunulmaz (K10, K11, K17).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.schemas import (
    FILLABLE_KINDS,
    TEMPLATE_FIELD_SOURCES,
    TemplateField,
    TemplateFieldMap,
    validate_template_field_map,
)
from app.db.models import OutputTemplate, OutputTemplateMap, OutputTemplateStatus, utcnow
from app.events import EventType, record_event
from app.output_templates.examine import TemplateArchivedError, store_map

UNASSIGNED = "unassigned"


class MapNotFoundError(LookupError):
    """Şablonun bu sürümde haritası yok."""


class StaleMapError(ValueError):
    """Onaylanmak istenen sürüm artık son sürüm değil."""


class MapAssignmentError(ValueError):
    """Atama kural dışı: bilinmeyen alan, eksik atama ya da doldurulamaz kutuya atama."""


class NothingBoundError(ValueError):
    """Haritada profil alanına bağlı tek kutu yok; onay reddedilir (15.1.3)."""


@dataclass(frozen=True, slots=True)
class Approval:
    """Onayın sonucu: onaylı sürüm, yeni sürüm açıldı mı, kaç atama değişti, zaten onaylı mıydı."""

    map: OutputTemplateMap
    created: bool
    changed_count: int
    already_approved: bool = False


def field_map_of(row: OutputTemplateMap, *, page_count: int) -> TemplateFieldMap:
    """Saklanan sürümün §8.7 alanları; sistemin eklediği anahtarlar (`template_id`, `version`,
    `pages`) dışarıda kalır."""
    data = {"fields": row.json.get("fields") or [], "notes": row.json.get("notes") or ""}
    return validate_template_field_map(data, page_count=page_count)


def approved_map(template: OutputTemplate) -> OutputTemplateMap | None:
    """Üretimin kullandığı harita: onay almış en yüksek sürüm."""
    approved = [row for row in template.maps if row.approved_at is not None]
    return approved[-1] if approved else None


def map_version(template: OutputTemplate, version: int) -> OutputTemplateMap:
    for row in template.maps:
        if row.version == version:
            return row
    raise MapNotFoundError(version)


def _assigned(fields: tuple[TemplateField, ...], assignments: Mapping[str, str]) -> dict[str, str]:
    known = {item.field_id: item for item in fields}
    stray = [field_id for field_id in assignments if field_id not in known]
    locked = [
        field_id
        for field_id in assignments
        if field_id in known and known[field_id].kind not in FILLABLE_KINDS
    ]
    if stray or locked:
        raise MapAssignmentError("haritada olmayan ya da doldurulamaz kutu")
    chosen: dict[str, str] = {}
    for item in fields:
        if item.kind not in FILLABLE_KINDS:
            continue
        value = assignments.get(item.field_id)
        if value is None or value not in TEMPLATE_FIELD_SOURCES:
            raise MapAssignmentError("eksik ya da bilinmeyen atama")
        chosen[item.field_id] = value
    return chosen


def approve_map(
    session: Session,
    template: OutputTemplate,
    version: int,
    assignments: Mapping[str, str],
    *,
    actor: str,
) -> Approval:
    """Son sürümü verilen atamalarla onaylar (modül açıklaması); şablonu `ready` yapar."""
    if template.status == OutputTemplateStatus.ARCHIVED.value:
        raise TemplateArchivedError(template.id)
    row = map_version(template, version)
    if row is not template.maps[-1]:
        raise StaleMapError(version)
    field_map = field_map_of(row, page_count=template.page_count)
    chosen = _assigned(field_map.fields, assignments)
    if all(source == UNASSIGNED for source in chosen.values()):
        raise NothingBoundError(template.id)
    changed = sum(
        1 for item in field_map.fields if chosen.get(item.field_id, item.source) != item.source
    )

    if changed == 0 and row.approved_at is not None:
        return Approval(row, created=False, changed_count=0, already_approved=True)
    approved = row
    if changed:
        edited = TemplateFieldMap(
            fields=tuple(
                item.model_copy(update={"source": chosen[item.field_id]})
                if item.field_id in chosen
                else item
                for item in field_map.fields
            ),
            notes=field_map.notes,
        )
        approved = store_map(session, template, edited, model=row.model)
    approved.approved_at = utcnow()
    approved.approved_by = actor
    template.status = OutputTemplateStatus.READY.value
    session.flush()
    record_event(
        session,
        EventType.TEMPLATE_MAP_APPROVED,
        actor=actor,
        data={
            "template_id": template.id,
            "version": approved.version,
            "based_on": row.version,
            "field_count": len(chosen),
            "bound_count": sum(1 for source in chosen.values() if source != UNASSIGNED),
            "changed_count": changed,
        },
    )
    return Approval(approved, created=approved is not row, changed_count=changed)
