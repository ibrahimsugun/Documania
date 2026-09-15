# PLAN — belgeee (neredeyiz?)

> Bu dosya projenin **durum haritasıdır**. Ne yapılacağı `urun-gereksinim-dokumani-PRD.md`'de,
> nasıl yapılacağı `MASTER-PROMPT.md`'de, "bitti"nin tanımı `CONVENTIONS.md`'dedir.
> Bu dosyayı bir izleme paneli ayrıştırır — biçim kuralları kesindir (§1).

## 0. Özet tablo

| Faz | PRD | Genel durum | Must sayacı | Kapanış |
| --- | --- | --- | --- | --- |
| Faz 0 — MVP | §5.1 | 58 ✅ · 0 ◐ · 44 ⬜ · 0 🔒 | 56/98 Must | AÇIK |
| Faz 1 — v1 | §5.2 | 0 ✅ · 0 ◐ · 0 ⬜ · 32 🔒 | 0/21 Must | AÇIK |
| Faz 2 — v2 | §5.3 | 0 ✅ · 0 ◐ · 0 ⬜ · 13 🔒 | 0/0 Must | AÇIK |
| Faz 3 — Enterprise | §5.4 | 0 ✅ · 0 ◐ · 0 ⬜ · 8 🔒 | 0/0 Must | AÇIK |

## 1. Bu planın nasıl okunacağı

### 1.1 Temel kural

**PRD kimliği olmayan iş yapılmaz.** Her satır bir PRD gereksinimidir; her Task Master
görevi bir PRD kimliğine bağlanır. Kimliksiz iş ne fazda sayılır ne kapsam denetiminden geçer.

### 1.2 Durum işaretleri (değiştirme)

| İşaret | Anlamı |
| --- | --- |
| ✅ | Teslim edildi — kod + test yeşil + commit |
| ◐ | Kısmi — çekirdek var, kabul kriteri tamamlanmadı |
| ⬜ | Açık — kod yok |
| 🔒 | Bu fazda yapılmayacak (sonraki faza ait) |
| ⛔ | Kapsam dışı |

Damga değiştirme yetkisi **yalnız görev pencerelerinindir**. Elle ✅ yazmak, panelde
`suspicious-done` bulgusu doğurur.

### 1.3 Kanıt nerede durur

`Durum` hücresi **yalnız** damga + kanıt referansı taşır: `✅ → K04.1`. Kanıt metni
(dosya · test · tm id) hücreye değil, `## K. Kanıt Geçmişi` bölümündeki `#### K04.1`
bloğuna madde olarak yazılır. Sebebi `CONVENTIONS.md` §1.2'de.

### 1.4 Sayım kuralı

§0'daki sayılar **tablolardan sayılarak** yazılır, tahminle değil. Elle yazılmış sayı
panelde `plan-count-drift` bulgusu doğurur.

## 2. Modül × Faz matrisi

| Modül | Ad | Faz | Kalem |
| --- | --- | --- | --- |
| FR-MOD-00 | Altyapı ve iskelet | 0 | 18 |
| FR-MOD-01 | Yükleme ve Inbox | 0 | 8 |
| FR-MOD-02 | Sayfa üretimi | 0 | 5 |
| FR-MOD-03 | Yapay zekâ analiz katmanı | 0 | 12 |
| FR-MOD-04 | Karar motoru | 0 | 10 |
| FR-MOD-05 | Kimlik ve çalışan eşleştirme | 0 | 15 |
| FR-MOD-06 | Plan ve doğrulayıcılar | 0 | 10 |
| FR-MOD-07 | Uygulayıcı | 0 | 9 |
| FR-MOD-08 | Kuyruklar ve çözüm | 0 | 5 |
| FR-MOD-09 | Çalışan profili ve orkestrasyon | 0 | 10 |
| FR-MOD-10 | Web yönetim paneli | 1 | 21 |
| FR-MOD-11 | Belge türü kataloğu ve öğrenme | 1, 2 | 15 |
| FR-MOD-12 | Telegram botu | 2 | 9 |
| FR-MOD-13 | İşletme, maliyet ve dayanıklılık | 3 | 8 |

## 3. FAZ 0 — MVP (PRD §5.1)

