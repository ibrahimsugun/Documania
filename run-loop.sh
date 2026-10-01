#!/usr/bin/env bash
# =============================================================================
# belgeee — Otonom Görev Döngüsü (CANLI loglamalı)
# Her görev TEMİZ bir Claude Code penceresinde çalışır; durum Task Master + git'te.
# Politika: full-otonom (bypassPermissions) | hata → 1 kez temiz pencerede retry
#           → yine olmazsa görev atlanır (sayılı) | efor görev etiketinden.
# İZLEME: her pencere terminale canlı akar + tam kayıt .loop-logs/'a yazılır.
# ÖNCE OKU: unattended bırakmadan ilk 1-2 turu izle; `claude --help` ile
#           --effort / --permission-mode adlarını sürümünde teyit et.
# =============================================================================
set -uo pipefail

# --- Ayarlar -----------------------------------------------------------------
# Görev başlığındaki etiket hem MODELİ hem EFORU seçer (MASTER-PROMPT §6):
#   [SONNET-HIGH]  → sonnet + high    küçük, tek dosyalık, riski düşük iş
#   [OPUS-HIGH]    → opus   + high
#   [SONNET-XHIGH] → sonnet + xhigh   mekanik, kapsamı net iş
#   [OPUS-XHIGH]   → opus   + xhigh   karar/bütünlük taşıyan iş
#   [OPUS-MAX]     → opus   + max     gruplama, MRZ, eşleştirme, PDF kopyalama,
#                                     kuyruk akışları, kabul senaryosu koşumu
#   [SONNET-MAX]   → sonnet + max     (tanımlı ama kullanılmıyor)
# HIGH gerçekten high'da çalışır — eskiden bu seviye yoktu ve seçicinin "high"
# cevabı xhigh demekti (2026-09-21 kaldırıldı).
# Eski tek boyutlu etiketler geriye dönük çalışır: [MAX] → opus+max,
# [XHIGH], etiketsiz veya tanınmayan etiket → opus+xhigh.
# Model sürümleri sabittir (insan kararı 2026-10-01, PLAN §D88): "opus" Opus 5.5, "sonnet"
# Sonnet 5.5 demektir. `--model`'e takma ad değil tam kimlik verilir; takma ad CLI sürümüne göre
# ailenin en yeni modeline gider ve sürüm sessizce değişebilirdi. Seçici yine "sonnet"/"opus"
# döndürür; aşağıdaki eşleme (`case "$mdl"`) onu bu kimliklere çevirir.
MODEL="claude-opus-5-5"     # varsayılan/geri-uyum modeli (Opus 5.5)
MODEL_BIG="claude-opus-5-5"     # Opus 5.5
MODEL_SMALL="claude-sonnet-5-5" # Sonnet 5.5
EFFORT_MAX="max"            # opus 'max' desteklemiyorsa: "high"
EFFORT_XHIGH="xhigh"        # [*-XHIGH] ve etiketsiz görevler
EFFORT_HIGH="high"          # [*-HIGH] görevler
PERM="bypassPermissions"    # tam otonom, prompt YOK. Güvenli alternatif: "auto"
MAX_TURNS=250
RUNNER_PROMPT_FILE="TASK-RUNNER-PROMPT.md"
PRD_FILE="urun-gereksinim-dokumani-PRD.md"
LOG_DIR=".loop-logs"; mkdir -p "$LOG_DIR"
MAX_CONSEC_ERRORS=5
BACKOFF_SECS=90
ALLOW=""                    # gerekirse: '--allowedTools Bash(git *),Bash(pytest *)'

# Bir görev kapıyı geçemeyip 'blocked' kalırsa iş TERK EDİLMİŞ olur: pick_next
# blocked görev seçmezse döngü sessizce bir sonrakine geçer ve yarım kalan iş bir
# daha ele alınmaz. Böyle görevler (bağımlılıkları kapalıysa) yeniden seçilir —
# ama sonsuz döngü olmasın diye sayılı.
MAX_TASK_ATTEMPTS="${LOOP_MAX_TASK_ATTEMPTS:-2}"
ATTEMPTS_FILE="$LOG_DIR/attempts.tsv"; : >> "$ATTEMPTS_FILE"
# Tek görev başarısızlığı döngüyü durdurmaz, ama ÜST ÜSTE bu kadar pencere
# başarısız olursa sorun tek görevde değil ortamdadır (bozuk kurulum, düşen
# servis, yanlış dal) — o zaman durmak doğrusu.
MAX_CONSEC_TASK_FAILS="${LOOP_MAX_CONSEC_TASK_FAILS:-3}"

