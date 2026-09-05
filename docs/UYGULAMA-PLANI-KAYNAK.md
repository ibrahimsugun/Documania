# Akıllı Çalışan Belge Yönetim Sistemi: Uygulama Planı

| | |
|---|---|
| **Sürüm** | 1.0 |
| **Tarih** | 2026-09-05 |
| **Durum** | Faz 0 başlamadı |
| **Kaynak** | Proje tanım belgesi (bölüm 1-25) ve 2026-09-05 tarihli değerlendirme görüşmesi |

---

## Bu plan nasıl yönetilir

- Fazlar sıralıdır. Bir faz bitmeden sonrakine geçilmez. İstisna: Faz 5 ve Faz 6, Faz 2 bittikten sonra herhangi bir sırada yapılabilir.
- Her görevin bir **Bitti sayılır** ölçütü vardır. Kutucuk yalnızca o ölçüt sağlandığında işaretlenir.
- Görevler tek bir Claude Code oturumunda bitecek büyüklükte tutuldu. Oturum şöyle başlatılır:
  `PLAN.md içindeki 1.4 numaralı görevi uygula. Bölüm 1'deki kararlara uy. Bitince alt görev kutucuklarını işaretle.`
- Büyüklük etiketi: **K** küçük, birkaç saat. **O** orta, yarım gün ile bir gün. **B** büyük, birkaç gün.
- Bir karar değişecekse önce Bölüm 1'deki satır güncellenir, sonra etkilenen görevler.
- Gerçek çalışan belgeleri hiçbir zaman depoya girmez. Testler Bölüm 5'teki sentetik belgelerle yapılır.
- Her fazın sonunda o fazın **Faz kapanış** listesi kontrol edilir.

---

## 1. Kesinleşen kararlar

Bu tablo projenin anayasasıdır. Kod bu tabloya uyar, tablo koda uymaz.

| No | Karar |
|----|-------|
| K1 | **Güven kuralı.** Belge türünün zorunlu alanlar listesindeki her alan okunaklıysa belge kabul edilir. Ayrı bir güven skoru yoktur. Tek bir zorunlu alan bile okunamıyorsa belge Unreadable'a gider ve hangi alanın okunamadığı kaydedilir. |
| K2 | **Girdi türleri.** PDF, JPEG/JPG ve PNG analiz edilir. Word ve Excel analiz edilmez, dönüştürülmez; "Attachment" türüyle olduğu gibi saklanır. Sahibi yükleme bağlamından belli değilse Unresolved'a düşer, İK elle atar. |
| K3 | **Direkt Belge açık.** Çıktı, tek bir kaynak dosyadan alınmış ardışık sayfalardan oluşur. Başka dosyadan sayfa eklenmez, format dönüştürülmez, görüntü yeniden kodlanmaz. Bir dosyanın içinden sayfa çıkarmak serbesttir. Beklenen dosya türü tutmuyorsa belge Unresolved'a gider ve "uygun formatta yeniden gönderin" notu düşülür. |
| K4 | **Direkt Belge kapalı.** Aynı yükleme partisindeki farklı dosyalardan sayfalar birleştirilebilir, türün izin verdiği format dönüşümleri yapılabilir. Ardışıklık kuralı yine geçerlidir. |
| K5 | **Ardışıklık kuralı.** Çok sayfalı bir belgenin sayfaları arasına başka bir belgeye ait sayfa girmişse otomatik birleştirme yapılmaz; parçalar Unresolved'a gider. |
| K6 | **Kişi eşleştirme sırası.** Önce belge numarası tam eşleşmesi. Sonra normalize ad-soyad artı doğum tarihi. Yalnızca ad-soyad eşleşmesi otomatik eşleştirme sayılmaz, Unresolved'a gider. MRZ varsa görünen metinden önce MRZ okunur. |
| K7 | **Yeni çalışan.** Otomatik profil yalnızca temiz okunmuş bir belge numarası varsa açılır. Aksi halde "onay bekleyen profil" olarak Unresolved'a düşer. |
| K8 | **Adlandırma.** Klasör: `Ad_Soyad_E0001`. E numarası sistem tarafından verilir, asla değişmez. Dosya: `Ad_Soyad-Belge-Turu.pdf`. Aynı türden ikinci belge `-2`, üçüncü `-3` eki alır. |
| K9 | **Karar ve uygulama ayrımı.** Yapay zekâ analizi bir Plan JSON olarak dondurulur. Uygulayıcı bu planı yapay zekâya tekrar sormadan yürütür. Yeniden çalıştırma aynı planı kullanır. |
| K10 | **Orijinal dokunulmaz.** Yüklenen dosya Inbox'a yazılır, çözüldükten sonra ilgili çalışanın Alinan klasörüne kopyalanır. SHA-256 ile tekrar yükleme tespit edilir. |
| K11 | **İzinli fiziksel işlemler.** Yalnızca sayfa çıkarma, sayfa birleştirme (K4 dahilinde), görüntüyü PDF'e kayıpsız sarma, PDF sayfasını görüntüye çevirme (K12 dahilinde), yeniden adlandırma, kopyalama, taşıma. İçerik hiçbir koşulda üretilmez, kırpılmaz veya değiştirilmez. |
| K12 | **Dönüşüm kısıtı.** Yalnızca belge türünün izinli dönüşümler listesindeki dönüşümler yapılır. PDF'den JPEG'e dönüşüm kayıplı olduğu için yalnızca Profile Picture gibi görsel türlerde ve sabit çözünürlükle yapılır. Sayfada gömülü tek bir görüntü varsa render yerine gömülü görüntü kayıpsız çıkarılır. |
| K13 | **Telegram.** Yalnızca İK kullanır. Telegram kullanıcı ID beyaz listesi yeterlidir, ek şifreleme önlemi alınmaz. |
| K14 | **Yığın.** Python 3.12, FastAPI, SQLAlchemy, geliştirmede SQLite, üretimde PostgreSQL, PyMuPDF, pypdf, img2pdf, Pillow, Jinja2 + HTMX panel, python-telegram-bot, Docker Compose. Yapay zekâ: Anthropic API birincil; sağlayıcı katmanı OpenAI'ye geçişe izin verecek şekilde soyutlanır. |
| K15 | **Olay logu.** Her adım `events` tablosuna yazılır. Üretilen her çıktı, kaynak dosya ve sayfa aralığına bağlanır. |
| K16 | **Manuel işlemler.** Yalnızca: belgeyi başka çalışana taşı, Unresolved öğesini çalışana ata, onay bekleyen profili onayla, yeni belge türünü onayla, belgeyi arşive taşı. Silme yoktur, arşiv vardır. Hepsi iki aşamalı onay ister ve olay loguna kullanıcı adıyla yazılır. |
| K17 | **İçerik düzenlenemez.** Panelde ve botta belge içeriği düzenleme özelliği yoktur, olmayacaktır. |
| K18 | **Yeniden analiz.** Bir parti yeniden analiz edilirse yeni bir plan sürümü oluşur. Eski çıktılar silinmez ve yeniden adlandırılmaz; veritabanında "eski sürüm" olarak işaretlenir. Temizlik İK'nın arşive taşımasıyla yapılır. |

---

## 2. Sözlük

| Terim | Anlamı |
|-------|--------|
| Yükleme partisi | Tek seferde, tek kanaldan gelen dosya grubu. Bir `upload_id` alır. |
| Kaynak dosya | Partideki tek bir orijinal dosya. |
| Sayfa | Kaynak dosyanın tek bir sayfası. JPEG ve PNG tek sayfalı kaynak sayılır. |
| Sayfa analizi | Yapay zekânın tek sayfa için ürettiği yapılandırılmış sonuç. |
| Belge adayı | Karar motorunun aynı belgeye ait olduğuna hükmettiği sayfa grubu. |
| Çıktı belgesi | Hazir klasörüne yazılan nihai dosya. |
| Plan | Bir parti için dondurulmuş karar kümesi. JSON. |
| Plan öğesi | Plandaki tek bir çıktı veya kuyruk kararı. |
| Bilinen belge türü | Katalogdaki, şirketin kabul ettiği belge türü. |
| Aday belge türü | Sistem tarafından önerilmiş, henüz onaylanmamış tür. |
| Zorunlu alan | Bir türün kabul edilmesi için okunaklı olması gereken alan. |
| Kuyruk | Unknown, Unreadable, Unresolved klasörleri ve bunların panel görünümü. |
| Köken | Bir çıktının hangi kaynak dosyanın hangi sayfalarından üretildiği bilgisi. |

---

## 3. Mimari

### 3.1 İşlem akışı

```
Web Panel / Telegram Botu
        │
        ▼
    FastAPI API
        │
        ▼
  Inbox (orijinaller, değişmez)
        │
        ▼
  Sayfa üretici ── PDF/JPEG/PNG → sayfa görüntüleri + varsa metin katmanı
        │
        ▼
  Analizci (AI) ── her sayfa için yapılandırılmış JSON
        │
        ▼
  Karar motoru ── gruplama, tür, kişi, eşleştirme → PLAN JSON (dondurulur)
        │
        ▼
  Doğrulayıcılar ── zorunlu alan, MRZ, sayfa sayısı, dosya türü, Direkt kuralı
        │
        ▼
  Uygulayıcı ── çıkar / birleştir / sar / adlandır / kopyala
        │
        ├──► Employees/<Ad_Soyad_E0001>/Hazir
        ├──► Unknown
        ├──► Unreadable
        └──► Unresolved

  Her adım ──► events tablosu
```

Yapay zekâ yalnızca "Analizci" kutusunda ve Faz 4'teki Telegram niyet çözümlemesinde çağrılır. Diğer her kutu deterministik koddur.

### 3.2 Depo dizini

