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

## 26 — 04.2 Ardışıklık güvenlik kuralı — done — 2026-09-14
- Yapıldı: `app/pipeline/group.py` — `group_file_pages` aynı dosyada aynı belgenin parçası olabilen (aynı katalog türü; `front_back`'te yalnız ön + yalnız arka, sıra fark etmez; tek yüzlüde toplam sayfa ≤ `expected_pages.max`; çelişmeyen kimlik) ve arasına başka aday ya da analizsiz sayfa girmiş adayları birleştirmeden `DocumentCandidate.contiguity_violation` (`ContiguityViolation`: R6, Unresolved, değersiz `reason`) ile işaretler; hüküm adayın `DOC_TYPE_DETERMINED` olayına veri + mesaj olarak yazılır. S3 kayıtları eklendi (`tests/fixtures/ai/recordings/s3_interleaved_pdf`).
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (810 geçti, +30; 3 PG testi atlandı), kapsam %99.53 (`app/pipeline/group.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 10 kural bozulması bellekte denendi, her biri testte kırmızı.
- Varsayımlar: PLAN.md §C19 — katalog dışı/türü belirsiz aday yargılanmaz (Unknown 04.6'nın); iki parçanın her biri tek başına geçerli olsa da (1+1 sayfalık çalışma izni) R7 gereği işaretlenir; analizsiz sayfa "başka belge olabilir", boş sayfa belge değil; gerekçede sayfa numarası 1'den; §8.3'te tür olmadığı için yeni olay türü yok; kuyruk kaydı/`QUEUED_UNRESOLVED` 08.1'in.
- Sonraki pencereye not: 06.1 `contiguity_violation` dolu adaya `route: unresolved`, `route_reason: reason` yazmalı ve başka kontrol onu Hazir'a çevirmemeli; 04.3 işaretli parçayı dosyalar arası eşleştirmeye sokmamalı (eşi aynı dosyada, araya belge girmiş); bitişik ya da yalnız boş sayfayla ayrılmış eksik parçalar işaretsiz kalır, rotaları 04.5/06.5'in.

## 25 — 04.1 Dosya içi gruplama ve ön/arka eşleşmesi — done — 2026-09-14
- Yapıldı: `app/pipeline/group.py` — `group_file_pages` (saf çekirdek) ve `group_upload` bir dosyanın analiz edilmiş sayfalarını belge adaylarına ayırır: ardışık (yalnız 02.4 boş sayfası atlanır), `continues_previous_page: true`, aynı tür ve kimlik değerleri çelişmeyen sayfa açık adaya katılır; `front_back` türde ön yüz onu izleyen arka yüzle sırayla eşleşir; aday başına `DOC_TYPE_DETERMINED`/`DOC_TYPE_UNKNOWN` yazılır. S4 kayıtları eklendi (`tests/fixtures/ai/recordings/s4_sequential_pdf`).
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (780 geçti, +55; 3 PG testi atlandı), kapsam %99.42 (`app/pipeline/group.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 5 kural bozulması bellekte denendi, her biri testte kırmızı.
- Varsayımlar: PLAN.md §C18 — "ardışık" devam işaretiyle okunur (`false` böler, C14); analizi başarısız ve analizcinin boş dediği sayfa zinciri kırar; sayfa sayısı sınırında bölünmez; kişi çelişkisi yalnız iki sayfada da dolu belge numarası/doğum tarihi/ad alanlarında (isimde kelime kümesi kapsama); katalog dışı türde yüz sınır değil.
- Sonraki pencereye not: 04.2/04.3 `FileGrouping.candidates` üzerinde çalışmalı — eksik yüzlü aday (`sides == (front,)` ya da `(back,)`) 04.1'de aday olarak kalır, rota vermez; `CandidatePage.file_id` dosyalar arası adayı aynı tiple kurmaya izin verir; aday sayfa listesi boş sayfayı atlayabilir (`[0, 2]`), 06.2 bunu ardışık alt küme okumalı; 04.6 `DOC_TYPE_UNKNOWN`'u yeniden yazmamalı.

## 24 — 03.7 Sayfa analizi çalıştırıcı — done — 2026-09-14
- Yapıldı: `analyze_upload` (`app/pipeline/analyze.py`) partinin boş olmayan, tekrar olmayan sayfalarını dosya/sayfa sırasıyla tek tek analiz eder; istek metnine sayfa sırası, aynı dosyadaki önceki analiz edilen sayfanın kişisel değer taşımayan yapısal özeti ve metin katmanı girer; sayfa hatası o sayfayı `failed` + `PAGE_ANALYSIS_FAILED` yapar, diğerleri tamamlanır ve parti `partial` olur.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (725 geçti, +23; 3 PG testi atlandı), kapsam %99.38 (`app/pipeline/analyze.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0.
- Varsayımlar: PLAN.md §C17 — boş sayfa/tekrar dosyası `skipped`; özet deterministik ve değersiz (tür, yüz, dil, alan adları, evet/hayır), boş sayfa zinciri kırmaz, dosya sınırında sıfırlanır; yakalanan hatalar yalnız `ProviderError`/`PageAnalysisError`/`PageImageError`; `partial` tüm sayfalar başarısızken de yazılır, başarıda durum değişmez; oturum commit edilmez.
- Sonraki pencereye not: 04.1 `continues_previous_page`'i "analize gönderilen önceki sayfanın devamı" olarak okumalı (boş sayfalar atlanmış); 09.2 analizden önce `analyzing`'i kendisi yazmalı, `partial`'ı planlama/uygulama boyunca koruyup sonda `done` yerine bırakmalı ve SQLite kilidi için işlem sınırını (sayfa başına commit) belirlemeli.

## 23 — 03.6 Kayıtlı yanıt sağlayıcısı (test altyapısı) — done — 2026-09-14
- Yapıldı: `RecordingProvider` (`app/ai/recording_provider.py`) — `AnalysisProvider`'ı ağ çağrısı yapmadan uygular, `tests/fixtures/ai/recordings/<senaryo>/<sıra>.json` kayıtlarını dosya adına göre sıralı okuyup ortak `validate_page_analysis`'ten geçirir; iki sentetik kayıt (`russian_passport`, `serbian_residence_card` ön/arka) eklendi.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (702 geçti, +8 durum; 3 PG testi atlandı), kapsam %99.44 (`app/ai/recording_provider.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0.
- Varsayımlar: PLAN.md §C16 — kayıt sırası dosya adına göredir (`0.json`, `1.json`, ...) ve `analyze_page` çağrı sırasıyla eşlenir; `PROVIDER_FACTORIES`'e eklenmedi, sağlayıcı doğrudan `RecordingProvider.from_directory(...)` ile kurulur.
- Sonraki pencereye not: 03.7 (sayfa analizi çalıştırıcı) ve sonrası, canlı sağlayıcı yerine `RecordingProvider.from_directory(tests/fixtures/ai/recordings/<senaryo>)` kullanarak uçtan uca ağsız test yazabilir; yeni senaryo eklerken dosyaları `0.json`, `1.json` sırasıyla adlandırmalı.

## 22 — 03.5 Yeniden deneme ve hata dayanıklılığı — done — 2026-09-14
- Yapıldı: `AnalysisProvider.analyze_page`'e (`app/ai/provider.py`) hız sınırı (429) ve 5xx'te en fazla 3 deneme yapan geri çekilmeli (`time.sleep`, 1 sn/2 sn üstel) `_request_analysis_with_retry` sarmalayıcısı eklendi; bağlantı hatası, diğer 4xx ve `PageAnalysisError` yeniden denenmez.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (694 geçti, +11 durum net; 3 PG testi atlandı), kapsam %99.32 (`app/ai/provider.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: PLAN.md §C15 — yalnız `ProviderRateLimitError`/`ProviderServerError` yeniden denenir (PRD kabul kriteri yalnız bunları sayıyor; C13'ün bıraktığı karar); geri çekilme sabit üstel (1 sn/2 sn), `Retry-After` okunmaz, süre ayarlanamaz.
- Sonraki pencereye not: `tests/ai/conftest.py`'deki `no_sleep` fixture'ı (`app.ai.provider.time.sleep` monkeypatch) yeniden deneme geciktiren her yeni AI testinde kullanılmalı — mock'lanmadan `analyze_page` çağıran bir test hız sınırı/5xx senaryosunda gerçekten uyur. 03.7 (sayfa analizi çalıştırıcı) `analyze_page`'i doğrudan çağırabilir, ayrı bir yeniden deneme katmanına gerek yok.

## 21 — 03.4 Analiz promptu ve disiplin kuralları — done — 2026-09-14
- Yapıldı: `app/ai/prompts/page_analysis.md` — "Tahmin etme", "Okuyamadığını `legible: false` yap", "Katalogda yoksa aday öner" kurallarını alan açıklamalarından önce taşıyan sağlayıcıdan bağımsız sistem talimatı; `build_page_analysis_instructions(catalog)` (`app/ai/prompts/page_analysis.py`) tek `{{catalog}}` yuvasına etkin + `analyze: true` türleri slug sırasıyla yazar ve metinle aynı `known_slugs`'ı döner.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (683 geçti, +34 durum; 3 PG testi atlandı), kapsam %99.42 (`app/ai/prompts` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0. Canlı prompt testi (`-m live`) anahtar olmadığı için koşulmadı.
- Varsayımlar: PLAN.md §C14 — katalog talimata sade liste olarak girer (kompakt derleme 11.4), `attachment`/pasif tür sunulmaz; `fields` sayfa başınadır ve bu sayfada okunmayan (yüzde bulunmayan dahil) zorunlu alan `legible: false`'tur; `continues_previous_page` emin değilse `false`; görünen alan ve MRZ birbirinden doldurulmaz.
- Sonraki pencereye not: 03.7 `PageAnalysisRequest(instructions=ins.text, known_slugs=ins.known_slugs, …)` ile ikisini birlikte vermeli ve `prompt`'a `page_index`'i, varsa metin katmanını ve önceki sayfa özetini yazmalı (talimat bunlara atıf yapar); 04.4 okunaklılığı adayın sayfaları üzerinden birleştirmeli (arka yüzdeki `legible: false` alanın o yüzde olmaması olabilir). İlk anahtarlı ortamda `pytest -m live tests/ai/test_prompts.py`.

## 19 — 03.2 Sağlayıcı soyutlaması ve Anthropic uygulaması — done — 2026-09-14
- Yapıldı: `app/ai/provider.py` — sağlayıcıdan bağımsız `PageAnalysisRequest`/`PageImage`, yanıt kabulü ortak ve atlanamaz `AnalysisProvider.analyze_page` (§8.4 + katalog + `page_index` eşitliği), `ProviderError` aileleri ve `AI_PROVIDER` ile seçilen `create_provider`/`PROVIDER_FACTORIES`; `app/ai/anthropic_provider.py` — görüntü + metni zorlanmış `record_page_analysis` aracıyla (şema `PageAnalysis.model_json_schema()`) gönderip doğrulanmış `PageAnalysis` döner.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (649 geçti, +82 durum; 3 PG testi atlandı), kapsam %99.41 (yeni modüller %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0. Canlı Anthropic testi (`-m live`) anahtar olmadığı için koşulmadı.
- Varsayımlar: PLAN.md §C13 — katı `output_config.format` yerine zorlanmış araç çağrısı (§8.4 `fields` sözlüğü katı şemaya sığmıyor), düşünme kapalı, SDK yeniden denemesi kapalı (`max_retries=0`), varsayılan model `claude-opus-5`; yeni bağımlılık `anthropic>=1.5` (yerelde `uv pip install --python .venv/Scripts/python.exe -e ".[dev]"`).
- Sonraki pencereye not: 03.5 yeniden denemeyi `analyze_page` çevresine kurmalı ve `ProviderRateLimitError`/`ProviderServerError`'ı yakalamalı (`PageAnalysisError` yeniden denenmez); 03.3 `openai`'yi `PROVIDER_FACTORIES`'e ekler; 03.4/03.7 prompta sayfa sırasını yazmalı, yanıtın `page_index`'i istekle eşleşmezse reddedilir. İlk anahtarlı ortamda `pytest -m live tests/ai/test_anthropic_provider.py` ile araç şemasının API'ce kabulü doğrulanmalı.

## 18 — 03.1 Sayfa analizi şeması — done — 2026-09-14
- Yapıldı: `app/ai/schemas.py` — §8.4 pydantic sözleşmesi (`PageAnalysis`, `PagePerson`, `PageContact`, `FieldReading`, `Script`, `Side`, ISO 639-1 kümesi) ve yanıt kabul girişi `validate_page_analysis(data, known_slugs=…)`; uymayan yanıt `PageAnalysisError` (her ihlal konumuyla, değersiz mesaj) ile reddedilir, `PagePerson.employee_fields()` kişiyi `employees` sütunlarına (`other_names` dahil) eşler.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (567 geçti, +165 durum; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.35 (`app/ai` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0.
- Varsayımlar: PLAN.md §C12 — tüm §8.4 anahtarları zorunlu, `person`/`contact` hep nesne, okunmayan değer `null`; metinsiz sayfada `language`/`script` `null` olabilir; `legible: true` ⇔ `value` dolu; slug katalog denetimi yalnız yanıt kabulünde (saklanan `analysis_json` katalogsuz `PageAnalysis.model_validate` ile okunur).
- Sonraki pencereye not: 03.2 yapılandırılmış çıktı için `PageAnalysis.model_json_schema()`'yı kullanmalı (tüm anahtarlar `required`, `language`/`script`/`side` `enum`); sağlayıcı yanıtı mutlaka `validate_page_analysis`'ten geçmeli — `known_slugs` analizde prompta verilen kataloğun slug'larıdır. MRZ satır biçimi şemada denetlenmez (05.3'ün işi).

## 17 — 02.5 Gömülü tek görüntü tespiti — done — 2026-09-14
- Yapıldı: `single_full_page_image_xref`/`detect_pdf_single_image_pages`/`mark_upload_file_single_image_pages` (`app/pipeline/render.py`) — sayfa MuPDF kayıt aygıtıyla (`_PaintRecorder`, `pymupdf.mupdf.FzDevice2`) çalıştırılır; yalnız çıkarılan görüntünün sayfada görünenle aynı olduğu kesinse `pages.has_single_embedded_image=True` yazılır ve xref döner.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (402 geçti, +38 durum; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.30 (yeni kod %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0.
- Varsayımlar: PRD ölçüt vermiyor; belirsizlikte işaret verilmez (yanlış işaret görünen içeriği düşürür, eksik işaret yalnız `render_image`'a düşer). Görünmez OCR metni serbest, tolerans 1 pt modül sabiti; tüm kurallar PLAN.md §C11. Olay yazılmıyor (§D6, 02.4'teki soru ile aynı).
- Sonraki pencereye not: 07.5.1 (`extract_image`) xref'i yeniden aramak yerine `single_full_page_image_xref(page)`'i çağırmalı — işaretle aynı kuralı paylaşır; `None` dönerse `render_image`'a düşülür. Orkestrasyona (09.x) bağlanmadı.

## 16 — 02.4 Boş sayfa tespiti — done — 2026-09-14
- Yapıldı: `is_page_blank`/`detect_pdf_blank_pages`/`mark_upload_file_blank_pages` (`app/pipeline/render.py`) — sayfa yalnız metin katmanı, gömülü görüntü ve çizimin üçü de yoksa boş sayılır (PDF içerik nesnelerine bakar, OCR/piksel analizi yok); boş bulunan sayfaya `pages.is_blank=True` yazılır ve `PAGE_BLANK` olayı atılır, hata fırlatılmaz.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (364 geçti, +10 durum; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.11 (`app/pipeline/render.py` %99, yeni kod %100), temiz SQLite'ta `alembic upgrade head` (göç yok — `is_blank` sütunu zaten 00.3'te vardı), `import app.main` — hepsi exit 0.
- Varsayımlar: PRD/karar tablosu eşik/algoritma vermiyor; "fiziksel boş" PDF'in kendi içerik nesnelerine (metin/görüntü/çizim) bakılarak, piksel analizi olmadan belirlendi (K11) — metinsiz taranmış sayfa (02.2.1) gömülü görüntü taşıyorsa boş sayılmaz. `mark_upload_file_blank_pages` `extract_upload_file_text` ile simetrik: var olan `Page` satırını günceller, yalnız `is_blank`'e dokunur, `render_upload_file`'ın alanlarına dokunmaz.
- Sonraki pencereye not: "Analizciye gönderilmez" kabul kriterinin ikinci yarısı henüz bağlanmadı — 03.7 (sayfa analizi çalıştırıcı) veya 09.x orkestrasyonu `pages.is_blank`'i okuyup atlamalı. 02.5 (gömülü tek görüntü tespiti) aynı `Page` satırlarına yazacak, yenisini açmamalı.

## 15 — 02.3 Görüntü dosyaları için analiz kopyası — done — 2026-09-14
- Yapıldı: `render_image_copy`/`render_image_file` (`app/pipeline/render.py`) — JPEG/PNG'nin EXIF yönelimi Pillow `ImageOps.exif_transpose` ile fiziksel olarak uygulanmış kopyası kaynağın kendi biçiminde `cache/pages/<file_id>/0000.<uzantı>` altına yazılır (K10: orijinale dokunulmaz), `pages`/`page_count=1` yazılır, `PAGE_RENDERED` olayı atılır (02.1 ile aynı sözleşme).
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (354 geçti, +10 durum; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.10 (`app/pipeline/render.py` %99, `app/storage/layout.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: analiz kopyası kaynağın biçimini korur (JPEG→jpg, PNG→png), PDF render'ının aksine JPEG'e dönüştürülmez — PNG alfa/format dönüşümü kararı gerektirmediği için (bkz. PLAN.md §K02.3). Bunun için `DataLayout.page_image_path`'e geriye dönük uyumlu `extension` parametresi eklendi (yol kuralı MASTER-PROMPT §4 — görevin ÇIKTI alanı yalnız render.py'yi listeliyordu ama yol üretimi app/storage/ dışında yapılamaz).
- Sonraki pencereye not: 02.4 (boş sayfa) ve 02.5 (gömülü tek görüntü) hem PDF hem görüntü dosyası `Page` satırlarını (index 0 dahil) güncelleyecek; hangi adımın PDF mi görüntü mü işlediğine karar veren yönlendirme (hangi dosya türünde `render_upload_file` mi `render_image_file` mi çağrılacağı) henüz 09.x orkestrasyonunun işi, burada bağlanmadı.

## 14 — 02.2 PDF metin katmanı çıkarma — done — 2026-09-14
- Yapıldı: `app/pipeline/render.py`'ye `extract_page_text`/`extract_pdf_text`/`extract_upload_file_text` eklendi — PyMuPDF `get_text()` ile sayfanın gömülü metin katmanı okunur, boşsa (taranmış sayfa) `text_layer` `None` kalır; `render_pdf_pages`'in PDF açma/doğrulama mantığı `_open_pdf` ortak yardımcısına çıkarıldı.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (344 geçti, +9 durum; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.38 (`app/pipeline/render.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0.
- Varsayımlar: PRD §8.3'ün kapalı olay listesinde metin katmanı için ayrı tür yok; bu adım yeni olay atmıyor (PLAN.md §D6).
- Sonraki pencereye not: `extract_upload_file_text` var olan `Page` satırını günceller (render'da açılmışsa), yoksa açar; yalnız `text_layer`'a dokunur — `image_path`/`page_count` render'ın işi. Orkestrasyona (hangi adımın hangi sırayla çağrılacağı) henüz bağlanmadı, bu 09.x'in işi. 02.4 (boş sayfa) ve 02.5 (gömülü tek görüntü) aynı `Page` satırlarına yazmalı, yenisini açmamalı; onlar da aynı "yeni olay yok" sorusuyla karşılaşabilir.

## 13 — 02.1 PDF sayfa görüntüsü üretimi — done — 2026-09-14
- Yapıldı: `app/pipeline/render.py` — PyMuPDF ile her PDF sayfası `PAGE_RENDER_DPI`'da render edilir, uzun kenar `PAGE_RENDER_MAX_LONG_EDGE_PX`'i aşacaksa ölçek sınıra küçültülür, JPEG `cache/pages/<file_id>/0000.jpg` altına atomik yazılır; `render_upload_file` `pages` satırlarını + `page_count`'u yazar ve sayfa başına `PAGE_RENDERED` olayı atar. Yol kuralı için `DataLayout.page_image_path` ve DB'deki göreli yolu kökten kaçmadan çözen `DataLayout.resolve` eklendi.
- Doğrulama: ruff check/format, compileall, `pytest -q -m "not live"` (335 geçti, +48 durum; 3 PG testi ortam değişkeni yokken atlandı), kapsam %99.21 (`app/pipeline/render.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0. Şema değişmedi, göç yok.
- Varsayımlar: PLAN.md §C10 — varsayılan 200 DPI / 1568 px uzun kenar / JPEG kalite 90; küçültme render ölçeğine uygulanır (yeniden örnekleme yok); önbellek türev veri olduğu için yeniden render `replace_file` ile üzerine yazar.
- Sonraki pencereye not: `pymupdf` bağımlılığı eklendi (yerelde `uv pip install --python .venv/Scripts/python.exe -e ".[dev]"`). `render_upload_file` commit etmez ve PDF olmayan dosyada `RenderError` verir — görüntü dosyaları 02.3.1'in, parti durumu/tekrar dosyası atlama 09.2.x orkestrasyonunun işi; 02.2/02.4/02.5 aynı `Page` satırlarına yazmalı, yenisini açmamalı.

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
