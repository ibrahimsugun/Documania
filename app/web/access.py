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
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AccessAction, AccessChannel, AccessLog


def record_access(
    session: Session,
    *,
    user_id: int,
    document_id: int,
    action: AccessAction,
    channel: AccessChannel = AccessChannel.WEB,
) -> AccessLog:
    """Erişim satırını ekler (`ts` şimdiki UTC anıdır); commit çağırana aittir."""
    entry = AccessLog(
        user_id=user_id, document_id=document_id, action=action.value, channel=channel.value
    )
    session.add(entry)
    session.flush()
    return entry
