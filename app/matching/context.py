"""Profilden yüklemede kişi denetimi — PRD 10.5.5 (PLAN.md §C83; §20.2.1, §20.2.3; K6).

Bağlam çalışanıyla yapılan yüklemede (profil sayfasından 10.5.3, yükleme sayfasında çalışan
seçilerek 10.2.1) analiz edilmiş her adayın kişi anahtarı (`PersonKey`, 05.4.1) bağlam çalışanıyla
karşılaştırılır. Yöntem sırayla uygulanır, ilk kesin sonuç kazanır:

1. **Belge numarası.** Temiz numara (§20.2.3, `clean_document_number`) bağlam çalışanının
   `employee_identifiers`'ında → `same`; yalnız başka çalışanlarınkinde → `different`. Temiz
   olmayan ya da hiçbir çalışanda olmayan numara hüküm vermez.
2. **Doğum tarihi.** Anahtarın doğum tarihi (MRZ önce; okunmamış ya da çelişen tarih yoktur) ve
   çalışanın doğum tarihi ikisi de varsa ve farklıysa → `different`.
3. **Ad.** Belgenin yazımları — ad-soyad (sayfanın diliyle), Latin yazımı (05.2.2) ve orijinal
   yazım — çalışanın bütün yazımlarıyla (`employee_aliases`; kayıttaki Latin ad-soyad ve orijinal
   yazım) §20.2.1 normalizasyonuyla karşılaştırılır: harf çevirisi, aksan, büyük/küçük harf,
   noktalama ve kelime sırası farkı yok sayılır. İki yazım uyar: birinin kelime kümesi ötekini
   kapsıyor ve bir soyad kelimesi ikisinde de geçiyor — ikinci adın yazılmaması çelişki değildir
   (04.1.1 gruplama kuralıyla aynı), yalnız adın tutması uyum sayılmaz. Soyad kelimesi belgenin
   okuduğu soyadındır (ve Latin yazımının); belge soyad okumadıysa (yalnız orijinal yazım)
   çalışanın soyadındır. Bir çift uyarsa `same`; belgenin yazımı var ama hiçbiri uymuyorsa
   `different`.
4. Hiçbir adım hüküm vermezse — okunaklı ne temiz numara ne ad var — `unknown`.

`different` belgeyi `context_person` doğrulayıcısıyla (06.5.1, `app.pipeline.validate`)
Unresolved'a gönderir: profile de başka çalışana da uygulanmaz, çalışan açılmaz, kimlik birikmez
(planlayıcı, `app.pipeline.plan`). `same` ve `unknown` akışı değiştirmez. Bağlam K6'yı gevşetmez:
`same` eşleştirme sayılmaz, çalışan kararı yine §20.2.2'nindir.

`compare_context_person` saf işlevdir; `context_person_verdict` bağlam çalışanının kayıtlarını ve
numaranın sahiplerini veritabanından okur. İkisi de veritabanına ve olay loguna yazmaz; sonuç
kişisel değer taşımaz, yalnız hükmü ve dayanağını (`ContextPersonBasis`).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import CatalogEntry
from app.db.models import Employee, EmployeeAlias, EmployeeIdentifier
from app.matching.match import PersonKey, clean_document_number
from app.matching.names import EmptyNameError, normalize_name


class ContextPersonResult(enum.StrEnum):
    """Belgenin kişisi bağlam çalışanı mı (PLAN.md §C83)."""

    SAME = "same"
    DIFFERENT = "different"
    UNKNOWN = "unknown"


class ContextPersonBasis(enum.StrEnum):
    """Kesin sonucu veren adım, yöntemin sırasıyla."""

    DOCUMENT_NUMBER = "document_number"
    DATE_OF_BIRTH = "date_of_birth"
    NAME = "name"


@dataclass(frozen=True, slots=True)
class ContextPersonVerdict:
    """Karşılaştırmanın hükmü; `basis` kesin sonucu veren adımdır (`unknown`'da boş)."""

    result: ContextPersonResult
    basis: ContextPersonBasis | None = None


UNKNOWN = ContextPersonVerdict(ContextPersonResult.UNKNOWN)


@dataclass(frozen=True, slots=True)
class ContextProfile:
    """Bağlam çalışanının karşılaştırmaya giren kayıtları.

    `identifiers` §20.2.1 normalize belge numaralarıdır; `spellings` bütün yazımların §20.2.1
    normalize anahtarları (alias'lar, kayıttaki ad-soyad, orijinal yazım), tekrarsız; `surname`
    kayıttaki soyadın normalize anahtarıdır.
    """

    employee_id: str
    identifiers: frozenset[str]
    date_of_birth: date | None
    spellings: tuple[str, ...]
    surname: str | None


def compare_context_person(
    key: PersonKey,
    profile: ContextProfile,
    *,
    clean_number: str | None,
    number_owners: Iterable[str] = (),
) -> ContextPersonVerdict:
    """Kişi anahtarını bağlam çalışanıyla yöntemin sırasıyla karşılaştırır (modül açıklaması).

    `clean_number` anahtarın §20.2.3'e göre temiz numarasıdır (`None`: yok); `number_owners` o
    numarayı `employee_identifiers`'ında taşıyan çalışanların E numaraları. Saf işlevdir.
    """
    if clean_number is not None:
        owners = set(number_owners)
        if profile.employee_id in owners or clean_number in profile.identifiers:
            return ContextPersonVerdict(
                ContextPersonResult.SAME, ContextPersonBasis.DOCUMENT_NUMBER
            )
        if owners:
            return ContextPersonVerdict(
                ContextPersonResult.DIFFERENT, ContextPersonBasis.DOCUMENT_NUMBER
            )
    born = key.date_of_birth
    if born is not None and profile.date_of_birth is not None and born != profile.date_of_birth:
        return ContextPersonVerdict(ContextPersonResult.DIFFERENT, ContextPersonBasis.DATE_OF_BIRTH)
    documents = _document_spellings(key)
    if not documents:
        return UNKNOWN
    surname = _surname_words(key) or _words(profile.surname)
    employees = [_words(spelling) for spelling in profile.spellings]
    if any(_fits(document, employee, surname) for document in documents for employee in employees):
        return ContextPersonVerdict(ContextPersonResult.SAME, ContextPersonBasis.NAME)
    return ContextPersonVerdict(ContextPersonResult.DIFFERENT, ContextPersonBasis.NAME)


def context_profile(session: Session, employee_id: str) -> ContextProfile:
    """Bağlam çalışanının kayıtları; çalışan yoksa `LookupError` (kişisel değer taşımaz)."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise LookupError(f"Bağlam çalışanı bulunamadı: {employee_id}")
    identifiers = frozenset(
        session.scalars(
            select(EmployeeIdentifier.value).where(EmployeeIdentifier.employee_id == employee_id)
        )
    )
    aliases = session.scalars(
        select(EmployeeAlias.normalized_name)
        .where(EmployeeAlias.employee_id == employee_id)
        .order_by(EmployeeAlias.id)
    )
    recorded = (
        _normalized(employee.given_names, employee.surname),
        _normalized(employee.original_script_name),
    )
    spellings = dict.fromkeys(
        spelling for spelling in (*aliases, *recorded) if spelling is not None and spelling
    )
    return ContextProfile(
        employee_id=employee.id,
        identifiers=identifiers,
        date_of_birth=employee.date_of_birth,
        spellings=tuple(spellings),
        surname=_normalized(employee.surname),
    )


def context_person_verdict(
    session: Session, key: PersonKey, *, entry: CatalogEntry, employee_id: str
) -> ContextPersonVerdict:
    """Adayın kişi anahtarını partinin bağlam çalışanıyla karşılaştırır (10.5.5).

    `entry` adayın katalog türüdür (numaranın temizliği türün zorunlu alanlarına bağlıdır,
    §20.2.3). Veritabanından okur, yazmaz; oturum commit edilmez.
    """
    profile = context_profile(session, employee_id)
    number = clean_document_number(key, entry)
    owners: tuple[str, ...] = ()
    if number is not None:
        owners = tuple(
            session.scalars(
                select(EmployeeIdentifier.employee_id)
                .where(EmployeeIdentifier.value == number)
                .distinct()
            )
        )
    return compare_context_person(key, profile, clean_number=number, number_owners=owners)


def _document_spellings(key: PersonKey) -> list[frozenset[str]]:
    # Belgenin okunmuş yazımları: ad-soyad (anahtarın, sayfanın diliyle), Latin yazımı ve orijinal
    # yazım; aynı kelime kümesi bir kez.
    spellings = (
        key.normalized_name,
        _normalized(key.latin_given_names, key.latin_surname)
        if key.latin_given_names is not None and key.latin_surname is not None
        else None,
        key.normalized_original_name,
    )
    words = (_words(spelling) for spelling in spellings)
    return list(dict.fromkeys(word_set for word_set in words if word_set))


def _surname_words(key: PersonKey) -> frozenset[str]:
    # Belgenin okuduğu soyadın kelimeleri; Latin yazımı sayfanın dilindeki çeviriyi de taşır.
    return _words(_normalized(key.surname)) | _words(_normalized(key.latin_surname))


def _fits(document: frozenset[str], employee: frozenset[str], surname: frozenset[str]) -> bool:
    # Bir kelime kümesi ötekini kapsıyor ve bir soyad kelimesi ikisinde de geçiyor.
    if not (document <= employee or employee <= document):
        return False
    return bool(surname & document & employee)


def _normalized(*parts: str | None) -> str | None:
    if all(part is None for part in parts):
        return None
    try:
        return normalize_name(*parts)
    except EmptyNameError:
        return None


def _words(spelling: str | None) -> frozenset[str]:
    return frozenset(spelling.split()) if spelling else frozenset()