# --- Kota kapısı ayarları -----------------------------------------------------
# Bir pencere açılmadan ÖNCE "kalan kota bu işi kaldırır mı?" diye sorulur.
# RESERVE_PCT = kullanıcının elle kullanımı için ayrılan pay.
PANEL_URL="${DASH_URL:-http://127.0.0.1:4545}"
RESERVE_PCT="${LOOP_RESERVE_PCT:-5}"
COST_MAX_PCT="${LOOP_COST_MAX_PCT:-20}"
COST_HIGH_PCT="${LOOP_COST_HIGH_PCT:-10}"
# Panel "elle başlatma önceliği" bildirdiğinde kota bitmişse döngü KAPANMAZ,
# sıfırlanmayı bekler — ama bu üst sınırdan uzun bir bekleyiş gerekiyorsa eski
# davranışa (temiz çıkış + panelden otomatik devam) dönülür.
WAIT_RESET_MAX_MIN="${LOOP_WAIT_RESET_MAX_MIN:-90}"

pick_schema='{"type":"object","properties":{"has_task":{"type":"boolean"},"task_id":{"type":"string"},"model":{"type":"string","enum":["sonnet","opus"]},"effort":{"type":"string","enum":["max","xhigh","high"]},"remaining":{"type":"integer"}},"required":["has_task"]}'
result_schema='{"type":"object","properties":{"status":{"type":"string","enum":["done","blocked"]},"task_id":{"type":"string"},"summary":{"type":"string"}},"required":["status"]}'

log(){ echo "[$(date -u +%H:%M:%S)] $*"; }

# --- Görev deneme sayacı (tur bazlı, koşular arasında kalıcı) -----------------
# Biçim: "<task_id>\t<tur_sayısı>" — awk/grep dışında bağımlılık yok.
attempts_of(){ awk -F'\t' -v id="$1" '$1==id{n=$2} END{print n+0}' "$ATTEMPTS_FILE" 2>/dev/null; }
# Tam ALAN eşleşmesi şart: grep -F "3.4" satır içinde "13.4"e de uyar ve yanlış
# kaydı silerdi. awk $1==id bunu yapısal olarak engeller.
_drop_id(){
  awk -F'\t' -v id="$1" '$1!=id' "$ATTEMPTS_FILE" > "$ATTEMPTS_FILE.tmp" 2>/dev/null || : > "$ATTEMPTS_FILE.tmp"
  mv "$ATTEMPTS_FILE.tmp" "$ATTEMPTS_FILE"
}
bump_attempt(){
  local id="$1" n; n=$(( $(attempts_of "$id") + 1 ))
  _drop_id "$id"; printf '%s\t%s\n' "$id" "$n" >> "$ATTEMPTS_FILE"
}
clear_attempt(){ _drop_id "$1"; }
exhausted_ids(){ awk -F'\t' -v max="$MAX_TASK_ATTEMPTS" '$2>=max{print $1}' "$ATTEMPTS_FILE" 2>/dev/null | paste -sd, - ; }

