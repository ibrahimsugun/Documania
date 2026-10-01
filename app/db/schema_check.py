"""Açılışta şema sürümü denetimi (PRD 13.5.3 — PLAN.md §D77).

Uygulama şemayı kendisi kurmaz; göçleri `alembic upgrade head` (ya da `baslat.bat`) koşar. Göç
koşulmadan açılan süreç, eksik sütunu ilk istekte 500 olarak gösterir — o yüzden panel, işçi ve bot
açılırken veritabanının `alembic_version` kaydını koddaki son göçle karşılaştırır
(`ensure_schema_current`) ve uyuşmazsa açılmaz:

- kayıt yok (tablo hiç yok ya da boş): göç hiç koşulmamış;
- kayıt koddaki zincirde ama son göç değil: şema eski;
- kayıt koddaki zincirde yok: veritabanı kodun bilmediği ileri bir sürümde (eski kod, yeni şema).

Hata iletisi mevcut ve beklenen sürümü ve çare komutunu söyler. Denetim yalnız okur; şemaya ve
veriye dokunmaz. `STARTUP_SCHEMA_CHECK=false` onu kapatır (yalnız şemayı `create_all` ile kuran
testler için; varsayılan açık).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import Engine, create_engine, pool

from app.config import Settings

REMEDY = "Önce `python -m alembic upgrade head` çalıştırın ya da `baslat.bat` ile başlatın."
FORWARD_REMEDY = (
    "Kodu veritabanını yükselten sürüme güncelleyin, sonra `baslat.bat` ile başlatın "
    "(`python -m alembic upgrade head` bu kodla ileri sürümü tanımaz)."
)


class SchemaVersionError(RuntimeError):
    """Veritabanı şeması kodun beklediği göç sürümünde değil; süreç açılmaz."""


def _script_location() -> Path:
    # Depoda ve Docker imajında (`/srv/alembic`, çalışma dizini `/srv`) göç betikleri `app/`'in
    # yanındadır; paket site-packages'tan yüklendiyse çalışma dizinine bakılır.
    candidates = (Path(__file__).resolve().parents[2] / "alembic", Path.cwd() / "alembic")
    for candidate in candidates:
        if (candidate / "env.py").is_file():
            return candidate
    raise SchemaVersionError(
        "Göç betikleri bulunamadı (alembic/ dizini); şema sürümü denetlenemiyor. "
        "Süreci depo kökünden başlatın."
    )


@lru_cache
def _script_directory() -> ScriptDirectory:
    return ScriptDirectory(str(_script_location()))


def expected_revision() -> str:
    """Koddaki son göçün sürümü (ör. `0022`)."""
    heads = _script_directory().get_heads()
    if len(heads) != 1:
        raise SchemaVersionError(f"Göç zincirinde tek son sürüm yok: {', '.join(sorted(heads))}.")
    return heads[0]


def current_revision(engine: Engine) -> str | None:
    """Veritabanının `alembic_version` kaydı; tablo yoksa ya da boşsa `None`.

    Birden fazla kayıt (dallanmış zincir) virgülle birleştirilir; hiçbiri tek son sürüme eşit
    olmayacağı için uyuşmazlık sayılır.
    """
    with engine.connect() as connection:
        heads = MigrationContext.configure(connection).get_current_heads()
    return ", ".join(sorted(heads)) if heads else None


def _is_known(revision: str) -> bool:
    try:
        return _script_directory().get_revision(revision) is not None
    except CommandError:  # zincirde olmayan sürüm
        return False


def schema_mismatch(current: str | None, expected: str) -> str | None:
    """Uyuşmazlık iletisi; şema güncelse `None`."""
    if current == expected:
        return None
    remedy = REMEDY
    if current is None:
        reason = "veritabanında göç sürümü yok (göçler hiç koşulmamış)"
    elif "," not in current and _is_known(current):
        reason = "veritabanı şeması eski"
    elif "," in current:
        reason = "veritabanında birden fazla göç sürümü kayıtlı"
    else:
        # `upgrade head` burada işe yaramaz: veritabanını yükselten göç bu kodda yok.
        reason = "veritabanı bu kodun bilmediği ileri bir sürümde (kod eski ya da başka daldan)"
        remedy = FORWARD_REMEDY
    shown = current or "yok"
    return (
        f"Şema ve kod sürümü uyuşmuyor: {reason}. Mevcut sürüm: {shown}, beklenen sürüm: "
        f"{expected}. {remedy}"
    )


def ensure_schema_current(settings: Settings) -> str | None:
    """Şema son göçte değilse `SchemaVersionError` atar; doğrulanan sürümü döner.

    Denetim ayarla kapalıysa hiçbir şeye bakmaz ve `None` döner.
    """
    if not settings.startup_schema_check:
        return None
    expected = expected_revision()
    # Uygulamanın motoru değil: SQLite'ta her işlemi `BEGIN IMMEDIATE` ile açar, yalnız okuyan
    # denetim çalışan işçinin yazma kilidini beklememeli.
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    try:
        current = current_revision(engine)
    finally:
        engine.dispose()
    message = schema_mismatch(current, expected)
    if message is not None:
        raise SchemaVersionError(message)
    return expected
