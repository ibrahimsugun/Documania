"""Belge grubu testleri: izole SQLite veritabanı ve sentetik katalog türleri."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import Base, KnownDocumentType
from app.db.session import create_db_engine, create_session_factory

# (slug, ad, dosya etiketi, ülke, etkin) — etiketler bilerek yazım farkı ve yakın ad taşır.
CATALOG = (
    ("russian_passport", "Russian Passport", "Passport", "RU", True),
    ("turkish_passport", "Turkish Passport", "Passport", "TR", True),
    ("serbian_passport", "Serbian Passport", "  passport ", "RS", False),
    ("residence_card", "Serbian Residence Card", "Residence Card", "RS", True),
    ("turkish_id_card", "Turkish Identity Card", "Identity Card", "TR", True),
    ("kosovo_id_document", "Kosovo Identity Document", "Identity Document", "XK", True),
    ("profile_picture", "Profile Picture", "Profile Picture", None, True),
)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'gruplar-test.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as db_session:
        for slug, name, label, country, active in CATALOG:
            db_session.add(
                KnownDocumentType(
                    slug=slug,
                    name=name,
                    file_label=label,
                    country=country,
                    sides="single",
                    direct=False,
                    analyze=True,
                    output_format="keep",
                    active=active,
                )
            )
        db_session.commit()
        yield db_session
