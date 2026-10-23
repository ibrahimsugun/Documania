"""Belge erişim logu (PRD 10.9.2): her açma ve indirme kullanıcı ve zamanla kaydedilir.

Kayıt `access_log` tablosuna gider (PRD §8.1: ts, user_id, document_id, action, channel) — olay
logundan (K15, `events`) ayrı bir tablodur. Belgeyi sunan panel yolları (`GET
/employees/{id}/documents/{id}/file` açma, `.../download` indirme) sunmadan **önce** satırı yazar
ve commit eder: log yazılamazsa belge sunulmaz (kimin baktığı bilinmeyen erişim olmaz). Dosyası
kayıp ya da çalışana ait olmayan belge sunulmadığı için kayıt da düşmez.

Yazılmayanlar (PLAN.md §D27): profil kartının fotoğrafı (`.../photo`) ve belge geçmişi sayfası —
sayfayı görüntülemek belgeyi "açmak" sayılmaz —, ve yükleme detayındaki sayfa görüntüleri
(`/uploads/.../image`), çünkü onlar henüz bir `documents` satırı değildir (`access_log.document_id`
zorunlu). Kayıtlar yalnız eklenir; silinmez, değiştirilmez.

Hazır şablon (15.1.4) ve üretilen belge (15.2.2) da aynı tabloya yazılır (PLAN.md §D123 f): satır
`document_id`, `template_id` ya da `generated_document_id`'den tam olarak birini taşır (CHECK
`target`). Çalışan erişim logu görünümleri belgeye bağlandığı için şablon satırlarını göstermez.
Şablonun sayfa önizleme görüntüleri sayfa görüntülemedir, kayda girmez (yükleme detayındaki sayfa
görüntüleri gibi).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AccessAction, AccessChannel, AccessLog


def record_access(
    session: Session,
    *,
    user_id: int,
    action: AccessAction,
    document_id: int | None = None,
    template_id: int | None = None,
    generated_document_id: int | None = None,
    channel: AccessChannel = AccessChannel.WEB,
) -> AccessLog:
    """Erişim satırını ekler (`ts` şimdiki UTC anıdır); commit çağırana aittir. Erişilen şey
    `document_id`, `template_id` ya da `generated_document_id`'den tam olarak biridir."""
    targets = (document_id, template_id, generated_document_id)
    if sum(target is not None for target in targets) != 1:
        raise ValueError("Erişim kaydı tam olarak bir hedef taşır.")
    entry = AccessLog(
        user_id=user_id,
        document_id=document_id,
        template_id=template_id,
        generated_document_id=generated_document_id,
        action=action.value,
        channel=channel.value,
    )
    session.add(entry)
    session.flush()
    return entry
