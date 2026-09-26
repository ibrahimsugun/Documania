"""11.9.5 — Harita yükle: CSV haritasının okunması (envanter, önerilen tür ve genel slug + yol
biçimleri), yol önceliği ve güvenliği, gerekçeli atlama, yerindeki dosya, önizleme sayıları ve
toplu taramanın başlatılması (`app.training.map_import`; PLAN.md §C87).

Haritalar testte kurulan sentetik CSV'lerdir; gerçek envanter kullanılmaz. Dosyalar sentetik
PDF/görüntülerdir (`tests/fixtures/gen.py`); kişisel değer yoktur (CONVENTIONS §6).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Event,
    ExampleFileRecord,
    ExampleMethod,
    TrainingItem,
    TrainingRun,
    TrainingRunKind,
)
from app.events import EventType
from app.storage import DataLayout, sha256_bytes
from app.training import (
    KnownTypes,
    MapError,
    MapPlan,
    MapRoot,
    SkipReason,
    create_run,
    item_source_path,
    parse_map,
    plan_map,
    preview_map,
    start_map_scan,
)
from app.training.map_import import MAP_CHECK_KEY, READ_COLUMNS, Outlook, map_outlooks
from app.training.mechanical import parse_example_inventory
from tests.fixtures.gen import make_half_filled_image_bytes, make_pdf_bytes
from tests.training.invariants import assert_employee_data_untouched

MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000
INVENTORY_COLUMNS = (
    "slug",
    "in_catalog",
    "role",
    "dest",
    "source_collection_path",
    "source",
    "author",
    "note",
    "sha256",
    "status",
)


def _jpeg(width: int = 200) -> bytes:
    return make_half_filled_image_bytes("JPEG", (width, 100))


def _csv(
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[str],
    *,
    delimiter: str = ",",
    bom: bool = True,
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(column, "") for column in columns])
    return ("﻿" if bom else "").encode() + buffer.getvalue().encode("utf-8")


def _example(layout: DataLayout, slug: str, name: str, content: bytes) -> Path:
    folder = layout.type_examples_dir(slug)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(content)
    return path


def _file(layout: DataLayout, relative: str, content: bytes) -> Path:
    path = layout.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _plan(
    content: bytes,
    layout: DataLayout,
    known: KnownTypes,
    *,
    collection_root: Path | None = None,
    max_rows: int = MAX_ROWS,
) -> MapPlan:
    rows = parse_map(content, max_bytes=MAX_BYTES, max_rows=max_rows)
    return plan_map(rows, layout, known, collection_root=collection_root, max_files=max_rows)


def _record(session: Session, slug: str, name: str, sha256: str) -> None:
    session.add(
        ExampleFileRecord(
            type_slug=slug, name=name, sha256=sha256, method=ExampleMethod.LEGACY.value
        )
    )
    session.flush()


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# --- biçimler -------------------------------------------------------------------------------


def test_the_inventory_format_is_read_with_dest_sha256_and_role(
    layout: DataLayout, known: KnownTypes
) -> None:
    content = _jpeg()
    _example(layout, "albanian_passport", "GEN-a.jpg", content)
    _file(layout, "KnownDocuments/_referans/albanian_passport/kural.pdf", make_pdf_bytes(1))
    rows = [
        {
            "slug": "albanian_passport",
            "role": "example",
            "dest": "KnownDocuments/examples/albanian_passport/GEN-a.jpg",
            "source_collection_path": "albanian_passport/a.jpg",
            "source": "https://ornek.invalid/a.jpg",
            "author": "Kurgusal Yazar",
            "note": "Serbest not",
            "sha256": sha256_bytes(content).upper(),
        },
        {
            "slug": "albanian_passport",
            "role": "reference",
            "dest": "KnownDocuments/_referans/albanian_passport/kural.pdf",
        },
    ]

    plan = _plan(_csv(rows, INVENTORY_COLUMNS), layout, known)

    (entry,) = plan.entries
    assert (entry.row, entry.slug, entry.column, entry.root) == (
        2,
        "albanian_passport",
        "dest",
        MapRoot.DATA,
    )
    assert entry.sha256 == sha256_bytes(content)  # küçük harfe iner
    assert entry.reference == "KnownDocuments/examples/albanian_passport/GEN-a.jpg"
    assert (entry.name, entry.in_place, entry.type_slug) == (
        "GEN-a.jpg",
        "albanian_passport",
        "albanian_passport",
    )
    assert [(s.row, s.reason) for s in plan.skipped] == [(3, SkipReason.REFERENCE)]
    assert plan.rows == 2


def test_the_suggested_types_format_expands_the_example_folder(
    layout: DataLayout, known: KnownTypes
) -> None:
    for name in ("b.png", "a.jpg", "notlar.txt"):
        _example(layout, "afghan_passport", name, _jpeg())
    columns = ("slug", "onerilen_name", "country_iso3", "kaynak_tur", "ornek_klasoru")
    rows = [
        {
            "slug": "afghan_passport",
            "onerilen_name": "Afghan Passport",
            "ornek_klasoru": "KnownDocuments/examples/afghan_passport/",
        },
        {"slug": "afghan_identity_card", "ornek_klasoru": "KnownDocuments/examples/yok/"},
    ]

    plan = _plan(_csv(rows, columns), layout, known)

    assert [(e.row, e.name, e.column, e.in_place) for e in plan.entries] == [
        (2, "a.jpg", "ornek_klasoru", "afghan_passport"),
        (2, "b.png", "ornek_klasoru", "afghan_passport"),
    ]
    assert plan.entries[0].reference == "KnownDocuments/examples/afghan_passport/a.jpg"
    assert [(s.row, s.reason, s.detail) for s in plan.skipped] == [
        (3, SkipReason.MISSING, "klasör yok")
    ]


def test_a_generic_map_with_semicolons_and_upper_case_headers_is_read(
    layout: DataLayout, known: KnownTypes
) -> None:
    _file(layout, "tarama/ornek.jpg", _jpeg())
    content = _csv(
        [{"SLUG": "turkish_passport", " Path ": "tarama\\ornek.jpg"}],
        ("SLUG", " Path "),
        delimiter=";",
        bom=False,
    )

    (entry,) = _plan(content, layout, known).entries

    assert (entry.slug, entry.column, entry.reference, entry.in_place, entry.type_slug) == (
        "turkish_passport",
        "path",
        "tarama/ornek.jpg",
        None,
        "turkish_passport",
    )


def test_only_the_type_role_sha256_and_path_columns_are_read() -> None:
    # Kişisel içerik taşıyabilecek sütunlar (`personal_values_transcribed`, `note`, `author`) ve
    # uzak adres (`source`) okunmaz: okunan satırda karşılıkları yoktur.
    assert set(READ_COLUMNS) == {
        "slug",
        "role",
        "sha256",
        "dest",
        "output_relative_path",
        "ornek_klasoru",
        "source_collection_path",
        "path",
    }
    content = _csv(
        [
            {
                "slug": "turkish_passport",
                "path": "a.jpg",
                "personal_values_transcribed": "ORNEKOVA TEST 1990-01-01",
                "note": "../../gizli.jpg",
                "author": "Kurgusal",
            }
        ],
        ("slug", "path", "personal_values_transcribed", "note", "author"),
    )

    (row,) = parse_map(content, max_bytes=MAX_BYTES, max_rows=MAX_ROWS)

    assert row.paths == (("path", "a.jpg"),)
    assert "ORNEKOVA" not in repr(row) and "gizli" not in repr(row)
    with pytest.raises(MapError, match="yol sütunu yok"):
        parse_map(
            _csv([{"note": "a.jpg"}], ("slug", "note")), max_bytes=MAX_BYTES, max_rows=MAX_ROWS
        )


def test_row_numbers_follow_the_spreadsheet_and_blank_rows_count(
    layout: DataLayout, known: KnownTypes
) -> None:
    content = b"slug,path\r\n,\r\n\r\nturkish_passport,\r\n"

    (row,) = parse_map(content, max_bytes=MAX_BYTES, max_rows=MAX_ROWS)

    assert (row.number, row.slug, row.paths) == (4, "turkish_passport", ())
    assert [(s.row, s.reason) for s in _plan(content, layout, known).skipped] == [
        (4, SkipReason.NO_PATH)
    ]


# --- yol önceliği ve gerekçeler ---------------------------------------------------------------


def test_the_path_column_priority_is_dest_output_folder_collection_path(
    layout: DataLayout, known: KnownTypes, tmp_path: Path
) -> None:
    for relative in ("d.jpg", "o.jpg", "p.jpg"):
        _file(layout, relative, _jpeg())
    _example(layout, "turkish_passport", "k.jpg", _jpeg())
    collection = tmp_path / "koleksiyon"
    collection.mkdir()
    (collection / "c.jpg").write_bytes(_jpeg())
    columns = (
        "slug",
        "path",
        "source_collection_path",
        "ornek_klasoru",
        "output_relative_path",
        "dest",
    )
    folder = "KnownDocuments/examples/turkish_passport"
    rows = [
        {"path": "p.jpg", "output_relative_path": "o.jpg", "dest": "d.jpg"},
        {"path": "p.jpg", "ornek_klasoru": folder, "output_relative_path": "o.jpg"},
        {"path": "p.jpg", "source_collection_path": "c.jpg", "ornek_klasoru": folder},
        {"path": "p.jpg", "source_collection_path": "c.jpg"},
        {"path": "p.jpg"},
    ]

    plan = _plan(_csv(rows, columns), layout, known, collection_root=collection)

    assert [(e.row, e.column, e.root, e.name) for e in plan.entries] == [
        (2, "dest", MapRoot.DATA, "d.jpg"),
        (3, "output_relative_path", MapRoot.DATA, "o.jpg"),
        (4, "ornek_klasoru", MapRoot.DATA, "k.jpg"),
        (5, "source_collection_path", MapRoot.COLLECTION, "c.jpg"),
        (6, "path", MapRoot.DATA, "p.jpg"),
    ]
    assert plan.entries[3].path == (collection / "c.jpg").resolve()


def test_the_collection_column_needs_the_optional_collection_root(
    layout: DataLayout, known: KnownTypes, tmp_path: Path
) -> None:
    collection = tmp_path / "koleksiyon"
    (collection / "alt").mkdir(parents=True)
    (collection / "alt" / "c.jpg").write_bytes(_jpeg())
    _file(layout, "p.jpg", _jpeg())
    content = _csv(
        [
            {"slug": "turkish_passport", "source_collection_path": "alt\\c.jpg"},
            {"source_collection_path": "alt/c.jpg", "path": "p.jpg"},
        ],
        ("slug", "source_collection_path", "path"),
    )

    unset = _plan(content, layout, known)
    configured = _plan(content, layout, known, collection_root=collection)

    assert [(s.row, s.reason) for s in unset.skipped] == [(2, SkipReason.NO_COLLECTION)]
    assert [(e.row, e.column) for e in unset.entries] == [(3, "path")]  # sıradaki sütun
    assert [(e.row, e.column, e.reference) for e in configured.entries] == [
        (2, "source_collection_path", "alt/c.jpg"),
        (3, "source_collection_path", "alt/c.jpg"),
    ]
    assert configured.entries[0].in_place is None  # koleksiyon dosyası yerinde değildir


@pytest.mark.parametrize(
    ("value", "detail"),
    [
        ("/etc/passwd", "mutlak yol"),
        ("C:\\Windows\\a.jpg", "sürücü harfi"),
        ("\\\\sunucu\\pay\\a.jpg", "UNC yolu"),
        ("KnownDocuments/../../a.jpg", "`..` parçası"),
    ],
)
def test_unsafe_paths_are_skipped_and_nothing_outside_is_read(
    layout: DataLayout, known: KnownTypes, value: str, detail: str
) -> None:
    content = _csv([{"slug": "turkish_passport", "path": value}], ("slug", "path"))

    plan = _plan(content, layout, known)

    assert plan.entries == ()
    (skipped,) = plan.skipped
    assert (skipped.reason, skipped.detail, skipped.value) == (
        SkipReason.UNSAFE_PATH,
        detail,
        value,
    )
    assert skipped.label == f"güvensiz yol ({detail})"


def test_missing_files_and_empty_folders_are_skipped(layout: DataLayout, known: KnownTypes) -> None:
    (layout.root / "bos").mkdir()
    (layout.root / "bos" / "notlar.txt").write_bytes(b"x")
    _file(layout, "dosya.jpg", _jpeg())
    content = _csv(
        [
            {"path": "yok.jpg"},
            {"path": "bos"},  # klasör, dosya değil
            {"ornek_klasoru": "bos"},
            {"ornek_klasoru": "dosya.jpg"},  # dosya, klasör değil
        ],
        ("slug", "path", "ornek_klasoru"),
    )

    plan = _plan(content, layout, known)

    assert plan.entries == ()
    assert [(s.row, s.reason) for s in plan.skipped] == [
        (2, SkipReason.MISSING),
        (3, SkipReason.MISSING),
        (4, SkipReason.EMPTY_FOLDER),
        (5, SkipReason.MISSING),
    ]
    assert plan.skipped_counts() == {SkipReason.MISSING: 3, SkipReason.EMPTY_FOLDER: 1}


def test_an_unknown_slug_is_no_hint_and_a_file_in_place_takes_its_folder_type(
    layout: DataLayout, known: KnownTypes
) -> None:
    _example(layout, "turkish_passport", "a.jpg", _jpeg())
    _file(layout, "gelen/b.jpg", _jpeg())
    content = _csv(
        [
            {"slug": "yok_boyle_tur", "path": "gelen/b.jpg"},
            {"path": "KnownDocuments/examples/turkish_passport/a.jpg"},
            {"slug": "x" * 80, "path": "gelen/b.jpg"},
        ],
        ("slug", "path"),
    )

    unknown, in_place, long_slug = _plan(content, layout, known).entries

    assert (unknown.type_slug, unknown.hint_slug) == (None, "yok_boyle_tur")
    assert (in_place.slug, in_place.in_place, in_place.type_slug, in_place.hint_slug) == (
        None,
        "turkish_passport",
        "turkish_passport",
        "turkish_passport",
    )
    assert (long_slug.type_slug, long_slug.hint_slug) == (None, None)


# --- sınırlar ve bozuk harita ---------------------------------------------------------------


def test_the_map_is_refused_beyond_its_limits_or_when_unreadable(
    layout: DataLayout, known: KnownTypes
) -> None:
    rows = [{"path": f"{index}.jpg"} for index in range(3)]
    with pytest.raises(MapError, match="2 satır sınırını"):
        parse_map(_csv(rows, ("path",)), max_bytes=MAX_BYTES, max_rows=2)
    with pytest.raises(MapError, match="MB sınırını"):
        parse_map(_csv(rows, ("path",)), max_bytes=10, max_rows=MAX_ROWS)
    with pytest.raises(MapError, match="UTF-8"):
        parse_map("slug,path\nç,ş.jpg\n".encode("cp1254"), max_bytes=MAX_BYTES, max_rows=9)
    with pytest.raises(MapError, match="satır yok"):
        parse_map(b"slug,path\r\n", max_bytes=MAX_BYTES, max_rows=MAX_ROWS)
    with pytest.raises(MapError, match="yol sütunu yok"):
        parse_map(b"", max_bytes=MAX_BYTES, max_rows=MAX_ROWS)
    with pytest.raises(MapError, match="CSV olarak okunamadı"):
        parse_map(
            b'path\r\n"' + b"a" * (csv.field_size_limit() + 1) + b'"\r\n',
            max_bytes=10 * MAX_BYTES,
            max_rows=MAX_ROWS,
        )
    for index in range(3):
        _example(layout, "turkish_passport", f"{index}.jpg", _jpeg(200 + index))
    folder = _csv(
        [{"ornek_klasoru": "KnownDocuments/examples/turkish_passport"}], ("ornek_klasoru",)
    )
    with pytest.raises(MapError, match="2 dosya sınırını"):
        _plan(folder, layout, known, max_rows=2)


# --- önizleme ------------------------------------------------------------------------------


def test_the_preview_counts_and_writes_nothing(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    registered, fresh = _jpeg(201), _jpeg(202)
    _example(layout, "turkish_passport", "kayitli.jpg", registered)
    _example(layout, "turkish_passport", "yeni.jpg", fresh)
    _record(session, "turkish_passport", "kayitli.jpg", sha256_bytes(registered))
    known_sha, listed_sha = _jpeg(203), _jpeg(204)
    _record(session, "albanian_passport", "baska.jpg", sha256_bytes(known_sha))
    for relative, data in (
        ("gelen/a.jpg", known_sha),
        ("gelen/b.jpg", listed_sha),
        ("gelen/c.jpg", _jpeg(205)),
        ("gelen/d.jpg", _jpeg(206)),
    ):
        _file(layout, relative, data)
    inventory = parse_example_inventory(
        f"slug,role,sha256\nafghan_passport,example,{sha256_bytes(listed_sha)}\n"
    )
    content = _csv(
        [
            {"path": "KnownDocuments/examples/turkish_passport/kayitli.jpg"},  # kayıtlı, yerinde
            {"path": "KnownDocuments/examples/turkish_passport/yeni.jpg"},  # mekanik, yerinde
            {"path": "gelen/a.jpg", "sha256": sha256_bytes(known_sha)},  # kayıtlı (SHA tek tür)
            {"path": "gelen/b.jpg", "sha256": sha256_bytes(listed_sha)},  # mekanik (envanter)
            {"slug": "turkish_passport", "path": "gelen/c.jpg"},  # mekanik (haritanın türü)
            {"slug": "yok_boyle_tur", "path": "gelen/d.jpg"},  # yapay zekâ gerekebilir
            {"role": "reference", "path": "gelen/c.jpg"},
            {"path": "gelen/yok.jpg"},
        ],
        ("slug", "role", "path", "sha256"),
    )
    session.commit()
    files_before = _files(layout.root)
    plan = _plan(content, layout, known)

    preview = preview_map(session, plan, known, inventory=inventory)

    assert map_outlooks(session, plan, known, inventory=inventory) == [
        Outlook.REGISTERED,
        Outlook.MECHANICAL,
        Outlook.REGISTERED,
        Outlook.MECHANICAL,
        Outlook.MECHANICAL,
        Outlook.AI,
    ]
    assert (preview.rows, preview.files, preview.skipped_total) == (8, 6, 2)
    assert (preview.registered, preview.mechanical, preview.ai_possible) == (2, 3, 1)
    assert preview.skipped == ((SkipReason.REFERENCE, 1), (SkipReason.MISSING, 1))
    assert [s.row for s in preview.samples] == [8, 9]
    assert preview.as_event_data()["skipped"] == {"reference": 1, "missing": 1}
    # Önizleme yazmaz: dosya, çalıştırma, öğe, kayıt ve olay değişmez.
    assert _files(layout.root) == files_before
    assert session.scalar(select(func.count()).select_from(TrainingRun)) == 0
    assert session.scalar(select(func.count()).select_from(TrainingItem)) == 0
    assert session.scalar(select(func.count()).select_from(ExampleFileRecord)) == 2
    assert session.scalar(select(func.count()).select_from(Event)) == 0


def test_an_in_place_file_whose_record_or_map_disagrees_is_not_counted_as_registered(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    content = _jpeg()
    _example(layout, "turkish_passport", "a.jpg", content)
    _record(session, "turkish_passport", "a.jpg", sha256_bytes(content))
    path = "KnownDocuments/examples/turkish_passport/a.jpg"
    rows = [
        {"path": path, "sha256": "0" * 64},  # haritanın SHA-256'sı tutmuyor: inceleme
        {"slug": "albanian_passport", "path": path},  # tür klasörle çelişiyor: inceleme
        {"slug": "turkish_passport", "path": path, "sha256": sha256_bytes(content)},
    ]
    plan = _plan(_csv(rows, ("slug", "path", "sha256")), layout, known)

    assert map_outlooks(session, plan, known, inventory=None) == [
        Outlook.MECHANICAL,
        Outlook.MECHANICAL,
        Outlook.REGISTERED,
    ]


# --- başlatma ------------------------------------------------------------------------------


def test_starting_queues_one_item_per_file_logs_and_saves_the_map(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    _example(layout, "turkish_passport", "a.jpg", _jpeg(201))
    _file(layout, "gelen/b.jpg", _jpeg(202))
    content = _csv(
        [
            {"path": "KnownDocuments/examples/turkish_passport/a.jpg"},
            {"slug": "albanian_passport", "path": "gelen/b.jpg", "sha256": "A" * 64},
            {"role": "reference", "path": "gelen/b.jpg"},
        ],
        ("slug", "role", "path", "sha256"),
    )
    plan = _plan(content, layout, known)
    preview = preview_map(session, plan, known, inventory=None)
    run = create_run(session, kind=TrainingRunKind.MAP, created_by="ik", map_name="harita.csv")

    items = start_map_scan(session, layout, run, plan, preview, content=content, actor="ik")
    session.commit()

    assert [
        (i.row_number, i.original_name, i.source_ref, i.hint_slug, i.status) for i in items
    ] == [
        (
            2,
            "a.jpg",
            "KnownDocuments/examples/turkish_passport/a.jpg",
            "turkish_passport",
            "queued",
        ),
        (3, "b.jpg", "gelen/b.jpg", "albanian_passport", "queued"),
    ]
    assert items[0].checks_json == {
        MAP_CHECK_KEY: {
            "root": "data",
            "column": "path",
            "slug": None,
            "sha256": None,
            "in_place": "turkish_passport",
        }
    }
    assert items[1].checks_json is not None
    assert items[1].checks_json[MAP_CHECK_KEY]["sha256"] == "a" * 64
    assert all(item.staged_path is None and item.sha256 is None for item in items)
    assert (run.status, run.counts_json, run.map_name) == ("running", {"queued": 2}, "harita.csv")
    (event,) = session.scalars(select(Event)).all()
    assert (event.type, event.actor) == (EventType.TRAINING_MAP_STARTED.value, "ik")
    assert event.data_json == {
        "run_id": run.id,
        "rows": 3,
        "files": 2,
        "skipped": {"reference": 1},
        "registered": 0,
        "mechanical": 2,
        "ai_possible": 0,
    }
    assert "a.jpg" not in (event.message or "") and "gelen" not in str(event.data_json)
    assert layout.training_map_path(run.id).read_bytes() == content
    assert layout.training_map_path(run.id).name == f"{run.id}.csv"
    assert_employee_data_untouched(session, layout)


def test_the_item_source_is_the_staged_copy_or_the_in_place_example(
    session: Session, layout: DataLayout, known: KnownTypes
) -> None:
    _example(layout, "turkish_passport", "a.jpg", _jpeg(201))
    _file(layout, "gelen/b.jpg", _jpeg(202))
    content = _csv(
        [
            {"path": "KnownDocuments/examples/turkish_passport/a.jpg"},
            {"path": "gelen/b.jpg"},
        ],
        ("slug", "path"),
    )
    plan = _plan(content, layout, known)
    run = create_run(session, kind=TrainingRunKind.MAP, created_by="ik")
    in_place, elsewhere = start_map_scan(
        session,
        layout,
        run,
        plan,
        preview_map(session, plan, known, inventory=None),
        content=content,
        actor="ik",
    )

    assert item_source_path(layout, in_place) == plan.entries[0].path
    assert item_source_path(layout, elsewhere) is None  # kopyası henüz yok, yerinde değil
    elsewhere.staged_path = "KnownDocuments/_egitim/gelen/1/2.jpg"
    assert item_source_path(layout, elsewhere) == layout.resolve(elsewhere.staged_path)
    (layout.type_examples_dir("turkish_passport") / "a.jpg").unlink()
    assert item_source_path(layout, in_place) is None  # artık listelenmiyor
