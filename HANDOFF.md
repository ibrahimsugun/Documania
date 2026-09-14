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

## 12 — 01.6 Parti durumu sorgulama — done — 2026-09-14
- Yapıldı: `GET /api/uploads/{upload_id}` (`app/web/routers/uploads.py`) — bilinmeyen `upload_id` için 404, aksi halde parti `status`, `files` listesi (ad/mime/sha256/page_count/is_duplicate) ve `progress` (`total_files`, `rendered_files`) döner.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (287 geçti, +4 durum sorgulama; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.23 (`app/web/routers/uploads.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: PRD "ilerleme" alanının biçimini vermiyor; sayfa üretimi (02.x) henüz yok, bu yüzden `progress.rendered_files` en az bir `Page` satırı oluşmuş dosya sayısı olarak dar tutuldu (PLAN.md §C9).
- Sonraki pencereye not: `UploadFile.page_count` bu görevde doldurulmadı (hâlâ `null`) — 02.x sayfa üretimi geldiğinde hem onu hem `progress.rendered_files`'ı besleyecek, response şemasını değiştirmeye gerek yok.

## 11 — 01.5 Inbox'a değişmez yazma — done — 2026-09-14
- Yapıldı: `write_to_inbox(layout, upload_id, name, content)` (`app/storage/inbox.py`) — Inbox yazımını tek bir yüzeye topladı; `write_file`'ın sabit bağ garantisi sayesinde aynı `Inbox/<upload_id>/<name>` yoluna ikinci yazma `FileExistsError` ile reddedilir. Yükleme uç noktası artık elle `inbox_dir / name` kurup `write_file` çağırmak yerine bunu kullanıyor.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (283 geçti, +3 Inbox durumu; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.05 (`app/storage/inbox.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: yok — davranış (K10 immutable yazma) zaten tm 7'de doğru kurulmuştu, bu görev onu adlandırılmış/test edilmiş bir yüzeye çıkardı.
- Sonraki pencereye not: Inbox'a yazan her yeni kod `app.storage.write_to_inbox` çağırmalı, doğrudan `write_file(layout.upload_inbox_dir(...) / name, ...)` kurmamalı.

## 10 — 01.4 Tekrar yükleme tespiti (SHA-256) — done — 2026-09-14
- Yapıldı: `find_original_by_sha256` (K10) — aynı SHA-256'nın daha önce yüklenmiş özgün satırını bulur (zincirlenmeyi önlemek için yalnız `is_duplicate_of IS NULL` satırlara bakar); yükleme uç noktasına bağlandı — eşleşme varsa dosya yine değişmeden Inbox'a yazılır, `UploadFile.is_duplicate_of` kök satıra işaret eder, `FILE_UPLOADED` yerine `FILE_DUPLICATE` olayı (`duplicate_of_file_id` verisiyle) yazılır.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (280 geçti, +6 tekrar tespiti durumu; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.22 (`app/storage/hashing.py` ve `app/web/routers/uploads.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: Analiz boru hattı henüz yok (Faz 0'ın sonraki bir görevi); bu görev yalnız tespit + işaretleme + olay logunu yapar, "analiz edilmez" kısmı ileride `is_duplicate_of` alanını okuyacak analiz adımının sorumluluğu. Görevin ÇIKTI listesindeki `app/storage/hashing.py` yeni bir dosya olarak açıldı — SHA-256 hesaplama zaten `app/storage/atomic.py`'de vardı, bu modül yalnız DB'de eşleşen özgün satırı arayan sorguyu taşır.
- Sonraki pencereye not: Tekrar kontrolü dosya adına değil yalnız içerik SHA-256'sına bakar, farklı partiler arasında da çalışır; ileride analiz/plan adımı `UploadFile.is_duplicate_of is not None` olan satırları atlamalı, `EventType.FILE_DUPLICATE` zaten olay logunda.

## 9 — 01.3 Boyut ve sayfa sınırı denetimi — done — 2026-09-14
- Yapıldı: Yükleme uç noktasına 01.3.1 boyut/sayfa sınırı denetimi eklendi — her dosya diske yazılmadan önce boyut (`Settings.max_upload_file_size_bytes`) ve, içerik PDF ise (`detect_file_kind`), sayfa sayısı (`Settings.max_upload_pdf_pages`, `pypdf.PdfReader`) kontrol edilir; sınırı aşan tek dosya bile partiyi tamamen reddeder (400 + "bölüp tekrar yükleyin") ve hiçbir DB satırı/dosya yazılmaz.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (274 geçti, +6 sınır durumu; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.03 (`app/web/routers/uploads.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: PRD 01.3.1 sayı vermez; varsayılan 20 MiB / 30 sayfa seçildi, `.env` ile değiştirilebilir (PLAN.md §C8). PDF imzalı ama pypdf ile çözülemeyen (gerçek yapılı olmayan) içerikte sayfa denetimi atlanır, yalnız boyut denetimi uygulanır. `tests/fixtures/gen.py` bu görevle ilk kez oluşturuldu (`make_pdf_bytes`) — CONVENTIONS §6'nın öngördüğü sentetik belge üretici, yalnız gerçek pypdf ile okunabilir boş sayfalı PDF üretir.
- Sonraki pencereye not: `app/web/routers/uploads.py`'de `get_settings` artık `Depends(get_settings)` ile enjekte ediliyor (önceden düz çağrıydı) — testte `app.dependency_overrides[get_settings]` ile geçersiz kılınıyor (`tests/web/conftest.py`); yeni bir `app` fixture eklendi, `client` fixture ondan türetiliyor. `pyproject.toml`'a `pypdf` bağımlılığı eklendi (MASTER-PROMPT §4'teki kilitli PDF kütüphanesi, ilk kez kullanıldı).

## 8 — 01.2 İçerik tabanlı dosya türü tespiti — done — 2026-09-14
- Yapıldı: `detect_file_kind(content)` — yalnız içerik baytlarına bakarak PDF/JPEG/PNG (imza), DOCX/XLSX (ZIP içi `word/document.xml`/`xl/workbook.xml`) ve eski DOC/XLS'i (CFBF içi UTF-16LE `WordDocument`/`Workbook`/`Book` akış adı) tanır; yedi türün dışındaki içerik `UnsupportedFileTypeError` ile Türkçe anlaşılır mesajla reddedilir.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (269 geçti, +14 dosya türü durumu; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.19 (`app/storage/filetype.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: Görevin ÇIKTI'sı yalnız `app/storage/filetype.py` olduğu için `uploads.py`'ye entegre edilmedi (mime alanı hâlâ istemcinin bildirdiği `content_type`); tm 9 (01.3) zaten `uploads.py`'ye dokunuyor, kablolama muhtemelen o veya sonraki bir görevin işi.
- Sonraki pencereye not: Tür tespiti `app.storage.detect_file_kind` / `FileKind` / `UnsupportedFileTypeError` olarak dışa açık; yükleme akışına bağlamak isteyen görev `app/web/routers/uploads.py`'de `file.content_type` yerine bunu çağırmalı.

## 7 — 01.1 Yükleme uç noktası ve parti oluşturma — done — 2026-09-14
- Yapıldı: `POST /api/uploads` — çoklu dosyayı tek partide kabul eder, her dosyayı `Inbox/<upload_id>/<orijinal_ad>` altına yazar (K10), `upload_id`'yi `u_yyyymmdd_0001` biçiminde günlük sıfırlanan sırayla üretir (`allocate_upload_id`), `context_employee_id` verilirse partiye kaydeder.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (255 geçti, +23 yükleme durumu; 3 PG testi ortam değişkeni yokken atlandı), kapsam %98.96, temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: `channel="web"` sabit (istekte alan yok, panel/bot dışı kanal şimdilik tanımlı değil); dosya `mime` alanı istemcinin bildirdiği `content_type` — içerik tabanlı tespit 01.2'nin işi; sahibi belirsiz dosyanın `context_employee_id`'ye atanması FR-MOD-05 eşleştirme boru hattının işi, bu görev yalnız alanı partiye kaydeder.
- Sonraki pencereye not: `python-multipart` bağımlılığı eklendi (dosya/form alanı FastAPI'de bunsuz ayrıştırılamaz). Router testleri gerçek `DATABASE_URL`/`DATA_DIR` gerektirmez — `app.dependency_overrides[get_session]`/`[get_layout]` ile (`tests/web/conftest.py`) geçici SQLite + geçici veri dizinine bağlanır; sonraki 01.x görevleri (içerik tespiti, boyut/sayfa sınırı, tekrar tespiti, durum sorgulama) aynı `app/web/routers/uploads.py` dosyasına eklenir.

## 6 — 00.6 Belge türü kataloğu ve başlangıç tohumu — done — 2026-09-14
- Yapıldı: `app/catalog/` — §8.6 pydantic sözleşmesi (`direct: true` + dolu `allowed_conversions` tüm kataloğu reddeder), 8 türlük paketli tohum `seed_catalog.yaml` (açılışta `data/KnownDocuments/catalog.yaml` yoksa yazılır), YAML ↔ DB eşitleme (`import_catalog`/`export_catalog`) ve `python -m app.catalog import|export` komutu.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (234 geçti, +87 katalog durumu; 2 PG testi atlandı), kapsam %99, temiz SQLite'ta `alembic upgrade head` + `alembic check`, `import app.main`, CLI import→export bayt bayt tohuma eşit, wheel'de tohum dosyası var — hepsi exit 0.
- Varsayımlar: PLAN §C7 (ek tutarlılık kuralları, tohum değerleri, DB'ye yükleme açılışta değil komutla); §D5: `allowed_conversions` işlem adı taşır (§20.3), §20.5'teki `pdf_to_jpeg` adı kullanılmadı.
- Sonraki pencereye not: Türün kurallarını `CatalogEntry` üzerinden okuyun (`export_catalog(session).get(slug)`); dönüşüm izni `operation in entry.allowed_conversions` (`Conversion` enum). Tohum pasaportları §8.6 gibi `[pdf, jpeg]` bekler — S6 ("katalog yalnız PDF bekliyor") senaryo testi kendi pasaport kaydını kurmalı.

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
