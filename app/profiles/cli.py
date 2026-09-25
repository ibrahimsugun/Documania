"""Çalışan profili yönetici komutları.

    python -m app.profiles repair-latin-names [--dry-run] [--actor AD]
    python -m app.profiles fill-fields [--dry-run] [--actor AD]
    python -m app.profiles fill-original-spelling [--dry-run] [--actor AD]

`repair-latin-names` (PRD 05.2.2, PLAN.md §C81): ad, soyad ya da diğer isimler alanında Latin
olmayan harf taşıyan çalışanları onarır (`app.profiles.latin_names`).

`fill-fields` (PRD 05.7.3, PLAN.md §C82): mevcut çalışanların boş profil alanlarını etkin
belgelerinden, en eski belge önce, boru hattının kuralıyla doldurur; dolu alan değişmez, farklı
değer profil kartında uyarı olur (`app.profiles.field_fill`).

`fill-original-spelling` (PRD 05.2.2, PLAN.md §C83): orijinal yazımı boş olan çalışanların alanını
kayıttaki Latin adlardan doldurur (`app.profiles.original_spelling`); Latin belgeyle açılmış eski
kayıtlar içindir, dolu alana dokunmaz.

İkisi de tekrar çalıştırılabilir: ikinci çalıştırma değişiklik yapmaz. Değişen çalışanın klasörü
varsa `profil.md`'si güncel kayıttan yeniden üretilir (09.1.1); klasör adı değişmez (K8).
`--dry-run` yalnız ne yapılacağını yazar. Çıktı yalnız E numarası ve alan adı taşır, kişisel değer
taşımaz (CONVENTIONS §6). Bağlantı dizesi ve veri dizini `app.config` ayarlarından gelir; şema
önceden `alembic upgrade head` ile kurulmuş olmalıdır.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.config import get_settings
from app.db.models import Employee
from app.db.session import create_db_engine, create_session_factory
from app.profiles.field_fill import ProfileFieldFill, fill_profile_fields
from app.profiles.latin_names import LatinRepair, repair_latin_names
from app.profiles.original_spelling import OriginalSpellingFill, fill_original_spelling
from app.profiles.render import write_profile
from app.storage import DataLayout


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.profiles", description="Çalışan profili")
    commands = parser.add_subparsers(dest="command", required=True)
    repair = commands.add_parser(
        "repair-latin-names",
        help="Latin alanlarında Latin olmayan yazım taşıyan çalışanları onarır (05.2.2)",
    )
    repair.add_argument(
        "--dry-run", action="store_true", help="yalnız ne yapılacağını yazar, kaydetmez"
    )
    repair.add_argument("--actor", default="system", help="olay logundaki kullanıcı adı")
    fill = commands.add_parser(
        "fill-fields",
        help="boş profil alanlarını çalışanın etkin belgelerinden doldurur (05.7.3)",
    )
    fill.add_argument(
        "--dry-run", action="store_true", help="yalnız ne yapılacağını yazar, kaydetmez"
    )
    fill.add_argument("--actor", default="system", help="olay logundaki kullanıcı adı")
    spelling = commands.add_parser(
        "fill-original-spelling",
        help="orijinal yazımı boş çalışanların alanını kayıttaki adlardan doldurur (05.2.2)",
    )
    spelling.add_argument(
        "--dry-run", action="store_true", help="yalnız ne yapılacağını yazar, kaydetmez"
    )
    spelling.add_argument("--actor", default="system", help="olay logundaki kullanıcı adı")
    return parser


def _describe(repair: LatinRepair) -> str:
    filled = ", ".join(f"{name} ({source.value})" for name, source in repair.filled) or "yok"
    line = f"{repair.employee_id}: yazılan {filled}"
    if repair.latin_missing:
        line += f"; Latin yazım eksik: {', '.join(repair.latin_missing)}"
    return line


def _describe_fill(fill: ProfileFieldFill) -> str:
    filled = ", ".join(fill.filled) or "yok"
    line = f"{fill.employee_id}: {fill.documents} belge; doldurulan {filled}"
    if fill.conflicts:
        line += f"; belgede farklı değer: {', '.join(fill.conflicts)}"
    return line


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "fill-fields":
        return _fill_fields(args.actor, dry_run=args.dry_run)
    if args.command == "fill-original-spelling":
        return _fill_original_spelling(args.actor, dry_run=args.dry_run)
    return _repair_latin_names(args.actor, dry_run=args.dry_run)


def _repair_latin_names(actor: str, *, dry_run: bool) -> int:
    settings = get_settings()
    layout = DataLayout(settings.data_dir)
    engine = create_db_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            repairs = repair_latin_names(session, actor=actor, dry_run=dry_run)
            if dry_run:
                session.rollback()
            else:
                session.commit()
                for repair in repairs:
                    employee = session.get_one(Employee, repair.employee_id)
                    if repair.filled and layout.employee_dir(employee.folder_name).is_dir():
                        write_profile(session, layout, employee)
    finally:
        engine.dispose()
    for repair in repairs:
        print(_describe(repair))
    verb = "onarılacak" if dry_run else "onarıldı"
    print(f"Latin ad onarımı: {len(repairs)} çalışan {verb}.")
    return 0


def _fill_fields(actor: str, *, dry_run: bool) -> int:
    settings = get_settings()
    layout = DataLayout(settings.data_dir)
    engine = create_db_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            # Kuru çalıştırma da alanları sırayla yazar (sonraki belge dolan alanı görmeli), sonra
            # hepsini geri alır.
            fills = fill_profile_fields(session, actor=actor)
            if dry_run:
                session.rollback()
            else:
                session.commit()
                for fill in fills:
                    employee = session.get_one(Employee, fill.employee_id)
                    if fill.filled and layout.employee_dir(employee.folder_name).is_dir():
                        write_profile(session, layout, employee)
    finally:
        engine.dispose()
    for fill in fills:
        print(_describe_fill(fill))
    changed = sum(1 for fill in fills if fill.filled)
    verb = "doldurulacak" if dry_run else "dolduruldu"
    print(
        f"Profil alanı tamamlama: {len(fills)} çalışanın belgeleri işlendi, {changed} çalışanda "
        f"alan {verb}."
    )
    return 0


def _describe_spelling(fill: OriginalSpellingFill) -> str:
    written = "orijinal yazım" if fill.filled else "yazılacak ad yok"
    return f"{fill.employee_id}: {written}"


def _fill_original_spelling(actor: str, *, dry_run: bool) -> int:
    settings = get_settings()
    layout = DataLayout(settings.data_dir)
    engine = create_db_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            fills = fill_original_spelling(session, actor=actor, dry_run=dry_run)
            if dry_run:
                session.rollback()
            else:
                session.commit()
                for fill in fills:
                    employee = session.get_one(Employee, fill.employee_id)
                    if fill.filled and layout.employee_dir(employee.folder_name).is_dir():
                        write_profile(session, layout, employee)
    finally:
        engine.dispose()
    for fill in fills:
        print(_describe_spelling(fill))
    changed = sum(1 for fill in fills if fill.filled)
    verb = "doldurulacak" if dry_run else "dolduruldu"
    print(f"Orijinal yazım: {len(fills)} çalışanın alanı boştu, {changed} çalışanda {verb}.")
    return 0
