#!/usr/bin/env bash
# Documania — eğitim malzemesinin yedeği (PRD 13.4.2; PLAN.md §D129).
#
# Eğitim malzemesi (`KnownDocuments/examples`, `_egitim`, `_referans`) birkaç GB tutar ve gece
# arşivine (`scripts/backup.sh`) girmez. Bu betik onu ARTIMLI ve SIKIŞTIRMASIZ kopyalar (`rsync`):
# ilk koşu hepsini, sonrakiler yalnız yeni ya da değişen dosyaları taşır. Hiçbir şey silinmez —
# ne kaynakta ne hedefte (`--delete` yok): bağlanamayan bir hacim boş görünse bile hedefteki yedek
# yerinde kalır. Boş ya da olmayan kaynak dizin atlanır.
#
# Kullanım:
#   scripts/backup-material.sh              kaynaktan hedefe kopyalar
#   scripts/backup-material.sh --restore    hedeften kaynağa geri koyar; var olan dosyanın üzerine YAZMAZ
#
# Ayarlar (ortam değişkeni ya da `.env`):
#   BACKUP_MATERIAL_DIR      hedef: yerel dizin (harici disk, ağ paylaşımı) ya da `kullanıcı@sunucu:/dizin`
#   DATA_DIR                 veri dizini (varsayılan: data); kaynaklar varsayılan olarak onun altındadır
#   MATERIAL_EXAMPLES_DIR    `examples` kaynağı   (varsayılan: $DATA_DIR/KnownDocuments/examples)
#   MATERIAL_TRAINING_DIR    `_egitim` kaynağı    (varsayılan: $DATA_DIR/KnownDocuments/_egitim)
#   MATERIAL_REFERENCE_DIR   `_referans` kaynağı  (varsayılan: $DATA_DIR/KnownDocuments/_referans)
# Docker Compose'ta ilk ikisi ayrı hacimlerdir; yolları `docker volume inspect <proje>_known_examples
# --format '{{ .Mountpoint }}'` (ve `_known_training`) verir. Çıkış kodu 0: kopya tamam.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/backup-lib.sh
. "$here/backup-lib.sh"

restore=0
for arg in "$@"; do
  case "$arg" in
    --restore) restore=1 ;;
    *) die "bilinmeyen seçenek: $arg (kullanım: backup-material.sh [--restore])" ;;
  esac
done

command -v rsync >/dev/null 2>&1 || die "rsync bulunamadı (kurulu olmalı)"
find_python

dest="$(env_value BACKUP_MATERIAL_DIR)"
[ -n "$dest" ] || die "BACKUP_MATERIAL_DIR tanımlı değil (yerel dizin ya da kullanıcı@sunucu:/dizin)"
data_dir="$(env_value DATA_DIR)"
data_dir="${data_dir:-data}"

remote=0
case "$dest" in
  *:*) remote=1 ;;
esac

source_for() {
  local override
  case "$1" in
    examples) override="$(env_value MATERIAL_EXAMPLES_DIR)" ;;
    _egitim) override="$(env_value MATERIAL_TRAINING_DIR)" ;;
    _referans) override="$(env_value MATERIAL_REFERENCE_DIR)" ;;
  esac
  printf '%s' "${override:-$data_dir/KnownDocuments/$1}"
}

[ "$remote" -eq 1 ] || mkdir -p "$dest"
failed=0
for name in examples _egitim _referans; do
  src="$(source_for "$name")"
  if [ "$remote" -eq 0 ] && [ -n "$(relative_inside "$dest" "$src")" ]; then
    die "BACKUP_MATERIAL_DIR ($dest) kaynağın ($src) içinde olamaz"
  fi
  if [ "$restore" -eq 0 ]; then
    if [ ! -d "$src" ] || [ -z "$(ls -A "$src" 2>/dev/null)" ]; then
      log "UYARI: $name kaynağı yok ya da boş, atlandı: $src"
      continue
    fi
    status=0
    rsync -a --partial "$src/" "$dest/$name/" || status=$?
  else
    if [ "$remote" -eq 0 ] && [ ! -d "$dest/$name" ]; then
      log "hedefte $name yok, atlandı"
      continue
    fi
    mkdir -p "$src"
    status=0
    rsync -a --partial --ignore-existing "$dest/$name/" "$src/" || status=$?
  fi
  # 24: kopya sürerken kaynakta kaybolan dosya (yükleme/taşıma); yedek yine geçerlidir.
  if [ "$status" -eq 0 ] || [ "$status" -eq 24 ]; then
    log "$name: tamam"
  else
    log "HATA: $name kopyalanamadı (rsync çıkış $status)"
    failed=1
  fi
done
[ "$failed" -eq 0 ] || exit 1
if [ "$restore" -eq 1 ]; then
  log "geri yükleme tamam; dosyalar uygulama kullanıcısına ait olmalı (Docker: chown -R 10001:10001)"
else
  log "eğitim malzemesi yedeği hazır: $dest"
fi
