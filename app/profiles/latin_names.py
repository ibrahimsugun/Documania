"""Latin ad onarımı — PRD 05.2.2 (PLAN.md §C81).

05.2.2'den önce açılmış bir çalışanın ad, soyad ya da diğer isimler alanı Latin olmayan yazım
taşıyabilir: yapay zekâ Latin adı yalnız MRZ'de olan sayfada Kiril yazımı `surname`'e koydu, kayıt
çevrilmeden açıldı. `repair_latin_names` bu kayıtları tekrar çalıştırılabilir biçimde düzeltir:

1. Latin olmayan yazım `original_script_name`'e taşınır — alan boşsa; ad, diğer isimler ve soyad
   sırasıyla (`PersonKey.original_spelling` ile aynı kural).
2. Her Latin olmayan alanın Latin yazımı önce çalışanın Latin isim yazımlarından (alias; belge ya
   da MRZ kaynaklı, 05.7.2 — ad ve soyad birlikte, `Ad Soyad` yazımını kelime sınırından bölerek),
   sonra Kiril çevirisinden (`transliterate_cyrillic`) bulunur. Çevirinin dili çalışanın
   belgelerinin Kiril sayfalarından okunur (tek dil varsa; yoksa ICAO). Bulunamayan alan değişmez;
   profil kartı "Latin yazım eksik" uyarısı gösterir (10.5.1).
3. Değişen her alan için `EMPLOYEE_FIELD_FILLED` olayı yazılır: alan adı ve kaynak, değer değil
   (CONVENTIONS §6).

Onarım göç değildir, yönetici komutuyla çalışır (`python -m app.profiles repair-latin-names`).
Alanları Latin olan çalışana dokunulmaz; ikinci çalıştırma değişiklik ve olay yazmaz. Klasör ve
dosya adları (K8), eşleştirme anahtarı ve isim yazımları değişmez; belge içeriğine dokunulmaz.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import Script
from app.db.models import Document, Employee, EmployeeAlias, Page
from app.events import EventType, record_event
from app.matching.names import (
    EmptyNameError,
    is_latin_name,
    normalize_name,
    transliterate_cyrillic,
)

GIVEN_NAMES = "given_names"
SURNAME = "surname"
OTHER_NAMES = "other_names"
ORIGINAL_SCRIPT_NAME = "original_script_name"
# Yalnız Latin harfi taşıyan alanlar, orijinal yazımın kuruluş sırasıyla.
LATIN_FIELDS = (GIVEN_NAMES, OTHER_NAMES, SURNAME)
REPAIR_RULE = "05.2.2"


class RepairSource(enum.StrEnum):
    """Onarımda yazılan değerin kaynağı (`EMPLOYEE_FIELD_FILLED` verisi)."""

    LATIN_FIELDS = "latin_fields"  # orijinal yazım: Latin alanlardaki Latin olmayan yazım
    ALIAS = "alias"  # çalışanın Latin isim yazımı
    TRANSLITERATION = "transliteration"  # Kiril çevirisi


@dataclass(frozen=True, slots=True)
class LatinRepair:
    """Bir çalışanın onarımı: `filled` yazılan alanlar (alan → kaynak), `latin_missing` Latin
    yazımı bulunamayıp değişmeden kalan alanlar. Kişisel değer taşımaz."""

    employee_id: str
    filled: tuple[tuple[str, RepairSource], ...]
    latin_missing: tuple[str, ...]


def needs_latin_repair(employee: Employee) -> bool:
    """Ad, soyad ya da diğer isimler Latin olmayan harf taşıyor mu (05.2.2)."""
    return any(not is_latin_name(value) for value in _names(employee).values())


def repair_latin_names(
    session: Session, *, actor: str = "system", dry_run: bool = False
) -> list[LatinRepair]:
    """Latin alanında Latin olmayan harf taşıyan çalışanları onarır (E numarası sırasıyla).

    Dönen liste yalnız onarım gerektiren çalışanlardır; `dry_run` ise ne yapılacağı hesaplanır,
    kayıt ve olay yazılmaz. Olaylar `actor` adıyla yazılır. Oturum commit edilmez.
    """
    employees = session.scalars(select(Employee)).all()
    repairs = []
    # E numarası sırası (`E9999` < `E10000`).
    for employee in sorted(employees, key=lambda each: (len(each.id), each.id)):
        if not needs_latin_repair(employee):
            continue
        repairs.append(_repair(session, employee, actor=actor, dry_run=dry_run))
    return repairs


def _repair(session: Session, employee: Employee, *, actor: str, dry_run: bool) -> LatinRepair:
    names = _names(employee)
    foreign = {name: value for name, value in names.items() if not is_latin_name(value)}
    changes: dict[str, tuple[str, RepairSource]] = {}
    if not employee.original_script_name:
        original = " ".join(foreign[name] for name in LATIN_FIELDS if name in foreign)
        changes[ORIGINAL_SCRIPT_NAME] = (original, RepairSource.LATIN_FIELDS)
    language = _cyrillic_language(session, employee.id)
    from_alias = _alias_spelling(session, employee, names, language)
    for name, value in foreign.items():
        if from_alias is not None and name in from_alias:
            changes[name] = (from_alias[name], RepairSource.ALIAS)
            continue
        latin = transliterate_cyrillic(value, language=language)
        if latin is not None:
            changes[name] = (latin, RepairSource.TRANSLITERATION)
    if not dry_run:
        for name, (value, source) in changes.items():
            setattr(employee, name, value)
            record_event(
                session,
                EventType.EMPLOYEE_FIELD_FILLED,
                employee_id=employee.id,
                actor=actor,
                data={"field": name, "source": source.value, "rule": REPAIR_RULE},
            )
        session.flush()
    return LatinRepair(
        employee_id=employee.id,
        filled=tuple((name, source) for name, (_, source) in changes.items()),
        latin_missing=tuple(name for name in foreign if name not in changes),
    )


def _names(employee: Employee) -> dict[str, str]:
    # Latin olması gereken dolu alanlar, orijinal yazımın kuruluş sırasıyla.
    values = {
        GIVEN_NAMES: employee.given_names,
        OTHER_NAMES: employee.other_names,
        SURNAME: employee.surname,
    }
    return {name: value for name, value in values.items() if value}


def _alias_spelling(
    session: Session, employee: Employee, names: dict[str, str], language: str | None
) -> dict[str, str] | None:
    # Çalışanın Latin `Ad Soyad` yazımı (05.7.2): kelime sınırından bölündüğünde iki parçası
    # kayıttaki ad ve soyadla aynı anahtara inen ilk yazım. Diğer isimler alias'ta yoktur.
    given, surname = names.get(GIVEN_NAMES), names.get(SURNAME)
    if given is None or surname is None:
        return None
    aliases = session.scalars(
        select(EmployeeAlias.raw_name)
        .where(EmployeeAlias.employee_id == employee.id)
        .order_by(EmployeeAlias.id)
    )
    languages = tuple(dict.fromkeys((language, None)))
    for raw_name in aliases:
        if not is_latin_name(raw_name):
            continue
        words = raw_name.split()
        for index in range(1, len(words)):
            head, tail = " ".join(words[:index]), " ".join(words[index:])
            head_key, tail_key = _key(head), _key(tail)
            if head_key is None or tail_key is None:
                continue
            if any(
                head_key == _key(given, candidate) and tail_key == _key(surname, candidate)
                for candidate in languages
            ):
                return {GIVEN_NAMES: head, SURNAME: tail}
    return None


def _key(text: str, language: str | None = None) -> str | None:
    try:
        return normalize_name(text, language=language)
    except EmptyNameError:
        return None


def _cyrillic_language(session: Session, employee_id: str) -> str | None:
    # Çalışanın belgelerinin kaynak sayfalarından Kiril olanların dili; tek dil yoksa `None`.
    refs = session.scalars(
        select(Document.source_refs_json).where(Document.employee_id == employee_id)
    )
    pages = {
        (ref["file_id"], index)
        for source_refs in refs
        for ref in _refs(source_refs)
        for index in ref.get("pages", ())
    }
    if not pages:
        return None
    rows = session.execute(
        select(Page.file_id, Page.index, Page.analysis_json).where(
            Page.file_id.in_({file_id for file_id, _ in pages})
        )
    )
    languages = {
        analysis.get("language")
        for file_id, index, analysis in rows
        if (file_id, index) in pages
        and isinstance(analysis, dict)
        and analysis.get("script") == Script.CYRILLIC.value
    } - {None}
    return next(iter(languages)) if len(languages) == 1 else None


def _refs(source_refs: object) -> list[dict[str, Any]]:
    # `documents.source_refs_json`: `[{"file_id": 4, "pages": [0]}]`; bozuk kayıt atlanır.
    if not isinstance(source_refs, list):
        return ()
    return [ref for ref in source_refs if isinstance(ref, dict) and "file_id" in ref]
