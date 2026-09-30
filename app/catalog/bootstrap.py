"""Açılışta katalog kurulumu (00.6.2, 00.6.3 — PLAN.md §D76).

Analiz kataloğu yalnız `known_document_types` tablosundan okur (`export_catalog`); tohum yalnız
veri dizinine yazılırsa taze kurulumdaki her belge Unknown'a düşer. Panel, işçi ve bot süreçleri
açılırken `load_catalog_on_startup` çağırır:

1. `KnownDocuments/catalog.yaml` yoksa tohum oraya yazılır (`install_seed_catalog`).
2. Tablo **boşsa** o dosya doğrulanıp veritabanına yüklenir (`import_catalog`).
3. Tablo doluysa hiçbir şey yapılmaz. Veritabanı çalışma zamanı kaynağıdır ve panel (11.1.1) yalnız
   onu yazar: her açılışta içe aktarma, paneldeki düzenlemeyi dosyadaki eski hâlle ezerdi. Dosyada
   yapılan değişikliği yüklemek `python -m app.catalog import`'un işidir.

Açılışı durdurmayan durumlar (log yazılır, süreç açılır — sağlayıcısı olmayan işçi kuyruğu gibi):

- şema yok: uygulama şemayı kendisi kurmaz, önce `alembic upgrade head`;
- `catalog.yaml` geçersiz: dosya bütün olarak doğrulanır (00.6.1), hiçbir tür yüklenmez;
- aynı anda açılan başka süreç (panel, işçi, bot) tabloyu önce doldurdu: birincil anahtar çakışması
  yutulur. SQLite'ta `BEGIN IMMEDIATE` iki açılışı zaten sıraya koyar; çakışma PostgreSQL yoludur.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.schema import CatalogError
from app.catalog.sync import CatalogImportResult, import_catalog
from app.catalog.yaml_io import install_seed_catalog, read_catalog_file
from app.db.models import KnownDocumentType
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout

logger = logging.getLogger(__name__)


def _is_empty(session: Session) -> bool:
    return session.scalar(select(KnownDocumentType.slug).limit(1)) is None


def seed_empty_catalog(
    session_factory: sessionmaker[Session], path: Path
) -> CatalogImportResult | None:
    """`known_document_types` boşsa `path`'teki kataloğu yükleyip commit eder.

    Yüklediyse sonucu, tabloya dokunmadıysa `None` döner.
    """
    with session_factory() as session:
        if not inspect(session.connection()).has_table(KnownDocumentType.__tablename__):
            logger.warning(
                "Katalog veritabanına yüklenmedi: şema kurulmamış (önce `alembic upgrade head`)."
            )
            return None
        if not _is_empty(session):
            return None
        try:
            catalog = read_catalog_file(path)
        except CatalogError as exc:
            logger.error(
                "Katalog veritabanına yüklenmedi, belge türleri tanınmayacak: %s geçersiz.\n%s\n"
                "Dosyayı düzeltip `python -m app.catalog import` çalıştırın.",
                path,
                exc,
            )
            return None
        try:
            result = import_catalog(session, catalog)
            session.commit()
        except IntegrityError:
            session.rollback()
            if _is_empty(session):
                raise  # çakışan süreç yok: başka bir kısıt bozuldu
            logger.info("Katalog bu arada açılan başka bir süreç tarafından yüklendi.")
            return None
    logger.info("Başlangıç kataloğu veritabanına yüklendi (%d tür): %s", len(catalog), path)
    return result


def load_catalog_on_startup(database_url: str, layout: DataLayout) -> CatalogImportResult | None:
    """Süreç açılışı: tohum dosyası yoksa yazılır, tablo boşsa dosya veritabanına yüklenir."""
    install_seed_catalog(layout)
    engine = create_db_engine(database_url)
    try:
        return seed_empty_catalog(create_session_factory(engine), layout.catalog_path)
    finally:
        engine.dispose()
