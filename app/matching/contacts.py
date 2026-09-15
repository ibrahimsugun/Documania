"""İletişim bilgisi birikimi — PRD 05.8.1, 05.8.2 (§8.1 `employee_contacts`, §8.4 `person.contact`).

Bir belge adayının sayfalarından okunan telefon, e-posta ve adres eşleşen ya da yeni açılan bir
çalışana eklenir (05.5, 05.6). Eşleşme yoksa (onay bekleyen profil, kişisiz belge) çağrılmaz:
`employee_id` yoktur, `employee_contacts` yabancı anahtarı boş kayıt kabul etmez.

**Okuma (05.8.1).** Sayfa kendini boş ya da okunamaz veriyorsa (`build_person_key` ile aynı
kural, K1) okumasına güvenilmez. `person.contact`'ın üç alanı (`phone`, `email`, `address`)
birbirinden bağımsızdır; adayın sayfaları arasında **en son görülen** değer alınır (sayfa sırası
adayın belge sırasıdır). Okunmayan tür (belgede açıkça yazılı değil, §8.4) taşınmaz.

**Çakışma (05.8.2).** Yazma `record_contact_sighting`'e (`app/db/models.py`) bırakılır: türün
güncel kaydıyla aynı değer yalnız `last_seen_at`'i ilerletir, farklı değer güncel kaydı kapatıp
(`is_current: False`) yeni bir satır açar — eski kayıt silinmez, geçmiş olarak kalır (K16).

`source_document_id` bu adımda (05.5–05.7, çıktı belgesi henüz yok) boştur; `employee_identifiers`
ve `employee_aliases`'ın bu aşamada izlediği örüntüyle aynıdır. Olay yazılmaz: §8.3'ün kapalı
olay türü listesinde iletişim bilgisi için ayrı bir tür yok (D6/D11 ile aynı gerekçe).
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis
from app.db.models import ContactKind, record_contact_sighting

CONTACT_KINDS = (ContactKind.PHONE, ContactKind.EMAIL, ContactKind.ADDRESS)


def collect_contacts(analyses: Iterable[PageAnalysis]) -> dict[str, str]:
    """Adayın sayfalarından (belgedeki sırasıyla) her tür için en son görülen değeri döner.

    Boş ya da okunamaz sayfanın `person.contact`'ı okunmaz (K1). Bir türün hiçbir sayfada
    değeri yoksa sözlükte anahtarı yoktur.
    """
    latest: dict[str, str] = {}
    for analysis in analyses:
        if analysis.is_blank or not analysis.is_readable:
            continue
        contact = analysis.person.contact
        for kind in CONTACT_KINDS:
            value = getattr(contact, kind.value)
            if value is not None:
                latest[kind.value] = value
    return latest


def accumulate_contacts(
    session: Session,
    employee_id: str,
    analyses: Iterable[PageAnalysis],
    *,
    source_document_id: int | None = None,
) -> tuple[str, ...]:
    """Adayın sayfalarından okunan iletişim bilgilerini çalışana ekler (05.8.1, 05.8.2).

    Her okunan tür `record_contact_sighting` ile yazılır. Dönen değer bu çağrıda yeni güncel
    satır açılan türlerdir (`changed: True`); aynı değer tekrarında tür dönmez. Oturum commit
    edilmez.
    """
    changed: list[str] = []
    for kind, value in collect_contacts(analyses).items():
        sighting = record_contact_sighting(
            session,
            employee_id=employee_id,
            kind=kind,
            value=value,
            source_document_id=source_document_id,
        )
        if sighting.changed:
            changed.append(kind)
    return tuple(changed)
