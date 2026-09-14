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

## 5 — 00.5 Olay logu altyapısı — done — 2026-09-14
- Yapıldı: `app/events.py` — PRD §8.3'teki 37 olay türü için `EventType(enum.StrEnum)`, `record_event` (bir olayı `events` tablosuna yazar) ve `event_context` (contextvar tabanlı, upload/file/page alanlarını içteki `record_event` çağrılarına açıkça verilmedikçe otomatik taşıyan, iç içe kullanımda belirtilmeyen alanları dıştan miras alan bağlam yöneticisi).
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (147 geçti, +7 olay testi), kapsam %98.71 (`app/events.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: yok.
- Sonraki pencereye not: Olay atan her pipeline adımı `record_event(session, EventType.X, ...)` çağırır; upload/file/page bağlamını elle her çağrıda tekrarlamak yerine ilgili blok `with event_context(upload_id=..., file_id=..., page_index=...):` ile sarılır.

## 4 — 00.4 Depolama katmanı: yol, slug, adlandırma, atomik yazma — done — 2026-09-14
- Yapıldı: `app/storage/` — `DataLayout` (§8.2 yolları, açılışta `prepare_data_dir` ile FastAPI lifespan'de ağaç kurulumu), `slugify` (Türkçe/Kiril/Arap → `[A-Za-z0-9_-]`), K8 adları (`employee_folder_name`, `document_stem`, `-2`/`-3`), atomik yazma (`write_file`/`copy_file`/`write_sequenced` sabit bağla üzerine yazmadan, `replace_file` türev dosyalar için, SHA-256 yazarken); kapsayıcıya `/srv/data` volume + `DATABASE_URL` eklendi.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (140 geçti, +104 depolama durumu; 2 PG testi atlandı), kapsam %98.9, temiz SQLite'ta `alembic upgrade head`, `import app.main`, `docker compose config` exit 0; `docker compose up --build` → healthy + `/srv/data` ağacı; POSIX yazma yolu Linux kapsayıcısında elle denendi.
- Varsayımlar: PLAN §C6 (slug çeviri tabloları ve harf büyüklüğü, 64 karakter sınırı, sıra ekinde uzantıdan bağımsız + ilk boş ek, hard link zorunluluğu, 1 saatlik geçici dosya temizliği).
- Sonraki pencereye not: Yol yalnız `DataLayout` yöntemleriyle kurulur; orijinal/çıktı dosyası daima `write_file`/`copy_file`/`write_sequenced` ile yazılır (`StoredFile.sha256` + `sequence_no` döner), `replace_file` yalnız `profil.md`/`reason.json`/katalog dışa aktarımı içindir. Uygulama artık açılışta `DATABASE_URL` ister (import için gerekmez).

## 3 — 00.3 Veri modeli ve göç altyapısı — done — 2026-09-14
- Yapıldı: §8.1'deki 16 tablo `app/db/models.py`'da (UTC zaman tipi, sabit kısıt adları, silme kaskadı yok) + `app/db/session.py` (motor/oturum, `get_session` FastAPI bağımlılığı) + Alembic zinciri `0001` + `allocate_employee_number` (E0001, eşzamanlılıkta çakışmasız).
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (36 geçti, 2 PG testi ortam değişkeni yokken atlanır), kapsam %99, temiz SQLite'ta `alembic upgrade head` exit 0, `import app.main` exit 0; geçici `postgres:16-alpine` üzerinde `alembic upgrade head` + `alembic check` + PG testleri (`BELGEEE_TEST_POSTGRES_URL`) yeşil.
- Varsayımlar: PLAN §C3–C5 (metin `uploads.id`, CHECK yalnız PRD'de harfiyen yazılı kümelerde, SQLite `BEGIN IMMEDIATE`, `queue_items`'ın plan sürümü bağı); §D4: PRD "15 tablo" der ama §8.1'de 16 tablo var, 16'sı modellendi.
- Sonraki pencereye not: Çalışan eklerken numarayı `allocate_employee_number(session)` ile al ve `Employee`'yi aynı işlemde ekleyip commit et; şema değişikliği yalnız yeni Alembic göçüyle (`alembic revision --autogenerate`, ruff kancası kurulu), SQLite'ta açık oturum yazarları beklettiği için oturumları kısa tutun.

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
