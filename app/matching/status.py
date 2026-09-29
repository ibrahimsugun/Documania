"""Çalışanı pasife alma ve yeniden etkinleştirme — PRD 10.5.7 (PLAN.md §C90-b, §D61; K16, R7, R11).

Pasif (`inactive`) çalışanın kimliği gerçektir: eşleştirme (05.5.1, §20.2.2) onu bulmaya devam eder,
sıra değişmez. Değişen yalnız rotadır — pasif çalışanla eşleşen yeni belge otomatik yerleşmez,
planlayıcı (`app.pipeline.plan_planner`) öğeyi `inactive_employee_reason` gerekçesiyle Unresolved'a
gönderir (R7) ve çalışan kişi tahmini olarak kalır. İK öğeyi atar (atama pasife izinlidir, 10.7.2)
ya da çalışanı etkinleştirip partiyi yeniden analiz eder. Profilden bağlam yüklemesi pasif çalışana
yapılmaz (`app.web.routers.uploads.store_upload`, 409).

`change_employee_status` iki aşamalı onaydan (K16, §20.6) sonra çağrılır: durumu çevirir ve
`EMPLOYEE_DEACTIVATED` ya da `EMPLOYEE_REACTIVATED` olayını kullanıcı adıyla yazar — veri `from`,
`to` ve (verildiyse) İK'nın `reason` notudur; isim ya da numara yazılmaz. Klasör, belgeler, alt
kayıtlar ve olaylar yerinde kalır; hiçbir şey silinmez, dosya taşınmaz (R11). Birleştirilmiş
(`merged`, 10.5.9) çalışanın durumu buradan değişmez.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Employee, EmployeeStatus, Event
from app.events import EventType, record_event

# Panelin, `profil.md`'nin ve botun durum etiketleri; `EmployeeStatus`'un her değeri burada.
STATUS_LABELS: dict[str, str] = {
    EmployeeStatus.ACTIVE.value: "Aktif",
    EmployeeStatus.INACTIVE.value: "Pasif",
    EmployeeStatus.MERGED.value: "Birleşti",
}
# Arama sonuçlarında (atama, taşıma, bot) pasif çalışanın adının eki.
INACTIVE_SUFFIX = " (pasif)"
# Profilde isteğe bağlı durum notu (§C90-b); form sınırı yalnız aşırı girdiye karşıdır.
REASON_MAX_LENGTH = 200

# Pasif çalışanla eşleşen öğenin gerekçe kodu (§20.2.2 notu, R7): gerekçe metninde durur, kuyruk
# öğesinin detayı onu tanıyıp çalışanın profiline bağlantı verir.
INACTIVE_EMPLOYEE_CODE = "inactive_employee"
INACTIVE_EMPLOYEE_REASON = (
    "Pasif çalışan ({employee_id}) ile eşleşti ({code}): belge otomatik yerleşmez (R7); öğeyi bir "
    "çalışana atayın ya da çalışanı etkinleştirip partiyi yeniden analiz edin."
)

_EVENTS = {
    EmployeeStatus.INACTIVE: EventType.EMPLOYEE_DEACTIVATED,
    EmployeeStatus.ACTIVE: EventType.EMPLOYEE_REACTIVATED,
}


class EmployeeStatusError(ValueError):
    """Durum değişmez; hiçbir şey yazılmadı. Mesaj kişisel değer taşımaz."""


class EmployeeMergedError(EmployeeStatusError):
    """Çalışan birleştirilmiş; durumu pasife alma/etkinleştirmeyle değişmez."""


class StatusUnchangedError(EmployeeStatusError):
    """Çalışan zaten istenen durumda (aynı işlem iki kez gönderildi)."""


class StatusReasonError(EmployeeStatusError):
    """Durum notu `REASON_MAX_LENGTH` karakterden uzun."""


def status_label(status: str) -> str:
    """Durumun Türkçe etiketi; tanınmayan değer (elle yazılmış eski kayıt) ham görünür."""
    return STATUS_LABELS.get(status, status)


def is_inactive(employee: Employee) -> bool:
    return employee.status == EmployeeStatus.INACTIVE.value


def status_suffix(status: str) -> str:
    """Pasif çalışanın adına eklenen " (pasif)"; öteki durumlarda boş."""
    return INACTIVE_SUFFIX if status == EmployeeStatus.INACTIVE.value else ""


def inactive_employee_reason(employee_id: str) -> str:
    """Pasif çalışanla eşleşen öğenin gerekçesi: kod ve E numarası, kişisel değer yok (08.1.2)."""
    return INACTIVE_EMPLOYEE_REASON.format(employee_id=employee_id, code=INACTIVE_EMPLOYEE_CODE)


def is_inactive_employee_reason(reason: str | None) -> bool:
    """Gerekçe pasif çalışan hükmünü taşıyor mu (kuyruk öğesinin detayı için)."""
    return reason is not None and f"({INACTIVE_EMPLOYEE_CODE})" in reason


def status_target(employee: Employee) -> EmployeeStatus:
    """Profildeki düğmenin hedefi: etkin çalışan pasife alınır, pasif olan etkinleştirilir.

    Birleştirilmiş çalışan `EmployeeMergedError`; tanınmayan durumdaki çalışan etkinleştirilir.
    """
    if employee.status == EmployeeStatus.MERGED.value:
        raise EmployeeMergedError(
            f"Çalışan {employee.id} birleştirilmiş; durumu değiştirilmez (10.5.9)"
        )
    if employee.status == EmployeeStatus.ACTIVE.value:
        return EmployeeStatus.INACTIVE
    return EmployeeStatus.ACTIVE


def check_status_change(employee: Employee, target: EmployeeStatus) -> None:
    """Değişikliğin denetimi; hiçbir şey yazmaz. Hedef yalnız `active` ya da `inactive`."""
    if target not in _EVENTS:
        raise ValueError(f"Hedef durum active ya da inactive olmalı: {target.value}")
    if employee.status == EmployeeStatus.MERGED.value:
        raise EmployeeMergedError(
            f"Çalışan {employee.id} birleştirilmiş; durumu değiştirilmez (10.5.9)"
        )
    if employee.status == target.value:
        raise StatusUnchangedError(f"Çalışan {employee.id} zaten {target.value}")


def normalized_reason(reason: str | None) -> str | None:
    """Notun boşlukları sadeleşir; boş not `None`, uzun not `StatusReasonError`."""
    text = " ".join((reason or "").split())
    if len(text) > REASON_MAX_LENGTH:
        raise StatusReasonError(f"Not en çok {REASON_MAX_LENGTH} karakter olabilir.")
    return text or None


def change_employee_status(
    session: Session,
    employee: Employee,
    target: EmployeeStatus,
    *,
    actor: str,
    reason: str | None = None,
) -> Event:
    """10.5.7 — çalışanın durumunu `target`'a çevirir ve olayını yazar; kurallar modül
    açıklamasındadır.

    `actor` iki aşamalı onayı (K16, §20.6.1) tamamlamış kullanıcının adıdır; boşsa `ValueError`.
    Denetim hataları `check_status_change`'inkiler ve `StatusReasonError`'dır. Oturum commit
    edilmez.
    """
    if not actor.strip():
        raise ValueError("Manuel işlem kullanıcı adıyla loglanır (K16): actor boş olamaz")
    check_status_change(employee, target)
    note = normalized_reason(reason)
    data: dict[str, object] = {"from": employee.status, "to": target.value}
    if note is not None:
        data["reason"] = note
    employee.status = target.value
    event = record_event(session, _EVENTS[target], employee_id=employee.id, actor=actor, data=data)
    session.flush()
    return event


def last_deactivation(session: Session, employee_id: str) -> Event | None:
    """Çalışanın en son `EMPLOYEE_DEACTIVATED` olayı (profildeki pasif bildirimi için)."""
    return session.scalars(
        select(Event)
        .where(
            Event.employee_id == employee_id,
            Event.type == EventType.EMPLOYEE_DEACTIVATED.value,
        )
        .order_by(Event.ts.desc(), Event.id.desc())
        .limit(1)
    ).first()