```
belgeee/
  app/
    main.py                 FastAPI uygulaması, yönlendirici kayıtları
    config.py               ortam değişkenleri (pydantic-settings)
    events.py               olay logu yardımcıları
    db/                     modeller, oturum, Alembic göçleri
    storage/                yol yardımcıları, Inbox, çalışan klasörleri, hash, atomik yazma
    catalog/                bilinen belge türleri: yükleyici, şema, prompt derleyici
    ai/
      provider.py           soyut arayüz
      anthropic_provider.py
      openai_provider.py    başlangıçta iskelet
      schemas.py            sayfa analizi pydantic şeması
      prompts/              prompt şablonları (metin dosyaları)
    pipeline/
      render.py             sayfa görüntüsü ve metin katmanı üretimi
      analyze.py            sayfa analizi çalıştırıcı
      group.py              gruplama ve tür kararı
      legibility.py         zorunlu alan kontrolü (K1)
      plan.py               Plan JSON üretimi
      validate.py           deterministik doğrulayıcılar
      execute.py            uygulayıcı
      route.py              kuyruklara yönlendirme
      orchestrate.py        process_upload()
    matching/
      names.py              normalizasyon ve harf çevirisi
      mrz.py                MRZ ayrıştırıcı ve kontrol haneleri
      match.py              çalışan eşleştirme (K6, K7)
    profiles/               profil.md üretimi
    web/                    panel: yönlendiriciler, şablonlar, statik dosyalar
    telegram/               bot
  data/                     çalışma zamanı verisi, git dışı
  tests/
    fixtures/               sentetik belgeler ve kayıtlı AI yanıtları
  docker-compose.yml
  Dockerfile
  PLAN.md
```

### 3.3 Veri dizini

```
data/
  Inbox/<upload_id>/              orijinaller, hiçbir zaman değiştirilmez
  Employees/<Ad_Soyad_E0001>/
      Alinan/                     bu çalışana ait orijinallerin kopyası
      Hazir/                      çıktı belgeleri ve Attachment dosyaları
      profil.md                   sistem tarafından üretilir, elle düzenlenmez
  Unknown/<upload_id>/            kaynak dosya kopyası + reason.json
  Unreadable/<upload_id>/         kaynak dosya kopyası + reason.json
  Unresolved/<upload_id>/         kaynak dosya kopyası + reason.json
  Archive/<yyyy-mm>/              arşive taşınan belgeler
  KnownDocuments/
      catalog.yaml                dışa aktarım ve tohum dosyası; asıl kaynak veritabanı
      examples/<tur_slug>/        örnek belgeler
  cache/pages/<file_id>/          analiz için üretilmiş sayfa görüntüleri, silinebilir
  db.sqlite3                      yalnızca geliştirme
```

### 3.4 Veritabanı tabloları

| Tablo | Amaç | Önemli sütunlar |
|-------|------|-----------------|
| `employees` | Çalışan ana kaydı | id (E0001), folder_name, given_names, surname, original_script_name, date_of_birth, nationality, status (active, pending), created_at |
| `employee_identifiers` | Belge numaraları | employee_id, kind (passport_no, id_no, residence_no, license_no), value, source_document_id |
| `employee_aliases` | Görülen tüm isim yazımları | employee_id, raw_name, normalized_name, script |
| `uploads` | Yükleme partisi | id, channel (web, telegram), uploaded_by, context_employee_id, status, created_at |
| `upload_files` | Kaynak dosyalar | id, upload_id, original_name, stored_path, sha256, mime, page_count, is_duplicate_of |
| `pages` | Sayfalar | id, file_id, index, image_path, text_layer, is_blank, has_single_embedded_image, analysis_json, analysis_status |
| `plans` | Dondurulmuş planlar | id, upload_id, version, json, model, plan_hash, created_at, executed_at |
| `documents` | Çıktı belgeleri | id, employee_id, type_slug, path, format, sequence_no, plan_id, source_refs_json, status (current, superseded, archived), created_at |
| `queue_items` | Kuyruk öğeleri | id, upload_id, plan_item_id, kind (unknown, unreadable, unresolved), reason, payload_json, resolved_at, resolved_by |
| `known_document_types` | Katalog | slug, name, file_label, country, description, expected_file_types, expected_pages_min, expected_pages_max, sides, direct, analyze, required_fields, allowed_conversions, output_format, prompt_description, photo_rules, active |
| `candidate_document_types` | Aday türler | id, proposed_name, normalized_name, description, first_seen_upload_id, sample_page_ids, seen_count, status |
| `events` | Olay logu | id, ts, upload_id, file_id, page_index, document_id, employee_id, actor, type, message, data_json |
| `access_log` | Görüntüleme ve indirme | ts, user_id, document_id, action, channel |
| `users` | Panel kullanıcıları | id, username, password_hash, role |
| `telegram_users` | Beyaz liste | telegram_id, user_id, allowed |

### 3.5 Sayfa analizi şeması

Analizci her sayfa için tam olarak bu yapıyı döndürür. Model tahmin etmez; emin olmadığı alanı `null`, okuyamadığı alanı `legible: false` yapar.

```json
{
  "page_index": 0,
  "is_blank": false,
  "is_readable": true,
  "language": "ru",
  "script": "cyrillic",
  "document_type_slug": "russian_passport",
  "candidate_type_name": null,
  "side": "single",
  "continues_previous_page": false,
  "person": {
    "surname": "VASILIEV",
    "given_names": "DMITRY",
    "other_names": null,
    "original_script_name": "Васильев Дмитрий",
    "date_of_birth": "1990-04-12",
    "nationality": "RUS",
    "document_number": "71 1234567",
    "mrz_lines": ["P<RUSVASILIEV<<DMITRY<<<<<<<<<<<<<<<<<<<<<<<<", "7112345671RUS9004121M3001015<<<<<<<<<<<<<<04"]
  },
  "fields": {
    "surname":         {"value": "VASILIEV",   "legible": true},
    "given_names":     {"value": "DMITRY",     "legible": true},
    "date_of_birth":   {"value": "1990-04-12", "legible": true},
    "document_number": {"value": "71 1234567", "legible": true},
    "expiry_date":     {"value": null,         "legible": false}
  },
  "notes": "Alt kenar hafif bulanık."
}
```

Alan anlamları:

- `document_type_slug`: katalogdaki bir slug veya `null`.
- `candidate_type_name`: slug `null` ise modelin önerdiği tür adı, örneğin "Peruvian University Diploma".
- `side`: `front`, `back`, `single`, `unknown`.
- `continues_previous_page`: bu sayfa bir önceki sayfadaki belgenin devamı mı.
- `fields`: türün zorunlu alanları artı model tarafından okunan diğer alanlar. Zorunlu alanların hepsi `legible: true` değilse belge kabul edilmez (K1).

### 3.6 Plan JSON şeması

Karar motorunun çıktısıdır. Dondurulduktan sonra değişmez; yalnızca kuyruk çözümü sırasında tek bir öğenin `employee` ve `route` alanı İK tarafından güncellenebilir ve bu güncelleme yeni plan sürümü olarak kaydedilir.

```json
{
  "upload_id": "u_20260905_0001",
  "version": 1,
  "model": "claude-sonnet-5",
  "created_at": "2026-09-05T10:00:00Z",
  "items": [
    {
      "item_id": "i1",
      "document_type_slug": "serbian_residence_card",
      "sources": [{"file_id": "f1", "pages": [3, 4]}],
      "operation": "extract",
      "target_format": "pdf",
      "target_name": "Ahmet_Cakar-Residence-Card.pdf",
      "employee": {"action": "match", "employee_id": "E0007", "matched_by": "document_number"},
      "route": "hazir",
      "route_reason": null,
      "validations": [{"name": "required_fields", "ok": true}, {"name": "page_count", "ok": true}]
    },
    {
      "item_id": "i2",
      "document_type_slug": "serbian_driving_license",
      "sources": [{"file_id": "f1", "pages": [0]}, {"file_id": "f1", "pages": [5]}],
      "operation": null,
      "target_format": null,
      "target_name": null,
      "employee": {"action": "match", "employee_id": "E0007", "matched_by": "name_dob"},
      "route": "unresolved",
      "route_reason": "Ön ve arka yüz ardışık değil (sayfa 1 ve 6). K5.",
      "validations": []
    }
  ]
}
```