### 3.1 FR-MOD-00 — Altyapı ve iskelet

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 00.1.1 | Python 3.12 + FastAPI uygulama iskeleti | Must (MVP) | ✅ → K00.1 |
| 00.1.2 | Bağımlılık yönetimi ve test komutu | Must (MVP) | ✅ → K00.1 |
| 00.1.3 | Docker Compose ile ayağa kalkma | Must (MVP) | ✅ → K00.1 |
| 00.1.4 | Lint ve biçim kapısı | Must (MVP) | ✅ → K00.1 |
| 00.2.1 | Ortam değişkeni tabanlı yapılandırma | Must (MVP) | ✅ → K00.2 |
| 00.2.2 | Eksik zorunlu ayarda anlaşılır hata | Must (MVP) | ✅ → K00.2 |
| 00.3.1 | Veri modeli (§8'deki 15 tablo) | Must (MVP) | ✅ → K00.3 |
| 00.3.2 | Göç altyapısı | Must (MVP) | ✅ → K00.3 |
| 00.3.3 | Çalışan numarası üretici | Must (MVP) | ✅ → K00.3 |
| 00.4.1 | Veri dizini otomatik oluşturma | Must (MVP) | ✅ → K00.4 |
| 00.4.2 | İsim sadeleştirme (slug) | Must (MVP) | ✅ → K00.4 |
| 00.4.3 | Çıktı adlandırma ve sıra eki | Must (MVP) | ✅ → K00.4 |
| 00.4.4 | Bütünlük ve atomik yazma | Must (MVP) | ✅ → K00.4 |
| 00.5.1 | Olay logu altyapısı | Must (MVP) | ✅ → K00.5 |
| 00.5.2 | Olay bağlamı yöneticisi | Must (MVP) | ✅ → K00.5 |
| 00.6.1 | Katalog şeması ve tutarlılık kuralı | Must (MVP) | ✅ → K00.6 |
| 00.6.2 | Başlangıç belge türleri | Must (MVP) | ✅ → K00.6 |
| 00.6.3 | Katalog YAML ↔ veritabanı eşitleme | Should (v1) | ✅ → K00.6 |

### 3.2 FR-MOD-01 — Yükleme ve Inbox

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 01.1.1 | Çoklu dosya yükleme uç noktası | Must (MVP) | ✅ → K01.1 |
| 01.1.2 | Bağlam çalışanı ile yükleme | Must (MVP) | ✅ → K01.1 |
| 01.2.1 | İçerik tabanlı tür tespiti | Must (MVP) | ✅ → K01.2 |
| 01.2.2 | Desteklenmeyen türün reddi | Must (MVP) | ✅ → K01.2 |
| 01.3.1 | Boyut ve sayfa sınırı | Must (MVP) | ✅ → K01.3 |
| 01.4.1 | Tekrar yükleme tespiti | Must (MVP) | ✅ → K01.4 |
| 01.5.1 | Inbox'a değişmez yazma | Must (MVP) | ✅ → K01.5 |
| 01.6.1 | Parti durumu sorgulama | Must (MVP) | ✅ → K01.6 |

### 3.3 FR-MOD-02 — Sayfa üretimi

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 02.1.1 | PDF sayfa görüntüsü üretimi | Must (MVP) | ✅ → K02.1 |
| 02.2.1 | PDF metin katmanı çıkarma | Must (MVP) | ✅ → K02.2 |
| 02.3.1 | Görüntü dosyaları için analiz kopyası | Must (MVP) | ✅ → K02.3 |
| 02.4.1 | Boş sayfa tespiti | Must (MVP) | ✅ → K02.4 |
| 02.5.1 | Gömülü tek görüntü tespiti | Must (MVP) | ✅ → K02.5 |

### 3.4 FR-MOD-03 — Yapay zekâ analiz katmanı

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 03.1.1 | Sayfa analizi şeması | Must (MVP) | ✅ → K03.1 |
| 03.1.2 | Dil ve alfabe tespiti | Must (MVP) | ✅ → K03.1 |
| 03.1.3 | Diğer isimler alanı | Must (MVP) | ✅ → K03.1 |
| 03.1.4 | İletişim bilgisi alanları | Must (MVP) | ✅ → K03.1 |
| 03.2.1 | Sağlayıcı soyutlaması | Must (MVP) | ✅ → K03.2 |
| 03.2.2 | Anthropic sağlayıcı | Must (MVP) | ✅ → K03.2 |
| 03.3.1 | OpenAI sağlayıcı iskeleti | Should (v1) | ⬜ |
| 03.4.1 | Analiz promptu disiplini | Must (MVP) | ✅ → K03.4 |
| 03.5.1 | Yeniden deneme ve dayanıklılık | Must (MVP) | ✅ → K03.5 |
| 03.6.1 | Kayıtlı yanıtla test sağlayıcısı | Must (MVP) | ✅ → K03.6 |
| 03.7.1 | Sayfa analizi çalıştırıcı | Must (MVP) | ✅ → K03.7 |
| 03.7.2 | Kısmi başarı davranışı | Must (MVP) | ✅ → K03.7 |

### 3.5 FR-MOD-04 — Karar motoru

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 04.1.1 | Dosya içi gruplama | Must (MVP) | ✅ → K04.1 |
| 04.1.2 | Ön/arka yüz yapısı | Must (MVP) | ✅ → K04.1 |
| 04.2.1 | Ardışıklık güvenlik kuralı (R6) | Must (MVP) | ✅ → K04.2 |
| 04.3.1 | Dosyalar arası gruplama | Must (MVP) | ✅ → K04.3 |
| 04.3.2 | Belirsiz eşleştirmenin reddi | Must (MVP) | ✅ → K04.3 |
| 04.4.1 | Zorunlu alan okunaklılık kapısı (R1) | Must (MVP) | ✅ → K04.4 |
| 04.4.2 | Kabul kriteri değerlendirmesi | Should (v1) | ✅ → K04.4 |
| 04.5.1 | Beklenen sayfa sayısı kontrolü | Must (MVP) | ✅ → K04.5 |
| 04.6.1 | Bilinmeyen tür → aday öneri | Must (MVP) | ✅ → K04.6 |
| 04.7.1 | Word/Excel yolu (Attachment) | Must (MVP) | ✅ → K04.7 |

### 3.6 FR-MOD-05 — Kimlik ve çalışan eşleştirme

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 05.1.1 | İsim normalizasyonu | Must (MVP) | ✅ → K05.1 |
| 05.2.1 | Harf çevirisi | Must (MVP) | ✅ → K05.2 |
| 05.3.1 | MRZ ayrıştırma | Must (MVP) | ✅ → K05.3 |
| 05.3.2 | MRZ kontrol hanesi doğrulaması | Must (MVP) | ✅ → K05.3 |
| 05.3.3 | MRZ önceliği | Must (MVP) | ✅ → K05.3 |
| 05.4.1 | Kişi anahtarı | Must (MVP) | ✅ → K05.4 |
| 05.5.1 | Eşleştirme sırası | Must (MVP) | ⬜ |
| 05.5.2 | Yalnız isim eşleşmesinin reddi (R8) | Must (MVP) | ⬜ |
| 05.5.3 | Belirsiz eşleşme | Must (MVP) | ⬜ |
| 05.6.1 | Otomatik çalışan oluşturma (R9) | Must (MVP) | ⬜ |
| 05.7.1 | Onay bekleyen profil | Must (MVP) | ⬜ |
| 05.7.2 | Alias ve numara birikimi | Must (MVP) | ⬜ |
| 05.8.1 | İletişim bilgisi saklama | Must (MVP) | ⬜ |
| 05.8.2 | İletişim bilgisi çakışması | Must (MVP) | ⬜ |
| 05.8.3 | Dil ve alfabe kaydı | Should (v1) | ⬜ |

### 3.7 FR-MOD-06 — Plan ve doğrulayıcılar

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 06.1.1 | Plan JSON üretimi (R10) | Must (MVP) | ⬜ |
| 06.1.2 | Plan determinizmi | Must (MVP) | ⬜ |
| 06.2.1 | İşlem seçimi | Must (MVP) | ⬜ |
| 06.3.1 | Direkt Belge kuralı (R5) | Must (MVP) | ⬜ |
| 06.3.2 | Direkt Belge format kontrolü | Must (MVP) | ⬜ |
| 06.4.1 | Dönüşüm izni kontrolü | Must (MVP) | ⬜ |
| 06.5.1 | Doğrulayıcı seti | Must (MVP) | ⬜ |
| 06.5.2 | Doğrulama başarısızlığı | Must (MVP) | ⬜ |
| 06.6.1 | Planı yeniden çalıştırma | Must (MVP) | ⬜ |
| 06.6.2 | Yeniden analiz ve sürüm | Must (MVP) | ⬜ |

### 3.8 FR-MOD-07 — Uygulayıcı

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 07.1.1 | passthrough | Must (MVP) | ⬜ |
| 07.2.1 | extract | Must (MVP) | ⬜ |
| 07.3.1 | merge | Must (MVP) | ⬜ |
| 07.4.1 | wrap_image | Must (MVP) | ⬜ |
| 07.5.1 | extract_image | Must (MVP) | ⬜ |
| 07.6.1 | render_image | Must (MVP) | ⬜ |
| 07.7.1 | Çıktı yazma ve köken (R13) | Must (MVP) | ⬜ |
| 07.7.2 | Alinan kopyası | Must (MVP) | ⬜ |
| 07.8.1 | İdempotenlik | Must (MVP) | ⬜ |

### 3.9 FR-MOD-08 — Kuyruklar ve çözüm

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 08.1.1 | Kuyruğa yönlendirme (R7) | Must (MVP) | ⬜ |
| 08.1.2 | Gerekçe içeriği | Must (MVP) | ⬜ |
| 08.2.1 | Kuyruk öğesini çalışana atama | Must (MVP) | ⬜ |
| 08.3.1 | Onay bekleyen profili onaylama | Must (MVP) | ⬜ |
| 08.4.1 | Arşive taşıma (R11) | Must (MVP) | ⬜ |

### 3.10 FR-MOD-09 — Çalışan profili ve orkestrasyon

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 09.1.1 | profil.md üretimi | Must (MVP) | ⬜ |
| 09.1.2 | Orijinal yazım gösterimi | Must (MVP) | ⬜ |
| 09.1.3 | Profil içeriği eksiksizliği | Must (MVP) | ⬜ |
| 09.2.1 | Parti durum makinesi | Must (MVP) | ⬜ |
| 09.2.2 | Uçtan uca orkestrasyon | Must (MVP) | ⬜ |
| 09.2.3 | Hata dayanıklılığı | Must (MVP) | ⬜ |
| 09.3.1 | Sentetik belge üreteci | Must (MVP) | ⬜ |
| 09.3.2 | Kabul senaryoları S1–S5 | Must (MVP) | ⬜ |
| 09.3.3 | Kabul senaryoları S6–S10 | Must (MVP) | ⬜ |
| 09.3.4 | Kabul senaryoları S11–S15 ve S18 | Must (MVP) | ⬜ |

## 4. FAZ 1 — v1 (PRD §5.2)

### 4.1 FR-MOD-10 — Web yönetim paneli

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 10.1.1 | Panel iskeleti ve gezinme | Must (v1) | 🔒 |
| 10.1.2 | Oturum tabanlı giriş | Must (v1) | 🔒 |
| 10.1.3 | İlk kullanıcı oluşturma | Must (v1) | 🔒 |
| 10.2.1 | Yükleme sayfası | Must (v1) | 🔒 |
| 10.2.2 | İlerleme görünümü | Should (v1) | 🔒 |
| 10.3.1 | Yükleme detay sayfası | Must (v1) | 🔒 |
| 10.3.2 | Yeniden çalıştır / yeniden analiz | Should (v1) | 🔒 |
| 10.4.1 | Çalışan listesi | Must (v1) | 🔒 |
| 10.4.2 | Arama | Must (v1) | 🔒 |
| 10.5.1 | Çalışan profili sayfası | Must (v1) | 🔒 |
| 10.5.4 | Profil fotoğrafı yokluğu | Should (v1) | 🔒 |
| 10.5.2 | Belge listesi ve açma | Must (v1) | 🔒 |
| 10.5.3 | Profil sayfasından yükleme | Should (v1) | 🔒 |
| 10.6.1 | Belge geçmişi | Must (v1) | 🔒 |
| 10.7.1 | Kuyruk ekranları | Must (v1) | 🔒 |
| 10.7.2 | Kuyruktan çalışana atama | Must (v1) | 🔒 |
| 10.7.3 | Kuyruktan profil oluşturma | Must (v1) | 🔒 |
| 10.8.1 | İki aşamalı onay mekanizması | Must (v1) | 🔒 |
| 10.8.2 | Belgeyi başka çalışana taşıma | Must (v1) | 🔒 |
| 10.9.1 | İçerik düzenlemenin yokluğu (R12) | Must (v1) | 🔒 |
| 10.9.2 | Görüntüleme ve indirme logu | Should (v1) | 🔒 |

### 4.2 FR-MOD-11 — Belge türü kataloğu ve öğrenme (Faz 1 kalemleri)

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 11.1.1 | Katalog yönetim ekranı | Must (v1) | 🔒 |
| 11.1.2 | Katalog form doğrulaması | Must (v1) | 🔒 |
| 11.1.3 | Kabul kriteri düzenleme | Should (v1) | 🔒 |
| 11.2.1 | Örnek belge yükleme | Should (v1) | 🔒 |
| 11.3.1 | Tür açıklaması üretimi | Should (v1) | 🔒 |
| 11.4.1 | Prompt derleyici | Must (v1) | 🔒 |
| 11.4.2 | Token bütçesi | Should (v1) | 🔒 |
| 11.5.1 | Aday tür listesi | Must (v1) | 🔒 |
| 11.5.2 | Aday türü onaylama | Must (v1) | 🔒 |
| 11.5.3 | Onay sonrası yeniden analiz | Should (v1) | 🔒 |
| 11.5.4 | Aday türü reddetme | Should (v1) | 🔒 |

## 5. FAZ 2 — v2 (PRD §5.3)

### 5.1 FR-MOD-11 — Belge türü kataloğu ve öğrenme (Faz 2 kalemleri)

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 11.6.1 | Profil fotoğrafı kural seti | Should (v2) | 🔒 |
| 11.7.1 | Fotoğraf görsel kontrolü | Should (v2) | 🔒 |
| 11.7.2 | Fotoğrafta içerik korunması | Should (v2) | 🔒 |
| 11.8.1 | Fotoğraf örneklerinden öğrenme | Could (v3) | 🔒 |

### 5.2 FR-MOD-12 — Telegram botu

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 12.1.1 | Bot iskeleti | Should (v2) | 🔒 |
| 12.1.2 | Kullanıcı beyaz listesi | Should (v2) | 🔒 |
| 12.2.1 | Belge alma | Should (v2) | 🔒 |
| 12.2.2 | Çoklu mesaj grubu | Should (v2) | 🔒 |
| 12.2.3 | Sonuç özeti | Should (v2) | 🔒 |
| 12.3.1 | Belge isteme | Should (v2) | 🔒 |
| 12.3.2 | Belirsizlikte seçim | Should (v2) | 🔒 |
| 12.3.3 | Erişim kaydı | Should (v2) | 🔒 |
| 12.4.1 | Kuyruk ve hata bildirimi | Could (v3) | 🔒 |

## 6. FAZ 3 — Enterprise (PRD §5.4)

### 6.1 FR-MOD-13 — İşletme, maliyet ve dayanıklılık

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 13.1.1 | Maliyet ölçümü | Could (v3) | 🔒 |
| 13.2.1 | Ucuz model ön eleme | Could (v3) | 🔒 |
| 13.2.2 | Metin katmanı önceliği | Could (v3) | 🔒 |
| 13.3.1 | Kalıcı işçi kuyruğu | Could (v3) | 🔒 |
| 13.4.1 | Erişim logu görünümü | Could (v3) | 🔒 |
| 13.4.2 | Yedekleme ve geri yükleme | Could (v3) | 🔒 |
| 13.5.1 | Üretim dağıtımı | Could (v3) | 🔒 |
| 13.6.1 | İzleme ve uyarı | Could (v3) | 🔒 |

## C. Varsayımlar

Onay beklemeden yapılan varsayımlar buraya numaralı olarak yazılır.

- **C1** — Geliştirme ortamında PostgreSQL yerine SQLite kullanılır; şema farkları
  Alembic göçleriyle iki motorda da doğrulanır (NFR-05).
- **C2** — Uzak git deposu tanımlı değildir; kapanışta push adımı atlanır (CONVENTIONS §2).
- **C3** — Veri modeli (tm 3): `uploads.id` metin kimliktir (Plan JSON `upload_id` ve
  `Inbox/<upload_id>/` gereği; üretimi 01.1'in işi), diğer tablolar tamsayı kimlik taşır.
  §8.1'de alan listesi olmayan ama §8'in başka yerinde tanımlı iki alan eklendi:
  `employees.other_names` (§8.4, 03.1.3) ve `known_document_types.acceptance_criteria`
  (§8.6, 00.6.1). DB düzeyinde CHECK kısıtı yalnız değer kümesi PRD'de harfiyen yazılı
  alanlarda var: `uploads.status` (09.2.1), `employee_contacts.kind` (§8.1),
  `queue_items.kind` (§8.5 route). Diğer durum alanları serbest metin + varsayılandır.
- **C4** — SQLite motoru (`app/db/session.py`) her işlemi `BEGIN IMMEDIATE` ile açar; E
  numarası üreticisinin eşzamanlılık garantisi buna, PostgreSQL'de ise işlem ömürlü
  advisory kilide dayanır. Yan etkisi: SQLite'ta açık kalan oturum diğer yazarları bekletir.
- **C5** — `queue_items` §8.1'deki alanlarla (upload_id + plan_item_id) plana bağlanır;
  K18 plan sürümleri arasında öğe kimliği ayrımı gerekirse 06.6.2 göçle `plan_id` ekler.
- **C6** — Depolama (tm 4): slug Türkçe harfleri §20.2.1 eşlemesiyle, Rusça Kiril'i ICAO
  9303 eşlemesiyle, Arapçayı sade ünsüz eşlemesiyle (ICAO'nun `X`'li biçimi değil) Latin'e
  indirir; tablo dışı yazıdan (ör. Çince) karakter kalmazsa `SlugError` verir. Kişi adı
  kelimeleri büyük harfle başlar (`VASILEV → Vasilev`), isimdeki tire `_` olur, isim ve etiket
  parçaları 64 karakterle sınırlıdır. Sıra eki: aynı gövdeli dosya uzantısı farklı da olsa
  (`.jpeg`/`.png`) aynı türden sayılır, karşılaştırma harf büyüklüğüne duyarsızdır, arada boş
  kalmış ilk ek kullanılır. Yeni dosya sabit bağla (`os.link`) yayınlanır — hard link
  desteklemeyen dosya sisteminde yazma açık hatayla durur. Öldürülmüş yazmanın gizli geçici
  dosyası açılışta, 1 saatten eskiyse silinir. Kapsayıcı `/srv/data` adlı volume kullanır.
- **C7** — Katalog (tm 6): `allowed_conversions` §20.3 satır 3–6'daki işlem adlarını taşır
  (`merge`, `wrap_image`, `extract_image`, `render_image`; bkz. D5). 00.6.1'deki Direkt Belge
  kuralına ek tutarlılık kuralları: `analyze: false` ⇒ `required_fields` boş, slug tekil,
  listelerde tekrar yok, `expected_pages` ya iki sınırıyla ya `null` (sınır yok); bilinmeyen
  anahtar ve YAML'da tekrarlanan anahtar reddedilir. `front_back` ⇒ 2 sayfa kuralı 11.1.2'ye
  bırakıldı (tohum ona uyar). Veri dizini git dışı olduğu için tohum paket içindedir
  (`app/catalog/seed_catalog.yaml`); açılışta `data/KnownDocuments/catalog.yaml` yoksa oraya
  yazılır, varsa korunur. Veritabanına yükleme açılışta değil `python -m app.catalog import`
  ile yapılır (kapsayıcı göç koşmadan açılıyor). İçe aktarma katalogda olmayan türe dokunmaz
  (silme/pasifleştirme yok); dışa aktarma slug sırasıyla kanonik YAML üretir. Tohum değerleri:
  pasaportlar §8.6 örneği gibi direkt, `[pdf, jpeg]`, çıktı `keep`, iki kabul kriteri; oturma
  izni ve ehliyet `front_back`, direkt kapalı, `[merge, wrap_image]`, çıktı pdf (S5); Work Permit
  ülke kodsuz, direkt kapalı; Profile Picture çıktı jpeg + `[extract_image, render_image]` (K12,
  S3); Attachment yalnız doc/docx/xls/xlsx, `analyze: false`, direkt. YAML için PyYAML
  bağımlılığı eklendi (§4'te YAML kütüphanesi kilitli değil).
- **C8** — Boyut/sayfa sınırı (tm 9, 01.3.1): PRD sayı vermez. Ortam değişkeniyle değiştirilebilir
  varsayılan olarak dosya başına 20 MiB (`MAX_UPLOAD_FILE_SIZE_BYTES`) ve PDF başına 30 sayfa
  (`MAX_UPLOAD_PDF_PAGES`) seçildi — kimlik belgesi taramaları için cömert, yanlışlıkla tüm bir
  cilt/klasörün yüklenmesini yine de yakalayan bir eşik. Sayfa sayısı yalnız içerik `detect_file_kind`
  ile PDF olarak tanınırsa `pypdf.PdfReader` ile sayılır; PDF imzalı ama yapısal olarak
  çözülemeyen içerikte sayfa denetimi atlanır (boyut denetimi yine de uygulanır). Kesin sayılar
  insan onayına açıktır.
- **C9** — Parti durumu sorgulama (tm 12, 01.6.1): PRD "ilerleme" alanının biçimini vermez.
  Sayfa üretimi (02.x) ve sonraki analiz/plan adımları henüz yok; bu yüzden "ilerleme"
  şimdilik `progress.total_files` / `progress.rendered_files` (en az bir `Page` satırı
  oluşmuş dosya sayısı) olarak dar tutuldu. `UploadFile.page_count` alanı bu görevde
  doldurulmuyor (hâlâ hep `null`) — dolduran kod ayrı bir görevin işi. `rendered_files`
  02.x sayfa üretimi devreye girdiğinde otomatik doğru sayar; daha zengin bir ilerleme
  modeli (analiz/plan/uygulama aşaması bazında) gerekirse ileriki bir görev bu alanı genişletir.
- **C10** — PDF sayfa görüntüsü (tm 13, 02.1.1): PRD DPI, uzun kenar ve görüntü biçimi vermez.
  Ortam değişkeniyle değiştirilebilir varsayılanlar: `PAGE_RENDER_DPI=200`,
  `PAGE_RENDER_MAX_LONG_EDGE_PX=1568` (Anthropic görüntü girdisinin sunucu tarafında
  küçültmeden kabul ettiği uzun kenar; daha büyüğü maliyet/gecikme ekler, okunaklılık katmaz),
  `PAGE_RENDER_JPEG_QUALITY=90`. Önbellek biçimi JPEG seçildi: sağlayıcı maliyeti piksel
  boyutuna bağlıdır, biçime değil; taranmış renkli sayfada PNG, istek başına görüntü bayt
  sınırına (Anthropic 5 MB) yaklaşabilir. Görüntü yalnız analiz kopyasıdır, çıktı belge
  değildir — kayıplı biçim K12'yi ilgilendirmez (07.6.1 `render_image` kendi ayarını kullanır).
  "Küçültme" render ölçeğine uygulanır: uzun kenar sınırı aşılacaksa sayfa doğrudan sınır
  boyutunda rasterleştirilir, büyük görüntü üretilip yeniden örneklenmez (aynı piksel boyutu,
  daha az bellek, Pillow'a gerek yok). Sayfa görüntüsü `cache/pages/<file_id>/0000.jpg`
  (0 tabanlı sıra) adını alır ve türev veri olduğu için yeniden render'da `replace_file` ile
  yeniden üretilir. `render_upload_file` `pages` satırlarını açar/günceller, `page_count`'u
  doldurur, sayfa başına `PAGE_RENDERED` olayı yazar; parti durum geçişi (`rendering`) ve
  tekrar dosyaları (`is_duplicate_of`) atlama kararı orkestrasyonun (09.2.x) işidir.
- **C11** — Gömülü tek görüntü tespiti (tm 17, 02.5.1): PRD "tek tam sayfa görüntü"nün ölçütünü
  vermez; işaret `extract_image`'ı (§20.5) seçtiği için ölçüt "çıkarılan orijinal baytlar
  sayfada görünenle aynı mı" olarak kuruldu ve belirsizlikte işaret VERİLMEZ — yanlış işaret
  görünen içeriği (damga, not, kırpma) sessizce düşürür, eksik işaret yalnız kayıplı ama sayfaya
  sadık `render_image`'a düşer. Sayfa MuPDF ile çalıştırılıp çizim komutları kaydedilir
  (`pymupdf.mupdf.FzDevice2`; yüksek düzey API sabit alfa, yumuşak maske ve dikdörtgen olmayan
  kırpmayı göstermiyor). İşaret için: `/Rotate` yok; açıklamalar dahil tam bir görüntü çizimi,
  başka görünür komut yok (görünmez OCR metni serbest — PDF→JPEG'de iki işlem de metin katmanını
  taşımaz); görüntü döndürülmemiş/aynalanmamış, tam opak, sayfa kutusuyla her kenarda
  `FULL_PAGE_TOLERANCE_PT = 1.0` pt içinde eşit (300 DPI taramada sayfa boyutu yuvarlaması);
  kırpmalar yalnız sayfayı kaplayan dikdörtgen; karışım modu normal, grup opak; sayfanın tek görüntü
  nesnesi (satır içi değil) ve `SMask`/`Mask`/`Decode`/`SMaskInData` anahtarı yok. Tolerans
  yapılandırma değeri değil modül sabitidir: işletme ayarı değil, geometri eşiğidir.
- **C12** — Sayfa analizi şeması (tm 18, 03.1.x): §8.4 örnekten öte kural vermez; "uymayan yanıt
  reddedilir" şöyle okundu — §8.4'ün her anahtarı zorunludur (eksik anahtar varsayılanla
  doldurulmaz), tanımsız anahtar ve tip zorlaması reddedilir, `person` ve `person.contact` her
  zaman nesnedir, okunmayan değer `null`dır (boş metin, boş `mrz_lines` listesi reddedilir).
  `language`/`script` sayfada dili belirlenecek metin yoksa `null` olabilir — değer zorunlu
  olsaydı fotoğraf/boş sayfada model uydurmak zorunda kalırdı (03.4.1 "tahmin etme"); anahtar yine
  zorunludur ve dolu değer kapalı kümededir. ISO 639-1 kümesi kayıttaki 183 kodun kendisidir
  (kaldırılmış `bh`/`iw`/`in`/`ji`/`mo`/`sh` yok), yalnız küçük harf. `fields` okumasında
  `legible: true` ⇔ `value` dolu: okunamayan alanın değeri taşınmaz. `document_type_slug`
  katalogdaki slug'lara karşı yalnız yanıt kabulünde (`validate_page_analysis`) denetlenir;
  saklanan `analysis_json` katalogsuz okunur (tür sonradan kaldırılmış olabilir). PRD'nin
  sessiz kaldığı biçimler DB sütunlarına sığacak ve standarda uyacak kadar dar tutuldu: tarih
  yalnız `YYYY-AA-GG` ve takvimde geçerli, `nationality` ICAO 9303 kodu (1–3 büyük harf; `D`
  Almanya), isimler 255, belge numarası 128 karakter (§8.1 sütunları). MRZ satırlarının biçimi ve
  karakter kümesi şemada denetlenmez — §20.1.1 "uymuyorsa MRZ yok sayılır, hata değil" 05.3'ün
  işidir. İletişim alanları olduğu gibi taşınır (e-posta/telefon biçimi denetlenmez).
  Reddetme mesajları alan konumu ve kuralı söyler, gelen değeri tekrarlamaz (CONVENTIONS §6).
- **C13** — Sağlayıcı soyutlaması ve Anthropic (tm 19, 03.2.x): PRD arayüzü tanımlamaz. Boru hattı
  yalnız `create_provider(settings).analyze_page(PageAnalysisRequest)` çağırır; istek sağlayıcıdan
  bağımsızdır (0 tabanlı `page_index`, JPEG/PNG `PageImage` — ortam türü baytlardan çıkarılır,
  çağırandan alınmaz —, sistem talimatı `instructions`, sayfaya özgü `prompt`, katalog
  `known_slugs`). Talimat ve metnin içeriği 03.4/03.7'nindir; sağlayıcı yalnız API biçimine
  yerleştirir. Yanıt kabulü ortak ve atlanamaz (`@final analyze_page`): `validate_page_analysis`
  + yanıtın `page_index`'i istenen sayfaya eşit olmalı (başka sayfanın yanıtı 04.1 gruplamasını
  bozar; bu yüzden 03.4/03.7 prompta sayfa sırasını yazmalı). Sağlayıcı `AI_PROVIDER` adıyla
  seçilir (küçük harf tanımlayıcı, varsayılan `anthropic`), ad kayıt defteri
  `PROVIDER_FACTORIES`'tir — 03.3 `openai`'yi buraya ekler; sağlayıcıya özgü ayarlar kendi
  önekini taşır (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) ki geçiş tek değişkenle olsun. Anahtar
  yalnız o sağlayıcı kurulurken zorunludur (`ProviderConfigError`), `Settings` onsuz yüklenir.
  Varsayılanlar: `ANTHROPIC_MODEL=claude-opus-5` (en yetenekli güncel model; ucuz model ön elemesi
  13.2.1'in işi), `AI_MAX_OUTPUT_TOKENS=4096`, `AI_REQUEST_TIMEOUT_SECONDS=120`. Hata aileleri
  ayrı: çağrı tamamlanmadıysa `ProviderError` (`ProviderRateLimitError` 429, `ProviderServerError`
  5xx/529, `ProviderConnectionError` bağlantı/zaman aşımı, diğer 4xx taban tür) — 03.5 bunlardan
  hangisini yeniden deneyeceğini seçer; yanıt geldi ama uymuyorsa `PageAnalysisError`. SDK'nın
  kendi yeniden denemesi kapalı (`max_retries=0`), iki katman üst üste denemesin. Anthropic
  yapılandırılmış çıktısı API'nin katı `output_config.format` şemasıyla DEĞİL, zorlanmış tek araç
  çağrısıyla alınır (`record_page_analysis`, `input_schema=PageAnalysis.model_json_schema()`,
  `tool_choice` sabit, paralel çağrı kapalı): katı şema her nesnede `additionalProperties: false`
  ister, §8.4 `fields` ise `patternProperties` ile tanımlı alan adı sözlüğüdür ve katı şemada boş
  nesneye iner. Araç şeması katı olmadığından uyum `validate_page_analysis`'e dayanır. Zorlanmış araç
  seçimi genişletilmiş düşünmeyle kullanılamadığı için `thinking` açıkça kapalıdır. Kabul edilen
  tek yanıt: `stop_reason == "tool_use"` ve tam bir `record_page_analysis` çağrısı; `max_tokens`
  (kesik), `refusal`, araçsız veya çok çağrılı yanıt `PageAnalysisError` olur. Hata mesajı HTTP
  durumunu ve API hata türü/açıklamasını taşır, istek içeriğini taşımaz. Anthropic SDK
  (`anthropic>=1.5`, taşıma `httpx2`) yalnız bu sağlayıcı seçilince içe aktarılır.
- **C14** — Analiz promptu (tm 21, 03.4.1): PRD yalnız üç kuralın varlığını ister. Talimat
  `app/ai/prompts/page_analysis.md`'dir (Türkçe; kural başlıkları kabul kriterinin ifadeleridir,
  JSON anahtarları §8.4'teki gibi), sağlayıcıdan bağımsızdır (araç adı geçmez) ve paket verisi
  olarak yüklenir. Katalog talimata girer, çünkü "katalogda yoksa aday öner" ve zorunlu alan
  okuması kataloğu görmeden yapılamaz: şablondaki tek `{{catalog}}` yuvasına yalnız etkin ve
  `analyze: true` türler slug sırasıyla (deterministik) yazılır — `attachment` analize gitmediği
  için slug olarak sunulmaz (K2), pasif tür atanmaz. Tür başına ülke, yüz yapısı, beklenen sayfa,
  zorunlu alanlar, `prompt_description` (yoksa `description`) ve §8.6 gereği kabul kriterleri
  yazılır; `direct`/dönüşüm/çıktı biçimi karar motorunundur, yazılmaz. `build_page_analysis_instructions`
  metinle birlikte o metnin slug'larını (`known_slugs`) döner; 03.7 ikisini isteğe birlikte vermeli.
  Sade liste Faz 0 içindir; kompakt derleme ve token bütçesi 11.4'ün işidir, yuva sözleşmesi
  aynı kalır. Promptun kurduğu, sonraki görevleri bağlayan anlamlar: `fields` sayfa başınadır —
  türün her zorunlu alanı yazılır, bu sayfada okunmayan (okunaksız **veya** bu yüzde bulunmayan)
  alan `legible: false`'tur, dolayısıyla 04.4 okunaklılığı adayın sayfaları üzerinden
  birleştirmelidir; `document_type_slug` `null` ise `fields` `{}`'dir. Görünen alanlar ve MRZ
  birbirinden doldurulmaz/düzeltilmez (MRZ önceliği 05.3.3'ündür). `continues_previous_page`
  emin değilse `false` (yanlış `true` farklı belgeleri birleştirir, yanlış `false` yalnız
  Unresolved'a düşürür). `candidate_type_name` katalog adları gibi İngilizce "<Ülke sıfatı>
  <Belge türü>" (11.5.1 görülme sayısında aynı ad toplansın). `language`/`script` iki dilli
  belgede belgenin kendi dili ve Latin olmayan alfabesidir (§8.4 örneğiyle aynı). Sayfa metni
  talimat sayılmaz; metin katmanı görüntüyle çelişirse görüntü yazılır, çelişki `notes`'a.
  `notes` kişisel değer tekrarlamaz.
- **C15** — Yeniden deneme ve dayanıklılık (tm 22, 03.5.1): PRD yalnız "hız sınırı ve 5xx'te
  geri çekilmeli üç deneme" der; hangi hata ailelerinin yeniden deneneceği C13'te 03.5'e
  bırakılmıştı. Yeniden deneme yalnız `ProviderRateLimitError` (429) ve `ProviderServerError`
  (5xx/529) içindir; `ProviderConnectionError` (bağlantı/zaman aşımı) ve diğer `ProviderError`
  alt türleri (kalıcı 4xx) ilk denemede yükselir — tekrar aynı sonucu verme ihtimalleri yeniden
  deneme maliyetini haklı çıkarmaz, ayrıca kabul kriteri de yalnız hız sınırı/5xx'i sayar.
  `PageAnalysisError` (şemaya uymayan yanıt) hiçbir zaman yeniden denenmez. Toplam deneme sayısı
  `MAX_ANALYSIS_ATTEMPTS = 3` (ilk deneme + iki yeniden deneme), geri çekilme üstel:
  `RETRY_BACKOFF_SECONDS * 2 ** (deneme - 1)` — ikinci denemeden önce 1 sn, üçüncüden önce 2 sn.
  Süre yapılandırılabilir değildir (PRD sayı vermiyor, sabit tutuldu) ve `Retry-After` başlığı
  okunmaz (kabul kriteri istemiyor, kapsam dışı). Yeniden deneme `AnalysisProvider.analyze_page`
  (`@final`) içindeki yeni `_request_analysis_with_retry` sarmalayıcısında yapılır — somut
  sağlayıcılar (`_request_analysis`) değişmez, tek HTTP isteği atmaya devam eder. Bekleme
  `time.sleep` iledir; testte `app.ai.provider.time.sleep` monkeypatch'lenir (`tests/ai/conftest.py`
  `no_sleep`), gerçek bekleme olmaz.
- **C16** — Kayıtlı yanıt sağlayıcısı (tm 23, 03.6.1): PRD yalnız "testler ağ erişimi olmadan
  çalışır ve deterministik sonuç verir" der, arayüz vermez. `tests/ai/test_provider.py`'deki
  `CannedProvider`/`QueuedProvider` yanıtı Python değişmezi olarak taşıyıp yalnız provider.py'nin
  kendi testleri içindir; 03.6 bunun yerine `app/ai/recording_provider.py`'de paylaşılan bir
  `RecordingProvider` kurar — kayıt diskteki `tests/fixtures/ai/recordings/<senaryo>/<sıra>.json`
  dosyasıdır (`0.json`, `1.json`, ...), sıradaki her `analyze_page` çağrısına dosya adına göre
  sıralı karşılık gelir (03.7'nin sayfaları sırayla analiz etmesiyle simetrik). İçerik
  ayrıştırılmadan `AnalysisProvider.analyze_page`'e döner — doğrulama tek yerde
  (`validate_page_analysis`) kalır, kayıtlı sağlayıcı kendi kabulünü yazmaz; bozuk/eksik kayıt
  orada `PageAnalysisError` olur (somut sağlayıcılarla aynı sorumluluk ayrımı). Kayıt sayısından
  fazla istek `RecordingExhaustedError`, boş/yok dizin `RecordingNotFoundError` — sessiz tekrar
  veya boş sağlayıcı yok, eksik test hazırlığı DoD'da fark edilsin diye. `PROVIDER_FACTORIES`'e
  eklenmedi: o kayıt defteri `.env`'den seçilen gerçek sağlayıcılar içindir (03.3 `openai`);
  bu sağlayıcı bir dizin yolu ister, testin kendisi `RecordingProvider.from_directory(...)`'yi
  doğrudan çağırır, gerekiyorsa `monkeypatch.setitem(PROVIDER_FACTORIES, ...)` ile enjekte eder.
  İki örnek kayıt eklendi: `russian_passport/0.json` (tek sayfa) ve
  `serbian_residence_card/{0,1}.json` (ön/arka, `continues_previous_page` ikinci sayfada `true`) —
  ikisi de sentetik, gerçek kişi/belge yok (CONVENTIONS §6).
- **C17** — Sayfa analizi çalıştırıcı (tm 24, 03.7.x): PRD yalnız "sırayla, önceki sayfa özetiyle"
  ve "başarısız sayfada parti `partial`" der; özetin içeriği, analize hangi sayfaların gideceği ve
  `partial`'ın yazılma anı yazılı değil. Giriş `analyze_upload(session, layout, upload, provider=,
  instructions=)`; talimat çağırandan gelir (09.2 `build_page_analysis_instructions(export_catalog(
  session))` kurar). Sıra: dosyalar `upload_files.id`, sayfalar `pages.index`, aynı anda tek istek.
  **Gönderilmeyen sayfa:** tekrar dosyasının sayfaları (01.4.1 — K01.4 bu atlamayı analiz adımına
  bırakmıştı) ve boş sayfa (02.4.1); ikisi de `analysis_status = skipped`, `analysis_json` boş, yeni
  olay yok (tespitleri zaten loglu). `analysis_status` kümesi `pending`·`done`·`failed`·`skipped`
  (`PageAnalysisStatus`; DB CHECK yok, C3). **Özet** önceki sayfanın doğrulanmış analizinden
  deterministik üretilir, yapay zekâya yazdırılmaz ve kişisel değer taşımaz — önceki sayfa başka
  çalışana ait olabilir, sağlayıcıya yalnız işlenen sayfanın verisi gider (CONVENTIONS §6): tür
  (slug / aday adı / belirlenemedi), `side`, `continues_previous_page`, boş/okunabilir, dil/alfabe,
  ad·belge numarası·MRZ yazılı mı (evet/hayır), okunaklı ve okunaksız zorunlu alan adları; `notes`
  girmez. Özet dosya sınırında sıfırlanır (dosyalar arası eşleştirme 04.3'ün). Boş sayfa zinciri
  kırmaz, atlanan boş sayfaların sırası metinde yazılır; bu yüzden `continues_previous_page`
  "analize gönderilen bir önceki sayfanın devamı" anlamındadır — 04.1 bunu boş sayfaları atlayarak
  okumalı (dupleks taramada kartın iki yüzü arasına boş sayfa girer; boş sayfanın K5'teki "başka
  belgeye ait sayfa" sayılıp sayılmayacağı 04.1'in kararıdır). Önceki sayfanın analizi başarısızsa
  özet verilmez, bu metinde söylenir, daha eski sayfanın özeti yerine konmaz. **Başarısızlık** yalnız
  `ProviderError` (03.5 yeniden denemesinden sonra), `PageAnalysisError` ve `PageImageError`
  (görüntü üretilmemiş, dosya yok, JPEG/PNG değil, geçersiz yol): sayfa `failed`, eski
  `analysis_json` boşaltılır, `PAGE_ANALYSIS_FAILED` (mesaj hata metnidir — C12/C13 gereği değer
  taşımaz; veri `provider`, `model`, `error` türü, varsa `status_code`). Başka istisna yakalanmaz;
  partinin `failed` olması 09.2.3'ündür. Kalıcı sağlayıcı hatası (ör. 401) da sayfa hatasıdır: her
  sayfa bir istek atar; toplu erken durdurma 09.2.3'e bırakıldı. **`partial`:** en az bir sayfa
  başarısızsa — hepsi başarısız olsa da (kabul kriterinin harfi) — `uploads.status = partial`
  analizin sonunda yazılır; hepsi başarılıysa durum değişmez. `partial` 09.2.1'de son durum
  olduğundan 09.2 bu değeri (veya `UploadAnalysisResult.is_partial`) koruyarak başarılı sayfalarla
  planlamaya devam etmeli ve partiyi sonunda `done` yerine `partial` bırakmalı. **Başarılı sayfa:**
  `analysis_json = PageAnalysis.model_dump(mode="json")`, `done`, `PAGE_ANALYZED` (veri `provider`,
  `model`, `document_type_slug`, `side`, `is_readable` — kişisel değer yok); `is_readable: false`
  ise ayrıca `PAGE_UNREADABLE` (sayfa düzeyi olgu; Unreadable kuyruk kararı 04.4'ün). Token
  kullanımı yazılmaz — sağlayıcı arayüzü döndürmüyor (13.1). Yeniden çalıştırmada uygun her sayfa
  yeniden analiz edilir (`done` atlanmaz, K18). Oturum commit edilmez (render adımlarıyla simetrik);
  SQLite `BEGIN IMMEDIATE` (C4) altında analiz boyunca açık işlem diğer yazarları bekletir — işlem
  sınırını (ör. sayfa başına commit) 09.2 belirlemeli.
- **C18** — Dosya içi gruplama (tm 25, 04.1.x): PRD "ardışık, aynı tür, aynı kişi" ve "ön/arka sıralı
  eşleşir" der; ardışıklığın, kişi aynılığının ve yüz yapısının ölçütü yazılı değil. Giriş
  `group_upload(session, upload, catalog=)` (tekrar dosyası atlanır; katalog `export_catalog`), saf
  çekirdek `group_file_pages(file_id, pages, catalog=)`; çıktı `UploadGrouping.files` →
  `FileGrouping` (`candidates`, `blank_pages`, `unanalyzed_pages`) → `DocumentCandidate.pages`
  (`CandidatePage`: `file_id`, `index`, `analysis` — dosya kimliği sayfadadır ki 04.3 dosyalar arası
  adayı aynı tiple kursun). Sayfa açık adaya ancak beş koşul birden sağlanırsa katılır.
  **(1) Ardışık:** adayın son sayfası bu sayfadan hemen önce analize gönderilen sayfadır. 02.4 boş
  sayfası analize gitmez ve başka belgeye ait sayfa sayılmaz (C17'nin bıraktığı K5 sorusu): zinciri
  kırmaz, adaya girmez — aday sayfa listesi bu yüzden boş sayfayı atlayabilir (`[0, 2]`), 06.2/06.3
  bunu ardışık alt küme okumalı, boş sayfa çıktıya girmez (S8). Analizi başarısız/yapılmamış sayfa
  (içeriği bilinmez, başka belge olabilir) ve analizcinin boş dediği, hiçbir değer okumadığı sayfa
  (sonraki sayfanın devam işareti ona göre verilmiştir) zinciri kırar, aday olmaz; tür, kişi değeri
  veya okunaklı alan taşıyan çelişkili "boş" yanıt normal sayfadır. **(2) Devam:**
  `continues_previous_page: true` — kabul kriterinin "ardışık"ı bu işaretle okunur; `false` aynı
  kişinin art arda taranmış iki aynı tür belgesini ayırır (C14). **(3) Aynı tür:** aynı slug; slug'sız
  sayfada harf büyüklüğü/boşluk farkı yok sayılan aynı aday tür adı; türü belirlenemeyen sayfa hiç
  gruplanmaz. **(4) Yüz yapısı:** katalogda `front_back` türde yalnız `[front]` adayına `back`
  katılır — arkadan sonra gelen ön, tamamlanmış çifte üçüncü sayfa, `single`/`unknown` yüz eşleşmez
  (`F F B` → `[F] [F B]`); tek yüzlü ve katalog dışı türde yüz sınır değildir; katalogda bulunmayan
  slug gruplanmaz. `expected_pages` gruplamada uygulanmaz: sınırda bölmek geçerli görünen iki belge
  üretirdi, aralık dışı aday 04.5'te Unresolved olur. **(5) Aynı kişi:** iki sayfada da dolu olan
  belge numarası (§20.2.1 normalizasyonu), doğum tarihi, soyad, ad ve orijinal yazım çelişmez. İsim
  harf büyüklüğü, aksan (NFKD), Türkçe `ı`, noktalama ve kelime sırasından arındırılmış kelime
  kümesidir; biri ötekini kapsıyorsa çelişki yoktur (ikinci adı yazılmamış sayfa). Değeri olmayan
  sayfa (kart arka yüzü) çelişmez; sayfa adayın her sayfasıyla karşılaştırılır. Alfabeler arası
  çeviri 05.1/05.2'nindir; MRZ, uyruk ve kişi dışı alanlar (`expiry_date`) karşılaştırılmaz — aynı
  kişinin iki kartının yüzlerini ayırmak devam işaretine ve yüz sırasına kalır. Eksik aday (yalnız ön
  ya da arka, aralık dışı) aday olarak döner; rotası 04.2 (araya belge), 04.3 (başka dosyadaki eş),
  04.5 (sayfa sayısı) kararıdır. **Olay:** aday başına katalog türünde `DOC_TYPE_DETERMINED`, değilse
  `DOC_TYPE_UNKNOWN` (`page_index` ilk sayfa; veri `document_type_slug`/`candidate_type_name`,
  `pages`, `sides` — kişisel değer yok); 04.6 aday tür kaydını ve `CANDIDATE_TYPE_PROPOSED`'ı ekler,
  `DOC_TYPE_UNKNOWN`'u ikinci kez yazmamalı. Saklanan analiz katalogsuz okunur (C12); şemaya uymayan
  `analysis_json` değer taşımayan `StoredAnalysisError` ile durur. Oturum commit edilmez.
- **C19** — Ardışıklık güvenlik kuralı (tm 26, 04.2.1): PRD "araya başka belge girmiş parçalar otomatik
  birleştirilmez, gerekçesiyle Unresolved'a gider" der; hangi adayların aynı belgenin parçası
  sayılacağı, "başka belge"nin ne olduğu ve Unresolved'a gitmenin karar motorunda neye karşılık
  geldiği yazılı değil. 04.1 parçaları zaten birleştirmez (C18); 04.2 onları **işaretler**:
  `group_file_pages` sonunda aynı dosyadaki aynı slug'lı her aday çifti denenir, parça sayılan adaya
  `DocumentCandidate.contiguity_violation` (`ContiguityViolation`: `pages`, `counterparts`,
  `intervening_pages`, `unanalyzed_pages`; `rule = "R6"`, `queue = QueueKind.UNRESOLVED`, `reason`)
  konur. Adaylar, sıraları ve aradaki belgeler değişmez (S3: foto ve oturum izni aday kalır, sayfa 3
  kendi türüyle). **Parça çifti** dört koşulun hepsidir. (1) Aynı slug ve slug katalogda: katalog
  dışı (aday tür adı) ve türü belirlenemeyen adayın yüz/sayfa yapısı bilinmez, hüküm verilmez —
  Unknown rotası 04.6'nın, tür onayı ve yeniden analizden (K18) sonra kural katalog yapısıyla
  işler. (2) Tek belgede birleşebilir: `front_back` türde biri yalnız `(front,)`, öteki yalnız
  `(back,)` — sıra fark etmez (arka yüzü önce taranmış kart da aynı karttır); tamamlanmış çift ve
  `single`/`unknown` yüzlü aday parça değildir. Tek yüzlü türde toplam sayfa ≤ `expected_pages.max`
  (aralık yoksa sınır yok) — iki parçanın her biri tek başına aralıkta olsa da (1+1 sayfalık
  çalışma izni) iki belge mi araya belge girmiş tek belge mi bilinemez, kuyruğa gider (R7);
  1 sayfalık türde (pasaport, foto) iki aday parça olamaz. (3) Kimlik değerleri iki parçanın hiçbir
  sayfa çiftinde çelişmez (C18 5. koşulu). (4) Araya belge girmiş: iki parça arasında başka bir aday
  (türü ne olursa olsun, aynı türden başka aday dahil) ya da analizi başarısız/yapılmamış sayfa
  (içeriği bilinmez, K5 — C18 ile tutarlı) vardır; 02.4 boş sayfası ve analizcinin boş dediği sayfa
  belge değildir, sayılmaz ve listelenmez. Bitişik ya da yalnız boş sayfayla ayrılmış eksik parçalar
  (`F B` devam etmeyen, `B F`) bu kuralın konusu değildir; rotaları sayfa sayısı (04.5) / yüz
  doğrulayıcısıdır (06.5). Kural dosya içidir: başka dosyadaki eş 04.3'ündür. Aday birden çok
  parçayla çift olabilir (`F x B y B`: ön yüz iki arka yüzle, iki arka yüz birbirinin parçası
  değil); `counterparts` hepsini, `intervening_pages` aradaki adayların sayfalarını (öteki parçalar
  hariç), `unanalyzed_pages` aradaki analizsiz sayfaları taşır. **Gerekçe** (`reason`): kural,
  parçanın ve öteki parçaların sayfaları, araya girenler; metinde sayfa numarası 1'den başlar
  (kullanıcının PDF görüntüleyicide gördüğü ve S3'ün "ehliyet 1 ve 6"sı), yapılandırılmış alanlar
  `pages.index`'tir (0'dan). Tür ve kişi tahmini metne girmez (plan öğesi taşır, 08.1.2 birleştirir);
  kişisel değer yok. **Unresolved'a gitmek** bu aşamada karar motorunun hükmüdür: kuyruk kaydı,
  klasör kopyası ve `QUEUED_UNRESOLVED` planlamadan sonra 08.1'in işidir (K9). 06.1 dolu
  `contiguity_violation`'lı adaya `route: unresolved`, `route_reason: reason` yazmalı; başka bir
  kontrol bu adayı Hazir'a çeviremez. 04.3 işaretli parçayı dosyalar arası eşleştirmeye sokmamalı —
  eşi aynı dosyada, araya belge girmiş hâlde durmaktadır. **Olay:** §8.3'te ardışıklık hükmüne
  ayrı tür yok (D6 ile aynı soru); hüküm adayın kendi `DOC_TYPE_DETERMINED` olayına
  `contiguity_violation` verisi (`rule`, `queue`, `counterparts`, `intervening_pages`,
  `unanalyzed_pages` — değer yok) ve `message = reason` olarak yazılır, yeni olay türü eklenmedi.
- **C20** — Dosyalar arası gruplama (tm 27, 04.3.1, 04.3.2): PRD "yalnız `direct: false` türlerde aynı
  partideki ayrı dosyalardaki ön ve arka yüz eşleştirilir" ve "aynı türden birden fazla ön yüz varsa
  eşleştirme yapılmaz, hepsi Unresolved'a gider" der; hangi yüzün eş beklediği, çokluğun neyi
  saydığı, birden fazla arka yüz, analizi olmayan ya da türü kesin olmayan sayfaların etkisi ve K4'teki
  "ardışıklık kuralı yine geçerlidir"in dosyalar arasında ne demek olduğu yazılı değil. Saf çekirdek
  `group_across_files(groupings, catalog=)` (dosyalar `file_id` sırasına dizilir, tekrar eden dosya
  `ValueError`); `group_upload` bütün dosyaları gruplayıp onu çağırır, olayları sonra yazar (şemaya
  uymayan saklı analiz hiç olay yazılmadan durur). Eşleşen yüzler dosyalarının
  `FileGrouping.candidates`'inden çıkar, `UploadGrouping.cross_file_candidates`'e tek
  `DocumentCandidate` olarak girer (sayfalar önce ön, sonra arka yüz; `file_ids` iki dosya);
  `UploadGrouping.candidates` dosya adaylarını dosya sırasıyla, ardından dosyalar arası adayları ön
  yüzün yerine göre verir. **Eş bekleyen yüz:** katalogda
  `sides: front_back` ve `direct: false` türün yalnız `(front,)` ya da `(back,)` yüzlü adayı;
  tamamlanmış çift eş beklemez ve sayılmaz. Direkt Belge'ye başka dosyadan sayfa eklenmez (K3):
  yüzleri eksik aday kalır, hüküm yok (04.5/06.3). Tek yüzlü, katalog dışı ve türü belirlenemeyen
  adaylar dosyalar arasında eşleşmez. **Ardışıklık dosya içidir:** yükleme sırası belge yapısı değildir
  (S5'te `arka.jpg` önce yüklenebilir), dosyalar arasına ardışıklık uygulanmaz; K4'ün "yine geçerli"si
  R6 işaretli parçanın (C19) dosyalar arası eşleşmemesidir — parça eşleşmez ama türün eksik yüzü
  olarak sayılır (asıl eşi başka dosyadaki yüz de olabilir). **Eşleşme** yalnız şu hâlde yapılır:
  türün partide tam bir eksik ön ve bir eksik arka yüzü var, ikisi de R6 işaretsiz ve ayrı dosyalarda,
  C18 5. koşuldaki kimlik değerleri çelişmiyor ve partide başka yüz olabilecek sayfa yok. **Başka yüz
  olabilecek sayfa:** (a) türün yüzü `single`/`unknown` okunmuş sayfası; (b) partide analizi
  başarısız/yapılmamış sayfa — içeriği bilinmez (C18/C19 ile aynı tutum; parti zaten `partial`);
  (c) katalog türü verilmemiş (slug `null` — türü belirlenemeyen ya da aday tür adlı — veya slug'ı
  katalogda olmayan) ve yüzü `single` okunmamış sayfa: 03.4 kural 3 analizciye emin olmadığı katalog
  türünü aday adla yazdırır, kartın emin olunmayan yüzü böyle görünür; tek yüzlü okunmuş katalog dışı
  belge (diploma) kart yüzü olamaz. Başka katalog türü (analizci emindir), başka `front_back` türün
  yüzleri ve boş sayfa (02.4 ya da analizcinin boş dediği) engel değildir; aday tür onaylanıp parti
  yeniden analiz edilince (K18) engel kalkar. **Belirsiz eşleştirme (04.3.2):** ayrı dosyalarda R6
  işaretsiz bir ön ve bir arka yüz varken (eşleşebilecek yüz çifti) türün birden fazla eksik ön **ya da
  arka** yüzü (arka yüzde kimlik yazmaz; hangi arka yüzün ön yüzle aynı karta ait olduğu da bilinemez,
  R7) veya (a)–(c) engeli varsa eşleştirme yapılmaz. Kimlik değerleri çoklukta dikkate alınmaz — PRD
  "birden fazla ön yüz varsa" der, istisna vermez. Türün R6 işaretsiz bütün eksik yüzleri (aynı
  dosyada bitişik eksik parçalar dahil) `DocumentCandidate.ambiguous_pairing` taşır
  (`AmbiguousPairing`: `face`, `fronts`, `backs`, `unoriented_pages`, `unanalyzed_pages`,
  `uncertain_type_pages` — `PageRef(file_id, index)` listeleri; `queue = unresolved`, `reason`); R6
  işaretli parça yalnız kendi hükmünü taşır, listelerde yer alır. Eşleşebilecek yüz çifti yoksa (yalnız
  ön yüzler, eksik yüzler aynı dosyada, karşı yüz yalnız R6 parçası) hüküm verilmez, eksik aday 04.5'in;
  tek ön ve tek arka yüzün kimliği çelişiyorsa aynı kart değildir, işaretsiz ayrı kalır. Türler
  birbirinden bağımsızdır; (b) ve (c) her türe uygulanır. **Gerekçe:** "Belirsiz ön/arka yüz
  eşleştirmesi: bu yüz (dosya X, sayfa N) partide tek anlamlı bir eşle eşleştirilemiyor.", boş olmayan
  listeler ve "Yüzler dosyalar arasında otomatik eşleştirilmez."; dosya `upload_files.id`, sayfa
  numarası 1'den. Özgün dosya adı (kişi adı taşıyabilir, CONVENTIONS §6), tür ve kişi değeri metne
  girmez. **Olay:** dosyalar arası aday `DOC_TYPE_DETERMINED`'ı ilk sayfanın (ön yüz) dosyası ve
  sırasıyla yazar, sayfaları `pages` yerine Plan JSON biçimindeki `sources` (`[{file_id, pages}]`) ile
  taşır; belirsizlik hükmü adayın kendi olayına `ambiguous_pairing` verisi (`queue` ve
  `{file_id, page_index}` listeleri) ve `message = reason` olarak yazılır — §8.3'te ayrı tür yok (C19).
  Kuyruk kaydı (08.1) ve S5'in fiziksel çıktısı (iki JPEG'in kayıpsız sarılıp birleştirilmesi: 06.2
  satır 3 `merge`, 07.3/07.4) sonraki görevlerindir.
- **C21** — Zorunlu alan okunaklılık kapısı ve kabul kriterleri (tm 28, 04.4.1, 04.4.2): PRD "zorunlu
  alanların biri bile okunaksızsa Unreadable, eksik alan adları gerekçeye" ve "her madde değerlendirilir,
  karşılanmayan madde Unresolved gerekçesine adıyla" der; okumaların sayfalar arasında nasıl
  birleşeceği, maddenin kim tarafından ve hangi alanla değerlendirildiği ve iki hükmün önceliği yazılı
  değil. Saf çekirdek `check_legibility(candidate, catalog=)` → `LegibilityCheck` (`document_type_slug`,
  `illegible_fields: IllegibleRequiredFields | None` — `rule = "R1"`, `queue = unreadable`, `fields`;
  `unmet_criteria: UnmetAcceptanceCriteria | None` — `queue = unresolved`, `criteria`; `accepted`,
  `queue`, `reason`). Katalog türünde olmayan aday (aday tür adlı, türü belirlenemeyen, slug'ı katalogda
  olmayan) `None` — zorunlu alanı bilinmez, 04.6'nın. Tür ve maddeler güncel katalogdan okunur.
  **Birleştirme:** alan adayın herhangi bir sayfasında `legible: true` ise okunaklıdır (C14: bu yüzde
  bulunmayan alan da `false` okunur); hiçbir sayfada okunaklı olmayan ya da anahtarı hiç yazılmamış
  zorunlu alan okunamayandır. Okunaklı okuma yalnız kendi yanıtı `is_readable: true` ve `is_blank:
  false` olan sayfadan sayılır — "bütün olarak okunamıyor/boş" diyen yanıttaki okunaklı alan çelişkidir
  (R7). `is_readable` tek başına rota vermez: zorunlu alanı olmayan türde (foto) kapı yok (K1, güven
  skoru yok). **Gerekçe:** tam olarak `Okunamayan alanlar: <alanlar>` (S9 metni), alanlar katalogdaki
  `required_fields` sırasıyla, virgülle; kural `rule` alanındadır. **Kabul kriterleri:** §8.4'te madde
  sonucu için alan yok ve §8.4 değiştirilmedi (değişiklik insan kararı olurdu); maddeler 03.4 gereği
  analizciye tür tanımıyla gider ve analizci karşılanmayanı zaten `notes`'a yazar. Değerlendirme bu
  kanaldır: analiz talimatının `notes` açıklamasına alt madde eklendi — bu sayfada açıkça karşılanmayan
  her madde katalogdaki metniyle, kelimesi kelimesine `Karşılanmayan kabul kriteri: <madde>` biçiminde
  yazılır; karşılanan ve konusu bu sayfada olmayabilecek madde yazılmaz. Madde, adayın **bir** sayfasının
  notunda kelime dizisi olarak geçiyorsa karşılanmamıştır; geçmiyorsa karşılanmıştır (analizciye yalnız
  açıkça karşılanmayanı yazması söylenir). Kelime dizisi: NFKD + birleşik işaretler atılır, casefold,
  `ı`→`i`, harf/rakam dışı her şey ayraç — harf büyüklüğü, aksan, noktalama, boşluk farkı yok sayılır;
  eksik/ek almış kelime, farklı sıra veya başka sözcükler eşleşmez. Notlar sayfa sayfa aranır (iki
  sayfanın notundan madde kurulmaz). Uzun madde önce aranır; uzun maddenin eşleştiği aralığın içinde
  kalan kısa madde ayrıca sayılmaz, yalnız örtüşen (birbirini kapsamayan) maddeler ikisi de sayılır.
  Aynı kelime dizisine inen maddeler birlikte hüküm alır; gerekçede tek satıra indirilmiş metin tekrar
  etmez; kelimesi olmayan madde (`***`) alıntılanamaz, hiç karşılanmamış sayılmaz. Liste boşsa yalnız
  R1. **Gerekçe:** `Karşılanmayan kabul kriterleri: "<madde>"; "<madde>"` (katalog sırası, tek satır).
  **Öncelik:** iki ölçüt her zaman değerlendirilir; ikisi de sağlanmıyorsa `queue`/`reason` Unreadable'ın
  (K1 tek kabul ölçütü, maddeler "onun ötesindeki" koşullar — §8.6), öteki hüküm nesnede kalır. Hüküm
  adayın bütün belge olduğu varsayımıyla verilir: yalnız arka yüzden oluşan eksik aday "okunamayan
  alanlar" alır — 06.1 yapısal hükümleri (R6 C19, 04.3.2 C20, 04.5 sayfa sayısı) bu kapıdan önce
  uygulamalı. 06.5 `required_fields` doğrulayıcısı bu sonucu kullanmalı ve rotayı Unresolved değil
  Unreadable yapmalı (K1, 06.5.2'nin genel "Unresolved"ı bu doğrulayıcıya uygulanmaz). **Olay:** modül
  saf işlevdir, olay yazmaz — §8.3'te okunaklılık hükmüne ayrı tür yok; `PAGE_UNREADABLE` sayfa
  olgusudur (03.7), hüküm plana (`validations`, `route_reason`, `PLAN_CREATED`) ve kuyruk kaydına
  (`QUEUED_UNREADABLE`/`QUEUED_UNRESOLVED`, 08.1) geçer. Sonuç `DocumentCandidate`'e alan olarak
  eklenmedi (group.py'ye dokunulmadı); 06.1 aday başına çağırır.
- **C22** — Bilinmeyen tür ve aday tür önerisi (tm 30, 04.6.1): PRD "katalogda olmayan belge zorla bir
  türe atanmaz; aday tür olarak kaydedilir ve Unknown'a gider" der; hangi adayın katalogda olmayan
  sayıldığı, önerecek adı olmayan adayın, aday tür kaydının tekillik ve sayım kuralının ve aynı partinin
  yeniden gruplanmasının ne yapacağı yazılı değil. **Kapsam:** güncel katalogda türü olmayan her dosya
  adayı `DocumentCandidate.unknown_type` (`UnknownDocumentType`: `pages`, `candidate_type_name`,
  `document_type_slug`, `candidate_type_id`; `queue = unknown`, `reason`) taşır — (a) analizcinin aday
  tür adı yazdığı (slug `null`), (b) türünü hiç belirleyemediği (ikisi de `null`, boş okunmamış), (c)
  analizde yazılan slug'ı güncel katalogda olmayan aday (saklanan analiz katalogsuz okunur, C12). İşaret
  `group_file_pages`'te verilir; dosyalar arası aday hep katalog türüdür. **Zorla atanmaz:** aday tür
  adı katalogdaki bir türün adına ya da slug'ına benzese de (`Russian Passport`) eşlenmez, slug boş
  kalır — türü seçmek analizcinin (03.4 kural 3) ve onaydan sonra yeniden analizin (K18, 11.5.3)
  işidir. Pasif ama katalogda duran tür katalog türü sayılır (gruplama değişmedi). **Tek hüküm:** R6
  (C19), 04.3.2 (C20) ve 04.5 katalog türünün yapısını ister; `unknown_type` onlarla birlikte bulunmaz.
  (b)'de sayfa `is_readable: false` olsa da kuyruk Unknown'dır: K1'in Unreadable'ı türü bilinen belgenin
  zorunlu alanıdır, neden `analysis_json.notes`'tadır. **Aday tür kaydı** yalnız (a)'da, `group_upload`
  içinde `record_candidate_type_sighting` (`app/db/models.py`) ile yazılır. Tekillik anahtarı
  `normalize_candidate_type_name` (casefold + boşluk sadeleştirme) — 04.1 gruplama anahtarıyla aynıdır,
  aynı adayın sayfaları tek kayda iner; noktalama/aksan farkı ayrı ad sayılır. `proposed_name` ilk
  görülen yazım (boşlukları sadeleşmiş), `first_seen_upload_id` ilk parti, `description` boş (tür
  açıklaması 11.3'ün; `notes` konmaz). **Görülme** belge adayı başınadır: adayın ilk sayfasının
  `pages.id`'si `sample_page_ids`'e eklenir ve `seen_count` artar; sayfa zaten listedeyse sayılmaz —
  aynı partinin yeniden gruplanması ya da yeniden analizi sayıyı şişirmez. Bu yüzden liste sınırsızdır
  (görülme başına bir tamsayı); 11.5.1 örnek olarak ilk birkaçını gösterir, 11.5.3 ilişkili sayfaları
  buradan bulabilir. Yeniden görülme adı, ilk partiyi ve **durumu** değiştirmez (`CandidateTypeStatus`:
  `pending`/`approved`/`rejected`, kararlar 11.5.2/11.5.4) — reddedilen aday listeye geri düşmez. Durum
  kümesine CHECK kısıtı eklenmedi, göç yok (`pages.analysis_status` deseni). Eşzamanlılık
  `allocate_employee_number` ile aynıdır (SQLite `BEGIN IMMEDIATE`, PostgreSQL advisory kilit).
  **Olay:** katalog türü olmayan her adayın olayı `DOC_TYPE_UNKNOWN`'dur ((c) artık `DETERMINED`
  değil) ve `unknown_type` verisi (`queue`, `candidate_type_id` — (b)/(c)'de `null`) ile `message =
  reason` taşır; ikinci `DOC_TYPE_UNKNOWN` yazılmaz. Görülme sayıldıysa ardından
  `CANDIDATE_TYPE_PROPOSED` (adayın ilk sayfası; veri `candidate_type_id`, `candidate_type_name`,
  `pages`, `created`, `seen_count`; mesaj yok) yazılır, sayılmayan tekrarda yazılmaz. **Gerekçe:**
  `Bilinmeyen belge türü (04.6.1): bu adayın (dosya X, sayfa N) türü katalogda yok; önerilen aday tür:
  "<ad>". Belge katalogdaki bir türe zorla atanmaz.` — (c) `analizde yazılan türü (<slug>) güncel
  katalogda yok.`, (b) `türü belirlenemedi.`; aday tür adı analizcinin tür adıdır, olay verisinde C18'den
  beri vardır. **Sonrası:** 06.1 `unknown_type` dolu adaya `route: unknown`, `route_reason: reason`
  yazmalı; kuyruk kaydı, `QUEUED_UNKNOWN` ve `Unknown/<upload_id>/` kopyası 08.1'in; S14'ün "onay ve
  yeniden analizden sonra Hazir" kısmı 11.5.2/11.5.3 ve 06–07'nindir.
- **C23** — İsim normalizasyonu (tm 32, 05.1.1): §20.2.1 adımları sırayla yazar ama "aksan" ve
  "noktalama"yı tanımlamaz. `normalize_name(*parts)` (`app/matching/names.py`) şöyle okur: **aksan**
  Unicode uyumluluk katlaması (NFKD + casefold, iki tur) sonrası bütün `Mn`/`Me` işaretleridir
  (`İ → i`, `ß → ss`, `ﬁ → fi`, Arapça hareke); ayrışmayan Latin harfleri (`ł ø đ ð ħ ŧ ŋ → l o d d h
  t n`, `æ œ þ → ae oe th`) tabloyla iner. Almanca `ü → u`dur, `ue` değil (§20.2.1 Türkçe eşlemesiyle
  aynı) — MRZ'nin `MUELLER` yazımı `Müller` ile aynı anahtara inmez; bu 05.3/05.4'ün MRZ önceliğine
  kalır. **Noktalama:** kesme işaretleri (`' ’ ´ ʼ ʿ ʾ ＇`…) ve görünmez biçim karakterleri (`Cf`:
  yumuşak tire, sıfır genişlikli boşluk, BOM) kelimeyi bölmeden silinir (`O'Brien → obrien`, ICAO MRZ
  yazımıyla aynı); harf ve rakam dışındaki her karakter (tire, virgül, nokta, MRZ `<`) kelime
  ayırıcıdır (`Ana-Maria` ≠ `Anamaria`). Rakam kelimede kalır, tekrarlanan kelime korunur (`Ali Ali
  Veli` ≠ `Ali Veli`), kelimeler kod noktası sırasıyla dizilir ve tek boşlukla birleşir. Parçalar
  (`given_names`, `surname`…) tek isim sayılır, `None` atlanır; hangi alanların anahtara gireceği
  05.4'ündür. **Latin dışı harfler** 05.2 gelene kadar olduğu gibi (katlanmış) kalır: düşürülmez, çünkü
  düşürmek bütün Kiril isimleri aynı boş anahtara indirirdi. **Kelimesiz isim** (boş, yalnız
  noktalama/görünmez karakter, hiç parça yok) `EmptyNameError` (`ValueError`) verir; boş anahtar
  döndürülmez ki iki okunamayan isim birbiriyle "eşleşmesin" (§20.2.2 satır 8 çağıranın kararıdır).
  Modül saf fonksiyondur: veritabanı, olay ve göç yok.
- **C24** — Harf çevirisi (tm 33, 05.2.1): §20.2.1 "ICAO çeviri tablosu" der, tabloyu vermez.
  Kaynak ICAO Doc 9303 Bölüm 3 (8. baskı) §6'dır: Tablo B (Kiril) ve Tablo C (Arap, MRZ sütunu),
  `transliterate_name` / `normalize_name` (`app/matching/names.py`). **Anahtar Unicode kod
  noktasıdır**, basılı glif değil: tablonun `0402` satırında glif `Ћ` basılı, değer `D` — `Ђ`
  (U+0402) `D` olur. **Tabloda satırı olmayan harfler:** `Ь` yazılmaz (Rus/Ukrayna/Belarus ICAO
  uygulamalarında atılır; tutulsaydı `Васильев` pasaportun `VASILEV` yazımıyla hiç eşleşmezdi),
  `Ћ` `C` olur (Sırp Latin karşılığı `Ć`, Tablo A'da `C`; `-ић` soyadları için). Satırı olmayan ama
  Unicode'da temel harf + işarete ayrışan harf (`Ѓ Ѝ Ӣ Ӯ Ӂ`) temel harfin satırıyla çevrilir. Başka
  tablo dışı harf (Kazakça `Қ Ә Ө Ү`, Grekçe) **tahminle Latin'e indirilmez**, olduğu gibi kalır:
  aynı yazımla eşleşir, Latin yazımla eşleşmez (yanlış eşleşme yerine eşleşmeme). **Dil
  istisnaları** tabloda yazılı olduğu için uygulanır; dil `language` (ISO 639-1, büyük/küçük harf
  duyarsız, `PageAnalysis.language`) ile gelir — `be` (`Ё IO`, `Г H`), `bg` (`Щ SHT`), `mk` (`Ќ KJ`,
  `Џ DJ`, `Х H`, `Ц C`, `Ғ GJ`), `sr` (`Г H`, `Ж Z`, `Х H`, `Ц C`, `Ч C`, `Ш S`), `uk` (`Г H`,
  `И Y`); başka dil ya da dil yok → varsayılan sütun. Ukraynaca "first character" kelimenin ilk
  harfi okunur (tire/boşluk kelime böler, kesme işareti bölmez: `Мар'яна → Mar'iana`, `Ющенко-Ярова
  → Yushchenko-Yarova`). **Arap:** Tablo C'nin MRZ sütunu (`X`'li geri çevrilebilir biçim), çünkü
  C6'daki sade ünsüz biçimi `ح`/`ه`'yi aynı `h`'ye indirir — eşleştirme anahtarında daha çok
  çakışma; slug (C6) ile anahtar Arapçada farklı yazar, ikisi farklı iştir. "(Not encoded)"
  satırları (harekeler, sükun, üst elif, tatvil, `ڜ ڢ ڧ ڨ`) boş karşılıktır; şedde tablonun
  örneğindeki gibi önceki harfin karşılığını tekrarlar (`عبّاس → EBBAS`, `فضّة → FXDZXDZXAH`),
  araya giren hareke ikilemeyi kesmez, önünde harf yoksa yazılmaz — bu yüzden harekeli `مُحَمَّد`
  (`mxhmmd`) harekesiz `محمد` (`mxhmd`) ile eşleşmez (05.1 testi buna göre güncellendi). `ة`
  arkasından (hareke, tatvil, kesme işareti atlanarak) harf/rakam gelmiyorsa `XAH`, geliyorsa
  `XTA`. Arap sunum biçimleri (U+FB50–FDFF, U+FE70–FEFE) NFKC ile açılır, sonra NFC (`ا + ٓ → آ`,
  `и + ̆ → й`). **Sıra:** çeviri §20.2.1'deki yerinden (aksan atmadan sonra) öne alındı, çünkü
  `й`/`ё`/`ї` ve şedde aksan atılınca kaybolur; tablo çıktısı ASCII olduğundan varsayılan sütunda
  sonuç aynıdır. **Orijinal yazım:** `TransliteratedName(original, latin)` — `original` verilen
  metnin kendisi (NFC bile uygulanmaz), `latin` yalnız Kiril/Arap harfleri çevrilmiş hâli; Kiril
  büyük harfin çok harfli karşılığı komşu harf büyükse büyük (`ЖУКОВ → ZHUKOV`), değilse baş harfi
  büyük (`Жуков → Zhukov`), Arap karşılığı tablodaki gibi büyük. Veritabanına/profile yazma
  (`employee_aliases.raw_name`, profil.md) 05.7.2 / 09.1'in; hangi alanın anahtara gireceği 05.4'ün.
- **C25** — MRZ ayrıştırma, kontrol haneleri ve MRZ önceliği (tm 34, 05.3.1–05.3.3): §20.1 biçimi,
  konumları, algoritmayı ve sonuçları yazar; tablonun sessiz kaldığı yerler şöyle okundu
  (`app/matching/mrz.py`). **Biçim ve karakter:** biçim önce satır sayısı + uzunluktan (her satır
  aynı uzunlukta) belirlenir, sonra karakter kümesine bakılır — sonda boşluk/satır sonu taşıyan satır
  "biçime uymuyor"dur. Yalnız ASCII `a-z` büyütülür; `ı`, `ß`, Kiril `А`, tam genişlikli `Ａ` büyütmeyle
  izinli harfe dönüştürülmez, geçersizdir. Belge kodu 1–2. konumlar birlikte (`P`, `I`, `AC`); dolgu
  değerlerin sağından atılır; cinsiyet `M`/`F` dışında `None`. İsteğe bağlı veri hanesi yalnız TD3'te
  vardır (tablo TD1/TD2'ye hane vermez). PRD'nin 05.3.2 satırı "kontrol hanesi tutmayan MRZ geçersiz"
  der; ayrıntılı §20.1.7 uygulandı: alan hanesi tutmuyorsa yalnız o alan okunamadı, bileşik tutmuyorsa
  MRZ şüpheli (§20.1.5'teki "12.1.4" atfı 20.1.4 okundu). **Değeri kullanılamayan alan:** §20.1.6'nın
  tarih ölçüsü (okunamadı, MRZ geçersiz değil) biçimce bozuk diğer değerlere de uygulandı — rakam
  taşıyan isim alanı (soyad ve adlar birlikte), 1–3 harf olmayan uyruk, boş belge numarası; TD1'in 9
  karakteri aşan numara taşması (hane yerinde `<`) tabloda yok, hane tutmadığı için okunamadı sayılır.
  Son geçerlilikte `<<<<<<` de okunamadır. **Öncelik (05.3.3):** MRZ'nin taşıdığı altı alan
  (`surname`, `given_names`, `document_number`, `nationality`, `date_of_birth`, `expiry_date`) `person`
  ve türün `fields` okumasıyla karşılaştırılır. K6 "MRZ önce okunur" gereği MRZ birincil okumadır:
  görünen okuma yoksa MRZ değeri notsuz yazılır; aynı anahtara iniyorsa görünen yazım olduğu gibi
  kalır (`00 0000001`, `TESTOVA-SHCHELKINA`, `ÖRNEKOVA`); bir yerde bile çelişiyorsa iki yere de MRZ
  yazılır, alan adı nota. MRZ'nin okunamadı saydığı alan görünen okuma okunaklı olsa bile
  `legible: false`/`null` olur (§20.1.7 "o alan geçersizdir") — tür zorunlu tutuyorsa K1 gereği
  Unreadable, güvenli yön. **Karşılaştırma:** belge numarası §20.2.1 normalizasyonuyla; isim
  `normalize_name` ile, görünen yazım sayfanın `language`'ıyla (Ukraynaca `Григоренко = HRYHORENKO`);
  verilen adlar MRZ'nin ikincil tanımlayıcısı `given_names` ya da `given_names + other_names` ile aynı
  anahtara iniyorsa çelişmez (MRZ baba adını yazabilir de yazmayabilir de); çelişkide `other_names`
  değiştirilmez. Tarih ISO metni, uyruk birebir. Kelimesiz görünen okuma çelişkidir. MRZ'de boş isim
  parçası (`<<` yok → verilen ad yok) "MRZ bu alanı taşımıyor" sayılır, görünen okuma kalır. Almanca
  `MÜLLER`/`MUELLER` çelişir, MRZ kazanır (C23). ICAO isim kısaltması (39 karakteri aşan isim) ayrıca
  tanınmaz: kısaltılmış MRZ ismi çelişki olarak kazanır — eşleşmeme yönüdür. **Durumlar:** MRZ yok →
  dokunulmaz; biçime uymuyor → yok sayılır, bilgi notu, §20.2.3 koşul 3 atlanır (tablo "hata değil"
  der); izinsiz karakter → MRZ kullanılmaz, görünen okuma kalır, not; sayfa `is_blank`/`is_readable:
  false` → MRZ'ye güvenilmez (C21), dokunulmaz. **§20.2.3 koşul 3** (`allows_clean_document_number`):
  MRZ yok/yok sayıldıysa doğru; okunduysa numara hanesi ve bileşik hane tutmalı; geçersiz ya da
  güvenilmeyen MRZ'de yanlış (tablo bu durumu yazmaz; hayalet çalışan riskine karşı bileşik hane
  hatasıyla aynı yönde). **Notlar** yalnız alan adı taşır, sabit dört cümle (kontrol hanesi, bileşik,
  geçersiz değer, çelişki); analizcinin notu başta korunur, var olan cümle yeniden eklenmez
  (idempotent); kabul kriteri metni içermez (04.4.2 tanımasını etkilemez). Sonuç yeniden §8.4 şemasıyla
  doğrulanır. Modül saf işlevdir: olay, veritabanı, göç yok; boru hattına bağlanması (04.4 kapısından
  ve 05.4 anahtarından önce) 05.4/06.1'in. `russian_passport` kaydının dört hatalı hanesi düzeltildi
  (görünen değerler aynı).
- **C26** — Kişi anahtarı (tm 35, 05.4.1): PRD anahtarın dört parçasını sayar ama nereden ve nasıl
  okunacağını yazmaz; `build_person_key(analyses, *, today)` (`app/matching/match.py`) şöyle okur.
  **Birim** belge adayıdır (sayfa analizleri belgedeki sırasıyla): kartın ön ve arka yüzü tek anahtar
  verir, parçalar adayın farklı sayfalarından gelebilir. **MRZ önce (K6):** her sayfaya
  `apply_mrz_priority` uygulanır (idempotent, çağıran önceden uygulamışsa sonuç aynı); aday tek belge
  olduğu için MRZ önceliği sayfalar arasında da geçerlidir — MRZ'si okunmuş ve alan için kullanılabilir
  değer taşıyan sayfa varsa `document_number`/`surname`/`given_names`/`date_of_birth` yalnız o
  sayfalardan okunur, ön yüzün farklı görünen okuması anahtara girmez (gruplama kimliği çelişen
  sayfaları zaten birleştirmez). MRZ alanı taşımıyorsa (hane tutmadı, `<<` yok) alan bütün sayfalardan
  okunur. **Okuma:** `person` değeri ve okunaklı `fields` okuması (§8.4'te iki yer); boş/okunamaz diyen
  sayfanın okumasına güvenilmez (C21); sayfa alanı `legible: false` yazıyorsa o sayfanın `person`
  değeri de girmez (K1), öteki yüzün okunamadı yazması ön yüzü etkilemez. **Karşılaştırma anahtarı:**
  numara §20.2.1 (`normalize_document_number`: büyük harf, `[\s./-]` silinir — `mrz.py` ile aynı
  küme), isim parçası sayfanın `language`'ıyla `normalize_name`, doğum tarihi takvim günü (`fields`
  metni yalnız geçerli `YYYY-AA-GG`). Kelimesiz isim ve ayırıcıdan ibaret numara okuma değildir.
  **Çelişki:** farklı anahtar kalan alanın adı `conflicts`'e (sabit sıra) yazılır; ad-soyad, doğum
  tarihi ve orijinal yazım tekildir, çelişirse `None` (tahminle seçilmez; alt küme isim `TEST` / `TEST
  ANNA` de çelişkidir); belge numaraları PRD'deki gibi çoğuldur, her farklı numara sayfa sırasıyla
  kalır — birden fazla numara çelişkidir, yorumu 05.5/05.6'nın. **Ad-soyad** = `given_names` +
  `surname`, ikisi de okunmuşsa (tek parçalı isim anahtar vermez, eşleşmeme yönü); `other_names`
  girmez. **Orijinal yazım** ilk okunduğu gibi `TransliteratedName` (sayfanın diliyle) + normalize
  anahtar; `name_keys` ad-soyad ve orijinal yazım anahtarlarını tekrarsız verir (D7 gibi ICAO dışı
  Latin yazımda iki anahtar). **Numara başına `legible`:** bir sayfanın okunaklı `fields.document_number`
  okuması da bu değere iniyorsa doğru (§20.2.3 koşul 2'nin okunaklılık kısmı); yalnız `person`'dan
  okunan numara okunaklı sayılmaz. **`mrz_allows_clean_document_number`:** adayın bütün sayfalarında
  (güvenilmeyenler dahil) `allows_clean_document_number`. Temiz numara kararı (tür, 5 karakter)
  05.6'nın, eşleştirme 05.5'in. Modül saf işlevdir: olay, veritabanı, göç yok; boru hattına bağlanması
  05.5/06.1'in.

## D. Sapmalar

PRD'den veya kilitli kararlardan her sapma buraya numaralı yazılır (D1, D2…).
Sapma yazmadan karar değiştirilmez.

Aşağıdaki üç sapma **ürünün ilk sözlü tanımına** göredir ve kurulum aşamasında,
kullanıcı onayıyla verilmiştir. PRD ve `MASTER-PROMPT.md` zaten sapılmış hâli yazar;
bu kayıt neden sapıldığının izlenebilir olması içindir.

- **D1 — Çalışan klasörü adına kalıcı numara eklendi.** İlk tanım `Employees/Ahmet_Cakar/`
  diyordu. Aynı ad-soyada sahip iki çalışan geldiğinde bu yapı çöker ve iki kişinin
  belgeleri aynı klasörde birikir. Klasör adı `Ad_Soyad_E0001` oldu; E numarası sistem
  tarafından verilir ve asla değişmez (K8). İsim yalnız görüntüleme içindir.
- **D2 — Word ve Excel için format dönüşümü tümüyle kaldırıldı.** İlk tanım §10'da
  "gerektiğinde formatlar arasında fiziksel dönüşüm" diyordu. Office dosyalarının
  dönüştürülmesi yeniden render demektir (font ve sayfa kırılımları değişir) ve resmî
  belgeler bu formatlarda gelmez. Word/Excel artık analiz edilmez, dönüştürülmez;
  `attachment` türüyle olduğu gibi saklanır (K2). Kullanıcı kararıdır.
- **D3 — Dört faza bölündü.** İlk tanımda faz yoktu; her şey tek bir hedef olarak
  anlatılıyordu. Otonom döngünün iş sırası seçebilmesi ve kapanış kapısı
  işleyebilmesi için PRD §5'te Faz 0-3 tanımlandı. Kapsamda daralma yok; yalnız sıra var.
- **D4 — PRD'de tablo sayısı çelişkisi (tm 3).** 00.3.1 "§8'deki 15 tablo" der; §8.1
  tablosu ise 16 tablo listeler (`employee_contacts` 05.8 ile sonradan eklenmiş). §8.1
  listesi esas alındı, 16 tablonun hepsi modellendi. PRD metninin düzeltilmesi insana
  bırakıldı.
- **D5 — `allowed_conversions` sözlüğünde PRD içi çelişki (tm 6).** §20.3 "3, 4, 5 ve 6
  numaralı satırlar için seçilen işlem türün `allowed_conversions` listesinde bulunmak
  zorundadır" der (liste işlem adı taşır); §20.5 `render_image` için "listede `pdf_to_jpeg`
  varsa" der (dönüşüm adı). §20.3 karar tablosu esas alındı: değerler `merge`, `wrap_image`,
  `extract_image`, `render_image`; `pdf_to_jpeg` şemada yoktur ve reddedilir, 06.4.1 kontrolü
  "seçilen işlem ∈ liste" olur. PRD §20.5 metninin düzeltilmesi insana bırakıldı.
- **D6 — Metin katmanı çıkarma (02.2.1, tm 14) yeni olay atmıyor.** K15 "her adım events
  tablosuna yazılır" der, ama PRD §8.3'ün kapalı olay türü listesinde metin katmanı için
  ayrı bir tür yok; en yakın aday `PAGE_EXTRACTED` §7.2 sayfa çıkarma (fiziksel PDF işlemi)
  içindir, anlamı farklıdır. `extract_upload_file_text` bu yüzden olay atmadan yalnız
  `pages.text_layer`'ı yazıyor; sayfanın üretilmiş olması zaten `PAGE_RENDERED` ile loglanmış
  durumda. Aynı soru 02.4/02.5'te de çıkar (kapalı listede `PAGE_BLANK` var, gömülü görüntü
  tespiti için yok) — karar insana bırakıldı, gerekirse §8.3 listesine yeni tür eklenmeli.
- **D7 — §20.2.1'in isim örneği kendi istediği ICAO tablosuyla çelişiyor (05.2.1, tm 33).** PRD
  "Kiril ve Arap yazımı ICAO çeviri tablosuyla Latin'e çevir" der ve hemen ardından
  "`Дмитрий Васильев`, `VASILIEV DMITRY` ve `Dmitry Vasiliev` aynı anahtara inmelidir" der. ICAO
  Doc 9303 Tablo B `Дмитрий Васильев`'i `DMITRII VASILEV` yapar (`ий → II`, `Ь` yazılmaz); iki Latin
  örnek ICAO dışı İngilizce yazımdır ve ayrı anahtardır (`dmitry vasiliev` ≠ `dmitrii vasilev`).
  Örneği tutturmak `y/ii/i`, `ie/e` gibi PRD'de olmayan bir yazım varyantı katlaması uydurmak
  demekti; bu da farklı kişilerin isimlerini birleştirip yanlış eşleşme yüzeyini büyütür. Tablo
  uygulandı, katlama eklenmedi: Kiril yazım, 2014 sonrası Rus pasaportunun ICAO Latin yazımı
  (`VASILEV DMITRII`) ve MRZ'si ile aynı anahtara iner; eski/İngilizce yazımla inmez
  (`test_non_icao_spelling_is_not_folded_into_the_icao_key` bunu sabitler). Eşleşmemek güvenli
  yöndür (satır 5–8: Unresolved/onay bekleyen profil; satır 6'da temiz numara varsa mükerrer
  profil, İK taşımasıyla düzelir). Aynı belgede hem Latin hem orijinal yazım varsa ikisinin de
  alias olarak birikmesi (05.7.2) iki yazımı aynı çalışana bağlar. **Ayrıca tablonun kendi
  kusurları** tabloda yazıldığı gibi uygulandı: Sırpça `Г = H` (Sırp Latin yazısında `G`'dir —
  `Горан → Horan`), Makedonca `GJ` notu `Ѓ` (U+0403) yerine `Ғ` (U+0492) satırında, `Һ = C`, `0402`
  satırında glif `Ћ` (C24'te kod noktası esas alındı). Karar insana bırakıldı: PRD örneği ICAO
  yazımına düzeltilmeli mi, yoksa bir varyant katlaması mı tanımlanmalı; Sırpça `Г` istisnası
  kaldırılmalı mı.

## G. İş Kırılımı Dizini

Task Master'a aktarımın kaynağı budur. Her satır bir görevdir; `ID` sütunu görev
başlığının başında birebir geçer.

### Düz tablo (aktarım kaynağı)

| ID | Başlık | PRD | Etiket | Bağımlılık | Faz |
| --- | --- | --- | --- | --- | --- |
| 00.1 | Uygulama iskeleti, test ve kapsayıcı altyapısı | 00.1.1, 00.1.2, 00.1.3, 00.1.4 | [OPUS-XHIGH] | — | 0 |
| 00.2 | Ortam değişkeni tabanlı yapılandırma | 00.2.1, 00.2.2 | [SONNET-XHIGH] | 00.1 | 0 |
| 00.3 | Veri modeli ve göç altyapısı | 00.3.1, 00.3.2, 00.3.3 | [OPUS-XHIGH] | 00.2 | 0 |
| 00.4 | Depolama katmanı: yol, slug, adlandırma, atomik yazma | 00.4.1, 00.4.2, 00.4.3, 00.4.4 | [OPUS-XHIGH] | 00.2 | 0 |
| 00.5 | Olay logu altyapısı | 00.5.1, 00.5.2 | [SONNET-XHIGH] | 00.3 | 0 |
| 00.6 | Belge türü kataloğu ve başlangıç tohumu | 00.6.1, 00.6.2, 00.6.3 | [OPUS-XHIGH] | 00.3, 00.4 | 0 |
| 01.1 | Yükleme uç noktası ve parti oluşturma | 01.1.1, 01.1.2 | [SONNET-XHIGH] | 00.3, 00.4, 00.5 | 0 |
| 01.2 | İçerik tabanlı dosya türü tespiti | 01.2.1, 01.2.2 | [SONNET-XHIGH] | 01.1 | 0 |
| 01.3 | Boyut ve sayfa sınırı denetimi | 01.3.1 | [SONNET-XHIGH] | 01.1 | 0 |
| 01.4 | Tekrar yükleme tespiti (SHA-256) | 01.4.1 | [SONNET-XHIGH] | 01.1 | 0 |
| 01.5 | Inbox'a değişmez yazma | 01.5.1 | [SONNET-XHIGH] | 01.1 | 0 |
| 01.6 | Parti durumu sorgulama | 01.6.1 | [SONNET-XHIGH] | 01.1 | 0 |
| 02.1 | PDF sayfa görüntüsü üretimi | 02.1.1 | [OPUS-XHIGH] | 00.4, 01.5 | 0 |
| 02.2 | PDF metin katmanı çıkarma | 02.2.1 | [SONNET-XHIGH] | 02.1 | 0 |
| 02.3 | Görüntü dosyaları için analiz kopyası | 02.3.1 | [SONNET-XHIGH] | 02.1 | 0 |
| 02.4 | Boş sayfa tespiti | 02.4.1 | [SONNET-XHIGH] | 02.1 | 0 |
| 02.5 | Gömülü tek görüntü tespiti | 02.5.1 | [OPUS-XHIGH] | 02.1 | 0 |
| 03.1 | Sayfa analizi şeması | 03.1.1, 03.1.2, 03.1.3, 03.1.4 | [OPUS-XHIGH] | 00.6 | 0 |
| 03.2 | Sağlayıcı soyutlaması ve Anthropic uygulaması | 03.2.1, 03.2.2 | [OPUS-XHIGH] | 03.1 | 0 |
| 03.3 | OpenAI sağlayıcı uygulaması | 03.3.1 | [SONNET-XHIGH] | 03.2 | 0 |
| 03.4 | Analiz promptu ve disiplin kuralları | 03.4.1 | [OPUS-XHIGH] | 03.1, 00.6 | 0 |
| 03.5 | Yeniden deneme ve hata dayanıklılığı | 03.5.1 | [SONNET-XHIGH] | 03.2 | 0 |
| 03.6 | Kayıtlı yanıt sağlayıcısı (test altyapısı) | 03.6.1 | [SONNET-XHIGH] | 03.2 | 0 |
| 03.7 | Sayfa analizi çalıştırıcı | 03.7.1, 03.7.2 | [OPUS-XHIGH] | 03.2, 03.4, 03.5, 02.1 | 0 |
| 04.1 | Dosya içi gruplama ve ön/arka eşleşmesi | 04.1.1, 04.1.2 | [OPUS-MAX] | 03.7, 00.6 | 0 |
| 04.2 | Ardışıklık güvenlik kuralı | 04.2.1 | [OPUS-MAX] | 04.1 | 0 |
| 04.3 | Dosyalar arası gruplama | 04.3.1, 04.3.2 | [OPUS-MAX] | 04.1 | 0 |
| 04.4 | Zorunlu alan okunaklılık kapısı | 04.4.1, 04.4.2 | [OPUS-XHIGH] | 04.1 | 0 |
| 04.5 | Beklenen sayfa sayısı kontrolü | 04.5.1 | [SONNET-XHIGH] | 04.1 | 0 |
| 04.6 | Bilinmeyen tür ve aday tür önerisi | 04.6.1 | [OPUS-XHIGH] | 04.1 | 0 |
| 04.7 | Word/Excel (Attachment) yolu | 04.7.1 | [SONNET-XHIGH] | 01.2, 00.6 | 0 |
| 05.1 | İsim normalizasyonu | 05.1.1 | [OPUS-XHIGH] | 00.3 | 0 |
| 05.2 | Harf çevirisi (Kiril, Arap) | 05.2.1 | [OPUS-XHIGH] | 05.1 | 0 |
| 05.3 | MRZ ayrıştırma ve kontrol haneleri | 05.3.1, 05.3.2, 05.3.3 | [OPUS-XHIGH] | 05.1 | 0 |
| 05.4 | Kişi anahtarı üretimi | 05.4.1 | [OPUS-XHIGH] | 05.2, 05.3 | 0 |
| 05.5 | Çalışan eşleştirme sırası | 05.5.1, 05.5.2, 05.5.3 | [OPUS-XHIGH] | 05.4 | 0 |
| 05.6 | Otomatik çalışan oluşturma | 05.6.1 | [OPUS-XHIGH] | 05.5 | 0 |
| 05.7 | Onay bekleyen profil ve alias birikimi | 05.7.1, 05.7.2 | [OPUS-XHIGH] | 05.5 | 0 |
| 05.8 | İletişim bilgisi, dil ve alfabe kaydı | 05.8.1, 05.8.2, 05.8.3 | [SONNET-XHIGH] | 05.5, 00.3 | 0 |
| 06.1 | Plan JSON üretimi ve determinizm | 06.1.1, 06.1.2 | [OPUS-XHIGH] | 04.1, 04.4, 04.5, 04.6, 05.5, 05.6, 05.7, 00.6 | 0 |
| 06.2 | İşlem seçimi | 06.2.1 | [OPUS-XHIGH] | 06.1 | 0 |
| 06.3 | Direkt Belge kuralı | 06.3.1, 06.3.2 | [OPUS-XHIGH] | 06.2 | 0 |
| 06.4 | Dönüşüm izni kontrolü | 06.4.1 | [OPUS-XHIGH] | 06.2 | 0 |
| 06.5 | Doğrulayıcı seti | 06.5.1, 06.5.2 | [OPUS-XHIGH] | 06.1, 05.3 | 0 |
| 06.6 | Yeniden çalıştırma ve yeniden analiz | 06.6.1, 06.6.2 | [OPUS-XHIGH] | 06.1 | 0 |
| 07.1 | passthrough işlemi | 07.1.1 | [SONNET-XHIGH] | 06.1 | 0 |
| 07.2 | extract işlemi | 07.2.1 | [OPUS-XHIGH] | 06.2 | 0 |
| 07.3 | merge işlemi | 07.3.1 | [OPUS-XHIGH] | 06.2, 06.3 | 0 |
| 07.4 | wrap_image işlemi | 07.4.1 | [SONNET-XHIGH] | 06.2 | 0 |
| 07.5 | extract_image işlemi | 07.5.1 | [OPUS-XHIGH] | 06.2 | 0 |
| 07.6 | render_image işlemi | 07.6.1 | [SONNET-XHIGH] | 06.2, 06.4 | 0 |
| 07.7 | Çıktı yazma, köken kaydı ve Alinan kopyası | 07.7.1, 07.7.2 | [OPUS-XHIGH] | 07.1, 07.2, 00.5 | 0 |
| 07.8 | Uygulayıcı idempotenliği | 07.8.1 | [OPUS-XHIGH] | 07.7 | 0 |
| 08.1 | Kuyruğa yönlendirme ve gerekçe dosyası | 08.1.1, 08.1.2 | [SONNET-XHIGH] | 06.1, 07.7 | 0 |
| 08.2 | Kuyruk öğesini çalışana atama | 08.2.1 | [OPUS-XHIGH] | 08.1, 06.6 | 0 |
| 08.3 | Onay bekleyen profili onaylama | 08.3.1 | [OPUS-XHIGH] | 08.2, 05.7 | 0 |
| 08.4 | Arşive taşıma | 08.4.1 | [SONNET-XHIGH] | 08.1 | 0 |
| 09.1 | profil.md üretimi | 09.1.1, 09.1.2, 09.1.3 | [SONNET-XHIGH] | 07.7, 05.7, 05.8 | 0 |
| 09.2 | Orkestrasyon ve parti durum makinesi | 09.2.1, 09.2.2, 09.2.3 | [OPUS-XHIGH] | 07.8, 08.1, 09.1 | 0 |
| 09.3-a | Sentetik belge üreteci | 09.3.1 | [OPUS-XHIGH] | 09.2, 03.6 | 0 |
| 09.3-b | Kabul senaryoları S1-S5 | 09.3.2 | [OPUS-XHIGH] | 09.3-a | 0 |
| 09.3-c | Kabul senaryoları S6-S10 | 09.3.3 | [OPUS-XHIGH] | 09.3-b | 0 |
| 09.3-d | Kabul senaryoları S11-S15 ve S18 | 09.3.4 | [OPUS-XHIGH] | 09.3-c | 0 |
| 10.1 | Panel iskeleti ve giriş | 10.1.1, 10.1.2, 10.1.3 | [OPUS-XHIGH] | 09.2 | 1 |
| 10.2 | Yükleme sayfası | 10.2.1, 10.2.2 | [SONNET-XHIGH] | 10.1, 01.1 | 1 |
| 10.3 | Yükleme detay sayfası | 10.3.1, 10.3.2 | [SONNET-XHIGH] | 10.1, 09.2 | 1 |
| 10.4 | Çalışan listesi ve arama | 10.4.1, 10.4.2 | [SONNET-XHIGH] | 10.1, 09.1 | 1 |
| 10.5 | Çalışan profili sayfası | 10.5.1, 10.5.4, 10.5.2, 10.5.3 | [SONNET-XHIGH] | 10.4 | 1 |
| 10.6 | Belge geçmişi görünümü | 10.6.1 | [SONNET-XHIGH] | 10.3, 07.7 | 1 |
| 10.7-a | Kuyruk ekranları ve öğe detayı | 10.7.1 | [SONNET-XHIGH] | 10.1, 08.2, 08.3 | 1 |
| 10.7-b | Kuyruktan çalışana atama akışı | 10.7.2 | [OPUS-XHIGH] | 10.7-a | 1 |
| 10.7-c | Kuyruktan profil oluşturma akışı | 10.7.3 | [OPUS-XHIGH] | 10.7-b | 1 |
| 10.8 | İki aşamalı onay ve manuel taşıma | 10.8.1, 10.8.2 | [OPUS-XHIGH] | 10.5, 10.7-c | 1 |
| 10.9 | İçerik düzenleme yokluğu ve erişim logu | 10.9.1, 10.9.2 | [SONNET-XHIGH] | 10.5 | 1 |
| 11.1 | Katalog yönetim ekranı | 11.1.1, 11.1.2, 11.1.3 | [SONNET-XHIGH] | 10.1, 00.6 | 1 |
| 11.2 | Örnek belge yükleme | 11.2.1 | [SONNET-XHIGH] | 11.1 | 1 |
| 11.3 | Tür açıklaması üretimi | 11.3.1 | [OPUS-XHIGH] | 11.2, 03.2 | 1 |
| 11.4 | Prompt derleyici ve token bütçesi | 11.4.1, 11.4.2 | [OPUS-XHIGH] | 11.1, 03.4 | 1 |
| 11.5 | Aday tür akışı ve onay | 11.5.1, 11.5.2, 11.5.3, 11.5.4 | [OPUS-XHIGH] | 11.1, 04.6, 10.7-c | 1 |
| 11.6 | Profil fotoğrafı kural seti | 11.6.1 | [SONNET-XHIGH] | 11.1 | 2 |
| 11.7 | Profil fotoğrafı görsel kontrolü | 11.7.1, 11.7.2 | [OPUS-XHIGH] | 11.6, 03.7 | 2 |
| 11.8 | Fotoğraf örneklerinden öğrenme | 11.8.1 | [OPUS-XHIGH] | 11.7, 11.3 | 2 |
| 12.1 | Bot iskeleti ve beyaz liste | 12.1.1, 12.1.2 | [SONNET-XHIGH] | 09.2 | 2 |
| 12.2 | Telegram üzerinden belge alma | 12.2.1, 12.2.2, 12.2.3 | [SONNET-XHIGH] | 12.1, 01.1 | 2 |
| 12.3 | Doğal dil belge istekleri | 12.3.1, 12.3.2, 12.3.3 | [OPUS-MAX] | 12.1, 10.4 | 2 |
| 12.4 | Kuyruk ve hata bildirimleri | 12.4.1 | [SONNET-XHIGH] | 12.1, 08.1 | 2 |
| 13.1 | Maliyet ölçümü ve görünürlüğü | 13.1.1 | [SONNET-XHIGH] | 03.7, 10.1 | 3 |
| 13.2 | Ucuz model ön eleme | 13.2.1, 13.2.2 | [OPUS-XHIGH] | 13.1, 03.7 | 3 |
| 13.3 | Kalıcı işçi kuyruğu | 13.3.1 | [OPUS-XHIGH] | 09.2 | 3 |
| 13.4 | Erişim logu, yedekleme ve geri yükleme | 13.4.1, 13.4.2 | [SONNET-XHIGH] | 10.9 | 3 |
| 13.5 | Üretim dağıtımı | 13.5.1 | [SONNET-XHIGH] | 10.1 | 3 |
| 13.6 | İzleme ve uyarılar | 13.6.1 | [SONNET-XHIGH] | 13.3, 12.4 | 3 |

## K. Kanıt Geçmişi (evidence log)

Her kapanış, kapattığı gereksinimin `#### K<kod>` bloğuna madde ekler. Blok yoksa açılır;
var olan maddeler silinmez. Biçim:

```
#### K99.9 — <PRD kodu> · <kısa başlık>        <-- ÖRNEK, gerçek kod değil
- ✅ <ne yapıldı> — `<dosya>` · test `<test dosyası>` (n) · tm <id>
```

#### K00.1 — 00.1.1–00.1.4 · Uygulama iskeleti, test ve kapsayıcı altyapısı
- ✅ FastAPI iskeleti, `GET /health` → 200 `{"status":"ok"}` — `app/main.py` · test `tests/test_health.py` (2) · tm 1
- ✅ pyproject.toml bağımlılıkları (Python 3.12, dev: pytest/pytest-cov/httpx2/ruff), `live` işareti kayıtlı, çıplak `pytest` exit 0 — `pyproject.toml` · test `tests/test_health.py` (2) · tm 1
- ✅ `docker compose up -d --build` → konteyner healthy, `curl /health` 200 `{"status":"ok"}`; `docker compose config` exit 0 — `Dockerfile` · `docker-compose.yml` · `.dockerignore` · tm 1
- ✅ `ruff check .` exit 0 · `ruff format --check .` exit 0 · compileall exit 0 · kapsam %100 — `pyproject.toml` [tool.ruff] · tm 1

#### K00.2 — 00.2.1, 00.2.2 · Ortam değişkeni tabanlı yapılandırma
- ✅ pydantic-settings tabanlı `Settings` (`.env` + ortam değişkeni, zorunlu `database_url`, varsayılanlı `app_env`/`data_dir`); eksik zorunlu değişkende değişken adını söyleyen `RuntimeError` — `app/config.py` · `.env.example` · test `tests/test_config.py` (4) · tm 2

#### K00.3 — 00.3.1, 00.3.2, 00.3.3 · Veri modeli ve göç altyapısı
- ✅ §8.1'deki 16 tablo SQLAlchemy 2.x modeli (isimlendirme kuralı, UTC zaman tipi, silme kaskadı yok); iki yönlü ilişkiler, FK/CHECK/UNIQUE kısıtları testte doğrulandı — `app/db/models.py` · `app/db/session.py` · test `tests/db/test_models.py` (11) · `tests/db/test_session.py` (4) · tm 3
- ✅ Alembic zinciri (`0001`): temiz SQLite ve PostgreSQL 16 üzerinde `alembic upgrade head` exit 0, `alembic check` şema farkı yok, `DATABASE_URL` CLI yolu — `alembic.ini` · `alembic/env.py` · `alembic/versions/0001_initial_schema.py` · test `tests/db/test_migrations.py` (5; PG testi `BELGEEE_TEST_POSTGRES_URL` ile, geçici `postgres:16-alpine` üzerinde koşuldu) · tm 3
- ✅ `allocate_employee_number`: `E0001` biçimi, sayısal artış (`E9999 → E10000`), eşzamanlı 50 çağrıda çakışma yok (SQLite `BEGIN IMMEDIATE`, PG advisory kilit; kilitsiz kontrol denemesinde PG 46/50, SQLite 21/50 çakıştı) — `app/db/models.py` · test `tests/db/test_employee_number.py` (12; PG eşzamanlılık testi PG 16'da yeşil) · tm 3

#### K00.4 — 00.4.1–00.4.4 · Depolama katmanı: yol, slug, adlandırma, atomik yazma
- ✅ 00.4.1 uygulama açılışında (FastAPI lifespan) §8.2'nin sabit ağacı kurulur, tekrar açılış mevcut dosyaya dokunmaz; kimlikli yollar (`Inbox/<upload_id>`, `Employees/<klasör>/Alinan|Hazir|profil.md`, kuyruk + `reason.json`, `Archive/<yyyy-mm>`, `catalog.yaml`, `examples/<slug>`, `cache/pages/<file_id>`) tek yerden, `..`/`/` içeren parça reddedilerek üretilir; kapsayıcıda `docker compose up --build` → healthy, `/srv/data` ağacı kuruldu — `app/storage/layout.py` · `app/main.py` · `Dockerfile` · `docker-compose.yml` · test `tests/storage/test_layout.py` (9 fonksiyon / 19 durum) · tm 4
- ✅ 00.4.2 Türkçe, Kiril (Rusça/Ukraynaca/Sırpça/Kazakça) ve Arap (hareke, sunum biçimi, Arap-Hint rakamı dahil) isimler `[A-Za-z0-9_-]` kümesine iner; Latin-1/Latin Genişletilmiş, Kiril, Arapça ve Arapça sunum biçimi bloklarının her karakteri testte taranır — `app/storage/slug.py` · test `tests/storage/test_slug.py` (11 fonksiyon / 36 durum) · tm 4
- ✅ 00.4.3 `Ad_Soyad_E0001` klasör ve `Ad_Soyad-Belge-Turu.ext` dosya adı; aynı türden ikinci belge `-2`, üçüncü `-3`; mevcut dosyanın üzerine yazılmaz (farklı harf büyüklüğü, farklı uzantı, tarama sonrası yarış ve 16 eşzamanlı yazar dahil) — `app/storage/naming.py` · `app/storage/atomic.py` · test `tests/storage/test_naming.py` (10 fonksiyon / 26 durum) · `tests/storage/test_atomic.py` (21 fonksiyon / 23 durum) · tm 4
- ✅ 00.4.4 SHA-256 yazarken hesaplanır (`sha256_file` ile eşit); istisna, `KeyboardInterrupt`, `fsync`/yayın hatası ve **öldürülen alt süreçte** hedef adda yarım dosya kalmaz, geçici dosya silinir/açılışta temizlenir; `replace_file` kesilirse eski içerik korunur; POSIX yolu (`os.link` + dizin `fsync`) Linux kapsayıcısında elle doğrulandı — `app/storage/atomic.py` · test `tests/storage/test_atomic.py` · tm 4

#### K00.5 — 00.5.1, 00.5.2 · Olay logu altyapısı
- ✅ 00.5.1 PRD §8.3'teki 37 olay türü `EventType(enum.StrEnum)` sabit listesi; `record_event` her olayı `events` tablosuna yazar — `app/events.py` · test `tests/test_events.py` (7) · tm 5
- ✅ 00.5.2 `event_context` (contextvar tabanlı, iç içe kullanımda belirtilmeyen alanları dıştan miras alır) içinde atılan olaylar upload/file/page alanlarını açıkça verilmedikçe otomatik taşır — `app/events.py` · test `tests/test_events.py` (7) · tm 5

#### K00.6 — 00.6.1, 00.6.2, 00.6.3 · Belge türü kataloğu ve başlangıç tohumu
- ✅ 00.6.1 pydantic sözleşme §8.6'nın tüm alanlarını (`acceptance_criteria` dahil) ve `known_document_types`'ın her sütununu tanımlar; `direct: true` türde `allowed_conversions` doluysa katalog bütün olarak reddedilir (yanındaki geçerli kayıt da yüklenmez, CLI exit 1, DB'de 0 satır); geçersiz enum/tip/eksik alan/yazım hatalı anahtar/tekrar/sayfa aralığı hata satırıyla reddedilir — `app/catalog/schema.py` · test `tests/catalog/test_schema.py` (14 fonksiyon / 47 durum) · tm 6
- ✅ 00.6.2 8 türlük tohum: Russian/Turkish/Serbian Passport, Serbian Residence Card, Serbian Driving License, Work Permit, Profile Picture, Attachment; `russian_passport` §8.6 örneğine eşit; açılışta `data/KnownDocuments/catalog.yaml` yoksa yazılır, varsa korunur; temiz SQLite'ta `alembic upgrade head` + `python -m app.catalog import` → 8 tür; wheel içinde `app/catalog/seed_catalog.yaml` var — `app/catalog/seed_catalog.yaml` · `app/catalog/yaml_io.py` · `app/main.py` · `pyproject.toml` · test `tests/catalog/test_seed.py` (11) · tm 6
- ✅ 00.6.3 YAML → DB (slug'a göre ekle/güncelle, katalogda olmayan türe dokunmaz) ve DB → YAML (atomik `replace_file`); tohum → DB → dışa aktarım bayt bayt aynı (testte ve CLI ile elle), DB'deki düzenleme dışa aktarımla YAML'a geçer, tekrarlanan içe aktarma değişiklik yapmaz; `python -m app.catalog import|export` — `app/catalog/sync.py` · `app/catalog/yaml_io.py` · `app/catalog/__main__.py` · test `tests/catalog/test_sync.py` (9) · `tests/catalog/test_yaml_io.py` (10 fonksiyon / 12 durum) · `tests/catalog/test_cli.py` (8) · tm 6

#### K01.1 — 01.1.1, 01.1.2 · Yükleme uç noktası ve parti oluşturma
- ✅ `POST /api/uploads`: çoklu dosyayı tek partide kabul eder, her dosyayı `Inbox/<upload_id>/<orijinal_ad>` altına değişmez yazar (K10, `write_file`), `sha256`/`mime` ile `upload_files` satırı açar, her dosya için `FILE_UPLOADED` olayı yazar; `upload_id` `u_yyyymmdd_0001` biçiminde günlük sıfırlanan sırayla üretilir (`allocate_upload_id`, `allocate_employee_number` ile aynı kilit deseni); istek `context_employee_id` taşıyabilir ve partiye kaydedilir (var olmayan çalışan 404), aynı partide aynı adda dosya ve yol ayracı/`..` içeren ad 400 ile reddedilir — `app/web/routers/uploads.py` · `app/db/models.py` (`allocate_upload_id`) · `app/main.py` · test `tests/web/test_uploads.py` (9) · `tests/db/test_upload_id.py` (13; PG eşzamanlılık testi `BELGEEE_TEST_POSTGRES_URL` ile) · tm 7

#### K01.2 — 01.2.1, 01.2.2 · İçerik tabanlı dosya türü tespiti
- ✅ `detect_file_kind(content)` yalnız ilk baytlardaki imzaya bakar, dosya adı/uzantısı hiç okunmaz — PDF/JPEG/PNG imzası doğrudan, OOXML (DOCX/XLSX) ZIP içindeki `word/document.xml`/`xl/workbook.xml` yoluyla, eski ikili DOC/XLS (CFBF) UTF-16LE `WordDocument`/`Workbook`/`Book` akış adıyla ayırt edilir (K2: DOC/XLS/DOCX/XLSX yalnız tanınır, analiz edilmez); yedi türün dışındaki her içerik (boş, düz metin, bozuk zip, isimsiz OLE) `UnsupportedFileTypeError` ile anlaşılır Türkçe mesajla reddedilir — `app/storage/filetype.py` · test `tests/storage/test_filetype.py` (10 fonksiyon / 14 durum) · tm 8

#### K01.3 — 01.3.1 · Boyut ve sayfa sınırı denetimi
- ✅ Her dosya diske yazılmadan/parti oluşturulmadan önce boyut (`max_upload_file_size_bytes`, varsayılan 20 MiB) ve, içerik `detect_file_kind` ile PDF tespit edilirse, sayfa sayısı (`max_upload_pdf_pages`, varsayılan 30, `pypdf.PdfReader` ile sayılır) denetlenir; sınırı aşan tek dosya bile olsa 400 döner, kullanıcıya dosyayı bölmesi söylenir, parti/DB satırı hiç oluşmaz; PDF imzalı ama pypdf ile çözülemeyen içerikte (ör. sentetik olmayan test baytı) sayfa denetimi sessizce atlanır — `app/config.py` · `app/web/routers/uploads.py` · `pyproject.toml` (pypdf) · test `tests/web/test_uploads.py` (+6) · tm 9

#### K01.4 — 01.4.1 · Tekrar yükleme tespiti (SHA-256)
- ✅ `find_original_by_sha256`: aynı SHA-256 daha önce yüklenmişse özgün (`is_duplicate_of IS NULL`) satırı döner, zincirlenmeyi önlemek için tekrarın kendisi asla kök sayılmaz; yükleme uç noktası her dosya için bu sorguyu çalıştırır — eşleşme varsa dosya yine K10 gereği değişmeden Inbox'a yazılır, `UploadFile.is_duplicate_of` kök satıra bağlanır ve `FILE_UPLOADED` yerine `FILE_DUPLICATE` olayı (`duplicate_of_file_id` verisiyle) yazılır; analiz adımı henüz yok, bu bayrağı okuyup atlamak sonraki bir görevin işi — `app/storage/hashing.py` · `app/web/routers/uploads.py` · test `tests/storage/test_hashing.py` (4) · `tests/web/test_uploads.py` (+2) · tm 10

#### K01.5 — 01.5.1 · Inbox'a değişmez yazma
- ✅ `write_to_inbox(layout, upload_id, name, content)` — `Inbox/<upload_id>/<name>` yoluna `write_file`'ın sabit bağ garantisiyle yazar; aynı ada ikinci yazma denemesi `FileExistsError` ile reddedilir, orijinal içerik değişmeden kalır. Yükleme uç noktası artık `inbox_dir / name` ile elle yol kurup `write_file` çağırmak yerine bu sarmalayıcıyı kullanıyor (yol kuralı tek yerde, MASTER-PROMPT §4) — `app/storage/inbox.py` · `app/web/routers/uploads.py` · test `tests/storage/test_inbox.py` (3) · tm 11

#### K01.6 — 01.6.1 · Parti durumu sorgulama
- ✅ `GET /api/uploads/{upload_id}` — parti bulunamazsa 404, aksi halde `status` (`Upload.status`), `files` listesi (`id`, `original_name`, `mime`, `sha256`, `page_count`, `is_duplicate`) ve `progress` (`total_files`, `rendered_files` — en az bir `Page` satırı olan dosya sayısı, bkz. C9) döner — `app/web/routers/uploads.py` · test `tests/web/test_uploads.py` (+4) · tm 12

#### K02.1 — 02.1.1 · PDF sayfa görüntüsü üretimi
- ✅ PyMuPDF ile her PDF sayfası `PAGE_RENDER_DPI`'da render edilir; o çözünürlükte uzun kenar `PAGE_RENDER_MAX_LONG_EDGE_PX`'i aşacaksa ölçek uzun kenar tam sınıra oturacak kadar küçültülür (A4 200 DPI → 1109×1568, yatay ve `/Rotate` 90/270 sayfada genişlik sınıra iner, 15 tuhaf sayfa boyutunda uzun kenar sınırı hiç aşmaz, MuPDF'in dışa piksel yuvarlaması düzeltilir), en-boy oranı korunur, kırpma/döndürme yok (sol yarısı siyah sentetik sayfada piksel konumu doğrulandı), Inbox orijinalinin SHA-256'sı değişmez; JPEG `cache/pages/<file_id>/0000.jpg` altına atomik yazılır; PDF olmayan (JPEG/PNG baytlarını MuPDF'in PDF diye açmasına karşı imza denetimi), bozuk, sayfasız ve parolalı dosya `RenderError` ile reddedilir; `render_upload_file` `pages` satırlarını (yeniden çalıştırmada aynı satırlar, diğer alanlar korunur) ve `page_count`'u yazar, sayfa başına `PAGE_RENDERED` olayı (`image_path`/`width`/`height`/`dpi`) atar; durum sorgusu render sonrası `page_count` ve `rendered_files`'ı görür. Ayarlar ve gerekçe: C10 — `app/pipeline/render.py` · `app/storage/layout.py` (`page_image_path`, `resolve`) · `app/config.py` · `.env.example` · `pyproject.toml` (pymupdf) · test `tests/pipeline/test_render.py` (18 fonksiyon / 30 durum) · `tests/storage/test_layout.py` (+3) · `tests/test_config.py` (+2) · `tests/web/test_uploads.py` (+1) · tm 13

#### K02.2 — 02.2.1 · PDF metin katmanı çıkarma
- ✅ `extract_page_text`/`extract_pdf_text`/`extract_upload_file_text` (`app/pipeline/render.py`) — PyMuPDF `page.get_text()` ile sayfanın gömülü metin katmanı okunur (OCR yapılmaz, içerik üretilmez, K11); yalnız boşluktan ibaret/boş sonuç `text_layer`'ı `None` bırakır, taranmış (metin katmansız) sayfa böylece boş kalır. `render_pdf_pages`'in PDF açma/doğrulama mantığı (`_open_pdf`) iki fonksiyon arasında paylaşılacak şekilde ortak bir yardımcıya çıkarıldı, davranış ve hata mesajları değişmedi. `extract_upload_file_text` var olan `Page` satırını günceller (render'da oluşturulmuşsa), yoksa açar; yalnız `text_layer`'a dokunur, `image_path`/`page_count` gibi render'a ait alanları değiştirmez — `render_upload_file`'ın "diğer alanlara dokunulmaz" sözleşmesiyle simetrik. PRD §8.3'ün kapalı olay listesinde metin katmanı için ayrı bir olay türü yok; bu adım yeni olay atmıyor (bkz. §D). Oturum commit edilmez, çağıran sınırı belirler — `app/pipeline/render.py` · test `tests/pipeline/test_render.py` (+8 fonksiyon) · `tests/fixtures/gen.py` (`make_text_pdf_bytes`) · tm 14

#### K02.3 — 02.3.1 · Görüntü dosyaları için analiz kopyası
- ✅ `render_image_copy`/`render_image_file` (`app/pipeline/render.py`) — JPEG/PNG içeriği Pillow ile açılır, `ImageOps.exif_transpose` yalnız EXIF `Orientation` etiketini fiziksel olarak uygular (K11'in izin verdiği tek Pillow kullanımı: EXIF; kırpma/kontrast/boyutlandırma yok), kopya kaynağın kendi biçiminde (`jpg`/`png`, format dönüşümü yok) `cache/pages/<file_id>/0000.<uzantı>` altına atomik yazılır; sentetik 180°/90° EXIF etiketli görüntülerle piksel konumu doğrulandı (`tests/fixtures/gen.py::make_half_filled_image_bytes`). Inbox orijinaline dokunulmaz (SHA-256 testle doğrulandı, K10). PDF/desteklenmeyen içerik `RenderError` ile reddedilir. `render_image_file` tek sayfalık (index 0) `Page` satırını (yeniden çalıştırmada aynı satır, diğer alanlar korunur) ve `page_count=1`'i yazar, `PAGE_RENDERED` olayı (`image_path`/`width`/`height`) atar — 02.1'in PDF render'ıyla aynı olay türü ve alan sözleşmesi. `DataLayout.page_image_path`'e geriye dönük uyumlu `extension` parametresi eklendi (yol kuralı, MASTER-PROMPT §4 — biçim uzantısı da tek yerde üretilir); `RenderedPage.dpi` görüntü kopyalarında ölçek kavramı olmadığı için opsiyonel oldu — `app/pipeline/render.py` · `app/storage/layout.py` (`page_image_path`) · `pyproject.toml` (pillow) · test `tests/pipeline/test_render.py` (+8 fonksiyon/9 durum) · `tests/storage/test_layout.py` (+1) · `tests/fixtures/gen.py` (`make_half_filled_image_bytes`) · tm 15

#### K02.4 — 02.4.1 · Boş sayfa tespiti
- ✅ `is_page_blank`/`detect_pdf_blank_pages`/`mark_upload_file_blank_pages` (`app/pipeline/render.py`) — sayfa yalnız metin katmanı, gömülü görüntü ve çizimin üçü de yoksa boş sayılır (PDF'in kendi içerik nesnelerine bakar, OCR/piksel analizi yapılmaz — K11); taranmış (metinsiz) ama gömülü görüntü taşıyan sayfa boş SAYILMAZ. `mark_upload_file_blank_pages` var olan `Page` satırını günceller (yoksa açar), yalnız `is_blank`'e dokunur — `image_path`/`text_layer` render/metin adımlarının alanı, `extract_upload_file_text`'in sözleşmesiyle simetrik. Boş bulunan her sayfa için `PAGE_BLANK` olayı yazılır (K15); hata sayılmaz — `RenderError` yalnız dosya PDF değilse/bozuksa/parolalıysa fırlar, boş sayfa bunlardan biri değildir. Analizciye gönderilmemesi (kabul kriterinin ikinci yarısı) bu alanı okuyacak orkestrasyonun (09.x) işi, burada henüz bağlanmadı. Oturum commit edilmez — `app/pipeline/render.py` · test `tests/pipeline/test_render.py` (+9 fonksiyon) · tm 16

#### K02.5 — 02.5.1 · Gömülü tek görüntü tespiti
- ✅ `single_full_page_image_xref`/`detect_pdf_single_image_pages`/`mark_upload_file_single_image_pages` (`app/pipeline/render.py`) — sayfa MuPDF kayıt aygıtıyla (`_PaintRecorder`) çalıştırılır; tam bir görüntü çizimi, başka görünür komut yok, döndürme/aynalama/alfa yok, sayfa kutusunu 1 pt toleransla birebir kaplıyor, kırpma yalnız sayfayı kaplayan dikdörtgen, tek görüntü nesnesi ve maske/`Decode` anahtarı yoksa görüntünün `xref`'i döner, aksi halde işaret verilmez (ölçüt ve gerekçe: C11). İşaretli sayfanın xref'inden `extract_image` orijinal JPEG baytlarını birebir veriyor (testte doğrulandı — §20.5 girdisi). 8 olumlu (JPEG/PNG tam sayfa, görünmez OCR metni, sayfayı kaplayan kırpma, sayfa saydamlık grubu, tolerans içi kenar, kırpma kutusuna oturan görüntü, Pillow PDF çıktısı) ve 23 olumsuz sentetik durumun her biri hedeflenen kuralla reddedildi (boş/metin/çizim, küçük/kenar boşluklu görüntü, görünür metin, çizim, iki görüntü, kullanılmayan ikinci kaynak, aynı görüntü iki kez, açıklama notu, 90° ve aynalı yerleştirme, `/Rotate`, alfa kanallı PNG, `Decode`, renk anahtarı maskesi, dar ve dikdörtgen olmayan kırpma, yarı saydam çizim, Multiply karışımı, satır içi görüntü, kırpma kutusundan taşan görüntü). `mark_upload_file_single_image_pages` yalnız `pages.has_single_embedded_image`'e dokunur (render/metin/boş sayfa alanları değişmez), var olan satırı günceller; PRD §8.3'te tür olmadığı için olay yazmaz (§D6). Göç yok (sütun 00.3'te vardı). Oturum commit edilmez — `app/pipeline/render.py` · test `tests/pipeline/test_render.py` (+7 fonksiyon / 38 durum) · tm 17

#### K03.1 — 03.1.1–03.1.4 · Sayfa analizi şeması
- ✅ §8.4 pydantic sözleşmesi (`PageAnalysis`/`PagePerson`/`PageContact`/`FieldReading`, `extra="forbid"`, dondurulmuş) ve yanıt kabul girişi `validate_page_analysis(data, known_slugs=…)` — JSON metni, bayt veya çözülmüş nesne alır; §8.4 örneği harfiyen kabul edilir, şema anahtarları örneğin anahtarlarıyla birebir aynıdır; eksik/tanımsız anahtar, tip zorlaması (`"false"`, `"0"`, `True` sayı), negatif `page_index`, tanımsız `side`, geçersiz tarih (`12.04.1990`, `1990-02-30`, Unix zaman damgası, `datetime`), JSON olmayan/nesne olmayan yanıt `PageAnalysisError` ile her ihlal konumuyla reddedilir, mesajda kişisel değer yok; katalogda olmayan `document_type_slug` (tohum kataloğuna karşı) ve slug ile birlikte dolu `candidate_type_name` reddedilir, saklanan `analysis_json` katalogsuz geri okunur; `legible: true` ⇔ `value` dolu; JSON şeması tüm anahtarları `required`, kapalı kümeleri `enum` olarak verir (03.2 yapılandırılmış çıktı girdisi). Kurallar: C12 — `app/ai/schemas.py` · `app/ai/__init__.py` · test `tests/ai/test_schemas.py` (45 fonksiyon / 165 durum) · tm 18
- ✅ 03.1.2 `language` ISO 639-1 kayıt kümesi (183 kod, küçük harf; `xx`/`RU`/`rus`/`ru-RU`/kaldırılmış `sh`/`iw` reddedilir), `script` `latin`·`cyrillic`·`arabic`·`other` (`greek`/`Latin` reddedilir); metinsiz sayfada ikisi `null` olabilir, anahtar yine zorunlu — `app/ai/schemas.py` · test `tests/ai/test_schemas.py` · tm 18
- ✅ 03.1.3 `person.other_names` `given_names`'ten ayrı döner; `PagePerson.employee_fields()` alanları `employees` sütun adlarıdır ve geçici SQLite'ta `Employee` kaydına yazılıp geri okunduğunda `other_names`/`original_script_name`/`date_of_birth`/`nationality` korunur — `app/ai/schemas.py` · test `tests/ai/test_schemas.py` · tm 18
- ✅ 03.1.4 `person.contact` `phone`/`email`/`address` belgede yazılıysa döner, yoksa `null` (anahtar zorunlu, `contact: null` veya boş metin reddedilir); alan adları `ContactKind` değerleriyle birebir aynı (05.8.1 doğrudan eşler) — `app/ai/schemas.py` · test `tests/ai/test_schemas.py` · tm 18

#### K03.2 — 03.2.1–03.2.2 · Sağlayıcı soyutlaması ve Anthropic sağlayıcı
- ✅ 03.2.1 sağlayıcıdan bağımsız istek/yanıt sözleşmesi (`PageAnalysisRequest`, `PageImage`, `AnalysisProvider.analyze_page` — ortak ve atlanamaz yanıt kabulü: §8.4 şeması, istek kataloğu, `page_index` eşitliği), hata aileleri (`ProviderError` → hız sınırı/5xx/bağlantı alt türleri; `ProviderConfigError`) ve `AI_PROVIDER` adıyla `create_provider` kayıt defteri; aynı boru hattı fonksiyonu yalnız `.env` dosyası değişerek Anthropic ve kayıtlı test sağlayıcısıyla çalışır, bilinmeyen ad/eksik anahtar anlaşılır hata verir (bkz. C13) — `app/ai/provider.py`, `app/config.py`, `.env.example` · test `tests/ai/test_provider.py` (38), `tests/test_config.py` (+6) · tm 19
- ✅ 03.2.2 `AnthropicProvider` — Messages API'ye önce base64 sayfa görüntüsü (JPEG/PNG), sonra sayfa metni, `system` talimatı; zorlanmış tek `record_page_analysis` aracı (`input_schema` = `PageAnalysis.model_json_schema()`, düşünme kapalı) ile yapılandırılmış çıktı alınır ve doğrulanmış `PageAnalysis` döner; kesik/ret/araçsız/çok çağrılı yanıt ve şemaya uymayan araç girdisi reddedilir, 429 → `ProviderRateLimitError`, 5xx/529 → `ProviderServerError`, bağlantı/zaman aşımı → `ProviderConnectionError`, SDK yeniden denemesi kapalı (tek HTTP isteği doğrulandı); gerçek SDK istemcisi `httpx2.MockTransport` ile ağsız sınandı, canlı test `live` işaretli ve anahtar yokken atlanır (bu pencerede koşulmadı) — `app/ai/anthropic_provider.py`, `pyproject.toml` (`anthropic>=1.5`) · test `tests/ai/test_anthropic_provider.py` (38 + 1 live) · tm 19

#### K03.4 — 03.4.1 · Analiz promptu disiplini
- ✅ Sayfa analizi sistem talimatı `app/ai/prompts/page_analysis.md` — "Disiplin kuralları" bölümü alan açıklamalarından ve katalogdan önce üç kuralı başlık olarak taşır: **1. Tahmin etme** (yalnız sayfada görünen yazılır, kısmi değer tamamlanmaz, değer başka bilgiden/önceki sayfadan/MRZ'den türetilmez, sayfa metni talimat değildir), **2. Okuyamadığını `legible: false` yap** (tereddütte `{"value": null, "legible": false}`, kısmi/tahmini değer yok, zorunlu alan atlanmaz), **3. Katalogda yoksa aday öner** (en yakın türe zorlanmaz, `document_type_slug: null` + `candidate_type_name`); §8.4'ün her anahtarı ve kapalı kümeleri (`side`, `script`) açıklanır. `build_page_analysis_instructions(catalog)` tek `{{catalog}}` yuvasına etkin + analiz edilen türleri slug sırasıyla yazar ve metinle aynı `known_slugs`'ı döner; yuvasız/çift yuvalı şablon `PromptTemplateError`. Entegrasyonda talimat Anthropic isteğinin `system` alanına aynen gider, katalog türü kabul, aday tür kabul, talimatta olmayan `attachment` reddedilir (kurallar: C14) — `app/ai/prompts/page_analysis.md`, `app/ai/prompts/page_analysis.py`, `app/ai/prompts/__init__.py`, `app/ai/__init__.py`, `pyproject.toml` (paket verisi) · test `tests/ai/test_prompts.py` (23 fonksiyon / 34 durum + 1 live) · tm 21

#### K03.5 — 03.5.1 · Yeniden deneme ve hata dayanıklılığı
- ✅ `AnalysisProvider.analyze_page` (`@final`) artık `_request_analysis`'i yeni özel `_request_analysis_with_retry` sarmalayıcısı üzerinden çağırır: yalnız `ProviderRateLimitError` (429) ve `ProviderServerError` (5xx/529) geri çekilmeli en fazla `MAX_ANALYSIS_ATTEMPTS = 3` deneme yapılır (ilk deneme + iki yeniden deneme), her başarısız denemeden sonra `time.sleep(RETRY_BACKOFF_SECONDS * 2 ** (deneme - 1))` beklenir (1 sn, 2 sn — üstel); son denemede de başarısız olursa yakalanan hata aynı nesneyle yeniden yükselir. `ProviderConnectionError`, taban `ProviderError` (diğer 4xx) ve `PageAnalysisError` yeniden denenmez, ilk denemede yükselir (karar: C15). Somut sağlayıcılar değişmedi, hâlâ tek HTTP isteği atar. Anthropic entegrasyonunda hız sınırı/5xx'in tüm alt durumları (429/500/503/504/529) hem "ikinci denemede kurtarma" hem "üç denemede pes etme" senaryolarıyla, 4xx'in kalanı (400/401/403/404/413) tek denemeyle doğrulandı; `httpx2.MockTransport` sıralı yanıt kuyruğu kullanıldı, ağ çağrısı yok. Testte `time.sleep` `tests/ai/conftest.py`'deki `no_sleep` fixture'ıyla (`app.ai.provider.time.sleep` monkeypatch) kaydedilir, gerçekten beklenmez — `app/ai/provider.py` · test `tests/ai/test_provider.py` (44, +6), `tests/ai/test_anthropic_provider.py` (44, +5), `tests/ai/conftest.py` (yeni) · tm 22

#### K03.6 — 03.6.1 · Kayıtlı yanıt sağlayıcısı (test altyapısı)
- ✅ `RecordingProvider` (`app/ai/recording_provider.py`) — `AnalysisProvider`'ı ağsız uygular: `_request_analysis` `tests/fixtures/ai/recordings/<senaryo>/<sıra>.json` dosyasını (`0.json`, `1.json`, ...) ayrıştırmadan okuyup döner, ortak `validate_page_analysis` yanıtı doğrular. `from_directory` dosya adına göre sıralı yükler; kayıttan fazla istek `RecordingExhaustedError`, boş/yok dizin `RecordingNotFoundError`. `PROVIDER_FACTORIES`'e eklenmedi (C16) — test doğrudan `RecordingProvider.from_directory(...)` çağırır. İki sentetik kayıt: `russian_passport/0.json` (tek sayfa), `serbian_residence_card/{0,1}.json` (ön/arka). Kurallar ve gerekçe: C16 — `app/ai/recording_provider.py` · `tests/fixtures/ai/recordings/russian_passport/0.json` · `tests/fixtures/ai/recordings/serbian_residence_card/{0,1}.json` · test `tests/ai/test_recording_provider.py` (8 fonksiyon) · tm 23

#### K03.7 — 03.7.1–03.7.2 · Sayfa analizi çalıştırıcı
- ✅ 03.7.1 `analyze_upload` (`app/pipeline/analyze.py`) partinin sayfalarını dosya (`upload_files.id`) ve sayfa (`pages.index`) sırasıyla tek tek `AnalysisProvider.analyze_page`'e verir; istek önbellekteki sayfa görüntüsünü, 03.4 talimatını + `known_slugs`'ı ve `build_page_prompt` metnini (sayfa sırası, aynı dosyada analize gönderilen önceki sayfanın özeti, varsa PDF metin katmanı) taşır. Özet (`summarize_page_analysis`) önceki sayfanın doğrulanmış analizinden deterministik üretilir, kişisel değer taşımaz (ad/numara/doğum tarihi/orijinal yazım/adres/MRZ/not önceki sayfanın özetinde ve olaylarda geçmiyor — testle doğrulandı), dosya sınırında sıfırlanır; ilk sayfada "yok", önceki sayfa başarısızsa "analizi başarısız" yazılır. Boş sayfa ve tekrar dosyası analize gitmez (`skipped`), boş sayfa özet zincirini kırmaz. Başarılı sayfa `analysis_json` + `done` + `PAGE_ANALYZED`, okunamayan sayfa ayrıca `PAGE_UNREADABLE`. Kayıtlı sağlayıcıyla (sentetik PDF/JPEG/PNG, gerçek render adımları) çok dosyalı sıra, talimat/görüntü/metin katmanı, ön/arka kayıtlarıyla özet akışı doğrulandı (kurallar: C17) — `app/pipeline/analyze.py` · test `tests/pipeline/test_analyze.py` (23) · tm 24
- ✅ 03.7.2 Sayfa hatası (`PageAnalysisError` şemaya uymayan kayıt, 3 denemeden sonra `ProviderServerError`, `ProviderConnectionError`, eksik/üretilmemiş/geçersiz sayfa görüntüsü) yalnız o sayfayı `failed` yapar (`analysis_json` boşaltılır, `PAGE_ANALYSIS_FAILED` sağlayıcı/model/hata türü/HTTP durumuyla), kalan sayfalar tamamlanır ve parti `partial` olur; tüm sayfalar başarılıysa parti durumu değişmez; beklenmeyen hata (`RecordingExhaustedError`) yutulmaz, parti `partial` işaretlenmez (09.2.3'e kalır) — `app/pipeline/analyze.py` · test `tests/pipeline/test_analyze.py` · tm 24

#### K04.1 — 04.1.1, 04.1.2 · Dosya içi gruplama ve ön/arka eşleşmesi
- ✅ 04.1.1 `group_file_pages`/`group_upload` (`app/pipeline/group.py`) dosyanın analiz edilmiş sayfalarını sırayla belge adaylarına ayırır: sayfa açık adaya yalnız ardışıksa (araya yalnız 02.4 boş sayfası girebilir; analizi başarısız/yapılmamış ve analizcinin boş dediği sayfa zinciri kırar, aday olmaz), `continues_previous_page` doğruysa, türü aynıysa (slug ya da normalize aday tür adı) ve iki sayfada da yazılı kimlik değeri (normalize belge numarası, doğum tarihi, soyad/ad/orijinal yazım kelime kümesi) çelişmiyorsa katılır; aynı kişinin devam etmeyen iki pasaportu, farklı tür, çelişen kişi (6 durum) ve belirlenemeyen tür ayrı aday kalır, yalnız yazım farkı (boşluk/tire/nokta, aksan, `ı`, kelime sırası, eksik ikinci ad, Kiril harf büyüklüğü — 8 durum) bölmez, beklenen sayfa sayısında bölünmez; `group_upload` tekrar dosyasını atlar, boş/başarısız/analizsiz sayfaları ayrı listeler, aday başına kişisel değer taşımayan `DOC_TYPE_DETERMINED`/`DOC_TYPE_UNKNOWN` yazar, şemaya uymayan saklı analizde değersiz `StoredAnalysisError` verir (kurallar: C18). 5 kural bozulması (devam işareti, yüz yapısı, kişi çelişkisi, boş okuma, normalizasyon) bellekte ayrı ayrı denendi, her biri testte kırmızı — `app/pipeline/group.py` · test `tests/pipeline/test_group.py` (31 fonksiyon / 55 durum) · tm 25
- ✅ 04.1.2 katalogda `front_back` türde ön yüz ve onu izleyen arka yüz sırayla tek adayda eşleşir (`sides` `(front, back)`, ehliyet ve oturum izni); araya giren boş sayfa eşleşmeyi bozmaz, `F B F B` iki çift olur; `B F`, devam etmeyen arka, tamamlanmış çifte üçüncü sayfa, `single`/`unknown` yüz ve başka numaralı arka eşleşmez, `F F B` → `[F] [F B]` — `app/pipeline/group.py` · test `tests/pipeline/test_group.py` · tm 25
- ✅ S4: 5 sayfalık sentetik PDF (ehliyet ön, ehliyet arka, foto, oturum ön, oturum arka) gerçek render/metin/boş sayfa adımlarından ve yeni kayıtlı yanıtlarla `analyze_upload`'dan geçip `group_upload` ile üç bağımsız aday verir — `serbian_driving_license` [0, 1] (front, back), `profile_picture` [2], `serbian_residence_card` [3, 4] (front, back); üç `DOC_TYPE_DETERMINED` olayında kişisel değer yok — `tests/fixtures/ai/recordings/s4_sequential_pdf/{0..4}.json` · test `tests/pipeline/test_group.py` · tm 25

#### K04.2 — 04.2.1 · Ardışıklık güvenlik kuralı (R6)
- ✅ 04.2.1 `group_file_pages` (`app/pipeline/group.py`) aynı dosyada aynı belgenin parçası olabilen ve arasına başka belge girmiş adayları birleştirmeden `DocumentCandidate.contiguity_violation` (`ContiguityViolation`, `rule = "R6"`, `queue = unresolved`, değer taşımayan `reason`) ile işaretler; parça çifti: aynı katalog türü, tek belgede birleşebilir yapı (`front_back`'te yalnız ön + yalnız arka, sıra fark etmez; tek yüzlüde toplam sayfa ≤ `expected_pages.max`), çelişmeyen kimlik ve arada başka aday ya da analizsiz sayfa; bitişik/yalnız boş sayfayla ayrılmış eksik parçalar, iki ön yüz, tamamlanmış çift, yüzü belirsiz sayfa, başka tür/kişi, sayfa sınırını aşan, 1 sayfalık, katalog dışı, türü belirsiz ve katalogda olmayan tür (15 durum) parça sayılmaz; birden çok karşı parça ve araya girenler (öteki parçalar hariç) listelenir; gerekçe kural + 1'den başlayan sayfa numaraları. Hüküm adayın `DOC_TYPE_DETERMINED` olayına `contiguity_violation` verisi ve `message = reason` olarak yazılır, kişisel değer yok (kurallar: C19). 10 kural bozulması (bitişik parça, analizsiz sayfa, kişi çelişkisi, yüz sırası, sayfa sınırı, işaretleme, karşı parçayı araya sayma, olay verisi, katalogda olmayan slug, katalog dışı tür) bellekte ayrı ayrı denendi, her biri testte kırmızı — `app/pipeline/group.py` · test `tests/pipeline/test_group.py` (44 fonksiyon / 85 durum, +13 / +30) · tm 26
- ✅ S3: 6 sayfalık sentetik PDF (ehliyet ön, foto, başka belge, oturum ön, oturum arka, ehliyet arka) gerçek render/metin/boş sayfa adımlarından ve yeni kayıtlı yanıtlarla `analyze_upload` → `group_upload`: adaylar (0'dan sıra) [0] [1] [2] [3, 4] [5]; oturum izni [3, 4] (front, back) ve foto [1] işaretsiz, sayfa 3 ([2]) katalog türünde (`work_permit`) `DOC_TYPE_DETERMINED`, katalog dışı türde `DOC_TYPE_UNKNOWN` ile işaretsiz; ehliyet 1 ve 6 ([0], [5]) birleştirilmez, ikisi de R6 ile Unresolved (karşı parça birbirleri, araya giren [1, 2, 3, 4]) ve olay mesajı gerekçedir; ön ve arka yüz ayrı dosyalardaysa kural uygulanmaz (04.3) — `tests/fixtures/ai/recordings/s3_interleaved_pdf/{0..5}.json` · test `tests/pipeline/test_group.py` · tm 26

#### K04.3 — 04.3.1, 04.3.2 · Dosyalar arası gruplama ve belirsiz eşleştirmenin reddi
- ✅ 04.3.1 `group_across_files` (`app/pipeline/group.py`, `group_upload` üzerinden) katalogda `front_back` ve `direct: false` türde partinin ayrı dosyalarındaki eksik ön ve arka yüzü tek `DocumentCandidate`'e (önce ön, sonra arka; `UploadGrouping.cross_file_candidates`, yüzler dosya adaylarından çıkar) eşleştirir; eşleşme tek anlamlıysa yapılır: türün partide tek eksik ön ve tek eksik arka yüzü, ikisi R6 işaretsiz ve ayrı dosyada, kimlik çelişmiyor, partide başka yüz olabilecek sayfa (türün `single`/`unknown` yüzlü sayfası, analizsiz sayfa, katalog türü verilmemiş ve tek yüzlü okunmamış sayfa) yok. Yükleme sırası fark etmez (ehliyet ve oturum izni, iki yönde); çok sayfalı dosyanın içindeki yüz eşleşir, öteki adaylar yerinde kalır; aynı dosyadaki yüzler (bitişik, ters), Direkt Belge (`direct: true`), tek yüzlü tür (ön/arka okunmuş dahil), farklı tür, katalog dışı, türü belirsiz, yüzü belirsiz, yalnız ön yüzler ve kimliği çelişen yüzler eşleşmez ve hüküm almaz; tamamlanmış çift, başka katalog türleri, tek yüzlü katalog dışı belge ve boş sayfalar eşleşmeyi engellemez; türler birbirinden bağımsız eşleşir; dosya gruplamaları `file_id` sırasına dizilir, tekrar eden dosya reddedilir. Olay: dosyalar arası aday `DOC_TYPE_DETERMINED`'ı ön yüzün dosyası/sayfasıyla ve `sources` (`[{file_id, pages}]`) verisiyle yazar, kişisel değer yok (kurallar: C20) — `app/pipeline/group.py` · test `tests/pipeline/test_group.py` (67 fonksiyon / 132 durum, +23 / +47) · tm 27
- ✅ 04.3.2 eşleşebilecek yüz çifti varken türün birden fazla eksik ön yüzü (aynı ya da farklı kişi), birden fazla eksik arka yüzü veya başka yüz olabilecek sayfa varsa eşleştirme yapılmaz; türün R6 işaretsiz bütün eksik yüzleri `DocumentCandidate.ambiguous_pairing` (`AmbiguousPairing`: `face`, `fronts`, `backs`, `unoriented_pages`, `unanalyzed_pages`, `uncertain_type_pages`; `queue = unresolved`, dosya kimliği ve 1'den sayfa numarasıyla değersiz `reason`) ile Unresolved'a gider (iki kart, bir ön iki arka, aynı dosyada iki ön yüz, aynı dosyada eşleşmemiş arka yüz, 7 engel durumu, katalogda olmayan slug); R6 parçası eşleşmez, yalnız kendi hükmünü taşır ama eksik yüz olarak sayılır; bir türün belirsizliği öteki türün eşleşmesini durdurmaz. Hüküm adayın `DOC_TYPE_DETERMINED` olayına `ambiguous_pairing` verisi ve `message = reason` olarak yazılır. Entegrasyon: iki kişinin ehliyet ön yüzü + tek arka yüz (üç JPEG) → üç yüz de gerekçesiyle Unresolved, olaylarda kişisel değer yok; analizi başarısız fotoğraflı partide (`partial`) ön/arka yüz eşleşmez, gerekçe analizsiz sayfayı listeler. 23 kural bozulması (Direkt Belge, tek yüzlü tür, ayrı dosya şartı, R6 parçasını saymama, R6 parçasını eşleştirme, tamamlanmış çifti sayma, kimlik çelişkisi, üç engel türü, tek yüzlü katalog dışı belgeyi engel sayma, katalogda olmayan slug, yalnız ön yüz çokluğu, yüz sırası, eşleşebilecek çift şartı, olay `sources`/verisi/mesajı/dosyası, R6 parçasına belirsizlik hükmü, dosya sırası, tekrar dosya, eşleşen yüzün dosyada kalması) bellekte ayrı ayrı denendi, her biri testte kırmızı — `app/pipeline/group.py` · test `tests/pipeline/test_group.py` · tm 27
- ✅ S5: aynı partide `on.jpg` (ehliyet ön) ve `arka.jpg` (ehliyet arka) sentetik JPEG, gerçek görüntü analiz kopyası adımından ve yeni kayıtlı yanıtlarla `analyze_upload` → `group_upload`: iki yükleme sırasında da tek `serbian_driving_license` adayı (Driving License, `direct: false`) — sayfalar (on.jpg, 0) front, (arka.jpg, 0) back; dosya adaylarında yüz kalmaz, tek `DOC_TYPE_DETERMINED` olayı ön yüzün dosyasına `sources` ile yazılır, kişisel değer yok. Kayıpsız sarma ve birleştirme (çıktı PDF) 06.2/07.3/07.4'ün işi — `tests/fixtures/ai/recordings/s5_front_back_images/{0,1}.json` · test `tests/pipeline/test_group.py` · tm 27

#### K04.4 — 04.4.1, 04.4.2 · Zorunlu alan okunaklılık kapısı ve kabul kriteri değerlendirmesi
- ✅ 04.4.1 `check_legibility` (`app/pipeline/legibility.py`) katalog türündeki adayın zorunlu alanlarını sayfaları üzerinden birleştirir (alan bir sayfada okunaklıysa okunaklı; ön/arka yüz ve dosyalar arası aday dahil); hiçbir sayfada okunaklı olmayan ya da hiç yazılmamış alan varsa `IllegibleRequiredFields` (`rule = "R1"`, `queue = unreadable`) ve gerekçe `Okunamayan alanlar: <alanlar>` katalog sırasıyla; türün dışındaki alanlar, zorunlu alanı olmayan türde `is_readable` rota vermez; kendi yanıtı okunamaz/boş diyen sayfanın okunaklı alanına güvenilmez; aday tür adlı, türü belirlenemeyen ve slug'ı katalogda olmayan aday değerlendirilmez (`None`); zorunlu alanlar güncel katalogdan okunur (kurallar: C21) — `app/pipeline/legibility.py` · test `tests/pipeline/test_legibility.py` (32 fonksiyon / 55 durum) · tm 28
- ✅ 04.4.2 türün `acceptance_criteria` maddelerinin her biri adayın sayfa notlarında aranır: analizcinin katalog metniyle yazdığı madde (harf büyüklüğü, aksan, noktalama, boşluk farkı yok sayılarak kelime dizisi) `UnmetAcceptanceCriteria` (`queue = unresolved`) ve gerekçe `Karşılanmayan kabul kriterleri: "<madde>"` katalog sırasıyla; başka sözcüklerle/eksik/ek almış/farklı sırayla yazılan, iki sayfanın notuna bölünen ve daha uzun maddenin içinde kalan madde sayılmaz, örtüşen maddeler ikisi de sayılır, kelimesiz madde alıntılanamaz; liste boşsa tek ölçüt R1; iki ölçüt de sağlanmıyorsa kuyruk Unreadable, iki hüküm de nesnede. Analiz talimatının `notes` açıklaması karşılanmayan maddeyi `Karşılanmayan kabul kriteri: <madde>` biçiminde kelimesi kelimesine yazdırır; talimattaki biçim karar motorunda tanınıyor (testte talimattan okunarak). Modül olay yazmaz (entegrasyonda olay sayısı değişmiyor). 19 kural bozulması (güvenilmeyen/boş sayfa okuması, birleştirme, katalog sırası, öncelik, kapsama iki biçimde, `ı`/aksan/noktalama normalizasyonu, tekilleştirme, kelimesiz madde, tek satır, uzun madde önceliği, sayfa notlarını birleştirme, iki gerekçe metni, kriteri yok sayma, katalogsuz yargı) bellekte ayrı ayrı denendi, her biri testte kırmızı — `app/pipeline/legibility.py` · `app/ai/prompts/page_analysis.md` · test `tests/pipeline/test_legibility.py` · `tests/ai/test_prompts.py` (+1) · tm 28
- ✅ S9: tek sayfalık sentetik PDF gerçek render/metin/boş sayfa adımlarından ve yeni kayıtlı yanıtla (belge numarası `legible: false`, MRZ okunamıyor ve MRZ maddesi notta) `analyze_upload` → `group_upload` → `check_legibility`: `russian_passport` adayı Unreadable, gerekçe tam olarak `Okunamayan alanlar: document_number`; MRZ kabul kriteri ayrıca karşılanmamış olarak nesnede; gerekçelerde kişisel değer yok. Kayıtlı pasaport yanıtı kenar maddesiyle Unresolved, notsuz kabul; S5 dosyalar arası ehliyet kartı ön yüzdeki okumalarla kabul — `tests/fixtures/ai/recordings/s9_blurred_passport/0.json` · test `tests/pipeline/test_legibility.py` · tm 28

#### K04.5 — 04.5.1 · Beklenen sayfa sayısı kontrolü
- ✅ 04.5.1 dosya içi ve dosyalar arası gruplama bittikten sonra `group_across_files` (`app/pipeline/group.py`, `group_upload` üzerinden) başka bir kuralla (04.2.1/04.3.2) zaten işaretlenmemiş ve katalogda türü belirlenmiş her adayın sayfa sayısını türün `expected_pages` aralığıyla karşılaştırır; dışındaysa `DocumentCandidate.page_count_violation` (`PageCountViolation`: `queue = unresolved`, sayfalar + beklenen aralık, değer taşımayan `reason`) ile Unresolved'a gider — eşleşebilecek karşı yüzü partide hiç olmayan tek ön/arka yüz (04.3.2'nin hüküm vermediği durum) ve bitişik ama araya belge girmemiş eksik parçalar burada yakalanır; aralık tanımsız (`expected_pages: null`), katalog dışı/türü belirlenemeyen aday ya da zaten R6/04.3.2 ile işaretli aday yargılanmaz (iki gerekçe eklenmez). Hüküm adayın `DOC_TYPE_DETERMINED` olayına `page_count_violation` verisi ve `message = reason` olarak yazılır, kişisel değer yok. `group_file_pages` tek başına sayfa sayısıyla bölmez (04.1.2 notu); sınır yalnız `group_across_files`/`group_upload` çıktısında uygulanır — `app/pipeline/group.py` · test `tests/pipeline/test_group.py` (78 fonksiyon / 145 durum, +11 / +13) · tm 29

#### K04.6 — 04.6.1 · Bilinmeyen tür ve aday tür önerisi
- ✅ 04.6.1 `group_file_pages` (`app/pipeline/group.py`, `group_upload` üzerinden) güncel katalogda türü olmayan her adayı (aday tür adlı, türü belirlenemeyen, slug'ı katalogdan kalkmış) `DocumentCandidate.unknown_type` (`UnknownDocumentType`: `queue = unknown`, değer taşımayan `reason`) ile Unknown'a gönderir; aday katalog türüne zorla atanmaz (katalog türünün adı ya da slug'ı gibi yazılmış aday adı da eşlenmez, slug boş kalır) ve R6/04.3.2/04.5 hükümleri ona verilmez. `group_upload` aday tür adını `record_candidate_type_sighting` (`app/db/models.py`) ile `candidate_document_types`'a yazar: harf büyüklüğü/boşluk farkı yok sayılan tek kayıt (`normalize_candidate_type_name`), `pending`, ilk parti, adayın ilk sayfası `sample_page_ids`'te, `seen_count`; aynı sayfa ikinci kez sayılmaz, yeniden görülme durumu (reddedilmiş/onaylanmış) değiştirmez, eşzamanlı 20 görülme SQLite'ta tek kayıt ve doğru sayı verir. Hüküm `DOC_TYPE_UNKNOWN` olayına `unknown_type` verisi (`queue`, `candidate_type_id`) ve `message = reason` olarak, sayılan görülme ardından `CANDIDATE_TYPE_PROPOSED` olarak yazılır; kişisel değer yok (bkz. C22) — `app/pipeline/group.py`, `app/db/models.py` · test `tests/pipeline/test_group.py` (90 fonksiyon / 162 durum, +12 / +17), `tests/db/test_candidate_types.py` (15; PostgreSQL eşzamanlılık durumu ortam değişkeni yokken atlanır) · tm 30
- ✅ S14: tek sayfalık sentetik PDF gerçek render/metin/boş sayfa adımlarından ve yeni kayıtlı yanıtla (Peru diploması: slug `null`, `candidate_type_name: "Peruvian Diploma"`) `analyze_upload` → `group_upload`: aday Unknown (slug boş, gerekçede önerilen aday tür), `candidate_document_types`'ta `Peruvian Diploma` (`pending`, `seen_count` 1, örnek sayfa diplomanın sayfası), `DOC_TYPE_UNKNOWN` ardından `CANDIDATE_TYPE_PROPOSED`, `DOC_TYPE_DETERMINED` yok; aynı parti yeniden gruplanınca sayı artmaz, başka partideki iki diploma (başka yazımla) aynı kayıtta 3'e çıkar; tür kataloğa eklenip sayfa yeniden analiz edilince (K18) aday `peruvian_diploma` ile `DOC_TYPE_DETERMINED` alır, Unknown'dan çıkar ve kayıt yeniden sayılmaz. Onay akışı (11.5.2) ve Hazir çıktısı (06–07) sonraki görevlerin — `tests/fixtures/ai/recordings/s14_peruvian_diploma/0.json` · test `tests/pipeline/test_group.py` · tm 30

#### K04.7 — 04.7.1 · Word/Excel (Attachment) yolu
- ✅ 04.7.1 `Catalog.unanalyzed_entry_for` (`app/catalog/schema.py`) `analyze: false` olan ve verilen içerik türünü (`FileType`) `expected_file_types`'ta taşıyan katalog kaydını döner (tohumda yalnız `attachment`). `group_upload` (`app/pipeline/group.py`) hiç sayfası olmayan her dosyayı (K2: Word/Excel render/analiz edilmez) `layout`taki gerçek içeriğinden `detect_file_kind` ile sınar; eşleşirse `AttachmentFile` üretir — sayfalara ayrılmaz, kişi eşleştirme/kabul kriteri değerlendirilmez, dönüştürülmez. Partinin `Upload.context_employee_id`'si doluysa `unresolved` boş kalır (olduğu gibi Hazir'a kaydedilecek şekilde işaretsiz; fiziksel kopyalama 07.x'in işi); boşsa `AttachmentWithoutContext` (`queue = unresolved`, değer taşımayan `reason`) doldurulur. Her iki durumda da dosyaya `DOC_TYPE_DETERMINED` yazılır (veri: `document_type_slug`, varsa `unresolved.queue`). Eşleşen `analyze: false` kayıt yoksa (desteklenmeyen içerik ya da katalogda `attachment` tanımsız) aday üretilmez — bu görevin kapsamı dışı. `group_upload` imzasına `layout: DataLayout` eklendi (16 mevcut çağıran güncellendi) — `app/pipeline/group.py`, `app/catalog/schema.py` · test `tests/pipeline/test_group.py` (+9 durum), `tests/pipeline/test_legibility.py` (imza güncellemesi) · tm 31
- ✅ S15: Word CV (`.docx`, gerçek OOXML imzası) bağlam çalışanıyla (profil sayfası benzeri yükleme, 10.5.3) yüklenince attachment aday `unresolved` boş kalır ve olduğu gibi Hazir'a hazır işaretlenir; bağlam çalışanı olmadan (genel yükleme) yüklenince `AttachmentWithoutContext` ile Unresolved'a gider. Legacy Word/Excel (OLE imzası) ve OOXML Excel de aynı `attachment` türüne eşlenir; sayfa tabanlı bir pasaport adayıyla aynı partide birlikte var olabilirler — `tests/fixtures/gen.py` (`make_docx_bytes`, `make_xlsx_bytes`, `make_legacy_doc_bytes`, `make_legacy_xls_bytes`) · test `tests/pipeline/test_group.py` · tm 31

#### K05.1 — 05.1.1 · İsim normalizasyonu
- ✅ 05.1.1 `normalize_name(*parts)` (`app/matching/names.py`) isim parçalarını §20.2.1 sırasıyla tek eşleştirme anahtarına indirir: Unicode uyumluluk katlaması (NFKD + casefold) ve `Mn`/`Me` işaretlerinin atılması (aksan), Türkçe harfler (`ç ş ğ ı ö ü`) ve ayrışmayan Latin harfleri (`ł ø æ đ þ`…) tabloyla, kesme işaretleri ve görünmez biçim karakterleri kelimeyi bölmeden silinir, diğer noktalama ve çoklu boşluk tek ayırıcı olur, kelimeler alfabetik sıralanıp tek boşlukla birleşir. `José Müller`/`JOSE MULLER`, `IŞIK`/`Işık`/`İŞIK`/`isik`, `O'Brien`/`O´Brien`/`OBRIEN`, `Jean-Pierre Dupont`/`DUPONT<<JEAN<PIERRE`, `Dmitry Vasiliev`/`VASILIEV, DMITRY` ve parça sırası (`("Dmitry", "Vasiliev")`) aynı anahtara iner; farklı isimler (`Yılmaz`/`Yılmazer`, `Ali Ali Veli`/`Ali Veli`, `Ana-Maria`/`Anamaria`) ayrı kalır, anahtar idempotenttir, kelimesiz isim `EmptyNameError` verir. Latin dışı harfler düşürülmez, çeviri 05.2'nin (bkz. C23). 11 kural bozulması (sıralama, Türkçe/Latin tablo, iki kesme işareti silme adımı, `Cf`, çift katlama, `combining` yerine kategori, casefold, boş anahtar, kelime tekrarı) geçici olarak denendi, her biri testte kırmızı — `app/matching/names.py` · test `tests/matching/test_names.py` (14 fonksiyon / 44 durum) · tm 32

#### K05.2 — 05.2.1 · Harf çevirisi
- ✅ 05.2.1 `transliterate_name(text, *, language=None)` (`app/matching/names.py`) Kiril yazımı ICAO Doc 9303 Bölüm 3 §6 Tablo B'yle (varsayılan sütun + `be`/`bg`/`mk`/`sr`/`uk` dil istisnaları, Ukraynaca kelime başı `YE YI Y YU YA`), Arap yazımı Tablo C'nin MRZ sütunuyla (hareke/tatvil yazılmaz, şedde ikiler, `ة` ad parçası sonunda `XAH`, sunum biçimleri açılır) Latin karşılığına çevirir ve `TransliteratedName(original, latin)` döner — `original` verilen metnin dokunulmamış hâli (NFD girdi bile olduğu gibi), dondurulmuş. `normalize_name(*parts, language=None)` çeviriyi aksan atmadan önce uygular: `Дмитрий Васильев`/`ВАСИЛЬЕВ ДМИТРИЙ`/`VASILEV DMITRII`/`VASILEV<<DMITRII` → `dmitrii vasilev`, `Микола Григоренко` (`uk`) = `HRYHORENKO MYKOLA`, `Живковић Чедомир` (`sr`) = `ŽIVKOVIĆ ČEDOMIR`, `محمد علي` = `علي مُحَمَد` = `ELY MXHMD`; dil yalnız Kiril harflerini etkiler, anahtar idempotent. Tablo dışı: `Ь` yazılmaz, `Ћ → C`, ayrışan harf temel harfiyle, diğerleri (`Қ`, Grekçe) olduğu gibi kalır (C24). PRD örneğinin ICAO dışı `Dmitry Vasiliev` yazımı ayrı anahtar kalır (D7). 05.1'in `مُحَمَّد == محمد` testi şedde kuralı gereği harekeli ama şeddesiz yazımla güncellendi. Bütün Rus alfabesi, Tablo B'nin diğer 16 satırı ve Tablo C'nin 80 satırı (78'i NFC ve NFD girdiyle tek tek; `ة` ve şedde kural testinde) doğrulanır. 17 kural bozulması (şedde, `XAH`, Ukraynaca kelime başı, `uk`/`sr` istisnası, `Ь`, `Ћ`, `Һ`, büyük harf kuralı, ayrışma yedeği, sunum biçimi, kesme işaretinin kelimeyi bölmemesi, harekenin saydamlığı, dilin harf büyüklüğü, katlamadan sonra çeviri, orijinalin NFC'lenmesi, tablo dışı harfin Latin'e indirilmesi) geçici olarak denendi, her biri testte kırmızı — `app/matching/names.py` · test `tests/matching/test_transliteration.py` (15 fonksiyon / 155 durum), `tests/matching/test_names.py` (14 / 44, 2 test güncellendi) · tm 33
- ✅ S13 (isim düzeyi): sentetik Kiril isimli Rus pasaportu kaydı (`Тестова-Щёлкина Юлья`, Latin alanlar ve MRZ ICAO yazımıyla) §8.4 yanıt kabul girişinden (`validate_page_analysis`) geçer; `transliterate_name` orijinali aynen saklar ve `Testova-Shchelkina Iulia` verir; Kiril orijinal, Latin alanlar, çeviri ve MRZ ad alanı aynı anahtara (`iulia shchelkina testova`) iner; Latin alanlardan, çevrilmiş Kiril parçalardan ve doğrudan Kiril parçalardan (00.4.2 slug) aynı Latin klasör adı `Iulia_Testova_Shchelkina_E0001` çıkar. Orijinal yazımın profile (profil.md, 09.1.2/09.1.3) ve `employee_aliases`'a (05.7.2) yazılması sonraki görevlerin — `tests/fixtures/ai/recordings/s13_cyrillic_name/0.json` · test `tests/matching/test_transliteration.py` · tm 33

#### K05.3 — 05.3.1, 05.3.2, 05.3.3 · MRZ ayrıştırma, kontrol haneleri ve MRZ önceliği
- ✅ 05.3.1 `parse_mrz(lines, *, today)` (`app/matching/mrz.py`) biçimi satır sayısı ve uzunluğundan belirler (TD1 3×30, TD2 2×36, TD3 2×44; uymayan satırlar `None`, hata değil), ASCII küçük harfi büyütür, `A-Z 0-9 <` dışında karakter kalırsa `InvalidMrzError` (mesajda satır numarası, değer yok) verir ve §20.1.3 konumlarından `Mrz` döner: belge kodu, veren devlet, soyad/verilen adlar (ilk `<<` ayırır, `<` kelime ayracı, `<<` yoksa yalnız soyad), belge numarası, uyruk (`D<<` → `D`), doğum, cinsiyet, son geçerlilik, isteğe bağlı veri (TD1'de iki alan). ICAO Doc 9303'ün kurgusal UTO örnekleri (TD3, TD2, TD1) alan alan okunur; testteki yazıcı alanları anlamlarıyla birleştirip bu üç örneği birebir üretir ve üç biçimde her alanı ileri-geri doğrular (kurallar: C25) — `app/matching/mrz.py` · test `tests/matching/test_mrz.py` · tm 34
- ✅ 05.3.2 `compute_check_digit` §20.1.4'ün üç zorunlu örneğini (`L898902C3` → 6, `690806` → 1, `940623` → 6) ve değer/ağırlık dizisini verir. Hanesi tutmayan alan yalnız kendisi okunamadı sayılır (`failed_checks`, `illegible_fields`, değer `None`), diğer alanlar kullanılır; bileşik hane tutmazsa değerler kalır ama `composite_valid` yanlış; tümüyle dolgu isteğe bağlı verinin hanesi `<` veya `0`. Her biçimde her konumdaki tek karakter bozulunca yalnız o konumu kapsayan hanelerin tutmadığı doğrulanır — §20.1.5'in bitişik olmayan aralıkları dahil (TD3 iki kez, TD2, TD1: 338 konum). Tarih: son geçerlilik her zaman `20YY`, doğum `20YY` gelecekteyse `19YY` (bugün gelecek değil; `000229` 1999 sonunda okunamadı); takvimde geçersiz ya da harfli tarih alanı okunamadı yapar, MRZ'yi reddetmez; rakamlı isim alanı, bozuk uyruk ve boş numara da okunamadı — `app/matching/mrz.py` · test `tests/matching/test_mrz.py` · tm 34
- ✅ 05.3.3 `apply_mrz_priority(analysis, *, today)` MRZ'nin altı alanını `person` ve `fields` okumalarıyla karşılaştırır: aynı anahtara inen görünen yazım olduğu gibi kalır (`00 0000001`, tireli/aksanlı isim, `other_names`'te ayrı okunmuş baba adı, sayfa diliyle çevrilen Ukraynaca Kiril ad); çelişkide MRZ değeri iki yere de yazılır ve `notes`'a `MRZ ile görünen metin çelişiyor, MRZ değeri kullanıldı: <alanlar>.` eklenir (alan adı, kişisel değer yok; analizci notu başta korunur; ikinci uygulama sonucu değiştirmez); okunamayan görünen okuma MRZ'den notsuz doldurulur; MRZ'nin okunamadı saydığı alan görünen okuma okunaklı olsa da `legible: false`. Biçime uymayan MRZ yok sayılır, izinsiz karakterli MRZ kullanılmaz (ikisi de bilgi notuyla), boş/okunamaz sayfanın MRZ'sine güvenilmez; `MrzResolution.allows_clean_document_number` §20.2.3'ün üçüncü koşulunu verir. Entegrasyon: bütün kayıtlı yanıtlardaki MRZ'ler (dört hatalı hanesi düzeltilen `russian_passport` ve S13) geçerli ve görünen metinle çelişmiyor; kayıtlı pasaportun numara hanesi bozulunca 04.4 kapısı `Okunamayan alanlar: document_number` verir, görünen numarası bulanık pasaport geçerli MRZ'den okunup kapıdan geçer. 26 kural bozulması (ağırlık dizisi, dolgu değeri, üç biçimin bileşik aralıkları, TD2 uyruk konumu, dolgu hanesi, doğum yüzyılı sınırı, son geçerlilik yüzyılı, büyük harf, isim ayracı, isimde rakam, MRZ'nin kazanması, geçersiz alanın yazılması, baba adı, numara normalizasyonu, not tekrarı, güvenilmeyen sayfa, geçersiz ve bileşik hanesi tutmayan MRZ'de temiz numara, karışık satır uzunluğu, `<` hanesi, boş numara, uyruk biçimi, görünmeyen okumanın doldurulması, isim dili) geçici olarak denendi, her biri testte kırmızı — `app/matching/mrz.py`, `tests/fixtures/ai/recordings/russian_passport/0.json` · test `tests/matching/test_mrz.py` (50 fonksiyon / 182 durum) · tm 34

#### K05.4 — 05.4.1 · Kişi anahtarı
- ✅ 05.4.1 `build_person_key(analyses, *, today)` (`app/matching/match.py`) belge adayının sayfa analizlerinden `PersonKey` üretir: belge numaraları (§20.2.1 `normalize_document_number`, tekrarsız, sayfa sırasıyla, numara başına okunaklı `fields` okumasından gelip gelmediği), normalize ad-soyad (`given_names` + `surname`, sayfanın diliyle; `other_names` girmez), doğum tarihi, orijinal yazım (`TransliteratedName` + normalize anahtar), `name_keys`, `mrz_allows_clean_document_number` (§20.2.3 koşul 3, bütün sayfalar) ve sayfalar arası çelişen alanlar (`conflicts`; tekil alan `None` olur). MRZ önce okunur (K6): her sayfaya `apply_mrz_priority` uygulanır ve MRZ'si alanı taşıyan sayfa varsa alan yalnız oradan okunur — arka yüz MRZ'si ön yüzün görünen metnini yener, MRZ'nin taşımadığı alan (hanesi tutmayan numara, `<<`'süz ad) bütün sayfalardan okunur; boş/okunamaz sayfaya güvenilmez, sayfanın okunamadı dediği `person` değeri girmez. Kayıtlı yanıtlar: S13 Kiril pasaportu tam anahtar (`000000013`, `iulia shchelkina testova`, 1992-03-15, `Тестова-Щёлкина Юлья` → `Testova-Shchelkina Iulia`); `group_file_pages` ile gruplanan Sırp oturum kartı ön+arka ve `group_across_files` ile eşlenen S5 ehliyet yüzleri tek anahtar verir. Ukraynaca Kiril parça MRZ yazımıyla aynı anahtara iner, D7 yazımında iki isim anahtarı çıkar, `today` MRZ doğum yüzyılını seçer. 22 kural bozulması (sayfalar arası MRZ önceliği, okunamadı vetosu, güvenilmeyen sayfa, MRZ önceliğinin hiç uygulanmaması, `today`, isim/çeviri dili, `legible` birikimi (iki biçim), çelişkide ilk değer (doğum, orijinal yazım), çelişki eşiği, bayrağın yalnız güvenilir sayfalardan hesaplanması, numara ayırıcı kümesi, büyük harf, boş numara/isim, ISO tarih katılığı, `name_keys` tekrarı, MRZ'nin değer taşıması koşulu, `person` önceliği, tek parçalı ad) geçici olarak denendi, her biri testte kırmızı (kurallar: C26) — `app/matching/match.py` · test `tests/matching/test_person_key.py` (35 fonksiyon / 50 durum) · tm 35