# --- Canlı akış: stream-json olaylarını insana çevirir; jq yok/hata → raw -----
pretty(){
  if command -v jq >/dev/null 2>&1; then
    jq -r --unbuffered '
      if .type=="system" and .subtype=="init" then "   · pencere açıldı (model \(.model // "?"))"
      elif .type=="system" and .subtype=="api_retry" then "   · API retry #\(.attempt // "?") (\(.error // ""))"
      elif .type=="assistant" then
        ([ .message.content[]?
           | if .type=="text" then "   " + ((.text // "")|gsub("\n";" ")|.[0:180])
             elif .type=="tool_use" then "   → \(.name)"
             else empty end ] | .[])
      elif .type=="result" then "   · [pencere sonucu alındı]"
      else empty end' 2>/dev/null || cat
  else
    cat
  fi
}

# =============================================================================
# Sanity: doğru dizinde miyiz?
if [ ! -f "$PRD_FILE" ] || [ ! -f "$RUNNER_PROMPT_FILE" ]; then
  log "✖ HATA: bu script belgeee proje kökünde çalışmalı ($PRD_FILE + $RUNNER_PROMPT_FILE burada olmalı)."
  exit 1
fi

# Tek seferlik BOOTSTRAP — yalnız .taskmaster HİÇ yoksa. Normalde görev ağacı
# elle kurulur (panel docs §3.9); bu dal yalnız sıfırdan kurulum için vardır.
if [ ! -d ".taskmaster" ]; then
  log "⚙ İlk çalıştırma → kurulum (git + parse-prd + efor etiketleri). Canlı izliyorsun:"
  claude -p "Bu depoyu belgeee otonom yapımına HAZIRLA. Kod YAZMA, yalnız kurulum:
1) Oku: CLAUDE.md, MASTER-PROMPT.md, CONVENTIONS.md, $PRD_FILE.
2) Git: repo yoksa 'git init' + 'git branch -M main'. .gitignore zaten var.
   UZAK DEPO EKLEME — remote tanımlamak insanın işidir.
   İlk commit: doküman + döngü dosyaları → 'chore: bootstrap docs + autonomous loop'.
3) Task Master kurulu değilse kur+ekle; 'task-master parse-prd $PRD_FILE'
   ile PRD'yi görev ağacına çevir (PRD §5 faz sırası + bağımlılıklar).
   ÖNCELİK: yalnız 'high' (Faz 0 · v1 Must) / 'medium' (v1 Should) / 'low' (v2-v3).
   'critical' KULLANMA — o seviye panelin 'düzeltmeye gönder' akışına rezervedir (CONVENTIONS §4.1).
4) MASTER-PROMPT §6'daki [MAX] işlere görev başlığına [MAX] ekle; gerisi [XHIGH].
5) PLAN.md + HANDOFF.md yoksa iskeletlerini oluştur (biçim: CONVENTIONS §1.2).
6) DUR — hiçbir Faz görevini YAPMA." \
    --model "$MODEL" --effort high --permission-mode "$PERM" --max-turns 80 $ALLOW \
    --output-format stream-json --verbose \
    2>>"$LOG_DIR/bootstrap.err" | tee -a "$LOG_DIR/bootstrap.jsonl" | pretty
  if [ ! -d ".taskmaster" ]; then
    log "✖ Bootstrap tamamlanamadı. Bkz. $LOG_DIR/bootstrap.err"
    exit 1
  fi
  log "✓ Kurulum tamam. Döngüye giriliyor."
fi

# --- Sıradaki hazır görev + efor (ucuz, sessiz) ------------------------------
pick_next(){
  local skip skip_line
  skip=$(exhausted_ids)
  if [ -n "$skip" ]; then
    skip_line="ASLA SEÇME: $skip — bu görevlerin deneme hakkı tükendi, elle müdahale bekliyor."
  else
    skip_line="Atlanacak görev yok."
  fi
  claude -p "Task Master (MCP): sıradaki işi seç.

⚠ ÖNCE BUNU OKU — BAĞIMLILIK KİMLİĞİ ÇÖZÜMLEME (en sık yapılan hata):
Bir ALT GÖREVİN 'dependencies' alanındaki çıplak sayılar KARDEŞ ALT GÖREV numaralarıdır,
üst seviye görev id'si DEĞİLDİR. Örnek: 12.4 için dependencies=[\"1\",\"2\"] demek
12.1 ve 12.2 demektir — üst seviyedeki 1 ve 2 numaralı görevler DEĞİL.
KURAL: bir alt görevin bağımlılığını kontrol ederken sayının başına DAİMA üst görev id'sini ekle
(\"<üst_id>.<sayı>\"), zaten nokta içeriyorsa olduğu gibi kullan.

🚧 SEÇİM ÖNCESİ ZORUNLU DOĞRULAMA KAPISI:
Bir görevi seçmeden ÖNCE bağımlılıklarını TEK TEK, yukarıdaki kuralla çözerek oku ve her birinin
durumunun 'done' veya 'cancelled' olduğunu GÖR. Bir tanesi bile açıksa (pending/in-progress/
blocked/deferred) O GÖREVİ SEÇME — başka aday ara. Doğrulamadan seçilen görev pahalı bir pencereyi
boşa yakar. Hiçbir aday doğrulamadan geçmiyorsa has_task=false döndür.

ÖNCELİK SIRASI kesindir:
0) $skip_line
1) Durumu 'in-progress' olan bir görev VEYA alt görev varsa ONU seç. Bu yarım kalmış iştir —
   önceki pencere kota/çökme/elle durdurma yüzünden kapanmış olabilir; protokolün resume adımıyla
   kaldığı yerden devam edilir. Atlanırsa o iş sonsuza kadar asılı kalır.
   ⚠ ALT GÖREVLİ ÜST GÖREV TUZAĞI: bir üst görev, alt görevlerinden yalnız BİRİ bittiği için de
   'in-progress' görünür (CONVENTIONS §4). Bu NORMAL bir ara durumdur ve üst görevin KENDİSİ kod
   yazmaz. Bu yüzden 'in-progress' bir üst görevin alt görevleri VARSA üst görevi DEĞİL, onun ilk
   uygun alt görevini seç: önce 'in-progress' alt görev, o yoksa bağımlılıkları kapalı en küçük
   'pending' alt görev.
