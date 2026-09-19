#!/usr/bin/env bash
# belgeee — gece yedeği (PRD 13.4.2).
#
# Veritabanının tutarlı bir dökümünü ve `DATA_DIR` dizinini (Inbox, çalışan klasörleri, katalog)
# tek bir `belgeee-<UTC zaman>.tar.gz` arşivine alır, yanına SHA-256 dosyası yazar, isteğe bağlı
# olarak sunucu dışına kopyalar ve eski yedekleri budar. Belgeler yalnız kopyalanır, hiçbir belge
# değiştirilmez (K10, K11). Geri yükleme: `scripts/restore.sh`; prosedür: `docs/YEDEKLEME.md`.
#
# Ayarlar (ortam değişkeni ya da `.env`):
#   DATABASE_URL         sqlite:///... ya da postgresql[+sürücü]://kullanıcı:parola@sunucu/veritabanı
#   DATA_DIR             veri dizini (varsayılan: data)
#   BACKUP_DIR           yedeklerin yazıldığı yerel dizin (varsayılan: backups; DATA_DIR'in dışında)
#   BACKUP_KEEP_DAYS     bu günden eski yedekler silinir; 0 = silme (varsayılan: 14)
#   BACKUP_COPY_DIR      sunucu dışı kopya için dizin (bağlı bir ağ paylaşımı, harici disk)
#   BACKUP_SCP_TARGET    sunucu dışı kopya için `kullanıcı@sunucu:/dizin` (scp ile)
# Çıkış kodu 0: yedek alındı (sunucu dışı hedef tanımlıysa oraya da kopyalandı).
#
# Gece çalıştırma (sunucuda, uygulamanın depo kökünden): docs/YEDEKLEME.md'deki cron satırı.

set -euo pipefail
umask 077

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/backup-lib.sh
. "$here/backup-lib.sh"

find_python
require_gnu_tar

database_url="$(env_value DATABASE_URL)"
[ -n "$database_url" ] || die "DATABASE_URL tanımlı değil"
data_dir="$(env_value DATA_DIR)"
data_dir="${data_dir:-data}"
backup_dir="$(env_value BACKUP_DIR)"
backup_dir="${backup_dir:-backups}"
keep_days="$(env_value BACKUP_KEEP_DAYS)"
keep_days="${keep_days:-14}"
copy_dir="$(env_value BACKUP_COPY_DIR)"
scp_target="$(env_value BACKUP_SCP_TARGET)"

case "$keep_days" in
  '' | *[!0-9]*) die "BACKUP_KEEP_DAYS negatif olmayan bir tam sayı olmalı: $keep_days" ;;
esac
[ -d "$data_dir" ] || die "veri dizini yok: $data_dir"
# `tar -C` art arda verilince birikir (göreli yol öncekine göre çözülür): mutlak yol gerekir.
data_abs="$(cd "$data_dir" && pwd)"
mkdir -p "$backup_dir"
# Yedek veri dizininin içine düşerse her gece bir önceki yedeği de içine alır ve şişer.
if [ -n "$(relative_inside "$backup_dir" "$data_dir")" ]; then
  die "BACKUP_DIR ($backup_dir) veri dizininin ($data_dir) içinde olamaz"
fi

parse_database_url "$database_url"

stage="$(mktemp -d)"
partial=""
cleanup() {
  rm -rf "$stage"
  [ -z "$partial" ] || rm -f "$partial"
}
trap cleanup EXIT

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="belgeee-$stamp.tar.gz"
final="$backup_dir/$name"
[ ! -e "$final" ] || die "bu saniyeye ait yedek zaten var: $final"

mkdir "$stage/db"
data_files="$(count_files "$data_dir")"
excludes=()
case "$DB_KIND" in
  sqlite)
    log "SQLite anlık görüntüsü alınıyor"
    db_file="db/belgeee.sqlite"
    sqlite_snapshot "$DB_PATH" "$stage/$db_file" || die "SQLite anlık görüntüsü alınamadı"
    # Veritabanı veri dizininin içindeyse canlı dosya arşive girmez: yerine tutarlı anlık görüntü var.
    inside="$(relative_inside "$DB_PATH" "$data_dir")"
    if [ -n "$inside" ]; then
      for suffix in "" -wal -shm -journal; do
        excludes+=("--exclude=./$inside$suffix")
        [ ! -f "$data_abs/$inside$suffix" ] || data_files=$((data_files - 1))
      done
    fi
    ;;
  postgres)
    command -v pg_dump >/dev/null 2>&1 || die "pg_dump bulunamadı (postgresql-client kurulu olmalı)"
    log "PostgreSQL dökümü alınıyor"
    db_file="db/belgeee.pgdump"
    pg_dump --format=custom --no-owner --no-privileges --file="$stage/$db_file" ||
      die "pg_dump başarısız"
    ;;
esac

db_sha="$(sha256_of "$stage/$db_file")"
cat >"$stage/MANIFEST.txt" <<MANIFEST
belgeee-backup=1
created_utc=$stamp
db_kind=$DB_KIND
db_file=$db_file
db_sha256=$db_sha
data_files=$data_files
MANIFEST

partial="$backup_dir/.$name.partial"
log "arşiv yazılıyor: $name"
tar_status=0
tar --force-local --create --gzip --file="$partial" \
  --transform='s,^\./,data/,' "${excludes[@]+"${excludes[@]}"}" \
  -C "$stage" MANIFEST.txt db -C "$data_abs" . || tar_status=$?
# 1: okunurken değişen dosya var (yedek sürerken yükleme olmuş); ≥2: gerçek hata.
if [ "$tar_status" -eq 1 ]; then
  log "UYARI: bazı dosyalar arşivlenirken değişti (yedek sürerken yükleme olmuş olabilir)"
elif [ "$tar_status" -ne 0 ]; then
  die "tar başarısız (çıkış $tar_status)"
fi
tar --force-local --list --gzip --file="$partial" >/dev/null || die "arşiv okunamıyor"

mv "$partial" "$final"
partial=""
archive_sha="$(sha256_of "$final")"
printf '%s  %s\n' "$archive_sha" "$name" >"$final.sha256"
log "yedek hazır: $final ($data_files dosya, veritabanı: $DB_KIND)"

copied=0
if [ -n "$copy_dir" ]; then
  mkdir -p "$copy_dir"
  cp "$final" "$copy_dir/.$name.partial"
  [ "$(sha256_of "$copy_dir/.$name.partial")" = "$archive_sha" ] ||
    die "sunucu dışı kopya bozuk: $copy_dir"
  mv "$copy_dir/.$name.partial" "$copy_dir/$name"
  cp "$final.sha256" "$copy_dir/$name.sha256"
  log "sunucu dışı kopya yazıldı: $copy_dir"
  copied=1
fi
if [ -n "$scp_target" ]; then
  scp -q -- "$final" "$final.sha256" "$scp_target" || die "scp başarısız: $scp_target"
  log "sunucu dışı kopya gönderildi: $scp_target"
  copied=1
fi
[ "$copied" -eq 1 ] || log "UYARI: sunucu dışı hedef tanımlı değil; yedek yalnız bu sunucuda"

# Budama en son ve yalnız her şey başardıysa: yeni yedek alınamayan gece eskiler korunur.
if [ "$keep_days" -gt 0 ]; then
  for dir in "$backup_dir" "$copy_dir"; do
    [ -n "$dir" ] && [ -d "$dir" ] || continue
    find "$dir" -maxdepth 1 -type f -name 'belgeee-*.tar.gz*' -mtime +"$keep_days" -print -delete |
      while read -r old; do log "eski yedek silindi: $old"; done
  done
fi
