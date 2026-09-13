# HANDOFF — pencereler arası köprü

Her görev penceresi kapanırken buraya bir blok ekler. Bloklar **newest-first** sıralıdır:
en yeni blok `## Task log (newest-first)` başlığının hemen altındadır.

**Bu dosyayı baştan sona okuma.** Sana gereken en üstteki birkaç bloktur: `head -60 HANDOFF.md`.
Eski bir işi arıyorsan hedefli ara: `grep -n 'tm <id>' HANDOFF.md | head -5`.

Blok biçimi `CONVENTIONS.md` §3'te tanımlıdır:

```markdown
## <tm-id> — <başlık> — <done|blocked> — <YYYY-MM-DD>
- Yapıldı: <tek cümle>
- Doğrulama: <hangi kapılar yeşil, kaç test>
- Varsayımlar: <yoksa "yok">
- Sonraki pencereye not: <bir sonraki işin bilmesi gereken tek şey>
```

## Task log (newest-first)

## 2 — 00.2 Ortam değişkeni tabanlı yapılandırma — done — 2026-09-14
- Yapıldı: pydantic-settings tabanlı `Settings` (`app/config.py`) — zorunlu `database_url`, varsayılanlı `app_env`/`data_dir`, `.env` veya ortam değişkeninden okunur; `.env.example` şablonu eklendi.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (6 test, +4 yeni), `--cov-fail-under=70` (%93); `import app.main` exit 0. `alembic upgrade head` henüz yok (00.3.2), §1.1 gereği atlandı (00.1'de de aynı gerekçeyle atlanmıştı).
- Varsayımlar: `app/config.py` bilinçli olarak `app/main.py`'a bağlanmadı — ÇIKTI yalnız `app/config.py` + `.env.example`; gerçek kullanım (DB engine, storage yolu) 00.3/00.4'ün işi. Gerçek bir `.env` dosyası oluşturulmadı; testler kendi ortamını izole kurar (`_env_file` override).
- Sonraki pencereye not: 00.3 (veri modeli/göç) ve 00.4 (depolama) `app.config.get_settings()` ile `database_url`/`data_dir` alanlarını tüketecek — yeni ayar gerekirse `Settings`e alan ekleyin, başka yerde ortam değişkeni okumayın.

## 1 — 00.1 Uygulama iskeleti, test ve kapsayıcı altyapısı — done — 2026-09-14
- Yapıldı: `pyproject.toml` (Python 3.12, FastAPI/uvicorn; dev: pytest, pytest-cov, httpx2, ruff), `app/main.py` (`create_app()` + `GET /health`), `tests/` (conftest `client` fiksturu), `Dockerfile` (python:3.12-slim, root olmayan kullanıcı, HEALTHCHECK), `docker-compose.yml`, `.dockerignore` (data/ imaja girmez).
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (2 test), `--cov-fail-under=70` (%100), `import app.main` hepsi exit 0; `docker compose up -d --build` → healthy, `/health` 200 `{"status":"ok"}`. `alembic upgrade head` henüz yok (00.3.2), §1.1 gereği atlandı.
- Varsayımlar: Yerel ortam `uv venv --python 3.12 .venv` + `uv pip install -e ".[dev]"`; Starlette 1.x TestClient için `httpx` yerine `httpx2` kullanıldı (Starlette'in önerisi).
- Sonraki pencereye not: Konteyner `belgeee` (uid 10001) kullanıcısıyla çalışır ve `/srv/data` yazılabilir değildir — veri dizini/volume ekleyen görev sahipliği ayarlamalı.

## 0 — kurulum — done — 2026-09-05
- Yapıldı: Belge sözleşmesi kuruldu (PRD, MASTER-PROMPT, CONVENTIONS, CLAUDE, TASK-RUNNER-PROMPT,
  run-loop.sh, PLAN.md, görev ağacı). Henüz kod yazılmadı.
- Doğrulama: PLAN.md panel biçimine uygun (155 gereksinim satırı); `.taskmaster/tasks/tasks.json`
  92 görev; §G düz tablosu ile görev başlıkları birebir eşleşiyor. Kararlar PRD §12'ye
  karar tablosu olarak yazıldı; [OPUS-MAX] görev sayısı 4.
- Varsayımlar: C1 (geliştirmede SQLite), C2 (uzak git deposu yok, push atlanır) — PLAN §C.
- Sonraki pencereye not: İlk iş **tm 1 — `00.1` Uygulama iskeleti**. DoD kapısını kuran görev
  odur; `CONVENTIONS.md` §1.1'e göre kapı o görevde kurulduğu kadarıyla koşulur.