1.5) Yoksa: durumu 'blocked' AMA TÜM bağımlılıkları kapalı (done/cancelled) olan bir görev VEYA
   alt görev varsa ONU seç. Bu, kapıyı geçemeyip yarıda bırakılmış iştir; hiçbir şeyi beklemiyor,
   yeniden denenmelidir — yoksa kalıcı olarak terk edilir.
   ⛔ Bağımlılığı HÂLÂ AÇIK olan blocked görevleri SEÇME. Birden çok aday varsa en küçük id.
2) Yoksa priority='critical' olan bir 'pending' görev varsa ONU seç. Bunlar panelin sağlık
   taramasından doğan DÜZELTME görevleridir ve normal backlog'un önüne geçer. En küçük id.
3) Yoksa bağımlılıkları tamamlanmış, durumu 'pending' olanlardan en yüksek öncelikliyi seç
   (sıra: high > medium > low). Bir üst görevin alt görevleri varsa ALT GÖREVİ seç.
İş YAPMA, kod okuma/yazma yok.
Döndür: has_task, task_id, model, effort, remaining (kalan yapılabilir görev sayısı).
MODEL ve EFOR seçilen işin BAŞLIĞINDAKİ ETİKETTEN okunur (MASTER-PROMPT §6):
  [SONNET-HIGH]  -> model=\"sonnet\", effort=\"high\"
  [SONNET-XHIGH] -> model=\"sonnet\", effort=\"xhigh\"
  [SONNET-MAX]   -> model=\"sonnet\", effort=\"max\"
  [OPUS-HIGH]    -> model=\"opus\",   effort=\"high\"
  [OPUS-XHIGH]   -> model=\"opus\",   effort=\"xhigh\"
  [OPUS-MAX]     -> model=\"opus\",   effort=\"max\"
Etiketi OLDUĞU GİBİ uygula — HIGH'ı xhigh'a, XHIGH'ı max'a YÜKSELTME.
Eski tek boyutlu etiketler: [MAX] -> opus+max; [XHIGH], etiket YOK veya tanınmayan etiket -> opus+xhigh." \
    --model "$MODEL" --effort low --permission-mode "$PERM" --max-turns 10 $ALLOW \
    --output-format json --json-schema "$pick_schema" 2>>"$LOG_DIR/pick.err" \
    | jq -c '.structured_output' 2>/dev/null
}

