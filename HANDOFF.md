# HANDOFF — pencereler arası köprü

Her görev penceresi kapanırken buraya bir blok ekler. Bloklar **newest-first** sıralıdır:
en yeni blok `## Task log (newest-first)` başlığının hemen altındadır.

**Bu dosyayı baştan sona okuma.** Sana gereken en üstteki birkaç bloktur: `head -60 HANDOFF.md`.
Eski bir işi arıyorsan hedefli ara: `grep -n 'tm <id>' HANDOFF.md | head -5`.

Eski kayıtlar: `docs/archive/handoff/` (`grep -rn 'tm <id>' docs/archive/handoff`). Bu dosyada yalnız son 5 görev + açık görevler durur (CONVENTIONS §3).

Blok biçimi `CONVENTIONS.md` §3'te tanımlıdır:

```markdown
## <tm-id> — <başlık> — <done|blocked> — <YYYY-MM-DD>
- Yapıldı: <tek cümle>
- Doğrulama: <hangi kapılar yeşil, kaç test>
- Varsayımlar: <yoksa "yok">
- Sonraki pencereye not: <bir sonraki işin bilmesi gereken tek şey>
```

## Task log (newest-first)

## 191 — 10.1-k Erişilebilirlik: yaşlı ve az gören kullanıcı — done — 2026-10-26
- Yapıldı: yazı ölçeği 16/13 px ve satır yüksekliği 1,6; `--target` 40 px (düğme, alan, sekme, sayfalama, dil menüsü, araç düğmeleri) ve `--target-sm` 36 px (satır içi form); onay kutusu 20 px; `--muted-ink` ≥ 5:1, sekme/süzgeç metni `--ink-soft`; küçük büyük harfli etiketler normal yazı, `th` 2 px alt çizgi + zebra; metin bağlantıları altı çizili; `--focus-ring` 3 px düz halka; araç şeridinde "Büyük yazı" düğmesi (`html[data-text="large"]` %120, `documania-text`, ilk boyamadan önce); "İçeriğe atla" (`#content-start`); `prefers-contrast: more`; üç dil; standart §3/§5 güncel.
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; `tests/web` + `tests/i18n` (-n 6) yeşil. Tam kapı (`--cov`) koşulmadı: yalnız stil/şablon/betik değişti (insan kuralı: uzun kapı beklenmez).
- Varsayımlar: §D126'ya yazıldı — "Büyük yazı" tek kademe (%120), tarayıcı yakınlaştırmasının yerini almaz; skip link hedefi `main` içindeki boş `span` (test işareti `<main class="content">` korunur); zebra `tr:nth-child(even)` seçili/uyarılı satır kurallarının altında kalır.
- Sonraki pencereye not: panel görünümü büyüdü (düğme 40 px, gövde 16 px); ekran görüntüsü karşılaştıran bir test yok. Yerel geliştirme DB'si 0032'deydi — `baslat.bat` göçü kendisi uygular.

