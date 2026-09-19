#!/usr/bin/env bash
# belgeee — yedekleme ve geri yükleme ortak işlevleri (PRD 13.4.2).
# `backup.sh` ve `restore.sh` bunu kaynak alır; tek başına çalıştırılmaz.
#
# Ayarlar ortam değişkeninden okunur; tanımsızsa depo kökündeki `.env`'e (ya da `ENV_FILE`) bakılır.
# Uygulamayla aynı adlar: DATABASE_URL, DATA_DIR. Betiğe özel adlar backup.sh'in başında.

# Python çıktısı (Türkçe iletiler) Windows'ta da UTF-8 yazılsın.
export PYTHONUTF8=1

die() {
  echo "HATA: $*" >&2
  exit 1
}

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

# Python: yalnız standart kitaplık kullanılır (sqlite3, hashlib, urllib), uygulamanın sanal
# ortamı gerekmez. `PYTHON` ile yol verilebilir.
find_python() {
  local candidate
  for candidate in "${PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      return 0
    fi
  done
  die "Python 3 bulunamadı (PYTHON değişkeniyle yol verilebilir)"
}

# Ortam değişkeni, yoksa .env satırı. Değer yalnız çağırana döner, hiçbir yere yazdırılmaz.
env_value() {
  local key="$1" value env_file="${ENV_FILE:-.env}"
  value="${!key-}"
  if [ -z "$value" ] && [ -f "$env_file" ]; then
    value="$(sed -n "s/^${key}=//p" "$env_file" | tail -n 1 | tr -d '\r')"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
  fi
  printf '%s' "$value"
}

# DATABASE_URL'yi ayrıştırır: DB_KIND=sqlite|postgres, sqlite için DB_PATH, PostgreSQL için PG*
# ortam değişkenleri. Parola komut satırına değil ortama konur (`ps` çıktısında görünmesin).
parse_database_url() {
  local parsed
  parsed="$("$PYTHON_BIN" - "$1" <<'PY'
import shlex
import sys
from urllib.parse import parse_qs, unquote, urlsplit

url = sys.argv[1]
scheme = url.split(":", 1)[0].split("+", 1)[0]


def emit(**values):
    for key, value in values.items():
        if value:
            print(f"{key}={shlex.quote(value)}")


if scheme == "sqlite":
    path = url.split("://", 1)[1]
    if not path.startswith("/"):
        sys.exit("sqlite bağlantı dizesi 'sqlite:///yol' biçiminde olmalı")
    path = path[1:].split("?", 1)[0]
    if not path or path == ":memory:":
        sys.exit("bellek içi SQLite yedeklenemez")
    emit(DB_KIND="sqlite", DB_PATH=path)
elif scheme in ("postgresql", "postgres"):
    parts = urlsplit(url)
    if not parts.hostname or not parts.path.strip("/"):
        sys.exit("PostgreSQL bağlantı dizesinde sunucu ve veritabanı adı olmalı")
    query = parse_qs(parts.query)
    emit(
        DB_KIND="postgres",
        PGHOST=parts.hostname,
        PGPORT=str(parts.port or ""),
        PGUSER=unquote(parts.username or ""),
        PGPASSWORD=unquote(parts.password or ""),
        PGDATABASE=unquote(parts.path.strip("/")),
        PGSSLMODE=(query.get("sslmode") or [""])[0],
    )
else:
    sys.exit(f"desteklenmeyen veritabanı: {scheme}")
PY
)" || die "DATABASE_URL ayrıştırılamadı"
  eval "$parsed"
  if [ "$DB_KIND" = postgres ]; then
    export PGHOST PGDATABASE
    [ -z "${PGPORT-}" ] || export PGPORT
    [ -z "${PGUSER-}" ] || export PGUSER
    [ -z "${PGPASSWORD-}" ] || export PGPASSWORD
    [ -z "${PGSSLMODE-}" ] || export PGSSLMODE
  fi
}

sha256_of() {
  "$PYTHON_BIN" - "$1" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for chunk in iter(lambda: handle.read(1 << 20), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

# SQLite'ın yedekleme arayüzüyle tutarlı anlık görüntü: dosya kopyalamak yazma sürerken bozuk
# kopya verebilir. Görüntü de `integrity_check`'ten geçmezse yedek başarısız sayılır.
sqlite_snapshot() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
import os
import sqlite3
import sys

source_path, target_path = sys.argv[1:3]
if not os.path.isfile(source_path):
    sys.exit(f"SQLite dosyası yok: {source_path}")
source = sqlite3.connect(source_path, timeout=60)
target = sqlite3.connect(target_path)
try:
    source.backup(target)
    verdict = target.execute("PRAGMA integrity_check").fetchone()[0]
finally:
    target.close()
    source.close()
if verdict != "ok":
    sys.exit(f"anlık görüntü bütünlük denetiminden geçmedi: {verdict}")
PY
}

# `inner` yolu `outer` dizininin içindeyse dizine göre yolunu (/ ayraçlı), değilse boş yazar.
relative_inside() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
import os
import sys

inner, outer = (os.path.realpath(path) for path in sys.argv[1:3])
try:
    inside = os.path.commonpath([inner, outer]) == outer and inner != outer
except ValueError:  # Windows'ta farklı sürücüler
    inside = False
if inside:
    print(os.path.relpath(inner, outer).replace(os.sep, "/"))
PY
}

count_files() {
  find "$1" -type f | wc -l | tr -d ' '
}

# GNU tar gerekir (`--transform`, `--force-local`): üretim Linux'tur.
require_gnu_tar() {
  tar --version 2>/dev/null | head -n 1 | grep -q 'GNU tar' || die "GNU tar gerekli"
}