# --- Bir görevi temiz pencerede çalıştır (CANLI akar) ------------------------
stream_task(){
  local id="$1" eff="$2" mdl="${3:-$MODEL}"
  local logf="$LOG_DIR/task-$id.jsonl"
  : > "$logf"
  claude -p "$(cat "$RUNNER_PROMPT_FILE")

# HEDEF TASK: ${id}
Yalnız bu görevi baştan sona tamamla, protokolü uygula, en son JSON sonucu döndür." \
    --model "$mdl" --effort "$eff" --permission-mode "$PERM" --max-turns "$MAX_TURNS" $ALLOW \
    --output-format stream-json --verbose --json-schema "$result_schema" \
    2>>"$LOG_DIR/task-$id.err" | tee -a "$logf" | pretty
}
status_from(){ jq -r 'select(.type=="result") | (.structured_output.status // empty)' "$1" 2>/dev/null | tail -1; }

# --- Durdurma kapısı: panel istediğinde script KENDİ çıkar --------------------
# Panel nazik durdurma istediğinde .loop-logs/STOP-REQUESTED dosyasını bırakır.
# Bu kapı yalnız GÖREV SINIRLARINDA okunur — çalışan bir pencere asla kesilmez.
# Kendi çıkmak, panelin sinyal/taskkill göndermesinden çok daha temizdir: yarım
# dosya, commit'siz değişiklik, "done" işaretlenmemiş görev oluşmaz.
# Kapıyı geçerken dosya SİLİNMEZ, STOP-HONORED'a taşınır: panel böylece
# "istediğim gibi kendi çıktı" ile "çöktü/işi bitti" arasını ayırt eder.
STOP_FLAG="$LOG_DIR/STOP-REQUESTED"
STOP_HONORED="$LOG_DIR/STOP-HONORED"
stop_gate(){
  [ -f "$STOP_FLAG" ] || return 0
  log "⏹ Durdurma isteği görüldü ($1) — görev sınırında temiz çıkılıyor."
  log "  İstek: $(tr -s '[:space:]' ' ' < "$STOP_FLAG" 2>/dev/null | cut -c1-200)"
  mv -f "$STOP_FLAG" "$STOP_HONORED" 2>/dev/null || rm -f "$STOP_FLAG"
  exit 0
}

# --- Kota kapısı: bu pencereyi açmaya yetecek kota var mı? --------------------
# Panelin bekçisi yalnız GÖREVLER ARASINDA durdurabiliyor: bir pencere açıldıktan
# sonra "BİTTİ" satırı gelene kadar kesilmiyor. Yani tek bir pahalı görev (+retry)
# kalan payı aşıp kotayı pencere ORTASINDA bitirebilir — yarım dosya, commit'siz
# iş. Bu kapı kararı pencere AÇILMADAN önce verir.
# 0 → devam · 1 → kota yetmiyor (çağıran temiz çıkar).
# Panel kapalı/okunamıyorsa 0 döner (fail-open) — döngü panele bağımlı değildir.
# $1 = efor · $2 = aşama adı (log için) · $3 = model
quota_gate(){
  local stage="$2" mdl="${3:-$MODEL_BIG}" need used remaining usage resume_at ovr rounds=0
  if [ "$1" = "$EFFORT_MAX" ]; then need=$((COST_MAX_PCT+RESERVE_PCT)); else need=$((COST_HIGH_PCT+RESERVE_PCT)); fi
  # sonnet pencereleri opus maliyetinin küçük bir kesri — kapıyı orantılı gevşet,
  # ama RESERVE_PCT'yi asla yeme (kullanıcının elle kullanımına ayrılmış pay).
  if [ "$mdl" = "$MODEL_SMALL" ]; then need=$(( (need - RESERVE_PCT) / 3 + RESERVE_PCT )); fi

  while : ; do
    # Bekleyişten SONRAKİ ölçüm taze olmalı: panel kullanımı önbellekler,
    # sıfırlanmanın hemen ardından bayat (yüksek) değer dönerse boşuna bir tur
    # daha beklenirdi.
    if [ "$rounds" -gt 0 ]; then usage=$(curl -s --max-time 8 "$PANEL_URL/api/usage?fresh=1" 2>/dev/null)
    else usage=$(curl -s --max-time 5 "$PANEL_URL/api/usage" 2>/dev/null); fi
    used=$(printf '%s' "$usage" | jq -r '.fiveHour.utilization // empty' 2>/dev/null)
    case "$used" in ''|*[!0-9]*) return 0 ;; esac   # okunamadı → eski davranış

    remaining=$((100-used))
    [ "$remaining" -ge "$need" ] && return 0

    resume_at=$(printf '%s' "$usage" | jq -r '.resumeAtIfStopped // empty' 2>/dev/null)
    ovr=$(printf '%s' "$usage" | jq -r '.manualOverride.active // false' 2>/dev/null)

    # Öncelik varken: kapanmak yerine sıfırlanmayı bekle, sonra kotayı yeniden ölç.
    if [ "$ovr" = "true" ] && [ "$rounds" -lt 5 ] && wait_for_reset "$stage" "$resume_at" "$remaining" "$need"; then
      rounds=$((rounds+1))
      continue
    fi

    if [ -n "$resume_at" ]; then
      curl -s --max-time 5 -X POST "$PANEL_URL/api/schedules" \
        -H 'content-type: application/json' \
        -d "{\"atISO\":\"$resume_at\",\"note\":\"kota kapısı — $stage\"}" >/dev/null 2>&1
    fi
    log "⏸ Kota kapısı ($stage): kalan %$remaining < gerekli %$need (efor $1, rezerv %$RESERVE_PCT)."
    log "  Döngü temiz duruyor. Otomatik devam: ${resume_at:-YOK — panel kapalı, elle başlat}"
    return 1
  done
}

