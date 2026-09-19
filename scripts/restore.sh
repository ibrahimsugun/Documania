#!/usr/bin/env bash
# belgeee — yedekten geri yükleme (PRD 13.4.2). Yedek: `scripts/backup.sh`; prosedür: docs/YEDEKLEME.md.
#
# Kullanım: scripts/restore.sh [--force] <belgeee-...tar.gz>
#
# Hedef `DATABASE_URL` ve `DATA_DIR`'dir (ortam değişkeni ya da `.env`). Uygulama DURDURULMUŞ
# olmalıdır. Hedefte veri ya da veritabanı varsa betik dokunmadan durur; `--force` ile mevcut veri
# dizini ve SQLite dosyası silinmez, `.before-restore-<zaman>` adıyla yanına çekilir (PostgreSQL'de
# `pg_restore --clean` mevcut nesnelerin üzerine yazar; önce ayrı bir döküm alın).
#
# Sıra: arşivin SHA-256'sı ve içindeki veritabanı dökümünün özeti doğrulanır → hedef denetlenir
# → veri dizini yan dizine açılır → yerine konur → veritabanı yüklenir → bütünlük denetlenir.
# Doğrulama geçmezse hedefe hiçbir şey yazılmaz.

set -euo pipefail
umask 077

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/backup-lib.sh
. "$here/backup-lib.sh"

force=0
archive=""
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    -*) die "bilinmeyen seçenek: $arg (kullanım: restore.sh [--force] <arşiv>)" ;;
    *)
      [ -z "$archive" ] || die "tek bir arşiv verilmeli"
      archive="$arg"
      ;;
  esac
done
[ -n "$archive" ] || die "kullanım: restore.sh [--force] <arşiv>"
[ -f "$archive" ] || die "arşiv yok: $archive"

find_python
require_gnu_tar

database_url="$(env_value DATABASE_URL)"
[ -n "$database_url" ] || die "DATABASE_URL tanımlı değil"
data_dir="$(env_value DATA_DIR)"
data_dir="${data_dir:-data}"
parse_database_url "$database_url"

# 1) Arşivin sağlamlığı — hedefe dokunmadan önce.
if [ -f "$archive.sha256" ]; then
  expected="$(cut -d' ' -f1 "$archive.sha256")"
  [ "$(sha256_of "$archive")" = "$expected" ] || die "arşivin SHA-256 özeti tutmuyor: $archive"
  log "arşiv özeti doğrulandı"
else
  log "UYARI: $archive.sha256 yok, arşivin özeti doğrulanamadı"
fi

stage="$(mktemp -d)"
data_tmp=""
cleanup() {
  rm -rf "$stage"
  [ -z "$data_tmp" ] || rm -rf "$data_tmp"
}
trap cleanup EXIT

tar --force-local --extract --gzip --file="$archive" -C "$stage" MANIFEST.txt db ||
  die "arşiv açılamadı ya da MANIFEST.txt / db yok"
manifest_value() {
  sed -n "s/^$1=//p" "$stage/MANIFEST.txt" | tr -d '\r'
}
[ "$(manifest_value belgeee-backup)" = 1 ] || die "bu bir belgeee yedeği değil"
backup_kind="$(manifest_value db_kind)"
db_file="$(manifest_value db_file)"
db_sha="$(manifest_value db_sha256)"
[ "$backup_kind" = "$DB_KIND" ] ||
  die "yedek $backup_kind veritabanından, hedef DATABASE_URL $DB_KIND"
[ "$(sha256_of "$stage/$db_file")" = "$db_sha" ] || die "veritabanı dökümünün özeti tutmuyor"

# 2) Hedef denetimi — hiçbir şey yazmadan.
occupied=()
if [ -e "$data_dir" ] && [ -n "$(ls -A "$data_dir" 2>/dev/null)" ]; then
  occupied+=("veri dizini dolu: $data_dir")
