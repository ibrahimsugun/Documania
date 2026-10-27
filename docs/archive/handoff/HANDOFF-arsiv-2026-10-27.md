# HANDOFF arşivi — 2026-10-27

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

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
