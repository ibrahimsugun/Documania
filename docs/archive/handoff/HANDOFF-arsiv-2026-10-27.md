# HANDOFF arşivi — 2026-10-27

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

## 193 — 11.9-g Eğitimde çift inceleme (Sol + Sonnet 5.5) ve "AI kararı" yeniden inceleme komutu — done — 2026-10-27
- Yapıldı: iki anahtar tanımlıyken eğitim her belgeyi GPT-6.1 Sol ve Sonnet 5.5'e (`low`) ayrı sorar; ikisi aynı bilinen türü verirse örnek doğrudan `verified` (olay `review: pair`, aktör `system`), yoksa "AI kararı"; `python -m app.training recheck` mevcut "AI kararı" örneklerini aynı kuralla doğrular/taşır/bırakır ve model başına belirteç + tahmini maliyet yazar; `UsageTotals`, `TRAINING_AUTO_CONFIRM`, i18n (en, sr).
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check` exit 0; tests/training + ai + i18n + worker + config + ui_standard 1543 geçti, 4 atlandı. Tam kapı (`--cov`) koşulmadı (insan kuralı). Yerel kuru koşu (5 örnek, gerçek sağlayıcılar): 4 doğrulanır, 1 belirsiz, ~0,25 $.
- Varsayımlar: §D128 — aynı ama farklı türü veren iki model örneği o türe taşır (`move_example`); Yerleştirilemedi/Başarısız öğeler kapsam dışı; çift panelden seçilemez (sabit).
- Sonraki pencereye not: kod YanPC'ye dağıtılmadı ve canlıdaki 405 "AI kararı" örneği henüz incelenmedi (dağıtım izni bekliyor). Dağıtımdan sonra sunucuda `docker compose exec app python -m app.training recheck --limit 10` ile pilot, sonra tamamı (yaklaşık 20 $).


## 192 — 03.3-b OpenAI sağlayıcısı Responses API'ye, GPT-6.1 Sol — done — 2026-10-26
- Yapıldı: `OpenAIProvider` Chat Completions yerine Responses API (`instructions`, `input_image`/`input_text`, düz işlev aracı, `reasoning.effort` yalnız seçilince, `max_output_tokens` ≥ 16000, `incomplete`/ret reddi); model listesinde `gpt-6.1-sol` (`low`–`max`, varsayılan `medium`), `gpt-6-luna` çıktı; varsayılan `OPENAI_MODEL=gpt-6.1-sol`; `TrainingClassification.notes` 250 karakter (istem dahil). Anthropic sağlayıcısı değişmedi.
- Doğrulama: ruff check/format, compileall, `import app.main`, `python -m app.i18n check` exit 0; `tests/ai` + `tests/web/test_ai_settings_page.py` + `tests/test_config.py` + `tests/test_events.py` + `tests/web/test_ui_standard.py` + `tests/db/test_migrations.py` 962 geçti, 4 atlandı. Tam kapı (`--cov`) koşulmadı: değişiklik OpenAI sağlayıcısı ve model listesiyle sınırlı, göç yok (insan kuralı: uzun kapı beklenmez). Gerçek sağlayıcıyla sonda: Sol `low` 4 belge, Sonnet 5.5 (önceden `notes` > 200 ile reddedilen belge) geçti.
- Varsayımlar: §D127'ye yazıldı — ölçüm 14 belge (Luna `none` 9/14 + 3 yanlış; Sonnet 5.5 ve Sol 11/14 + 0 yanlış); `.env`'de `gpt-6-luna` kalan kurulum listede olmayan model olarak çalışmaya devam eder; Terra/Astra eklenmedi.
- Sonraki pencereye not: YanPC'de `ai_settings` satırı ya da `.env` hâlâ `gpt-6-luna` diyorsa kalıcı değişiklik için panelden `/ai-settings`ta OpenAI modelini Sol seçip kaydetmek gerekir (veritabanına dokunulmadı).



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