fi
case "$DB_KIND" in
  sqlite)
    for suffix in "" -wal -shm -journal; do
      [ ! -e "$DB_PATH$suffix" ] || occupied+=("SQLite dosyası var: $DB_PATH$suffix")
    done
    ;;
  postgres)
    command -v pg_restore >/dev/null 2>&1 || die "pg_restore bulunamadı"
    command -v psql >/dev/null 2>&1 || die "psql bulunamadı"
    tables="$(psql --no-psqlrc -Atc \
      "select count(*) from information_schema.tables where table_schema = 'public'")" ||
      die "hedef PostgreSQL veritabanına bağlanılamadı"
    [ "$tables" = 0 ] || occupied+=("PostgreSQL veritabanında $tables tablo var")
    ;;
esac
if [ "${#occupied[@]}" -gt 0 ] && [ "$force" -ne 1 ]; then
  printf 'HATA: %s\n' "${occupied[@]}" >&2
  die "hedef boş değil; üzerine yazmak için --force verin (mevcut veri silinmez, yanına çekilir)"
fi

# 3) Veri dizini yan dizine açılır (aynı dosya sistemi: taşıma tek adımdır).
data_tmp="$data_dir.restoring"
[ ! -e "$data_tmp" ] || die "önceki yarım geri yükleme kalmış, inceleyip silin: $data_tmp"
mkdir -p "$(dirname "$data_dir")"
mkdir "$data_tmp"
tar --force-local --extract --gzip --file="$archive" -C "$data_tmp" --strip-components=1 data ||
  die "veri dizini arşivden açılamadı"
in_archive="$(tar --force-local --list --gzip --file="$archive" | grep -c '^data/.*[^/]$' || true)"
extracted="$(count_files "$data_tmp")"
[ "$in_archive" = "$extracted" ] ||
  die "arşivde $in_archive dosya var, $extracted dosya açıldı"

# 4) Yerine koyma. Mevcut olan silinmez, yanına çekilir.
moved="$(date -u +%Y%m%dT%H%M%SZ)"
if [ -e "$data_dir" ]; then
  if [ -n "$(ls -A "$data_dir" 2>/dev/null)" ]; then
    mv "$data_dir" "$data_dir.before-restore-$moved"
    log "mevcut veri dizini yanına çekildi: $data_dir.before-restore-$moved"
  else
    rmdir "$data_dir"
  fi
fi
mv "$data_tmp" "$data_dir"
data_tmp=""

case "$DB_KIND" in
  sqlite)
    for suffix in "" -wal -shm -journal; do
      if [ -e "$DB_PATH$suffix" ]; then
        mv "$DB_PATH$suffix" "$DB_PATH$suffix.before-restore-$moved"
        log "mevcut SQLite dosyası yanına çekildi: $DB_PATH$suffix.before-restore-$moved"
      fi
    done
    mkdir -p "$(dirname "$DB_PATH")"
    cp "$stage/$db_file" "$DB_PATH"
    "$PYTHON_BIN" - "$DB_PATH" <<'PY' || die "geri yüklenen veritabanı bütünlük denetiminden geçmedi"
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
verdict = connection.execute("PRAGMA integrity_check").fetchone()[0]
tables = connection.execute(
    "select count(*) from sqlite_master where type = 'table'"
).fetchone()[0]
connection.close()
if verdict != "ok":
    sys.exit(verdict)
print(f"veritabanı bütünlük denetimi: ok ({tables} tablo)")
PY
    ;;
  postgres)
    restore_options=(--no-owner --no-privileges --exit-on-error)
    [ "$force" -ne 1 ] || restore_options+=(--clean --if-exists)
    pg_restore "${restore_options[@]}" --dbname="$PGDATABASE" "$stage/$db_file" ||
      die "pg_restore başarısız"
    ;;
esac

log "geri yükleme tamam: $extracted dosya, veritabanı: $DB_KIND (yedek: $(manifest_value created_utc))"
log "sıradaki adım: uygulama sürümü yedekten yeniyse 'alembic upgrade head', sonra uygulamayı başlatın"
