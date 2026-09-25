"""Orijinal yazımı kayıttaki Latin adlardan doldurma — PRD 05.2.2 (PLAN.md §C83).

05.2.2 değişmeden önce `original_script_name` yalnız Latin olmayan isimlerde doluyordu: Latin
belgeyle açılan çalışanın alanı boş kaldı. Yeni kural ismin belgede basılı hâlini alfabesi ne
olursa olsun bu alanda ister. Bundan sonra analiz edilen belgelerde alan boru hattından dolu
gelir; **daha önce açılmış** çalışanlar için bu tek seferlik komut vardır:

    python -m app.profiles fill-original-spelling [--dry-run] [--actor AD]

`original_script_name` alanı **boş** olan çalışanda, kayıttaki Latin ad alanları
(`given_names`, `other_names`, `surname` — bu sırayla) birleştirilip alana yazılır. Dolu alana
dokunulmaz: Kiril/Arap yazımlar olduğu gibi kalır.

Değer belgeden okunmaz, kayıttan türetilir — belgedeki basılı sıra (çoğu pasaportta önce soyad)
ve büyük/küçük harf bilinmez. Bu yüzden olay `source: record_latin_names` ile yazılır: alanın
belgeden okunmuş bir kanıt olmadığı, türetildiği ayırt edilebilsin. Belgeden okunmuş değer
istenirse partinin yeniden analizi (10.3.2) alanı belgedeki hâliyle yazar.

Tekrar çalıştırılabilir: ikinci çalıştırma alanları dolu bulur, değişiklik ve olay yazmaz.
Klasör ve dosya adları (K8), eşleştirme anahtarı ve isim yazımları değişmez; belge içeriğine
dokunulmaz. Oturum commit edilmez; çağıran commit eder.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Employee
from app.events import EventType, record_event
from app.profiles.latin_names import GIVEN_NAMES, ORIGINAL_SCRIPT_NAME, OTHER_NAMES, SURNAME

# Orijinal yazımın kuruluş sırası; `PersonKey.original_spelling` ile aynı.
NAME_FIELDS = (GIVEN_NAMES, OTHER_NAMES, SURNAME)
FILL_RULE = "05.2.2"
FILL_SOURCE = "record_latin_names"


@dataclass(frozen=True, slots=True)
class OriginalSpellingFill:
    """Bir çalışanın doldurulması. `filled` alan yazıldıysa `True`. Kişisel değer taşımaz."""

    employee_id: str
    filled: bool


def fill_original_spelling(
    session: Session, *, actor: str = "system", dry_run: bool = False
) -> list[OriginalSpellingFill]:
    """Orijinal yazımı boş olan çalışanların alanını kayıttaki adlardan doldurur.

    Dönen liste yalnız alanı boş olan çalışanlardır (E numarası sırasıyla); hiç adı olmayan
    çalışanda `filled` `False`'tur — yazacak bir şey yoktur. `dry_run` ise ne yapılacağı
    hesaplanır, kayıt ve olay yazılmaz.
    """
    employees = session.scalars(select(Employee)).all()
    fills = []
    # E numarası sırası (`E9999` < `E10000`).
    for employee in sorted(employees, key=lambda each: (len(each.id), each.id)):
        if employee.original_script_name:
            continue
        spelling = _spelling(employee)
        if spelling is not None and not dry_run:
            employee.original_script_name = spelling
            record_event(
                session,
                EventType.EMPLOYEE_FIELD_FILLED,
                employee_id=employee.id,
                actor=actor,
                data={
                    "field": ORIGINAL_SCRIPT_NAME,
                    "source": FILL_SOURCE,
                    "rule": FILL_RULE,
                },
            )
        fills.append(OriginalSpellingFill(employee_id=employee.id, filled=spelling is not None))
    if not dry_run:
        session.flush()
    return fills


def _spelling(employee: Employee) -> str | None:
    parts = [getattr(employee, name) for name in NAME_FIELDS]
    return " ".join(part for part in parts if part) or None