# Sıfırlanmayı bekle. 0 → beklendi (kota yeniden ölçülmeli) · 1 → beklenemez.
wait_for_reset(){
  local stage="$1" target_iso="$2" remaining="$3" need="$4" target now wait_sec next_note
  [ -n "$target_iso" ] || return 1
  target=$(date -u -d "$target_iso" +%s 2>/dev/null) || return 1
  [ -n "$target" ] || return 1
  now=$(date -u +%s)
  wait_sec=$((target-now))
  [ "$wait_sec" -le 0 ] && return 0                                  # zaten geçmiş → hemen ölç
  [ "$wait_sec" -gt $((WAIT_RESET_MAX_MIN*60)) ] && return 1         # çok uzun → temiz çıkış

  log "⏳ Kota kapısı ($stage): kalan %$remaining < gerekli %$need — ama ELLE BAŞLATMA ÖNCELİĞİ var."
  log "   Döngü KAPANMIYOR: sıfırlanma bekleniyor ($target_iso, ~$((wait_sec/60)) dk). Beklerken pencere açılmaz."
  next_note=$((now+300))
  while : ; do
    now=$(date -u +%s)
    [ "$now" -ge "$target" ] && break
    # Beklerken de durdurulabilmeli.
    stop_gate "kota sıfırlanması beklenirken"
    if [ "$now" -ge "$next_note" ]; then
      log "⏳ Sıfırlanmaya ~$(( (target-now)/60 )) dk (kota bekleniyor, döngü ayakta)."
      next_note=$((now+300))
    fi
    sleep 10
  done
  log "⏳ Sıfırlanma geldi — kota yeniden ölçülüyor, döngü kaldığı yerden sürüyor."
  return 0
}

# Koşu başında kalmış bayrak yeni koşuyu anında kapatmasın (panel de temizler).
rm -f "$STOP_FLAG" "$STOP_HONORED"

# =============================================================================
consec_errors=0; iteration=0; consec_task_fails=0
log "▶▶ Döngü başladı. Canlı akış aşağıda; tam kayıt: $LOG_DIR/"

