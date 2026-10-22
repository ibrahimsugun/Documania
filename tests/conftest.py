import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event

from app.config import Settings, get_settings
from app.main import create_app

# PRD 10.10.1 (PLAN.md §D92 b): panelin açılış dili İngilizcedir. Testlerin büyük çoğunluğu Türkçe
# arayüz metnini denetler (kaynak dil, msgid'in kendisi); bu yüzden test sürecinde varsayılan dil
# Türkçedir. Dil davranışını sınayan testler ayarı açıkça verir (`tests/i18n`,
# `tests/web/test_interface_language.py`).
os.environ["PANEL_DEFAULT_LANGUAGE"] = "tr"

# tm 162 (PLAN.md §D99): test süreci deponun `.env` dosyasını okumaz — yerel makinede de temiz
# ortamdaki (cloud, CI) sonuç alınsın; bir testin ayara ihtiyacı varsa onu açıkça verir. `.env`
# okumayı sınayan testler dosyayı `_env_file=` ile kendileri gösterir.
Settings.model_config["env_file"] = None
get_settings.cache_clear()


# Test hızı (CONVENTIONS §1.4): test veritabanları geçicidir, çökme dayanıklılığı gerekmez. Yalnız
# test sürecinde SQLite diske yazma onayını beklemez (`synchronous=OFF`), geri alma günlüğünü ve
# geçici tabloları bellekte tutar. Uygulamanın kendi motor ayarları (`app/db/session.py`) değişmez.
@event.listens_for(Engine, "connect")
def _fast_test_sqlite(dbapi_connection, _record) -> None:
    if type(dbapi_connection).__module__.split(".")[0] not in {"sqlite3", "pysqlite2"}:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.execute("PRAGMA temp_store=MEMORY")
        # WAL'a alınmış bir veritabanının kipi değiştirilmez (yedek/geri yükleme testleri).
        if cursor.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete":
            cursor.execute("PRAGMA journal_mode=MEMORY")
    finally:
        cursor.close()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