## 190 — 10.1-j Giriş kaydı ve "Girişler" sekmesi yalnız root — done — 2026-10-26
- Yapıldı: `login_log` (göç 0034) + `check_login` (neden, tek hata metni/401 ve sahte özet aynı) + `record_login` (savepoint, hata girişi engellemez) + `client_ip` (güvenilen vekilde `CF-Connecting-IP` → `X-Forwarded-For`, `TRUSTED_PROXIES`), giriş başarı/başarısızlık ve çıkış yazılır; `/access-log/logins` (sonuç + kullanıcı süzgeci, 50'lik sayfa, kullanıcı özeti, bilinmeyen adlar tek satır), iki sayfada `nav.tabs`, üç dil, YEDEKLEME notu.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0034), `import app.main`, `python -m app.i18n check`, `docker compose config`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7207 geçti, 6 atlandı, kapsam %98,73, 12 dk 36 sn, exit 0.
- Varsayımlar: §D125 "uygulama kararları (tm 190)"na yazıldı — pasif + doğru parola `inactive`, yanlış `wrong_password`; canlıda app konteynerde olduğu için `docker-compose.yml` özel ağları güvenilen vekile ekler ve `Caddyfile` istemcinin `CF-Connecting-IP`'sini siler; tanınmayan süzgeç değeri "tümü"; önceki oturumun girişte kapanması çıkış sayılmaz.
- Sonraki pencereye not: Faz 1'de açık satır kalmadı (96 ✅, 52/52 Must) — kapanış denetimi görevi açılabilir. YanPC'ye yeniden dağıtımda IP'nin gerçek istemci adresi göründüğü canlıda bir girişle doğrulanmalı (konteyner `TRUSTED_PROXIES`'i compose'dan alır).

## 189 — 10.1-i Yapay zekâ ayarları sayfası yalnız root — done — 2026-10-23
- Yapıldı: `app/web/routers/ai_settings.py` + `ai_settings.html` (sağlayıcı başına kart: anahtar yalnız tanımlı/tanımsız, tek etkin radyo, model ve efor `select`, satır yokken `.env` + "henüz kaydedilmedi"), tek adımlı kayıt (bilinmeyen sağlayıcı/model/efor ve anahtarsız sağlayıcı 422, `N_` metinleri), `AI_SETTINGS_CHANGED`, iki bildirim, root gezinmesinde simgeli `tool-link`, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0033, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7191 geçti, 6 atlandı, kapsam %98,73, exit 0.
- Varsayımlar: §D124 "uygulama kararları (tm 189)"na yazıldı — `require_root` artık Starlette 404'ü atar (bildirim çerezi yok, bilinmeyen yolla birebir), `app.main`'de root kapısı yazma kapısından önce (Kullanıcı'nın `POST`'u 404), `/ai-settings/{rest:path}` 404 yakalayıcısı (307 sızıntısı), değişiklik yoksa olay yok.
- Sonraki pencereye not: Faz 1 52/52 Must; kapanış denetimi görevi açılabilir. Testleri dosya listesiyle elle koşarken `test_access_log_view.py` başka dosyalarla birlikte "fixture 'app' not found" verebiliyor (conftest içe aktarma sırası) — tek başına ve tam kapıda yeşil.

## 188 — 03.8-a Çalışma zamanı yapay zekâ ayarı — done — 2026-10-23
- Yapıldı: `ai_settings` tek satır (göç 0033, `id = 1` ve sağlayıcı CHECK), `app/ai/runtime.py` (`active_settings`, `save_ai_settings`: tek sağlayıcı, anahtarsız sağlayıcı/uyumsuz efor reddi, `from`/`to` değişiklik sözlüğü), `app/ai/model_list.py` (5 Claude + GPT-6 Luna, kaynak/tarih, efor kümesi, istek biçimi), Anthropic `output_config.effort` + modele göre zorlanmış araç ya da `auto` + katı araç, OpenAI `reasoning_effort`; panel (`ActiveAiSettings`), bot ve işçi (`Worker.current_provider`, iş başına) yeniden başlatmasız; olayda `effort`; `.env.example` + README notu.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0033), `import app.main`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7172 geçti, 6 atlandı, kapsam %98,73, exit 0 (ilk koşudaki tek kırmızı `test_models` tablo listesi `ai_settings` eklenerek düzeltildi).
- Varsayımlar: §D124 "uygulama kararları"na yazıldı — Luna'da "varsayılan" da `none` gönderir (Chat Completions işlevi yalnız onunla), Astra/Sol listede yok; sayfa analizi aracı katı değil (`fields` sözlüğü); `auto` biçiminde `max_tokens` ≥ 16000; olayda `effort` yalnız seçiliyken; `AI_SETTINGS_CHANGED` tm 189'a bırakıldı.
- Sonraki pencereye not: tm 189 sayfası `current_choice` / `save_ai_settings(session, settings, AiChoice, actor=)` / `models_for` / `allowed_efforts` / `key_defined` ile kurulur, `AI_SETTINGS_CHANGED`'i dönen sözlükle yazar; `AiSettingsError` mesajları şimdilik çevrilmemiş Türkçe düz metin — sayfada gösterilecekse `N_` ile işaretlenmeli.