while true; do
  iteration=$((iteration+1))
  stop_gate "tur başı"

  pick=$(pick_next)
  if [ -z "${pick:-}" ] || [ "$pick" = "null" ]; then
    consec_errors=$((consec_errors+1))
    log "⚠ Sıradaki task alınamadı (muhtemelen rate-limit/transient). Hata #$consec_errors, ${BACKOFF_SECS}s bekleniyor..."
    [ "$consec_errors" -ge "$MAX_CONSEC_ERRORS" ] && { log "✖ Üst üste $MAX_CONSEC_ERRORS hata. Döngü durdu."; exit 1; }
    sleep "$BACKOFF_SECS"; continue
  fi
  consec_errors=0

  has_task=$(echo "$pick" | jq -r '.has_task // false')
  if [ "$has_task" != "true" ]; then
    log "✅ Hazır task kalmadı. Plan tamam (kalanlar bloke/beklemede olabilir). Döngü bitti."
    break
  fi
  task_id=$(echo "$pick" | jq -r '.task_id // "?"')
  remaining=$(echo "$pick" | jq -r '.remaining // "?"')
  eff_label=$(echo "$pick" | jq -r '.effort // "xhigh"')
  case "$eff_label" in
    max)  eff="$EFFORT_MAX" ;;
    high) eff="$EFFORT_HIGH" ;;
    *)    eff="$EFFORT_XHIGH" ;;
  esac
  mdl=$(echo "$pick" | jq -r '.model // empty')
  case "$mdl" in sonnet) mdl="$MODEL_SMALL" ;; opus) mdl="$MODEL_BIG" ;; *) mdl="$MODEL_BIG" ;; esac

  # KAPI 1 — görev penceresi açılmadan önce
  quota_gate "$eff" "görev öncesi" "$mdl" || exit 0
  # pick_next sürerken durdurma isteği gelmiş olabilir — pahalı pencereyi
  # açmadan önce son kez bak.
  stop_gate "görev penceresi açılmadan"

  log "──────────────────────────────────────────────────────────────"
  log "▶ Task $task_id  (model=$mdl, effort=$eff, kalan≈$remaining)  — tek sürekli akış başlıyor (build→doğrulama→kapanış)"
  start=$SECONDS
  stream_task "$task_id" "$eff" "$mdl"
  status=$(status_from "$LOG_DIR/task-$task_id.jsonl"); [ -z "$status" ] && status="blocked"

  if [ "$status" != "done" ]; then
    # RETRY'DE MODEL YÜKSELTME: sonnet penceresi kapıyı geçemediyse sorun büyük
    # olasılıkla yetenek sınırıdır — aynı modelle ikinci kez denemek çoğu zaman
    # aynı duvara toslar. Retry opus ile açılır. Zaten opus'sa değişmez.
    if [ "$mdl" = "$MODEL_SMALL" ]; then
      log "⇧ Retry için model yükseltiliyor: $MODEL_SMALL → $MODEL_BIG."
      mdl="$MODEL_BIG"
    fi

    # KAPI 2 — retry penceresi açılmadan önce. Bekçinin yapısal olarak giremediği
    # tek nokta burası: iki deneme arasında "BİTTİ" satırı yok.
    quota_gate "$eff" "retry öncesi" "$mdl" || exit 0

    log "⟳ Task $task_id ilk turda geçemedi ($status). 1 kez yeniden deneniyor (temiz pencere, model=$mdl)..."
    stream_task "$task_id" "$eff" "$mdl"
    status=$(status_from "$LOG_DIR/task-$task_id.jsonl"); [ -z "$status" ] && status="blocked"
  fi

  el=$((SECONDS-start))
  if [ "$status" = "done" ]; then
    clear_attempt "$task_id"; consec_task_fails=0
    log "✔ Task $task_id BİTTİ (+commit +done) — ${el}s. Sıradakine geçiliyor."
  else
    consec_task_fails=$((consec_task_fails+1))
    bump_attempt "$task_id"
    tries=$(attempts_of "$task_id")
    if [ "$tries" -ge "$MAX_TASK_ATTEMPTS" ]; then
      log "✖ Task $task_id $tries tam turda da kontrol kapısını geçemedi (${el}s). ATLANIYOR — elle müdahale gerek."
      log "  İncele:  $LOG_DIR/task-$task_id.err   ve   HANDOFF.md"
      log "  Sayaç sıfırlamak için: $ATTEMPTS_FILE içinden '$task_id' satırını sil."
    else
      log "✖ Task $task_id bu turda geçemedi (${el}s) — tur $tries/$MAX_TASK_ATTEMPTS. Sıradaki turda yeniden denenecek."
    fi
    if [ "$consec_task_fails" -ge "$MAX_CONSEC_TASK_FAILS" ]; then
      log "✖✖ Üst üste $consec_task_fails görev penceresi başarısız. Sorun tek görevde değil — döngü DURDU."
      log "  Ortamı kontrol et (kurulum/testler/dal), sonra panelden yeniden başlat."
      exit 2
    fi
  fi
done