`operation` değerleri: `passthrough` (dosya olduğu gibi), `extract` (tek dosyadan ardışık sayfa çıkarma), `merge` (aynı partiden birden çok dosya, yalnızca Direkt kapalı), `wrap_image` (JPEG/PNG'yi kayıpsız PDF'e sarma), `extract_image` (PDF sayfasındaki gömülü görüntüyü kayıpsız çıkarma), `render_image` (PDF sayfasını sabit çözünürlükle JPEG'e çevirme).

`route` değerleri: `hazir`, `unknown`, `unreadable`, `unresolved`, `skip` (boş sayfa).

`employee.action` değerleri: `match` (mevcut çalışan), `create` (temiz belge numarasıyla yeni çalışan, K7), `pending` (onay bekleyen profil önerisi), `none` (kişi tespit edilemedi).

### 3.7 Katalog kaydı biçimi

```yaml
- slug: russian_passport
  name: Russian Passport
  file_label: Passport
  country: RU
  description: Rusya Federasyonu dış pasaportu, kimlik sayfası.
  expected_file_types: [pdf, jpeg]
  expected_pages: {min: 1, max: 1}
  sides: single
  direct: true
  analyze: true
  required_fields: [surname, given_names, date_of_birth, document_number, expiry_date]
  allowed_conversions: []
  output_format: keep
  prompt_description: >
    Kiril ve Latin çift yazımlı kimlik sayfası, sağ altta iki satır MRZ,
    sol üstte fotoğraf, "ПАСПОРТ / PASSPORT" başlığı.

- slug: serbian_driving_license
  name: Serbian Driving License
  file_label: Driving-License
  country: RS
  expected_file_types: [pdf, jpeg, png]
  expected_pages: {min: 2, max: 2}
  sides: front_back
  direct: false
  analyze: true
  required_fields: [surname, given_names, date_of_birth, document_number]
  allowed_conversions: [jpeg_to_pdf, png_to_pdf]
  output_format: pdf

- slug: profile_picture
  name: Profile Picture
  file_label: Profile-Picture
  country: null
  expected_file_types: [jpeg, png, pdf]
  expected_pages: {min: 1, max: 1}
  sides: single
  direct: false
  analyze: true
  required_fields: []
  allowed_conversions: [png_to_jpeg, pdf_to_jpeg]
  output_format: jpeg
  photo_rules: []          # Faz 5'te doldurulur

- slug: attachment
  name: Attachment
  file_label: Attachment
  expected_file_types: [docx, xlsx, doc, xls]
  direct: true
  analyze: false           # K2: sayfa analizi yapılmaz
  required_fields: []
  allowed_conversions: []
  output_format: keep
```

`output_format: keep` kaynak biçimini korur. `direct: true` olan türlerde `allowed_conversions` boş olmak zorundadır; katalog yükleyici bunu doğrular. `analyze: false` olan türler sayfa üreticiye ve analizciye girmez.

---

## 4. Fazlar

### Faz 0: İskelet ve temel altyapı

**Amaç:** Sonraki her fazın üzerine oturacağı depo, yapılandırma, veritabanı, depolama, olay logu ve katalog tohumunu kurmak. Bu fazda hiçbir yapay zekâ çağrısı yoktur.

**Bağımlılık:** yok.

#### 0.1 Depo ve çalışma ortamı (K)

**Neden:** Tek komutla kurulan, tek komutla test edilen bir ortam olmadan sonraki görevler oturumdan oturuma sürüklenir.

Alt görevler:
- [ ] 0.1.1 `git init`, `.gitignore` (`data/`, `.env`, `__pycache__`, `.venv`).
- [ ] 0.1.2 `pyproject.toml` ile bağımlılıklar: fastapi, uvicorn, sqlalchemy, alembic, pydantic-settings, pymupdf, pypdf, img2pdf, pillow, python-multipart, jinja2, anthropic, openai, python-telegram-bot, pytest, ruff.
- [ ] 0.1.3 `ruff` ve `pytest` yapılandırması; `tests/` altında boş bir geçiş testi.
- [ ] 0.1.4 `Dockerfile` (python 3.12-slim) ve `docker-compose.yml` (app + postgres + volume `data/`).
- [ ] 0.1.5 `.env.example` ve kısa `README.md` (kurulum, çalıştırma, test komutları).

**Bitti sayılır:** `docker compose up` ile uygulama ayağa kalkar ve `/health` 200 döner; `pytest` yeşil.

#### 0.2 Yapılandırma (K)

**Neden:** Model adı, DPI, dizin yolu gibi değerler koda gömülürse her değişiklik kod değişikliği olur.

Alt görevler:
- [ ] 0.2.1 `app/config.py`: DATA_DIR, DATABASE_URL, AI_PROVIDER (anthropic | openai), ANTHROPIC_API_KEY, OPENAI_API_KEY, MODEL_MAIN, MODEL_CHEAP, RENDER_DPI, ANALYSIS_MAX_SIDE_PX, MAX_UPLOAD_MB, MAX_PAGES_PER_FILE, TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_IDS, SESSION_SECRET.
- [ ] 0.2.2 Eksik zorunlu değerde açılışta anlaşılır hata.

**Bitti sayılır:** Ayarlar yalnızca `.env` ile değişir; testte `config` nesnesi sahte değerlerle kurulabilir.

#### 0.3 Veritabanı modelleri ve göçler (O)

**Neden:** Bölüm 3.4'teki tablolar tüm fazların ortak omurgası.

Alt görevler:
- [ ] 0.3.1 SQLAlchemy modelleri: Bölüm 3.4'teki 15 tablo.
- [ ] 0.3.2 Alembic ilk göç; SQLite ve PostgreSQL'de çalışır.
- [ ] 0.3.3 E-numarası üretici: `E` + dört haneli artan sayı, yarış durumuna karşı tek transaction.
- [ ] 0.3.4 Model testleri: kayıt oluşturma, ilişkiler, E-numarası tekilliği.

**Bitti sayılır:** `alembic upgrade head` iki veritabanında da temiz çalışır; testler yeşil.

#### 0.4 Depolama katmanı (O)

**Neden:** Dosya yolu, adlandırma ve atomik yazma kuralları tek yerde olmalı (K8, K10).

Alt görevler:
- [ ] 0.4.1 Bölüm 3.3'teki dizin ağacını açılışta oluşturan `ensure_layout()`.
- [ ] 0.4.2 `slugify_name()`: Türkçe karakterler ASCII'ye (ç→c, ş→s, ğ→g, ı→i, ö→o, ü→u), Kiril ve Arap harfleri için standart çeviri tablosu, kalan her şey `_`. Yalnızca `[A-Za-z0-9_-]` kalır.
- [ ] 0.4.3 `employee_folder_name(given, surname, employee_id)` → `Ad_Soyad_E0001`.
- [ ] 0.4.4 `next_output_name(employee, file_label, ext)`: mevcut dosyalara bakıp `-2`, `-3` ekini seçer.
- [ ] 0.4.5 `sha256_file()` ve `atomic_write()` (geçici dosyaya yaz, sonra yeniden adlandır).
- [ ] 0.4.6 `inbox_path(upload_id)`, `queue_path(kind, upload_id)`, `archive_path()`.
- [ ] 0.4.7 Testler: Türkçe, Kiril ve Arap isimlerle slug; sıra eki; atomik yazma yarım dosya bırakmaz.

**Bitti sayılır:** Tüm yol üretimi bu modülden geçer; hiçbir başka modülde dizge birleştirmeyle yol yoktur.

#### 0.5 Olay logu (K)

**Neden:** K15. Loglama sonradan eklenirse her yerde eksik kalır; en başta kurulur.

Alt görevler:
- [ ] 0.5.1 Olay türleri sabit listesi: FILE_UPLOADED, FILE_DUPLICATE, PAGE_RENDERED, PAGE_BLANK, PAGE_ANALYZED, PAGE_ANALYSIS_FAILED, PAGE_UNREADABLE, DOC_TYPE_DETERMINED, DOC_TYPE_UNKNOWN, CANDIDATE_TYPE_PROPOSED, PERSON_IDENTIFIED, PERSON_MATCHED, PERSON_NOT_MATCHED, PERSON_AMBIGUOUS, EMPLOYEE_CREATED, EMPLOYEE_PENDING, PLAN_CREATED, VALIDATION_FAILED, DIRECT_DOC_CHECK, PAGE_EXTRACTED, PAGES_MERGED, IMAGE_WRAPPED, IMAGE_EXTRACTED, IMAGE_RENDERED, OUTPUT_SAVED, OUTPUT_SKIPPED, QUEUED_UNKNOWN, QUEUED_UNREADABLE, QUEUED_UNRESOLVED, MANUAL_MOVE, MANUAL_ASSIGN, MANUAL_APPROVE, TYPE_APPROVED, TYPE_REJECTED, USER_CONFIRMED, PLAN_RERUN, PLAN_REANALYZED, ARCHIVED, PIPELINE_FAILED.
- [ ] 0.5.2 `events.log(type, message, **context)` yardımcısı; bağlam alanları upload_id, file_id, page_index, document_id, employee_id, actor.
- [ ] 0.5.3 `with events.context(upload_id=...)` bağlam yöneticisi: içindeki loglara otomatik bağlam ekler.
- [ ] 0.5.4 Test: bağlam yöneticisi içinde atılan olay doğru alanlarla kaydedilir.

**Bitti sayılır:** Sonraki fazlarda her adım bu yardımcıyla loglanabilir; olay türü listesi tek dosyadadır.

#### 0.6 Katalog tohumu (O)

**Neden:** Analizci, katalog olmadan tür belirleyemez. Başlangıç türleri şirketin bugün kullandığı belgeler olmalı.

Alt görevler:
- [ ] 0.6.1 Bölüm 3.7 şemasını pydantic ile tanımla; `direct: true` ise `allowed_conversions` boş olmalı kuralını doğrula.
- [ ] 0.6.2 `catalog.yaml` tohumu: Russian Passport, Turkish Passport, Serbian Passport, Serbian Residence Card, Serbian Driving License, Work Permit, Profile Picture, Attachment. Her biri için zorunlu alanlar, beklenen sayfa, ön/arka, direkt bayrağı, kısa prompt_description.
- [ ] 0.6.3 Yükleyici: YAML'dan veritabanına eşitleme; veritabanı asıl kaynak, YAML tohum ve dışa aktarım.
- [ ] 0.6.4 `catalog.get(slug)`, `catalog.active_types()` erişimcileri.
- [ ] 0.6.5 Test: geçersiz kayıt (direkt + dönüşüm) reddedilir; tohum yüklenir.

**Bitti sayılır:** Sekiz tür veritabanında; yükleyici tutarsız kataloğu reddeder.

#### Faz 0 kapanış
- [ ] Docker ile ayağa kalkıyor, testler yeşil.
- [ ] Bölüm 3.3 dizin ağacı otomatik oluşuyor.
- [ ] Katalogda başlangıç türleri var.

---

### Faz 1: Çekirdek boru hattı

**Amaç:** Bir dosya API'den girsin, doğru çalışanın Hazir klasöründen veya doğru kuyruktan çıksın. Panel yok, Telegram yok; yalnızca API ve testler.

**Bağımlılık:** Faz 0.

#### 1.1 Yükleme uç noktası ve Inbox (O)

**Neden:** K10. Orijinal ilk saniyeden itibaren dokunulmaz biçimde saklanmalı; uzantıya değil içeriğe bakılmalı.

Alt görevler:
- [ ] 1.1.1 `POST /api/uploads`: çoklu dosya, isteğe bağlı `context_employee_id`, kanal bilgisi.
- [ ] 1.1.2 Dosya türü tespiti sihirli baytlarla (magic bytes); uzantı yalnızca bilgi olarak saklanır. PDF, JPEG, PNG, DOCX/XLSX/DOC/XLS dışındakiler reddedilir.
- [ ] 1.1.3 Boyut ve sayfa sınırı kontrolü (MAX_UPLOAD_MB, MAX_PAGES_PER_FILE).
- [ ] 1.1.4 SHA-256 hesapla; aynı hash daha önce varsa `is_duplicate_of` doldur, FILE_DUPLICATE logla, yeniden analiz etme.
- [ ] 1.1.5 Dosyayı `Inbox/<upload_id>/` altına orijinal adıyla, atomik yaz; `uploads` ve `upload_files` kayıtları; FILE_UPLOADED.
- [ ] 1.1.6 `GET /api/uploads/{id}`: durum ve dosya listesi.
- [ ] 1.1.7 Testler: sahte uzantılı dosya (PDF içerikli `.jpg`) doğru tanınır; tekrar yükleme tespit edilir.

**Bitti sayılır:** Yüklenen her dosya Inbox'ta hash'iyle duruyor; tekrar yüklemede ikinci kopya analiz kuyruğuna girmiyor.

#### 1.2 Sayfa üretici (O)

**Neden:** Analizci sayfa görüntüsüyle çalışır. Görüntü kalitesi ve boyutu hem doğruluğu hem maliyeti belirler.

Alt görevler:
- [ ] 1.2.1 PDF: PyMuPDF ile her sayfayı RENDER_DPI'da render et, uzun kenarı ANALYSIS_MAX_SIDE_PX'e küçült, `cache/pages/` altına JPEG yaz.
- [ ] 1.2.2 PDF metin katmanı: sayfada metin varsa çıkar ve `pages.text_layer` alanına yaz; taranmış sayfalarda boş kalır.
- [ ] 1.2.3 JPEG/PNG: EXIF yönelimine göre döndürülmüş bir analiz kopyası üret; orijinale dokunma.
- [ ] 1.2.4 Boş sayfa sezgisi: piksel varyansı ve metin yokluğu ile `is_blank`; PAGE_BLANK logla, analizciye gönderme.
- [ ] 1.2.5 Gömülü görüntü tespiti: sayfa tek bir tam sayfa görüntüden oluşuyorsa `has_single_embedded_image` işaretle (K12 için).
- [ ] 1.2.6 `pages` kayıtları ve PAGE_RENDERED olayları.
- [ ] 1.2.7 Testler: çok sayfalı sentetik PDF, EXIF döndürülmüş JPEG, boş sayfa.

**Bitti sayılır:** Her kaynak dosya için sayfa kayıtları ve görüntüleri var; boş sayfalar işaretli.

#### 1.3 Yapay zekâ sağlayıcı katmanı (O)

**Neden:** K14. Sağlayıcı değişse boru hattı değişmemeli; çıktı her zaman Bölüm 3.5 şemasına uymalı.

Alt görevler:
- [ ] 1.3.1 `ai/schemas.py`: Bölüm 3.5 şeması pydantic modeli olarak.
- [ ] 1.3.2 `ai/provider.py`: `analyze_page(image_bytes, text_layer, catalog_prompt, previous_summary) -> PageAnalysis` arayüzü; `usage` (token) döndürür.
- [ ] 1.3.3 `anthropic_provider.py`: görüntü + metin girdisi, şemaya zorlanmış yapılandırılmış çıktı (tool use), katalog prompt'u için prompt önbellekleme.
- [ ] 1.3.4 `openai_provider.py`: aynı arayüz, iskelet ve tek bir çalışır çağrı.
- [ ] 1.3.5 `prompts/page_analysis.md`: kurallar. Tahmin etme, okuyamadığını `legible:false` yap, katalogda yoksa `candidate_type_name` öner, MRZ satırlarını ham olarak aktar, ön/arka yüzü belirt, önceki sayfanın devamı olup olmadığını söyle.
- [ ] 1.3.6 Yeniden deneme ve geri çekilme (rate limit, 5xx); üç denemeden sonra hata.
- [ ] 1.3.7 `RecordingProvider`: gerçek yanıtları `tests/fixtures/ai/` altına kaydeden ve testte oradan okuyan sahte sağlayıcı.
- [ ] 1.3.8 Test: şema dışı yanıt reddedilir; kayıtlı yanıtla deterministik sonuç.

**Bitti sayılır:** Sağlayıcı `.env` ile değişir; testler ağ olmadan çalışır.

#### 1.4 Sayfa analizi çalıştırıcı (K)

**Neden:** Sayfaları sırayla, bağlamıyla ve hataya dayanıklı biçimde analizciye vermek.

Alt görevler:
- [ ] 1.4.1 Partideki her dosyanın boş olmayan sayfalarını sırayla analiz et; önceki sayfanın kısa özetini `previous_summary` olarak ver.
- [ ] 1.4.2 Sonucu `pages.analysis_json` ve `analysis_status` alanlarına yaz; PAGE_ANALYZED, token kullanımıyla birlikte.
- [ ] 1.4.3 Hata durumunda `analysis_status = failed`, PAGE_ANALYSIS_FAILED; parti durumu `partial` olur, diğer sayfalar devam eder.
- [ ] 1.4.4 `is_readable: false` dönen sayfa PAGE_UNREADABLE ile işaretlenir.
- [ ] 1.4.5 `analyze: false` türde olduğu bilinen dosyalar (Word, Excel) bu adıma hiç girmez.
- [ ] 1.4.6 Test: üç sayfalık partide bir sayfa hata verir, diğer ikisi tamamlanır.

**Bitti sayılır:** Her sayfanın analiz durumu izlenebilir; tek sayfa hatası partiyi durdurmaz.

#### 1.5 Gruplama ve tür kararı (B)

**Neden:** Sayfa analizlerinden belge adayları üretmek boru hattının en kritik mantığıdır. K3, K4, K5 burada uygulanır.

Alt görevler:
- [ ] 1.5.1 Dosya içi gruplama: ardışık sayfalar aynı `document_type_slug` ve aynı kişi anahtarına sahipse ve `side` dizisi katalogdaki `sides` yapısına uyuyorsa (front sonra back veya tek single) tek belge adayı olur.
- [ ] 1.5.2 Kişi anahtarı: MRZ belge numarası varsa o; yoksa normalize soyad + normalize ad (1.7'deki fonksiyonlarla).
- [ ] 1.5.3 Ardışıklık kuralı (K5): aynı tür ve kişiye ait ama araya başka sayfa girmiş parçalar tek aday olmaz; her parça `unresolved` gerekçesiyle ayrı aday olur.
- [ ] 1.5.4 Dosyalar arası gruplama (yalnızca `direct: false` türler): aynı partide farklı dosyalardaki tek sayfalık front ve back, yükleme sırasıyla eşleştirilir. Aynı türden birden fazla front varsa eşleştirme yapılmaz, hepsi `unresolved`.
- [ ] 1.5.5 `document_type_slug` null ve `candidate_type_name` dolu ise aday `unknown` rotasına gider, aday adı `candidate_document_types` tablosuna yazılır (tam akış Faz 3'te).
- [ ] 1.5.6 Beklenen sayfa sayısı kontrolü: aday, `expected_pages` aralığı dışındaysa `unresolved`, gerekçe yazılır.
- [ ] 1.5.7 Attachment türü (K2): analiz edilmeden tek aday olur; `context_employee_id` varsa `hazir`, yoksa `unresolved`.
- [ ] 1.5.8 Olaylar: DOC_TYPE_DETERMINED, DOC_TYPE_UNKNOWN, CANDIDATE_TYPE_PROPOSED.
- [ ] 1.5.9 Testler: Bölüm 5'teki S3, S4, S5, S7 senaryoları kayıtlı analiz yanıtlarıyla.

**Bitti sayılır:** Belgedeki altı sayfalık karışık örnek doğru parçalanıyor; ardışık olmayan ehliyet birleştirilmiyor.

#### 1.6 Zorunlu alan kontrolü (K)

**Neden:** K1. Kabulün tek ölçütü budur.

Alt görevler:
- [ ] 1.6.1 Adayın sayfalarındaki `fields` sözlüklerini birleştir; aynı alan birden fazla sayfada varsa `legible: true` olan kazanır.
- [ ] 1.6.2 Türün `required_fields` listesindeki her alan için `legible` kontrolü; eksik veya `false` olanların listesi.
- [ ] 1.6.3 Liste boş değilse aday `unreadable`, gerekçe: "Okunamayan alanlar: document_number, expiry_date".
- [ ] 1.6.4 Test: bir zorunlu alan okunaksızsa aday Unreadable'a düşer; tümü okunaklıysa geçer.

**Bitti sayılır:** Unreadable gerekçeleri alan adlarıyla yazılıyor.

#### 1.7 Kişi tanımlama ve isim normalizasyonu (O)

**Neden:** K6. Aynı kişinin farklı yazımlarını aynı anahtara indirmek eşleştirmenin temelidir.

Alt görevler:
- [ ] 1.7.1 `names.normalize()`: küçük harf, aksan temizliği, çoklu boşluk sadeleştirme, tire ve nokta kaldırma, jeton sıralama (ad sırası farkı için).
- [ ] 1.7.2 `names.transliterate()`: Kiril için ICAO 9303 tablosu, Arap için standart tablo; modelin verdiği Latin yazım varsa onu da alias olarak sakla.
- [ ] 1.7.3 `mrz.parse()`: TD1, TD2, TD3 biçimleri; kontrol haneleri doğrulanır; geçerliyse ad, soyad, doğum tarihi, belge numarası, uyruk döner.
- [ ] 1.7.4 Görünen metin ile MRZ çelişirse MRZ kazanır, çelişki nota yazılır (VALIDATION_FAILED değil, bilgi).
- [ ] 1.7.5 `PersonKey` nesnesi: identifiers (belge numaraları), normalized_surname, normalized_given, dob, original_script_name.
- [ ] 1.7.6 Testler: "Дмитрий Васильев" ve "DMITRY VASILIEV" aynı anahtara iner; MRZ kontrol hanesi hatalıysa geçersiz sayılır.

**Bitti sayılır:** Kiril, Arap ve Latin yazımlar deterministik biçimde aynı anahtara iniyor.

#### 1.8 Çalışan eşleştirme (O)

**Neden:** K6 ve K7. Yanlış birleştirme ve hayalet çalışan bu adımda önlenir.

Alt görevler:
- [ ] 1.8.1 Adım 1: `employee_identifiers` içinde belge numarası tam eşleşmesi → `match`, `matched_by: document_number`.
- [ ] 1.8.2 Adım 2: `employee_aliases` içinde normalize ad-soyad eşleşmesi ve `date_of_birth` eşitliği → `match`, `matched_by: name_dob`.
- [ ] 1.8.3 Adım 3: Yalnızca isim eşleşmesi → `unresolved`, gerekçe "İsim eşleşti ama doğum tarihi veya belge numarası doğrulanamadı".
- [ ] 1.8.4 Birden fazla çalışan eşleşirse → `unresolved`, PERSON_AMBIGUOUS.
- [ ] 1.8.5 Hiç eşleşme yok ve temiz belge numarası var → `create`; yeni `employees` kaydı, klasör, EMPLOYEE_CREATED.
- [ ] 1.8.6 Hiç eşleşme yok ve belge numarası yok → `pending`; `unresolved` rotası, payload'da önerilen profil, EMPLOYEE_PENDING.
- [ ] 1.8.7 Eşleşmede yeni alias ve yeni identifier kayıtları eklenir.
- [ ] 1.8.8 Testler: S10, S11, S12.

**Bitti sayılır:** Yalnızca isim benzerliğiyle hiçbir belge bir çalışana bağlanmıyor; numarası olmayan belgeden çalışan açılmıyor.

#### 1.9 Plan üretimi (O)

**Neden:** K9. Kararlar burada dondurulur; sonrası mekanik.

Alt görevler:
- [ ] 1.9.1 Her belge adayı için plan öğesi: kaynaklar, tür, çalışan kararı, rota.
- [ ] 1.9.2 İşlem seçimi: tek dosya tüm sayfalar → `passthrough`; tek dosya alt küme → `extract`; birden çok dosya → `merge`; JPEG/PNG kaynak ve PDF çıktı → `wrap_image`; Profile Picture için PDF kaynak → gömülü görüntü varsa `extract_image`, yoksa `render_image`.
- [ ] 1.9.3 Direkt kuralı (K3): `direct: true` türde `merge`, `wrap_image`, `render_image` yasak; kaynak dosya türü `expected_file_types` içinde değilse `unresolved` ve "uygun formatta yeniden gönderin" gerekçesi. DIRECT_DOC_CHECK logla.
- [ ] 1.9.4 Dönüşüm kuralı (K12): seçilen işlem türün `allowed_conversions` listesinde değilse `unresolved`.
- [ ] 1.9.5 Hedef ad: `next_output_name()` ile; çalışan `match` veya `create` değilse hedef ad boş.
- [ ] 1.9.6 Planı `plans` tablosuna JSON ve hash ile yaz; PLAN_CREATED.
- [ ] 1.9.7 Test: aynı analiz sonuçlarından iki kez plan üretimi aynı hash'i verir.

**Bitti sayılır:** Plan JSON Bölüm 3.6 şemasına uyuyor ve deterministik.

#### 1.10 Doğrulayıcılar (K)

**Neden:** Plan öğesi uygulanmadan önce mekanik kurallardan geçer; modelin hatası burada yakalanır.

Alt görevler:
- [ ] 1.10.1 `required_fields` (1.6'nın sonucu plana yazılır).
- [ ] 1.10.2 `page_count`: kaynak sayfa sayısı `expected_pages` aralığında.
- [ ] 1.10.3 `sides`: front_back türde bir front bir back var, sıralı.
- [ ] 1.10.4 `direct_single_source`: direkt türde tek kaynak dosya ve ardışık sayfa aralığı.
- [ ] 1.10.5 `file_type`: kaynak türü `expected_file_types` içinde.
- [ ] 1.10.6 `mrz_checksum`: MRZ varsa kontrol haneleri geçerli.
- [ ] 1.10.7 `dob_plausible`: doğum tarihi geçmişte ve 16-90 yaş aralığında; değilse `unresolved` (Unreadable değil).
- [ ] 1.10.8 Başarısız doğrulama rotayı `unresolved` yapar, gerekçe ve VALIDATION_FAILED.
- [ ] 1.10.9 Testler: her doğrulayıcı için bir geçen bir kalan örnek.

**Bitti sayılır:** Her plan öğesinin `validations` listesi dolu; hiçbir öğe doğrulanmadan uygulanmıyor.

#### 1.11 Uygulayıcı (B)

**Neden:** K11. Dosyalara dokunan tek modül. İdempotent olmalı, kökeni yazmalı, içeriği yeniden üretmemeli.

Alt görevler:
- [ ] 1.11.1 `passthrough`: kaynak dosyayı bayt bayt kopyala.
- [ ] 1.11.2 `extract`: pypdf ile sayfa nesnelerini yeni PDF'e kopyala; yeniden render yok, sıkıştırma değişikliği yok.
- [ ] 1.11.3 `merge`: birden çok kaynaktan sayfa nesnelerini sırayla kopyala (yalnızca `direct: false`).
- [ ] 1.11.4 `wrap_image`: img2pdf ile JPEG/PNG'yi kayıpsız PDF'e sar.
- [ ] 1.11.5 `extract_image`: PyMuPDF ile sayfadaki gömülü görüntüyü orijinal baytlarıyla çıkar.
- [ ] 1.11.6 `render_image`: sabit DPI ile JPEG; yalnızca `allowed_conversions` içinde `pdf_to_jpeg` varsa.
- [ ] 1.11.7 Çıktıyı `Hazir/` altına atomik yaz; `documents` kaydı `source_refs_json` ile; OUTPUT_SAVED olayı "f1 sayfa 4-5'ten üretildi" mesajıyla.
- [ ] 1.11.8 Kaynak dosyayı çalışanın `Alinan/` klasörüne kopyala (aynı hash zaten varsa atla).
- [ ] 1.11.9 İdempotenlik: aynı `plan_hash` ve `item_id` için çıktı zaten varsa yeniden üretme, OUTPUT_SKIPPED.
- [ ] 1.11.10 Rotası `hazir` olmayan öğeleri 1.12'ye devret.
- [ ] 1.11.11 Testler: her işlem için çıktı byte düzeyinde beklenen; iki kez çalıştırma ikinci dosya üretmez; extract sonrası sayfa içeriği kaynakla aynı (metin katmanı karşılaştırması).

**Bitti sayılır:** S1, S4, S5, S7, S18 senaryoları geçiyor.

#### 1.12 Kuyruklara yönlendirme ve çözüm mekanizması (O)

**Neden:** Sistem emin olmadığında dürüstçe kenara koyar; İK'nın çözmesi için gerekli bilgiyi yanına yazar.

Alt görevler:
- [ ] 1.12.1 `unknown`, `unreadable`, `unresolved` rotaları için `queue_items` kaydı ve `data/<Kuyruk>/<upload_id>/` altına kaynak dosya kopyası + `reason.json` (sayfalar, gerekçe, tür tahmini, kişi tahmini).
- [ ] 1.12.2 QUEUED_* olayları.
- [ ] 1.12.3 `resolve_queue_item(item_id, employee_id, actor)`: plan öğesinin `employee` ve `route` alanını güncelleyerek yeni plan sürümü yaz, yalnızca o öğeyi uygulayıcıya ver, kuyruk kaydını kapat, MANUAL_ASSIGN.
- [ ] 1.12.4 `approve_pending_profile(item_id, actor)`: payload'daki profilden çalışan oluştur, sonra 1.12.3'ü çağır, MANUAL_APPROVE.
- [ ] 1.12.5 Testler: kuyruk öğesi çözülünce çıktı üretiliyor ve yapay zekâ çağrılmıyor.

**Bitti sayılır:** Kuyruktaki her öğe panelsiz, API ile çözülebiliyor.

#### 1.13 Çalışan profili dosyası (K)

**Neden:** `profil.md` sistemin çalışan hakkında bildiği her şeyin dosya sistemi üzerindeki özetidir.

Alt görevler:
- [ ] 1.13.1 YAML ön blok: employee_id, given_names, surname, original_script_name, aliases, date_of_birth, nationality, identifiers, status, updated_at.
- [ ] 1.13.2 Markdown gövde: kimlik bilgileri tablosu, belge listesi (tür, dosya adı, tarih, köken).
- [ ] 1.13.3 Her uygulama, eşleştirme ve manuel işlemden sonra yeniden üret; elle düzenleme yok, dosya üst kısmında uyarı satırı.
- [ ] 1.13.4 Test: profil, belge eklenince güncelleniyor ve YAML bloğu geçerli.

**Bitti sayılır:** Her çalışan klasöründe güncel `profil.md` var.

#### 1.14 Orkestrasyon ve durum makinesi (O)

**Neden:** Adımları tek bir `process_upload()` altında toplamak, durumu izlenebilir kılmak.

Alt görevler:
- [ ] 1.14.1 Parti durumları: `received` → `rendering` → `analyzing` → `planning` → `executing` → `done` | `partial` | `failed`.
- [ ] 1.14.2 `process_upload(upload_id)`: 1.2 → 1.4 → 1.5 → 1.6 → 1.7/1.8 → 1.9 → 1.10 → 1.11 → 1.12 → 1.13 sırası; her adım bağlam yöneticisiyle loglanır.
- [ ] 1.14.3 FastAPI BackgroundTasks ile arka planda çalıştır (Faz 6'da işçi kuyruğuna taşınır).
- [ ] 1.14.4 `POST /api/uploads/{id}/rerun`: mevcut planı yeniden uygula, PLAN_RERUN; yapay zekâ çağrısı yok.
- [ ] 1.14.5 `POST /api/uploads/{id}/reanalyze`: yeni plan sürümü, K18 kuralı, PLAN_REANALYZED.
- [ ] 1.14.6 Beklenmeyen hata: parti `failed`, PIPELINE_FAILED olayında hata mesajı, dosyalar Inbox'ta kalır.
- [ ] 1.14.7 Test: uçtan uca S1 senaryosu kayıtlı sağlayıcıyla.

**Bitti sayılır:** Tek çağrıyla parti baştan sona işleniyor; durum her an sorgulanabiliyor.

#### 1.15 Sentetik belgeler ve kabul testleri (O)

**Neden:** Gerçek belge kullanılamaz (gizlilik). Bölüm 5'teki senaryoların tamamı otomatik test olmalı.

Alt görevler:
- [ ] 1.15.1 `tests/fixtures/gen.py`: Pillow ile sahte "belge" sayfaları üretir; başlık, isim, numara, sahte MRZ satırları; JPEG, PNG, tek ve çok sayfalı PDF.
- [ ] 1.15.2 Her senaryo için kayıtlı analiz yanıtı JSON'u (elle yazılmış, şemaya uygun).
- [ ] 1.15.3 Bölüm 5'teki S1'den S15'e ve S18 senaryoları test olarak.
- [ ] 1.15.4 İsteğe bağlı canlı test: `LIVE_AI=1` ile gerçek sağlayıcıya tek sayfa gönderir; CI'da kapalı.

**Bitti sayılır:** Test matrisi yeşil; canlı test bir gerçek sentetik sayfada makul sonuç veriyor.

#### Faz 1 kapanış
- [ ] Bölüm 5 senaryolarından S1-S15 ve S18 otomatik testte geçiyor.
- [ ] Bir partinin olay logu baştan sona okunabiliyor ve her çıktının kökeni yazılı.
- [ ] Yeniden çalıştırma yapay zekâ çağırmıyor.
- [ ] Sayfa başına ortalama token ve maliyet ölçüldü, README'ye not düşüldü.

---

### Faz 2: Web yönetim paneli

**Amaç:** İK'nın günlük kullandığı arayüz. Yükleme, arama, profil, belge görüntüleme, kuyruk çözme, manuel taşıma. İçerik düzenleme yok (K17).

**Bağımlılık:** Faz 1.

#### 2.1 Panel iskeleti ve giriş (O)

**Neden:** Tüm ekranların ortak çatısı ve erişim denetimi.

Alt görevler:
- [ ] 2.1.1 Jinja2 ana şablon, HTMX, hafif CSS (Pico.css veya benzeri); üst menü: Yükle, Çalışanlar, Kuyruklar, Belge Türleri, Yüklemeler.
- [ ] 2.1.2 Oturum tabanlı giriş; `users` tablosu; parola hash (argon2 veya bcrypt).
- [ ] 2.1.3 İlk kullanıcıyı oluşturan CLI komutu.
- [ ] 2.1.4 Tüm panel yolları giriş ister; API yolları oturum veya API anahtarı ister.
- [ ] 2.1.5 Test: girişsiz erişim yönlendirilir.

**Bitti sayılır:** Giriş yapılıyor, boş menüler açılıyor.

#### 2.2 Yükleme sayfası (K)

**Neden:** Belgelerin sisteme ana giriş kapısı.

Alt görevler:
- [ ] 2.2.1 Sürükle-bırak çoklu dosya; isteğe bağlı "Bu çalışan için" seçimi (arama kutusu) → `context_employee_id`.
- [ ] 2.2.2 Yükleme sonrası parti detay sayfasına yönlendirme; durum HTMX ile birkaç saniyede bir yenilenir.
- [ ] 2.2.3 Reddedilen dosya türleri için anlaşılır mesaj.

**Bitti sayılır:** Tarayıcıdan yüklenen dosya boru hattına giriyor ve ilerleme görülüyor.

#### 2.3 Yükleme detay sayfası (O)

**Neden:** "Sistem bu dosyaya ne yaptı?" sorusunun tek ekranda cevabı.

Alt görevler:
- [ ] 2.3.1 Dosyalar, sayfa küçük resimleri, her sayfanın tür ve kişi tahmini.
- [ ] 2.3.2 Plan öğeleri tablosu: kaynak sayfalar, işlem, hedef, rota, gerekçe.
- [ ] 2.3.3 Üretilen çıktılar ve kuyruk öğelerine bağlantılar.
- [ ] 2.3.4 Olay zaman çizelgesi.
- [ ] 2.3.5 "Yeniden çalıştır" düğmesi; "Yeniden analiz et" düğmesi iki aşamalı onayla (K18).

**Bitti sayılır:** Bir partiye ne yapıldığı tek sayfadan anlaşılıyor.

#### 2.4 Çalışan listesi ve arama (O)

**Neden:** Bölüm 19'daki arama gereksinimi.

Alt görevler:
- [ ] 2.4.1 Liste: ad, soyad, orijinal yazım, uyruk, belge sayısı, durum.
- [ ] 2.4.2 Arama kutusu: alias'lar, orijinal yazım, belge numarası, belge türü adı üzerinde; SQL `LIKE` ile başla, gerekirse FTS.
- [ ] 2.4.3 "Onay bekleyen" profiller listede ayrı işaretli.
- [ ] 2.4.4 Sonuç seçilince profil sayfası açılır.

**Bitti sayılır:** "Ahmet", "Passport", "Дмитрий" aramaları doğru çalışanları buluyor.

#### 2.5 Çalışan profili sayfası (O)

**Neden:** Bölüm 12 ve 13'teki CV benzeri profil ve belge listesi.

Alt görevler:
- [ ] 2.5.1 CV benzeri kart: profil fotoğrafı (varsa Profile-Picture çıktısı), ad, soyad, orijinal yazım, uyruk, doğum tarihi ve yaş, tespit edilen iletişim bilgileri, belge numaraları.
- [ ] 2.5.2 Belge listesi: tür, dosya adı, tarih, "Aç" (yeni sekme, `Content-Disposition: inline`) ve "İndir".
- [ ] 2.5.3 Her belge satırında "Geçmiş" bağlantısı (2.6).
- [ ] 2.5.4 Bu sayfadan yükleme: `context_employee_id` otomatik dolu (Attachment için K2).
- [ ] 2.5.5 Görüntüleme ve indirme `access_log` tablosuna yazılır.
- [ ] 2.5.6 Düzenleme alanı yok; yalnızca "Belgeyi taşı" ve "Arşive taşı" eylemleri (2.8).

**Bitti sayılır:** Profil bilgileri profil.md ile birebir; belge yeni sekmede açılıyor.

#### 2.6 Belge geçmişi (K)

**Neden:** Bölüm 22'deki izlenebilirlik hedefi.

Alt görevler:
- [ ] 2.6.1 Belgeye ait olaylar, köken (kaynak dosya + sayfa aralığı, Inbox bağlantısı), plan sürümü.
- [ ] 2.6.2 Kaynak sayfaların küçük resimleri.

**Bitti sayılır:** Bir çıktının hangi yüklemenin hangi sayfalarından geldiği tıklayarak izlenebiliyor.

#### 2.7 Kuyruk ekranları (B)

**Neden:** Sistemin "emin değilim" dediği her şey burada insana sunulur.

Alt görevler:
- [ ] 2.7.1 Üç sekme: Unknown, Unreadable, Unresolved; sayaçlar menüde.
- [ ] 2.7.2 Öğe detayı: sayfa görüntüleri, gerekçe, tür ve kişi tahmini, aday tür adı.
- [ ] 2.7.3 "Çalışana ata": arama kutusu, seçim, iki aşamalı onay, `resolve_queue_item`.
- [ ] 2.7.4 "Profil oluştur ve ata": önerilen profil düzenlenebilir alanlar (yalnızca profil bilgisi, belge içeriği değil), iki aşamalı onay, `approve_pending_profile`.
- [ ] 2.7.5 "Arşive taşı": belge hiçbir çalışana ait değilse arşiv, iki aşamalı onay, ARCHIVED.
- [ ] 2.7.6 Unreadable öğelerinde "Yeniden gönderilmesi istendi" notu (bilgi amaçlı işaret).
- [ ] 2.7.7 Testler: onaysız çözüm hiçbir şey değiştirmiyor.

**Bitti sayılır:** Kuyruklar sıfırlanabiliyor; her çözüm olay loguna kullanıcıyla yazılıyor.

#### 2.8 Manuel taşıma ve iki aşamalı onay (O)

**Neden:** K16. Belgeyi yanlış çalışana taşımak sistemin yapabileceği en pahalı hata; iki onay bunun içindir.

Alt görevler:
- [ ] 2.8.1 Ortak iki aşamalı onay bileşeni: birinci mesaj "Bu belgeyi başka bir çalışana taşımak üzeresiniz. Emin misiniz?", ikinci mesaj "Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?".
- [ ] 2.8.2 Sunucu tarafında tek kullanımlık onay belirteci: birinci onay belirteç üretir, ikinci onay belirteçle gelir; belirteçsiz istek reddedilir.
- [ ] 2.8.3 Taşıma: dosya hedef çalışanın Hazir klasörüne yeni adla, `documents` güncellenir, iki çalışanın profil.md'si yenilenir, MANUAL_MOVE ve USER_CONFIRMED olayları.
- [ ] 2.8.4 Arşive taşıma aynı bileşenle.
- [ ] 2.8.5 Testler: tek onayla istek reddedilir; iki onayla taşınır.

**Bitti sayılır:** S16 geçiyor.

#### 2.9 Panel testleri ve erişilebilirlik (K)

Alt görevler:
- [ ] 2.9.1 Her yol için yetki testi.
- [ ] 2.9.2 Temel klavye erişimi ve mobil genişlikte kırılmayan tablolar.

**Bitti sayılır:** Yetkisiz hiçbir yol açılmıyor; panel telefonda kullanılabiliyor.

#### Faz 2 kapanış
- [ ] İK bir belgeyi yükleyip, kuyruğu çözüp, profilde görüp, yeni sekmede açabiliyor.
- [ ] Hiçbir ekranda belge içeriği düzenleme yolu yok.
- [ ] Manuel işlemlerin tamamı olay logunda kullanıcı adıyla.

---

### Faz 3: Bilinen Belgeler ve yeni tür öğrenme

**Amaç:** Katalogun panelden yönetilmesi ve sistemin yeni belge türlerini İK onayıyla öğrenmesi.

**Bağımlılık:** Faz 2.

#### 3.1 Katalog yönetim ekranı (O)

**Neden:** Bölüm 16. Katalog değişikliği kod değişikliği olmamalı.

Alt görevler:
- [ ] 3.1.1 Liste, oluştur, düzenle, pasifleştir; Bölüm 3.7'deki tüm alanlar form olarak.
- [ ] 3.1.2 Form doğrulaması: direkt türde dönüşüm listesi boş; front_back türde sayfa aralığı 2.
- [ ] 3.1.3 `catalog.yaml` dışa ve içe aktarma.
- [ ] 3.1.4 Değişiklikler olay loguna.

**Bitti sayılır:** Yeni tür panelden ekleniyor ve bir sonraki analizde kullanılıyor.

#### 3.2 Örnek belge yükleme (K)

**Neden:** Tür açıklamalarının ham maddesi.

Alt görevler:
- [ ] 3.2.1 Tür sayfasından örnek yükleme; `KnownDocuments/examples/<slug>/` altına; sayfa görüntüleri üretilir.
- [ ] 3.2.2 Örnekler çalışan verisi sayılmaz, arama ve profillerde görünmez.

**Bitti sayılır:** Her türün altında örnekleri görülebiliyor.

#### 3.3 Tür açıklaması üretimi (O)

**Neden:** Modele her çağrıda örnek görüntü göndermek pahalıdır. Örneklerden bir kez metin açıklaması üretilir, o metin prompt'a girer.

Alt görevler:
- [ ] 3.3.1 `describe_type(slug)`: örnek sayfaları modele verir, yapılandırılmış açıklama ister: düzen, diller, alfabe, ayırt edici başlıklar, alanların konumu, MRZ varlığı, ön/arka farkları.
- [ ] 3.3.2 Sonuç `prompt_description` alanına yazılır; İK düzenleyebilir.
- [ ] 3.3.3 "Yeniden üret" düğmesi.

**Bitti sayılır:** Bir türün açıklaması örneklerinden üretilip prompt'ta kullanılıyor.

#### 3.4 Prompt derleyici (K)

**Neden:** Katalog büyüdükçe prompt kontrolsüz büyümemeli.

Alt görevler:
- [ ] 3.4.1 Aktif türlerin slug, ad, ülke, `prompt_description`, `sides`, zorunlu alanlarını kompakt bir katalog metnine derle.
- [ ] 3.4.2 Token bütçesi: katalog metni sınırı aşarsa açıklamalar kısaltılır, uyarı loglanır.
- [ ] 3.4.3 Katalog metni değişmediği sürece prompt önbelleği kullanılır (Anthropic prompt caching).

**Bitti sayılır:** Katalog değişince prompt otomatik güncelleniyor.

#### 3.5 Aday tür akışı (O)

**Neden:** Bölüm 17. Sistem bilmediği belgeyi zorla bir kategoriye sokmaz, İK'ya sorar.

Alt görevler:
- [ ] 3.5.1 1.5.5'te yazılan aday türler normalize adla tekilleştirilir; aynı aday ikinci kez görülünce `seen_count` artar, örnek sayfa eklenir.
- [ ] 3.5.2 "Yeni belge türleri" ekranı: aday adı, kaç kez görüldü, örnek sayfalar, modelin açıklaması.
- [ ] 3.5.3 "Bilinen türlere ekle": 3.1 formu aday bilgileriyle önceden dolu açılır; İK zorunlu alanları ve direkt bayrağını belirler; iki aşamalı onay; TYPE_APPROVED.
- [ ] 3.5.4 Onay sonrası bu adayla ilişkili Unknown öğeleri için "Yeniden analiz et" toplu düğmesi.
- [ ] 3.5.5 "Reddet": aday pasif, TYPE_REJECTED; aynı ad yeniden önerilirse listeye düşmez.
- [ ] 3.5.6 Test: S14.

**Bitti sayılır:** Peru diploması örneği onaylandıktan sonra ikinci yüklemede doğrudan Hazir'a gidiyor.

#### Faz 3 kapanış
- [ ] Katalog tamamen panelden yönetiliyor.
- [ ] Yeni tür akışı uçtan uca çalışıyor.
- [ ] Prompt boyutu ve maliyeti katalog büyüdükçe ölçülüyor.

---

### Faz 4: Telegram botu

**Amaç:** İK'nın telefondan belge gönderip belge istemesi. Aynı boru hattı, aynı kurallar.

**Bağımlılık:** Faz 2. Faz 3 gerekmez.

#### 4.1 Bot iskeleti ve beyaz liste (K)

**Neden:** K13. Bota kimin erişebileceği ilk günden kısıtlı olmalı.

Alt görevler:
- [ ] 4.1.1 python-telegram-bot; geliştirmede polling, üretimde webhook.
- [ ] 4.1.2 Her güncellemede `telegram_users` beyaz listesi; listede olmayan kullanıcıya yanıt verilmez.
- [ ] 4.1.3 `/start` ve `/yardim` komutları.
- [ ] 4.1.4 Bot ayrı bir Docker servisi olarak.

**Bitti sayılır:** Listedeki kullanıcı yanıt alıyor, listede olmayan almıyor.

#### 4.2 Belge alma (O)

**Neden:** Bölüm 20. Telefondan gönderilen belge web ile aynı yoldan işlenmeli.

Alt görevler:
- [ ] 4.2.1 Belge ve fotoğraf mesajlarını indir, `POST /api/uploads` ile kanal `telegram` olarak ver.
- [ ] 4.2.2 Aynı mesaj grubundaki (media group) dosyalar tek parti sayılır.
- [ ] 4.2.3 İlerleme mesajı, ardından sonuç özeti: "Ahmet Çakar için Ehliyet hazır. 1 sayfa Unresolved: ön ve arka yüz ardışık değil."
- [ ] 4.2.4 Telegram'ın fotoğraf sıkıştırmasına dikkat: kullanıcıya "belge olarak gönderin" uyarısı, sıkıştırılmış fotoğraf yine de işlenir.

**Bitti sayılır:** Telefondan gönderilen pasaport panelde görünen partiyle aynı yoldan işleniyor.

#### 4.3 Doğal dil istekleri (B)

**Neden:** Bölüm 20'deki "Ahmet Çakar'ın ehliyetini göster" akışı.

Alt görevler:
- [ ] 4.3.1 Metin mesajı yapay zekâya araç tanımlarıyla verilir: `search_employees(query)`, `list_documents(employee_id, type_slug=None)`, `send_document(document_id)`.
- [ ] 4.3.2 Niyet: belge isteme, çalışan arama, sohbet dışı mesaj (kibarca yönlendirme).
- [ ] 4.3.3 Tek çalışan ve tek belge → dosya gönderilir; birden fazla belge → "Ahmet Çakar'a ait 2 ehliyet bulundu. Hangisini istiyorsunuz?" satır içi klavye; birden fazla çalışan → önce çalışan seçimi.
- [ ] 4.3.4 Gönderilen her belge `access_log`'a kanal `telegram` ile yazılır.
- [ ] 4.3.5 Kısa süreli sohbet belleği: seçim mesajı önceki soruya bağlanır.
- [ ] 4.3.6 Test: S17, sahte bot ve kayıtlı yanıtlarla.

**Bitti sayılır:** "Ahmet Çakar'ın ehliyetini göster" doğru dosyayı veya doğru soruyu döndürüyor.

#### 4.4 Bildirimler (K)

**Neden:** İK'nın paneli açmadan kuyruğun dolduğunu görmesi.

Alt görevler:
- [ ] 4.4.1 Kuyruğa yeni öğe düşünce belirlenen sohbete kısa bildirim (isteğe bağlı ayar).
- [ ] 4.4.2 Parti `failed` olursa yönetici sohbetine hata.

**Bitti sayılır:** Bildirim ayarı açıkken kuyruk mesajı geliyor.

#### Faz 4 kapanış
- [ ] Bot yalnızca beyaz listeye yanıt veriyor.
- [ ] Yükleme ve isteme uçtan uca çalışıyor.

---

### Faz 5: Profil fotoğrafı kriterleri

**Amaç:** Profile Picture türü için şirket kurallarının kontrolü ve zamanla öğrenilmesi. Bölüm 18.

**Bağımlılık:** Faz 3.

#### 5.1 Kural seti (K)

**Neden:** Kurallar önce yazılı olmalı ki model neyi kontrol edeceğini bilsin.

Alt görevler:
- [ ] 5.1.1 Katalogda `photo_rules` listesi: yüz görünür, tek kişi, nötr ifade, sade arka plan, asgari çözünürlük, güneş gözlüğü yok, baş örtüsü kabul durumu (şirket kararı).
- [ ] 5.1.2 Kurallar 3.1 ekranından açılıp kapatılabilir.

**Bitti sayılır:** Kural listesi katalogda ve panelde görünüyor.

#### 5.2 Görsel kontrol (O)

**Neden:** Fotoğrafın yalnızca JPEG olması yetmez; şirket kriterine uymalı.

Alt görevler:
- [ ] 5.2.1 Analizci, Profile Picture için her kuralı `pass | fail | unsure` olarak döndürür.
- [ ] 5.2.2 Çözünürlük kontrolü deterministik (piksel boyutu).
- [ ] 5.2.3 `fail` varsa rota `unresolved`, gerekçe kural adlarıyla; `unsure` yalnızca not.
- [ ] 5.2.4 Çıktı JPEG; kırpma, düzeltme, arka plan değiştirme yok (K11). PNG'den JPEG'e dönüşüm sabit kaliteyle.
- [ ] 5.2.5 Test: sentetik "iki yüz" ve "düşük çözünürlük" görselleri Unresolved'a düşer.

**Bitti sayılır:** Kural ihlali olan fotoğraf Hazir'a girmiyor, gerekçesi yazılı.

#### 5.3 Örneklerden öğrenme (K)

**Neden:** Şirketin kabul ettiği fotoğraf tanımı zamanla netleşir.

Alt görevler:
- [ ] 5.3.1 İK'nın kabul ettiği fotoğraflar örnek olarak işaretlenebilir.
- [ ] 5.3.2 3.3'teki açıklama üretimi bu örneklerle "şirketin kabul ettiği fotoğraf" tanımını üretir ve `prompt_description`'a ekler.

**Bitti sayılır:** Örnek eklendikçe açıklama güncelleniyor.

#### Faz 5 kapanış
- [ ] Kural ihlali olan fotoğraf Hazir'a girmiyor, gerekçesi yazılı.

---

### Faz 6: İşletme, maliyet ve dayanıklılık

**Amaç:** Sistemi sunucuda güvenle çalıştırmak, maliyeti görmek, veri kaybını önlemek.

**Bağımlılık:** Faz 2. Görevler birbirinden bağımsızdır.

#### 6.1 Maliyet ölçümü ve ucuz ön eleme (O)

**Neden:** Sayfa başına maliyet görülmeden optimizasyon yapılamaz.

Alt görevler:
- [ ] 6.1.1 Her PAGE_ANALYZED olayında token ve tahmini maliyet; parti ve ay bazında toplam panelde.
- [ ] 6.1.2 Ucuz model ön eleme: boş, neredeyse boş ve bariz tür sayfaları için MODEL_CHEAP; belirsiz olanlar ana modele. Eşik ayarlanabilir.
- [ ] 6.1.3 Metin katmanı olan sayfalarda görüntü çözünürlüğünü düşürme denemesi; doğruluk düşmüyorsa varsayılan yap.
- [ ] 6.1.4 Prompt önbellek isabet oranı olaylarda.

**Bitti sayılır:** Sayfa başı maliyet Faz 1 kapanışındaki ölçüme göre düşmüş ve doğruluk test matrisinde aynı.

#### 6.2 İşçi kuyruğu (O)

**Neden:** BackgroundTasks uygulama yeniden başlayınca işi kaybeder.

Alt görevler:
- [ ] 6.2.1 BackgroundTasks yerine veritabanı tabanlı iş kuyruğu veya Redis + RQ; ayrı `worker` servisi.
- [ ] 6.2.2 Yeniden deneme, zaman aşımı, aynı partinin iki kez işlenmesini önleyen kilit.
- [ ] 6.2.3 Uygulama yeniden başlayınca yarım kalan partiler kaldığı adımdan devam eder veya `failed` olur.

**Bitti sayılır:** Uygulama işlem ortasında yeniden başlatılınca parti kaybolmuyor.

#### 6.3 Erişim logu, yedekleme ve geri yükleme (O)

**Neden:** Kimlik belgeleri barındıran sistemde "kim baktı" ve "yedek var mı" soruları cevapsız kalamaz.

Alt görevler:
- [ ] 6.3.1 `access_log` panelde çalışan bazında görüntülenir.
- [ ] 6.3.2 Gece yedek: `data/` dizini ve veritabanı dökümü; sunucu dışı bir hedefe kopya.
- [ ] 6.3.3 Geri yükleme prosedürü yazılı ve bir kez denenmiş.
- [ ] 6.3.4 Disk şifreleme sunucu düzeyinde (LUKS veya sağlayıcının çözümü); uygulama düzeyinde şifreleme yok.

**Bitti sayılır:** Yedekten geri yükleme bir kez başarıyla denendi.

#### 6.4 Üretim dağıtımı (O)

**Neden:** Bölüm 25'teki alan adı ve sunucu kaynaklarının kullanımı.

Alt görevler:
- [ ] 6.4.1 Docker Compose: app, worker, bot, postgres, caddy; kalıcı volume'ler.
- [ ] 6.4.2 Caddy ile alan adı ve otomatik HTTPS.
- [ ] 6.4.3 Gizli değerler `.env` dosyasında, depoda değil; sunucuda dosya izinleri.
- [ ] 6.4.4 `healthcheck` ve otomatik yeniden başlatma.
- [ ] 6.4.5 Dağıtım komutu tek satır (`docker compose pull && up -d`), README'de.

**Bitti sayılır:** Sunucuda alan adıyla çalışıyor.

#### 6.5 İzleme (K)

**Neden:** Sessizce bozulan sistem en tehlikelisidir.

Alt görevler:
- [ ] 6.5.1 Hata olaylarında yönetici Telegram sohbetine mesaj (4.4.2 ile ortak).
- [ ] 6.5.2 Disk doluluğu ve kuyruk uzunluğu için basit eşik uyarıları.
- [ ] 6.5.3 Günlük özet: işlenen parti, üretilen belge, kuyruk büyüklüğü, maliyet.

**Bitti sayılır:** Bir hata üretildiğinde bildirim geliyor.

#### Faz 6 kapanış
- [ ] Sunucuda alan adıyla çalışıyor.
- [ ] Yedekten geri yükleme bir kez başarıyla denendi.
- [ ] Maliyet paneli gerçek rakam gösteriyor.

---

## 5. Kabul senaryoları

Her satır Faz 1.15'te otomatik test olur. "Beklenen" sütunu tartışmasız olmalıdır; belirsizlik varsa önce Bölüm 1'e karar eklenir.

| No | Senaryo | Beklenen |
|----|---------|----------|
| S1 | Tek sayfalık Rus pasaportu PDF; pasaport numarası kayıtlı çalışanla eşleşiyor | `Hazir/Ad_Soyad-Passport.pdf` passthrough; Alinan'a kopya; olay zinciri tam |
| S2 | S1'deki dosya ikinci kez yükleniyor | FILE_DUPLICATE; ikinci çıktı üretilmez; analiz çağrısı yok |
| S3 | Altı sayfalık PDF: ehliyet ön, profil fotoğrafı, başka belge, oturum kartı ön, oturum kartı arka, ehliyet arka | Residence-Card.pdf (sayfa 4-5); Profile-Picture.jpeg (sayfa 2); ehliyet sayfa 1 ve 6 Unresolved (K5); sayfa 3 türüne göre Hazir veya Unknown |
| S4 | Beş sayfalık sıralı PDF: ehliyet ön, ehliyet arka, foto, oturum ön, oturum arka | Driving-License.pdf, Profile-Picture.jpeg, Residence-Card.pdf; üç bağımsız çıktı |
| S5 | Aynı partide `on.jpg` ve `arka.jpg` ehliyet (direkt kapalı) | Tek Driving-License.pdf, kayıpsız sarma ve birleştirme |
| S6 | Pasaport (direkt açık) JPEG olarak geldi; katalog yalnızca PDF bekliyor | Unresolved; gerekçe "uygun formatta yeniden gönderin"; dönüşüm yapılmaz |
| S7 | Pasaport sayfası çok sayfalı PDF'in içinde | Tek sayfa `extract` ile Passport.pdf; sayfa nesnesi kopyalanır, render yok |
| S8 | PDF'in ortasında boş sayfa | PAGE_BLANK; atlanır; hata değil |
| S9 | Bulanık pasaport; belge numarası okunamıyor | Unreadable; gerekçe "Okunamayan alanlar: document_number" |
| S10 | Belge yalnızca isimle mevcut çalışanla eşleşiyor; numara ve doğum tarihi yok | Unresolved; otomatik eşleştirme yok; yeni çalışan yok |
| S11 | Temiz pasaport numarası; kayıtlı çalışan yok | Yeni çalışan E000n; klasör ve profil.md; belge Hazir'da |
| S12 | Aynı normalize isimli iki çalışan; belgede doğum tarihi birine uyuyor | O çalışana eşleşir. Her ikisine uyuyorsa veya hiçbirine uymuyorsa Unresolved (PERSON_AMBIGUOUS) |
| S13 | Kiril isimli belge | Latin görüntü adı + `original_script_name` profil ve profil.md'de |
| S14 | Katalogda olmayan tür (Peru diploması) | Unknown; aday tür kaydı; onay ve yeniden analizden sonra Hazir |
| S15 | Word CV, profil sayfasından yüklendi / genel yüklemeden yüklendi | `Hazir/Ad_Soyad-Attachment-<orijinal>.docx` değişmeden / Unresolved |
| S16 | Manuel taşıma tek onayla / iki onayla | Hiçbir değişiklik / taşınır, iki profil güncellenir, MANUAL_MOVE kullanıcı adıyla |
| S17 | Telegram: "Ahmet Çakar'ın ehliyetini göster"; iki ehliyet / tek ehliyet | Seçim sorusu / dosya gönderilir |
| S18 | Mevcut plandan yeniden çalıştırma | Aynı çıktılar; sağlayıcı hiç çağrılmaz; ikinci dosya üretilmez |

---

## 6. Riskler ve karşı önlemler

| Risk | Etki | Önlem |
|------|------|-------|
| Harf çevirisi farklılıkları aynı kişiyi iki kişi yapar | Çift profil | K6: numara önce; alias tablosu; yalnızca isim eşleşmesi otomatik değil |
| Model yanlış tür atar | Yanlış klasörde belge | K1 zorunlu alan kontrolü; 1.10 doğrulayıcılar; kuşkuda kuyruk; hiçbir zaman sessiz kabul |
| Model hayali değer üretir | Yanlış kimlik bilgisi | Prompt "tahmin etme"; MRZ kontrol haneleri; görünen metinle çelişki notu |
| Sayfa başı maliyet yüksek çıkar | İşletme gideri | Metin katmanı öncelik; boş sayfa eleme; 6.1 ucuz ön eleme; prompt önbelleği |
| Büyük PDF (yüzlerce sayfa) | Süre ve maliyet | MAX_PAGES_PER_FILE; aşan dosya reddedilir ve İK'ya bölmesi söylenir |
| Sağlayıcı kesintisi | Parti takılır | Yeniden deneme; parti `failed`; panelden yeniden çalıştırma; 6.2 kuyruk |
| Veri kaybı | Belgeler gider | Orijinal dokunulmaz; 6.3 yedek ve denenmiş geri yükleme |
| Hayalet çalışan | Kirli çalışan listesi | K7: numarasız belgeden profil açılmaz |
| İK yanlış çalışana taşır | Organizasyon bozulur | İki aşamalı onay; olay logu; arşiv var silme yok |
| Telegram fotoğraf sıkıştırması | Okunaksız belge | "Belge olarak gönderin" uyarısı; Unreadable gerekçesi |
| Katalog büyüdükçe prompt şişer | Maliyet ve doğruluk düşüşü | 3.4 token bütçesi; açıklamalar kısa tutulur; önbellek |

---

## 7. Faz özeti

| Faz | İçerik | Büyüklük | Bağımlılık | Çıktı |
|-----|--------|----------|------------|-------|
| 0 | İskelet, veritabanı, depolama, olay logu, katalog tohumu | O | yok | Çalışan boş uygulama |
| 1 | Çekirdek boru hattı | B | 0 | API ile uçtan uca belge işleme |
| 2 | Web paneli | B | 1 | İK'nın günlük kullanabileceği sistem |
| 3 | Katalog ve yeni tür öğrenme | O | 2 | Kendini genişleten belge bilgi tabanı |
| 4 | Telegram botu | O | 2 | Telefondan kullanım |
| 5 | Profil fotoğrafı kriterleri | K | 3 | Fotoğraf kalite kontrolü |
| 6 | İşletme ve maliyet | O | 2 | Sunucuda güvenli çalışma |

Faz 2 bittiğinde sistem gerçek kullanıma alınabilir. Faz 3, 4, 5 ve 6 kullanım sırasında eklenir.

---

## 8. İlk adım

Görev 0.1 ile başlanır. Oturum komutu:

`PLAN.md içindeki 0.1 numaralı görevi uygula. Bölüm 1'deki kararlara uy. Bitince alt görev kutucuklarını işaretle ve Durum satırını güncelle.`