## 186 — 15.2-b Üretilen belge yaşam döngüsü — done — 2026-10-23
- Yapıldı: yeniden üretim aynı şablonun etkin belgesini `superseded` yapar; `app/output_templates/lifecycle.py` arşivle/geri al (tek adım, `OUTPUT_ARCHIVED/RESTORED`, `POST …/outputs/{id}/archive|restore`, profilde katlanmış `details.archived-outputs`); 10.5.6 `Uretilen/` K8 yeniden adlandırma (`app/storage/rename.py`), 10.5.9 kalanın `Uretilen/`'ine taşıma (`app/storage/merge.py`), 10.5.13 dosya silme + `deleted` satır + `EMPLOYEE_DELETED.outputs`; `profil.md` "Üretilen belgeler"; üç dil; S29 tam.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7143 geçti, 6 atlandı, kapsam %98,77 — 2 kırmızı (`…plan_d58_verbatim`, D58 bloğu PLAN'da yok) tm 180–185'teki gibi ilgisiz.
- Varsayımlar: §D123 (o)'ya yazıldı — geri alınan belge daha yeni belge varsa `superseded`; yeniden adlandırmada `Uretilen/`'in bütün belgeleri (eski sürüm dahil) K8 adı alır; birleştirmede durum korunur, sıra kalanınkinden devam eder; olay verilerine `outputs` / `superseded` anahtarları eklendi; silme onayının `<N>`'i değişmedi.
- Sonraki pencereye not: FR-MOD-15'in on satırı ✅ (Faz 1: 92 ✅, 49/49 Must; Kapanış AÇIK — kapanış denetimi görevi yeniden açılmalı). Yeni yol parametresi `generated_document_id` `tests/web/test_roles.py` `WORLD_PARAMS`'tadır. D58 testleri için ayrı küçük görev hâlâ gerekli.

## 180, 181, 182, 183, 184, 185, 186 — FR-MOD-15 Hazır şablonlar, çıktı hazırlama ve ek profil alanları açıldı — pending — 2026-10-23 (interaktif oturum: insan isteği)
- Yapıldı: İnsan isteği (2026-10-23, PLAN §D123'te birebir) PRD FR-MOD-15 (15.1.1–15.3.3, 10 satır), §3 R3/R12 notları, §4 sözlük, §5.2 kapsam, 10.1.1 menü sırası, §8.1 üç tablo + `employees` sütunları, §8.2 `Uretilen/` ve `_sablonlar/`, §8.3 olaylar, §8.4 `person` alanları, §8.7 alan haritası şeması, §9 S29, §10 kapsam dışı; MASTER-PROMPT K11/K16/K17 istisnası (insan kararı); PLAN §0 (Faz 1: 82 ✅ · 10 ⬜, 41/49 Must, Kapanış AÇIK), §2 matris, §4.4 tablo, §D123 sözleşme, §G 8 satır; tasks.json tm 180–186 (15.3-a/b, 15.1-a/b/c, 15.2-a/b), bağımlılıklar ve etiketler. Kod değişmedi.
- Doğrulama: PRD §20.6 tablosu değişmedi (`tests/web/test_confirm.py` okur) — test yeşil; `tests/web/test_ui_standard.py`, `tests/i18n` yeşil; sayım komutları (CONVENTIONS §1.3) §0 ile eşit; `node scripts/arsiv-dondur.mjs` dry-run sonucu HANDOFF'un altında.
- Varsayımlar: (1) R3/R12/K11/K17 daraltması insan tarafından 2026-10-23'te açıkça onaylandı (§D123 a, "Onay" cümlesi); veto ihtimali kapandı. (2) Word/Excel şablonu, kutu çizme, toplu üretim, e-imza kapsam dışı bırakıldı (ayrı insan isteği). (3) Pasaport numarası ayrı sütun değil, `employee_identifiers`'tan gösterim. (4) Onay ve üretim tek adımlı (§D61 geri alınabilirlik), §20.6'ya satır yok. (5) Sıra: önce tm 180 (alanlar) ve tm 182 (depo) paralel açılabilir; 181 → 180; 183 → 182; 184 → 183; 185 → 184+180; 186 → 185; (tm 187 kapanış denetimi insan isteğiyle silindi, 2026-10-23; Faz 1 kapanışı yeniden açılacak görevle yapılır).
- Sonraki pencereye not: `task-master next` tm 180 ya da 182'yi verir; `[OPUS-XHIGH]`. Her görev `docs/ARAYUZ-STANDARDI.md`'ye uyar ve `test_ui_standard`'ı yeşil tutar. D58 testleri (tm yok) hâlâ `PLAN.md`'de olmayan D58 bloğunu arıyor — ayrı küçük görev önerisi: testler `docs/archive/plan-kanit/`'ten okusun.
