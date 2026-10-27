# HANDOFF arşivi — 2026-10-27

Kaynak: HANDOFF.md (canlı dosyadan taşındı, birebir). Blok sayısı: 1.

<!-- bloklar (newest-first) -->

## 189 — 10.1-i Yapay zekâ ayarları sayfası yalnız root — done — 2026-10-23
- Yapıldı: `app/web/routers/ai_settings.py` + `ai_settings.html` (sağlayıcı başına kart: anahtar yalnız tanımlı/tanımsız, tek etkin radyo, model ve efor `select`, satır yokken `.env` + "henüz kaydedilmedi"), tek adımlı kayıt (bilinmeyen sağlayıcı/model/efor ve anahtarsız sağlayıcı 422, `N_` metinleri), `AI_SETTINGS_CHANGED`, iki bildirim, root gezinmesinde simgeli `tool-link`, üç dil.
- Doğrulama: ruff check/format, compileall, temiz SQLite'ta `alembic upgrade head` (→0033, göç yok), `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; tam paralel kapı (`-n 6 --cov`) 7191 geçti, 6 atlandı, kapsam %98,73, exit 0.
- Varsayımlar: §D124 "uygulama kararları (tm 189)"na yazıldı — `require_root` artık Starlette 404'ü atar (bildirim çerezi yok, bilinmeyen yolla birebir), `app.main`'de root kapısı yazma kapısından önce (Kullanıcı'nın `POST`'u 404), `/ai-settings/{rest:path}` 404 yakalayıcısı (307 sızıntısı), değişiklik yoksa olay yok.
- Sonraki pencereye not: Faz 1 52/52 Must; kapanış denetimi görevi açılabilir. Testleri dosya listesiyle elle koşarken `test_access_log_view.py` başka dosyalarla birlikte "fixture 'app' not found" verebiliyor (conftest içe aktarma sırası) — tek başına ve tam kapıda yeşil.
