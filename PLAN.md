# PLAN — belgeee (neredeyiz?)

> Bu dosya projenin **durum haritasıdır**. Ne yapılacağı `urun-gereksinim-dokumani-PRD.md`'de,
> nasıl yapılacağı `MASTER-PROMPT.md`'de, "bitti"nin tanımı `CONVENTIONS.md`'dedir.
> Bu dosyayı bir izleme paneli ayrıştırır — biçim kuralları kesindir (§1).

## 0. Özet tablo

| Faz | PRD | Genel durum | Must sayacı | Kapanış |
| --- | --- | --- | --- | --- |
| Faz 0 — MVP | §5.1 | 100 ✅ · 2 ◐ · 0 ⬜ · 0 🔒 | 97/98 Must | AÇIK |
| Faz 1 — v1 | §5.2 | 32 ✅ · 0 ◐ · 0 ⬜ · 0 🔒 | 21/21 Must | AÇIK |
| Faz 2 — v2 | §5.3 | 12 ✅ · 0 ◐ · 0 ⬜ · 1 🔒 | 0/0 Must | AÇIK |
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
| 01.2.2 | Desteklenmeyen türün reddi | Must (MVP) | ◐ → K01.2 |
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
| 03.3.1 | OpenAI sağlayıcı iskeleti | Should (v1) | ◐ → K03.3 |
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
| 05.5.1 | Eşleştirme sırası | Must (MVP) | ✅ → K05.5 |
| 05.5.2 | Yalnız isim eşleşmesinin reddi (R8) | Must (MVP) | ✅ → K05.5 |
| 05.5.3 | Belirsiz eşleşme | Must (MVP) | ✅ → K05.5 |
| 05.6.1 | Otomatik çalışan oluşturma (R9) | Must (MVP) | ✅ → K05.6 |
| 05.7.1 | Onay bekleyen profil | Must (MVP) | ✅ → K05.7 |
| 05.7.2 | Alias ve numara birikimi | Must (MVP) | ✅ → K05.7 |
| 05.8.1 | İletişim bilgisi saklama | Must (MVP) | ✅ → K05.8 |
| 05.8.2 | İletişim bilgisi çakışması | Must (MVP) | ✅ → K05.8 |
| 05.8.3 | Dil ve alfabe kaydı | Should (v1) | ✅ → K05.8 |

### 3.7 FR-MOD-06 — Plan ve doğrulayıcılar

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 06.1.1 | Plan JSON üretimi (R10) | Must (MVP) | ✅ → K06.1 |
| 06.1.2 | Plan determinizmi | Must (MVP) | ✅ → K06.1 |
| 06.2.1 | İşlem seçimi | Must (MVP) | ✅ → K06.2 |
| 06.3.1 | Direkt Belge kuralı (R5) | Must (MVP) | ✅ → K06.3 |
| 06.3.2 | Direkt Belge format kontrolü | Must (MVP) | ✅ → K06.3 |
| 06.4.1 | Dönüşüm izni kontrolü | Must (MVP) | ✅ → K06.4 |
| 06.5.1 | Doğrulayıcı seti | Must (MVP) | ✅ → K06.5 |
| 06.5.2 | Doğrulama başarısızlığı | Must (MVP) | ✅ → K06.5 |
| 06.6.1 | Planı yeniden çalıştırma | Must (MVP) | ✅ → K06.6 |
| 06.6.2 | Yeniden analiz ve sürüm | Must (MVP) | ✅ → K06.6 |

### 3.8 FR-MOD-07 — Uygulayıcı

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 07.1.1 | passthrough | Must (MVP) | ✅ → K07.1 |
| 07.2.1 | extract | Must (MVP) | ✅ → K07.2 |
| 07.3.1 | merge | Must (MVP) | ✅ → K07.3 |
| 07.4.1 | wrap_image | Must (MVP) | ✅ → K07.4 |
| 07.5.1 | extract_image | Must (MVP) | ✅ → K07.5 |
| 07.6.1 | render_image | Must (MVP) | ✅ → K07.6 |
| 07.7.1 | Çıktı yazma ve köken (R13) | Must (MVP) | ✅ → K07.7 |
| 07.7.2 | Alinan kopyası | Must (MVP) | ✅ → K07.7 |
| 07.8.1 | İdempotenlik | Must (MVP) | ✅ → K07.8 |

### 3.9 FR-MOD-08 — Kuyruklar ve çözüm

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 08.1.1 | Kuyruğa yönlendirme (R7) | Must (MVP) | ✅ → K08.1 |
| 08.1.2 | Gerekçe içeriği | Must (MVP) | ✅ → K08.1 |
| 08.2.1 | Kuyruk öğesini çalışana atama | Must (MVP) | ✅ → K08.2 |
| 08.3.1 | Onay bekleyen profili onaylama | Must (MVP) | ✅ → K08.3 |
| 08.4.1 | Arşive taşıma (R11) | Must (MVP) | ✅ → K08.4 |

### 3.10 FR-MOD-09 — Çalışan profili ve orkestrasyon

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 09.1.1 | profil.md üretimi | Must (MVP) | ✅ → K09.1 |
| 09.1.2 | Orijinal yazım gösterimi | Must (MVP) | ✅ → K09.1 |
| 09.1.3 | Profil içeriği eksiksizliği | Must (MVP) | ✅ → K09.1 |
| 09.2.1 | Parti durum makinesi | Must (MVP) | ✅ → K09.2 |
| 09.2.2 | Uçtan uca orkestrasyon | Must (MVP) | ✅ → K09.2 |
| 09.2.3 | Hata dayanıklılığı | Must (MVP) | ✅ → K09.2 |
| 09.3.1 | Sentetik belge üreteci | Must (MVP) | ✅ → K09.3-a |
| 09.3.2 | Kabul senaryoları S1–S5 | Must (MVP) | ✅ → K09.3-b |
| 09.3.3 | Kabul senaryoları S6–S10 | Must (MVP) | ✅ → K09.3-c |
| 09.3.4 | Kabul senaryoları S11–S15 ve S18 | Must (MVP) | ✅ → K09.3-d |

## 4. FAZ 1 — v1 (PRD §5.2)

### 4.1 FR-MOD-10 — Web yönetim paneli

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 10.1.1 | Panel iskeleti ve gezinme | Must (v1) | ✅ → K10.1 |
| 10.1.2 | Oturum tabanlı giriş | Must (v1) | ✅ → K10.1 |
| 10.1.3 | İlk kullanıcı oluşturma | Must (v1) | ✅ → K10.1 |
| 10.2.1 | Yükleme sayfası | Must (v1) | ✅ → K10.2 |
| 10.2.2 | İlerleme görünümü | Should (v1) | ✅ → K10.2 |
| 10.3.1 | Yükleme detay sayfası | Must (v1) | ✅ → K10.3 |
| 10.3.2 | Yeniden çalıştır / yeniden analiz | Should (v1) | ✅ → K10.3 |
| 10.4.1 | Çalışan listesi | Must (v1) | ✅ → K10.4 |
| 10.4.2 | Arama | Must (v1) | ✅ → K10.4 |
| 10.5.1 | Çalışan profili sayfası | Must (v1) | ✅ → K10.5 |
| 10.5.4 | Profil fotoğrafı yokluğu | Should (v1) | ✅ → K10.5 |
| 10.5.2 | Belge listesi ve açma | Must (v1) | ✅ → K10.5 |
| 10.5.3 | Profil sayfasından yükleme | Should (v1) | ✅ → K10.5 |
| 10.6.1 | Belge geçmişi | Must (v1) | ✅ → K10.6 |
| 10.7.1 | Kuyruk ekranları | Must (v1) | ✅ → K10.7-a |
| 10.7.2 | Kuyruktan çalışana atama | Must (v1) | ✅ → K10.7-b |
| 10.7.3 | Kuyruktan profil oluşturma | Must (v1) | ✅ → K10.7-c |
| 10.8.1 | İki aşamalı onay mekanizması | Must (v1) | ✅ → K10.8 |
| 10.8.2 | Belgeyi başka çalışana taşıma | Must (v1) | ✅ → K10.8 |
| 10.9.1 | İçerik düzenlemenin yokluğu (R12) | Must (v1) | ✅ → K10.9 |
| 10.9.2 | Görüntüleme ve indirme logu | Should (v1) | ✅ → K10.9 |

### 4.2 FR-MOD-11 — Belge türü kataloğu ve öğrenme (Faz 1 kalemleri)

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 11.1.1 | Katalog yönetim ekranı | Must (v1) | ✅ → K11.1 |
| 11.1.2 | Katalog form doğrulaması | Must (v1) | ✅ → K11.1 |
| 11.1.3 | Kabul kriteri düzenleme | Should (v1) | ✅ → K11.1 |
| 11.2.1 | Örnek belge yükleme | Should (v1) | ✅ → K11.2 |
| 11.3.1 | Tür açıklaması üretimi | Should (v1) | ✅ → K11.3 |
| 11.4.1 | Prompt derleyici | Must (v1) | ✅ → K11.4 |
| 11.4.2 | Token bütçesi | Should (v1) | ✅ → K11.4 |
| 11.5.1 | Aday tür listesi | Must (v1) | ✅ → K11.5 |
| 11.5.2 | Aday türü onaylama | Must (v1) | ✅ → K11.5 |
| 11.5.3 | Onay sonrası yeniden analiz | Should (v1) | ✅ → K11.5 |
| 11.5.4 | Aday türü reddetme | Should (v1) | ✅ → K11.5 |

## 5. FAZ 2 — v2 (PRD §5.3)

### 5.1 FR-MOD-11 — Belge türü kataloğu ve öğrenme (Faz 2 kalemleri)

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 11.6.1 | Profil fotoğrafı kural seti | Should (v2) | ✅ → K11.6 |
| 11.7.1 | Fotoğraf görsel kontrolü | Should (v2) | ✅ → K11.7 |
| 11.7.2 | Fotoğrafta içerik korunması | Should (v2) | ✅ → K11.7 |
| 11.8.1 | Fotoğraf örneklerinden öğrenme | Could (v3) | ✅ → K11.8 |

### 5.2 FR-MOD-12 — Telegram botu

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 12.1.1 | Bot iskeleti | Should (v2) | ✅ → K12.1 |
| 12.1.2 | Kullanıcı beyaz listesi | Should (v2) | ✅ → K12.1 |
| 12.2.1 | Belge alma | Should (v2) | ✅ → K12.2 |
| 12.2.2 | Çoklu mesaj grubu | Should (v2) | ✅ → K12.2 |
| 12.2.3 | Sonuç özeti | Should (v2) | ✅ → K12.2 |
| 12.3.1 | Belge isteme | Should (v2) | ✅ → K12.3 |
| 12.3.2 | Belirsizlikte seçim | Should (v2) | ✅ → K12.3 |
| 12.3.3 | Erişim kaydı | Should (v2) | ✅ → K12.3 |
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
- **C27** — Çalışan eşleştirme sırası (tm 36, 05.5.1–05.5.3): §20.2.2 satırları yazar ama karşılaştırmanın
  biçimini, satır 6–8'le sınırı ve olayları yazmaz; `match_employee(session, key, *, file_id,
  page_index)` (`app/matching/match.py`) şöyle uygular. **Kapsam:** satır 1–5 ve çelişkili anahtar (D8);
  hiçbir satır uymazsa hüküm `NO_MATCH`, `action`/`queue` boş — satır 6–8'in eylemi (`create`,
  `pending`, `none`) temiz numara tanımına bağlı olduğu için 05.6/05.7'nin. **Numara:** anahtarın
  numaraları `employee_identifiers.value` ile **tam eşitlikle** karşılaştırılır, `kind` bakılmaz (tablo
  türe sınırlamaz); yazan adım (05.6, 05.7.2) değeri §20.2.1 ile normalize saklamalı — `00 0000001`
  diye saklanmış değer eşleşmez. Aynı çalışanın aynı numaralı iki kaydı tek sahiptir. Numaranın
  `legible` bayrağı eşleştirmede aranmaz (tablo yalnız satır 6 için ister). **İsim:** `name_keys`'in
  (ad-soyad ve orijinal yazım) herhangi biri `employee_aliases.normalized_name` ile tam eşit olmalı;
  çalışanın `given_names`/`surname` sütunlarına bakılmaz (tablo alias der) — çalışan açan adım (05.6,
  11.x onayı) adını alias olarak da yazmalı. Alt küme/üst küme isim eşleşme değildir. **Doğum
  tarihi:** belgede ya da çalışanda yoksa "eşit" sayılmaz → satır 5. Satır 3 çalışanın kayıtlı başka bir
  numarası olmasına bakmaz. **Hüküm:** `EmployeeMatch(rule, employee_ids, conflicts)`; `employee_ids`
  E numarası sırasıyla (`E9999 < E10000`) — eşleşmede tek çalışan, belirsizde uyanların hepsi, yalnız
  isimde ismi eşleşenlerin hepsi (İK kuyrukta kimi kontrol edeceğini görsün). `matched_by`/`action`
  §8.5 değerleridir. **Gerekçe** kişisel değer taşımaz (alan adı, E numarası); satır 5'in gerekçesi
  PRD metniyle başlar. **Olay:** her hüküm tek olay — satır 1/3 `PERSON_MATCHED` (`employee_id`
  sütunu dolu), satır 2/4 `PERSON_AMBIGUOUS`, satır 5, çelişkili anahtar ve `NO_MATCH`
  `PERSON_NOT_MATCHED`; veri `rule`, varsa `matched_by`, `queue`, `employee_ids`, `conflicts`;
  gerekçe `message`. `PERSON_IDENTIFIED` bu adımda yazılmaz. Olay dışında yazmaz (alias/numara
  birikimi 05.7.2, kuyruk kaydı 08.1), commit etmez; boru hattına bağlanması 06.1'in.
- **C28** — Otomatik çalışan oluşturma (tm 37, 05.6.1): §20.2.2 satır 6 ve §20.2.3 kararı yazar ama
  kararın nerede verildiğini, yeni çalışan kaydının hangi okumalarla dolduğunu ve neyin yazıldığını
  yazmaz; `app/matching/match.py` şöyle uygular. **Temiz numara** (`clean_document_number(key,
  entry)`): `entry` adayın katalog türü; üç koşul harfiyen (`document_number ∈ required_fields`;
  `DocumentNumberKey.legible` ve normalize hâli ≥ 5 karakter; `mrz_allows_clean_document_number`) ve
  anahtarda **tek** numara — birden fazla numara çelişkidir (D8), biri seçilmez. **Karar**
  (`can_create_employee(key, match, *, entry)`, yan etkisiz — 06.1'in `employee.action: create`
  kararı): hüküm `NO_MATCH`, numara temiz, ad-soyad okunmuş ve klasör adı veriyor (D9). **Yazma**
  (`create_employee(session, layout, key, *, entry, file_id, page_index)`): çağıranın eşleştirmesine
  güvenmez, tabloyu veritabanında olaysız yeniden değerlendirir — aynı partide aynı yeni kişinin ikinci
  belgesi artık satır 1'e uyar ve reddedilir (mükerrer çalışan doğmaz); ret `EmployeeCreationRefusedError`
  (`ValueError`), mesajı yalnız hüküm/koşul, hiçbir şey yazılmaz. Uyarsa aynı işlemde E numarası
  (`allocate_employee_number`), `employee_folder_name` (K8), `employees` satırı
  `PersonKey.employee_fields()` ile (03.1.3 alanları), `employee_aliases`'a `"<given_names> <surname>"`
  (anahtarın ad-soyad normalize değeriyle) ve varsa orijinal yazım (kendi normalize değeriyle; aynı
  ham yazım bir kez; `script` boş — 05.8.3'ün), `employee_identifiers`'a temiz numara (`kind` = tür
  slug'ı, `source_document_id` boş — belge satırı 07.7'de doğar), flush, `ensure_employee_tree`
  (`Alinan/`, `Hazir/`), `EMPLOYEE_CREATED` (`employee_id` sütunu; veri `action: create`,
  `document_type_slug`; mesaj yok, kişisel değer ve klasör adı yok). Commit etmez; dizin işlem geri
  alınsa da diskte boş kalır (dosya sistemi işleme bağlı değil), aynı E numarası sonraki çağrıya yine
  verilir. `profil.md` (09.1.1), Hazir çıktısı ve Alinan kopyası (07.x), kuyruk kaydı (08.1) ve boru
  hattına bağlama (06.1) sonraki görevlerin. **Kayıt okumaları:** 05.4 anahtarına eşleştirmeye girmeyen
  dört alan eklendi — `surname`/`given_names` parçanın anahtara inen ilk okuması yazıldığı gibi (MRZ
  önceliği aynen); `other_names` isim anahtarıyla (aksan/harf büyüklüğü farkı tek okuma),
  `nationality` yalnız ICAO kodu biçimindeki okuma (`[A-Z]{1,3}`, büyük harfe çevrilir; `Russian
  Federation` gibi metin okuma sayılmaz), MRZ taşıyorsa MRZ'den. İkisi kimlik alanı değildir: çelişirse
  `None`, `conflicts`'e girmez (05.5 hükmü değişmez).
- **C29** — Onay bekleyen profil ve alias birikimi (tm 38, 05.7.1, 05.7.2): §20.2.2 satır 7–8 ve "satır 1
  ve 3'te eşleşme başarılıysa yeni isim yazımı ve numara eklenir" kararı yazar ama önerilen profilin
  içeriğini, neyin yazıldığını, birikimin neyi "yeni" saydığını ve olayları yazmaz; `app/matching/match.py`
  şöyle uygular. **Karar** (`resolve_unmatched(key, match, *, entry)`, yan etkisiz, yalnız `NO_MATCH`
  hükmüne — öteki hükümde `ValueError`): `UnmatchedResolution` `EmployeeMatch` ile aynı `action`/`queue`/
  `reason`'ı verir. `create` satır 6'dır (`can_create_employee` ile aynı karar); `pending_profile` satır 7 —
  temiz numara yok, ad-soyad klasör adı verecek biçimde okunmuş (D10); `no_person` satır 8 — ne ad/soyad
  parçası, ne orijinal yazım, ne numara (yalnız doğum tarihi kişi değildir); `incomplete_person` tablo
  dışı (D9, D10). Gerekçe kişisel değer taşımaz. **Önerilen profil** (`ProposedProfile`): `create_employee`'nin
  çalışan kaydına yazdığı okumalar (`given_names`, `surname`, `other_names`, `original_script_name`,
  `date_of_birth`, `nationality`) ve onayda `employee_aliases`'a yazılacak `(raw_name, normalized_name)`
  çiftleri (`Ad Soyad` + orijinal yazım; orijinal yazımın anahtarı sayfanın diliyle normalize edildiğinden
  onayda yeniden hesaplanmamalı). Temiz olmayan numara profile girmez. `payload()` JSON uyumlu
  `{"proposed_profile": {...}}` verir (tarih ISO): 08.1 kuyruk kaydının `payload_json`'una koymalı, 08.3
  onayda buradan okumalı. **Yazma** (`propose_pending_profile(session, key, *, entry, file_id,
  page_index)`): tabloyu veritabanında olaysız yeniden değerlendirir — satır 7 uymuyorsa
  `PendingProfileRefusedError` (mesaj yalnız hüküm/karar adı), uyuyorsa yalnız `EMPLOYEE_PENDING`
  (`employee_id` boş; veri `action: pending`, `queue: unresolved`, `document_type_slug`; mesaj gerekçe).
  Çalışan, alias, numara ve klasör yazılmaz, commit yok; aynı kişinin her numarasız belgesi ayrı öneridir.
  Satır 8 ve eksik kişi için ayrı olay yok: hüküm `PERSON_NOT_MATCHED`'te, kuyruk olayı 08.1'in.
  **Birikim** (`accumulate_identity(session, key, *, entry)`): tabloyu olaysız yeniden değerlendirir, satır
  1/3 değilse `IdentityAccumulationRefusedError`; eşleşen çalışana belgedeki yazımlardan (`Ad Soyad`,
  orijinal yazım; anahtarın normalize değeriyle, `script` boş) çalışanda aynı **ham** yazımı olmayanları,
  numarayı ise yalnız §20.2.3'e göre temizse (D11) ve çalışanda aynı **değer** hiçbir türle kayıtlı
  değilse (`kind` tür slug'ı, `source_document_id` boş) ekler. `IdentityAccumulation(employee_id, aliases,
  identifiers)` eklenenleri verir; tekrar çağrı boş döner. Satır 1'de numara zaten kayıtlı olduğundan
  numara pratikte satır 3'te birikir. Commit ve olay yok (D11). **Bağlama (06.1):** aday başına
  `match_employee` → `match` ise `accumulate_identity`; `NO_MATCH` ise `resolve_unmatched` → `create`'te
  `create_employee`, `pending`'de `propose_pending_profile`.
- **C30** — Plan JSON üretimi ve belirleyicilik (tm 40, 06.1.1, 06.1.2): §8.5 şemayı ve iki kabul kriterini
  yazar; planın neyi kapsadığı, alanların hangi adımda dolduğu, hükümlerin önceliği, yan etkilerin sırası ve
  hash'in girdisi yazılı değil. `create_plan(session, layout, upload, *, catalog, model=None,
  reference_date=None)` (`app/pipeline/plan.py`) şöyle okur. **Sözleşme:** `PlanDocument` → `PlanItem`
  (`PlanSource`, `PlanEmployee`, `PlanValidation`), pydantic, `extra=forbid`, her anahtar zorunlu; `Operation`,
  `Route` (`READY = "hazir"`), `EmployeeAction`/`MatchedBy` 05.5'ten. Değişmezler: `hazir` öğenin çalışanı
  (`match`/`create`) var, gerekçesi yok; öteki rotada gerekçe zorunlu, hedef yok; `target_name`'in uzantısı
  `target_format`; `employee_id` yalnız `match`/`create`'te, `matched_by` yalnız `match`'te; bir sayfa tek
  öğededir, `pages: []` bütün dosyadır ve o dosyanın başka öğesi olamaz; sayfalar artan. **Kapsam:** plan
  partinin bütün dosya ve sayfalarını kapsar — her aday, Word/Excel eki (`pages: []`), dosya başına boş
  sayfalar (`skip`, S8), dosya başına analizi yapılamamış sayfalar ve sayfasız tanınmayan dosya (`unresolved`,
  D14), tekrar yükleme (`skip`, S2). Sıra `(file_id, ilk sayfa)` (dosya öğesi -1), `item_id` `i1…`; kararlar
  bu sırayla verilir (aynı partide açılan çalışan sonraki öğede bulunur). **Alanlar:** `document_type_slug`
  yalnız katalog türünde (bilinmeyen türde `null`, aday adı gerekçede); `operation` `null` (06.2), `validations`
  boş (06.5); `target_format` türün `output_format`'ı, `keep` kaynak dosyaların içerikten tespit edilen ortak
  biçimi (farklı ya da tanınmıyorsa `null`, rota yine `hazir` — 06.2 karar verir); `target_name`
  `sequenced_filename(document_stem(çalışan kaydının adı, soyadı, file_label), 1, biçim)` — okumadan değil
  kayıttan, sıra eki yazma anında diskte (07.7). Word/Excel ekinin sahibi bağlam çalışanıdır: `match`,
  `matched_by: null`. **Öncelik:** bilinmeyen tür → yapısal hüküm (R6, 04.3.2, 04.5; okunaklılık kapısı
  uygulanmaz, C21) → okunaklılık (önce `unreadable`) → çalışan kararı. Rota ilk hükmün kuyruğu, `route_reason`
  kuyruğa gönderen bütün hükümlerin gerekçesi aynı sırayla boşlukla. MRZ önceliği kapıdan ve anahtardan önce
  her sayfaya (C25). **Çalışan:** her analizli aday `match_employee`'den geçer (olayı yazılır); yan etkiler
  (`accumulate_identity`, `accumulate_contacts`, `create_employee`, `propose_pending_profile`) yalnız belge
  düzeyinde hükmü olmayan adayda (D13). Kuyruğa giden adayda satır 1/3 hükmü kişi tahmini olarak `match` +
  çalışan kalır (08.1.2), öteki hükümlerde `none`; satır 2/4/5 ve çelişkili anahtarın gerekçesi eklenir,
  `resolve_unmatched` uygulanmaz. Önerilen profil (satır 7) plana girmez (§8.5'te alanı yok); 08.1 aynı saf
  adımlarla (`build_person_key(..., today=<referans gün>)` → `resolve_unmatched`) yeniden kurabilir.
  **Belirleyicilik:** girdi saklanan analizler, katalog, planlama anındaki çalışan kayıtları ve partidir;
  `plan_hash` = SHA-256(`json.dumps(model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)`), sürüm ve model hash'e girer. MRZ doğum yüzyılının referansı `reference_date` yoksa
  `uploads.created_at` günüdür (UTC) — saat plana girmez. Planın açtığı çalışan sonraki planlamanın girdisini
  değiştirir: aynı parti yeniden planlanırsa sürüm +1 (K18), yeniden çalıştırma mevcut planı `read_plan` ile
  okur (06.6.1). `read_plan(row)` sözleşmeyi, parti/sürüm/modeli ve hash'i doğrular; `PlanIntegrityError`
  değer taşımaz. **Olay:** `PLAN_CREATED` (veri `plan_id`, `version`, `plan_hash`, `model`, `items`, rota
  başına `routes`; mesaj yok); kuyruk kaydı ve `QUEUED_*` 08.1'in. Parti durumu değişmez (09.2), commit yok.
- **C31** — İşlem seçimi (tm 41, 06.2.1): §20.3 yedi satırı ve girdi değişkenlerini yazar; "tüm sayfalar",
  "ardışık", "tek sayfa"nın ölçütü, `keep`'te hedef biçimin nasıl okunacağı, Word/Excel'in hangi satıra
  düştüğü, satır 7'nin rota önceliği ve gerekçesi yazılı değil. Saf çekirdek `select_operation(sources, *,
  output_format)` (`app/pipeline/plan.py`) → `SelectedOperation(operation, target_format)` ya da
  `NoApplicableOperation` (`queue = unresolved`, `reason`); girdi `OperationSource` (`file_id`, içerikten
  `kind` ya da `None`, `pages`, `file_pages`, `blank_pages`, `single_image_pages`). **Kapsama:** dosyanın
  sayfaları `pages` satırları ∪ `range(page_count)`; aday hepsini alıyorsa "tüm sayfalar", `pages: []` (ek)
  bütün dosyadır. Adayda olmayan boş sayfa (02.4.1 ya da analizcinin boş dediği) adayı alt küme yapar: PDF'te
  `extract`, boş sayfa çıktıya girmez (S8) — sonunda boş sayfası olan tek sayfalık pasaport PDF'i
  `passthrough` değil `extract` olur; satırı açılmamış sayfa da alt küme yapar (bütün dosya kopyalanmaz).
  **Ardışık:** alınan en küçük ve en büyük sayfa arasındaki her sayfa alınmış ya da boş sayfadır (C18'in
  `[0, 2]`'si ardışık); analizsiz sayfa ya da başka belge araya girerse satır 2 uymaz. **Tek sayfa:** adayın
  tek sayfası (dosya çok sayfalı olabilir, S3/S4 fotoğrafı); satır 5/6 o sayfanın
  `has_single_embedded_image`'ına bakar — işaret yazılmamışsa `render_image` (C11'in güvenli yönü).
  **Hedef biçim:** `output_format` pdf/jpeg ise o; `keep` kaynakların içerikten tespit edilen ortak biçimi,
  farklı ya da tanınmayan biçimde hedef yok ve hiçbir satır uymaz. "Aynı biçim" kaynak = hedef demektir
  (PNG ≠ JPEG). Word/Excel eki `keep` türde satır 1 `passthrough` (S15), PDF isteyen türde satır 7 (K2).
  Satır 3 yalnız "birden çok dosya → PDF" okur; ardışıklık gruplamanındır (K4/K5). **Öncelik:** bilinmeyen
  tür ve yapısal hükümlü adaya uygulanmaz; okunaklılık kapısından sonra, çalışan kararından önce yürür —
  işlemi olmayan belgeden çalışan açılmaz, kimlik ve iletişim bilgisi birikmez (D13 gerekçesi), eşleşme kişi
  tahmini kalır. Gerekçe okunaklılık gerekçelerinin ardından, eşleştirme gerekçesinden önce gelir; ekte
  sahiplik (bağlamsız ek) gerekçesinden önce, bağlam çalışanı `match` tahmini kalır. **Gerekçe:**
  `İşlem seçilemedi (06.2.1): Kaynak(lar): dosya N, sayfa … (<biçim | biçimi tanınmadı>, dosyanın tüm
  sayfaları | ardışık alt kümesi | ardışık olmayan alt kümesi | bütün dosya). Hedef biçim: <biçim |
  belirlenemedi (…)>. §20.3'te … uyan fiziksel işlem yok; belge dönüştürülmez.` — kişisel değer yok.
  **Sözleşme:** `hazir` öğede `operation`, `target_format`, `target_name` zorunlu; kuyruğa ya da atlamaya
  giden öğede `operation` boş (uygulanmayacak işlem plana girmez, §20.4). C30'daki "`keep` farklı biçimde
  hedef boş, rota yine `hazir`" kalktı: o durum satır 7'dir. Satır 5'te `target_format` türün biçimidir
  (`jpeg`); gömülü görüntü başka biçimdeyse uzantıyı `ext`'e göre yazmak 07.5.1'in (§20.5) — plan gömülü
  görüntünün biçimini okumaz. **Olay:** yok (§8.3'te tür yok; seçim `PLAN_CREATED`'in planında). Direkt
  Belge matrisi ve format kontrolü (06.3) ile `allowed_conversions` (06.4) seçilen işlemi
  `_Planner._operation`'da hükme çevirmeli.
- **C32** — Direkt Belge kuralı (tm 42, 06.3.1, 06.3.2): §20.4 matrisi ve §20.4.1 format kontrolünü yazar;
  kontrollerin birbirine ve §20.3'e göre sırası, format kontrolünün hangi biçimi okuyacağı, çok kaynaklı ve
  tanınmayan biçimli kaynağın gerekçesi, format reddinin olayı ve izinli kontrolün loglanıp loglanmayacağı
  yazılı değil. Saf çekirdek (`app/pipeline/plan.py`): `check_direct_file_types(sources, *, entry)` →
  `DirectFileTypeMismatch` (`queue = unresolved`, `check = "file_type"`, `reason`) ya da `None`;
  `check_direct_operation(operation, *, entry)` → `DirectOperationForbidden` (`check = "operation"`) ya da
  `None`; `DIRECT_OPERATIONS = {passthrough, extract}`. **Sıra:** `_Planner._operation`'da format kontrolü →
  §20.3 → matris; ilk ret sonraki adımı keser (format tutmayan belgede satır 7 denenmez, uyan satırı olmayan
  belgede matris denenmez) ve öğenin tek işlem hükmü olur. İşlem adımının yeri C31'deki gibi okunaklılık
  kapısından sonra, çalışan kararından önce — "işlemden önce" (§20.4.1) yalnız işlem seçimine göre okundu;
  okunamayan JPEG pasaport `unreadable` rotasını alır, format gerekçesi ardından gelir. Belge adayına da
  Word/Excel ekine de uygulanır (`attachment` `direct: true`; ekin türü içerik türünden eşlendiği için format
  kontrolünü hep geçer); yapısal hükümlü ve bilinmeyen türlü adaya işlem adımı uygulanmadığından uygulanmaz.
  **Biçim:** içerikten tespit edilen biçim (01.2.1), kaynak başına; tanınmayan biçim beklenen türlerden
  değildir (ret). **Gerekçe:** `Direkt Belge: beklenen dosya türü <tür/tür>, gelen <biçim>. Uygun formatta
  yeniden gönderin.` — liste `expected_file_types` sırasıyla `/` ile birleşir (virgül `, gelen` ile karışır),
  `<biçim>` yalnız beklenmeyen kaynakların biçimleri, kaynak sırasıyla, tekrarsız, `/` ile; tanınmayan
  `tanınmayan biçim`. Matris gerekçesi `Direkt Belge: <işlem> bu tür için yapılamaz.` — PRD'deki ters tırnak
  biçimlendirme sayıldı, cümle sonuna nokta kondu (gerekçeler boşlukla birleşir). Kişisel değer yok.
  **Olay:** `DIRECT_DOC_CHECK` yalnız retlerde — matris reddi (§20.4) ve aynı bölümün format reddi — adayın
  ilk kaynağının ilk sayfasıyla (ekte `page_index` boş), `message` gerekçe, veri `document_type_slug`,
  `check`, `operation` (format reddinde `null`), `expected_file_types`, kaynak başına `file_types` (tanınmayan
  `null`), `queue`. İzinli kontrol olay atmaz (işlem `PLAN_CREATED`'in planında). `direct: false` sütununun
  "dönüşüm izinliyse" şartı 06.4.1'indir; matris o sütunda reddetmez. Katalog şeması `direct: true` türe
  `output_format: pdf|jpeg` verilmesine izin verir; o türde beklenen ama çıktı biçiminden farklı biçimde gelen
  belge format kontrolünü geçip matriste (`wrap_image`/`extract_image`/`render_image`) reddedilir — tablolar
  yazıldığı gibi uygulandı; tohum katalogdaki Direkt türlerin hepsi `keep`.
- **C33** — Dönüşüm izni kontrolü (tm 43, 06.4.1): §20.3 "3, 4, 5 ve 6 numaralı satırlar için seçilen işlem
  türün `allowed_conversions` listesinde bulunmak zorundadır; yoksa `unresolved`" der; kontrolün matrise göre
  sırası, izinsiz satırdan sonraki satıra düşülüp düşülmeyeceği, gerekçe metni ve olayı yazılı değil. Saf
  çekirdek (`app/pipeline/plan.py`): `CONVERSION_OPERATIONS = {merge, wrap_image, extract_image,
  render_image}` (katalogdaki `Conversion` adlarıyla aynı, D5); `check_conversion(operation, *, entry)` →
  `ConversionNotAllowed` (`queue = unresolved`, `operation`, türün `allowed_conversions`'ı, `reason`) ya da
  `None`; `passthrough` ve `extract` dönüşüm değildir, liste boş olsa da `None`. **Sıra:** `_Planner._operation`'da
  format kontrolü → §20.3 → Direkt Belge matrisi → dönüşüm izni; ilk ret sonrakini keser. Matris önce: §20.4
  `direct: false` sütununun "dönüşüm izinliyse" şartı matrisin ardından okundu; Direkt türün listesi şemaca
  boş olduğundan orada yalnız matris gerekçesi yazılır. **Düşme yok:** ilk uyan satırın işlemi izinsizse başka
  satır denenmez — gömülü tek görüntülü sayfada (satır 5) `extract_image` izni yoksa `render_image` (satır 6)
  izinli olsa da seçilmez; K12 render'ı yalnız gömülü görüntü yokken kabul eder. K12'nin "yalnız görsel
  türlerde" şartı için katalogda ayrı bayrak yok; şart türün `allowed_conversions`'ı ile uygulanır.
  **Gerekçe:** `Dönüşüm izni yok (06.4.1): <işlem> bu türün izinli dönüşümleri arasında değil
  (allowed_conversions: <liste>). Belge dönüştürülmez.` — liste katalog sırasıyla `/` ile (C32 ile aynı), boş
  liste `boş`; kişisel değer yok. Gerekçe okunaklılık gerekçelerinin ardından gelir; rota Unresolved, işlem ve
  hedef plana girmez, çalışan açılmaz, kimlik ve iletişim bilgisi birikmez, eşleşme kişi tahmini kalır (C31
  ile aynı yol). Word/Excel eki tüm dosyayı aldığı için satır 3–6'ya hiç uymaz; kontrol ona da uygulanır ama
  ret doğmaz. **Olay:** yok — §8.3'te dönüşüm izni için tür yok (D6/D11 sorusu); `DIRECT_DOC_CHECK` Direkt
  Belge'nin olayıdır, `direct: false` türde kullanılmadı. Ret planın gerekçesinde durur (`PLAN_CREATED`).
- **C34** — Doğrulayıcı seti ve doğrulama başarısızlığı (tm 44, 06.5.1, 06.5.2): PRD yedi doğrulayıcının adını,
  §20.1.6 `dob_plausible`'ın "geçmişte ve 16–90 yaş" ölçütünü, §20.1.7 MRZ hanelerinin sonucunu verir; her
  doğrulayıcının neyi ölçtüğü, hangi öğeye uygulandığı, var olan hükümlerle (04.4, 04.5, 06.3.2) ilişkisi,
  sırası, gerekçesi ve olayı yazılı değil. Saf çekirdek `app/pipeline/validate.py`: `ValidationName` (06.5.1
  sırası), `Validation(name, failure)`, `check_*` işlevleri geçerse `None`, geçmezse `queue` + `reason` taşıyan
  hüküm. **Ölçütler:** `required_fields` = 04.4.1 hükmü (`IllegibleRequiredFields`, Unreadable — C21); `page_count`
  = 04.5.1 hükmü (`PageCountViolation`); `sides` yalnız `front_back` türde yüzler tam `(front, back)` (yalnız ön/
  arka, ters sıra, `single`/`unknown` yüz, fazla sayfa geçmez), tek yüzlü türde geçer; `direct_single_source`
  yalnız `direct: true` türde tek kaynak ve C31 ardışıklığı (arada yalnız boş sayfa); `file_type` her türde
  içerikten tespit edilen biçim `expected_file_types`'ta (tanınmayan biçim geçmez) — §20.4.1'in "ayrıca"sı Direkt
  türe format reddini ve `DIRECT_DOC_CHECK`'i ekler, doğrulayıcının kendisini sınırlamaz; `mrz_checksum` sayfa
  başına `apply_mrz_priority` durumu: `READ`'de `failed_checks` (alan, isteğe bağlı veri, bileşik) boş olmalı,
  `INVALID` (§20.1.2 izin verilmeyen karakter) geçmez, `ABSENT`/`UNRECOGNIZED` (§20.1.1 "hata değil")/`UNTRUSTED`
  (C21) doğrulayıcıya girmez, görünen metinle çelişki hata değil; `dob_plausible` kişi anahtarının doğum tarihi
  (MRZ önce, yüzyıl §20.1.6), referans gün (partinin alındığı gün) öncesi ve tamamlanmış yılla 16 ≤ yaş ≤ 90,
  okunmamış/çelişen tarih girmez (çelişki D8'in). **Uygulama:** katalog türündeki aday (ardışıklık/belirsiz
  eşleştirme hükmü yoksa) önce `page_count` + `sides`; biri geçmezse öğe yalnız bu ikisini taşır, okunaklılık,
  öteki doğrulayıcılar ve işlem uygulanmaz (eski yapısal hüküm yolu). Geçerse yedisi de; `direct_single_source`
  ya da `file_type` geçmezse §20.3 denenmez. Word/Excel eki yalnız bu iki kaynak doğrulayıcısını taşır (K2: sayfa
  ve analiz yok, ekin türü içerik türünden eşlendiği için pratikte geçer). Bilinmeyen tür, R6/04.3.2 parçası, boş/
  analizsiz sayfa, tekrar ve işlenemeyen dosya öğeleri `validations: []`. **Rota ve gerekçe:** geçmeyen doğrulama
  bir hükümdür — `required_fields` Unreadable, öteki altısı Unresolved (06.5.2); gerekçeler 06.5.1 sırasıyla,
  kabul kriteri `required_fields`'ın hemen ardından, işlem reddi doğrulayıcılardan sonra, eşleştirme gerekçesi
  en sonda. Metinler: `Yüz doğrulaması (06.5.1, sides): tür önce bir ön, sonra bir arka yüz
  bekliyor (front, back); bu adayın yüzleri: dosya N, sayfa M: <yüz>.` · `Direkt Belge tek kaynak doğrulaması
  (06.5.1, direct_single_source): çıktı tek kaynak dosyanın ardışık sayfalarından oluşur (K3); belgenin sayfaları
  N kaynak dosyadan geliyor; dosya N, sayfa … ardışık değil.` · `Dosya türü doğrulaması (06.5.1, file_type):
  beklenen dosya türü <tür/tür>, gelen <biçim>. Uygun formatta yeniden gönderin.` (Direkt türde §20.4.1 metni) ·
  `MRZ kontrol hanesi doğrulaması (06.5.1, mrz_checksum): dosya N, sayfa M: tutmayan kontrol haneleri <alanlar> |
  izin verilmeyen karakter var, kontrol haneleri doğrulanamadı. Kontrol hanesi tutmayan MRZ geçersiz sayılır.` ·
  `Doğum tarihi doğrulaması (06.5.1, dob_plausible): okunan doğum tarihi geçmişte değil | referans güne göre 16–90
  yaş aralığı dışında; tarih yanlış okunmuş olabilir.` — tarih, yaş, MRZ değeri yok. Yan etki D13 yolundadır:
  doğrulaması geçmeyen belgeden çalışan açılmaz, profil önerilmez, kimlik/iletişim birikmez, eşleşme kişi tahmini
  kalır. **Sözleşme:** `PlanValidation.name` artık `ValidationName`; `PlanItem` doğrulamaları tekrarsız ve 06.5.1
  sırasıyla ister, `hazir` öğede `validations` dolu ve hepsi `ok` olmalı (PRD §8.5 örneğindeki tek maddelik liste
  geçerli kalır; "yedisi de" sözleşmeye yazılmadı). **Olay:** her geçmeyen doğrulama bir `VALIDATION_FAILED`
  (§8.3) — öğenin ilk sayfası (ekte dosya, `page_index` boş), mesaj gerekçe, veri `item_id`, `validation`,
  `document_type_slug`, `queue`; `required_fields` ve `page_count` için de yazılır (C21'in "okunaklılığa olay
  yok"u o modülün kendisi içindi; artık hükmün doğrulayıcı olayı var). Direkt türün format reddi önce
  `DIRECT_DOC_CHECK`, sonra `VALIDATION_FAILED` yazar. **Yan değişiklikler:** biçim listesi metni
  (`file_types_text`) ve beklenmeyen biçim toplama (`unexpected_file_types`) `validate.py`'ye alındı,
  `check_direct_file_types` onları kullanır (davranış aynı). Tanınmayan içerikli kaynak artık her türde `file_type`
  ile reddedildiği için §20.3 satır 7'nin "kaynak biçimi tanınmadı" gerekçesi planlayıcıda oluşmaz (saf
  `select_operation`'da durur); 06.2 plan testleri satır 7'yi PNG→JPEG ile sınar. §20.1.6'nın yüzyıl testi: iki
  yüzyıl da (1925/2025) 16–90 dışında kaldığından belge Unresolved, yüzyıl seçimi kişi tahmininde görünür.
- **C35** — Yeniden çalıştırma ve yeniden analiz (tm 45, 06.6.1, 06.6.2): PRD "mevcut plan yeniden uygulanır;
  yapay zekâ çağrılmaz; ikinci kopya üretilmez" ve "yeni plan sürümü açılır; eski çıktılar silinmez, eski sürüm
  işaretlenir" der; uygulayıcı (07.x) henüz yok, "güncel plan", "eski sürüm"ün değeri ve kapsamı, planı olmayan
  partinin yeniden analizi, yeniden analizin planı uygulayıp uygulamadığı ve olay verisi yazılı değil.
  `app/pipeline/orchestrate.py`. **Güncel plan** partinin en yüksek sürümüdür (`current_plan`); eski planlar
  değişmez. **Uygulayıcı portu** `PlanExecutor(session, layout, plan, document)`: doğrulanmış planı ve kaydını
  alır, yapay zekâ çağırmaz, planı değiştirmez, plan öğesi başına idempotenttir (07.8.1), commit etmez; 07.x
  çıktıları ve 08.1 kuyruk kayıtları bu tek adımda uygulanır, 09.2 bağlar. Uygulama bitince `plans.executed_at`
  son uygulamanın zamanıdır. **Yeniden çalıştırma** (`rerun_plan`): güncel plan `read_plan` ile doğrulanır (plan
  yoksa `NoPlanError`, değişmişse `PlanIntegrityError`; ikisinde de olay yok, uygulayıcı çağrılmaz), `PLAN_RERUN`
  (veri `plan_id`, `version`, `plan_hash`) yazılır ve aynı kayıt uygulayıcıya verilir. Sağlayıcı parametresi yok;
  analiz, gruplama, eşleştirme ve planlama yürümez (çalışan açma, profil önerisi, birikim tekrarlanmaz). "İkinci
  kopya üretilmez" bu katmanda aynı plan kimliği ve hash'le uygulamadır; dosya düzeyindeki garanti 07.8.1'indir —
  yeniden planlama aynı içerikte bile yeni sürüm ve hash doğurur, öğeleri uygulanmamış görünür. **Yeniden
  analiz** (`reanalyze_upload`): yalnız planı olan partide (planı olmayan partiyi işlemek 09.2'nin; sağlayıcı
  çağrılmadan `NoPlanError`). Sayfalar `analyze_upload` ile yeniden analiz edilir (tekrar dosyası ve boş sayfa yine
  atlanır; render, boş sayfa ve gömülü görüntü tespiti yapay zekâ dışı ve belirleyici olduğu için yeniden
  yapılmaz), `create_plan` sürüm +1 açar (model `provider.model`, katalog analizinkiyle aynı), partinin önceki
  sürümlerine bağlı `active` çıktılar `superseded` olur (`DocumentStatus`; satır, dosya ve ad yerinde; başka
  partinin, plana bağlı olmayan ve zaten eski olan çıktıya dokunulmaz), `PLAN_REANALYZED` (veri yeni ve önceki
  planın kimliği ile sürümü, `plan_hash`, `model`, `pages` analyzed/failed/skipped, `superseded_document_ids`;
  mesaj yok) yazılır ve yeni plan aynı işlemde uygulanır. Yeni analiz bağlayıcıdır: sayfa bu kez analiz edilemese
  de sürüm açılır ve eski çıktı eski sürüm olur (K18 koşul koymaz; kısmi başarı `partial` ve olay verisinde
  görünür). Eski sürüm işaretlemesi yeni sürümün değil yeniden analizin sonucudur: 08.2'nin elle atamayla açacağı
  sürüm önceki çıktıları eski yapmamalı. **Kuyruk (C5'in sorusu):** plan öğesi kimlikleri (`i1`…) sürümler
  arasında tekrar ettiği için göç `0002` `queue_items.plan_id`'yi (boş olabilir, `plans`'a FK, indeksli) ekler;
  kaydı yazan 08.1 doldurur. Kuyruk öğesine durum sütunu eklenmedi: güncel plana ait olmayan öğe eski sürümdür,
  08.2 onu yürütmemeli. **API:** `POST /api/uploads/{id}/rerun` (sağlayıcı bağımlılığı yok) ve `/reanalyze`
  (`get_analysis_provider` → `create_provider`, kurulamazsa 503; katalog `export_catalog`); iş tek işlemde, yalnız
  başarıda commit; bilinmeyen parti 404, plan yok ya da değişmiş 409. `get_plan_executor` uygulayıcı bağlanana
  kadar 503 verir — iki uç nokta bugün çalışan uygulamada planı uygulamaz. Parti durumu değişmez (09.2.1).
  SQLite'ta yeniden analiz yapay zekâ çağrıları boyunca yazma kilidini tutar (C4); arka plan işleyişi 09.2/13.3'ün.
- **C36** — extract işlemi (tm 47, 07.2.1): §20.5 yöntemi (`writer.add_page(reader.pages[i])`), yasakları ve
  doğrulamayı (sayfa sayısı + sayfa başına metin katmanı birebir) yazar; işlevin girdisi, sayfa dizininin tabanı,
  hangi metin çıkarıcıyla karşılaştırılacağı, doğrulamanın yayından önce mi sonra mı yapılacağı ve okunamayan
  kaynak yazılı değil. `execute_extract(source, destination, *, pages)` (`app/pipeline/execute.py`): `pages`
  `PlanSource.pages`'tir — 0 tabanlı `pages.index`, artan ve tekrarsız (boş, negatif, azalan ya da tekrarlı
  `ValueError`); verilen sırayla alınır, yeniden sıralanmaz; bitişik olması istenmez (aradaki boş sayfa, C31).
  **Metin katmanı** MuPDF `page.get_text()`'in ham çıktısıdır (02.2.1'in çıkarıcısı, boşluk normalleştirmesi
  olmadan — daha katı). **Doğrulama çıktı yayınlanmadan bellekte** yapılır; geçmeyen çıktı (`ExtractIntegrityError`)
  hedefe hiç yazılmaz, geçen `write_file` ile atomik yayınlanır, hedef varsa `FileExistsError`. **Kaynak**
  içerik imzası PDF değilse, MuPDF açamıyor ya da parola istiyorsa, pypdf okuyamıyorsa, istenen sayfa yoksa ya
  da iki okuyucu sayfa sayısında anlaşamıyorsa `ExtractSourceError` — sayfa dizinleri MuPDF'ten (render) gelir,
  bozuk PDF'i pypdf farklı onarırsa dizin başka sayfayı gösterebilir, tahmin edilmez. Yalnız sahip parolalı
  (boş kullanıcı parolalı) PDF iki okuyucuda da açılır ve çıkarılır; çıktı şifrelenmez (içerik değişmez).
  Sayfa boyutu, `/Rotate` ve sayfa ağacından kalıtılan özellikler pypdf'in sayfa nesnesine taşınır. Hatanın
  kuyruğa/olaya çevrilmesi 07.7/09.2'nin; bu görev DB'ye ve olay logına dokunmaz.
- **C37** — merge işlemi (tm 48, 07.3.1): §20.5 "`extract` ile aynı yöntem, birden çok kaynaktan sırayla; sıra
  `sources` dizisidir; yalnız `direct: false`" der; S5 iki JPEG'in "kayıpsız sarma ve birleştirme"sini bekler.
  Görüntü kaynağının nasıl birleşeceği, uygulayıcının Direkt Belge'yi yeniden denetleyip denetlemeyeceği, kaynak
  sayısı alt sınırı, EXIF yönelimi ve doğrulama yazılı değil. `execute_merge(sources, destination, *, direct)`
  (`app/pipeline/execute.py`), `MergeSource(path, pages)`: `sources` plan öğesinin `sources`'u, **en az iki
  kaynak** (§20.3 satır 3; aksi `ValueError`); sayfalar dizinin sırasıyla, kaynağın içinde `pages` sırasıyla —
  yeniden sıralama yok; her kaynağın sayfa seçimi C36'daki kural, kaynaklar okunmadan denetlenir. **Direkt
  Belge:** `direct` türün güncel katalogdaki bayrağı; doğruysa hiçbir kaynak okunmadan
  `DirectDocumentMergeError` — planlayıcı matrisi zaten reddeder (06.3.1), bekçi plan dondurulduktan sonra
  Direkt Belge yapılmış türde yeniden çalıştırmayı (06.6.1) K3'e karşı korur. "Aynı parti" (K4) uygulayıcıda
  denetlenmez, plan öğesinin kaynaklarıdır. **Yöntem:** PDF kaynak `extract`'la ortak çekirdekten (`_copy_pages`)
  sayfa nesnesi olarak kopyalanır; JPEG/PNG kaynak (tek sayfa, `0`) önce `img2pdf.convert()` ile tek sayfalık
  PDF'e sarılır (§20.5 `wrap_image` yöntemi; K14 yığınındaki `img2pdf` bu görevde `pyproject.toml`'a eklendi) ve
  o sayfa aynı biçimde kopyalanır — JPEG baytları gömülü akışta birebir, PNG pikselleri kayıpsız, sayfa
  görüntünün kendi boyutunda (A4'e yerleştirme yok). EXIF yönelimi img2pdf varsayılanıyla: 1/3/6/8 yalnız
  `/Rotate` (pikseller döndürülmez); aynalı (2/4/5/7) ya da geçersiz değer kayıpsız temsil edilemediği ya da
  analiz kopyasıyla (02.3.1, `exif_transpose`) aynı görünüm garanti edilemediği için `MergeSourceError` — tahmin
  yok. Karışık PDF + görüntü kaynakları birleşir (K4). **Kaynak hatası** (`MergeSourceError`, `ValueError`):
  PDF/JPEG/PNG olmayan içerik, açılamayan/parolalı PDF, okuyucu uyuşmazlığı, sarılamayan görüntü (img2pdf'in yedi
  hata sınıfı; adı mesajda), olmayan sayfa; mesaj kaynağı `sources[i]` (0 tabanlı) konumuyla anar, dosya yolu ya
  da özgün adı taşımaz. **Doğrulama** C36'daki gibi yayından önce bellekte: çıktı sayfa sayısı alınan sayfaların
  toplamı, her çıktı sayfasının MuPDF metin katmanı karşılık gelen kaynak sayfanınkiyle (görüntüde sarılmış
  sayfanınkiyle) birebir aynı; değilse `MergeIntegrityError`, hedefe yazma yok; hedef varsa `FileExistsError`.
  Görüntü baytlarının birebirliği çalışma anında ayrıca ölçülmez, testte kanıtlanır. Alfa kanallı PNG: §D17.
  DB, olay logu, hedef yolu ve `Alinan` kopyası 07.7'nin.
- **C38** — extract_image işlemi (tm 50, 07.5.1): §20.5 yöntemi (görüntü nesnesinin `xref`'i, `doc.extract_image`,
  baytlar olduğu gibi, JPEG değilse uzantı `ext`'e göre; Pillow ile kaydetme/boyutlandırma/kalite yok) yazılı;
  işlevin girdisi, `xref`'in nasıl bulunacağı, uzantının kimde değişeceği, doğrulama ve okunamayan kaynak yazılı
  değil. `execute_extract_image(source, destination, *, page)` (`app/pipeline/execute.py`): `page`
  `PlanSource.pages`'in tek sayfası (0 tabanlı; negatif `ValueError`), dosya çok sayfalı olabilir (S3/S4).
  **xref:** 02.5.1'in kuralı (`single_full_page_image_xref`) uygulayıcıda sayfanın kendisinden yeniden koşulur —
  yalnız çıkan görüntünün sayfada görünenle aynı olduğu kesinse `xref` vardır; kural tutmazsa
  `ExtractImageSourceError` ve `render_image`'a düşülmez (K12, C33). **Uzantı:** `destination` planın hedefidir
  (`target_name`, `.jpeg`); yayınlanan dosya aynı dizin ve gövdeyle gerçek biçimin uzantısını alır
  (`jpeg`/`png`, `FileKind` değeri), yol `StoredFile.path`'te döner. Sıra eki ve dizin 07.7'nin — `write_sequenced`
  gövdeyi uzantıdan bağımsız saydığı için `.jpeg` için boş bulunan gövde `.png` için de boştur. **Kaynak hatası**
  (`ExtractImageSourceError`): PDF olmayan içerik, açılamayan/parolalı PDF, olmayan sayfa, tek tam sayfa görüntü
  olmayan sayfa, MuPDF'in sayfayı ya da görüntüyü okuyamaması (`FzErrorBase`), JPEG/PNG dışı `ext`, 8 bitten
  derin örnek; sahip parolalı PDF çıkarılır. **Doğrulama** yayından önce bellekte, ölçütleri §D19. Hatada hedefe
  yazma yok; hedef varsa `FileExistsError`. DB, olay logu, hedef yolu ve `Alinan` kopyası 07.7'nin.
- **C39** — Çıktı yazma, köken kaydı ve Alinan kopyası (tm 52, 07.7.1, 07.7.2): §20.5 "tüm işlemler çıktıyı atomik
  yazar; `documents` kaydına kaynak dosya kimliği ve sayfa aralığı (`source_refs_json`) işlenir; `OUTPUT_SAVED` bu
  köken bilgisiyle loglanır" ve 07.7.2 "kaynak `Alinan/`'a kopyalanır; aynı hash tekrar kopyalanmaz" der; işlevin
  girdisi, `source_refs_json` biçimi, sıra ekinin nasıl seçileceği, Alinan kopyasının adı ve tekilliğin kapsamı,
  işlem olayları, olay verisi ve hata davranışı yazılı değil. `execute_ready_item(session, layout, plan, item, *,
  render_image_dpi, render_image_jpeg_quality)` (`app/pipeline/execute.py`) tek `hazir` öğeyi uygular; plan
  düzeyindeki `PlanExecutor` (idempotenlik 07.8.1, kuyruk 08.1, bağlama 09.2) bu görevde kurulmadı. **Girdi:**
  `hazir` olmayan, türsüz, işlemsiz ya da hedefsiz öğe `ValueError`; çalışan (`employees`), tür
  (`known_document_types` — `merge`'ün `direct` bekçisi güncel satırın bayrağı) ya da kaynak dosya yoksa veya dosya
  planın partisinde değilse `PlanItemReferenceError` (kaynak okunmadan). **K10 kaynak doğrulaması:** Inbox'taki her
  kaynağın SHA-256'sı `upload_files.sha256` ile aynı olmalı, değilse `SourceIntegrityError` — köken ve Alinan
  tekilliği bu hash'e dayanır. **Çıktı:** `layout.ready_dir(folder_name)` altına `write_sequenced` ile — plan
  `target_name`'i gövde + uzantıya ayrılır (`split_document_filename`), gövde doluysa K8 eki diskte (`-2`),
  `extract_image` uzantıyı gerçek biçimden alır (`.png`); `execute_<işlem>` çekirdekleri bayt üreten iç işlevlere
  ayrıldı, dışa açık imzaları değişmedi. `passthrough` içeriği yayından önce kaynak hash'iyle karşılaştırılır
  (`write_sequenced(expected_sha256=…)`, tutmazsa `PassthroughIntegrityError`, yayın yok). Tek kaynaklı işlemde
  (`merge` dışı) birden çok kaynak, `extract_image`/`render_image`'da tek olmayan sayfa `ValueError`. İşlem hataları
  olduğu gibi yükselir; bunlarda ve yukarıdaki retlerde çıktı, kopya, satır ve olay yazılmaz (kuyruğa çevirmek
  08.1/09.2'nin). **Alinan:** çıktı yayınlandıktan sonra (belge çözüldü) her kaynak `sources` sırasıyla
  `copy_to_received` (`app/storage/received.py`) ile çalışanın `Alinan/`'ına; ad Inbox'taki addır (`upload_files`
  satırındaki `stored_path`'in son parçası, orijinal ad), dolu ve içerik başkaysa `ad-2.uzantı` (`write_unique`,
  harf büyüklüğüne duyarsız, üzerine yazma yok). **Tekillik** çalışan klasöründe diskten: aynı boydaki
  dosyalardan biri aynı SHA-256'yı taşıyorsa (adı ne olursa olsun, başka partiden de) kopyalanmaz; geçici `.part`
  dosyaları sayılmaz; kopya yayından önce beklenen hash'le doğrulanır (`ContentMismatchError`). Aynı dosyadan
  iki çalışanın belgesi çıkarsa her çalışana ayrı kopya. Tarama ile yayın arası: PostgreSQL'de çalışan başına
  işlem ömürlü advisory kilit (`pg_advisory_xact_lock`), SQLite'ta `BEGIN IMMEDIATE`. **`documents`:**
  `employee_id`, `type_slug`, `path` veri köküne göreli POSIX (`DataLayout.relative`, `resolve`'un tersi),
  `format` yayınlanan dosyanın uzantısı, `sequence_no`, `plan_id`, `status: active`, `source_refs_json` öğenin
  `sources`'u olduğu gibi — `[{"file_id", "pages"}]`, 0 tabanlı sayfalar, bütün dosyada `[]`, sıra plan
  sırası. `employee_identifiers.source_document_id` geriye doldurulmadı (C28'in boş bıraktığı alan; hangi numaranın
  hangi çıktıdan geldiği bu katmanda bilinmez). **Olaylar:** işlemin §8.3 türü (`PAGE_EXTRACTED`, `PAGES_MERGED`,
  `IMAGE_WRAPPED`, `IMAGE_EXTRACTED`, `IMAGE_RENDERED`; `passthrough`'un türü yok) sonra `OUTPUT_SAVED`; ikisi de
  `upload_id`, ilk kaynağın `file_id`'si ve ilk sayfası (bütün dosyada boş), `document_id`, `employee_id`
  sütunlarıyla, mesajsız. Veri `item_id`, `plan_id`, `sources`; `OUTPUT_SAVED` ayrıca `document_type_slug`,
  `operation`, `format`, `sequence_no`, `sha256` (çıktı) ve `received` (`file_id`, `copied`) — §8.3'te Alinan
  kopyası için tür olmadığından sonucu buraya girer. Yol, hedef adı ve klasör adı kişi adı taşıdığı için olaya
  girmez. `render_image` DPI/kalitesi çağırandan (`Settings.render_image_*`). Commit yok; dosya sistemi işleme
  bağlı değil. İkinci çağrı `-2` ekli ikinci çıktı üretir — "ikinci dosya üretilmez" 07.8.1'in.
- **C40** — Uygulayıcı idempotenliği (tm 53, 07.8.1, S18): PRD "aynı plan ikinci kez uygulanınca ikinci dosya
  üretilmez" der; "uygulanmış öğe"nin neyle tanınacağı, uygulanmış öğede ne yazılacağı, geri alınmış uygulamanın
  diskte kalan çıktısı ve eşzamanlı uygulama yazılı değil. `execute_ready_item` (`app/pipeline/execute.py`) plan
  öğesi başına idempotenttir; plan düzeyi `PlanExecutor` hâlâ 09.2'nin. **Tanıma:** `documents.plan_id` = planın
  kimliği ve `source_refs_json` = öğenin `sources`'u olan satır (`executed_document`) — göç yok, `documents`'a
  öğe kimliği sütunu eklenmedi: `PlanDocument` bir sayfayı en fazla bir öğeye bağladığı için bu eşleşme tekildir.
  Satırın durumuna ve sahibine bakılmaz (eski sürüm, ileride arşiv ya da başka çalışana taşıma da uygulanmış
  sayılır; öğe yeniden uygulanıp çıktı ilk çalışana geri getirilmez). **Uygulanmış öğe:** kaynak okunmaz (Inbox
  sonradan değişmiş olsa da `SourceIntegrityError` yok), işlem yürümez, diske, `documents`'a ve Alinan'a hiçbir
  şey yazılmaz; `OUTPUT_SKIPPED` (§8.3'te tanımlı, anlamı yazılı değildi) partinin, ilk kaynağın dosyası ve ilk
  sayfasıyla, var olan satırın `document_id`'si ve **şimdiki** sahibi (`employee_id`) ile, mesajsız, veri
  `item_id`, `plan_id`, `sources` yazılır; sonuç `ExecutedItem(document=var olan satır, output=None,
  received=())`, `applied` yanlış. 09.2 atlama rotası (`skip`) için bu olayı kullanırsa `document_id`'siz yazar.
  **Geri alınmış uygulama:** dosya sistemi işleme bağlı olmadığından çıktı ve Alinan kopyası diskte kalır,
  satır ve olaylar kalmaz. Yeniden uygulamada işlem yürür; `Hazir/`'da aynı gövdeyle (`stem.ext`, `stem-N.ext`
  birebir — `find_sequenced`, `app/storage/atomic.py`), aynı boy ve SHA-256'yla duran ve hiçbir `documents.path`
  satırının göstermediği dosya varsa (en küçük sıra) yeni dosya yazılmaz, o dosya kaydedilir: `documents`
  satırı, işlem olayı ve `OUTPUT_SAVED` olağan biçimde yazılır (veride benimseme ayrıca işaretlenmez),
  `received` `copied: false` gösterir. Başka satırın gösterdiği dosya benimsenmez — başka öğenin (iki aynı
  sayfa) ya da eski sürümün (K18) çıktısı içerik aynı olsa da; yeni plan sürümü yine `-2` alır. **Belirleyicilik**
  bunun önkoşulu: altı işlem aynı girdiden aynı baytları üretir; `wrap_image` (ve `merge`'ün görüntü sarması)
  img2pdf'in kendi yazıcısıyla (`Engine.internal`) ve `nodate=True` ile sarılır — varsayılan pikepdf yazıcısı
  oluşturma tarihi ve zamana bağlı `/ID` yazıyordu (img2pdf 0.6.3 pikepdf sürümünü dize olarak karşılaştırdığı
  için `"10.13" >= "6.2.0"` yanlış, `deterministic_id` istenmiyor). Görüntü verisi yazıcıdan bağımsız taşınır;
  07.3/07.4'ün 125 testi değişmeden yeşil. pypdf/PyMuPDF/img2pdf sürümü değişirse eski geri alınmış çıktı
  tanınmayabilir (o durumda `-2`). **Eşzamanlılık:** çalışan kilidi (`_lock_employee_outputs`, eski adı
  `_lock_received_copies`; PostgreSQL advisory ad alanı `belgeee.employees.outputs`) denetimden önce alınır;
  aynı öğeyi eşzamanlı uygulayan ikinci işlem ilkinin commit'ini bekler ve satırını görür (SQLite `BEGIN
  IMMEDIATE`). Kalan açık: K16 taşıması (10.x) çalışana dosya yayınlarken aynı kilidi almazsa, satırı henüz
  güncellenmemiş birebir aynı içerikli dosya benimsenebilir — taşıma bu kilidi almalı.
- **C41** — Kuyruk öğesini çalışana atama (tm 55, 08.2.1): PRD yalnız "atama sonrası çıktı üretilir ve yapay zekâ
  çağrılmaz" der; atamanın plana nasıl yazılacağı, hangi öğenin atanabileceği, hangi hükümlerin insan kararıyla
  aşılacağı, işlemin nereden geleceği ve kuyruk kaydının ne olacağı yazılı değil. `assign_queue_item(session,
  layout, queue_item_id, employee_id, *, actor, render_image_dpi, render_image_jpeg_quality)`
  (`app/pipeline/route.py`). **Plan sürümü açılmaz** (C35'in "08.2'nin elle atamayla açacağı sürüm" öngörüsünün
  tersine): yeni sürüm güncel planı değiştirir, partinin öteki kuyruk kayıtlarını eski sürüm yapar (C35: eski
  sürümün öğesi yürütülmez) ve öteki `hazir` öğeleri uygulanmamış gösterir (07.8.1 tanıması `plan_id`'ye bağlı,
  yeniden çalıştırma ikinci kopya üretirdi). İnsan kararı kuyruk kaydında (`resolved_at`, `resolved_by`) ve
  `MANUAL_ASSIGN`'da donar; çıktı dondurulmuş planın kimliği ve öğenin kaynaklarıyla kaydedilir (`documents.plan_id`
  + `source_refs_json`), böylece yeniden çalıştırma (06.6.1) öğeyi yeniden üretmez (`route_queue_item` var olan
  kaydı döner) ve yeniden analiz (06.6.2, K18) atanmış çıktıyı da eski sürüm yapar. **Atanabilir öğe:** partinin
  güncel planının (en yüksek sürüm) çözülmemiş kuyruk öğesi; kayıt planın aynı rotalı öğesini göstermeli, plan
  `read_plan` ile doğrulanır (K9). Türsüz öğe (bilinmeyen tür, analizsiz sayfa, işlenemeyen dosya) atanmaz: K8 adı
  ve §20.3 hedef biçimi türden gelir; tür onaylanıp yeniden analiz edilmelidir. Tür güncel katalogdan
  (`export_catalog`) okunur. **Aşılan ve aşılmayan hükümler:** atama yalnız sahibi karara bağlar. İçerik ve kişi
  hükümleri (okunaklılık K1, kabul kriteri, MRZ, doğum tarihi, sayfa sayısı, yüzler, eşleştirme — satır 2/4/5/7/8,
  ardışıklık ihlalinin tek parçası) insan kararıyla aşılır; fiziksel kurallar aşılmaz: işlem planlayıcının kuralıyla
  ve sırasıyla yeniden seçilir — kaynak doğrulayıcıları (`direct_single_source`, `file_type`; Direkt Belge'de
  §20.4.1 → S6 atamada da dönüştürülmez), §20.3, Direkt Belge matrisi, dönüşüm izni (güncel katalogla). Ret
  planlayıcının gerekçesiyle `QueueItemNotAssignableError` verir, olay yazılmaz. §20.3'ün boş sayfa girdisi planın
  `skip` öğelerinden okunur (S8: boş sayfalar tek `skip` öğesidir; tekrar dosyası `skip`'i bütün dosyadır, sayfa
  katmaz) — gruplama yeniden koşulmaz. Planlayıcının `_operation_source`'u saf `operation_source`'a (`plan.py`)
  ayrıldı, iki taraf aynı kuralla kurar. **Uygulama:** `execute_ready_item`'ın gövdesi `execute_item(…, decision:
  ItemDecision)`'a ayrıldı (`execute.py`; davranış değişmedi): sahip/tür/işlem/K8 adı karardan, kaynak ve köken
  plandan. `hazir` olmayan öğeye `hazir` kılığı giydirilmedi (sözleşme doğrulamalarının hepsini `ok` ister).
  Uygulayıcının işlem/kayıt/bütünlük hataları `EXECUTION_ERRORS` demetinde toplandı (09.2 kuyruğa çevirirken de
  kullanabilir); atamada `QueueItemNotAssignableError`'a çevrilir. Aynı öğenin çıktısı varsa (07.8.1 tanıması)
  atama reddedilir — başka sahibe ikinci çıktı yazılmaz. **Olay:** işlem olayı ve `OUTPUT_SAVED` (`actor`
  `system`) → `MANUAL_ASSIGN`: `actor` kullanıcı adı, parti, ilk kaynağın dosyası/sayfası, `document_id`, atanan
  `employee_id`; veri `queue_item_id`, `queue`, `plan_id`, `item_id`, `document_type_slug`, `operation`; mesaj yok.
  **Kuyruk klasörü:** kaynak kopyası silinmez (K16); `reason.json` yeniden üretilir ve her girdi `resolved_at`
  (ISO, UTC) ve `resolved_by` taşır (çözülmemişte `null`). **Eşzamanlılık:** kuyruk satırı `FOR UPDATE` +
  `populate_existing` ile okunur (PostgreSQL; SQLite `BEGIN IMMEDIATE`), ikinci atama çözülmüş görür. **K16 / API:**
  iki aşamalı onay ve `USER_CONFIRMED` 10.8.1'in; çekirdek onaylanmış kullanıcı adını (`actor`, boş olamaz) alır.
  `POST /api/queue/{id}/assign` (`app/web/routers/queue.py`, gövde yalnız `employee_id`, fazla alan 422):
  kullanıcı adı `get_confirmed_actor` bağımlılığından gelir ve oturum (10.1.2) + onay belirteci (10.8.1)
  bağlanana kadar 503 verir — çalışan uygulamada onaysız atama yapılmaz (`get_plan_executor` örneği). Kuyruk öğesi
  ya da çalışan yok 404; atanamaz/çözülmüş/eski sürüm/plan değişmiş/Inbox değişmiş 409; iş tek işlemde, yalnız
  başarıda commit. Sağlayıcı bağımlılığı yok.

- **C42** — Onay bekleyen profili onaylama (tm 56, 08.3.1): PRD yalnız "onay sonrası çalışan oluşur ve belge ona
  bağlanır" der; önerilen profilin onayda nereden okunacağı, hükmün onay anında yeniden değerlendirilip
  değerlendirilmeyeceği, belgenin nasıl bağlanacağı ve hangi olayların yazılacağı yazılı değil.
  `approve_queued_profile(session, layout, queue_item_id, *, actor, render_image_dpi, render_image_jpeg_quality)`
  (`app/pipeline/route.py`) + `approve_pending_profile(session, layout, key, *, entry, actor, file_id, page_index)`
  (`app/matching/match.py`). **Profilin kaynağı (§D20'nin ikinci yolu):** payload'a yazılmadı; onay öğenin
  sayfalarının saklanan analizlerinden (`sources` sırasıyla, katalogsuz — C12) planlayıcının saf adımıyla
  (`build_person_key`; MRZ yüzyılı partinin `created_at` günü, `create_plan`'in varsayılanı — `reference_date`
  planda saklanmaz) yeniden kurar; yapay zekâ çağrılmaz. Analiz yok/başarısız/§8.4'e uymuyorsa
  `QueueItemNotApprovableError` (değer mesaja girmez). **Onaylanabilir öğe:** güncel planın çözülmemiş,
  `employee.action: pending` öğesi; öteki kuyruk öğeleri (satır 5 dahil) atanır (08.2.1). **Hüküm onay anında
  yeniden:** satır 7 veritabanında olaysız yeniden değerlendirilir; uymuyorsa (kişi öneriden sonra kayıtlı bir
  çalışanla eşleşiyor — ör. aynı kişinin öteki önerisi onaylandı — ya da katalog değişti)
  `ProfileApprovalRefusedError` → `QueueItemNotApprovableError`, hiçbir şey yazılmaz: aynı kişinin ikinci önerisi
  ikinci çalışan açmaz, belge ilk onayda açılan çalışana atanır. E numarası hükümden önce ayrılır
  (`allocate_employee_number`'ın kilidi — PostgreSQL advisory, SQLite `BEGIN IMMEDIATE`): eşzamanlı ikinci onay
  hükmü ilk onayın commit'inden sonra okur. **Sıra:** tür, fiziksel işlem (atamanın kuralları, C41) ve "çıktı zaten
  var mı" denetimleri çalışan açılmadan önce yapılır, ret çalışan açtırmaz; işlem çalışan açıldıktan sonra
  düşerse çağıran geri alır, boş klasör diskte kalır (`create_employee` ile aynı). **Çalışan:** satır 6'nın
  yazdıkları, numara hariç — `ProposedProfile` alanları, yazımları (`script` ile), `Alinan/` + `Hazir/`; temiz
  olmayan numara yazılmaz (D11). Belgede açıkça yazılı iletişim bilgisi satır 6'daki gibi eklenir (05.8;
  `source_document_id` çıktının satırı). **Bağlama:** atamanın çekirdeği (`_resolve_with_output`,
  `assign_queue_item` ile ortak; atamanın davranışı değişmedi): K8 adı yeni çalışanın ad-soyadıyla, köken
  `plan_id` + `source_refs_json`, yeni plan sürümü açılmaz, kuyruk kaydı `resolved_at`/`resolved_by`, `reason.json`
  yeniden üretilir. **Olaylar:** `EMPLOYEE_CREATED` (`actor` kullanıcı adı; veri `action: pending`,
  `document_type_slug`) → işlem olayı + `OUTPUT_SAVED` (`system`) → `MANUAL_APPROVE` (`actor`, `document_id`, yeni
  `employee_id`; veri `MANUAL_ASSIGN`'ınkiyle aynı alanlar); kişisel değer yok. Hata sınıfı
  `QueueItemNotApprovableError` `QueueAssignmentError`'ın altında (onay da belgeyi bir çalışana bağlar). **API
  yok:** görevin çıktı yüzeyi `route.py`/`match.py`'dir; uç nokta (`POST /api/queue/{id}/approve`, K16 onayı
  `get_confirmed_actor`) 10.7-c/10.8'in işi.

- **C43** — Orkestrasyon ve parti durum makinesi (tm 59, 09.2.1, 09.2.2, 09.2.3): PRD durum zincirini, "tek
  çağrıyla" işlemeyi ve "beklenmeyen hatada `failed`, dosyalar Inbox'ta, hata loglanır"ı yazar; geçişlerin nasıl
  izleneceği, işlem sınırı, hangi hatanın "beklenmeyen" sayılacağı, uygulayıcının kuyruk/atla rotaları ve profilin ne
  zaman yeniden üretileceği yazılı değil. `process_upload(session, layout, upload, *, settings, provider) ->
  ProcessedUpload`, `execute_plan`/`plan_executor(settings)`, `UPLOAD_TRANSITIONS`/`check_transition`
  (`app/pipeline/orchestrate.py`). **Durum makinesi:** zincir + bitmemiş her durumdan `failed`; `done`/`partial`/
  `failed`'dan çıkış yok. **İzlenebilirlik:** her geçiş `uploads.status`'a yazılıp hemen commit edilir — durum her an
  başka oturumdan (`GET /api/uploads/{id}`) görünür; geçiş olayı yok (D21). **İşlem sınırı:** `process_upload`
  kendisi commit eder, geçiş başına bir işlem; analiz adımı tek işlemdir (sayfa başına commit `analyze_upload`'a
  kanca ister — SQLite'ta analiz boyunca yazma kilidi tutulur, C17'nin sorusu arka plan işleyişiyle 13.3'e kaldı).
  **Başlangıç:** parti satırı `FOR UPDATE` (SQLite `BEGIN IMMEDIATE`) ile yeniden okunur; `received` değilse
  `UploadTransitionError`, iz yok — aynı partiyi alan ikinci işleyici bekler ve işlenmiş görür. **Render:** tekrar
  dosyası atlanır; tür içerik imzasından (01.2.1): PDF → render + metin katmanı + boş sayfa + gömülü tek görüntü,
  JPEG/PNG → analiz kopyası, Word/Excel ve tanınmayan içerik sayfasız. `RenderError` (bozuk/parolalı PDF) ve Pillow'un
  `UnidentifiedImageError`'ı dosya başına SAVEPOINT'te geri alınır, parti durmaz, dosya sayfasız kalır → plan
  "işlenemeyen dosya" Unresolved (D14); ret için olay yok (§8.3'te tür yok; gerekçe planda ve `QUEUED_UNRESOLVED`'da).
  **Analiz ve plan:** katalog (`export_catalog`) bir kez okunur, analiz talimatı ve plan aynı kataloğu kullanır;
  planın modeli `provider.model`, MRZ referans günü `create_plan`'in varsayılanı. **Sonuç:** analizde başarısız sayfa
  varsa `partial`, yoksa `done`; analizin erken yazdığı `partial` bir sonraki geçişle ezilir, commit edilmez.
  **Uygulayıcı:** `hazir` → `execute_ready_item`, kuyruk rotaları → `route_queue_item`, `skip` → `OUTPUT_SKIPPED`
  (C40'ın öngördüğü gibi `document_id`'siz; mesaj öğenin gerekçesi, veri `item_id`, `plan_id`, `route: skip`,
  `sources`; yeniden çalıştırmada uygulanmış `hazir` öğe gibi yeniden yazılır). Sonra partinin herhangi bir plan
  sürümünden çıktısı olan her çalışanın `profil.md`'si `write_profile` ile yeniden üretilir (yeniden analizde eski
  sürüm çıktısının sahibi dahil, 09.1.1). `get_plan_executor` artık bu uygulayıcıdır (503 kalktı); `rerun`/`reanalyze`
  uç noktaları `PLAN_EXECUTION_ERRORS`'u (`EXECUTION_ERRORS` + `QueueItemReferenceError`/`QueueSourceIntegrityError`)
  409'a çevirir. **Hata (09.2.3):** `Exception` alt sınıfı her hata beklenmeyendir — uygulayıcının `EXECUTION_ERRORS`'u
  da: öğe kuyruğa çevrilmez (kuyruk kaydı planın aynı rotalı öğesini göstermeli, C41; `hazir` öğenin kaydı ne atanır
  ne onaylanırdı), belge tahmin edilmez, uygulama durur. Adımın işi geri alınır, parti `failed`, `PIPELINE_FAILED`
  (`stage`; `error` tam tür adı; `traceback` en içteki 20 çerçeve `dosya:satır işlev`; mesaj yalnız `app.`
  modüllerinde tanımlı hatada `str(exc)`, dış hatada boş — SQL parametresi ve dosya yolu kişi adı taşır, CONVENTIONS
  §6) yazılıp commit edilir; hata yeniden fırlatılmaz. Plan `executing`'e geçişle commit edildiği için yürütmede
  durmuş parti `rerun` ile kurtarılır (diskte kalan çıktı benimsenir, 07.8.1). **Açık kalanlar:** (1) plan
  dondurulmadan `failed` olan partinin yeniden işleme yolu yok — `process_upload` yalnız `received`, `rerun`/
  `reanalyze` plan ister, aynı dosyalar yeniden yüklenirse tekrar sayılıp atlanır (13.3/insan kararı); (2)
  `rerun`/`reanalyze` parti durumunu değiştirmez (06.6): kurtarılan parti `failed` görünür (10.3.2 karar verebilir);
  (3) `process_upload` API'ye bağlanmadı — `POST /api/uploads` partiyi `received` bırakır, tetikleme (arka plan, yeni
  oturum, sağlayıcı) 10.2/13.3'ün; (4) manuel işlemler (08.2/08.3/08.4) profili yeniden üretmiyor — tm 93 açıldı.

- **C44** — Kabul senaryoları S11–S15, S18 (tm 63, 09.3.4): S14 "onay ve yeniden analizden sonra Hazir" ister;
  aday türün onay ekranı ve iki aşamalı onayı 11.5.2'dir (Faz 1, 🔒), kabul kriteri onayın sonucunu yazar: "Onay
  sonrası tür katalogda". Faz 0'da tür kataloğa İK'nın katalog eşitlemesiyle (00.6.3) girer; senaryo testi onayı bu
  sonucuyla kurar — `peruvian_diploma` güncel kataloğa (`import_catalog`) eklenir, aday tür kaydı `pending` kalır —
  ve partiyi gerçek `POST /api/uploads/{id}/reanalyze` uç noktasından geçirir. 11.5.2 geldiğinde testin onay adımı
  onay fonksiyonuna çevrilmeli. S15'in "profil sayfasından" yüklemesi (10.5.3, Faz 1 ekranı) yükleme uç noktasının
  `context_employee_id` alanıdır. Çalışan kaydı belgedeki yazımı olduğu gibi taşır (`TEST`/`ORNEKOVA`); Latin
  biçimlenmiş yalnız klasör ve dosya adıdır (K8).

- **C45** — Panel iskeleti ve giriş (tm 64, 10.1.1, 10.1.2, 10.1.3): PRD yalnız kabul cümlelerini verir; oturumun
  deposu, ömrü, "panel yolu"nun kapsamı ve ilk yönetici komutunun biçimi yazılı değil. **Oturum:** MASTER-PROMPT §4
  "sunucu tarafı oturum çerezi" — çerez (`belgeee_session`; HttpOnly, SameSite=Lax, üretimde Secure) yalnız
  `secrets.token_urlsafe(32)` belirtecini taşır, sunucuda `user_sessions` satırı durur (belirtecin SHA-256 özeti,
  `expires_at`, çıkışta `revoked_at`; satır silinmez). Tablo §8.1'de yok → D22. Ömür `SESSION_MAX_AGE_SECONDS`
  (varsayılan 12 saat, kayan değil). Her girişte yeni belirteç; tarayıcıda kalan önceki oturum kapanır. Parola argon2id
  (`argon2-cffi` varsayılanları; eski parametreli özet doğru girişte yeniden özetlenir), en az 8 karakter; bilinmeyen
  kullanıcı adında da sahte doğrulama yapılır ve hata iletisi hangi alanın yanlış olduğunu söylemez (401). Giriş/çıkış
  olayı yazılmaz — §8.3'ün kapalı listesinde tür yok (D21 ile aynı soru). **Kapsam:** "girişsiz hiçbir panel yolu
  açılmaz" panelin arka ucu olan `/api/*` uç noktalarını da kapsar (oturumsuz 401), panel sayfaları giriş sayfasına
  303 ile yönlendirir ve dönüşte istenen sayfayı açar (`next` yalnız bu sitedeki yol — açık yönlendirme yok).
  Oturumsuz açık kalanlar yalnız `GET/POST /login`, `POST /logout`, `GET /health` (kapsayıcı sağlık denetimi) ve
  `/static` (stil dosyası); FastAPI'nin `/docs`, `/redoc`, `/openapi.json` sayfaları kapatıldı. Bağlama
  `app.main`'de yönlendirici düzeyindedir; `tests/web/test_auth.py` uygulamanın bütün yollarını (`app.openapi()`)
  oturumsuz dener. **Menü:** Yükle `/upload`, Çalışanlar `/employees`, Kuyruklar `/queues`, Belge Türleri
  `/document-types`, Yüklemeler `/uploads`; `/` Yükle'ye gider. Bölüm içerikleri kendi gereksinimlerinin (10.2, 10.3,
  10.4, 10.7, 11.1) — o işler gelene kadar sayfa yalnız bölüm başlığını gösterir (`section.html`). HTMX henüz
  eklenmedi (etkileşimli ilk sayfa 10.2'nin). **İlk yönetici:** `python -m app.web create-admin --username AD`
  (parola terminalden iki kez gizli sorulur ya da `--password-stdin` ile standart girdiden okunur; argüman olarak
  alınmaz). Komut ilk kullanıcıyla sınırlanmadı — başka kullanıcı yönetimi yolu olmadığı için sonraki yöneticiler de
  aynı komutla açılır; aynı ad reddedilir. Rol yalnız `admin` (`UserRole`); rol ayrımı PRD'de yok.

- **C46** — Yükleme sayfası ve canlı ilerleme (tm 65, 10.2.1, 10.2.2): PRD yalnız kabul cümlelerini verir; parti
  oluşunca işlemenin kim tarafından başlatılacağı, ilerlemenin nasıl yenileneceği ve HTMX'in nasıl geleceği yazılı değil.
  **Sayfa:** `GET /upload` (`app/web/routers/upload_page.py`, `upload.html`; `panel.py`'deki yer tutucu kalktı) sürükle-bırak
  bölgesi + çoklu dosya alanı + isteğe bağlı çalışan seçimi (boş seçenek "belirtme"; liste tüm çalışanlar, `folder_name`
  sırasıyla) çizer. **Gönderim:** `POST /upload` (HTMX, `hx-encoding=multipart`) `POST /api/uploads`'ın işlevini
  (`create_upload`) doğrudan çağırır — boyut/sayfa sınırı, Inbox'a değişmez yazma, tekrar tespiti ve olaylar kopyalanmadı;
  uç noktanın hataları (400/404) sayfada hata parçası olur. Form `request.form()` ile elle okunur: tarayıcı dosya seçilmeden
  gönderince adı boş tek parça yollar, Starlette bunu düz alan sayar ve bildirimli `list[UploadFile]` 422 verirdi; boş adlı
  parça ayıklanır, hiç dosya kalmazsa 400 "Yüklenecek dosya seçilmedi.". Seçimsiz çalışan alanı boş dize gelir → `None`.
  **İşleme:** tm 59'un açık bıraktığı tetikleme (C43 açık kalan 3) bu yolda kapandı: `POST /upload` parti oluştuktan sonra
  `process_upload`'ı FastAPI `BackgroundTasks` ile (iş parçacığı havuzunda) başlatır; işleyici kendi oturumunu
  `get_session_factory()`'den açar, sağlayıcıyı `create_provider(settings)` kurar (`get_upload_processor`). Sağlayıcı
  kurulamazsa (eksik anahtar) parti yine de alınır — dosya Inbox'ta, K10 — ama işlenmez; kullanıcıya bu söylenir ve yenileme
  başlatılmaz. `POST /api/uploads` değişmedi: partiyi hâlâ `received` bırakır. Uygulama yeniden başlarsa yarım kalan parti
  kendiliğinden devam etmez — kalıcı işçi kuyruğu 13.3.1'in (Could, v3). **İlerleme:** `GET /upload/{id}/progress`
  `get_upload_status`'u (01.6.1) parçaya çevirir; parça kendini `hx-trigger="every 2s"` ile `outerHTML` yeniler, parti
  `done`/`partial`/`failed` olunca öznitelikler yoktur ve yenileme durur. Aşama şeridi `received → rendering → analyzing →
  planning → executing` (geçilenler "done", süren "current"); `failed`'da hangi aşamada durduğu bilinmez (`PIPELINE_FAILED.stage`
  10.3.1 zaman çizelgesinin), şerit tümüyle "todo" kalır. "Sayfaları hazırlanan dosya" sayacı yalnız süren partide ve tekrar
  dosyaları hariç gösterilir (tekrar ve Word/Excel hiç render edilmez, bitince "1 / 2" kalırdı). Parti ayrıntı sayfasına
  bağlantı yok (10.3.1). **HTMX:** MASTER-PROMPT §4'ün HTMX'i `app/web/static/htmx.min.js` (2.0.4, tek dosya) olarak depoya
  alındı — CDN yok, panel ağsız açılır; `base.html` her sayfada yükler. HTMX 4xx yanıtı değiştirmez; `upload.js` yalnız 4xx
  için `htmx:beforeSwap`'ta değişimi açar (hata parçası görünsün). **SQLite:** analiz adımı yazma kilidini yapay zekâ
  çağrıları boyunca tutar (C43); durum sorgusu da `BEGIN IMMEDIATE` açtığı için o sürede en çok `busy_timeout` (30 sn)
  bekler, HTMX son görünümü korur ve sonraki turda yeniden dener. PostgreSQL'de bu yok. **Açık:** parti `uploaded_by`
  yazılmıyor (API de yazmıyordu; PRD 01.x/10.2 istemiyor) — panel kullanıcısını partiye bağlamak isteniyorsa ayrı gereksinim.
- **C47** — Yükleme detay sayfası ve yeniden çalıştır / yeniden analiz (tm 66, 10.3.1, 10.3.2): PRD yalnız kabul cümlelerini
  verir; sayfanın adresi, neyi göstereceği ve işlemlerin ne zaman yapılabileceği yazılı değil. **Sayfa:**
  `GET /uploads/{upload_id}` (`upload_page.py`, `upload_detail.html`; "Yüklemeler" menüsü aktif) dört bölümü tek sayfada
  çizer: sayfalar, plan, çıktılar, olay zaman çizelgesi. `/uploads` (liste) hâlâ yer tutucudur — PRD 10.3 liste istemez; ilerleme
  parçası (`upload_result.html`) artık ayrıntıya bağlanır (C46'daki "bağlantı yok" kapandı). Parti yoksa 404 + iletişim metni.
  **Sayfalar:** dosya başına küçük resimler; küçük resim `GET /uploads/{id}/pages/{page_id}/image` ile sunulan **analiz
  kopyasıdır** (`cache/pages/`, K10: orijinal değil) ve tarayıcıda CSS ile küçülür — sunucu görüntüyü işlemez (K11, K17). Sayfa
  başka partiye aitse, görüntüsü yoksa, yolu veri dizininden kaçıyorsa (`DataLayout.resolve`) ya da dosya yoksa 404. Sayfanın
  altında durumu (analiz edildi/atlandı/…), "Boş" ve sayfayı alan plan öğesinin kimliği görünür. Sayfası olmayan dosya (Word/Excel,
  tekrar, henüz render edilmemiş) için neden yazılır. **Plan:** güncel (en yüksek sürümlü) plan; eski sürümler yalnız sayılır,
  öğeleri gösterilmez. Öğe: kimlik, tür, kaynak (dosya adı + 1 tabanlı sayfa aralığı), işlem, hedef ad, çalışan kararı, rota
  (+ gerekçe) ve doğrulamalar. Saklanan plan doğrulanamazsa (`PlanIntegrityError`) sayfa yine açılır, öğeler yerine neden gösterilir
  (uygulayıcı da o planı yürütmez, K9). **Çıktılar:** belgeler partinin **tüm** plan sürümlerinden gelir ("Etkin"/"Eski sürüm"/
  "Arşivlendi", K18) ve kuyruğa alınanlar (Unknown/Unreadable/Unresolved; eski sürümün öğesi "eski sürüm") ayrı tabloda —
  ikisi de "çıktı" sayıldı. Belge dosyasına bağlantı **yok**: açma/indirme ve erişim logu 10.5.2/10.9.2'nin işi (`access_log.document_id`
  gerektirir). **Zaman çizelgesi:** partinin `upload_id`'li olayları + çıktı belgelerine bağlı olaylar, `ts, id` sırasıyla (UTC).
  **İşlemler:** `POST /uploads/{id}/rerun` (06.6.1, tek adım) ve `POST /uploads/{id}/reanalyze` (06.6.2, iki aşamalı; D23) yalnız
  **son durumdaki** (`done`/`partial`/`failed`) ve **planı olan** partide yapılır — süren partiyi (`received`…`executing`) ezmemek
  için; değilse 409 ve neden. İşlem sayfada `#action-result` parçasına yazılır (HTMX; 4xx/5xx parçası `hx-on::before-swap` ile açılır).
  Uygulayıcı `get_plan_executor`, kataloğu `export_catalog`; iş tek işlemde, hata olursa hiçbir şey commit edilmez (onay olayı dahil).
  **Açıklar:** (1) `rerun`/`reanalyze` parti durumunu değiştirmez (C43): yürütmede durup `rerun` ile kurtarılan parti `failed`
  görünmeye devam eder — `orchestrate.py`'ye dokunmak kapsam dışıydı, karar insana; (2) `PLAN_RERUN` olayının `actor`'ü `system`
  (`rerun_plan` kullanıcı adı almaz) — panelden kimin çalıştırdığı yalnız yeniden analizde (`USER_CONFIRMED`) kayıtlı.

- **C48** — Çalışan listesi ve arama (tm 67, 10.4.1, 10.4.2): PRD yalnız kabul cümlelerini verir; adres, "belge sayısı" ve
  "durum" sütunlarının anlamı, aramanın terim kuralı ve sıralama yazılı değil. **Sayfa:** `GET /employees?q=&page=`
  (`app/web/routers/employees.py`, `employees.html` + parça `employees_results.html`; `panel.py`'deki yer tutucu kalktı, "Çalışanlar"
  menüsü aktif); sayfa başına 25 kayıt, sayfa sayısını aşan `page` son sayfaya iner, `page<1` 422, `q` en çok 100 karakter (422).
  **Sütunlar:** No (E numarası), Ad (`given_names surname`), Orijinal yazım, Uyruk (saklandığı gibi), Belge sayısı, Durum. **Belge sayısı**
  yalnız *etkin* belgelerdir (`documents.status = active`): eski sürüm (K18) ve arşive taşınan (K16) çalışanın klasöründe durmadığı için
  sayılmaz — profil sayfası (10.5.2) tüm durumları listeler. **Durum** `employees.status`'tur: bugün yalnız `active` yazılıyor ("Aktif");
  tanınmayan değer ham gösterilir. Sıra soyad, ad, E numarası (harf büyüklüğü yok sayılır; SQLite `lower()` ASCII dışını küçültmez —
  Ç/Ö/Ş/Ü/İ ile başlayan soyad geliştirme veritabanında sona düşer, PostgreSQL'de veritabanı kolasyonu belirler).
  **Arama:** metin boşlukla terimlere ayrılır (en çok 6), her terim çalışanın en az bir alanında geçmeli (terimler VE, alanlar VEYA):
  `ivan petrov` sırayla bağımsızdır, `ivan pasaport` pasaportu olan Ivan'ı bulur. Alanlar: `given_names`/`surname`/`other_names`/
  `original_script_name` ve alias `raw_name` (büyük/küçük harf duyarsız alt dize) + alias `normalize_name` anahtarı (aksan, harf büyüklüğü
  ve Kiril↔Latin farkı yok sayılır — bu yüzden çalışan açılırken alias yazılması (05.6) aramanın önkoşuludur); belge numarası
  `employee_identifiers.value` üzerinde alt dize, terim saklama biçimine (`normalize_document_number`) indirilir; belge türü katalog
  adı/dosya etiketi/slug'ı (Python'da isim katlamasıyla, `İkamet` SQLite'ta SQL ile karşılaştırılamaz) ve çalışanın **etkin** bir belgesinin
  o türde olması. `%`/`_` düz karakterdir (LIKE kaçışı). Çalışan numarası (E0001) PRD'nin arama alanları arasında olmadığı için aranmaz —
  istenirse tek yüklem. HTMX araması (`input changed delay:300ms`) yalnız `#employee-results` parçasını yeniler ve adresi günceller;
  yanıt `Vary: HX-Request` taşır, geçmiş geri yüklemesi tam sayfa alır; JavaScript kapalıyken form gönderimi aynı adrese gider.
  **Açıklar:** (1) satırlar profile bağlanmıyor — profil sayfası (10.5.1) henüz yok, ölü bağlantı konmadı; 10.5.1 ad/E numarasını
  `/employees/{id}`'ye bağlamalı; (2) arama metni adreste (GET) durur: belge numarası uvicorn erişim günlüğüne ve tarayıcı geçmişine
  düşebilir — CONVENTIONS §6 uygulama günlüğünü ve olay logunu kapsar, bu sayfa `q`'yu ne loglar ne olaya yazar; POST'a çevirmek adres/
  geri düğmesi/yer imini bozar (10.1 testleri `/employees?q=…&page=…` adresini bekler), karar insana.

- **C49** — Çalışan profili sayfası (tm 68, 10.5.1, 10.5.4, 10.5.2, 10.5.3): PRD yalnız kabul cümlelerini verir; adresler, alanların
  gösterimi, "güncel" fotoğrafın tanımı ve belge sunumunun kuralları yazılı değil. **Adresler** (`app/web/routers/employees.py`,
  `profile.html`; hepsi yalnız `GET`): `/employees/{id}` profil sayfası, `.../photo` kart fotoğrafı, `.../documents/{doc_id}/file` açma
  (satır içi), `.../documents/{doc_id}/download` indirme (ek). Çalışan listesinde No ve Ad artık profile bağlanır (C48 açığı (1) kapandı);
  bilinmeyen çalışan 404 + "Çalışan bulunamadı." sayfası. **Kart:** PRD'nin saydığı her alan görünür, boş olan "—" (gizlenmez): Ad ve Soyad
  ayrı satır, Diğer isimler, Orijinal yazım, Vatandaşlık (saklandığı gibi), Doğum tarihi (GG.AA.YYYY; `profil.md` ISO kullanır) ve Yaş
  (`calculate_age`, 09.1.3 — sunucunun bugünü), Telefon/E-posta/Adres (yalnız `is_current` olanlar, `profil.md` ile aynı; türde birden çok
  güncel değer alt alta, eski numara kartta yok), Belge numaraları (`employee_identifiers`; etiket katalogdaki tür adıdır çünkü `kind` tür
  slug'ıdır, katalogda yoksa ham `kind`). **Fotoğraf (10.5.4):** güncel fotoğraf = çalışanın en yeni **etkin** `profile_picture` belgesi
  (`created_at`, `id`); eski sürüm ve arşivlenmiş sayılmaz. "Eksik belge · Profile Picture" rozeti yalnız etkin fotoğraf **kaydı** yoksa
  çıkar; kayıt var ama dosya diskte yok ya da biçimi görüntü değil (pdf) ise yer tutucu çizilir, rozet çıkmaz (belge listesi sorunu
  "Dosya bulunamadı" ile gösterir) — kırık `<img>` çizilmez. Fotoğraf `file`'dan ayrı `/photo` adresindedir ki 10.9.2 profil sayfasını
  çizmeyi "belgeyi açma" saymasın; **10.9.2 `file` ve `download`'a log eklemeli, `photo`'nun loglanıp loglanmayacağı orada karara bağlanır.**
  **Belge listesi (10.5.2):** çalışanın **tüm** belgeleri (etkin/"Eski sürüm"/"Arşivlendi"; C48'in "profil sayfası tüm durumları listeler"
  sözü), yeniden eskiye; Tür (katalog adı), Dosya, Biçim, Durum, Tarih. Dosya adı yeni sekmede (`target="_blank" rel="noopener"`) açar,
  "İndir" ayrı bağlantıdır; eski/arşiv sönük çizilir. Dosya yoksa ya da kayıtlı yol veri dizininden kaçıyorsa (`DataLayout.resolve`)
  bağlantı çizilmez ("Dosya bulunamadı") ve uç nokta 404 verir; belge başka çalışana aitse 404. Sunum: ortam türü uzantı tablosundan
  (`pdf`, `jpg`/`jpeg`, `png`), dosya içeriğinden değil; başka biçim (Word/Excel, K2) `file`'da da ek olarak iner; `nosniff` +
  `Cache-Control: private, no-store`; sunucu bayt bayt dosyayı verir (K10, K17). "Düzenlenemez": dört yolun hiçbiri `GET dışı`
  yöntem kabul etmez (test OpenAPI şemasından sınar; 10.9.1 kendi kabulünü ayrıca yazar). **Yükleme (10.5.3):** profil sayfasında
  `/upload` formunun aynısı (dropzone + `upload.js`, aynı kimlikler) — çalışan seçici yok, gizli `context_employee_id` profilin
  çalışanıdır; `POST /upload`'a gider, ilerleme aynı sayfada `#upload-result`'ta. Bu form `upload.html`'in kopyasıdır (görevin dokunma
  yüzeyi `upload.html`'i kapsamıyordu); ikisi birlikte değişmeli. **Açıklar:** (1) yükleme bitince profilin belge listesi kendiliğinden
  yenilenmez (sayfa yenilenir ya da ilerleme parçasındaki parti ayrıntısına gidilir); (2) belgenin kaynak dosya/sayfa geçmişi
  bağlantısı 10.6.1'in; (3) tarayıcıda yalnız statik çizim (headless Chrome, kart + yer tutucu) görüldü, HTMX yükleme akışı tarayıcıda
  yeniden denenmedi — 10.2'de doğrulanan `upload.js`/HTMX kalıbı aynen kullanıldı, sınama `TestClient` ile.
- **C50** — Belge geçmişi görünümü (tm 69, 10.6.1): PRD yalnız "bir çıktının kaynak dosya ve sayfaları tıklanarak izlenir" der; adres ve
  "tıklanarak izlenir"in sınırı yazılı değil. **Adres** (`app/web/routers/documents.py`, `history.html`; yalnız `GET`, K17):
  `/documents/{id}/history`, menüde "Çalışanlar" etkin; bilinmeyen belge 404 + "Belge bulunamadı.". **İz** `documents.source_refs_json`'dan
  (K15, 07.7.1) okunur, köken kaydının sırasıyla: kaynak dosya adı yükleme detay sayfasındaki bölümüne (`/uploads/{id}#file-N`), her kaynak
  sayfa sayfa görüntüsüne (`/uploads/{id}/pages/{page_id}/image`, 10.3.1'in analiz kopyası) bağlanır; boş `pages` bütün dosyadır ve dosyanın
  bütün sayfaları listelenir; sayfa satırı ya da görüntüsü yoksa "Görüntü yok" (bağlantısız); dosya kaydı yok ya da kayıt bozuksa sayfa
  düşmez, o kayıt bağlantısız notla yazılır. Ayrıca çıktının kendisi (çalışan, tür, dosya + açma, durum, plan sürümü), partiye ve plan
  öğesine (`#item-<id>`; kimlik `OUTPUT_SAVED` olayının `item_id`'sinden, olay yoksa bağlantı çizilmez) bağlantı ve `events.document_id`'si
  bu belge olan olaylar görünür. Eski sürüm ve arşivlenmiş belgenin de geçmişi açılır. **Kaynak dosyanın kendisi (Inbox orijinali)
  sunulmaz:** belge sunan yeni yol 10.9.2 erişim logu gelmeden açılmadı; orijinali indirtmek istenirse 10.9.2 ile birlikte karar insanın.
  **Girişler:** görevin dokunma yüzeyi `documents.py` ve `history.html`'di; sayfaya panelden ulaşılsın diye `app/main.py` yönlendiriciyi
  bağlar, `profile.html` belge listesine ve `upload_detail.html` çıktı tablosuna "Geçmiş" bağlantısı, `panel.css`'e iki kural eklendi.
  `tests/web/test_profile.py`'deki "dosyası kayıp belge bağlantısız" testi `/documents/{id}/` yerine `file`/`download` yollarını sınayacak
  şekilde daraltıldı (geçmiş bağlantısı dosyaya bağlı değildir, kayıp dosyalı belgede de durur). `documents.py` diğer iki yönlendiricinin
  `_format_ts`, `_page_ranges`, `_event_place`, `_employee_label` ve `_stored_file` yardımcılarını içe aktarır (biçimler detay sayfasıyla aynı
  kalsın). **Açıklar:** (1) tarayıcıda çizim görülmedi, sınama `TestClient` ile; (2) izde Alinan kopyası ve yeniden analizde yerine geçen
  yeni belge gösterilmez; (3) geçmiş sayfasını görüntülemek erişim logu yazmaz (belge açılmıyor).
- **C51** — Kuyruk ekranları (tm 70, 10.7.1): PRD yalnız "üç kuyruk sekmesi, sayaçlar, öğe detayı ve sayfa görüntüleri" der; sayacın neyi saydığı, öğenin durumları ve adresler yazılı değil. **Adresler** (`app/web/routers/queue.py`'de ikinci yönlendirici `pages_router`, `queue.html`, `queue_item.html`; yalnız `GET`, K16/K17): `GET /queues?tab=unknown|unreadable|unresolved&state=open|resolved|superseded&page=` (varsayılan: ilk sekme Unknown, durum bekleyen; geçersiz değer 422; `tab` adı `test_auth.py`'deki örnek adresle uyumlu) ve `GET /queues/{id}` öğe detayı (bilinmeyen öğe 404 sayfası); `panel.py`'deki `/queues` yer tutucusu kalktı, `app/main.py` yönlendiriciyi `require_panel_user` ile bağlar. **Sayaç = bekleyen öğe sayısı.** Öğe üç durumdan birindedir: *bekleyen* (çözülmemiş ve `plan_id` partinin en yüksek plan sürümünde), *çözülen* (`resolved_at` dolu; eski sürümde çözülmüş de çözülen) ya da *eski sürüm* (çözülmemiş ve partinin daha yeni planı var ya da `plan_id` boş; K18 — `assign_queue_item`'ın reddettiği öğe). Sekme sayaçları yalnız bekleyeni sayar (çözülmüş ya da atanamayan öğe İK'yı bekletmez); durum bağlantıları seçili sekmenin üç durumdaki sayısını gösterir. Durumun tek tanımı `_state_filter`'dır; sayaç, liste ve detay ondan okur. **Sıra:** bekleyen en eskiden yeniye (kuyruk sırası), öbürleri en yeniden eskiye; 25'lik sayfalar, aşan sayfa sonuncuya iner. **Detay** `queue_items.payload_json`'dan (08.1'de donan) okunur: gerekçe (R7), tür (katalog adı; katalogda yoksa slug yazıldığı gibi; yoksa "Belirlenmedi"), kişi tahmini (`employee_guess`: yalnız `action`/çalışan/`matched_by` — **önerilen profil gösterilmez**, D20/C42: onay bekleyen profilin içeriği 10.7.3'ün), kaynak dosyalar (10.6.1'in `_source_view`'ü: dosya → `/uploads/{id}#file-N`, sayfa → sayfa görüntüsü `/uploads/{id}/pages/{page_id}/image`), parti / plan sürümü / plan öğesi bağlantısı, çözülmüşse çözen + zaman + çıktının geçmişi (`MANUAL_ASSIGN`/`MANUAL_APPROVE` olayının `document_id`'si) ve öğeyi anan olaylar (verisindeki `queue_item_id` bu öğe olanlar). Eksik ya da bozuk `payload_json` sayfayı düşürmez, o alan boş/bağlantısız yazılır. **Girişler:** görevin dokunma yüzeyi `queue.py` + `queue.html`'di; detay için ikinci şablon `queue_item.html`, ayrıca `panel.py` (yer tutucu), `app/main.py`, `panel.css` eklendi. Menü sayfasının `<title>`ı `test_auth.py`'nin sözleşmesi gereği yalnız "Kuyruklar"dır (sekme başlığa girmez). `queue.py` 10.6.1'in `SourceView`/`_source_view`/`_reference` ve 10.3.1'in `_format_ts`, `_event_place`, `_source_text`, `_plan_employee_text`, `QUEUE_LABELS` yardımcılarını içe aktarır. **Bilerek kapsam dışı:** atama (10.7.2) ve profil onayı (10.7.3) eylemleri; menüde toplam sayaç rozeti; çözülen öğe için çıktı dosyası bağlantısı (geçmiş sayfasına gider). **Açıklar:** (1) tarayıcıda çizim görülmedi, sınama `TestClient` ile; (2) durum süzgeci öğe başına `read_plan` doğrulaması yapmaz — saklı planı bozuk öğe bekleyen görünür, atama 409 verir; (3) durum sorgusundaki `IN (ilişkili alt sorgu)` yalnız SQLite'ta koştu (PostgreSQL testleri atlandı).

- **C52** — Kuyruktan çalışana atama (tm 71, 10.7.2): PRD yalnız "arama ile çalışan seçilir, iki aşamalı onayla atanır" der; akışın adresleri, aramanın kapsamı ve hangi öğenin atanabileceği yazılı değil. **Adresler** (`queue.py` `pages_router`, parça `queue_assign.html`, öğe detayında `#assign` bölümü): `GET /queues/{id}/assign/employees?q=` (arama) → `GET /queues/{id}/assign/confirm?employee_id=` (birinci onay metni) → `POST /queues/{id}/assign/prepare` (ikinci onay metni + belirteç) → `POST /queues/{id}/assign` (belirteçle atama). **Arama** 10.4.2'nin `list_employees`'idir (aynı alanlar ve kurallar); boş aramada liste gelmez (çalışan aranarak seçilir), ilk 25 sonuç gösterilir, fazlası "aramayı daraltın" notuyla söylenir. **Onay metinleri** §20.6'dan birebir (`<Ad Soyad>` = `given_names surname`); aynı adlı iki çalışan (D1) karışmasın diye metnin üstünde "Seçilen çalışan: Ad Soyad (E0001)" satırı ayrıca durur, metnin kendisi değişmez. **Atanabilir öğe** = bekleyen (C51) ve `payload_json`'da türü olan; türsüz öğede (Unknown) bölüm yalnız açıklama gösterir ("çıktının adı ve işlemi belge türünden seçilir", K8), çözülmüş ya da eski sürüm öğede bölüm yok. Her adım öğeyi yeniden denetler: öğe yoksa 404, çözülmüş/eski sürüm/türsüz 409, çalışan yoksa 404; yanıt HTMX parçasıdır (4xx da görünür). **Olay:** `USER_CONFIRMED` (`actor` oturumdaki kullanıcı; `data`: `operation: assign`, `target: {queue_item_id, employee_id}`, iki onayın zamanı; ad yazılmaz) `MANUAL_ASSIGN`'dan önce aynı işlemde; atama düşerse ikisi de geri alınır. Öğe detayının olay listesi artık onay olayını da gösterir (`_mentions_item`: hedefteki `queue_item_id`). **Girişler:** görevin yüzeyi `queue.py` + `queue_assign.html`'di; ayrıca `queue_item.html` (bölüm), `panel.css` (iki kural), `upload_page.py` (belirteç yardımcıları işlem-bağımsız oldu: `issue_confirmation(request, subject)` / `check_confirmation(request, subject, token)` + `reanalysis_subject`; yeniden analizin imzaladığı ileti bayt bayt aynı) ve `test_queue_page.py`'nin yol listesi testi dokunuldu. `POST /api/queue/{id}/assign` hâlâ `get_confirmed_actor` ile 503'tür (10.8.1'in işi); iki yol `_assign` yardımcısını paylaşır. **Açıklar:** (1) tarayıcıda çizim görülmedi, sınama `TestClient` ile; (2) türsüzlük `payload_json`'dan okunur — kaydı bozuk ama planında türü olan öğe panelden atanamaz (güvenli taraf, R7).

- **C53** — Kuyruktan profil oluşturma (tm 72, 10.7.3): PRD yalnız "önerilen profil düzenlenip onaylanabilir; belge içeriği düzenlenemez" der; hangi alanların düzenlenebileceği, düzeltmenin nereye yazılacağı, adresler ve düzeltilen kimliğin nasıl sınanacağı yazılı değil. **Düzenlenebilir alanlar** (`ProfileFields`, `app/matching/match.py`): önerinin çalışan kaydına yazdığı altı alan — ad, soyad, diğer isimler, orijinal yazım, doğum tarihi, vatandaşlık; belge numarası yok (temiz değil, D11). **Doğrulama** (`check_profile_fields`): ad ve soyad zorunlu; isim alanları boş, 255 karakterden uzun, denetim karakterli ya da harfsiz/rakamsız olamaz (alias anahtarı çıkmalı); ad-soyad klasör adı vermeli (K8); doğum tarihi gelecekte olamaz; vatandaşlık ICAO kodu (1–3 büyük harf; form kırpar ve büyük harfe çevirir); panel sorunları alan alan 422 ile gösterir. **Belge içeriği düzenlenemez** (K17): form yalnız bu altı alanı taşır, uç noktalar başka form alanı okumaz (`profile_form`; tür/sayfa gönderilse de yok sayılır, testli); çıktı yine kaynak sayfalardan planın işlemiyle üretilir, analizler ve plan değişmez; düzeltme yalnız çalışan kaydına ve çıktının K8 adına (klasör + dosya adı) gider. **Alias'lar:** belgenin yazımları (Ad Soyad + orijinal yazım, sayfanın diliyle normalize) kalır — belge böyle yazıyor; düzeltilmiş ad-soyad ve orijinal yazım belgede yoksa §20.2.1 normalize değeriyle eklenir. Düzeltilen kimlik kayıtlı çalışana uyarsa onay reddedilir (§D25). **Olaylar:** `USER_CONFIRMED` (`operation: approve_profile`, `target: {queue_item_id}`, iki onayın zamanı) → `EMPLOYEE_CREATED` (verisine öneriden farklı alanların *adları* `edited_fields` olarak girer, değerleri değil; düzeltme yoksa anahtar yok, 08.3.1'in verisi aynı kalır) → `OUTPUT_SAVED` → `MANUAL_APPROVE`, tek işlemde. **Adresler** (`queue.py` `pages_router`, parça `queue_new_profile.html`, öğe detayında `#new-profile` bölümü, atama bölümünün üstünde): form öneriyle dolu gelir (`review_queued_profile` — onayın ön denetimleri yazmadan, kuyruk satırı kilitlenmeden; yapay zekâ çağrılmaz); `POST /queues/{id}/profile/confirm` (birinci metin + onaylanacak değerler, düzeltilenler işaretli; kişisel veri adrese/erişim günlüğüne düşmesin diye GET değil POST) → `POST .../profile/prepare` (ikinci metin + belirteç) → `POST .../profile` (belirteçle onay). Bölüm yalnız *bekleyen* (C51) ve `payload_json`'daki `employee_guess.action: pending` öğede görünür; öneri artık onaylanamıyorsa (satır 7 uymuyor, analiz okunmuyor…) form yerine neden yazılır. Her adım öğeyi ve düzeltilen profili onayın hükmüyle yeniden denetler (404/409). Onay metinleri §20.6'dan birebir, `<Ad Soyad>` = onaylanan (düzeltilmiş) `given_names surname`. **Girişler:** görevin yüzeyi `queue.py` + `queue_new_profile.html`'di; düzeltmenin çekirdeği için `app/matching/match.py` (`ProfileFields`, `check_profile_fields`, `edited_profile_fields`, `review_pending_profile`, `approve_pending_profile(fields=)`; `_decide`'nin isim adımı `_decide_by_name` olarak ayrıldı, davranış aynı) ve `app/pipeline/route.py` (`review_queued_profile`, `approve_queued_profile(fields=)`), ayrıca `queue_item.html` (bölüm), `panel.css` ve `test_queue_page.py`'nin yol listesi testi dokunuldu. `POST /api/queue/{id}/approve` açılmadı (API'deki manuel işlemler `get_confirmed_actor` ile 503; 10.8.1'in işi). **Açıklar:** (1) tarayıcıda çizim görülmedi, sınama `TestClient` ile; (2) onaylanmış öğede atama bölümü sayfa yenilenene kadar görünür kalır (adımları 409 verir); (3) düzeltme sonrası belgenin yanlış okunmuş yazımı da alias olarak kalır — gelecekteki belgeyle yalnız doğum tarihi de tutarsa eşleşir (satır 3).

- **C54** — İki aşamalı onay mekanizması ve belgeyi başka çalışana taşıma (tm 73, 10.8.1, 10.8.2): PRD §20.6.1 akışı yazar; belirtecin nerede saklanacağı, neye bağlanacağı, tüketmenin işlem sınırı, API sözleşmesi, taşınan dosyanın adı, Alinan kopyası ve hangi belgenin taşınabileceği yazılı değil. **Mekanizma** (`app/web/confirm.py`): `Operation` (`move`, `assign`, `approve_profile`, `approve_type`, `archive`, §20.6 dışı `reanalyze`) ve `CONFIRMATION_TEXTS` — §20.6'nın beş satırı birebir, `<Ad Soyad>`/`<Tür adı>` yer tutucusuyla; `fill` doldurur, doldurulmamış yer tutucu `ValueError` (test PRD tablosunu dosyadan okuyup karşılaştırır). `issue_confirmation` `secrets.token_urlsafe(32)` üretir, `confirmation_tokens`'a yalnız SHA-256 özeti yazılır; belirteç oturum çerezinin SHA-256'sına (`session_hash`), kullanıcı adına, işleme ve hedef dizesine (`target`: taşımada `<belge>:<çalışan>`, atamada `<öğe>:<çalışan>`, profil onayında `<öğe>:<onaylanan alanların özeti>`, yeniden analizde `<parti>:<güncel plan>`, arşivde `<belge>`) bağlıdır; `created_at` birinci onayın anı, `expires_at` +10 dk. `consume_confirmation` tek koşullu `UPDATE` (bağların hepsi + `consumed_at IS NULL` + süre) — eşzamanlı iki istekten biri geçer; ret nedeni (yok, tanınmıyor, oturum, işlem/hedef, kullanılmış, süre) yalnız sunucuda ayırt edilir, istemciye tek genel metin (`CONFIRMATION_REFUSED`, 400). `confirm_operation` = tüket + `USER_CONFIRMED` (kullanıcı, işlem, hedef, iki onayın zamanı); `USER_CONFIRMED` yalnız burada yazılır. **İşlem sınırı:** tüketme, onay olayı ve işlem çağıranın tek işlemindedir — işlem düşerse (rollback) belirteç tüketilmemiş kalır ve aynı onaylanmış işlem 10 dk içinde yeniden denenebilir; başarıdan sonra aynı belirteç reddedilir (hedef artık uygun değilse önce hedef denetimi 409 verir). Hazırlık adımları belirteci yazıp commit eder. **Geçiş:** yeniden analiz (10.3.2), kuyruk ataması (10.7.2) ve profil onayı (10.7.3) panel akışları bu belirtece geçti; D23'ün HMAC belirteci (`upload_page.issue_confirmation(request, subject)`/`check_confirmation`) kaldırıldı, olay verisinin biçimi aynı. **API:** `get_confirmed_actor` (503) kaldırıldı; hazırlık `POST /api/queue/{id}/assign/prepare` (gövde `employee_id`; öğe/çalışan yok 404, atanamaz 409) ve `POST /api/queue/documents/{id}/archive/prepare` (belge yok 404, etkin değil 409) → `{operation, first_confirmation, second_confirmation, confirmation, expires_at}`; asıl istek belirteci `X-Confirmation-Token` başlığında taşır, kullanıcı oturumdakidir (`require_api_user`). **Taşıma çekirdeği** (`app/storage/move.py` `move_document(session, layout, document_id, employee_id, *, actor)`): yalnız `active` belge taşınır (eski sürüm K18 gereği yeniden adlandırılmaz; arşivlenen `Hazir/`'da değil) ve şimdiki sahibe taşınmaz → `DocumentNotMovableError`; belge/çalışan yok → `DocumentNotFoundError`/`MoveTargetNotFoundError`. Yeni ad yeni sahibin ad-soyadı + türün `file_label`'ı (K8) ve dosyanın kendi uzantısı; sıra eki diskte (`write_sequenced`, beklenen SHA-256 ile), yayından sonra eski dosya silinir (K11 taşıma, kopya kalmaz). Satırda yalnız `employee_id`, `path`, `sequence_no` değişir; köken, plan, tür, biçim, durum, `created_at` aynı. Köken kaydındaki kaynak orijinaller (tekrarsız) yeni sahibin `Alinan/`'ına `copy_to_received` ile kopyalanır (aynı SHA varsa kopyalanmaz, K10); eski sahibin Alinan kopyası silinmez (K16). Bozuk köken kaydı, eksik/SHA'sı tutmayan orijinal, bulunamayan dosya ya da okunamayan uzantı diske dokunmadan reddedilir. `MANUAL_MOVE`: `actor`, `document_id`, `employee_id` yeni sahip, ilk kaynağın parti/dosya/sayfası; veri `document_id`, `from_employee_id`, `to_employee_id`, `document_type_slug`, `sequence_no`, `sha256`, `received` (dosya + kopyalandı mı); yol ve ad yok (CONVENTIONS §6). **Panel** (`app/web/routers/documents.py`, parça `document_move.html`, geçmiş sayfasında `#move`): `GET /documents/{id}/move/employees?q=` (10.4.2'nin araması; boş aramada liste yok, belgenin sahibi seçilemez) → `GET .../move/confirm?employee_id=` (birinci metin) → `POST .../move/prepare` (ikinci metin + belirteç) → `POST .../move` (belirteç + `USER_CONFIRMED` + `MANUAL_MOVE` tek işlemde); commit'ten sonra iki çalışanın `profil.md`'si `write_profile` ile yeniden üretilir (§D26). Etkin olmayan belgede bölüm nedeni yazar; her adım belgeyi (404/409) ve çalışanı (404, sahibi 409) yeniden denetler.

- **C55** — İçerik düzenleme yokluğu ve erişim logu (tm 74, 10.9.1, 10.9.2): PRD yalnız "panelde belge içeriği düzenleyen hiçbir yol yoktur" ve "her açma ve indirme kullanıcı ve zamanla kaydedilir" der; hangi yolların "açma", kaydın nerede ve hangi sırayla yazılacağı ve yokluğun nasıl sınanacağı yazılı değil. **Kayıt** (`app/web/access.py`, `record_access`): `access_log` satırı (`ts` UTC, `user_id` oturumdaki kullanıcı, `document_id`, `action`, `channel`); `action` değerleri `AccessAction` (`view`, `download`), `channel` değerleri `AccessChannel` (`web`, `telegram`; bot 12.3.3'ün işi) — `app/db/models.py`, şema değişmedi (göç yok, sütun kısıtı yok). Açma = `GET /employees/{id}/documents/{id}/file` (`view`), indirme = `.../download` (`download`): log eylemi kullanıcının istediği yola göre tutar (Word eki `/file`'da da indirme olarak gider, `view` yazılır). **Sıra:** satır sunmadan önce yazılır ve commit edilir; yazılamazsa istek 500 olur ve belge gitmez (kimin baktığı bilinmeyen erişim olmaz). 404 (belge yok, başka çalışanın, dosyası kayıp) log yazmaz — hiçbir şey sunulmadı. Her durumdaki belge (etkin, eski sürüm, arşiv) loglanır. **Yokluk (10.9.1):** sunucunun bütün POST/PUT/PATCH/DELETE yolları `tests/web/test_access_log.py::REVIEWED_MUTATING_ROUTES`'ta gerekçesiyle sayılır; yeni bir değiştirici yol testi kırar, gözden geçirilip listeye girer. PUT/PATCH/DELETE yolu hiç yoktur; belge yollarından yalnız taşıma ve arşiv değiştirir (K11, K16 — yer ve ad, içerik değil); şablonlarda `contenteditable`, tuval, `<textarea>`, `hx-put/patch/delete` yoktur ve her `hx-post`/`method=post` hedefi listedeki bir yoldur.

- **C56** — Katalog yönetim ekranı (tm 75, 11.1.1, 11.1.2, 11.1.3): PRD yalnız "tür oluşturma, düzenleme ve pasifleştirme panelden yapılır", "Direkt türde dönüşüm listesi boş, front_back türde sayfa aralığı 2 olmalı" ve "acceptance_criteria maddeleri eklenip çıkarılabilir; değişiklik bir sonraki analizde geçerli olur" der; adresler, formun alanları, hatanın gösterimi ve pasifleştirmenin onayı yazılı değil. **Adresler** (`app/web/routers/catalog.py`; şablonlar `catalog.html`, `catalog_form.html`, `catalog_criteria.html`): `GET /document-types` listeyi verir — pasifler dahil bütün türler; ad, slug, dosya etiketi, ülke, yüz, direkt, analiz, kabul kriteri sayısı, durum (`panel.py`'deki yer tutucu kalktı, `<title>` "Belge Türleri" kaldı); `GET /document-types/new` + `POST /document-types` oluşturur (başarıda 303 → `/document-types?notice=created&slug=…`, slug varsa 409, `new` slug'ı yeni tür formunun adresi olduğu için ayrılmıştır); `GET /document-types/{slug}` + `POST /document-types/{slug}` düzenler (**slug adresten gelir, formdan değil ve değişmez**; bilinmeyen tür 404); `POST /document-types/{slug}/deactivate` ve `.../activate` pasifleştirir/etkinleştirir (yinelenen istek zararsız; **iki aşamalı onay istemez** — K16'nın manuel işlem listesinde yok ve silme değil pasifleştirmedir, silme yolu hiç yok); `POST /document-types/criteria/add` ve `.../remove` madde listesi parçasını yeniler, kaydetmez. Düzenleme yolu `/edit` adını taşımaz: 10.9.1 kilidi (`test_no_route_is_named_after_editing_content`) yol adlarında `edit` sözcüğünü yasaklar. **Form** §8.6 alanlarıdır: slug (yalnız yeni türde), ad, dosya etiketi, ülke, açıklama, beklenen dosya türleri (onay kutuları), sayfa aralığı (iki sayı), yüz yapısı, Direkt Belge, analiz, zorunlu alanlar (tek satırda virgülle), izinli dönüşümler, çıktı biçimi, kabul kriterleri, analizci açıklaması. **`active` ve `photo_rules` formdan değişmez** (pasifleştirme ayrı işlem, fotoğraf kuralları 11.6'nın): gönderilse de okunmaz ve `update_type` bu iki sütunu yazmaz. **Çok satırlı alan yok:** 10.9.1'in şablon denetimi `<textarea` işaretini yasaklar, bu yüzden açıklama, analizci açıklaması ve zorunlu alanlar tek satırlık girdidir; aynı denetim form `action` yollarını gözden geçirilmiş POST listesiyle eşler, bu yüzden yollar şablonda düz metindir ve listeye altı yeni POST yolu girdi (`tests/web/test_access_log.py`). **Doğrulama** (`app/catalog/form.py` `build_entry`): ham form metni §8.6 kaydına çevrilir ve `CatalogEntry`'den geçirilir — form ile YAML/veritabanı ayrı kural kümesi taşımaz; ihlal alan alan (`TypeFormError.problems`) 422 ile, girilen değerlerle yeniden çizilir, hiçbir şey yazılmaz. Şemanın alanlar arası kuralı (Direkt ⇒ dönüşüm boş, `analyze: false` ⇒ zorunlu alan boş) tek hata yerine `catalog_consistency` hatasında `(alan, mesaj)` çiftleri olarak toplanır (`CatalogEntry.consistency_problems`, mesaj metinleri aynı) ve form her ihlali kendi alanının yanına yazar; `front_back` ⇒ sayfa aralığı tam 2–2 kuralı **yalnız formdadır** (D28). **Kabul kriterleri:** her madde ayrı girdidir; "Madde ekle" ve "Çıkar" HTMX ile yalnız `#criteria` parçasını yeniler (`type=button`, htmx enclosing formun değerlerini kendisi gönderir, kaydetmez); JavaScript kapalıyken formun sonundaki boş alan eklemeyi, maddenin metnini boşaltmak çıkarmayı sağlar; boş madde kaydedilmez, sıra korunur. **"Bir sonraki analizde geçerli":** kayıt her analizin başında `export_catalog(session)` ile tablodan baştan okunur; panel yalnız `known_document_types`'ı yazar. Süren analiz kendi kataloğunu, donmuş plan (K9) kendi planını kullanır. Test panelden bir maddeyi çıkarıp bir yenisini ekler ve bir sonraki `process_upload`'ın sağlayıcıya verdiği talimatta çıkarılanın olmadığını, eklenenin olduğunu sınar. Pasif tür analiz talimatına girmez ama katalogda ve var olan belgelerde durur. Tutarsız kayıtlı tür (elle değiştirilmiş satır) listede "Tutarsız kayıt" rozetiyle, düzenleme formunda nedeniyle açılır; formdan kaydetmek onu düzeltir (liste tek satır bozuk diye düşmez). **Girişler:** görevin yüzeyi `app/web/routers/catalog.py` + `app/catalog/`'ti (`form.py`, `manage.py` yeni, `schema.py`, `__init__.py`); ayrıca `app/web/routers/panel.py` (yer tutucu), `app/main.py`, `app/web/static/panel.css`, üç şablon ve `tests/web/test_access_log.py` (gözden geçirilmiş POST listesi) dokunuldu. **Açıklar:** (1) tarayıcı denemesi tek seferlik bir betikle (headless Chrome, CDP) yapıldı ve depoya girmedi: madde ekleme/çıkarma, kaydetme, pasifleştirme ve Direkt + dönüşüm reddi elle doğrulandı; sürekli sınama `TestClient` ile, HTMX etkileşimi otomatik testte yok; (2) iki yönetici aynı türü aynı anda düzenlerse son yazan kazanır (iyimser eşzamanlılık yok); (3) kabul kriteri sayısına ve uzunluğuna üst sınır konmadı (PRD'de yok); (4) `catalog.yaml` yazılmaz, olay yazılmaz (D28).

- **C57** — Prompt derleyici ve token bütçesi (tm 78, 11.4.1, 11.4.2): PRD yalnız "aktif türler kompakt katalog metnine derlenir" ve "katalog metni sınırı aşarsa açıklamalar kısaltılır ve uyarı loglanır" der; biçim, sınırın değeri ve birimi, neyin kısaltılacağı ve logun yeri yazılı değil. **Derleyici** `app/catalog/prompt_builder.py` `compile_catalog(catalog, token_budget=)` → `CompiledCatalog` (`text`, `known_slugs`, `estimated_tokens`, `token_budget`, `shortened_slugs`, `over_budget`); `build_page_analysis_instructions` yuvayı bununla doldurur (yuva sözleşmesi C14'teki gibi, `known_slugs` aynı) — süreç ve yeniden analiz talimatı her seferinde katalogdan baştan derlenir, önbellek yok. **Hangi türler** C14'teki gibi: etkin ve `analyze: true`, slug sırasıyla. **Kompakt biçim:** tür başına başlık `### `slug` — Ad` (talimat slug'ı başlıktaki ters tırnaktan tanıtır), tek satırda `Ülke: RS · Yüz yapısı: `front_back` · Beklenen sayfa: 2`, `Zorunlu alanlar: …` (yoksa `yok`), `Tanım: …` (`prompt_description`, yoksa `description`), `Kabul kriterleri` madde madde. Kaldırılanlar: tür başına tekrarlanan yüz değeri açıklaması (anlamı talimatın "Yanıt alanları"nda bir kez yazılı), `Ülke: belirtilmemiş` ve boş-`fields` yer tutucuları, sayfa aralığı yoksa satır parçası. Karar motorunun alanları (`direct`, dönüşümler, çıktı biçimi, dosya etiketi, dosya türleri, `photo_rules`) C14'teki gibi girmez. Tohum katalog metni 3165 → 2693 bayt, tahmini 898 token. **Bütçe birimi:** tahmini token = UTF-8 bayt / 3, yukarı yuvarlanmış (`estimate_tokens`) — ağsız ve deterministik, gerçek tokenlaştırıcıdan temkinli (fazla) sayar; Latin olmayan harf 2 bayt olduğu için Kiril metin daha pahalı sayılır. **Sınır:** `CATALOG_TOKEN_BUDGET = 4000` (tohumun ~4,5 katı; ~30 tür) modül sabiti — `Settings` alanı açılmadı, çünkü yeniden analiz yolu (`reanalyze_upload` ve iki yönlendirici) ayar almaz; ilk analiz ve yeniden analiz aynı sınırı kullanır. Değiştirilebilir ayar istenirse iki yola da taşınmalı — karar insana. **Kısaltma:** yalnız tanımlar kısalır: bütün tanımlara ortak bir karakter sınırı konur, sınırı aşan tanım kelime sınırında kesilip `…` ile biter, tek kelimesi sığmayan tanımın satırı düşer; metnin bütçeye sığdığı en büyük sınır ikili aramayla seçilir (en uzun tanımlar önce kısalır, kısa tanıma dokunulmaz). Slug, ad, ülke/yüz/sayfa, zorunlu alanlar ve kabul kriterleri kısalmaz, tür düşmez: 04.4.2 karşılanmayan maddeyi katalog metniyle tanır, `fields` anahtarları zorunlu alan adlarıdır, talimatta olmayan tür hiç tanınamaz (yanlış Unknown). Bütün tanımlar düştüğü hâlde sığmıyorsa metin eksiksiz türlerle döner (`over_budget`) ve uyarı bunu ayrıca söyler. Sınıra tam eşit metin kısalmaz. **Log:** Python `logging` (`app.catalog.prompt_builder`, `WARNING`): ilk ve son tahmini token, bütçe, kısaltılan tür sayısı ve slug'ları — kişisel veri yok. Uygulama log yapılandırması kurmadığı için uyarı süreçte stderr'e düşer (`logging.lastResort`). Olay loguna yazılmaz: §8.3'te katalog/bütçe olayı yok (D28 emsali) ve derleme partiye değil kataloğa aittir; her analizde yeniden derlendiği için uyarı bütçe aşıldığı sürece her partide tekrarlanır. **Girişler:** görevin yüzeyi `app/catalog/prompt_builder.py`; ayrıca `app/ai/prompts/page_analysis.py` (sade liste renderer'ı kalktı, derleyiciye bağlandı; `token_budget` parametresi), `app/ai/prompts/__init__.py` (`render_catalog_section` ve `analyzable_types` dışa aktarımı kalktı — `analyzable_types` artık `app.catalog`'da), `app/catalog/__init__.py` ve `tests/ai/test_prompts.py` (03.4 testleri yeni satır biçimine uyarlandı; anlamları aynı) dokunuldu; talimat şablonu `page_analysis.md` değişmedi.

- **C58** — Aday tür akışı ve onay (tm 79, 11.5.1–11.5.4): PRD kabul cümlelerini ve §20.6'nın "Yeni belge türünü onayla" metnini verir; listenin yeri, onay formunun içeriği, "aday ile ilişkili Unknown öğesi"nin tanımı, toplu yeniden analizin birimi ve reddin onayı yazılı değil. **Liste** (`GET /document-types/candidate-types`; Belge Türleri sayfasında bağlantı ve bekleyen sayısı): yalnız `pending` adaylar, görülme sayısına göre (eşitlikte önce görülen önce), her birinin ilk 3 örnek sayfası (`sample_page_ids` sırası; analiz kopyası `/uploads/{id}/pages/{page_id}/image`), bekleyen Unknown öğe sayısı ve ilk görüldüğü parti; detay (`.../{id}`) ilk 24 örneği ve ilişkili öğeleri kuyruk detayına bağlı gösterir. Onaylanmış ama ilişkili Unknown öğesi bekleyen aday ayrı bölümde durur (toplu yeniden analize ulaşmak için); reddedilen aday hiçbir listede yok (adresiyle açılır). Yol parçasındaki tire hiçbir slug'la çakışmaz (slug `[a-z][a-z0-9_]*`), ayrılmış slug eklenmedi. **Onay:** aday doğrudan kataloğa giremez — §8.6 kaydının yapısı (dosya türleri, yüzler, Direkt Belge, zorunlu alanlar, dönüşümler, çıktı biçimi) adayda yok. Onay 11.1'in tür formuyla yapılır (alanlar ortak parça `catalog_type_fields.html`, doğrulama `build_entry` — 11.1.2 kuralları aynen); form ad ve dosya etiketi = önerilen ad, slug addan (`slugify`, biçime uymazsa boş), açıklama adayınki ile açılır, yapı formun varsayılanlarıyladır. Adımlar tam sayfa (JavaScript'siz): `POST .../approve/confirm` (birinci metin, `<Tür adı>` = formdaki ad, eklenecek kaydın özeti) → `.../approve/prepare` (ikinci metin + 10.8.1 belirteci; hedef `<aday>:<kaydın SHA-256'sı>`) → `.../approve` (`USER_CONFIRMED` → `create_type` → `decide_candidate_type` → `TYPE_APPROVED` tek işlemde, sonra detaya 303). Form değerleri adımlar arasında gizli alanla (doğrulanmış kayıttan) taşınır; her adım adayı, formu ve slug'ı yeniden denetler (karara bağlanmış 409, geçersiz form 422 alan başına mesajla, katalogda olan slug 409). Onay yalnız yeni tür açar — adayı var olan bir türe eşleme yok. **Karar kaydı:** `app/db/models.py` `decide_candidate_type` koşullu `UPDATE` (`status = 'pending'`): aday bir kez karara bağlanır, geri alınmaz, aynı anda iki karardan biri geçer; yeni sütun ve göç yok — onaylanan türün slug'ı `TYPE_APPROVED` verisinden okunur (`approved_type_slug`). Olay verisi: aday kimliği, aday tür adı (analizcinin tür adı, kişisel değer değil), onayda slug; `upload_id` boş (karar partiye değil kataloğa ait). **İlişkili Unknown öğesi (11.5.3):** ilk kaynak sayfası `(file_id, sayfa)` adayın `sample_page_ids` sayfalarından biri olan *bekleyen* Unknown öğesi — bekleyenin tanımı kuyruk ekranlarınınki (`queue.py` `_state_filter`: çözülmemiş ve partisinin güncel planında); C22'nin "11.5.3 ilişkili sayfaları buradan bulabilir" notu. Kaynak kaydı bozuk ya da sayfasız öğe hiçbir adaya bağlanmaz. **Toplu yeniden analiz:** yeniden analizin birimi partidir (06.6.2, K18) — ilişkili öğelerin partileri (tekil, kimlik sırasıyla) bütünüyle ve güncel katalogla yeniden analiz edilir (`reanalyze_upload`); yalnız onaylanmış adayda. 10.3.2 gereği iki aşamalı onay (metinler D30; hedef `candidate-types:<aday>:<parti:plan kümesinin SHA-256'sı>` — hazırlıktan sonra küme ya da bir planı değişirse belirteç geçmez). Hepsi tek işlemdir: sağlayıcı kurulamazsa 503, uygulayıcı düşerse 409 ve hiçbir partinin yeniden analizi kalmaz (belirteç tüketilmez); süren (son durumda olmayan) parti varsa hiçbiri yapılmaz (409, detayda neden). Sonuç sayfası parti başına önceki/yeni sürümü, eski sürüm işaretlenen çıktı sayısını ve hâlâ bu adayla bekleyen öğe sayısını verir. **Ret:** tek adım (D30). **S14:** senaryo testinin onay adımı `approve_candidate_type`'a çevrildi (C44'ün notu); panel adımları `tests/web/test_candidate_types_page.py`'de. **Girişler:** görevin yüzeyi `app/web/routers/catalog.py`, `app/db/models.py`; ayrıca yeni `app/catalog/candidates.py` (+ `app/catalog/__init__.py` dışa aktarımı), şablonlar `catalog_candidates.html`, `catalog_candidate.html`, `catalog_candidate_step.html`, `catalog_candidate_samples.html`, `catalog_type_fields.html` (`catalog_form.html`'den ayrıldı, çıktısı aynı), `catalog.html` (bağlantı) ve `tests/web/test_access_log.py` (10.9.1 kilidinin gözden geçirilmiş listesine altı yol) dokunuldu. Yalnız `TestClient`: tarayıcıda çizim görülmedi.

- **C59** — Manuel işlemlerden sonra profil yeniden üretimi (tm 93, 09.1.1): PRD "her değişiklikten sonra yeniden üretilir" der; hangi işlemlerin hangi çalışanın profilini üreteceği ve işlem sınırı yazılı değil. **Kapsam:** `assign_queue_item` atanan çalışanın, `approve_queued_profile` onayla açılan çalışanın, `archive_document` belgenin sahibinin profilini yeniden üretir; öteki çalışanların profili yazılmaz. **Sıra:** `write_profile` her işlevin son adımıdır — atamada çıktı, kuyruk çözümü ve `MANUAL_ASSIGN`'dan; onayda ayrıca belgeden eklenen iletişim bilgisinden (`accumulate_contacts`) sonra; arşivde `ARCHIVED` olayından sonra — böylece profil hata verebilecek başka adım kalmadan, oturumun (autoflush) güncel hâlinden üretilir. Bir işlev hata verip hiçbir şey yazmadıysa (ret) profil de yazılmaz. **Yer:** çağrı çekirdek işlevlerin içindedir (görevin çıktı yüzeyi `route.py` + `archive.py`); web yolları (`queue.py`) değişmedi. `archive.py`'de `app.profiles`, `app.storage`'ı içe aktardığı için içe aktarma işlev içindedir (üst düzeyde `app.storage` ↔ `app.profiles` döngüsü paket başlatmayı kırar). Profil `today` almaz (yaş bugünden hesaplanır). K16 taşıması (`move_document`, 10.8.2) bu işlevlerden değildir; kendi yolunda profili commit'ten sonra üretir (§D26, §D31).

- **C60** — OpenAI sağlayıcı (tm 20, 03.3.1): PRD yalnız "aynı arayüzü uygular ve en az bir gerçek çağrıyla doğrulanır" der; API, model ve parametre seçimi yazılı değil. **API:** Chat Completions (Responses API değil) — Anthropic'in zorlanmış araç çağrısının birebir karşılığı olan zorlanmış işlev seçimi (`tool_choice` adlı işlev) orada; katı `response_format` şeması kullanılmadı çünkü §8.4'ün `fields` sözlüğü katı şemaya sığmaz (§C13). İşlev `strict: false`; `parameters` Anthropic aracının `input_schema`'sıyla aynıdır (testte eşitlik denetlenir). **Ortak sözleşme:** sağlayıcı yalnız `_request_analysis`'i uygular; yanıt kabulü, yeniden deneme ve `page_index` denetimi `analyze_page`'te kalır. **`finish_reason`:** zorlanmış işlev seçiminde API `tool_calls` yerine `stop` dönebildiği için kabul ölçütü `finish_reason` değil, tek ve tam bir `record_page_analysis` işlev çağrısıdır; yalnız `length` ve `content_filter` işlev çağrısı olsa da reddedilir (kesik/süzülmüş argüman). Ret metni hata mesajına alınmaz. **Kota:** OpenAI kota/bakiye bitince de 429 döner (`code: insufficient_quota`); beklemek çözmediği için taban `ProviderError` (03.5.1 yeniden denemez), ötekiler `ProviderRateLimitError`. **Gizlilik:** `store=False` (sayfa kimlik belgesi olabilir, CONVENTIONS §6), `detail: high` (küçük yazıların okunması), `max_completion_tokens` (`max_tokens` kalktı). **Ayarlar:** `OPENAI_API_KEY` (yalnız `AI_PROVIDER=openai` iken zorunlu, `Settings` onsuz yüklenir), `OPENAI_MODEL` varsayılanı `gpt-5.5` (SDK'nın model listesindeki, tarihli sürümü olan kararlı ad; canlı doğrulanmadı — model adı `.env`'den değişir); `reasoning_effort` gönderilmez (modelin varsayılanı; çıktı kesilirse `AI_MAX_OUTPUT_TOKENS` artırılır). **Bağımlılık:** `openai>=3.16` (`httpx2` kullanır, Anthropic ile aynı taşıma katmanı). **Yüzey:** görevin çıktısı `app/ai/openai_provider.py`; kayıt (`provider.py`), ayarlar (`config.py`, `.env.example`), bağımlılık (`pyproject.toml`) ve `tests/test_config.py` bunun zorunlu eşlikçisidir.

- **C61** — Örnek belge yükleme (tm 76, 11.2.1): PRD yalnız "Türe örnek yüklenir; örnekler çalışan verisinden ayrı tutulur ve aramada görünmez" der (§8.2: `KnownDocuments/examples/<tur_slug>/`); yükleme yeri, kabul edilen türler, ad, tekrar ve "ayrı tutulur / aramada görünmez"in somut anlamı yazılı değil. **Yer:** türün düzenleme sayfasında (`GET /document-types/{slug}`; yeni tür formunda yok) tür formunun altında "Örnek belgeler" bölümü (`catalog_examples.html`): liste (dosya sisteminden), çok dosyalı düz form (`POST /document-types/{slug}/examples`, alan `files`) ve dosya bağlantıları (`GET /document-types/{slug}/examples/{ad}`, `nosniff`). POST sonucu aynı sayfanın yeniden çizimidir: başarıda 200 (yüklenen adlarla, aynı içerik varsa "zaten kayıtlı" notuyla), dosya reddedilirse 422, dosya seçilmemişse (eksik ya da tarayıcının adı boş parçası) 400. Uçlar yalnız katalogdaki türler içindir (yoksa 404). **Çekirdek** `app/storage/examples.py` — yol kuralı gereği dizin/dosya yolu yalnız `app/storage/`'da kurulur (`DataLayout.type_examples_dir` zaten vardı). **Kabul:** PDF/JPEG/PNG — tür içerik imzasından (`detect_file_kind`), saklanan uzantı içeriğe göre yeniden yazılır (`.pdf`/`.jpg`/`.png`; `.jpg` adlı PDF `.pdf` olur); Word/Excel analiz edilmediği (K2) için örnek olamaz; boş, `MAX_UPLOAD_FILE_SIZE_BYTES`'ı aşan ve açılamayan (bozuk ya da parolalı PDF, çözülemeyen görüntü; 11.3'ün girdisi olacağı için) dosya reddedilir; 01.3.1'in PDF sayfa sınırı örneğe uygulanmadı. Her dosya sınırın bir baytı ötesine kadar okunur (devasa dosya belleğe tümüyle alınmaz). **Hep-ya-hiç:** bir dosya reddedilirse hiçbiri yazılmaz (01.3.1'in parti kuralı gibi), hata dosya başına bildirilir. **Ad:** yüklenen adın gövdesi `slugify(…, "-")` ile en çok 80 karaktere sadeleşir (`Ön Yüz.PNG` → `On-Yuz.png`; yol parçası yükleyenden gelmez), sadeleşemezse `ornek`; dizinde varsa `-2`, `-3` eki (`write_unique`, atomik). **Tekrar:** türün dizininde aynı SHA-256'lı örnek varsa yeni dosya yazılmaz ve var olan bildirilir (tür başına; başka türdeki aynı içerik ayrı örnektir). **"Ayrı tutulur":** örnek yalnız dosyadır — `uploads`, `upload_files`, `documents`, `events` tablolarına satır açılmaz; `Inbox/`, `Employees/`, kuyruk ve arşiv dizinlerine dosya girmez. **"Aramada görünmez"** bunun sonucudur: çalışan/belge araması (10.4.2), kuyruklar ve yükleme listesi yalnız o tabloları okur; tekrar yükleme tespiti (K10) `upload_files`'a baktığı için örnekle aynı baytlı gerçek bir yükleme "tekrar" sayılmaz — üçü de testle kilitli. **Elle yerleştirilmiş örnekler:** dizin önceden doldurulabilir (veri dizini git dışıdır); liste izinli uzantılı (`pdf`/`jpg`/`jpeg`/`png`, büyük harf dahil) düz dosyaları ad sırasıyla gösterir; gizli, `.part`, başka uzantılı dosya ve alt dizin görünmez, içerikleri doğrulanmaz. Dosya sunumu istekteki adı yolla birleştirmeden önce bu listeyle eşler (yol çıkışı yok). **Girişler:** görevin yüzeyi `app/web/routers/catalog.py` + `data/KnownDocuments/examples/`; ayrıca `app/storage/examples.py` (yeni), `catalog_examples.html` (yeni) + `catalog_form.html` (bölüm dahil edildi), `panel.css` ve `tests/web/test_access_log.py` (10.9.1 kilidinin gözden geçirilmiş POST listesine `POST /document-types/{slug}/examples`) dokunuldu. Yalnız `TestClient`: tarayıcıda çizim görülmedi.

- **C62** — Tür açıklaması üretimi (tm 77, 11.3.1): PRD yalnız "Örneklerden yapılandırılmış tür açıklaması üretilir ve düzenlenebilir" der; "yapılandırılmış"ın alanları, girdinin sınırı, sonucun nerede durduğu ve "düzenlenebilir"in yolu yazılı değil. Tarihi plan (`docs/UYGULAMA-PLANI-KAYNAK.md` 3.3.1–3.3.3) alanları sayar — düzen, diller, alfabe, ayırt edici başlıklar, alanların konumu, MRZ varlığı, ön/arka farkları — ve sonucun `prompt_description`'a yazılıp İK'ca düzenlenmesini, bir "yeniden üret" düğmesini ister; bunlar esas alındı. **Sözleşme** `app/ai/type_description.py` `TypeDescription`: `layout` (≤200 karakter), `headings` (≤4, her biri ≤60, büyük/küçük harf duyarsız tekrarsız), `languages` (ISO 639-1), `scripts` (§8.4'ün alfabe kümesi), `field_locations` (`field` katalog alan adı biçiminde + `location` ≤80; ≤12, alan tekrarsız), `mrz` (`line_count` 2 ya da 3 + `location`; MRZ yoksa `null`), `side_differences` (≤200; tek yüzlüde `null`). §8.4 ölçüsüyle: her anahtar zorunlu, tanımsız anahtar reddedilir, tip zorlanmaz, yanıt düzeltilmez (`TypeDescriptionError`), hata mesajı yanıttaki değeri taşımaz. `field` zorunlu alanlarla sınırlanmadı (talimat zorunlu alanları ister). **Sağlayıcı:** `AnalysisProvider` ikinci bir iş kazandı — `describe_type(TypeDescriptionRequest)` (`@final`; yeniden deneme `analyze_page`'inkiyle aynı `_with_retry`, kabul `validate_type_description`); somut sağlayıcı `_request_description`'ı uygular, varsayılanı `ProviderError`dır (test sağlayıcıları değişmedi). Anthropic ve OpenAI ortak `_forced_tool_call`/`_forced_function_call`'a çevrildi — sayfa analizinin isteği ve hata metinleri birebir aynı kaldı; açıklama aracı `record_type_description`, şeması `TypeDescription.model_json_schema()`, görüntüler sırayla, sonra metin. Kayıtlı yanıt sağlayıcısı iki istek türüne tek sıradan kayıt dağıtır; tür açıklaması kaydı `tests/fixtures/ai/type_descriptions/` altındadır (`recordings/` dizinlerinin üreteçle yeniden üretilme kuralı var). **Girdi:** türün örnekleri ad sırasıyla (11.2.1'in listesi), sayfaları sırasıyla, tek istekte en çok `MAX_DESCRIPTION_PAGES = 8` sayfa; gerisi gönderilmez, sayısı sayfada bildirilir. PDF sayfası analiz görüntüsünün ölçeğinde JPEG'e (`render_pdf_images`), JPEG/PNG EXIF yönelimi uygulanmış kopyaya (`image_copy`) çevrilir — bellekte; önbelleğe ya da diske yazılmaz, örnek dosyası değişmez (testle). Açılamayan (bozuk, boyut sınırını aşan, listelendikten sonra kaybolan) örnek atlanır ve bildirilir; hiç sayfa kalmazsa istek yapılmaz. Kullanıcı metni türün adı, slug'ı, ülkesi, yüz yapısı, beklenen sayfası ve zorunlu alanlarıyla görüntülerin "örnek n, sayfa m" sırasını taşır; örneklerin dosya adı isteğe girmez. Talimat (`app/ai/prompts/type_description.md`): türü anlat, kişiyi değil (örnekteki ad, numara, tarih, MRZ içeriği yazılmaz); kısa yaz (katalog bütçesi, 11.4.2); serbest metin Türkçe, basılı başlık aslıyla. **Metin:** `format_description` tek satır üretir — düzen; `Başlıklar: A / B.`; `Dil: ru, en; alfabe: Kiril, Latin.`; `Alanlar: surname — …; ….`; `MRZ: 2 satır, ….` (yoksa `MRZ yok.` — yokluk da türü tanıtır); `Ön/arka yüz: ….`; boş liste ve `null` parça yazılmaz. **Panel ve "düzenlenebilir":** düzenleme formunda (türün örneği varsa ve formda analiz işaretliyse) "Örneklerden açıklama üret" düğmesi formu (`formaction`, "Kaydet"ten sonra — Enter kaydeder) `POST /document-types/{slug}/description`'a gönderir. Form 11.1.2 doğrulamasından geçer (geçersizse 422, istek gitmez); açıklama formdaki (kaydedilmemiş) tür bilgileriyle istenir, slug adresten gelir. Başarıda 200: form aynı değerlerle, `prompt_description` üretilen metinle yeniden çizilir; üstünde yapılandırılmış hâl, kullanılan sayfalar, gönderilmeyen sayfa sayısı ve atlanan örnekler. **Hiçbir şey kaydedilmez** (tür satırı, olay, dosya — testle); İK metni düzenleyip "Kaydet" (11.1.1'in yolu) ile kaydeder ve kayıt bir sonraki analizin talimatına girer (testle). "Yeniden üret" aynı düğmedir. Hatalar: örnek yok ya da hiçbiri açılmıyor 422 (atlananlar adıyla), analiz edilmeyen tür 422, sağlayıcı kurulamıyor 503, sağlayıcı yanıt vermedi (`ProviderError`, mesajıyla) ya da yanıt şemaya uymadı 502; hepsinde form değerleri korunur. Veritabanı işlemi sağlayıcı çağrısından önce bırakılır (uzun çağrıda SQLite yazma kilidi tutulmaz); sağlayıcı `get_description_provider` bağımlılığıyla kurulur. **Girişler:** görevin yüzeyi `app/catalog/describe.py` + `app/ai/` (`type_description.py`, `provider.py`, `anthropic_provider.py`, `openai_provider.py`, `recording_provider.py`, `prompts/type_description.{md,py}`, dışa aktarımlar); ayrıca `app/pipeline/render.py` (bellekte render yardımcıları `render_pdf_images`, `image_copy`; var olan `render_pdf_pages`/`render_image_copy` bunları kullanır, davranışları aynı), `app/web/routers/catalog.py`, şablonlar `catalog_form.html`, `catalog_description.html` (yeni), `catalog_examples.html`, `panel.css`, `app/catalog/__init__.py` (yalnız belge metni: `describe` dışa aktarılmaz — `app.ai` ↔ `app.catalog` içe aktarma döngüsü), `tests/web/test_access_log.py` (10.9.1 kilidinin gözden geçirilmiş POST listesine `POST /document-types/{slug}/description`) ve `tests/web/test_catalog_examples.py` (örnek yüklemeden önce/sonra form karşılaştırması düğmelerden önceki alanlara daraltıldı — örnek varken düğme çıkar) dokunuldu. Yalnız `TestClient`: tarayıcıda çizim görülmedi; canlı sağlayıcı çağrısı yapılmadı.
- **C63** — Profil fotoğrafı kural seti (tm 80, 11.6.1): PRD yalnız "Kurallar katalogda tutulur ve panelden açılıp kapatılabilir" der; kuralların listesi, saklama biçimi, varsayılanlar ve açma-kapamanın arayüzü yazılı değil. Tarihi plan (`docs/UYGULAMA-PLANI-KAYNAK.md` 5.1.1–5.1.2) listeyi sayar — yüz görünür, tek kişi, nötr ifade, sade arka plan, asgari çözünürlük, güneş gözlüğü yok, baş örtüsü kabul durumu (şirket kararı) — ve kuralların katalog ekranından açılıp kapatılmasını ister; bunlar esas alındı. **Sözleşme** `app/catalog/photo_rules.py`: yedi kural (`PHOTO_RULE_SPECS`: `face_visible`, `single_person`, `neutral_expression`, `plain_background`, `min_resolution`, `no_sunglasses`, `no_head_covering`; her birinin Türkçe adı ve açıklaması var), `known_document_types.photo_rules` sütununda (§8.6, JSON; göç yok) `{kural: {"enabled": bool}}`, çözünürlük kuralı ayrıca `min_width_px`/`min_height_px` (1–20000 piksel). **Okuma toleranslı** (`read_photo_rules`): kayıt `None`/sözlük dışı, kuralın girişi eksik ya da bozuk → kuralın varsayılanı, tanımsız anahtar yok sayılır; `CatalogEntry.photo_rules` serbest sözlük kaldığı için katalog kural seti yüzünden okunamaz olmaz. **Yazma katı** (`build_photo_rules`): bütün kurallar açıkça yazılır, tanımsız kural ve geçersiz piksel `PhotoRulesError` (alan başına), piksel sınırı çözünürlük kuralı kapalıyken de denetlenir. `enabled_photo_rules` yalnız açık kuralları verir — 11.7'nin okuyacağı yüzey; kapalı kural değerlendirilmez. **Yalnız Profile Picture:** `PHOTO_RULE_TYPES = {profile_picture}` (K12'nin görsel türü, PRD başlığı "profil fotoğrafı"); `set_photo_rules` başka türde `PhotoRulesUnsupportedError`, panel 404 verir. **Panel:** Profile Picture düzenleme sayfasında tür formunun altında, örnek belgelerin üstünde ayrı bir form (`catalog_photo_rules.html`): her kural bir işaret kutusu, çözünürlük için iki sayı alanı; `POST /document-types/{slug}/photo-rules` bütün seti tek işlemde yazar ve `.../{slug}?notice=photo_rules#photo-rules`'a yönlendirir (sayfada "Fotoğraf kuralları kaydedildi."); geçersiz değer 422 ile alan başına, girilen değerler yerinde, hiçbir şey yazılmaz. Tür formu (11.1.1) kuralları hâlâ değiştirmez. Yazma veritabanına gider, `catalog.yaml`'a değil (11.1 ile aynı); dışa aktarım kural setini taşır. **Bu görev değerlendirmez:** fotoğrafın pass/fail/unsure'ı, piksel ölçümü ve fail → Unresolved 11.7'nindir; kurallar analiz talimatına (11.4) girmez.
- **C64** — Profil fotoğrafı görsel kontrolü (tm 81, 11.7.1, 11.7.2): PRD yalnız "Her kural pass/fail/unsure olarak değerlendirilir; fail varsa Unresolved" ve "Kırpma, düzeltme ve arka plan değiştirme yapılmaz" der; değerlendirmenin yeri, sonucun nerede durduğu ve `unsure`'ın etkisi yazılı değil. Tarihi plan (`docs/UYGULAMA-PLANI-KAYNAK.md` 5.2.1–5.2.5) esas alındı: kurallar pass/fail/unsure döner, çözünürlük deterministik (piksel boyutu), fail → Unresolved ve gerekçe kural adlarıyla, `unsure` yalnız not, "iki yüz" ve "düşük çözünürlük" Unresolved'a düşer. **Nerede:** analiz adımında (`app/pipeline/analyze.py` `check_page_photo`): sayfa analizi fotoğraf türü (`PHOTO_RULE_TYPES`, en az bir kuralı açık; `PageAnalysisInstructions.photo_rules`, talimatla aynı katalogdan) ve boş olmayan sayfa verince ayrı bir yapay zekâ isteği (`AnalysisProvider.check_photo`, zorlanmış `record_photo_check` aracı/işlevi, talimat `app/ai/prompts/photo_check.md`) yapılır; kurallar sayfa analizi talimatına girmez (11.4 bütçesi, C63). Sağlayıcıya yalnız işlenen sayfanın analiz görüntüsü gider. **Sözleşme** `app/ai/photo_check.py` `PhotoCheck`: `rules` = `{rule, result: pass|fail|unsure, note (≤200) | null}`, her kural bir kez; yanıt kabulü sorulan kuralların tam kümesini ister (eksik ya da sorulmayan kural → `PhotoCheckError`; yanıttan gelen kimlik mesaja konmaz). **Çözünürlük** yapay zekâya sorulmaz: `app/pipeline/render.py` `photo_pixel_size` kaynaktan ölçer — JPEG/PNG'de EXIF yönelimiyle görünen boyut, PDF'te tek tam sayfa gömülü görüntünün (02.5.1; `extract_image`'in çıkaracağı) piksel boyutu; ikisi de asgariyi karşılıyorsa pass, biri karşılamıyorsa fail, not `300×400 piksel; asgari 400×400.`; sayfa tek gömülü görüntü değilse unsure (D36e). **Saklama:** sonuç katalog sırasıyla `pages.photo_check_json`'a (yeni sütun, göç 0005) yazılır, `PAGE_ANALYZED` verisine kural → sonuç eklenir (not olaya girmez); başarısız, atlanan ya da fotoğraf olmayan yeniden analiz kaydı boşaltır. Kontrol yapılamazsa sayfanın analizi düşer (D36d). **Hüküm planda** (`app/pipeline/plan.py` `check_photo_rules`, `PhotoRulesNotMet`): türün planlama anındaki açık kuralları sayfaların saklı kontrolüyle karşılaştırılır (K9: yapay zekâya yeniden sorulmaz); bir sayfada fail → Unresolved (`Fotoğraf kurallarına uymuyor (11.7.1): Tek kişi; Asgari çözünürlük (300×400 piksel; asgari 400×400).` — yapay zekânın notu gerekçeye girmez), sonucu olmayan açık kural → Unresolved (`Fotoğraf kuralları değerlendirilmedi (11.7.1): …`, D36c), unsure rota vermez, kapalı kural okunmaz. Gerekçe doğrulayıcılarınkinden sonra, işlem gerekçesinden önce gelir; ihlal belge düzeyinde ret sayılır, D29'un sahibi onu ezmez. Doğrulayıcı (`ValidationName`) değildir: planın `validations` listesi 06.5.1'in yedisi kaldı, `VALIDATION_FAILED` yazılmaz. **11.7.2:** kontrol hiçbir dosya yazmaz; fotoğrafın çıktısı §20.3'ün kayıpsız işlemidir (ihlal eden fotoğrafı İK atasa da çıktı gömülü görüntünün kendisi); kırpma/düzeltme/arka plan işlemi yoktur, eklenmedi. **Test verisi:** sentetik vesikalığın varsayılan boyutu 300×400 → 480×600 (tohumun 400×400 asgarisini karşılasın; S3/S4 Hazir kaldı), `people` ile "iki kişi" silueti; `profile_picture_page` kontrolün kayıtlı yanıtını taşır, `recorded_provider` onu analiz kaydının hemen ardından verir (`batch_responses`; `batch_analyses` ve `recordings/` dizinleri yalnız sayfa analizi kaldı). **Girişler:** görevin yüzeyi `app/pipeline/analyze.py` + `app/ai/prompts/` (`photo_check.{md,py}`, `page_analysis.py`, `__init__.py`); ayrıca `app/ai/photo_check.py` (yeni), `provider.py`, `anthropic_provider.py`, `openai_provider.py`, `recording_provider.py`, `app/ai/__init__.py`, `app/db/models.py` + `alembic/versions/0005_pages_photo_check.py`, `app/pipeline/render.py` (ölçüm) ve `app/pipeline/plan.py` (hüküm) dokunuldu; testlerde `tests/fixtures/gen.py`, `tests/pipeline/test_plan.py` (`_upload` fotoğraf sayfasına analizin saklayacağı kontrolü yazar), `test_group.py` ve iki kayıtlı S4/S3 testi (kontrol kaydı araya girer), `tests/db/test_migrations.py` (0005).
- **C65** — Fotoğraf örneklerinden öğrenme (tm 82, 11.8.1): PRD yalnız "Kabul edilen fotoğraflar örnek işaretlenir ve açıklamayı besler" der; "kabul edilen"in tanımı, işaretin nerede durduğu, beslemenin yolu ve kimin tetiklediği yazılı değil. Tarihi plan (`docs/UYGULAMA-PLANI-KAYNAK.md` 5.3.1–5.3.2): "İK'nın kabul ettiği fotoğraflar örnek olarak işaretlenebilir"; "3.3'teki açıklama üretimi bu örneklerle 'şirketin kabul ettiği fotoğraf' tanımını üretir ve `prompt_description`'a ekler". **Kabul edilen fotoğraf** (`app/catalog/describe.py` `is_accepted_photo`, `accepted_photos`): fotoğraf türünün (`PHOTO_RULE_TYPES`) `active` çıktı belgesi (Hazir) ve kökenindeki (`source_refs_json`; boş sayfa listesi dosyanın bütün sayfaları) her kaynak sayfanın saklı kontrolünde (`pages.photo_check_json`, 11.7.1) türün **kayıtlı ve şu an açık** her kuralı `pass`. `fail` (İK Unresolved'dan atasa da), `unsure` (Hazir'a girer ama kabulü kesin değil), değerlendirilmemiş kural (kontrol yok, okunamayan kayıt, kural sonradan açıldı), eski sürüm (K18), arşiv ve bozuk köken örnek değildir; açık kural yoksa örnek yoktur; kapatılan kuralın sonucu okunmaz. **İşaret kendiliğindendir ve saklanmaz:** PRD edilgen yazar ("işaretlenir") ve K16'nın manuel işlem listesi kapalıdır; işaret her okumada kayıtlardan çıkarılır (göç yok, `documents`'a sütun yok), kural seti değişince işaret de değişir; sıra yeniden eskiye. **Açıklamayı besler:** `describe_type(..., photos=)` fotoğraf türünde kabul edilen fotoğrafları örnek sayfalardan sonra aynı isteğe koyar (öteki türde yok sayılır); her fotoğraf tek görüntüdür — Hazir dosyasının JPEG/PNG'sinin EXIF yönelimli bellek kopyası ya da PDF'in ilk sayfasının render'ı; dosya okunur, değiştirilmez, kopyalanmaz. Sınır (`MAX_DESCRIPTION_PAGES = 8`) paylaşılır: fotoğraf varsa `min(fotoğraf sayısı, 4)` yer ayrılır, örnek sayfalar kalanı alır, örneklerin kullanmadığı yer fotoğraflarındır. Açılamayan fotoğraf (dosya yok, bozuk, desteklenmeyen içerik, sayfasız PDF, geçersiz saklı yol, boyut sınırı) atlanır, sınırı tüketmez ve belge numarasıyla bildirilir (dosya adı çalışanın adıdır). Kullanıcı metninde "Fotoğraf türü: evet" satırı ve "n. kabul edilen fotoğraf k" sırası; belge kimliği, yol, çalışan bilgisi yok. **Sözleşme:** `TypeDescription.accepted_photo` (≤200 karakter ya da `null`) — şirketin kabul ettiği fotoğrafın ortak çekim özellikleri; her anahtar zorunlu olduğundan kayıtlı yanıt (`tests/fixtures/ai/type_descriptions/passport/0.json`) ve `description_payload` `null` taşır. `format_description` metnin sonuna `Kabul edilen fotoğraf: ….` ekler; fotoğraf türü olmayan türün yanıtında dolu `accepted_photo` `TypeDescriptionError`dır (düzeltilmez). Talimat (`type_description.md`): fotoğraftaki kişi tarif edilmez (yüz hatları, saç, ten rengi, yaş, cinsiyet, köken), yalnız çekim (kadraj, arka plan, ışık, renk, baş ve bakış); ortak özellik yoksa `null`. **Kaydedilmez:** 11.3.1'in akışı aynen — üretim öneridir, İK düzenleyip Kaydet'le `prompt_description`'a yazar (D37c). **Panel:** Profile Picture düzenleme sayfasında fotoğraf kurallarının altında "Kabul edilen fotoğraflar" bölümü (`catalog_accepted_photos.html`): sayı; en yeni 8'i "Belge n", tarih ve "örnek" etiketiyle köken sayfasına (`/documents/{id}/history`) bağlantı; fazlası "daha eski n". Fotoğrafın kendisi gösterilmez (açmak erişim kaydı ister, 10.9.2). "Örneklerden açıklama üret" yüklenmiş örnek olmasa da kabul edilen fotoğraf varken çıkar; sonuçta kullanılan fotoğraflar bağlantıyla, gönderilmeyen sayısı, atlananlar ve "Kabul edilen fotoğraf" tanımı gösterilir. Yeni yol yok; kabul edilen fotoğraflar sağlayıcı çağrısından önce okunur ve işlem bırakılır (`_accepted_photos`). **Girişler:** görevin yüzeyi `app/catalog/describe.py`; ayrıca `app/ai/type_description.py` (alan), `app/ai/prompts/type_description.{md,py}`, `app/web/routers/catalog.py` (`_accepted_photos`; `_photo_context` oturumu alır), şablonlar `catalog_accepted_photos.html` (yeni), `catalog_form.html`, `catalog_description.html`, `panel.css`; testlerde `tests/fixtures/accepted_photos.py` (yeni), `tests/ai/payloads.py`, `tests/ai/test_type_description.py`, kayıtlı yanıt ve `tests/test_scenarios_s01_s05.py`. Yalnız `TestClient`: tarayıcıda çizim görülmedi; canlı sağlayıcı çağrısı yapılmadı.

- **C66** — Telegram botu iskeleti ve beyaz liste (tm 83, 12.1.1, 12.1.2): PRD yalnız "Bot ayrı servis olarak çalışır; geliştirmede polling, üretimde webhook" ve "Listede olmayan kullanıcıya yanıt verilmez" der; servisin nasıl başladığı, ayarları, beyaz listenin kaynağı ve "yanıt verilmez"in kapsamı yazılı değil. Tarihi plan (`docs/UYGULAMA-PLANI-KAYNAK.md` 0.2.1, 4.1.1–4.1.4) esas alındı: python-telegram-bot, her güncellemede `telegram_users` süzgeci, `/start` ve `/yardim`, ayrı Docker servisi, `TELEGRAM_BOT_TOKEN` ayarı. **Süreç:** `app/telegram/bot.py` `main()` — `python -m app.telegram.bot`; Compose'ta `bot` servisi (`profiles: [telegram]`, aynı imaj; token'sız `docker compose up` onu başlatmaz, `docker compose --profile telegram up bot` başlatır). **Mod:** `APP_ENV=production` → webhook, aksi halde polling (yeni ayar yok; PRD "geliştirmede/üretimde"yi ortama bağlar). **Ayarlar** (`app/config.py`): `TELEGRAM_BOT_TOKEN` (zorunlu), `TELEGRAM_WEBHOOK_URL` (üretimde zorunlu, https; yol kısmı dinlenen yoldur), `TELEGRAM_WEBHOOK_SECRET` (üretimde zorunlu; 1–256 karakter `[A-Za-z0-9_-]`), `TELEGRAM_WEBHOOK_LISTEN` (`127.0.0.1`) ve `TELEGRAM_WEBHOOK_PORT` (`8443`); doğrulama bot başlarken (`load_bot_config` → `BotConfigError`, iletide değer yok, çıkış kodu 1; geliştirmede webhook ayarları yok sayılır). **Beyaz liste:** `telegram_users` satırı ve `allowed` doğru (`is_whitelisted`); tablo 0001 göçünde zaten var — göç yok. **Kapı:** `WhitelistGate` (`TypeHandler(Update, …)`, `GATE_GROUP = -1`) her güncellemeyi öteki işleyicilerden önce süzer; izin yoksa `ApplicationHandlerStop` — hiçbir yanıt (`answerCallbackQuery` dahil) gitmez. Kapı gönderen ya da sohbet bilinmiyorsa, sohbet özel değilse, kullanıcı listede değilse ve liste okunamıyorsa (hata durumunda kapalı: python-telegram-bot işleyici hatasından sonra sonraki gruplara geçer) reddeder. Yeni işleyiciler `HANDLER_GROUP` (0) ve üstüne eklenir. **Komutlar:** `/start` ve `/yardim` aynı yardım metnini yanıtlar ("Belge gönderme ve belge isteme henüz etkin değil" — 12.2/12.3 gelene kadar doğru); başka mesaja yanıt yok. **Güncelleme türleri:** yalnız `message` ve `callback_query` istenir (`HANDLED_UPDATES`). **Loglar:** `httpx`/`httpcore` INFO'da token'lı adres yazdığı için `main()` onları WARNING'e çeker; bot hata iletisi token ve webhook gizli değeri maskelenerek yazılır; reddedilen güncelleme için yalnız `update_id` (kimlik ve içerik yok, CONVENTIONS §6). **Bağımlılık:** `python-telegram-bot[webhooks]>=22` (webhook sunucusu tornado ister); yerelde `uv pip install --python .venv/Scripts/python.exe "python-telegram-bot[webhooks]>=22"` gerekti. GİRDİ'de adı geçen `app/pipeline/orchestrate.py` 12.1'de kullanılmadı — belge alma 12.2'nin işi.

- **C67** — Telegram'dan belge alma (tm 84, 12.2.1, 12.2.2, 12.2.3): PRD yalnız "Gönderilen belge web ile aynı boru hattından işlenir", "Aynı medya grubundaki dosyalar tek parti sayılır" ve "İşlem sonucu ve kuyruğa düşen öğeler kısa mesajla bildirilir" der; hangi mesaj türlerinin alınacağı, albümün nasıl birleşeceği, adların, sınırların ve özetin içeriği yazılı değil. **Aynı boru hattı:** `create_upload`'ın çekirdeği (ad denetimi, boyut/sayfa sınırı 01.3.1, Inbox'a değişmez yazma K10, tekrar tespiti 01.4.1, `FILE_UPLOADED`/`FILE_DUPLICATE`) `app/web/routers/uploads.py`'de eşzamanlı `store_upload(session, layout, settings, files, channel=, uploaded_by=)` olarak çıkarıldı; web uç noktası ve bot aynı işlevi çağırır (web davranışı değişmedi), sonra bot aynı `process_upload`'ı çalıştırır (render → analiz → plan → uygulama). Fark yalnız `uploads.channel = telegram` ve `uploaded_by` = beyaz listedeki kullanıcının panel kullanıcı adıdır. **Alınan mesajlar** (`app/telegram/handlers.py` `DocumentIntake`, `HANDLER_GROUP`'ta `MessageHandler(Document.ALL | PHOTO)`): dosya eki (her tür — Word/Excel dahil, K2 boru hattında karar verir) ve fotoğraf (Telegram'ın verdiği en büyük boyut); ad sadeleştirilir (`/ \ : * ? " < > |` ve denetim karakterleri `_`, 255 karakter), adsız belge `belge_<kimlik><uzantı>`, fotoğraf `foto_<kimlik>.jpg`. Metin, ses, video ve başka medya alınmaz (yanıt yok). **Albüm:** aynı `(sohbet, media_group_id)` dosyaları biriktirilir; son dosyadan `GROUP_WAIT_SECONDS` (2 sn) yeni dosya gelmezse tek parti açılır, dosyalar mesaj numarasıyla sıralanır; albümde aynı ad tekrarlarsa (büyük/küçük harf duyarsız) `-2`, `-3` eki alır (aynı partide aynı ad olmaz); süre dolduktan sonra gelen dosya yeni partidir; albüm dışı her mesaj kendi partisidir. İşleyici hemen döner, indirme/kayıt/işleme arka plandadır (`asyncio` görevi, işlem `to_thread`'de). **Sınırlar:** bildirilen boyut `MAX_UPLOAD_FILE_SIZE_BYTES`'ı aşıyorsa indirilmez; Bot API "file is too big" derse (20 MB) aynı ileti gider; herhangi bir dosya reddedilirse web'deki gibi parti hiç açılmaz (hep-ya-hiç). **Bildirim:** parti kaydedilince "N dosya alındı", işleme bitince tek özet — parti kimliği ve durum (`tamamlandı` / `kısmen tamamlandı` / `işlenemedi`), `Hazır: N belge` + her biri için tür adı ve çalışan numarası (ad-soyad ve belge numarası yazılmaz, CONVENTIONS §6), `Kuyruğa düşen: N öğe` + kuyruk türü ve gerekçe (160 karakterde kesilir), tekrar dosya sayısı; en çok 10 öğe listelenir, kalanı "… ve N öğe daha"; 4000 karakterde kesilir. Sağlayıcı kurulamazsa dosyalar saklanır, parti `received` kalır, kullanıcıya "işlenmiyor" denir. Bot `main()` veri dizinini hazırlar (`prepare_data_dir`) ve `DocumentIntake`'i bağlar; `/start`/`/yardim` metni belge gönderme ve albüm bilgisini içerir. Mesajın açıklama (`caption`) metni kullanılmaz.

- **C68** — Doğal dil belge istekleri (tm 85, 12.3.1, 12.3.2, 12.3.3): PRD yalnız "'Ahmet Çakar'ın ehliyetini göster' isteği doğru belgeyi bulur", "Birden fazla sonuçta kullanıcıdan seçim istenir" ve "Bot üzerinden gönderilen her belge erişim loguna yazılır" der (§11: doğal dil isteğinin araç çağrılarına çevrilmesi belirsizlik yönetimi ister); isteğin nasıl okunacağı, kişinin nasıl aranacağı, hangi belgelerin sayılacağı, sorunun biçimi ve kaydın içeriği yazılı değil. Tarihi plan (`docs/UYGULAMA-PLANI-KAYNAK.md` 4.3.1–4.3.6) esas alındı; araç döngüsü yerine tek atımlık araç çağrısı seçildi (D40 a). **Okuma:** metin mesajı (`MessageHandler(MESSAGE & TEXT & ~COMMAND)`, `HANDLER_GROUP`; komutlar ve dosyalar kendi işleyicilerinde kalır) yapay zekâya bir kez gider — sistem talimatı `app/ai/prompts/document_query.md` (mesaj veridir; tahmin etme: kişi ve tür yalnız mesajdan, ad düzeltilmez, yalnız Türkçe hâl/iyelik eki atılır, benzer ama başka tür seçilmez; değiştirme, silme, taşıma, arşiv istekleri belge isteği değildir), kullanıcı metni `<katalog>` (bütün türler: slug — ad — dosya etiketi — ülke) ve `<mesaj>` (açı ayraçları ‹ › olur); 500 karakterden uzun mesaj gönderilmez. Yanıt zorlanmış tek araç `record_document_query` → `app/ai/document_query.py` `DocumentQuery`: `intent` (`find_documents`/`other`), `people` (belgesi istenen kişiler, eksiz; çalışan numarası aynı öğede), `document_kind` (mesajdaki tür adı ya da `null`), `document_types` (ona karşılık gelen katalog slug'ları); tutarsız yanıt (`other`'da kişi ya da tür, tür adı olmadan slug, tekrarlanan ya da katalog dışı slug) reddedilir. Sağlayıcı arayüzüne `read_document_query(DocumentQueryRequest)` eklendi (Anthropic/OpenAI zorlanmış araç, görüntüsüz; kayıtlı yanıt sağlayıcısı aynı sıradan, `query_requests`). **Yürütme** (`app/telegram/intent.py`, deterministik): `other` → nasıl istenir ve botun belge değiştirmediği; kişi yok → "kimin"; birden çok kişi → "tek çalışan"; tür adı var ama katalogda karşılığı yok → söylenir, arama yapılmaz. Kişi ifadesi `E\d{4,}` çalışan numarasına (kesme işaretli eki numaraya aittir) ve `normalize_name` kelimelerine ayrılır; çalışanın ad yazımlarından biri (ad-soyad, diğer isimlerle birlikte, orijinal yazım, her alias) aranan her kelimeyi tam kelime olarak (tekrarıyla) taşımalıdır; numara verilmişse yalnız o çalışan, ad da verilmişse ona uymalı. Belgeler: çalışanın `active` belgeleri (eski sürüm ve arşiv değil), tür verildiyse o türlerden, yeniden eskiye. **Belirsizlik (12.3.2):** tek çalışan ve tek belge doğrudan gönderilir; birden çok çalışan → önce çalışan sorulur (ad, E numarası, doğum tarihi, istenen türde belge sayısı), seçilince onun belgeleri; birden çok belge → belge sorulur (tür adı, dosya adı, tarih); en çok 10 seçenek, fazlası "… ve N daha" notuyla; düğme verisi `sec:<belirteç>:<sıra>`. Seçim belleği bot sürecinde (`ChoiceStore`): rastgele belirteç, tek kullanımlık, yalnız sorulan sohbet ve kullanıcı, 10 dk, aynı sohbette yeni soru eskisini düşürür, en çok 1000 bekleyen soru; seçilen sorunun düğmeleri kaldırılır, geçersiz basış uyarıyla yanıtlanır. **Gönderim ve kayıt (12.3.3):** belge dosyası olduğu gibi `sendDocument` ile gider (dosya adı Hazir'daki ad; açıklama tür + çalışan adı ve numarası); göndermeden önce `record_access(user_id=telegram_users.user_id, action=download, channel=telegram)` yazılır ve commit edilir — yazılamazsa belge gitmez; gönderim sonradan başarısız olursa kayıt kalır, kullanıcıya "gönderilemedi" denir (C55 ile aynı sıra). Belge artık etkin değilse, dosyası yoksa ya da veri dizininden kaçıyorsa, 50 MB Telegram sınırını aşıyorsa ya da hesap listeden çıkmışsa belge gitmez, kayıt yazılmaz. `events` satırı açılmaz (D38 d). Loglara yalnız hata türü yazılır; mesaj, ad, dosya adı yazılmaz. Yardım metni belge göndermeyi ve istemeyi anlatır.

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
- **D8 — Çelişkili kişi anahtarı §20.2.2'de yok, Unresolved'a alındı (05.5, tm 36).** 05.4 anahtarı
  adayın sayfaları bir kimlik alanını (belge numarası, ad/soyad, doğum tarihi, orijinal yazım) farklı
  okuduğunda alanı `conflicts`'e yazar; iki farklı numara taşıyan anahtar için satır 1'in "normalize
  belge numarası" tekil değildir, isim/doğum tarihi çelişkisi de sayfaların iki kişiye ait
  olabileceğini söyler. Tablo bu durumu yazmaz. Görev kuralı gereği en güvenli yön seçildi: `conflicts`
  doluysa **hiçbir satır denenmeden** hüküm `conflicting_key`, `action: none`, Unresolved, gerekçede
  çelişen alan adları, olay `PERSON_NOT_MATCHED` — numara tek bir çalışana ait olsa bile otomatik
  eşleştirilmez, yeni çalışan/onay bekleyen profil de açılmaz. Gruplama (04.1) `person` değerleri
  çelişen sayfaları zaten birleştirmediği için durum seyrektir (MRZ ya da `fields` okuması `person`'dan
  farklıysa doğar). Karar insana bırakıldı: yalnız orijinal yazım çelişkisi gibi zararsız görünen
  durumlar için tabloya satır eklenmeli mi.
- **D9 — Ad-soyadı okunmamış temiz numaralı belgeden çalışan açılmıyor (05.6.1, tm 37).** §20.2.2 satır
  6 yalnız "hiç eşleşme yok ve temiz belge numarası var" der; ad-soyad şartı yazmaz. Ama çalışan klasörü
  `Ad_Soyad_E0001` (K8) ve `employees.given_names`/`surname` zorunlu: ad ya da soyadı okunmamış
  (`required_fields`'ında numara olup isim olmayan bir tür, ya da isim parçası kelimesiz) veya klasör
  adına çevrilemeyen (slug'da karakter kalmayan, ör. Çince) anahtardan klasör kurulamaz. Tabloda
  karşılığı yok; görev kuralı gereği en güvenli yön seçildi: çalışan **açılmaz**
  (`can_create_employee` yanlış, `create_employee` reddeder), isim uydurulmaz, numaradan klasör adı
  türetilmez. Tohum katalogda numara isteyen her tür ad ve soyadı da ister ve 04.4 kapısı okunamayan
  zorunlu alanı Unreadable'a gönderir; durum bugün yalnız katalog dışı düzenlemeyle ya da slug'a
  çevrilemeyen yazıyla doğar. Bu belgenin hangi rotaya gideceği (satır 7'nin "ad-soyad okunabildi"
  şartı sağlanmadığı için onay bekleyen profil değil; satır 8 de "ne isim ne numara" der) 05.7'nin
  kararıdır — güvenli yön Unresolved, `action: none`. Karar insana bırakıldı: satır 6'ya ad-soyad şartı
  yazılmalı mı, çevrilemeyen yazı için klasör adı kuralı tanımlanmalı mı.
- **D10 — Satır 7–8'in arasında kalan eksik kişi Unresolved'a alındı, satır 7'ye klasör adı şartı
  okundu (05.7.1, tm 38).** Satır 7 "hiç eşleşme yok, temiz numara yok, ama ad-soyad okunabildi", satır 8
  "ne isim ne numara" der; arada kalan anahtarlar tabloda yok: (a) temiz numara var ama ad-soyad okunmamış
  ya da klasör adına çevrilemiyor (D9'da satır 6'dan çıkan durum; satır 7 temiz numaranın olmamasını
  ister); (b) ad-soyad okunmamış ama temiz olmayan bir numara, orijinal yazım ya da tek bir ad/soyad parçası
  okunmuş (satır 8'in "ne isim ne numara"sı tutmaz). Görev kuralı gereği en güvenli yön seçildi:
  `incomplete_person`, `action: none`, Unresolved, gerekçede okunamayan ve temiz numaranın varlığı (değer
  yok); profil **önerilmez**. Satır 7'nin "ad-soyad okunabildi" şartı D9'daki gibi okundu: ad-soyadı klasör
  adına çevrilemeyen (ör. Çince) anahtar da onay bekleyen profil olmaz — onay (08.3.1) çalışanı
  `Ad_Soyad_E0001` klasörüyle açacağından onaylanamayacak öneri üretilmedi. İki yön de belgeyi Unresolved'a
  götürür, fark yalnız öneridir. Karar insana bırakıldı: eksik kişi için tabloya satır eklenmeli mi;
  çevrilemeyen yazıya klasör adı kuralı (D9) tanımlanırsa satır 7 genişletilmeli mi.
- **D11 — Birikimde yalnız temiz numara ekleniyor ve ayrı olay atılmıyor (05.7.2, tm 38).** PRD "Satır 1
  ve 3'te eşleşme başarılıysa … yeni belge numarası `employee_identifiers`'a eklenir" der, okumanın
  kalitesini yazmaz. Okunaksız, 5 karakterden kısa ya da MRZ haneleri tutmayan yanlış bir okuma çalışana
  eklenirse, gerçek numarası o okumaya denk gelen başka bir kişinin belgesi sonradan satır 1'le bu çalışana
  **otomatik** eşleşir ve yanlış çalışanın Hazir'ına düşer; eklenmezse en kötü sonuç o numarayla gelen
  belgenin isim + doğum tarihine, Unresolved'a ya da mükerrer profile düşmesidir (İK taşımasıyla düzelir,
  D7). Güvenli yön seçildi: numara yalnız §20.2.3'ün üç koşulunu sağlıyorsa eklenir; isim yazımları
  koşulsuz eklenir (isim tek başına eşleşme vermez, R8). **Olay:** K15 her adımın loglanmasını ister ama
  §8.3'ün kapalı listesinde alias/numara eklemeye tür yok (D6 ile aynı soru); eşleştirme hükmü dosya, sayfa
  ve çalışanla `PERSON_MATCHED`'te zaten var, yeni tür eklenmedi ve başka bir türün anlamı zorlanmadı —
  hangi yazımın hangi belgeden geldiği logda yok. Karar insana bırakıldı: okunaklı ama temiz olmayan numara
  da eklenmeli mi; §8.3'e çalışan kaydı güncellemesi için bir olay türü eklenmeli mi.
- **D12 — Kişi taşımayan belge (profil fotoğrafı) S3/S4'ün beklediği çıktıyı vermiyor (06.1, tm 40).** §9
  S3 "Profile-Picture.jpeg (2)", S4 "Üç bağımsız çıktı" bekler; fotoğrafta ne isim ne numara vardır ve
  §20.2.2 satır 8 "kişi hiç tespit edilemedi → `none`, `unresolved`" der. Sahibi aynı dosya ya da partideki
  kimlikli belgelerden çıkarmak (tek kişi varsayımı) veya yükleme bağlamını (K2 yalnız Word/Excel için
  yazar) analizli belgeye genişletmek PRD'de yok; ikisi de uydurma olurdu. Tablo uygulandı: fotoğraf
  Unresolved'a gider (`test_s4_recorded_pdf_with_registered_employee_plans_three_documents` sabitler), S3/S4'ün
  fotoğraf çıktısı bu hâliyle 09.3-b'de tutmaz. Ayrıca S3 kaydında kayıtlı çalışan yoksa çalışma izni
  (doğum tarihi yok) çalışanı açar ve oturma izni onunla yalnız isimden eşleşir (satır 5, Unresolved) — S3
  testi çalışanı numaralarıyla önceden kaydetmeli. Karar insana bırakıldı: kişi taşımayan tür için sahip
  kuralı (bağlam çalışanı, aynı dosyada tek çalışana bağlanan kimlikli belge ya da yalnız İK ataması)
  tanımlanmalı mı; S3/S4 beklentisi buna göre mi okunmalı.
- **D13 — Kuyruğa giden belgeden çalışan açılmıyor, kimlik ve iletişim bilgisi birikmiyor (06.1, tm 40).**
  §20.2.2 satır 6 "hiç eşleşme yok ve temiz numara var → `create`" ve satır 1/3 birikimi (05.7.2) belge
  düzeyindeki hükümleri (04.2–04.6) anmaz; hangisinin önce uygulanacağı yazılı değil. Zorunlu alanı okunmayan
  (K1), kabul kriteri karşılanmayan, parça ya da sayfa sayısı tutmayan belgeden çalışan açılırsa Hazir'ında
  belgesi olmayan, okuması doğrulanmamış bir profil doğar (R9'un "temiz" şartı yalnız numaraya bakar); birikim
  de doğrulanmamış yazımı ya da numarayı çalışana bağlar (D11 gerekçesi). Güvenli yön seçildi: yan etkiler
  yalnız belge düzeyinde hükmü olmayan adayda yürür; kuyruğa giden adayda yalnız `match_employee` çalışır ve
  hükmü kişi tahmini olarak öğede kalır. Aynı kişinin kabul edilen belgesi geldiğinde çalışan açılır. Karar
  insana bırakıldı: kuyruğa giden belgenin temiz numarası da çalışan açmalı mı.
- **D14 — Analizi yapılamamış sayfa ve işlenemeyen dosya Unresolved öğesi oldu (06.1, tm 40).** PRD kısmi
  analizde (03.7.2) başarısız sayfanın ve sayfası üretilmemiş, Word/Excel olarak da tanınmayan dosyanın
  rotasını yazmaz; plana girmezlerse sessizce kaybolurlar (R7). Güvenli yön seçildi: dosya başına tek
  `unresolved` öğesi (sayfalar ya da `pages: []`), tür `null`, çalışan `none`; Unknown seçilmedi — türü
  tespit edilmemiş belge aday tür onayı akışına (11.5) girmesin. Boş sayfa (S8) ve tekrar dosyası (S2) çıktı
  ve kuyruk üretmeyen `skip` öğesidir (`skip` §8.5'te var; kaynak plan onu boş sayfa için yazmıştı). Karar
  insana bırakıldı: başarısız sayfa için ayrı kuyruk ya da otomatik yeniden analiz istenir mi.
- **D15 — PNG profil fotoğrafı §20.3'te hiçbir işleme uymuyor (06.2.1, tm 41).** Tohum katalog (C7)
  `profile_picture` için `expected_file_types: [jpeg, png, pdf]`, `output_format: jpeg`,
  `allowed_conversions: [extract_image, render_image]` der. §20.3'te PNG kaynaktan JPEG hedefe satır yok:
  satır 1 aynı biçim, satır 4 PDF hedef, satır 5/6 PDF kaynak ister; PNG'yi JPEG'e yeniden kodlamak K11'in
  izinli işlemleri arasında da yok. Tablo uygulandı, dönüşüm uydurulmadı: PNG profil fotoğrafı satır 7 ile
  Unresolved'a gider (`test_without_a_matching_row_no_operation_is_selected_and_the_reason_is_written[png-to-jpeg]`).
  Bugün fotoğraf kişi taşımadığı için zaten Unresolved'dadır (D12); D12 çözülse de PNG fotoğraf kuyruğa düşer.
  Karar insana bırakıldı: `profile_picture` çıktısı `keep` mi olmalı, `png` beklenen türlerden mi çıkmalı,
  yoksa tabloya (kayıplı) bir PNG→JPEG satırı mı eklenmeli.
- **D16 — MRZ kontrol hanesi tutmayan belge Unresolved'a gidiyor, çalışan kararına ulaşmıyor (06.5, tm 44).**
  §20.1.7 alan hanesi tutmazsa yalnız "o alan geçersizdir, diğer alanlar kullanılabilir", bileşik hane tutmazsa
  "alanlar kullanılabilir ama `document_number` temiz sayılmaz" der; §20.2.3 temiz olmayan numarada satır 7'yi
  (onay bekleyen profil) uygular. Aynı PRD 05.3.2'de "kontrol hanesi tutmayan MRZ geçersiz sayılır", 06.5.2'de
  "başarısız doğrulama rotayı Unresolved yapar" der; §20.1.7'nin "hata sayılmaz / doğrulama hatası değildir"
  istisnaları (dolgu isteğe bağlı veri, görünen metinle çelişki) öteki durumların doğrulama hatası olduğunu
  gösterir. Güvenli yön seçildi: herhangi bir hane tutmazsa `mrz_checksum` geçmez, belge Unresolved'a gider;
  §20.1.7'nin okuma sonuçları (alan okunamadı, numara temiz değil) 05.3.3'te ayrıca uygulanmaya devam eder
  (zorunlu alansa Unreadable önce). Sonuç: bileşik hanesi tutmayan yeni kişinin belgesi satır 7'ye değil (D13
  gereği kuyruğa giden belgeden profil önerilmez) doğrulama gerekçesiyle Unresolved'a gider; kayıtlı çalışanla
  numarası eşleşen ama bileşik hanesi tutmayan belge de Hazir'a değil Unresolved'a gider (kişi tahmini `match`).
  Zorunlu olmayan bir alanın hanesi tutmayan belge de Unresolved'dır. Pratikte tek karakterlik okuma hatası hem
  alan hem bileşik haneyi bozar. Karar insana bırakıldı: `mrz_checksum` yalnız belge düzeyinde hükme (bileşik
  hane / geçersiz MRZ) mi bakmalı, alan hanesi hatası yalnız alanı mı düşürmeli, bileşik hane hatasında belge
  çalışan kararına (satır 1/3 eşleşme, satır 7 profil) devam mı etmeli.
- **D17 — img2pdf alfa kanallı PNG'yi reddetmiyor; saydamlık düzleştirilmeden `/SMask` olarak saklanıyor (07.3.1,
  tm 48).** §20.5 `wrap_image` "img2pdf alfa kanalı içeren PNG'leri reddeder; görüntü alfasız RGB'ye (beyaz zemin)
  düzleştirilir ve olay loguna yazılır" der. Kurulu img2pdf 0.6.3 8 bit RGBA/LA PNG'yi reddetmez: renk kanallarını
  ve alfa kanalını ayrı iki kayıpsız görüntüye (`/SMask`) böler; yalnız 8 bitten derin alfalı görüntüde
  `AlphaChannelError` verir. `merge` kütüphanenin davranışını olduğu gibi kullandı: alfalı PNG düzleştirilmez,
  olay atılmaz, renk ve alfa pikselleri kaynakla birebir
  (`test_execute_merge_keeps_png_alpha_as_soft_mask_without_flattening`); `AlphaChannelError` `MergeSourceError`
  olur. Düzleştirme bir piksel dönüşümüdür ve artık gerekmediği için uydurulmadı. Karar insana ve 07.4'e
  bırakıldı: `/SMask` saklama kabul mü, yoksa §20.5'teki düzleştirme + olay kütüphane reddetmese de mi
  uygulanmalı (o zaman `merge`'ün görüntü sarması da aynı yola bağlanmalı).
- **D18 — §20.5'in beyaz zemine düzleştirmesi uygulanmadı: K11 içeriği hiçbir koşulda değiştirmez,
  MASTER-PROMPT çelişkide PRD'nin önünde (07.4.1, tm 49).** D17'nin sorusu buradaydı: img2pdf 0.6.3 yalnız
  >8 bit alfalı PNG'de (`AlphaChannelError`) reddeder, 8 bit alfayı `/SMask` olarak kayıpsız saklar. §20.5
  "alfa kanalı içeren PNG'ler... alfasız RGB'ye (beyaz zemin) düzleştirilir" der — bu bir piksel dönüşümüdür.
  K11 "İçerik hiçbir koşulda üretilmez, kırpılmaz veya değiştirilmez" der ve izinli işlemler listesinde alfa
  kompozisyonu yoktur; `MASTER-PROMPT.md` §2 çelişki sırası "bu dosya (MASTER-PROMPT) > PRD > PLAN.md" —
  kilitli kural PRD metnini geçersiz kılar. Karar: `execute_wrap_image` (ve `merge`'ün paylaştığı
  `_wrap_image_to_pdf`) >8 bit alfalı PNG'de ya da img2pdf'in sarılamadığı başka görüntüde düzleştirme
  denemez, `WrapImageSourceError`/`MergeSourceError` verir; belge kuyruğa gider, tahmin edilmez
  (CLAUDE.md'nin değişmez kuralı). 8 bit alfalı PNG (yaygın durum) zaten reddedilmediği için D17'nin
  gözlemi (`/SMask`, düzleştirme yok) değişmedi.
- **D19 — PyMuPDF `extract_image` her görüntüde orijinal gömülü baytları vermiyor; kanıtlanamayan çıktı kuyruğa
  gidiyor (07.5.1, tm 50).** §20.5 "dönen `image` alanı orijinal gömülü baytlardır; `ext` gerçek biçimi verir;
  JPEG değilse uzantı `ext`'e göre yazılır" der. Kurulu PyMuPDF 1.28.2 (`_make_image_dict`): DCTDecode/JPXDecode
  akışın sıkıştırılmış tamponunu olduğu gibi döndürür, ama CMYK JPEG'i (4 bileşen) kalite 95 ile **yeniden
  kodlar**; Flate/LZW/CCITT/JBIG2/süzgeçsiz görüntüde gömülü bir dosya yoktur, çözülmüş pikselleri PNG'ye yazar —
  gri/RGB/Indexed/1 bit birebir (ICCBased gri üç RGB kanalına aynı değerle), ama CMYK'yi RGB'ye **çevirir**, 16
  bitlik örneği 8 bite **indirir**. Bunlar K11/K12'nin kayıpsızlığını sessizce bozar. Güvenli yön seçildi: çıktı
  yalnız JPEG ya da PNG; yayından önce JPEG baytları PDF'teki ham akışla birebir aynı olmalı (CMYK yeniden
  kodlaması ve `[/FlateDecode /DCTDecode]` gibi zincirli süzgeç — ham bayt JPEG değil, orijinallik dosyadan
  kanıtlanamaz — `ExtractImageIntegrityError`), PNG pikselleri MuPDF'in gömülü görüntüden çözdüğü piksellerle
  birebir aynı olmalı (renk dönüşümü `ExtractImageIntegrityError`; boyut ve kip de karşılaştırılır, Pillow yalnız
  ölçer); 8 bitten derin görüntü ve JPEG 2000 (`jpx` — `detect_file_kind` tanımaz, K2'nin biçimlerinden değil)
  `ExtractImageSourceError`. Hepsinde belge kuyruğa gider, render'a düşülmez (K12, C33). Karar insana bırakıldı:
  JPEG 2000 çıktısı kabul mü; zincirli süzgeçteki ve CMYK JPEG'in orijinal baytları ham akıştan süzgeç çözülerek
  mi çıkarılmalı; Flate görüntünün kayıpsız PNG'si "orijinal bayt" sayılır mı (bugün sayılıyor).
- **D20 — `queue_items.payload_json`'da onay bekleyen profilin tam içeriği yok (08.1.1, 08.1.2, tm 54).**
  C29 (05.7.1) "önerilen profil plana girmez; 08.1 aynı saf adımlarla (`build_person_key` →
  `resolve_unmatched`) yeniden kurabilir" diyordu. `route_queue_item` (`app/pipeline/route.py`) bunu
  yapmadı: `ProposedProfile`'ı yeniden kurmak `app.matching.match`'e ve öğenin sayfa analizlerine
  (`pages.analysis_json`) bağımlılık ister — bu görevin GİRDİ'sü yalnız `plan.py` (§8.5 `PlanItem`) ve
  `execute.py`/`storage`'dı (Task Master görev detayı), eşleştirme modülü değil. `payload_json` (ve
  `reason.json`) şimdilik yalnız plan öğesinin kendi taşıdığı `document_type_slug`, `sources` ve
  `employee_guess` (`PlanEmployee`) üçlüsünü yazıyor; bu 08.1.1/08.1.2'nin kabul kriterini (hangi
  sayfalar, hangi kural, hangi tür, kişi tahmini) karşılıyor ama satır 7'nin önerilen profilini
  (ad-soyad, orijinal yazım, doğum tarihi, uyruk, alias adayları) taşımıyor. 08.3 (onay bekleyen
  profili onaylama) bu içeriğe ihtiyaç duyarsa ya `route_queue_item`'a eşleştirme bağımlılığı eklemeli
  ya da C29'un önerdiği gibi saf adımları kendi görevinde yeniden kurmalı. Karar insana bırakıldı.
  **08.3 (tm 56):** ikinci yol seçildi (C42) — onay profili saklanan analizlerden yeniden kurar ve hükmü onay
  anında yeniden değerlendirir; `payload_json`/`reason.json` hâlâ profili taşımıyor. Panel (10.7-a) öneriyi
  göstermek isterse aynı yeniden kurulumu kullanmalı; payload'a yazılıp yazılmayacağı insanın kararı.

- **D21 — Parti durum geçişi olay loguna yazılmıyor (09.2.1, tm 59).** K15 "her adım events tablosuna yazılır",
  09.2.1 "geçişler izlenebilir" der; §8.3'ün kapalı listesinde durum geçişi için tür yok (D6 ile aynı soru), en
  yakın aday `PIPELINE_FAILED` yalnız hataya aittir. Geçişler bu yüzden `uploads.status`'a yazılıp her geçişte commit
  edilerek izlenir — durum her an sorgulanabilir (`docs/UYGULAMA-PLANI-KAYNAK.md` 1.14: "durum her an
  sorgulanabiliyor"); adımların olayları (`PAGE_RENDERED`, `PAGE_ANALYZED`, `PLAN_CREATED`, `OUTPUT_SAVED`/
  `OUTPUT_SKIPPED`/`QUEUED_*`) ve `PIPELINE_FAILED.data.stage` tarihçeyi verir. Eksik kalan: sayfası ya da öğesi
  olmayan adımın zaman damgalı izi yok (ör. yalnız Word dosyalı partide render ve analiz). Zaman damgalı geçiş
  tarihçesi gerekiyorsa §8.3'e tür (ör. `UPLOAD_STATUS_CHANGED`) eklenmeli — karar insana bırakıldı.

- **D22 — `user_sessions` tablosu PRD §8.1'de yok (10.1.2, tm 64).** MASTER-PROMPT §4 panel girişini "sunucu tarafı
  oturum çerezi" olarak kilitler; sunucu tarafı oturumun bir deposu olmalı, §8.1 ise yalnız `users` tablosunu sayar.
  Kilitli karar PRD'den önce geldiği için (MASTER-PROMPT §2) tablo göç 0003 ile eklendi (`id`, `user_id`,
  `token_hash`, `created_at`, `expires_at`, `revoked_at`); `tests/db/test_models.py` onu §8.1 dışı tablo olarak ayrıca
  sayar. İmzalı istemci çerezi (Starlette `SessionMiddleware`) seçilseydi tablo gerekmezdi ama oturum sunucuda
  kapatılamazdı (çıkıştan sonra çalınmış çerez geçerli kalır). §8.1'e eklenip eklenmeyeceği insanın kararı.

- **D23 — Yeniden analizin iki aşamalı onayı: metinler PRD'de yok, belirteç 10.8.1 gelmeden kuruldu (10.3.2, tm 66).**
  10.3.2 "yeniden analiz iki aşamalı onay ister" der; §20.6 tablosu yalnız K16'nın beş manuel işlemini kapsar (yeniden analiz
  onlardan değil) ve §20.6.1'in sunucu belirteci 10.8.1'in işidir (henüz yok). Kararlar: **(a) Metinler** §20.6 kalıbıyla yazıldı
  (birinci cümle ne yapılacağını, ikinci geri dönüşü olmayan sonucu söyler): `Bu partiyi yeniden analiz etmek üzeresiniz. Emin
  misiniz?` / `Bu işlem partiye yeni bir plan sürümü açacak; önceki sürümün çıktıları "eski sürüm" olarak işaretlenecektir. Son
  kararınız mı?` **(b) Sunucu tarafında zorlanır:** birinci onaydan sonra `POST .../reanalyze/prepare` belirteç verir, ikinci
  onaydan sonra `POST .../reanalyze` belirteçle gelir; belirteçsiz/süresi geçmiş (10 dk)/başka partiye ya da başka oturuma ait
  istek 400 ve hiçbir şey yapılmaz. Belirteç saklanmaz: `HMAC-SHA256(oturum çerezinin özeti, işlem + parti + güncel plan kimliği
  + üretim anı)`; çerez yalnız tarayıcıda ve sunucuda bilinir. **(c) Tek kullanımlık DEĞİL:** §20.6.1 adım 4 (belirteç tüketilir)
  için sunucu tarafı depo gerekirdi (yeni tablo/göç, kapsam dışı); yerine belirteç *güncel plana* bağlıdır ve yeniden analiz yeni
  plan sürümü açtığı için başarılı işlemden sonra aynı belirteç geçmez (testli). Başarısız işlemde (rollback) plan değişmediğinden
  aynı belirteç 10 dk içinde yeniden denenebilir. **(d)** `USER_CONFIRMED` bu yolda zaten yazılır (§20.6.1: kullanıcı adı, işlem,
  hedef, iki onayın zamanı) ve `PLAN_REANALYZED`'dan önce düşer. 10.8.1 gelince bu belirteç onun mekanizmasıyla değiştirilmeli ve
  `USER_CONFIRMED` çift yazılmamalı; yeniden analizin onay metinlerinin §20.6 tablosuna eklenip eklenmeyeceği insanın kararı.

- **D24 — Kuyruk atamasının onay belirteci tek kullanımlık değil, öğenin çözülmesine bağlı (10.7.2, tm 71).**
  §20.6.1 adım 4 belirtecin *tüketilmesini* ister; bunun için sunucu tarafı depo (yeni tablo + göç) gerekirdi ve genel mekanizma
  10.8.1'indir. D23'ün belirteci (oturum çerezinden HMAC, 10 dk) işlem-bağımsız yapılıp atamaya bağlandı: imzalanan konu
  `assign:<queue_item_id>:<employee_id>` — başka öğe, başka çalışan, başka işlem (yeniden analiz) ya da başka oturumla 400.
  Tüketme yerine: başarılı atama öğeyi çözer, çözülmüş öğe hiçbir adımdan geçmez; aynı belirteçle ikinci istek **409** ile
  reddedilir (§20.6.2 "reddedilir" der, kodu söylemez; testli). Atama düşerse (rollback) öğe çözülmediği için aynı belirteç 10 dk
  içinde aynı çalışan için yeniden denenebilir — onaylanan işlemin aynısıdır. 10.8.1 gelince bu belirteç de onun mekanizmasıyla
  değiştirilmeli ve `USER_CONFIRMED` çift yazılmamalı.

- **D25 — Düzeltilen profilin kayıtlı çalışana uyması karar tablosunda yok; en güvenli davranış seçildi, belirteç tüketilmiyor (10.7.3, tm 72).**
  §20.2.2 belgenin kişi anahtarını değerlendirir; İK'nın düzelttiği ad ya da doğum tarihinin kayıtlı bir çalışana uyması tabloda yok
  ("hayalet çalışan" riski, R7). Karar: çalışana yazılacak bütün yazımlar (belgeninkiler + düzeltilenler) onaylanan doğum tarihiyle
  satır 3–5'e karşı sınanır (`_decide_by_name`, onayda E numarası kilidinin içinde, panelde her adımda); satır 3, 4 ya da 5 uyarsa
  ikinci çalışan açılmaz, öğe onaylanmaz ve mesaj hükmün dayandığı E numaralarını taşır — belge o çalışana atanır (10.7.2). Yalnız
  isim eşleşmesinde (satır 5) de reddedilir: satır 5'e düşen belge de profil olarak onaylanamıyordu (C42); gerçek bir adaşa profil
  açmanın yolu yok — karar insana. Belirteç D24'ün mekanizmasıdır (tüketilmez): konu `approve_profile:<öğe>:<onaylanan alanların
  SHA-256 özeti>` — ikinci onaydan sonra değiştirilen alan, başka öğe, işlem ya da oturum 400; başarılı onay öğeyi çözdüğü için aynı
  belirteçle ikinci istek 409. 10.8.1 gelince bu belirteç de onun mekanizmasıyla değiştirilmeli ve `USER_CONFIRMED` çift yazılmamalı.

- **D26 — Onay belirteci tablosu (`confirmation_tokens`) PRD §8.1'de yok; taşımada profiller commit'ten sonra üretilir (10.8.1, 10.8.2, tm 73).**
  §20.6.1 adım 4 belirtecin *tüketilmesini* ister; bunun için sunucu tarafı depo gerekir (D23/D24'ün ertelediği iş). Tablo göç 0004 ile eklendi (`id`, `token_hash`, `session_hash`, `username`, `operation`, `target`, `created_at`, `expires_at`, `consumed_at`); `tests/db/test_models.py` onu §8.1 dışı tablo olarak sayar. Belirteç `user_sessions` satırına yabancı anahtarla değil oturum çerezinin SHA-256 özetiyle bağlıdır (aynı değer `user_sessions.token_hash`'tedir). Satırlar silinmez; süresi geçen ve tüketilen satırlar birikir — temizlik politikası yok, §8.1'e eklenip eklenmeyeceği ve temizlik insanın kararı. Bu görevle D23 (c), D24 ve D25'in "belirteç tek kullanımlık değil" kısımları kapandı (C54). API'nin hazırlık uç noktaları ve `X-Confirmation-Token` başlığı PRD'de yazılı değil (C54). **Profil:** taşımada iki çalışanın `profil.md`'si commit'ten *sonra* yeniden üretilir: dosya diskte taşındıktan sonra profil yazımı düşüp işlem geri alınırsa veritabanı eski yolu gösterirdi; önce kayıt kesinleşir, profil üretimi düşerse yalnız profil bayat kalır. tm 93 (atama, profil onayı, arşiv sonrası profil) "oturum commit edilmez, çağıranın işlem sınırı" der — iki yol farklıdır; birleştirme kararı tm 93'te.

- **D27 — Erişim logu yalnız `file` ve `download`'a yazılır; fotoğraf, geçmiş sayfası ve yükleme sayfa görüntüleri loglanmaz (10.9.2, tm 74).**
  PRD "her açma ve indirme" der; 10.5.1/10.6.1 pencereleri kararı 10.9.2'ye bırakmıştı. Karar: (1) profil kartının fotoğrafı (`/employees/{id}/photo`) kartın parçasıdır, sayfayı çizmek belgeyi "açmak" sayılmaz (C49) — loglanmaz; (2) belge geçmişi sayfasını görüntülemek belge açmaz (C50) — loglanmaz, ama geçmişteki dosya bağlantısı `/file`'dır ve loglanır; (3) yükleme detayındaki sayfa görüntüleri (`/uploads/{id}/pages/{id}/image`) henüz bir `documents` satırı değildir ve `access_log.document_id` zorunlu bir yabancı anahtardır (PRD §8.1) — loglanmaz. Üçüncüsü kimlik belgesi görüntüsünün panelden kayıtsız izlenebilmesi demektir; kapatmak için ya `access_log`'un belgesiz sayfaya bağlanması (şema değişikliği) ya da sayfa görüntüsünün olay loguna (`events`) yazılması gerekir — karar insana. Orijinal kaynak dosyanın kendisi (Inbox) hâlâ panelden sunulmaz (C50). `tests/web/conftest.py` `app` fikstürü artık oturumdaki test kullanıcısını `users`'a da yazar (yabancı anahtar açık).

- **D28 — Katalog değişikliği olay loguna yazılmıyor; `front_back` sayfa kuralı yalnız formda; panel `catalog.yaml`'ı yazmıyor (11.1.1, 11.1.2, tm 75).**
  (a) K15 "her adım `events` tablosuna yazılır" der; §8.3'ün olay türleri kapalı listedir ve tür oluşturma/düzenleme/pasifleştirme için tür yoktur (`TYPE_APPROVED` aday türün onayıdır, 11.5.2). Uydurma bir tür eklenmedi: paneldeki katalog değişikliğini kimin yaptığı kaydedilmiyor. Yeni bir olay türü ve kullanıcı adıyla yazma insanın kararı. (b) PRD 11.1.2 "front_back türde sayfa aralığı 2 olmalı"yı *form doğrulaması* olarak yazar, C7 kuralı 11.1.2'ye bırakmıştı. Kural önce katalog şemasına (`CatalogEntry`) konmuştu; ama `tests/pipeline/test_plan.py`'nin `sides-only` senaryosu bilinçli olarak sayfa aralığı 1–2 olan bir `front_back` türe dayanır ve şema kuralı, böyle bir türü olan eski bir `catalog.yaml`/veritabanı kaydında `export_catalog`'u — yani her analizi — düşürürdü. Kural `app/catalog/form.py`'ye taşındı; katalog yüklemesi (00.6.1) davranışı değişmedi. Sonuç: YAML içe aktarma ya da elle veritabanı yazımı 1–2 sayfalı bir `front_back` türü hâlâ kabul eder, form o türü kaydederken 2–2 ister. Kuralın şemaya da konması istenirse `sides-only` senaryosunun şemayı atlayan bir yolla (ör. `model_construct`) kurulması gerekir — karar insana. (c) Panel `catalog.yaml`'ı yeniden üretmez (§8.2: tohum ve dışa aktarım dosyası; dışa aktarım `python -m app.catalog export`). Paneldeki değişiklikten sonra `python -m app.catalog import`'ı eski dosyayla koşmak o değişikliği geri alır; önce `export` gerekir. Karar insana.

- **09.3.2 çelişki denetimi (2026-09-19, panel bulgusu: PLAN.md:216 ◐ ↔ kapanmış tm 60–63):** kod PLAN'ı doğruladı, iş kısmi — S1, S2, S5 ve S3/S4'ün fotoğraf dışı yeşil, ama PRD §9'un "tartışmasız" S3/S4 beklentisi `Profile-Picture.jpeg` `tests/test_scenarios_s01_s05.py:589`'da strict xfail (D12); damga ◐ kaldı, kapanmış görevler geri açılmadı, kalan sahip kuralı tm 95'e (critical) verildi.

- **D29 — Kişi taşımayan belgenin sahibi aynı dosyadaki tek kayıtlı çalışandır; D12 kapandı (09.3.2, tm 95).**
  Dayanak PRD:524 ("'Beklenen' sütunu tartışmasızdır"): §9 S3 "Profile-Picture.jpeg (2)", S4 "Üç bağımsız çıktı" ister. D12'nin seçeneklerinden §9'u karşılayan en dar olanı uygulandı; D12 silinmedi, bu satır onu kapatır. Kural (`app/pipeline/plan.py` `_Planner._owned`/`_file_owner`): zorunlu alanı olmayan türün (tohumda yalnız `profile_picture`) belge düzeyinde kabul edilmiş, §20.2.2 satır 8'e düşen adayı; aynı yüklenen dosyanın (aynı `file_id`) kişi okunan adaylarının hepsi tek bir kayıtlı çalışana satır 1/3 ile bağlıysa ve en az biri Hazir'a gidiyorsa o çalışanla (`match`, `matched_by: null`) Hazir'a gider, aksi halde satır 8 aynen kalır. Sahip ikinci geçişte bulunur (S4'te fotoğraf oturma izninden önce gelir); öğe kimlikleri ve sırası değişmez. Görev tanımından dar okunan iki nokta: (1) kuyruğa giden kimlikli aday da sayılır — kişi tahmini aynı çalışan (satır 1/3) değilse (başka çalışan, yalnız isim, onay bekleyen profil, belirsiz, çelişkili anahtar) dosya "tek çalışanın" sayılmaz; (2) satır 6 (yeni çalışan), aynı çalışana eşleşen belgeyle birlikte olsa da sahip vermez. Bağlam çalışanı (K2) ve partinin başka dosyası girmez; kişi alanı beklenen türde ad/numarası okunmamış belge atanmaz (R7); belge düzeyindeki ret (işlem, dönüşüm izni, dosya türü; D15'in PNG fotoğrafı) ezilmez; kimlik ve iletişim bilgisi birikmez. **Olay:** §8.3'e tür eklenmedi (D6/D11 emsali); sahip kararı yalnız planda durur (Word/Excel ekinin bağlam sahibi gibi `match` + `matched_by: null`), fotoğrafın eşleştirme olayı `PERSON_NOT_MATCHED` olarak kalır — sahibin hangi belgeden alındığı logda yok. S18 senaryosu kuyruk öğesini artık fotoğrafla değil katalog dışı belgeyle sınar. Karar insana bırakıldı: sahibin kaynağı olay loguna yazılmalı mı; kural panelden eklenecek, zorunlu alanı boş öteki analizli türlere de uygulanmalı mı (bugün hepsine uygulanır).

- **D30 — Toplu yeniden analizin onay metinleri PRD'de yok; aday türün reddi onaysız ve geri alınamaz (11.5.3, 11.5.4, tm 79).**
  (a) 10.3.2 yeniden analize iki aşamalı onay ister; §20.6'da toplu yeniden analiz satırı yok ve D23'ün metinleri tekildir ("Bu partiyi…"). Pencere D23'ün çoğulunu yazdı (`app/web/routers/catalog.py` `BATCH_REANALYZE_FIRST`/`_SECOND`): birinci `Bu <n> partiyi yeniden analiz etmek üzeresiniz. Emin misiniz?`, ikinci `Bu işlem her partiye yeni bir plan sürümü açacak; önceki sürümlerin çıktıları "eski sürüm" olarak işaretlenecektir. Son kararınız mı?`. Metinler insan onayı bekler ya da §20.6'ya satır eklenmeli. (b) Ret K16'nın iki aşamalı onay isteyen beş işleminden değil ve §20.6'da metni yok; pasifleştirme gibi (C56) tek adımdır. Ama pasifleştirmenin aksine geri alınamaz: panelde "reddi geri al" yok, kayıt `rejected` kalır ve aynı ad yeniden önerilse de listeye düşmez (11.5.4'ün istediği). Yanlışlıkla reddedilen tür 11.1'in "Yeni tür" formuyla eklenebilir; o adayın bekleyen Unknown öğeleri toplu yeniden analize girmez, partinin kendi yeniden analiziyle (10.3.2) işlenir. Redde onay istenmeli mi, ret geri alınabilmeli mi — karar insana. (c) Toplu işlem tek veritabanı işlemidir; uygulayıcı ikinci partide düşerse ilk partinin kayıtları geri alınır ama diske yazdığı çıktı dosyaları kalır — tekil yeniden analizdeki durumun aynısı; sonraki yazım onları kayıtsız bulup yeniden kullanır (07.8.1, `_publish_ready_output`).

- **D31 — Profil yeniden üretimi atama/onay/arşivde commit'ten önce, taşımada commit'ten sonra (09.1.1, tm 93).**
  D26 "birleştirme kararı tm 93'te" demişti. Görev metni ("oturum commit edilmez, çağıranın işlem sınırı; profil dosyası atomik yazılır") atama, profil onayı ve arşivde profilin çekirdek işlevin içinde üretilmesini ister; yapıldı (§C59). Bunun bir bedeli var: `profil.md` diske atomik yazılır ama oturum henüz commit edilmemiştir; çağıran commit'ten önce işlemi geri alırsa (ya da commit düşerse) dosya geri alınan durumu gösterir ve bir sonraki yeniden üretime (yeni parti, sonraki manuel işlem, yeniden analiz) kadar bayat kalır. Bugünkü çağıranlar (`queue.py`: atama, profil onayı ve arşiv uçları) çekirdek işlevden sonra doğrudan commit eder; arada hata verecek başka iş yoktur, yani pencere yalnız commit'in kendisinin düşmesiyle sınırlı. Aynı nedenle atama ve onayda çıktı dosyası da commit'ten önce diske yazılır (mevcut sözleşme); arşivde dosya taşıması da öyle — geri alma dosyayı geri getirmez. Taşıma (`move_document`, tm 73) farklı: profil commit'ten *sonra* yazılır (D26), çünkü orada kayıt kesinleşmeden profilin yeni yolu göstermesi istenmedi. İki yol bilerek ayrı bırakıldı: tek yola çevirmek ya atama/onay/arşivin çağıranlarına ikinci bir yeniden üretim adımı (commit sonrası) ekler ya da taşımayı çekirdeğe alıp D26'yı bozar; ikisi de görev kapsamını aşar. Karar insana: atama/onay/arşivde de commit sonrası üretim istenirse çağıranlar (`queue.py`) `write_profile`'ı taşımadaki gibi commit'ten sonra çağırır ve çekirdekteki çağrı kalkar.

- **D32 — 03.3.1'in "gerçek çağrı" kabulü koşulmadı; damga ◐ kaldı (tm 20).**
  Kabul kriteri "aynı arayüzü uygular ve en az bir gerçek çağrıyla doğrulanır" der. Arayüz kısmı tamam ve testli (§C60); gerçek çağrı kısmı ortamda `OPENAI_API_KEY` olmadığı için yapılamadı, kapıda da `live` testler bilerek dışarıda (CONVENTIONS §1.4, MASTER-PROMPT §8). Doğrulanmayan, canlı çağrıda kırılabilecek varsayımlar: (1) `gpt-5.5` model adı ve `max_completion_tokens`/`parallel_tool_calls`/`store` parametrelerini kabul etmesi; (2) katı olmayan işlevin `patternProperties`/`$defs`/`anyOf` içeren şemayı olduğu gibi kabul etmesi; (3) zorlanmış işlev seçiminde `finish_reason`'ın `stop`/`tool_calls` davranışı (ikisi de kabul edilir); (4) modelin varsayılan akıl yürütme eforuyla 4096 çıktı token'ının yetmesi. 03.2.2 (Anthropic) aynı boşlukla ✅ kapandı çünkü kabulü canlı çağrı istemiyordu; bu satır istiyor, bu yüzden ✅ uydurulmadı. Karar insana: anahtarlı ortamda `pytest -m live tests/ai/test_openai_provider.py` yeşil koşunca 03.3.1 `✅ → K03.3` yapılır; kırmızı ise `openai_provider.py` düzeltilir. Satır Should (v1) olduğu için Must sayacını ve MVP kapanışını etkilemez.

- **D33 — Örnek belge yüklemede olay kaydı, silme ve düzenleme yok (11.2.1, tm 76).**
  (a) K15 "her adım `events` tablosuna yazılır" der; §8.3'ün kapalı listesinde örnek yükleme olayı yoktur (D28 emsali) ve uydurma bir tür eklenmedi: örneği kimin, ne zaman yüklediği kaydedilmiyor — örnek yalnız dosyadır. Yeni olay türü insanın kararı. (b) Örneği silme ya da değiştirme yolu yok: K16 silmeyi (arşiv vardır), K17 içerik düzenlemeyi yasaklar; ama yanlış yüklenen bir örneği panelden çıkarmanın da yolu yok — kaldırmak elle dosya sisteminden yapılır. Gerekirse "örneği arşivle" ayrı görev ve insan kararıdır (K16'nın manuel işlem listesi kapalı). (c) Örnek dosyaları erişim logunun (10.9.2) dışındadır: o `documents` satırlarına bağlıdır, örnek çalışan belgesi değildir. (d) CONVENTIONS §6: yükleme bölümü gerçek kimlik belgesi yüklenmemesini hatırlatır ama bunu denetleyemez; örnekte gerçek kişisel belge olmaması yükleyenin sorumluluğudur.

- **D34 — Tür açıklaması örnek sayfalarını tek istekte gönderir; olay kaydı yok; canlı çağrı doğrulanmadı (11.3.1, tm 77).**
  (a) CONVENTIONS §6 "yapay zekâ sağlayıcısına yalnız işlenmekte olan sayfa gönderilir; başka çalışanın verisi aynı isteğe konmaz" der. Tür açıklaması türün birden çok örneğinin sayfalarını (en çok 8) aynı isteğe koyar: açıklama tek sayfadan değil, örneklerin ortak görünüşünden çıkar. Örnekler 11.2.1 gereği çalışan verisi değildir ve yükleme bölümü gerçek kimlik belgesi yüklenmemesini ister; ama biri gerçek belgeleri örnek diye yüklediyse birden çok kişinin verisi aynı isteğe girer. Önlemler: talimat kişisel değer yazmayı yasaklar, dosya adları isteğe girmez, sonuç kaydedilmeden İK'ya gösterilir ve "kişiye ait değer girdiyse silin" uyarısı taşır. Örnek başına ayrı istek ve sonra birleştirme insan kararına bırakıldı. (b) K15: üretim hiçbir şeyi değiştirmediği (öneridir, kaydedilmez) için olay yazılmadı; kaydetme 11.1.1'in tür düzenlemesidir, onun da §8.3'te türü yok (D28). Maliyetli yapay zekâ çağrısını kimin yaptığı loglanmıyor — yeni olay türü insan kararı. (c) Kabul kriteri canlı çağrı istemez; testler kayıtlı yanıt ve `httpx2.MockTransport` iledir. Canlı modelin şemaya uyan, kısa ve kişisel değer taşımayan açıklama yazdığı, 8 görüntü + talimatın `AI_MAX_OUTPUT_TOKENS` ve zaman aşımına sığdığı doğrulanmadı; anahtarlı ortamda panelden örnekli bir türle denenmeli. (d) Görüntü dosyası örnekleri analiz kopyası gibi küçültülmeden gider (02.3.1); çok büyük bir fotoğraf sağlayıcının görüntü sınırını aşarsa 502 döner. (e) `AnalysisProvider`'ın ikinci işinin (`_request_description`) varsayılanı "desteklemiyor"dur, soyut değildir: yeni bir somut sağlayıcı onu uygulamayı unutursa hata kurulumda değil çalışma zamanında (`ProviderError`, 502) görünür.

- **D35 — Fotoğraf kural setinin varsayılanları, biçimi ve olay kaydı PRD'de yok (11.6.1, tm 80).**
  (a) Kaynak plan baş örtüsü için "kabul durumu (şirket kararı)" der; PRD karar vermez. Kural "Baş örtüsü yok" biçiminde tanımlandı ve **varsayılan KAPALI**: İK açana kadar hiçbir fotoğrafı bu yüzden elemez; yönünün (kabul edilmez) ve açılıp açılmayacağının kararı insanın. Asgari çözünürlük için PRD/kaynak sayı vermez: ilk değer 400×400 piksel uydurma bir başlangıçtır, panelden değişir. (b) Kayıt boşken (`photo_rules: null` — tohum ve bugünkü kurulumlar) kurallar **varsayılanındadır**: 11.7 geldiğinde İK hiç kaydetmemiş olsa da altı kural etkin olur; "hiç kaydedilmedi" "kural yok" demek değildir. İstenmiyorsa tohuma boş bir küme yazmak ya da varsayılanları kapatmak insanın kararı. (c) Kural kimlikleri ve `{kural: {enabled}}` biçimi PRD §8.6'da yok (yalnız `photo_rules` sütununun adı var); kaynak plan `photo_rules: []` (liste) demişti, PRD/şema sözlük olduğu için sözlük kullanıldı. 11.7 kuralları bu biçimden `enabled_photo_rules` ile okumalı. (d) K15 "her adım `events` tablosuna yazılır" der; §8.3'ün kapalı listesinde kural değişikliği olayı yoktur (D28, D33 emsali): kural setini kimin, ne zaman değiştirdiği kaydedilmiyor; yeni olay türü insanın kararı. (e) Kurallar yalnız `profile_picture`'da (`PHOTO_RULE_TYPES`); başka bir görsel tür açılırsa kümeye eklenmesi gerekir. Görevin yüzeyi dışında `app/web/templates/catalog_form.html` + yeni `catalog_photo_rules.html`, `panel.css`, `app/catalog/__init__.py` (dışa aktarım), `tests/web/test_access_log.py` (10.9.1 kilidine bir yeni POST yolu) dokunuldu; tür sayfası artık `?notice=` alır. Tarayıcıda çizim görülmedi (yalnız `TestClient`).

- **01.1.1/01.2.2 çelişki denetimi (2026-09-19, panel bulgusu: açık tm 94 ↔ PLAN.md:95, :98 ✅):** kod 01.1.1'i doğruladı (kabul yeşil, ✅ kaldı; Windows'ta yasak karakterli ad → 500 kabulün dışında bir sağlamlık kusuru, yeniden üretildi) ama 01.2.2 ✅ erkendi — `POST /api/uploads` desteklenmeyen içeriği 201 ile Inbox'a alıyor, kullanıcıya mesaj yok (K01.2); 01.2.2 ◐'ye çekildi, tm 94 açık kaldı ve yalnız kalan iki parçaya (ad doğrulaması + yüklemede tür reddi) daraltıldı, yeni görev açılmadı.

- **D36 — Fotoğraf kontrolü: PRD'de olmayan sütun, olay türü yok, değerlendirilmeyen kural kuyruğa, kontrol hatası sayfayı düşürür, canlı doğrulanmadı (11.7.1, 11.7.2, tm 81).**
  (a) PRD §8.1 `pages` satırında `photo_check_json` yok. Değerlendirme §8.4 sayfa analizine konamazdı (her sayfanın sözleşmesi değişir, tanımsız anahtar reddedilir) ve plan yapay zekâya yeniden soramaz (K9); sonuç kalıcı olmalıydı — sütun ve göç 0005 eklendi (C64). (b) K15: §8.3'ün kapalı listesinde fotoğraf kontrolü olayı yok (D28/D33/D35 emsali); sonuç `PAGE_ANALYZED` verisine kural → sonuç olarak, hata `PAGE_ANALYSIS_FAILED`'a `step: photo_check` ile yazıldı; planın hükmü `route_reason` ve `QUEUED_UNRESOLVED` mesajındadır. Ayrı olay türü insanın kararı. (c) PRD yalnız "fail varsa Unresolved" der. Açık bir kuralın saklı sonucu yoksa (kontrol yok, kayıt okunamıyor, kural analizden sonra açıldı) pencere fotoğrafı `Fotoğraf kuralları değerlendirilmedi` gerekçesiyle Unresolved'a gönderdi (CLAUDE.md: emin olunamayan belge kuyruğa alınır); boru hattında analiz ve plan aynı katalogla yapıldığından bu yol yalnız dışarıdan yazılmış sayfada görülür. `unsure` ise PRD ve kaynak plan gereği yalnız nottur, fotoğraf Hazir'a gider; "unsure da kuyruğa" istenirse değişiklik `check_photo_rules`'ta tek koşuldur — karar insanın. (d) Kontrol yapılamazsa (sağlayıcı hatası, şemaya uymayan yanıt, kaynak ölçülemiyor) sayfanın analizi bütün olarak `failed` sayılır ve parti `partial` olur (03.7.2 yolu): iyi okunmuş sayfa analizi de atılır, yeniden analiz ikisini birlikte yeniler. (e) PDF sayfası tek tam sayfa gömülü görüntü değilse (render yolu) fotoğrafın kendi piksel boyutu yoktur; çözünürlük `unsure` (yalnız not) — çıktı `render_image_dpi` ile render edilir. Render boyutunu ölçmek (`render_image_dpi`'ı analiz adımına taşıyarak) ya da bu durumu fail saymak insanın kararı. (f) `no_head_covering`'in açıklaması ("… açılmadıkça fotoğraf bu yüzden elenmez") panel içindir ama kural açıldığında yapay zekâya olduğu gibi gider; talimat "listede gelen her kural bu fotoğraf için geçerlidir" der. Kurala ayrı bir soru metni (`PhotoRuleSpec`, 11.6 yüzeyi) eklemek insanın kararı. (g) Canlı sağlayıcıyla doğrulanmadı (kabul istemiyor; testler kayıtlı yanıt ve `httpx2.MockTransport` ile): modelin gerçek fotoğrafta kuralları makul değerlendirdiği ve `record_photo_check` şemasına uyduğu anahtarlı ortamda denenmeli. (h) Kaynak planın 5.2.4'ü "PNG'den JPEG'e dönüşüm sabit kaliteyle" der; §20.3'te bu işlem yok (D15: PNG fotoğraf Unresolved) ve eklenmedi — 11.7.2'nin kabulü dışında.

- **D37 — Fotoğraf örnekleri: işaret türetilir, çalışan fotoğrafları tek istekte, açıklama kendiliğinden güncellenmez, olay/erişim kaydı yok, canlı doğrulanmadı (11.8.1, tm 82).**
  (a) "Örnek işaretlenir" saklı bir bayrakla (`documents` sütunu + göç) değil, her okumada kayıtlardan çıkarılan işaretle karşılandı: saklı bayrak ya uygulayıcıda karar (K9: karar planındır) ya plan şeması değişikliği isterdi ve kural seti değişince bayatlardı. Kaynak plan "İK'nın kabul ettiği … işaretlenebilir" (elle) der; PRD edilgendir ve K16'nın manuel işlem listesi kapalıdır — elle işaretleme ya da işaret kaldırma yok. İK kötü bir örneği yalnız kuralları sıkılaştırarak ya da belgeyi arşivleyerek dışarıda bırakabilir; "örnekten çıkar" düğmesi insanın kararı. (b) CONVENTIONS §6 "başka çalışanın verisi aynı isteğe konmaz" der; kabul edilen fotoğraflar farklı çalışanların gerçek fotoğraflarıdır ve (D34'ün örneklerinden farklı olarak) kesin kişisel veridir — açıklama isteğine birlikte girer (en çok 8). Önlemler: istek yalnız İK düğmeye basınca yapılır; talimat kişiyi tarif etmeyi yasaklar; isteğe ad, numara, yol, belge kimliği girmez; sonuç kaydedilmeden İK'ya gösterilir. Fotoğraf başına ayrı istek + birleştirme ya da öğrenmeyi yalnız yüklenmiş örneklere kısmak insanın kararı. (c) Kaynak plan "Örnek eklendikçe açıklama güncelleniyor" der; açıklama kendiliğinden yeniden üretilmez ve kaydedilmez — 11.3.1'in "öneri, İK kaydeder" ilkesi korundu (her yeni fotoğrafta sağlayıcı çağrısı ve gözden geçirilmeden değişen analiz talimatı olmasın). Kendiliğinden yenileme insanın kararı. (d) K15 / 10.9.2: fotoğrafların sağlayıcıya gönderilmesi için olay ya da `access_log` satırı yazılmaz (D34b emsali; `access_log` "açtı ya da indirdi" içindir). Hangi çalışanın fotoğrafının dışarı gönderildiği loglanmıyor — yeni olay türü insanın kararı. (e) `unsure` fotoğraf Hazir'a girer (11.7.1) ama örnek sayılmaz; `fail` fotoğrafı İK atasa da örnek değildir. İK'nın atadığı fotoğrafı "kabul edilmiş" saymak insanın kararı. (f) Sınırın paylaşımı (fotoğraflara yarısına kadar) ve fotoğrafların yeniden eskiye seçilmesi pencerenin kararıdır; PRD ve kaynak plan sayı vermez. (g) Canlı sağlayıcıyla doğrulanmadı (kabul istemiyor; testler ağsız sağlayıcıyla): modelin kişiyi tarif etmeden ortak çekimi yazdığı ve fotoğraf olmayan türde `accepted_photo`'yu boş bıraktığı anahtarlı ortamda denenmeli.

- **D38 — Telegram botu: yanıt yalnız özel sohbette, beyaz liste yönetimi yok, üretimde webhook gizli değeri zorunlu, olay kaydı yok, canlı doğrulanmadı (12.1.1, 12.1.2, tm 83).**
  (a) PRD "listede olmayan kullanıcıya yanıt verilmez" der; listedeki kullanıcının grup ya da kanaldaki mesajı için sessizdir. Yanıt sohbetteki herkese görünür ve 12.3 kimlik belgesi gönderecektir; listede olmayan üyelere yanıt gitmemesi için kapı yalnız özel sohbeti geçirir (C66). K13 "yalnız İK kullanır" der; grupta kullanım istenirse bu kural gevşetilmeden önce insan karar vermeli. (b) PRD beyaz listeye kimin, nasıl kullanıcı ekleyeceğini yazmaz: `telegram_users.user_id` bir panel kullanıcısına bağlıdır (boş olamaz) ve satır ekleyen ya da `allowed` bayrağını çeviren bir panel ekranı ya da komut satırı yoktur; şimdilik satır doğrudan veritabanına yazılır. CONVENTIONS §5 gereği eklenmedi — yönetim yüzeyi (panel ekranı ya da `python -m app.telegram` alt komutu) yeni görev olmalı. (c) Üretimde `TELEGRAM_WEBHOOK_SECRET` zorunlu: beyaz liste güncellemedeki kullanıcı kimliğine güvenir ve webhook'a gelen isteğin Telegram'dan geldiğini yalnız bu gizli değer doğrular; olmadan herkes listedeki birinin kimliğiyle sahte güncelleme yollayabilir. Bu PRD'de yazılı değildir, güvenlik gereği eklendi. (d) K15: §8.3'ün kapalı listesinde Telegram olayı yok (D28/D33/D35–D37 emsali); reddedilen ya da yanıtlanan güncelleme için `events` satırı açılmaz, yalnız log satırı (`update_id`) yazılır. Ayrı olay türü insanın kararı. (e) **Canlı doğrulanmadı:** gerçek Telegram'a bağlanılmadı (token yok). Polling (`run()` → gerçek `run_polling`) ve webhook sunucusu (gerçek `updater.start_webhook`, yerel port, gizli değersiz istek 403) `FakeTelegram` aktarıcısıyla sınandı; gerçek `getMe`/`setWebhook`, kapsayıcının derlenip çalışması ve Caddy arkasında TLS sonlandırma sınanmadı. Kabul ölçütü bağlantıyı değil davranışı söylediği için 12.1.1 `✅` verildi; ilk tokenlı ortamda bot elle açılıp `/start` denenmeli. (f) `/start` ve `/yardim` PRD'de yok; listedeki kullanıcı yanıt alsın diye eklendi (kaynak plan 4.1.3). Metin "belge gönderme ve isteme henüz etkin değil" der; 12.2/12.3 değiştirmeli.

- **D39 — Telegram'dan belge alma: paylaşılan çekirdek, Telegram sınırları, yarım kalan işlem, canlı doğrulanmadı (12.2.1, 12.2.2, 12.2.3, tm 84).**
  (a) Görevin çıktı yüzeyi `app/telegram/handlers.py`'dir; "web ile aynı boru hattı"nı sağlamak için ayrıca `app/web/routers/uploads.py` (`store_upload` çıkarıldı, `create_upload` onu çağırır — HTTP davranışı ve 10 dk'lık web testleri aynı), `app/telegram/bot.py` (`build_application(intake=)`, `main`, yardım metni) ve test altyapısı (`tests/telegram/conftest.py`: `FakeTelegram` dosya indirme, `document_update`/`photo_update`, `make_intake_bot`) dokunuldu; çekirdeği kopyalamak iki yolun ayrışmasına yol açardı. (b) **Telegram kısıtları:** fotoğraf olarak gönderilen görüntüyü Telegram kendisi yeniden kodlar ve küçültür — bot yalnız aldığını olduğu gibi saklar (K10/K11 bozulmaz ama kaynak zaten kayıplıdır); kimlik/pasaport için "dosya olarak gönderin" yardım metninde söylenir. Bot API bota 20 MB'tan büyük dosya vermez (yerel Bot API sunucusu ya da bölme gerekir; ayar eklenmedi). (c) **Yarım kalan işlem:** bot süreci parti işlenirken durdurulursa parti ara durumda (`rendering`, `analyzing`…) kalır ve kullanıcıya sonuç gitmez — web'in arka plan işleyicisiyle aynı sınırlama; dosyalar Inbox'ta güvendedir. Yeniden başlatmada devam ettiren/kapanışta bekleyen bir mekanizma CONVENTIONS §5 gereği eklenmedi; yeni görev olmalı. (d) K15/§8.3: Telegram'a özgü olay türü yok (D38 d emsali); iz `FILE_UPLOADED`, `PLAN_CREATED`, `OUTPUT_SAVED`… olaylarında ve `uploads.channel`/`uploaded_by` sütunlarında — Telegram kimliği (`telegram_id`) saklanmaz, panel kullanıcı adı saklanır. (e) Albüm bekleme süresi (2 sn) ve "geç dosya yeni partidir" kuralı PRD'de yok; gerçek ağda albüm zamanlaması ölçülmedi, ayarlanabilir değil (`GROUP_WAIT_SECONDS`). (f) Albümde ad çakışırsa `original_name` Telegram'daki adından farklı olur (`-2`); içerik değişmez. (g) Compose'ta `bot` servisi `app` gibi sağlayıcı ortam değişkenlerini (`AI_PROVIDER`, anahtarlar) açıkça geçirmez; bunlar aynı `.env`/ortamdan gelmelidir — compose değiştirilmedi. (h) **Canlı doğrulanmadı:** gerçek Telegram'a ve gerçek yapay zekâ sağlayıcısına bağlanılmadı (token/anahtar yok); Bot API `FakeTelegram` aktarıcısıyla, sağlayıcı kayıtlı yanıtlarla taklit edildi. İlk tokenlı ortamda bir PDF, bir fotoğraf ve bir albüm gönderilip özet görülmeli.

- **D40 — Doğal dil belge istekleri: tek atımlık araç çağrısı, mesaj yapay zekâya gider, süreç içi seçim belleği, erişim eylemi `download`, canlı doğrulanmadı (12.3.1, 12.3.2, 12.3.3, tm 85).**
  (a) Tarihi plan (4.3.1) yapay zekâya `search_employees`/`list_documents`/`send_document` araçlarını verip sonuçları ona geri besleyen çok turlu bir döngü öngörüyordu. Uygulanmadı: arama sonuçları (başka çalışanların adları, numaraları, belge listeleri) sağlayıcıya gitmiş olurdu (CONVENTIONS §6: başka çalışanın verisi isteğe konmaz) ve hangi belgenin gönderileceği kararı yapay zekâya kalırdı (K9'un karar/uygulama ayrımı). Yerine yapay zekâ mesajı tek bir araç çağrısına çevirir (kişi ifadesi, tür adı, katalog türleri); arama, belirsizlik sorusu ve gönderim deterministik koddur. Tarihi plandaki "çalışan arama" niyeti (4.3.2) PRD'de olmadığı için eklenmedi. (b) Yapay zekâya İK'nın mesajı olduğu gibi gider (kişi adı ve yazılmışsa numara); okumanın kendisi budur. Veritabanından katalog türleri dışında hiçbir değer isteğe girmez. (c) Seçim belleği bot sürecinin belleğindedir (§8.1'de tablo yok, göç açılmadı): bot yeniden başlarsa bekleyen sorular düşer; birden çok bot süreci aynı anda koşarsa bir sürecin sorusuna öteki "geçersiz" der — bot tek süreç olmalıdır (Compose'ta tek `bot` servisi). (d) `access_log.action` yalnız `view`/`download` taşır; Telegram'a gönderilen dosya cihaza indiği için `download` yazıldı. Kayıt dosya okunmadan ve gönderilmeden önce yazıldığı için dosya o anda okunamazsa ya da gönderim başarısız olursa kayıt kalır — eksik değil fazla kayıt (web ile aynı, C55). (e) Kişi eşleştirmesi paneldeki aramadan (10.4.2, alt dizgi) bilerek farklıdır: tam kelime ve ad yazımı başına — "Ali" "Alican"ı bulmaz; yalnız soyadla birden çok kişi çıkarsa sorulur. Türkçe eklerin atılması talimatla yapay zekâya bırakıldı; ek atılmadan gelen ad ("Çakar'ın") eşleşmez ve "bulunamadı" denir — tahmin yerine güvenli ret. (f) Yalnız etkin belgeler önerilir; eski sürüm ve arşivdeki belge botla istenemez (panelden açılır). (g) Görevin yüzeyi `app/telegram/intent.py`'dir; ayrıca `app/ai/` (sözleşme `document_query.py`, talimat `prompts/document_query.md`/`.py`, `provider.py`, iki sağlayıcı, kayıtlı yanıt sağlayıcısı, dışa aktarımlar), `app/telegram/bot.py` (bağlantı, yardım metni) ve test altyapısı (`tests/telegram/conftest.py`: `sendDocument` yüklemeleri, başarısız yöntemler, `make_request_bot`, `callback_update` verisi; `tests/ai/payloads.py`) dokunuldu. Yardım metni 12.2'den sonra da "belge gönderme ve belge isteme henüz etkin değil" diyordu (tm 84 kapanış notu güncellendiğini yazıyordu, metin değişmemişti); ikisini de anlatacak biçimde yenilendi. (h) Erişilemeyen (48 saatten eski) ya da satır içi iletideki düğme basışında python-telegram-bot `TelegramError` değil `TypeError` verir; düğme kaldırma yalnız erişilebilir iletide denenir. (i) **Canlı doğrulanmadı:** gerçek Telegram'a ve gerçek yapay zekâya bağlanılmadı (token/anahtar yok); Bot API `FakeTelegram`, okuma kayıtlı yanıtlarla taklit edildi — talimatın gerçek modelde Türkçe ekleri atıp atmadığı ve türü doğru eşlediği ölçülmedi. İlk tokenlı ortamda tek sonuç, iki sonuç, bilinmeyen tür, eki atılmamış ad ve selam gibi birkaç istek elle denenmeli.

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
| 09.1-b | Manuel işlemlerden sonra profil.md yeniden üretimi | 09.1.1 | [SONNET-XHIGH] | 09.2 | 0 |
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
- ✅ Çelişki denetimi (2026-09-19, panel bulgusu: açık tm 94 ↔ PLAN.md:95 ✅): 01.1.1'in kabulü (çoklu dosya tek parti, `upload_id` döner) koda karşı yeniden koşuldu — `tests/web/test_uploads.py` + `tests/storage/test_filetype.py` + `tests/db/test_upload_id.py` 57 geçti, 1 PG atlandı; damga ✅ kaldı. Kabulün dışında kalan sağlamlık kusuru yeniden üretildi: Windows'ta yasak karakter (`<` `>` `:` `?` `*` vb.) içeren ad (`a<b.pdf`) `_validated_name`'den geçer, `write_file` → `os.link` `OSError` (WinError 123) → 500; kalan iş tm 94 (1) — `app/web/routers/uploads.py` · tm 94

#### K01.2 — 01.2.1, 01.2.2 · İçerik tabanlı dosya türü tespiti
- ✅ `detect_file_kind(content)` yalnız ilk baytlardaki imzaya bakar, dosya adı/uzantısı hiç okunmaz — PDF/JPEG/PNG imzası doğrudan, OOXML (DOCX/XLSX) ZIP içindeki `word/document.xml`/`xl/workbook.xml` yoluyla, eski ikili DOC/XLS (CFBF) UTF-16LE `WordDocument`/`Workbook`/`Book` akış adıyla ayırt edilir (K2: DOC/XLS/DOCX/XLSX yalnız tanınır, analiz edilmez); yedi türün dışındaki her içerik (boş, düz metin, bozuk zip, isimsiz OLE) `UnsupportedFileTypeError` ile anlaşılır Türkçe mesajla reddedilir — `app/storage/filetype.py` · test `tests/storage/test_filetype.py` (10 fonksiyon / 14 durum) · tm 8
- ◐ Çelişki denetimi (2026-09-19, panel bulgusu: açık tm 94 ↔ PLAN.md:98 ✅): 01.2.2'nin kabulü ("yedi tür dışındaki dosya anlaşılır mesajla reddedilir") uçtan uca karşılanmıyor, ✅ erkendi. Tespit işlevi reddediyor, ama yükleme uç noktası onu reddetmek için çağırmıyor (`_pdf_page_count` hatayı yutar): düz metin `notlar.txt` → `POST /api/uploads` 201, dosya Inbox'a yazılır, `GET /api/uploads/{id}` `page_count: null` ile sessizce `received`, kullanıcı mesaj görmez; `/upload` sayfasının `accept=` süzgeci yalnız tarayıcıda. EKSİK: yedi tür dışındaki içerik yüklemede 400 + `detect_file_kind` mesajıyla, 01.3.1 emsaliyle hep-ya-hiç reddedilmeli (parti, `upload_files` satırı, olay ve Inbox dizini oluşmadan) ve bunun uç nokta testi yazılmalı. Kalan iş tm 94 (2) — `app/web/routers/uploads.py` · test yok · tm 94

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

#### K03.3 — 03.3.1 · OpenAI sağlayıcı iskeleti
- ◐ `OpenAIProvider` (`AI_PROVIDER=openai`) `AnalysisProvider`'ın ikinci somut uygulamasıdır: Chat Completions API'ye `system` talimatı + önce base64 veri URL'siyle sayfa görüntüsü (JPEG/PNG, `detail: high`) sonra sayfa metni gider; zorlanmış tek `record_page_analysis` işlevi (`parameters` = `PageAnalysis.model_json_schema()`, katı mod kapalı, Anthropic aracıyla aynı şema) ile yapılandırılmış çıktı alınır, işlev argümanları ortak `analyze_page` kabulünden (`validate_page_analysis`) geçip `PageAnalysis` döner; `store=False`, `parallel_tool_calls=False`, SDK yeniden denemesi kapalı. Kesik (`length`), süzülmüş (`content_filter`), ret, işlevsiz, çok çağrılı, başka işlev adlı, özel araç çağrılı ve çok seçenekli yanıt reddedilir; `finish_reason` `stop` olan tam işlev çağrısı (zorlanmış seçimde olağan) kabul edilir; 429 → `ProviderRateLimitError`, 5xx → `ProviderServerError`, bağlantı/zaman aşımı → `ProviderConnectionError`, öteki 4xx ve `insufficient_quota` (429) → yeniden denenmeyen `ProviderError`; `create_provider` `openai` adını kurar, `OPENAI_API_KEY` yoksa `ProviderConfigError` (`OPENAI_MODEL` varsayılanı `gpt-5.5`) — `app/ai/openai_provider.py`, `app/ai/provider.py`, `app/config.py` · test `tests/ai/test_openai_provider.py` (59), `tests/test_config.py` · tm 20
- ◐ Kabul kriterinin "en az bir gerçek çağrıyla doğrulanır" kısmı BU ORTAMDA KOŞULMADI: `OPENAI_API_KEY` yok. İstek/yanıt gerçek `openai` SDK istemcisinden `httpx2.MockTransport` ile geçirilerek doğrulandı (gövde, başlık, yol, hata eşlemesi); `api.openai.com`'a hiçbir çağrı yapılmadı. Canlı test yazılı ve `live` işaretli: `test_live_openai_returns_schema_conforming_analysis`. Anahtarlı ortamda `pytest -m live tests/ai/test_openai_provider.py` yeşil koşunca damga `✅ → K03.3` olur (§C60, §D32).

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

#### K05.5 — 05.5.1, 05.5.2, 05.5.3 · Çalışan eşleştirme sırası
- ✅ 05.5.1 `match_employee(session, key, *, file_id, page_index)` (`app/matching/match.py`) 05.4 kişi anahtarını kayıtlı çalışanlarla §20.2.2 sırasıyla karşılaştırır, ilk uyan satır kazanır: satır 1 anahtarın numarası `employee_identifiers.value` ile tam eşit ve tek çalışana ait → `EmployeeMatch(document_number)`, `action: match`, `matched_by: document_number`; satır 3 numara eşleşmedi ya da yok, `name_keys`'ten (ad-soyad, orijinal yazım) biri `employee_aliases.normalized_name` ile eşit ve doğum tarihi eşit tek çalışan → `name_dob`. Numara başka bir çalışanın isim + doğum tarihinden önce gelir; aynı çalışanın aynı numaralı iki kaydı tek sahiptir; Kiril orijinal yazımlı alias, Latin anahtarla ve tersi eşleşir; alt/üst küme isim, çalışanın alias'sız ad sütunları ve normalize edilmemiş saklı numara eşleşmez. Hiçbir satır uymazsa `no_match` (`action`/`queue` boş; satır 6–8 05.6/05.7'nin). Hüküm `PERSON_MATCHED` olayına (`employee_id` sütunu, veri `rule`, `matched_by`, `employee_ids`) yazılır; olay dışında yazmaz, commit etmez (kurallar: C27) — `app/matching/match.py` · test `tests/matching/test_employee_match.py` · tm 36
- ✅ 05.5.2 / S10: yalnız isim eşleşmesi (doğum tarihi belgede yok, çalışanda yok, ikisinde yok ya da farklı; eşleşmeyen numaralı ve numarasız) → `name_only`, `action: none`, `QueueKind.UNRESOLVED`, gerekçe PRD metniyle başlar (`İsim eşleşti ama doğum tarihi veya belge numarası doğrulanamadı. İsmi eşleşen çalışan: E0001. …`), `PERSON_NOT_MATCHED`; çalışan, alias ya da numara eklenmez, satır 6'ya inilmez. Çelişkili anahtar (numara, doğum tarihi, isim çelişkisi) numara tek bir çalışana ait olsa bile hiçbir satır denenmeden `conflicting_key` ile Unresolved'a gider (D8) — `app/matching/match.py` · test `tests/matching/test_employee_match.py` · tm 36
- ✅ 05.5.3 / S12: numara birden fazla çalışana ait (isim + doğum tarihi tek çalışana uysa bile) → `document_number_ambiguous`; isim + doğum tarihi birden fazla çalışana uyuyor → `name_dob_ambiguous`; ikisi de `action: none`, Unresolved, E numaraları sayısal sırayla gerekçede, `PERSON_AMBIGUOUS` olayında `message` + `employee_ids`. S12: aynı isimli iki çalışandan doğum tarihi birine uyan eşleşir (iki yönde), ikisine uyarsa belirsiz, hiçbirine uymazsa `name_only` (iki çalışan da gerekçede). Entegrasyon: sentetik PDF gerçek render adımlarından ve `russian_passport` kaydıyla analizden geçer, `group_upload` → `build_person_key` → `match_employee` S1 (numara), S10, S12 (bir/iki çalışan) hükümlerini verir; olay parti, dosya ve sayfaya bağlı, kişisel değer (ad, numara, doğum tarihi) taşımaz, yeni çalışan açılmaz. 16 kural bozulması (belirsiz numaranın satır 3'e düşmesi, çelişki kontrolü, boş doğum tarihinin eşit sayılması, belirsiz ismin eşleşme sayılması, yalnız isimin `no_match`'e ya da numaralıyken satır 6'ya inmesi, gerekçe metni, E numarası sırası, tekrarsızlık, belirsiz isim olay türü, yalnız ad-soyad anahtarıyla arama, `no_match`'in kuyruğa alınması, ismin numaradan önce denenmesi, olayda `queue`, belirsizde `employee_id`, anahtarın bütün numaralarıyla arama) geçici olarak denendi, her biri testte kırmızı — `app/matching/match.py` · test `tests/matching/test_employee_match.py` (17 fonksiyon / 40 durum), `tests/matching/conftest.py` · tm 36

#### K05.6 — 05.6.1 · Otomatik çalışan oluşturma
- ✅ 05.6.1 `clean_document_number(key, entry)` (`app/matching/match.py`) §20.2.3'ün üç koşulunu uygular: türün `required_fields`'ında `document_number` (tohumda `profile_picture` ya da numarasız kopya → temiz değil), numara okunaklı ve normalize hâli en az 5 karakter (`AB123` temiz, `AB12` değil), MRZ alan ve bileşik haneleri tutuyor; anahtarda tek numara (iki numara çelişki, D8). `can_create_employee(key, match, *, entry)` §20.2.2 satır 6'yı yan etkisiz verir: yalnız `NO_MATCH` hükmü (satır 1–5 ve çelişkili anahtarın her biri yanlış), temiz numara, okunmuş ve klasör adı veren ad-soyad (D9). `create_employee(session, layout, key, *, entry, file_id, page_index)` tabloyu veritabanında yeniden değerlendirir; uyarsa E numarası (`E0041` varken `E0042`), `Test_Ornekova_E0001` klasörü (`Alinan/`, `Hazir/`), `employees` satırı (ad, soyad, diğer isimler, orijinal yazım, doğum tarihi, uyruk), `employee_aliases` (`Ad Soyad` + orijinal yazım, aynı yazım bir kez), `employee_identifiers` (tür slug'ı, normalize numara) ve `EMPLOYEE_CREATED` (kişisel değer yok) yazar, commit etmez; açılan çalışanı sonraki belge numarasından, ad-soyad + doğum tarihinden ve orijinal yazımından bulur (05.5), aynı anahtarla ikinci çağrı `eşleştirme hükmü document_number` ile reddedilir. Ret (`EmployeeCreationRefusedError`: kayıtlı numara, yalnız isim, çelişkili anahtar, okunaksız/eksik numara, MRZ hanesi, numarasız tür, okunmamış ad-soyad, klasör adına çevrilemeyen isim) hiçbir kayıt, alias, numara, olay ya da klasör yazmaz ve mesajında kişisel değer yoktur. 05.4 anahtarına yeni çalışan kaydının eşleştirmeye girmeyen okumaları eklendi (`surname`, `given_names` ilk okuma yazıldığı gibi, `other_names`, ICAO kodu biçimindeki `nationality`, MRZ önceliğiyle; çelişki `None`, `conflicts`'e girmez; `employee_fields()` sırası `EMPLOYEE_FIELDS`), üç tam anahtar testi yeni alanlarla güncellendi (kurallar: C28). 21 kural bozulması (5 karakter sınırı, `required_fields` koşulu, okunaklılık, MRZ koşulu, tek numara, `NO_MATCH` koşulu, çağıranın hükmüne güvenme, ad-soyad okunması, klasör adı denetimi, orijinal yazım alias'ı, alias yazım sırası, numara `kind`'ı, klasör açma, olay verisi, E numarası tahsisi, uyruk anahtarı ve biçimi, ilk okuma, orijinal yazım yerine Latin karşılığı, diğer isimlerin isim anahtarı) geçici olarak denendi, 20'si testte kırmızı; hayatta kalan (aynı ham yazıma iki normalize değer) oluşturulabilen bir anahtarda farklılaşmıyor — `app/matching/match.py` · test `tests/matching/test_employee_creation.py` (15 fonksiyon / 41 durum), `tests/matching/test_person_key.py` (41 / 61, +6 / +11) · tm 37
- ✅ S11 (çalışan ve klasör düzeyi): sentetik PDF gerçek render adımlarından ve `russian_passport` kaydıyla analizden geçer, kayıtlı çalışan yokken `group_upload` → `build_person_key` → `match_employee` (`no_match`, `PERSON_NOT_MATCHED`) → `create_employee` E0001'i `Test_Ornekova_E0001` klasörüyle açar; olay zinciri parti, dosya ve sayfaya bağlı, kişisel değer taşımaz; commit sonrası aynı anahtar numarasından E0001'le eşleşir. S13 kaydı `Iulia_Testova_Shchelkina_E0001` açar ve orijinal yazımı (`Тестова-Щёлкина Юлья`) çalışan kaydında saklar. S9 bulanık pasaportunun numarası okunamadığı için (isim okunmuş olsa da) çalışan ve klasör açılmaz (R9). `profil.md` (09.1.1), belgenin Hazir çıktısı (07.x) ve boru hattına bağlama (06.1) sonraki görevlerin — `tests/fixtures/ai/recordings/russian_passport/0.json`, `s13_cyrillic_name/0.json`, `s9_blurred_passport/0.json` · test `tests/matching/test_employee_creation.py` · tm 37

#### K05.7 — 05.7.1, 05.7.2 · Onay bekleyen profil ve alias birikimi
- ✅ 05.7.1 `resolve_unmatched(key, match, *, entry)` (`app/matching/match.py`) `NO_MATCH` hükmünü §20.2.2 satır 6–8'e çevirir ve `EmployeeMatch` ile aynı `action`/`queue`/`reason`'ı verir: temiz numara yokken (okunaksız, 4 karakter, MRZ hanesi, numarasız tür, numara yok) okunmuş ad-soyad → `pending_profile` (`pending`, Unresolved, `PENDING_PROFILE_REASON`, `ProposedProfile`); temiz numara ve klasör adı → `create` (`can_create_employee` ile aynı karar); ne isim ne numara (yalnız doğum tarihi dahil) → `no_person`; klasör adı kurulamayan ya da eksik okunan kişi → `incomplete_person` (`none`, Unresolved, profil yok; D9, D10); öteki hükümde `ValueError`. `ProposedProfile` çalışan kaydı okumalarını ve onayda yazılacak `(raw_name, normalized_name)` çiftlerini taşır (orijinal yazımın anahtarı sayfa diliyle — Ukraynaca örnek), numara taşımaz; `payload()` JSON uyumlu `proposed_profile`. `propose_pending_profile(session, key, *, entry, file_id, page_index)` tabloyu veritabanında yeniden değerlendirir, yalnız `EMPLOYEE_PENDING` yazar (kişisel değer yok): çalışan, alias, numara, klasör oluşmaz, commit yok, aynı anahtardan `create_employee` hâlâ reddedilir; kayıtlı numara, isim + doğum tarihi, yalnız isim, çelişkili anahtar, temiz numara, kişisiz ve eksik anahtarda `PendingProfileRefusedError` hiçbir şey yazmaz (kurallar: C29) — test `tests/matching/test_pending_profile_and_aliases.py` (25 fonksiyon / 61 durum) · tm 38
- ✅ 05.7.2 `accumulate_identity(session, key, *, entry)` satır 1 ve 3'teki eşleşmeyi veritabanında yeniden değerlendirir ve eşleşen çalışana yalnız yeni ham isim yazımlarını (`Ad Soyad`, orijinal yazım; aynı normalize anahtarlı farklı yazım da yeni) ve §20.2.3'e göre temiz, çalışanda hiçbir türle kayıtlı olmayan numarayı (tür slug'ı, normalize) ekler, `IdentityAccumulation` döner; numarayla eşleşmede numara yeniden yazılmaz, tekrar çağrı boş döner, başka çalışana dokunulmaz, temiz olmayan numara eklenmez (D11), olay ve commit yok; eşleşme yoksa (hiç eşleşme, yalnız isim, iki belirsizlik, çelişkili anahtar) `IdentityAccumulationRefusedError` hiçbir şey yazmaz. 20 kural bozulması (temiz numara şartı, bilinen numara/yazım denetimi, orijinal yazım, eşleşme şartı, satır 6/7 ayrımı, klasör adı şartı, satır 8 koşulları, kuyruk ve eylem, veritabanında yeniden değerlendirme, olay türü ve verisi, tarih biçimi, profil alanı, hüküm denetimi, numara türü, çoklu yazım, eksik kişi gerekçesi) geçici olarak denendi, her biri testte kırmızı — `app/matching/match.py` · test `tests/matching/test_pending_profile_and_aliases.py` · tm 38
- ✅ S9 (profil düzeyi) ve birikim zinciri: bulanık pasaport kaydı gerçek render ve kayıtlı yanıtla `group_upload` → `build_person_key` → `match_employee` (`no_match`) → `resolve_unmatched` (`pending_profile`) → `propose_pending_profile`'dan geçer; önerilen profil kayıttaki okumaları taşır, çalışan ve klasör açılmaz, `PERSON_NOT_MATCHED` ve `EMPLOYEE_PENDING` parti/dosya/sayfaya bağlı ve kişisel değersiz. `russian_passport` kaydı yalnız isim + doğum tarihiyle bilinen çalışana satır 3'le eşleşip `00 0000001` okumasını normalize `000000001` olarak biriktirir, sonraki numaralı anahtar satır 1'le eşleşir. Aynı kişinin temiz numaralı belgesi çalışanı açınca numarasız belge satır 3'le eşleşir, profil önerisi reddedilir, birikim boş döner. Kuyruk kaydı (08.1), onay (08.3) ve boru hattına bağlama (06.1) sonraki görevlerin — `tests/fixtures/ai/recordings/s9_blurred_passport/0.json`, `russian_passport/0.json` · test `tests/matching/test_pending_profile_and_aliases.py` · tm 38

#### K05.8 — 05.8.1, 05.8.2, 05.8.3 · İletişim bilgisi, dil ve alfabe kaydı
- ✅ 05.8.1, 05.8.2 `record_contact_sighting(session, *, employee_id, kind, value, source_document_id=None)` (`app/db/models.py`) `employee_contacts`'ı günceller: türün güncel (`is_current`) kaydı aynı değeri taşıyorsa yalnız `last_seen_at` ilerler (`changed: False`, yeni satır yok); farklı değerde güncel kayıt kapatılır (`is_current: False`) ve yeni değer ayrı bir satır olarak eklenir — eski kayıt silinmez, geçmiş kalır (K16). `app/matching/contacts.py` — `collect_contacts(analyses)` adayın sayfalarından (`person.contact`, §8.4) her tür (`phone`, `email`, `address`) için en son görülen değeri toplar; boş/okunamaz sayfa okunmaz (K1), yazılmayan tür sözlükte yer almaz. `accumulate_contacts(session, employee_id, analyses, *, source_document_id=None)` her okunan türü `record_contact_sighting`'e yazar, bu çağrıda güncel satırı değişen türleri döner. `source_document_id` bu aşamada (05.5–05.7, çıktı belgesi henüz yok) boştur — `employee_identifiers`/`employee_aliases`'ın izlediği örüntüyle aynı (D11); olay yazılmaz (§8.3'te tür yok, D6/D11 ile aynı gerekçe) — `app/db/models.py`, `app/matching/contacts.py` · test `tests/db/test_contact_sighting.py` (6), `tests/matching/test_contacts.py` (12) · tm 39
- ✅ 05.8.3 `employee_aliases.script` artık dolu: `_detect_script(text)` (`app/matching/match.py`) yazımın ilk harfinin Unicode adına bakar (`LATIN`/`CYRILLIC`/`ARABIC` önekiyle başlıyorsa o alfabe, harf varsa ama önek tutmuyorsa `other`, hiç harf yoksa `None`); `create_employee` ve `accumulate_identity` her alias yazarken bunu kullanır. Sayfa kaydının dili ve alfabesi (`pages.analysis_json.language`/`.script`) 03.1.2 ile zaten saklanıyordu — bu görev yalnız çalışan düzeyinde (`employee_aliases`) alfabe bilgisini ekledi ki 09.1 profil üretimi çalışanın belgelerinde görülen alfabeleri listeleyebilsin. İlk harften önceki rakam/noktalama atlanır (`007 BOND` → `latin`), hiç harf yoksa `None` (`007 1990`) — `app/matching/match.py` · test `tests/matching/test_employee_creation.py` (+4: iki alfabe + iki kenar durumu), `tests/matching/test_pending_profile_and_aliases.py` (güncellenen `script` beklentisi) · tm 39

#### K06.1 — 06.1.1, 06.1.2 · Plan JSON üretimi ve determinizm
- ✅ 06.1.1 `create_plan(session, layout, upload, *, catalog, model, reference_date)` partiyi gruplar ve her aday (dosya içi/dosyalar arası), Word/Excel eki, boş sayfa (`skip`), analizi yapılamamış sayfa ve işlenemeyen dosya (`unresolved`, D14) ve tekrar yükleme (`skip`) için `sources`, `operation` (06.2'ye kadar `null`), `target_format`/`target_name` (çalışan kaydının adıyla K8, `keep` içerikten), `employee` ve `route`/`route_reason` taşıyan §8.5 öğesi üretir; rota önceliği bilinmeyen tür → yapısal hüküm → okunaklılık (MRZ önceliği önce) → çalışan kararı, yan etkiler yalnız kabul edilen adayda (D13); `plans`'a sürümüyle yazar, `PLAN_CREATED` — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` (67) · tm 40
- ✅ 06.1.2 `plan_hash` kanonik JSON'un (sıralı anahtar, boşluksuz, UTF-8) SHA-256'sı: geri alınıp aynı analizlerden yeniden üretilen plan ve ayrı veritabanında anahtar sırası değiştirilmiş analizlerden üretilen plan aynı bayt ve hash'i verir, analiz değişince hash değişir; MRZ yüzyılı saat değil partinin alındığı günle seçilir; `read_plan` saklanan planı sözleşme, parti/sürüm/model ve hash ile doğrular (`PlanIntegrityError`); `plan.py` satır+dal kapsamı %100, 22 kural bozulması geçici olarak denendi, her biri testte kırmızı — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` · tm 40

#### K06.2 — 06.2.1 · İşlem seçimi
- ✅ 06.2.1 `select_operation(sources, *, output_format)` §20.3 karar tablosunu sırayla uygular (ilk uyan satır): tek dosyanın tüm sayfaları aynı biçimde (ya da `keep`) `passthrough` (S1, Word/Excel eki S15), tek PDF'in ardışık alt kümesi — boş sayfa arada ya da dışarıda kalabilir — `extract` (S4, S7, S8), birden çok dosya → PDF `merge` (S5), tek JPEG/PNG → PDF `wrap_image`, tek PDF sayfası → JPEG gömülü tek görüntüde `extract_image`, yoksa `render_image` (gerçek PDF'ten 02.5.1 işaretiyle); uyan satır yoksa `NoApplicableOperation` Unresolved gerekçesi (dosya, sayfa, biçim, kapsama, hedef; kişisel değer yok). Planlayıcı kapsamayı sayfa satırları ∪ `page_count`'la, boş sayfaları gruplamadan, biçimi içerikten okur; seçim yapısal hükümlü adaya uygulanmaz, okunaklılıktan sonra ve çalışan kararından önce yürür (işlemi olmayan belgeden çalışan açılmaz); `hazir` öğede `operation`/hedef zorunlu, kuyruk öğesinde `operation` boş (C31, D15). `plan.py` satır+dal kapsamı %100, 21 kural bozulması geçici olarak denendi, her biri testte kırmızı — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` (109, +42) · tm 41

#### K06.3 — 06.3.1, 06.3.2 · Direkt Belge kuralı
- ✅ 06.3.1 `check_direct_operation(operation, *, entry)` §20.4 matrisini uygular: `direct: true` türde yalnız `passthrough` ve `extract` izinli, `merge`/`wrap_image`/`extract_image`/`render_image` `DirectOperationForbidden` ("Direkt Belge: <işlem> bu tür için yapılamaz."); `direct: false` türde matris reddetmez (06.4). Planlayıcı §20.3'ün seçtiği işlemi matristen geçirir: ret işlemi ve hedefi plandan siler, belge Unresolved'a gider, çalışan açılmaz, `DIRECT_DOC_CHECK` yazılır; JPEG çıktılı Direkt türde gömülü görüntü çıkarma ve render, PDF çıktılı Direkt türde görüntü sarma gerçek dosyalarla reddedildi; S7 `extract` olaysız geçer (C32) — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` (129, +20) · tm 42
- ✅ 06.3.2 `check_direct_file_types(sources, *, entry)` §20.4.1'i işlem seçiminden önce uygular: Direkt türde içerikten tespit edilen kaynak biçimi `expected_file_types`'ta yoksa (tanınmayan biçim dahil) işlem seçilmez, gerekçe "Direkt Belge: beklenen dosya türü pdf, gelen jpeg. Uygun formatta yeniden gönderin.", rota Unresolved, `DIRECT_DOC_CHECK`. S6: yalnız PDF bekleyen pasaport JPEG geldi → Unresolved, dönüşüm yok, işlem/hedef yok, çalışan açılmaz, kayıtlı çalışan yalnız kişi tahmini; format gerekçesi okunaklılık gerekçesinin ardından gelir ve satır 7'yi keser. `plan.py` satır+dal kapsamı %100, 14 kural bozulması geçici olarak denendi, 13'ü testte kırmızı (kalan eşdeğer: ret varken seçimi taşımak öğeyi değiştirmez) — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` · tm 42

#### K06.4 — 06.4.1 · Dönüşüm izni kontrolü
- ✅ 06.4.1 `check_conversion(operation, *, entry)` §20.3 satır 3–6'nın işlemlerini (`CONVERSION_OPERATIONS`: `merge`, `wrap_image`, `extract_image`, `render_image`, katalogdaki `Conversion` adları) türün `allowed_conversions`'ında arar; listede yoksa `ConversionNotAllowed` ("Dönüşüm izni yok (06.4.1): <işlem> bu türün izinli dönüşümleri arasında değil (allowed_conversions: merge). Belge dönüştürülmez."), `passthrough`/`extract` boş listede de izinli. Planlayıcı kontrolü Direkt Belge matrisinden sonra uygular, ilk ret keser: izinsiz dönüşüm plana girmez, belge Unresolved'a gider, çalışan açılmaz, kimlik ve iletişim bilgisi birikmez, kayıtlı çalışan kişi tahmini kalır, olay yok (C33). Gerçek dosyalarla: `merge`'e izinli çalışma izni JPEG'i sarılmaz, `wrap_image`'a izinli oturum kartının ayrı yüzleri birleştirilmez, tohum katalogdaki `wrap_image` izni Hazir'a gider; JPEG çıktılı türde gömülü tek görüntülü sayfanın izinsiz `extract_image`'ı `render_image`'a düşmez, görüntüsüz sayfanın `render_image`'ı kendi iznini ister; gerekçe okunaklılık gerekçesinin ardından gelir. `plan.py` satır+dal kapsamı %100, 9 kural bozulması (kontrolün kaldırılması, matrisle sıra, liste ayırıcısı, boş liste yazımı, eksik dönüşüm, `passthrough`/`extract`'ın dönüşüm sayılması, listedekinin reddi, gerekçedeki liste, kuyruk) geçici olarak denendi, her biri testte kırmızı — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` (147, +18) · tm 43

#### K06.5 — 06.5.1, 06.5.2 · Doğrulayıcı seti
- ✅ 06.5.1 yedi saf doğrulayıcı, 06.5.1 sırasıyla (`ValidationName`): `required_fields` (04.4.1 hükmü, Unreadable), `page_count` (04.5.1 hükmü), `sides` (`front_back` türde tam `(front, back)`), `direct_single_source` (Direkt türde tek kaynak, arada yalnız boş sayfa), `file_type` (her türde içerik biçimi `expected_file_types`'ta, Direkt türde §20.4.1), `mrz_checksum` (§20.1.7: alan/isteğe bağlı veri/bileşik hanesi tutmayan ya da izin verilmeyen karakterli MRZ geçmez; MRZ'siz, biçimi tanınmayan, güvenilmeyen sayfa ve görünen metinle çelişki hata değil), `dob_plausible` (§20.1.6: kişi anahtarının doğum tarihi referans günden önce ve 16–90 yaş, iki uç dahil, 29 Şubat dahil); her biri geçen ve kalan örnekle, gerekçesi kişisel değer taşımadan (C34) — `app/pipeline/validate.py` · test `tests/pipeline/test_validate.py` (67) · tm 44
- ✅ 06.5.2 planlayıcı katalog türündeki bütün adayı önce yapı (`page_count`, `sides`), sonra öteki doğrulayıcılardan geçirir, sonucu öğenin `validations`'ına yazar; geçmeyen doğrulama öğeyi kuyruğa gönderir (`required_fields` Unreadable, öteki altısı Unresolved), gerekçe doğrulayıcı sırasıyla `route_reason`'a eklenir, `VALIDATION_FAILED` (item_id, validation, tür, kuyruk) yazılır, çalışan açılmaz; kaynak doğrulaması geçmeyen belgede işlem seçilmez; Word/Excel eki kaynak doğrulayıcılarından geçer; sözleşme `hazir` öğede dolu ve hepsi `ok` doğrulama, tekrarsız ve sıralı ad ister. Gerçek dosyalarla: yalnız ön yüzlü oturma kartı, satırı eksik sayfayla dağılmış pasaport, yalnız PDF bekleyen izin JPEG'i, bileşik hanesi tutmayan pasaport (D16), 15 yaş doğum tarihli izin Unresolved'a gider; S6 ve MRZ yüzyılı testleri yeni hükümle güncellendi. `plan.py` ve `validate.py` satır+dal kapsamı %100, 19 kural bozulması geçici olarak denendi, her biri testte kırmızı — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` (164, +17) · tm 44

#### K06.6 — 06.6.1, 06.6.2 · Yeniden çalıştırma ve yeniden analiz
- ✅ 06.6.1 `rerun_plan(session, layout, upload, *, executor)` (`app/pipeline/orchestrate.py`) partinin güncel planını (`current_plan`, en yüksek sürüm) `read_plan` ile doğrular, `PLAN_RERUN` yazar ve aynı `plans` kaydını `PlanExecutor` portuna verir, `executed_at`'i günceller; sağlayıcı almaz, analiz/gruplama/eşleştirme/planlama yürümez (sağlayıcıya giden istek testi düşürür; plan, çalışan, aday tür ve analizler değişmez, yeni olay yalnız `PLAN_RERUN`); plan yoksa `NoPlanError`, değişmiş plan `PlanIntegrityError` — olay ve uygulama yok; S18 plan katmanında: öğe başına idempotent sahte uygulayıcıyla iki yeniden çalıştırma aynı çıktıyı, tek dosyayı ve aynı baytları bırakır (dosya düzeyi garanti 07.8.1, uçtan uca S18 09.3-d; C35) · test `tests/pipeline/test_orchestrate.py` (11) · tm 45
- ✅ 06.6.2 `reanalyze_upload(session, layout, upload, *, provider, catalog, executor, reference_date=None)` planı olan partiyi sağlayıcıya yeniden gönderir (planı yoksa sağlayıcı çağrılmadan `NoPlanError`), `create_plan` ile sürüm +1 açar, önceki sürümlerin `active` çıktılarını `DocumentStatus.SUPERSEDED` yapar — satır, yol ve dosya baytları yerinde, başka partinin/plansız/zaten eski çıktıya dokunulmaz — `PLAN_REANALYZED` yazar ve yeni planı uygular; planın açtığı çalışan yeni sürümde numarasından bulunur (ikinci çalışan yok), yeni çıktı `-2` adını alır, sonraki yeniden çalıştırma yeni sürümü ikinci kopyasız uygular; analiz edilemeyen sayfada da sürüm açılır, parti `partial`. Göç `0002` `queue_items.plan_id` (C5) · test `tests/pipeline/test_orchestrate.py`, `tests/db/test_migrations.py` (+1: 0001↔0002 kayıt korunur), `tests/db/test_models.py` · tm 45
- ✅ API `POST /api/uploads/{id}/rerun` (sağlayıcı bağımlılığı yok) ve `POST /api/uploads/{id}/reanalyze` (`get_analysis_provider`, kurulamazsa 503) tek işlemde çalışır, yalnız başarıda commit; bilinmeyen parti 404, plan yok/değişmiş 409, uygulayıcı hatasında hiçbir şey yazılmaz; `get_plan_executor` uygulayıcı bağlanana kadar 503 — `app/web/routers/uploads.py` · test `tests/web/test_uploads.py` (+9) · tm 45
- ✅ Kapı: 1824 geçti (+21), kapsam %99.72 (`orchestrate.py` ve `uploads.py` %100); 11 kural bozulması (bütünlükten önce olay, durum/parti filtresi, `executed_at`, en eski plan, işaretleme yok, planı sormadan analiz, yeniden planlama, rerun'da sağlayıcı bağımlılığı, commit yok, model) geçici olarak denendi, her biri testte kırmızı · tm 45

#### K07.1 — 07.1.1 · passthrough işlemi
- ✅ `execute_passthrough(source, destination)` (`app/pipeline/execute.py`) kaynağı `copy_file` ile bayt bayt, atomik olarak hedefe kopyalar (yeniden yazma/yeniden kodlama yok, K10/K11); yayınlanan dosyanın SHA-256'sı kopyadan önce hesaplanan kaynak hash'iyle karşılaştırılır, eşleşmezse `PassthroughIntegrityError` — hedef zaten varsa `copy_file`'ın `FileExistsError`'ı olduğu gibi yükselir (üzerine yazma yok). Yalnız işlemin çekirdeği: çıktı yazma, köken kaydı, `documents`/`OUTPUT_SAVED` ve `Alinan` kopyası 07.7'nindir; işlem seçimi ve izinleri planlayıcının (06.2–06.4), bu görev planı yeniden sormaz. `execute.py` satır+dal kapsamı %100 — `app/pipeline/execute.py` · test `tests/pipeline/test_execute.py` (4) · tm 46

#### K07.2 — 07.2.1 · extract işlemi
- ✅ `execute_extract(source, destination, *, pages)` (`app/pipeline/execute.py`) kaynak PDF'in `PlanSource.pages` sayfalarını pypdf sayfa nesnesi kopyasıyla (`writer.add_page(reader.pages[i])`, `compress_content_streams` yok) yeni PDF'e çıkarır; sayfa render edilmez, içerik akışı ve gömülü görüntü baytları, boyut, `/Rotate` ve sayfa ağacından kalıtılan özellikler aynen taşınır (K3/K11). Doğrulama yayından önce bellekte: çıktı sayfa sayısı `len(pages)` ve her sayfanın MuPDF metin katmanı kaynağındakiyle birebir aynı, değilse `ExtractIntegrityError` ve hedefe yazma yok; geçen çıktı `write_file` ile atomik, üzerine yazma yok. PDF olmayan/bozuk/parolalı kaynak, olmayan sayfa ve okuyucular arası sayfa sayısı farkı `ExtractSourceError`, geçersiz sayfa seçimi `ValueError` (C36). S7 işlem katmanında: 4 sayfalık sentetik PDF'in pasaport sayfası tek sayfa çıkarılır — metin katmanı eşit, içerik akışı ve JPEG ham baytları kaynağınkiyle aynı (render yok); uçtan uca S7 09.3-c'nin. `execute.py` satır+dal kapsamı %100; 11 kural bozulması (sıkıştırma, yeniden sıralama, döndürmeyi içeriğe aktarma, metin/sayfa sayısı/okuyucu uyumu/aralık/tür/negatif/sıra denetimini kaldırma, doğrulamadan önce yayın) geçici olarak denendi, her biri testte kırmızı — `app/pipeline/execute.py` · test `tests/pipeline/test_execute.py` (31, +27) · tm 47

#### K07.3 — 07.3.1 · merge işlemi
- ✅ `execute_merge(sources, destination, *, direct)` (`app/pipeline/execute.py`, `MergeSource(path, pages)`) plan öğesinin en az iki kaynağının sayfalarını `sources` sırasıyla, kaynak içinde `pages` sırasıyla tek PDF'te birleştirir — yeniden sıralama yok (iki yönde doğrulandı); yöntem `extract`'la ortak çekirdek (`_copy_pages`, pypdf sayfa nesnesi kopyası, `compress_content_streams` yok): PDF sayfalarının içerik akışı, görüntü baytları, boyutu ve `/Rotate`'i aynen taşınır. Yalnız `direct: false` türde: `direct` doğruysa kaynaklar okunmadan `DirectDocumentMergeError` (K3; tohum katalogda `russian_passport` Direkt, `serbian_driving_license` değil). JPEG/PNG kaynak önce `img2pdf` ile kayıpsız sarılır: JPEG akışı kaynak baytlarıyla birebir, PNG pikselleri birebir, görüntü sayfayı tam kaplar, EXIF 6 yalnız `/Rotate 90`; alfalı PNG renk + `/SMask` olarak birebir (D17). Aynalı/geçersiz EXIF, bozuk görüntü, Word, tanınmayan içerik, bozuk/parolalı PDF, okuyucu uyuşmazlığı ve olmayan sayfa `MergeSourceError` (`sources[i]` konumuyla, dosya adı yok); tek/boş kaynak listesi ve geçersiz sayfa seçimi okumadan `ValueError`; çıktı sayfa sayısı ve sayfa başına metin katmanı yayından önce doğrulanır (`MergeIntegrityError`, hedefe yazma yok), hedef varsa `FileExistsError` (C37). Bağımlılık `img2pdf>=0.6` (K14) — `app/pipeline/execute.py` · `pyproject.toml` · test `tests/pipeline/test_execute.py` (62, +31) · tm 48
- ✅ S5 plan → uygulayıcı: aynı partide sentetik `on.jpg` (ehliyet ön) ve `arka.jpg` (ehliyet arka), iki yükleme sırasında da gerçek görüntü analiz kopyası + kayıtlı yanıtlarla `analyze_upload` → `create_plan`: tek `serbian_driving_license` öğesi `hazir`, `merge`, `pdf`, `…-Driving-License.pdf`, kaynaklar önce ön yüz; öğenin kaynakları Inbox yollarına çözülüp `execute_merge(direct=entry.direct)` ile yürütülür → tek 2 sayfalık PDF, sayfa 0 ön yüzün, sayfa 1 arka yüzün JPEG baytlarını birebir gömülü taşır (kayıpsız sarma ve birleştirme). Çıktının `Hazir/` yeri, köken kaydı ve `Alinan` kopyası 07.7'nin, uçtan uca S5 09.3'ün · test `tests/pipeline/test_execute.py` (`test_s5_planned_merge_item_yields_one_driving_license_pdf`, 2) · tm 48
- ✅ Kapı: `execute.py` satır+dal kapsamı %100; 16 kural bozulması (Direkt Belge bekçisi, tek kaynak, yol adına göre sıralama, okuduktan sonra sayfa denetimi, sıkıştırma, EXIF'i yok sayma, EXIF'i uygulamama, görüntüyü Pillow ile yeniden kodlama, tür denetimi, sarma hatasını yakalamama, sayfa aralığı, çıktı doğrulaması, okuyucu uyumu, mesajda kaynak konumu, hata sınıfı, metin katmanı denetimi) geçici olarak denendi, her biri yalnız `merge` testleriyle kırmızı · tm 48

#### K07.4 — 07.4.1 · wrap_image işlemi
- ✅ `execute_wrap_image(source, destination)` (`app/pipeline/execute.py`) kaynak JPEG/PNG'yi `img2pdf.convert()` ile kayıpsız tek sayfalık PDF'e sarar; JPEG akışı yeniden kodlanmadan gömülür, PNG pikselleri kayıpsız taşınır, EXIF yönelimi yalnız `/Rotate`'e yazılır (piksel döndürülmez). Yöntem `merge`'ün görüntü sarma yoluyla ortak çekirdekte (`_wrap_image_to_pdf`) paylaşılır — D17'nin kararı ikisine birden uygulanır. Kaynak JPEG/PNG değilse ya da img2pdf'in yedi hata sınıfından biriyle sarılamıyorsa (açılamayan/bozuk görüntü, aynalı/geçersiz EXIF, >8 bit alfa → `AlphaChannelError`) `WrapImageSourceError`; hedefe hiçbir şey yazılmaz, belge kuyruğa gider (tahmin edilmez). **D18:** §20.5 alfa reddinde beyaz zemine düzleştirmeyi ister; bu bir piksel dönüşümüdür ve K11'in izinli işlemler listesinde yoktur — `MASTER-PROMPT.md` §2 çelişki sırasında (bu dosya > PRD) kilitli kural kazanır, düzleştirme uygulanmadı; >8 bit alfalı PNG de öteki sarılamayan görüntüler gibi `WrapImageSourceError` ile kuyruğa gider. 8 bit alfalı PNG (yaygın durum) img2pdf tarafından zaten reddedilmediği için D17'deki gibi `/SMask` olarak kayıpsız saklanmaya devam eder. `execute.py` satır+dal kapsamı %100 — `app/pipeline/execute.py` · test `tests/pipeline/test_execute.py` (75, +13) · tm 49

#### K07.5 — 07.5.1 · extract_image işlemi
- ✅ `execute_extract_image(source, destination, *, page)` (`app/pipeline/execute.py`) sayfanın tek tam sayfa gömülü görüntüsünün `xref`'ini 02.5.1'in kuralıyla (`single_full_page_image_xref`) bulur ve `doc.extract_image(xref)` baytlarını Pillow'dan geçirmeden yazar: gömülü JPEG PDF'teki ham akışın baytlarıyla birebir (kabul kriteri), JPEG olmayan görüntü `.png` uzantısıyla ve gömülü görüntünün pikselleriyle birebir; tek tam sayfa görüntü olmayan sayfa `render_image`'a düşmez, `ExtractImageSourceError` (C38). **D19:** PyMuPDF'in CMYK JPEG'i yeniden kodlaması, zincirli süzgeç ve CMYK→RGB renk dönüşümü `ExtractImageIntegrityError`; JPEG 2000 ve 16 bit örnek `ExtractImageSourceError` — hepsi yayından önce yakalanır, belge kuyruğa gider. `execute.py` satır+dal kapsamı %100 — `app/pipeline/execute.py` · test `tests/pipeline/test_execute.py` (109, +34) · tm 50
- ✅ Plan → uygulayıcı: JPEG çıktılı türde gerçek PDF içeriğinden işaretlenen (02.5.1) sayfanın `extract_image` öğesi planın `target_name`'iyle o sayfanın gömülü JPEG'ini orijinal baytlarıyla yazar (`test_planned_extract_image_item_yields_the_embedded_jpeg_of_its_page`) · tm 50
- ✅ Kapı: 13 kural bozulması (ham akış karşılaştırması, uzantı, 02.5.1 kuralı, 8 bit sınırı, PNG piksel denetimi, bayt imzası, gri→RGB kanal denetimi, boyut denetimi, JPEG 2000 reddi, PDF imzası, sayfa aralığı, MuPDF hatası, negatif sayfa) geçici olarak denendi, her biri `extract_image` testleriyle kırmızı · tm 50

#### K07.6 — 07.6.1 · render_image işlemi
- ✅ `execute_render_image(source, destination, *, page, dpi, jpeg_quality)` (`app/pipeline/execute.py`) gömülü tek görüntü yoksa son çare: `document[page].get_pixmap(dpi=dpi, alpha=False)` ile sayfayı sabit çözünürlükte rasterleştirir, `pixmap.tobytes("jpeg", jpg_quality=jpeg_quality)` ile kayıplı JPEG yazar (§20.5, kabul kriteri). `dpi`/`jpeg_quality` planlayıcı gibi çağırana bırakılan yapılandırma değeridir — görevde sabit yazılmaz; `Settings.render_image_dpi`/`render_image_jpeg_quality` (varsayılan 200/90, `RENDER_IMAGE_DPI`/`RENDER_IMAGE_JPEG_QUALITY`) analiz önbelleğinin (`page_render_*`, 02.1.1) ayarından bağımsız yeni alanlardır (bkz. PLAN.md §C10). Kaynak PDF değilse, açılamıyorsa (bozuk, sahip parolalı açılır ama kullanıcı parolalı `parola korumalı` reddedilir) ya da sayfa kaynakta yoksa `RenderImageSourceError`, hedefe hiçbir şey yazılmaz; negatif sayfa `ValueError`; hedef varsa `write_file`'ın `FileExistsError`'ı. Dosya çok sayfalı olabilir (S3/S4), yalnız planlanan sayfa okunur — iki farklı geometrili sayfa içeren sentetik PDF ile sayfa seçiminin karıştırılmadığı kanıtlandı; DPI/kalite ayarının pikselde ve dosya boyutunda etkisi bağımsız `page.get_pixmap`/dosya boyutu karşılaştırmasıyla doğrulandı. Plan → uygulayıcı: JPEG çıktılı türde gömülü görüntüsü olmayan (02.5.1 işaretsiz) sayfanın `render_image` öğesi planın sayfasını rasterleştirir (`test_planned_render_image_item_yields_a_raster_of_the_planned_page`). `execute.py` satır+dal kapsamı %100 — `app/pipeline/execute.py` · `app/config.py` (`render_image_dpi`, `render_image_jpeg_quality`) · `.env.example` · test `tests/pipeline/test_execute.py` (125, +16) · tm 51

#### K07.7 — 07.7.1, 07.7.2 · Çıktı yazma, köken kaydı ve Alinan kopyası
- ✅ `execute_ready_item(session, layout, plan, item, *, render_image_dpi, render_image_jpeg_quality)` (`app/pipeline/execute.py`) `hazir` öğenin işlemini plandaki `operation`'la yürütür, çıktıyı çalışanın `Hazir/`'ına `write_sequenced` ile atomik ve K8 sıra ekiyle yazar (`extract_image` gerçek uzantı), `documents` satırına `source_refs_json` = öğenin `sources`'u (`file_id`, 0 tabanlı `pages`) işler, işlem olayı + `OUTPUT_SAVED` (köken verisi, kişisel değer yok) yazar; Inbox kaynağının hash'i `upload_files.sha256` ile doğrulanır (K10), ret ve işlem hatasında hiçbir şey yazılmaz — test `tests/pipeline/test_execute_output.py` (24; S5 merge, passthrough, extract `-2`, extract_image/render_image, wrap_image, gömülü PNG `-2.png`, Word eki `pages: []`) · tm 52
- ✅ Alinan kopyası `copy_to_received` (`app/storage/received.py`): Inbox adıyla, dolu adda `ad-2.uzantı` (`write_unique`, `app/storage/atomic.py`); aynı SHA-256 çalışan klasöründe varsa (başka ad/parti dahil) kopyalanmaz, kopya yayından önce hash'le doğrulanır; çalışan başına ayrı kopya, PostgreSQL'de çalışan başına advisory kilit — test `tests/storage/test_received.py` (8), `tests/storage/test_atomic.py` (+16), `tests/storage/test_layout.py` (+4, `DataLayout.relative`), `tests/storage/test_naming.py` (+6, `split_document_filename`) · tm 52
- ✅ Kapı: 2007 geçti (+58; 4 PG testi atlandı), kapsam %99 (`execute.py`, `received.py`, `layout.py`, `naming.py` %100); 12 kural bozulması (Alinan tekilliği, köken sırası, K10 hash denetimi, PNG uzantısı, advisory kilit koşulu, işlem olayı, beklenen hash, dosyanın partisi, passthrough yayın öncesi hash, `direct` bayrağı, Alinan kopyası, olay sayfası) her biri testte kırmızı · tm 52

#### K07.8 — 07.8.1 · Uygulayıcı idempotenliği
- ✅ `execute_ready_item` (`app/pipeline/execute.py`) plan öğesi başına idempotent: öğenin önceki uygulaması `executed_document(session, plan, item)` ile (`documents.plan_id` + `source_refs_json`) çalışan kilidinin altında bulunur; bulunursa kaynak okunmaz, işlem yürümez, hiçbir dosya/satır yazılmaz, `OUTPUT_SKIPPED` loglanır ve `ExecutedItem(document, None, ())` (`applied` yanlış) döner. Kabul kriteri: altı işlemin her biri commit sonrası iki kez daha uygulanınca `Hazir/`/`Alinan/` bayt bayt aynı, tek satır, tek `OUTPUT_SAVED` (bkz. PLAN.md §C40) — test `tests/pipeline/test_execute_idempotency.py` (25) · tm 53
- ✅ Geri alınmış uygulamanın diskte kalan çıktısı ikinci kez yazılmaz, kaydedilir: `find_sequenced(directory, stem, extension, *, sha256, size)` (`app/storage/atomic.py`) K8 adıyla aynı içerikli dosyaları bulur, `documents.path`'in göstermediği ilki benimsenir; iki aynı sayfanın çıktıları ve eski plan sürümünün dosyası birbirine verilmez. `wrap_image` sarması belirleyici (`Engine.internal`, `nodate`) — sahte saatle iki sarım aynı bayt, trailer'da `/ID` yok — test `tests/storage/test_atomic.py` (+17), `tests/pipeline/test_execute_idempotency.py` · tm 53
- ✅ S18: gerçek uygulayıcıyla (`rerun_plan` + `hazir` öğeleri `execute_ready_item`) iki yeniden çalıştırma — sağlayıcı çağrılmaz, aynı satır ve yol, `Hazir/`'da tek dosya kaynağıyla birebir, 2 `OUTPUT_SKIPPED`, 1 `OUTPUT_SAVED`, tek plan; iki eşzamanlı işlem (SQLite, iki oturum) tek çıktı yayınlar · tm 53
- ✅ Kapı: 2049 geçti (+42; 4 PG testi atlandı), kapsam %99.71 (`execute.py` %100); 11 kural bozulması (denetimsiz uygulama, benimsemesiz yeniden yazım, kayıtlı dosyayı benimseme, pikepdf yazıcısı, `nodate`'siz sarım, pikepdf+`nodate`, atlama olayı, durum süzgeci, sahip süzgeci, kilitten önce denetim, atlamada kaynak okuma) her biri testte kırmızı · tm 53

#### K08.1 — 08.1.1, 08.1.2 · Kuyruğa yönlendirme ve gerekçe dosyası
- ✅ `route_queue_item(session, layout, plan, item)` (`app/pipeline/route.py`) planın `unknown`/`unreadable`/`unresolved` öğesini kuyruğa alır (07.7'nin `execute_ready_item`'ıyla aynı tanecik): öğenin kaynak dosyaları `Unknown/`/`Unreadable/`/`Unresolved/<upload_id>/`'a Alinan'daki kuralla kopyalanır (orijinal ad, `write_unique`, aynı SHA-256 tekrar kopyalanmaz), `queue_items` satırı (`upload_id`, `plan_id`, `plan_item_id`, `kind`, `reason`, `payload_json`) yazılır ve §8.3 olayı (`QUEUED_UNKNOWN`/`QUEUED_UNREADABLE`/`QUEUED_UNRESOLVED`; mesaj `route_reason`, veri kişisel değer taşımaz) atılır. Plan öğesi başına idempotent (`queue_items.plan_id` + `plan_item_id`): aynı öğe ikinci kez kuyruğa alınmaya çalışılırsa kaynak okunmaz, hiçbir şey yazılmaz, önceki satır döner (`RoutedItem.applied` yanlış) — 06.6.1'in yeniden çalıştırması ikinci kopya üretmez.
- ✅ Gerekçe dosyası (08.1.2, K9): `reason.json` (`layout.queue_reason_path`) o (parti, kuyruk türü) çiftindeki **bütün** `queue_items` satırlarından `replace_file` ile baştan üretilir — türetilmiş dosya (`app/storage/atomic.py`'nin kuralı); her girdi `plan_item_id`, `reason` (route_reason — hangi sayfalar/hangi kural), `document_type_slug` (hangi tür; bilinmeyen türde `null`) ve `employee_guess` (kişi tahmini — `PlanEmployee`) taşır; aynı üçlü `queue_items.payload_json`'a da yazılır. Aynı yapı olay verisine de girer.
- ✅ Kapı: 2064 geçti (+15), kapsam %99.71 (`route.py` satır+dal %100) — test `tests/pipeline/test_route.py` (15: kaynak kopyası ve kuyruk satırı, tür/kişi tahmini `null`/dolu, olay verisi ve `page_index` boş dosya, gerekçe dosyasının dört alanı, aynı türden birden çok öğenin birikmesi, iki farklı kuyruk türünün ayrı dosyası, aynı kaynak dosyanın iki öğe arasında tek kopyalanması, idempotenlik, `hazir`/`skip` reddi, planın partisinde olmayan/başka partiye ait/hash'i tutmayan kaynak hatası, S14 bilinmeyen türün gerçek `create_plan` çıktısıyla uçtan uca kuyruğa alınması) · tm 54
- ✅ Kapsam dışı (PLAN.md §D20): önerilen profilin tam içeriği (§20.2.2 satır 7, `ProposedProfile`) bu görevde yeniden kurulmadı — eşleştirme modülüne ve sayfa analizlerine bağımlılık ister, bu görevin GİRDİ'sü yalnız `plan.py`/`execute.py`/`storage`'dı. `payload_json`/`reason.json` şimdilik yalnız plan öğesinin kendi taşıdığı `document_type_slug`/`sources`/`employee_guess` üçlüsünü yazıyor; karar insana bırakıldı (08.3'ün kapsamı).

#### K08.2 — 08.2.1 · Kuyruk öğesini çalışana atama
- ✅ `assign_queue_item(session, layout, queue_item_id, employee_id, *, actor, render_image_dpi, render_image_jpeg_quality)` (`app/pipeline/route.py`) partinin güncel planının çözülmemiş kuyruk öğesini insanın seçtiği çalışana atar: çıktı `execute_item` (`app/pipeline/execute.py`, `execute_ready_item`'ın `ItemDecision`'lı çekirdeği) ile atanan çalışanın `Hazir/`'ına K8 adıyla yazılır, kaynak `Alinan/`'a kopyalanır, `documents` dondurulmuş planın kimliği ve öğenin kaynaklarıyla kaydedilir; yapay zekâ çağrılmaz, plan sürümü açılmaz, plan ve analizler değişmez (K9). Kuyruk kaydı `resolved_at`/`resolved_by`, `MANUAL_ASSIGN` kullanıcı adıyla ve `document_id`'yle yazılır, `reason.json` çözülen öğeyi işaretler (kopya silinmez, K16). Türsüz öğe atanmaz; işlem planlayıcının kuralıyla seçilir (kaynak doğrulayıcıları, §20.3, Direkt Belge matrisi, dönüşüm izni — K3, K5, K11, K12 insan kararıyla aşılmaz; boş sayfalar planın `skip` öğelerinden, `operation_source` planlayıcıyla ortak); içerik/kişi hükümleri aşılır (PLAN.md §C41).
- ✅ `POST /api/queue/{queue_item_id}/assign` (`app/web/routers/queue.py`): gövde `employee_id`; K16 onaylanmış kullanıcı adı `get_confirmed_actor`'dan — oturum (10.1.2) ve onay belirteci (10.8.1) bağlanana kadar 503; yok 404, atanamaz/çözülmüş/eski sürüm/plan ya da Inbox değişmiş 409, yalnız başarıda commit, sağlayıcı bağımlılığı yok.
- ✅ Kapı: 2097 geçti (+33), kapsam %99.72 (`route.py`, `queue.py`, `execute.py`, `plan.py` %100) — test `tests/pipeline/test_route_assign.py` (25: Unreadable öğe atanınca çıktı + köken + `MANUAL_ASSIGN` ve sağlayıcıya istek yok/analiz ve plan değişmedi, boş sayfalı kartta `extract` (S8), bağlamsız Word eki `passthrough` (S15), `reason.json` işaretlemesi, yeniden yönlendirmede yeni yazım yok, bilinmeyen tür/S6/§20.3 satır 7/tanınmayan biçim/planlamadan sonra Direkt Belge ya da dönüşüm izni değişen katalog/katalogda olmayan tür/işlem hatası/Inbox değişmiş reddi ve hiçbir şey yazılmaması, çözülmüş/çıktısı olan/eski sürüm/plansız/planla uyuşmayan kayıt, değişmiş plan, bilinmeyen öğe/çalışan, boş kullanıcı adı, işlem sınırı çağıranda) · `tests/web/test_queue.py` (8: onaysız 503 ve değişiklik yok, 200 + commit + sağlayıcı kurulmadı, ikinci atama 409, türsüz öğe 409, 404 ×2, 422 ×2); 9 kural bozulması geçici olarak denendi, her biri testte kırmızı · tm 55.

#### K08.3 — 08.3.1 · Onay bekleyen profili onaylama
- ✅ `approve_queued_profile(session, layout, queue_item_id, *, actor, render_image_dpi, render_image_jpeg_quality)` (`app/pipeline/route.py`) güncel planın çözülmemiş `employee.action: pending` kuyruk öğesini onaylar: önerilen profil öğenin saklanan sayfa analizlerinden `build_person_key` ile yeniden kurulur (yapay zekâ çağrılmaz, plan ve analizler değişmez — K9), tür/fiziksel işlem/çıktı denetimleri çalışan açılmadan önce yapılır, çalışan `approve_pending_profile` (`app/matching/match.py`) ile açılır ve belge atamanın ortak çekirdeğiyle (`_resolve_with_output`) onun `Hazir/`'ına K8 adıyla yazılır, kaynak `Alinan/`'a kopyalanır; kuyruk kaydı `resolved_at`/`resolved_by`, `MANUAL_APPROVE` kullanıcı adıyla yazılır, belgedeki iletişim bilgisi yeni çalışana eklenir (PLAN.md §C42, §D20).
- ✅ `approve_pending_profile(session, layout, key, *, entry, actor, file_id, page_index)` satır 7'yi onay anında veritabanında yeniden değerlendirir (kişi öneriden sonra kayıtlı çalışanla eşleşiyorsa `ProfileApprovalRefusedError`, hiçbir şey yazılmaz — aynı kişinin ikinci önerisi ikinci çalışan açmaz); uyuyorsa E numarası (hükümden önce, tahsis kilidiyle), `ProposedProfile` alanlarıyla `employees` satırı, yazımlar (`script` ile), `Alinan/`+`Hazir/` ve kullanıcı adlı `EMPLOYEE_CREATED`; temiz olmayan numara yazılmaz (D11).
- ✅ Kapı: 2131 geçti (+34; 4 PG testi atlandı), kapsam %99.72 (`route.py` satır+dal %100, `match.py` yeni kod %100) — test `tests/pipeline/test_route_approve.py` (19: onay sonrası çalışan + çıktı + köken + iletişim bilgisi + `EMPLOYEE_CREATED`/`OUTPUT_SAVED`/`MANUAL_APPROVE` ve sağlayıcıya istek yok/analiz ve plan değişmedi, boş sayfalı kartta `extract`, aynı kişinin ikinci önerisinin reddi ve yeni çalışana atanması, öneriden sonra kaydedilen kişi, Unreadable ve yalnız isim öğesinin reddi, dönüşüm izni ve Inbox değişikliğinde çalışan açılmaması, analiz yok/başarısız/şemaya uymuyor, işlem hatasında çağıranın geri alması, çözülmüş/yeniden yönlendirilmiş/eski sürüm/bilinmeyen öğe, boş kullanıcı adı ×2, işlem sınırı çağıranda) · `tests/matching/test_profile_approval.py` (15: profilden çalışan, sıradaki E numarası, satır 7 dışı yedi hükmün reddi, ikinci onayın reddi ×2, boş kullanıcı adı ×2, commit yok, kayıtlı yanıtlı pasaport önerisinin onayı); 6 kural bozulması (pending denetimi, yeniden değerlendirme, denetimlerin çalışandan sonra yapılması, iletişim bilgisi, olay türü, `actor`) geçici olarak denendi, her biri testte kırmızı · tm 56

#### K08.4 — 08.4.1 · Arşive taşıma
- ✅ `archive_document(session, layout, document_id, *, actor, today=None)` (`app/storage/archive.py`) etkin (`DocumentStatus.ACTIVE`) belgeyi `Archive/<yyyy-mm>/`'e taşır (R11, K11): kaynak `write_unique` ile hedefe yayınlanır (K8'deki gibi `-2`, `-3`… ekiyle çakışmasız, `expected_sha256` ile bütünlük doğrulanır), yayın bittikten sonra kaynak silinir — gerçek bir taşıma, kopya bırakılmaz; `documents.path`/`status` (`archived`) güncellenir, satır/köken/sıra numarası silinmez ya da yeniden adlandırılmaz (K18'deki gibi). Belge satırı `with_for_update` ile kilitlenir (eşzamanlı ikinci çağrı belgeyi arşivlenmiş görür). Yalnız `active` belge arşivlenir; zaten arşivlenmiş ya da eski sürüm (`superseded`) `DocumentNotArchivableError`, kayıt yoksa `DocumentNotFoundError`; K16 gereği `actor` boşsa `ValueError`. Başarıyla biten işlem `ARCHIVED` olayını (K15) kullanıcı adı, belge ve çalışan kimliğiyle yazar. Oturum commit edilmez.
- ✅ `POST /api/queue/documents/{document_id}/archive` (`app/web/routers/queue.py`): gövde yok; K16 onaylanmış kullanıcı adı `get_confirmed_actor`'dan — oturum (10.1.2) ve onay belirteci (10.8.1) bağlanana kadar 503; belge yoksa 404, etkin değilse (zaten arşivlenmiş/eski sürüm) 409, yalnız başarıda commit.
- ✅ Kapı: 2143 geçti (+12), kapsam %99.73 (`archive.py`, `queue.py` %100) — test `tests/storage/test_archive.py` (8: arşive taşıma + durum/yol güncellemesi + kaynağın silinmesi + `ARCHIVED` olayı, bulunamayan belge, eski sürüm/zaten arşivlenmiş belgenin reddi ×2, ikinci arşivlemenin reddi, boş kullanıcı adı ×2, işlem sınırı çağıranda) · `tests/web/test_queue.py` (+4: onaysız 503 ve değişiklik yok, 200 + durum/dosya taşınması + olay, ikinci arşivleme 409, bilinmeyen belge 404) · tm 57

#### K09.1 — 09.1.1, 09.1.2, 09.1.3 · profil.md üretimi
- ✅ `render_profile(session, employee, *, today=None)` (`app/profiles/render.py`) `profil.md` içeriğini çalışanın güncel veritabanı kaydından baştan üretir — kısmi güncelleme yoktur, bu yüzden herhangi bir değişiklikten sonra çağrı güncel hâli verir (09.1.1). Sıra: YAML ön blok (`employee_id`, `folder_name`, `given_names`, `surname`, `other_names`, `original_script_name`, `nationality`, `date_of_birth`, hesaplanan `age`, `document_numbers`, `contacts`), `## Kimlik` tablosu (aynı alanlar + iletişim satırları, okunmayan `—`) ve `## Belgeler` tablosu (tür adı, dosya adı, durum, tarih; belge yoksa "Henüz belge yok."). `given_names`/`surname` belgeden okunan yazımdır, `original_script_name` doluysa Latin olmayan asıl yazım ayrıca görünür — ikisi birlikte göründüğü için 09.1.2 ayrı dönüştürme istemez. `calculate_age(date_of_birth, *, today)` tam yaşı verir. `write_profile(session, layout, employee, *, today=None)` çıktıyı `layout.profile_path(employee.folder_name)`'e `replace_file` ile atomik yazar (dosya varsa baştan üretilir, elle düzenleme beklenmez — §8.2).
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2157 geçti, +14; 4 PG testi atlandı), kapsam %99.73 (`app/profiles/render.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0002, bu görevde göç yok), `import app.main` — hepsi exit 0 — test `tests/profiles/test_render.py` (14: YAML ön blok + kimlik tablosu + belge listesi, Latin olmayan isimde ikisi bir arada, yalnız Latin isimde orijinal yazım yer tutucusu, eksiksizlik, okunmayan alan yer tutucusu, yalnız güncel iletişim satırı, `calculate_age` 4 durum, `write_profile` yayın yolu + değişiklik sonrası yeniden üretim + eski içerik kalmaması, birden fazla belge durumu) · tm 58
- ✅ Manuel işlemlerden sonra profil yeniden üretimi (09.1.1 "her değişiklikten sonra yeniden üretilir"): `assign_queue_item` (08.2.1) atanan çalışanın, `approve_queued_profile` (08.3.1) onayla açılan çalışanın (belgeden eklenen iletişim bilgisi `accumulate_contacts`'tan sonra yazıldığı için profilde), `archive_document` (08.4.1) belgenin sahibinin `profil.md`'sini son adım olarak `write_profile` ile yeniden üretir; ret yollarında profil yazılmaz, yalnız etkilenen çalışan yazılır, oturum commit edilmez (PLAN.md §C59, §D31) — `app/pipeline/route.py`, `app/storage/archive.py` (`app.profiles` döngüsü için yerel içe aktarma) · test `tests/pipeline/test_route_assign.py` (2), `tests/pipeline/test_route_approve.py` (2), `tests/storage/test_archive.py` (3: 1 + 2 parametre; bayat profilin baştan yazılması, başka çalışanın profilinin yazılmaması, geçici dosya kalmaması, ret yollarında profilsizlik; her çağrının çıkarılması ve onayda sıranın bozulması testte kırmızı) · tm 93
- ✅ Kapı (tm 93): ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2911 geçti, +7; 4 PG testi atlandı), kapsam %99.81, temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0 (kapı `COVERAGE_FILE=.pytest_cache/.coverage` ile koşuldu) · tm 93

#### K09.2 — 09.2.1, 09.2.2, 09.2.3 · Orkestrasyon ve parti durum makinesi
- ✅ Durum makinesi `UPLOAD_TRANSITIONS` + `check_transition` (`app/pipeline/orchestrate.py`): `received → rendering → analyzing → planning → executing → done/partial`, bitmemiş her durumdan `failed`, son durumlardan çıkış yok; her geçiş `uploads.status`'a yazılıp commit edilir (geçiş olayı yok, D21) — test `tests/pipeline/test_process_upload.py` (tablo, 6 ret, zincir; commit sırası motorun `commit` olayıyla; analiz sürerken ayrı bağlantı `analyzing` okur) · tm 59
- ✅ `process_upload(session, layout, upload, *, settings, provider)` `received` partiyi tek çağrıda render → analiz → plan → uygulama → `done`/`partial` götürür (yalnız `received`, satır kilidiyle; render reddi partiyi durdurmaz); `execute_plan`/`plan_executor` hazir → çıktı, kuyruk rotaları → `route_queue_item`, skip → `OUTPUT_SKIPPED`, sonra partinin çalışanlarının `profil.md`'si; `get_plan_executor` gerçek uygulayıcı, yürütülemeyen öğe 409 (`app/web/routers/uploads.py`) — test `tests/pipeline/test_process_upload.py` (uçtan uca pasaport + boş sayfa + Word, S2, S5, kısmi analiz, render reddi, yalnız `received`, yeniden analizde profil) · `tests/web/test_uploads.py` (gerçek uygulayıcıyla rerun, 409) · tm 59
- ✅ 09.2.3: dört adımın her birinde beklenmeyen hata adımın veritabanı işini geri alır, partiyi `failed` yapar, Inbox'ı bayt bayt bırakır, `PIPELINE_FAILED` (`stage`, `error`, `traceback`; dış hata metni ve kişisel değer yok) yazar; uygulamanın kendi hatası (K10 Inbox değişmiş) metniyle loglanır; yürütmede duran parti `rerun` ile ikinci dosya olmadan kurtarılır · tm 59
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2184 geçti, +27; 4 PG testi atlandı), kapsam %99.74 (`orchestrate.py` %100, `uploads.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0; 8 kural bozulması (dış hata metni, geri alma, render reddi, `partial`, profil, geçiş commit'i, skip izi, tekrar dosyası) testte kırmızı · tm 59

#### K09.3-a — 09.3.1 · Sentetik belge üreteci
- ✅ MRZ yazıcısı `make_mrz_lines` (TD1/TD2/TD3) ve `mrz_check_digit` (`tests/fixtures/gen.py`) §20.1.3–§20.1.5'i ayrıştırıcıdan bağımsız uygular (alanlar anlamlarıyla birleşir, bileşik hane kapsanan alanların bitişik birleşimi; sığmayan alan kesilmez, reddedilir); ICAO "Utopia" örneklerini birebir üretir, `parse_mrz` üretilen her MRZ'yi aynı değerlere ve tutan hanelere geri okur, yazılan her haneyi bozmak yalnız o alanı + bileşik haneyi düşürür — test `tests/fixtures/test_gen.py` · tm 60
- ✅ Kimlikli sentetik sayfalar: `SyntheticPerson` (kayıtlardaki kurgusal kişiler), `document_page` + `passport_page` (TD3), `driving_license_pages`, `residence_card_pages` (isteğe bağlı TD1), `work_permit_page`, `unknown_document_page`, `profile_picture_page`, `blank_page`; her sayfa görünür metni ve §8.4 kayıtlı yanıtını aynı değerlerden taşır (bulanık alan leke + `legible: false`), `make_document_pdf_bytes`/`make_page_image_bytes` belirleyici PDF/JPEG/PNG, `batch_analyses`/`write_recordings`/`recorded_provider` çağrı sırasıyla kayıtlı yanıt; depodaki 8 kayıt dizininin hepsi üreteçle birebir yeniden üretilir, test ağacında belge dosyası yok — test `tests/fixtures/test_gen.py` (68) · tm 60
- ✅ Üretilen parti `process_upload`'dan geçer: pasaport + boş sayfa Hazir'a extract ile, çok dosyalı partide boş/tek görüntü tespiti ve istek sırası (`page_index` 0, 2, 3, 4, 5, 0) üreteçle tutar — test `tests/pipeline/test_synthetic_documents.py` (2) · tm 60
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2254 geçti, +70; 4 PG testi atlandı), kapsam %99.74, temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0 · tm 60

#### K09.3-b — 09.3.2 · Kabul senaryoları S1–S5
- ✅ S1, S2, S5 PRD beklentisiyle birebir: partiler gerçek yükleme uç noktasıyla (`POST /api/uploads`) açılır, `process_upload`'dan geçer, dosyalar ve kayıtlı yanıtlar `gen.py`'den. S1: kayıtlı çalışanın (numarası `employee_identifiers`'ta) pasaportu `passthrough` ile `Hazir/Test_Ornekova-Passport.pdf` (yüklenen baytların kendisi), `Alinan/` kopyası, olay zinciri `FILE_UPLOADED → PAGE_RENDERED → PAGE_ANALYZED → DOC_TYPE_DETERMINED → PERSON_MATCHED → PLAN_CREATED → OUTPUT_SAVED` (kişisel değer yok). S2: aynı dosya `FILE_DUPLICATE`, sağlayıcı hiç çağrılmaz, sayfa/çıktı/Alinan kopyası yok, tek `skip` öğesi. S5: `on.jpg` + `arka.jpg` tek `Driving-License.pdf` (`merge`), sayfalarda yüklenen JPEG'lerin baytları olduğu gibi — test `tests/test_scenarios_s01_s05.py` · tm 61
- ◐ S3/S4: oturma izni sayfa 4-5 (S3/S4) ve ehliyet 1-2 (S4) `extract` ile içerik akışları bayt bayt kaynakla aynı; S3 ehliyet 1 ve 6 ayrı Unresolved (R6), sayfa 3 çalışma izni Hazir'a / katalog dışı tür Unknown'a (iki parametre). **Eksik:** fotoğraf sayfası (S3 sayfa 2, S4 sayfa 3) kişi taşımadığı için §20.2.2 satır 8 gereği Unresolved'a gider — `Profile-Picture.jpeg` otomatik üretilmez (§D12, insan kararı bekliyor). PRD beklentisi `strict` xfail testi olarak duruyor (D12 uygulanınca XPASS testi kırar); İK atamasıyla (08.2) çıktı sayfa 2'nin gömülü görüntüsünden kayıpsız (`extract_image`) üretildiği ayrıca doğrulandı — test `tests/test_scenarios_s01_s05.py` · tm 61
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2261 geçti, +7; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.74, temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0 · tm 61
- ◐ Çelişki denetimi (2026-09-19, panel bulgusu PLAN.md:216 ↔ kapanmış tm 61): kabul kriteri (PRD 09.3.2: S1–S5 otomatik test olarak var ve geçer) koda karşı yeniden koşuldu — `tests/test_scenarios_s01_s05.py` 7 geçti, 2 strict xfail. Yeşil: S1 (`:272`), S2 (`:344`), S3 fotoğraf dışı (`:479`), S4 fotoğraf dışı (`:552`), İK atamasıyla fotoğrafın kayıpsız çıktısı (`:608`), S5 (`:636`). **Eksik (değişmedi):** S3 "Profile-Picture.jpeg (2)" ve S4 "üç bağımsız çıktı" — fotoğraf §20.2.2 satır 8 ile Unresolved'a gidiyor (`:536`, `:584`), PRD beklentisi `:589`'da `xfail(strict=True)` (D12); sahip kuralı `app/pipeline/plan.py` `_decide_employee`'de yok. tm 60 üreteci eksiksiz; eksik planlayıcıda. Kalan iş → tm 95 (critical) · tm 61
- ✅ S3/S4 fotoğrafı (§D29; D12 kapandı): kişi taşımayan türün satır 8 adayı sahibini aynı dosyanın tek kayıtlı çalışanından ikinci geçişte alır, öğe kimlikleri değişmez. S3 sayfa 2 ve S4 sayfa 3 kayıtlı çalışanın `Hazir/Ivan_Sidorov-Profile-Picture.jpeg`'i (`match`, `matched_by: null`), baytları vesikalığın kendisi (`extract_image`, K12); S3'ün iki parametresinde sonuç aynı; S4 üç çıktı, kuyruk boş. Kayıtlı çalışan yoksa fotoğraf Unresolved kalır ve İK atamasıyla aynı çıktı üretilir. Strict xfail kaldırıldı (9 geçti, 0 xfail); planlayıcı birim testleri kuralın pozitif/negatif durumlarını (iki çalışan, kuyruktaki başka/doğrulanmamış kişi, Hazir'a giden kimlik yok, başka dosya + bağlam çalışanı, yalnız satır 6, kişi alanlı tür, belge düzeyi ret, kişi okunan fotoğraf) sınar; S18 kuyruk öğesini katalog dışı belgeyle sınar — `app/pipeline/plan.py` · test `tests/test_scenarios_s01_s05.py` (9), `tests/pipeline/test_plan.py` (+13), `tests/test_scenarios_s11_s18.py` · tm 95
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2833 geçti, +15; xfail 2 → 0; 4 PG testi atlandı), kapsam %99.80 (`plan.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 9 geçici bozmanın (koşul 1 kişisiz tür, koşul 2 satır 8, aynı dosya, tek çalışan, en az biri Hazir, yalnız satır 1/3, kuyruktaki kişi, belge düzeyi kabul, ikinci geçiş) her biri testte kırmızı · tm 95

#### K09.3-c — 09.3.3 · Kabul senaryoları S6–S10
- ✅ S6–S10 PRD §9 beklentisiyle birebir, S1–S5 ile aynı gerçek yoldan (yükleme uç noktası → `process_upload`; dosya ve kayıtlı yanıtlar `gen.py`'den). S6: katalogda pasaport `expected_file_types: [pdf]` yapılır, JPEG pasaport Unresolved'a (`Direkt Belge: beklenen dosya türü pdf, gelen jpeg. Uygun formatta yeniden gönderin.`), JPEG kuyrukta bayt bayt, veri dizininde PDF/çıktı/sarma yok. S7: 4 sayfalık PDF'in 2. sayfası `extract` ile tek sayfalık `Passport.pdf` — içerik akışı bayt bayt kaynak, metin katmanı ve MRZ duruyor, görüntü yok, `IMAGE_RENDERED` yok. S8: boş sayfa (kartın yüzleri arasında / iki belge arasında) analize gitmez, tek `skip` öğesi, hiçbir çıktıya girmez, parti `done`, hata ve kuyruk yok. S9: bulanık numara + MRZ → Unreadable, gerekçe `Okunamayan alanlar: document_number` ile başlar; çalışan açılmaz/önerilmez. S10: yalnız isim eşleşmesi (doğum tarihi yok / farklı, numara temiz) → Unresolved (satır 5, R8), `match` ve yeni çalışan yok, kayıtlı çalışana numara/yazım eklenmez — test `tests/test_scenarios_s06_s10.py` (9) · tm 62
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2270 geçti, +9; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.78, temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0 · tm 62

#### K09.3-d — 09.3.4 · Kabul senaryoları S11–S15 ve S18
- ✅ S11–S15 ve S18 PRD §9 beklentisiyle, S1–S10 ile aynı gerçek yoldan (yükleme uç noktası → `process_upload`; dosya ve kayıtlı yanıtlar `gen.py`'den; yeniden analiz/çalıştırma parti uç noktalarından). S11: temiz pasaport numarası, eşleşen kayıt yok (boş veritabanı / başka kayıtlı çalışan) → satır 6 `create`, yeni E numarası, K8 klasörü, `profil.md` (kimlik, numara, belge satırı), belge `Hazir`'da passthrough, `Alinan`'da kopya. S12: aynı isimli iki çalışandan doğum tarihi uyan eşleşir (iki yönde, numara ona eklenir); ikisine uyarsa `name_dob_ambiguous`, hiçbirine uymazsa `name_only` → Unresolved, yeni çalışan yok. S13: Kiril isimli pasaport → `Iulia_Testova_Shchelkina_E0001` / `Iulia_Testova_Shchelkina-Passport.pdf` (ASCII), profilde Latin ad ve `Тестова-Щёлкина Юлья` birlikte. S14: Peru diploması Unknown + aday tür (`pending`, örnek sayfa, `CANDIDATE_TYPE_PROPOSED`); tür kataloğa eklenip (C44) yeniden analiz edilince plan v2'de ad + doğum tarihiyle kayıtlı çalışanın `Hazir/Ana_Prueba-Diploma.pdf`'i, eski plan ve Unknown kopyası yerinde (K18), aday yeniden sayılmaz. S15: Word CV (docx / eski doc) bağlam çalışanıyla `Hazir/Ivan_Sidorov-Attachment.<uzantı>` bayt bayt, analiz/render yok; genel yüklemede Unresolved, dönüştürülmeden kuyrukta. S18: hazir + kuyruk + skip öğeli parti `rerun` uç noktasıyla iki kez yeniden çalıştırılır — sağlayıcı çağrılmaz, aynı plan/çıktı/kuyruk satırları, veri dizini bayt bayt aynı, `-2` yok, olaylar yalnız `PLAN_RERUN` + 3 `OUTPUT_SKIPPED`. 7 kural bozulması (profil yazılmaması, belirsiz isim+doğum tarihinin eşleşme sayılması, yalnız ismin yeni çalışana inmesi, idempotenliğin kalkması, eki bağlamın yok/hep sayılması, yeniden analizin tohum kataloğuyla yapılması) geçici olarak denendi, her biri testte kırmızı — test `tests/test_scenarios_s11_s18.py` (13) · tm 63
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2283 geçti, +13; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.74, temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0 · tm 63

#### K10.1 — 10.1.1, 10.1.2, 10.1.3 · Panel iskeleti ve giriş
- ✅ 10.1.1 panel iskeleti: `app/web/templates/base.html` (üst çubuk: menü + kullanıcı adı + çıkış; girişsiz sayfada menü çizilmez), menü tek yerde `PANEL_MENU` (`app/web/templating.py`, Jinja2 otomatik kaçış, paketle yüklenen şablonlar), sayfalar `app/web/routers/panel.py` (`/upload`, `/employees`, `/queues`, `/document-types`, `/uploads`; `/` → Yükle; içerik gelene kadar `section.html`), tek stil dosyası `app/web/static/panel.css` — beş menü girişten sonra 200 açılır, bulunulan bölüm işaretli · test `tests/web/test_auth.py` · tm 64
- ✅ 10.1.2 oturum tabanlı giriş: `app/web/auth.py` (argon2id parola, `user_sessions`'ta belirtecin SHA-256 özeti, süre/çıkış ile kapanma; `get_current_user` → `require_panel_user` 303 girişe / `require_api_user` 401), `app/web/routers/auth.py` (`GET/POST /login`, `POST /logout`; `next` yalnız yerel yol), göç `alembic/versions/0003_user_sessions.py`, `SESSION_MAX_AGE_SECONDS` (`app/config.py`); `app/main.py` panel ve `/api/*` yönlendiricilerini oturuma bağlar, `/docs`/`/openapi.json` kapalı — uygulamanın bütün yolları (`app.openapi()`) oturumsuz denenir: açık yalnız giriş/çıkış ve `/health`, sayfalar girişe, API 401 · test `tests/web/test_auth.py` (46), `tests/db/test_migrations.py` (+1), `tests/test_config.py` (+1) · tm 64
- ✅ 10.1.3 ilk yönetici: `python -m app.web create-admin --username AD [--password-stdin]` (`app/web/__main__.py`; parola gizli iki kez ya da standart girdiden, argüman değil; kısa parola/boşluklu ya da alınmış ad çıkış 1, hiçbir şey yazılmaz) — ayrı süreçte göçlü temiz veritabanında açılan yönetici panele girip beş menüyü açar · test `tests/web/test_admin_cli.py` (8) · tm 64
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2339 geçti, +56; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.73, temiz SQLite'ta `alembic upgrade head` (0001→0003), `import app.main` — hepsi exit 0; 6 geçici kural bozulmasının (API korumasız, panel korumasız, açık yönlendirme, kapalı ya da süresi dolmuş oturum geçerli, üretimde Secure yok) her biri testte kırmızı. Mevcut API test fikstürleri (`tests/web/conftest.py`, `tests/test_scenarios_s01_s05.py`) oturumu açık kullanıcıyla gelir. · tm 64

#### K10.2 — 10.2.1, 10.2.2 · Yükleme sayfası ve ilerleme görünümü
- ✅ 10.2.1 yükleme sayfası: `app/web/routers/upload_page.py` (`GET /upload` form + çalışan listesi, `POST /upload` HTMX gönderimi — `create_upload`'ı çağırır, sınır/Inbox/tekrar mantığı tek yerde), `app/web/templates/upload.html` + `upload_result.html`, `app/web/static/upload.js` (sürükle-bırak; art arda bırakılanlar birikir, aynı ad+boyut tekrarlanmaz, seçilenler listelenir), `app/web/static/htmx.min.js` (HTMX 2.0.4), isteğe bağlı çalışan → `uploads.context_employee_id` · test `tests/web/test_upload_page.py` (31) · tm 65
- ✅ 10.2.2 ilerleme görünümü: `GET /upload/{id}/progress` parçası `hx-trigger="every 2s"` ile yenilenir, son durumda (`done`/`partial`/`failed`) durur; parti `POST /upload` sonrası `process_upload` ile arka planda `received → … → done` ilerler (`get_upload_processor`) — gerçek tarayıcıda (Chromium, CDP) iki dosyayı sürükleyip bırakma → gönderim → "Alındı → Tamamlandı" doğrulandı · test `tests/web/test_upload_page.py` (kayıtlı sağlayıcıyla uçtan uca) · tm 65
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2370 geçti, +31; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.74 (`upload_page.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0; 6 geçici kural bozulmasının (boş çalışan dizesi, son durumda yenileme, arka plan işleyicisi, boş adlı parça, `failed` aşama şeridi, başkasının aldığı parti) her biri testte kırmızı

#### K10.3 — 10.3.1, 10.3.2 · Yükleme detay sayfası ve yeniden çalıştır / yeniden analiz
- ✅ 10.3.1 yükleme detay sayfası: `app/web/routers/upload_page.py` (`GET /uploads/{id}` → `build_detail_view`; `GET /uploads/{id}/pages/{page_id}/image` analiz kopyasını sunar, başka partinin/yolu kaçan/eksik görüntü 404) + `app/web/templates/upload_detail.html` — sayfa küçük resimleri (durum, "Boş", sayfayı alan plan öğesi), güncel planın öğeleri (tür, kaynak, işlem, hedef, çalışan, rota + gerekçe, doğrulamalar), çıktılar (tüm sürümlerin belgeleri "Etkin"/"Eski sürüm" + kuyruğa alınanlar) ve olay zaman çizelgesi tek sayfada; bozuk plan sayfayı düşürmez · test `tests/web/test_upload_detail.py` (35, hepsi bu dosyada) · tm 66
- ✅ 10.3.2 yeniden çalıştır / yeniden analiz: `POST /uploads/{id}/rerun` (`rerun_plan`, yapay zekâ yok) ve `POST /uploads/{id}/reanalyze/prepare` + `POST /uploads/{id}/reanalyze` (`reanalyze_upload`) — birinci onay `<details>` içinde, hazırlık isteği ikinci onay formunu ve belirteci verir, belirteçsiz/süresi geçmiş/başka partiye ya da oturuma ait/kullanılmış belirteç 400 ve hiçbir şey yapılmaz; onay `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki zaman) yazar; yalnız son durumdaki ve planı olan partide (409), sağlayıcı kurulamazsa 503, hata olursa rollback (onay olayı dahil) — D23 · test `tests/web/test_upload_detail.py` · tm 66
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2405 geçti, +35; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.75 (`upload_page.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 6 geçici kural bozulmasının (belirteç doğrulaması atlandı, belirteç plana bağlı değil, süresiz belirteç, süren partiye işlem, başka partinin sayfa görüntüsü, onay olayı yok) her biri testte kırmızı; gerçek Chrome'da (CDP) detay sayfası → küçük resim yüklenir → yeniden çalıştır → birinci onay → ikinci onay metni birebir → bayat belirteçle 400 hata parçası sayfada görünür → temiz akışta yeni plan sürümü ve "Eski sürüm" çıktı elle doğrulandı

#### K10.4 — 10.4.1, 10.4.2 · Çalışan listesi ve arama
- ✅ 10.4.1 çalışan listesi: `app/web/routers/employees.py` (`GET /employees` → `list_employees`; No, Ad, Orijinal yazım, Uyruk, Belge sayısı (yalnız etkin belge), Durum; soyad/ad sırası, 25'lik sayfalar, boş dizin ve eşleşmeme iletileri) + `app/web/templates/employees.html` / `employees_results.html`; `panel.py`'deki yer tutucu kaldırıldı, `app/main.py` yönlendiriciyi oturuma bağlar, `panel.css` tablo/arama/sayfalama stili · test `tests/web/test_employees.py` (60) · tm 67
- ✅ 10.4.2 arama: `q` terimlere bölünür (terimler VE, alanlar VEYA; en çok 6 terim, 100 karakter) ve ad/diğer isimler, alias (ham + `normalize_name` anahtarı: harf büyüklüğü, aksan, Kiril↔Latin), orijinal yazım, belge numarası (`normalize_document_number` ile ayırıcı farkı yok) ve belge türü (ad/dosya etiketi/slug, etkin belge; `İkamet` Python katlamasıyla) üzerinde çalışır; `%`/`_` LIKE kaçışlı; HTMX parçası (`HX-Request`, `Vary`, geçmiş geri yüklemesi tam sayfa) — gerçek Chrome'da (CDP) yazarak arama, adres güncelleme, tam yenileme olmadan sonuç, eşleşmeyen ileti, temizleme ve geri tuşu doğrulandı · test `tests/web/test_employees.py` · tm 67
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2465 geçti, +60; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.75 (`employees.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 12 geçici kural bozulmasının (belge sayısı eski/arşiv dahil, tür araması eski sürüm dahil, alias anahtarı yok, LIKE kaçışı yok, terimler VEYA, numara normalize yok, `Vary` yok, geçmiş geri yüklemesi parça alır, sayfa kelepçesi yok, harf duyarlı sıra, tür katlaması yok, terim sınırı yok) her biri testte kırmızı · tm 67

#### K10.5 — 10.5.1, 10.5.4, 10.5.2, 10.5.3 · Çalışan profili sayfası
- ✅ 10.5.1 çalışan profili kartı: `app/web/routers/employees.py` (`GET /employees/{id}` → `build_profile`; fotoğraf, ad, soyad, diğer isimler, orijinal yazım, vatandaşlık, doğum tarihi + yaş (`calculate_age`), Telefon/E-posta/Adres (yalnız güncel), belge numaraları (etiket katalog tür adı); boş alan "—", gizlenmez; bilinmeyen çalışan 404 sayfası) + `app/web/templates/profile.html`; `employees_results.html` No ve Ad'ı profile bağlar, `panel.css` kart/belge/yükleme stili — C49 · test `tests/web/test_profile.py` (26, hepsi bu dosyada) · tm 68
- ✅ 10.5.4 profil fotoğrafı yokluğu: kart en yeni **etkin** `profile_picture` belgesini `GET /employees/{id}/photo` ile gösterir (bayt bayt dosya); etkin kayıt yoksa (yalnız eski sürüm/arşiv dahil) yer tutucu + "Eksik belge · Profile Picture" rozeti, kayıt var ama dosya yok/görüntü değilse yer tutucu ve rozetsiz, kırık `<img>` yok; `/photo` 404 · test `tests/web/test_profile.py` · tm 68
- ✅ 10.5.2 belge listesi ve açma: çalışanın tüm belgeleri (etkin/eski sürüm/arşivlendi; tür, dosya, biçim, durum, tarih), dosya adı `target="_blank" rel="noopener"` ile yeni sekmede açar (`.../documents/{id}/file`, satır içi), ayrı "İndir" (`.../download`, ek, dosya adıyla); Word/Excel her koşulda indirme; ortam türü uzantı tablosundan, `nosniff` + `Cache-Control: private, no-store`, içerik bayt bayt; başka çalışanın belgesi / kaydı olmayan / dosyası olmayan / yolu veri dizininden kaçan belge 404; düzenleme yolu yok — dört profil yolu yalnız `GET` (POST/PUT/PATCH/DELETE 405, OpenAPI şeması doğrular) · test `tests/web/test_profile.py` · tm 68
- ✅ 10.5.3 profil sayfasından yükleme: profil sayfası `/upload` formunu gizli `context_employee_id` (çalışan seçici yok) ile taşır, `POST /upload`'a gider; sayfanın verdiği alanla yapılan yükleme partiyi o çalışanın bağlamıyla açar, ilerleme aynı sayfada — C49 · test `tests/web/test_profile.py` · tm 68
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2491 geçti, +26; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.76 (`employees.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 7 geçici kural bozulmasının (sahip denetimi yok, fotoğraf durum süzgeci yok, eski iletişim bilgisi görünür, açma "ek" olarak iner, yaş yanlış gün, `no-store` yok, `/photo` görüntü olmayanı da sunar) her biri testte kırmızı; headless Chrome'da (statik çizim) kart + fotoğraf + belge tablosu + yükleme formu ve yer tutucu/"Eksik belge"/"—" görünümü elle görüldü · tm 68

#### K10.6 — 10.6.1 · Belge geçmişi görünümü
- ✅ 10.6.1 belge geçmişi: `app/web/routers/documents.py` (`GET /documents/{id}/history` → `build_history`; çıktı (çalışan, tür, dosya + açma, durum, plan sürümü), kaynak dosyalar ve sayfalar (`source_refs_json`: dosya adı → `/uploads/{id}#file-N`, her sayfa → sayfa görüntüsü; boş sayfa listesi = bütün dosya; sıra köken kaydındaki gibi; eksik/bozuk kayıt bağlantısız notla yazılır), parti ve plan öğesi bağlantısı, belgenin kendi olayları; bilinmeyen belge 404; yalnız `GET`) + `app/web/templates/history.html`; `app/main.py` yönlendiriciyi oturuma bağlar, profil belge listesi ve yükleme detayı çıktı tablosu "Geçmiş" bağlantısı taşır — C50 · test `tests/web/test_documents.py` (29) · tm 69
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2520 geçti, +29; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.76 (`documents.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 9 geçici kural bozulmasının (alınmayan sayfalar da izde, bütün dosya boş liste, dosya bölümü çapası yok, olaylar süzülmemiş, görüntüsüz sayfa bağlantılı, sayfa bağlantısı yanlış partiye, `bool` dosya kimliği kabul, kaynak sırası ters, kayıp çıktıya açma bağlantısı) her biri testte kırmızı · tm 69

#### K10.7-a — 10.7.1 · Kuyruk ekranları ve öğe detayı
- ✅ 10.7.1 kuyruk ekranları: `app/web/routers/queue.py` (`pages_router`: `GET /queues?tab=&state=&page=` → `list_queue`; üç kuyruk sekmesi (Unknown/Unreadable/Unresolved) + bekleyen sayaçları, durum bağlantıları (bekleyen/çözülen/eski sürüm) sayılarıyla, 25'lik sayfalar; `GET /queues/{id}` → `build_item_view`: gerekçe, tür, kişi tahmini, kaynak dosyalar + sayfa görüntüleri, çözüm bilgisi + çıktının geçmişi, öğenin olayları; bozuk `payload_json` düşmez, bilinmeyen öğe 404) + `app/web/templates/queue.html` / `queue_item.html`; `panel.py`'deki yer tutucu kalktı, `app/main.py` yönlendiriciyi oturuma bağlar, `panel.css` sekme/sayaç stili — C51 · test `tests/web/test_queue_page.py` (22) · tm 70
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2542 geçti, +22; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.77 (`queue.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 8 geçici kural bozulmasının (bekleyen güncel plana bakmıyor, çözülen süzgeci ters, plansız öğe eski sürüm sayılmıyor, sayfa sınırı yok, olaylar öğeye süzülmemiş, bekleyen sırası ters, sayaç seçili durumdan okunuyor, güncel plan yönü ters) her biri testte kırmızı. Tarayıcıda çizim görülmedi (yalnız `TestClient`) · tm 70

#### K10.7-b — 10.7.2 · Kuyruktan çalışana atama
- ✅ 10.7.2 kuyruktan çalışana atama: `app/web/routers/queue.py` (`assignment_search` → 10.4.2'nin `list_employees` araması, `assignment_first_confirmation`, `prepare_assignment` → `issue_confirmation(assignment_subject(...))`, `assign_from_queue` → `check_confirmation` + `USER_CONFIRMED` + `assign_queue_item`/`MANUAL_ASSIGN` tek işlemde) + `app/web/templates/queue_assign.html` (arama sonucu / birinci onay / ikinci onay / sonuç; §20.6 metinleri birebir) + `queue_item.html` `#assign` bölümü (bekleyen ve türü belli öğede) · C52, D24 · test `tests/web/test_queue_assign.py` (27) + `tests/web/test_queue_page.py` yol listesi · tm 71
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2569 geçti, +27; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.77 (`queue.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 6 geçici kural bozulmasının (belirteç denetlenmiyor, birinci metin değişik, belirteç çalışana bağlı değil, türsüz öğe reddedilmiyor, `USER_CONFIRMED` yazılmıyor, eski sürüm reddedilmiyor) her biri testte kırmızı · tm 71

#### K10.7-c — 10.7.3 · Kuyruktan profil oluşturma
- ✅ 10.7.3 kuyruktan profil oluşturma: `app/web/routers/queue.py` (`profile_first_confirmation`, `prepare_profile`, `create_profile_from_queue`; `profile_form`, `profile_subject`, `_profile_section`) + `app/web/templates/queue_new_profile.html` (öğe detayında `#new-profile` düzenleme formu ve iki onay adımı), çekirdek `app/matching/match.py` (`ProfileFields`, `check_profile_fields`, `edited_profile_fields`, `review_pending_profile`, `approve_pending_profile(fields=)`) ve `app/pipeline/route.py` (`review_queued_profile`, `approve_queued_profile(fields=)`) — önerilen profil düzenlenip iki aşamalı onayla (§20.6 metinleri birebir) çalışan olarak açılır; belge içeriği formda yok ve değişmez (çıktı kaynağın baytları, analiz ve plan aynı, fazla form alanı yok sayılır); düzeltilen kimlik kayıtlı çalışana uyarsa onay reddedilir (PLAN.md §C53, §D25) · test `tests/web/test_queue_new_profile.py` (29), `tests/matching/test_profile_edit.py` (21), `tests/pipeline/test_route_approve.py` (+4) · tm 72
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2623 geçti, +54; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.78 (`queue.py`, `match.py`, `route.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 7 geçici kural bozulmasının her biri testte kırmızı · tm 72

#### K10.8 — 10.8.1, 10.8.2 · İki aşamalı onay ve manuel taşıma
- ✅ 10.8.1 iki aşamalı onay mekanizması: `app/web/confirm.py` (§20.6 metinleri birebir `CONFIRMATION_TEXTS` + `fill`; tek kullanımlık belirteç `issue_confirmation` / `consume_confirmation` / `confirm_operation` → `USER_CONFIRMED`), model `ConfirmationToken` (`app/db/models.py`) + göç `alembic/versions/0004_confirmation_tokens.py`; yeniden analiz (`upload_page.py`), kuyruk ataması ve profil onayı (`queue.py` panel akışları) ve API `POST /api/queue/{id}/assign`, `POST /api/queue/documents/{id}/archive` (hazırlık `.../prepare` + `X-Confirmation-Token`; `get_confirmed_actor` 503 kaldırıldı) bu belirtece bağlandı — test `tests/web/test_confirm.py` (14: PRD tablosuyla birebir karşılaştırma, yalnız özet saklanır, bir kez tüketilir, geri alınan işlem tüketmez, belirteçsiz/tanınmayan/süresi geçmiş/başka oturum-kullanıcı-işlem-hedef reddi, `USER_CONFIRMED` verisi), `tests/web/test_queue.py` (21), `tests/web/test_queue_assign.py` (27), `tests/web/test_queue_new_profile.py` (29), `tests/web/test_upload_detail.py` (35), `tests/db/test_migrations.py` (8: 0004 geri alınabilir) · tm 73
- ✅ 10.8.2 belgeyi başka çalışana taşıma: çekirdek `app/storage/move.py` (`move_document`: yalnız etkin belge, yeni sahibin K8 adı + sıra eki, bayt bayt aynı içerik, eski dosya silinir, kaynak orijinal yeni sahibin `Alinan/`'ına, `MANUAL_MOVE` kullanıcı adıyla) + panel `app/web/routers/documents.py` (arama → birinci onay → hazırlık → taşıma; commit'ten sonra iki `profil.md`) + `app/web/templates/document_move.html`, `history.html` `#move` — test `tests/storage/test_move.py` (21), `tests/web/test_document_move.py` (23: S16 tek onayla değişiklik yok / iki onayla taşınır, iki profil — `profil.md` ve profil sayfası — güncellenir, `USER_CONFIRMED` + `MANUAL_MOVE` kullanıcı adı ve iki zamanla; belirteç kuralları; taşınamayan belge, bilinmeyen kayıt) · tm 73
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2691 geçti, +68; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.79 (`confirm.py`, `move.py`, `documents.py`, `queue.py`, `upload_page.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004), `import app.main` — hepsi exit 0; 12 geçici kural bozulmasının (tek kullanımlık değil, oturuma/hedefe bağlı değil, süre denetimi yok, metin birebir değil, taşımada belirteç denetimi yok, eski dosya silinmiyor, profiller güncellenmiyor, Alinan kopyası yok, etkin olmayan belge taşınıyor, API arşivi belirteçsiz, hazırlık belirteci saklamıyor) her biri testte kırmızı · tm 73

#### K10.9 — 10.9.1, 10.9.2 · İçerik düzenleme yokluğu ve erişim logu
- ✅ 10.9.1 panelde belge içeriği düzenleyen yol yok: bütün değiştirici yollar gözden geçirilmiş listede (`REVIEWED_MUTATING_ROUTES`), PUT/PATCH/DELETE yok, belge yollarından yalnız taşıma/arşiv değiştirir, şablonlarda düzenleme arayüzü yok, `file`/`download`/`photo`/geçmiş yolları her yazma yöntemine 405 verir ve dosya baytları değişmez — `tests/web/test_access_log.py` (10.9.1 bölümü, 9 test) · tm 74
- ✅ 10.9.2 her açma ve indirme kullanıcı ve zamanla kaydedilir: `app/web/access.py` `record_access` + `app/db/models.py` `AccessAction`/`AccessChannel`; `app/web/routers/employees.py` `_employee_document` satırı sunmadan önce yazar ve commit eder (log düşerse 500, belge gitmez), 404'te log yok, eski/arşiv belge de loglanır, fotoğraf/geçmiş/sayfa görüntüsü loglanmaz (D27) — test `tests/web/test_access_log.py` (10.9.2 bölümü, 12 test) · tm 74
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2712 geçti, +21; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.79 (`access.py`, `employees.py`, `documents.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 5 geçici kural bozulmasının (indirme `view` yazılıyor, log hiç yazılmıyor, kullanıcı sabit, PUT yolu, `contenteditable`) her biri testte kırmızı · tm 74

#### K11.1 — 11.1.1, 11.1.2, 11.1.3 · Katalog yönetim ekranı
- ✅ 11.1.1 tür oluşturma, düzenleme ve pasifleştirme panelden yapılır: `app/web/routers/catalog.py` (liste `GET /document-types`, `new`, `{slug}`, `deactivate`/`activate`) + `app/catalog/manage.py` (`create_type`, `update_type`, `set_type_active`, `list_types`, `load_record`) + şablonlar `catalog.html`, `catalog_form.html`; silme yolu yok (K16), slug düzenlemede adresten gelir ve değişmez, `active`/`photo_rules` formdan değişmez, pasif tür listede kalır ama analiz talimatına girmez, tutarsız kayıtlı tür rozetle listelenir ve formdan düzeltilir — test `tests/web/test_catalog_page.py` (39), `tests/catalog/test_manage.py` (12) · C56 · tm 75
- ✅ 11.1.2 katalog form doğrulaması: `app/catalog/form.py` `build_entry`/`TypeFormError` — Direkt türde dönüşüm listesi boş (şema kuralı), `front_back` türde sayfa aralığı tam 2–2 (yalnız form kuralı, D28), `analyze: false` türde zorunlu alan boş; alan adı, slug, ülke, dosya türü, seçim, sayfa sayısı hataları Türkçe ve alan başına, hepsi birlikte; reddedilen form 422 ile girilen değerlerle çizilir, hiçbir şey yazılmaz; `app/catalog/schema.py` `CatalogEntry.consistency_problems` alanlar arası ihlalleri `(alan, mesaj)` olarak taşır (mesajlar aynı) — test `tests/catalog/test_form.py` (55), `tests/web/test_catalog_page.py` · C56, D28 · tm 75
- ✅ 11.1.3 kabul kriteri düzenleme: `app/web/templates/catalog_criteria.html` + `POST /document-types/criteria/add|remove` (HTMX, yalnız madde listesi parçası, kaydetmez), kayıtta boş madde atılır ve sıra korunur; değişiklik bir sonraki analizde geçerli — panelden çıkarılan madde bir sonraki `process_upload` talimatında yok, eklenen var (kayıt her analizin başında `export_catalog` ile okunur) — test `tests/web/test_catalog_page.py` (`test_an_edit_reaches_the_next_analysis_and_only_that_one`) · C56 · tm 75
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2818 geçti, +106; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.80 (`form.py`, `manage.py`, `routers/catalog.py`, `schema.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; ilk turda `front_back` kuralı şemaya konmuştu ve `tests/pipeline/test_plan.py::test_front_back_card_without_its_back_goes_to_unresolved_and_opens_nobody[sides-only]`'yi kırdı, kural forma taşınıp tam suite yeniden koşuldu (D28); 10.9.1 kilidi (`tests/web/test_access_log.py`) yeni yolları ve şablonları gözden geçirilmiş listeyle eşler; headless Chrome'da madde ekleme/çıkarma, kaydetme, pasifleştirme ve Direkt + dönüşüm reddi elle doğrulandı (betik depoya girmedi)

#### K11.2 — 11.2.1 · Örnek belge yükleme
- ✅ 11.2.1 türe örnek yüklenir, çalışan verisinden ayrı tutulur ve aramada görünmez: `app/storage/examples.py` (`check_example`, `store_example`, `list_examples`, `example_path`; PDF/JPEG/PNG içerik imzasıyla, boş/boyut aşan/bozuk reddedilir, ad sadeleşir ve `-2` eki alır, aynı SHA-256 bir kez, baytlar değişmez) + `app/web/routers/catalog.py` (`POST /document-types/{slug}/examples` hep-ya-hiç, `GET .../examples/{ad}`; düzenleme sayfasında liste ve yükleme formu) + şablon `catalog_examples.html`; örnek yalnız `KnownDocuments/examples/<slug>/` altında dosyadır — `uploads`/`upload_files`/`documents`/`events` satırı açılmaz, Inbox/Employees'a dosya girmez, çalışan araması ile yükleme/kuyruk listelerinde görünmez, örnekle aynı baytlı gerçek yükleme "tekrar" sayılmaz — test `tests/storage/test_examples.py` (23), `tests/web/test_catalog_examples.py` (18) · C61, D33 · tm 76
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3012 geçti, +41; 4 PG testi atlandı), kapsam %99.82 (`examples.py` %100, `routers/catalog.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 10.9.1 kilidine (`tests/web/test_access_log.py`) bir yeni POST yolu eklendi · tm 76

#### K11.3 — 11.3.1 · Tür açıklaması üretimi
- ✅ 11.3.1 örneklerden yapılandırılmış tür açıklaması üretilir ve düzenlenebilir: sözleşme `app/ai/type_description.py` (`TypeDescription`: düzen, başlıklar, dil, alfabe, alanların yeri, MRZ, ön/arka yüz farkı; her anahtar zorunlu, tanımsız anahtar/tekrar/uzun metin reddedilir) + `app/ai/provider.py` `describe_type`/`TypeDescriptionRequest` (Anthropic ve OpenAI'de zorlanmış `record_type_description` aracı, birkaç görüntü tek istekte, yeniden deneme ortak; kayıtlı yanıt sağlayıcısı aynı sıradan dağıtır) + talimat `app/ai/prompts/type_description.md` + çekirdek `app/catalog/describe.py` (`collect_example_pages` en çok 8 sayfa bellekte — `app/pipeline/render.py` `render_pdf_images`/`image_copy`; `describe_type`; `format_description` → `prompt_description` metni) + panel `POST /document-types/{slug}/description` (form doğrulanır, üretilen metin "Analizci için açıklama" alanına yazılır ve yapılandırılmış hâli gösterilir, hiçbir şey kaydedilmez; İK düzenleyip Kaydet'le kaydeder, kayıt bir sonraki analizin talimatına girer) — test `tests/ai/test_type_description.py` (55), `tests/catalog/test_describe.py` (23), `tests/web/test_catalog_description.py` (18), `tests/ai/test_anthropic_provider.py` (+5), `tests/ai/test_openai_provider.py` (+6), `tests/pipeline/test_render.py` (+11) · C62, D34 · tm 77
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3130 geçti, +118; 4 PG testi atlandı; suite iki ön plan koşusuna bölündü — `tests/web` ve geri kalanı, kapsam `--cov-append` ile birleşti), kapsam %99.85 (`type_description.py`, `describe.py`, `provider.py`, `anthropic_provider.py`, `openai_provider.py`, `recording_provider.py`, `render.py`, `routers/catalog.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 10 geçici kural bozmasının her biri testte kırmızı; 10.9.1 kilidine (`tests/web/test_access_log.py`) bir yeni POST yolu eklendi · tm 77

#### K11.4 — 11.4.1, 11.4.2 · Prompt derleyici ve token bütçesi
- ✅ 11.4.1 aktif türler kompakt katalog metnine derlenir: `app/catalog/prompt_builder.py` `compile_catalog` → `CompiledCatalog` (yalnız etkin + `analyze: true` türler, slug sırasıyla; başlık + ülke/yüz/sayfa tek satırda + zorunlu alanlar + tanım + kabul kriterleri; yüz değeri açıklaması ve yer tutucular tür başına tekrarlanmaz, karar motoru alanları girmez; tohum 3165 → 2693 bayt) + `app/ai/prompts/page_analysis.py` yuvayı derleyiciyle doldurur — test `tests/catalog/test_prompt_builder.py` (11.4.1 bölümü, 8), `tests/ai/test_prompts.py` (35, biçime uyarlandı) · C57 · tm 78
- ✅ 11.4.2 katalog metni sınırı aşarsa açıklamalar kısaltılır ve uyarı loglanır: `estimate_tokens` (UTF-8 bayt / 3), `CATALOG_TOKEN_BUDGET = 4000`; aşımda yalnız tanımlar ortak karakter sınırıyla kelime sınırında `…` ile kısalır (en uzun önce, sığan en büyük sınır ikili aramayla), kabul kriterleri/zorunlu alanlar/türler korunur, sığmazsa `over_budget`; `app.catalog.prompt_builder` `WARNING` logu ilk/son tahmin, bütçe ve kısaltılan slug'larla — test `tests/catalog/test_prompt_builder.py` (11.4.2 bölümü 11 + entegrasyon 1 — `process_upload`: tohum + 12 uzun tür bütçeyi aşar, sağlayıcıya giden talimat bütçe içinde ve bütün slug'larla, uyarı loglandı, parti `done`) · C57 · tm 78
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2853 geçti, +20; 4 PG testi atlandı), kapsam %99.80 (`prompt_builder.py`, `page_analysis.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 14 geçici kural bozulmasının (kısaltma yok, sınırda kısaltma, uyarı yok, bütün tanımları düşürme, kabul kriteri kısaltma, pasif tür girer, sırasız, yüz açıklaması tekrarı, `…` yok, kelime ortasında kesme, karakterle tahmin, sığmama uyarısı yok, bütçe denetimi yok, karar motoru alanı girer) her biri testte kırmızı

#### K11.5 — 11.5.1, 11.5.2, 11.5.3, 11.5.4 · Aday tür akışı ve onay
- ✅ 11.5.1 aday türler adı, görülme sayısı ve örnek sayfalarıyla listelenir: `app/catalog/candidates.py` `list_candidate_types` (yalnız `pending`, görülme sayısına göre, `sample_page_ids` sırasıyla örnek sayfa + parti/dosya/sıra) + `app/web/routers/catalog.py` `GET /document-types/candidate-types` ve `.../{id}` + şablonlar `catalog_candidates.html`, `catalog_candidate.html`, `catalog_candidate_samples.html` (analiz kopyası görüntüleri, bekleyen Unknown öğe sayısı, Belge Türleri'nden bağlantı ve bekleyen sayısı) — test `tests/catalog/test_candidates.py` (liste bölümü), `tests/web/test_candidate_types_page.py` (gerçek `process_upload` partileri; görüntü yolu 200 döner) · C58 · tm 79
- ✅ 11.5.2 onay sonrası tür katalogda, iki aşamalı onay istenir: tür formu adayla önceden dolu (`suggested_form`, ortak `catalog_type_fields.html`), `POST .../approve/confirm` (§20.6 birinci metni birebir) → `.../approve/prepare` (ikinci metin + kayda bağlı tek kullanımlık belirteç) → `.../approve` (`USER_CONFIRMED` + `create_type` + `app/db/models.py` `decide_candidate_type` + `TYPE_APPROVED` tek işlemde); yalnız birinci onayla, belirteçsiz, süresi geçmiş, başka işleme/kayda/adaya ait ya da tekrar kullanılan belirteçle hiçbir şey değişmez; geçersiz form 422, alınmış slug 409, karara bağlanmış aday 409 — test `tests/web/test_candidate_types_page.py` (onay bölümü), `tests/catalog/test_candidates.py` (onay bölümü: tür `export_catalog`'da ve derlenen analiz kataloğunda), `tests/db/test_candidate_types.py` (+5: bir kez karar, eksik aday, `pending` karar değil, 20 eşzamanlı karardan biri geçer), `tests/test_scenarios_s11_s18.py` (S14 onayı `approve_candidate_type` ile) · C58 · tm 79
- ✅ 11.5.3 aday ile ilişkili Unknown öğeleri toplu yeniden analiz edilebilir: onaylanmış adayın ilk kaynak sayfası örnek sayfalarından olan bekleyen Unknown öğelerinin partileri iki aşamalı onayla (`.../reanalyze/prepare` → `.../reanalyze`, belirteç parti + güncel plan kümesine bağlı) tek işlemde `reanalyze_upload` ile yeniden analiz edilir — test `tests/web/test_candidate_types_page.py` (iki parti v2'ye geçer, öğeler katalog türüyle Unknown dışına çıkar, ilgisiz parti dokunulmaz; onaysız adayda, belirteçsiz, küme değişince 400/409; ikinci partide uygulayıcı düşerse hiçbiri kalmaz; sağlayıcı yok 503; süren parti 409) · C58, D30 · tm 79
- ✅ 11.5.4 reddedilen aday tekrar listeye düşmez: `reject_candidate_type` (`rejected` + `TYPE_REJECTED`, kullanıcı adıyla) + `POST .../reject`; aynı ad yeni partide yeniden önerilince görülme sayılır, aday listeye dönmez, katalog ve kuyruk değişmez — test `tests/web/test_candidate_types_page.py` (ret bölümü), `tests/catalog/test_candidates.py` (ret bölümü) · C58, D30 · tm 79
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2904 geçti, +51; 4 PG testi atlandı), kapsam %99.81 (`candidates.py`, `routers/catalog.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 10.9.1 kilidine (`tests/web/test_access_log.py`) altı yeni POST yolu eklendi; 12 geçici kural bozulmasının (liste karar verilmişi gösterir, görülme sırası ters, onayda belirteç denetimi yok, onay metni birebir değil, belirteç kayda bağlı değil, ret durumu yazmaz, ilişki adaydan bağımsız, toplu yeniden analiz onaysız adayda, süren parti denetimi yok, parti parti commit, karar koşulsuz, `TYPE_APPROVED` kullanıcısız) her biri testte kırmızı

#### K11.6 — 11.6.1 · Profil fotoğrafı kural seti
- ✅ 11.6.1 kurallar katalogda tutulur ve panelden açılıp kapatılır: sözleşme `app/catalog/photo_rules.py` (yedi kural `PHOTO_RULE_SPECS`; `photo_rules` sütununda `{kural: {enabled}}`, çözünürlük kuralı ayrıca `min_width_px`/`min_height_px`; toleranslı `read_photo_rules`, katı `build_photo_rules`, açık kurallar `enabled_photo_rules`) + `app/catalog/manage.py` `set_photo_rules` (yalnız `profile_picture`; tür formu kuralları ezmez) + `app/web/routers/catalog.py` `POST /document-types/{slug}/photo-rules` (bütün set tek işlemde, geçersiz piksel/tanımsız kural 422 alan başına, fotoğraf kuralı olmayan tür 404) + şablon `catalog_photo_rules.html` (Profile Picture düzenleme sayfasında işaret kutuları ve çözünürlük alanları; tür sayfası `?notice=` alır) — test `tests/catalog/test_photo_rules.py` (42), `tests/web/test_photo_rules_page.py` (26) · C63, D35 · tm 80
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3198 geçti, +68; 4 PG testi atlandı; suite iki ön plan koşusuna bölündü — `tests/web` hariç 2651 ve `tests/web` 547, kapsam `--cov-append` ile birleşti), kapsam %99.85 (`photo_rules.py`, `manage.py`, `routers/catalog.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 10.9.1 kilidine (`tests/web/test_access_log.py`) bir yeni POST yolu eklendi; 9 geçici kural bozmasının (baş örtüsü varsayılan açık, piksel üst sınırı yok, bir kural hep açık, tür formu kuralı eziyor, `set_photo_rules` ve router'da tür denetimi yok, commit yok, işaret kutusu ters, kapalı kural da sorulur) her biri testte kırmızı · tm 80

#### K11.7 — 11.7.1, 11.7.2 · Profil fotoğrafı görsel kontrolü
- ✅ 11.7.1 her açık kural pass/fail/unsure değerlendirilir, fail varsa Unresolved: sözleşme `app/ai/photo_check.py` (`PhotoCheck`, `validate_photo_check`) + `app/ai/provider.py` `check_photo`/`PhotoCheckRequest` (Anthropic/OpenAI zorlanmış `record_photo_check`; kayıtlı yanıt sağlayıcısı aynı sıradan) + talimat `app/ai/prompts/photo_check.md`, açık kurallar `PageAnalysisInstructions.photo_rules` + analiz adımı `app/pipeline/analyze.py` `check_page_photo` (çözünürlük `app/pipeline/render.py` `photo_pixel_size` ile deterministik) → `pages.photo_check_json` (göç 0005) + plan hükmü `app/pipeline/plan.py` `check_photo_rules` (fail ya da değerlendirilmemiş açık kural → Unresolved, gerekçe kural adlarıyla; unsure yalnız not) — test `tests/ai/test_photo_check.py` (37), `tests/pipeline/test_photo_check.py` (28), `tests/pipeline/test_plan.py` (+14), `tests/ai/test_anthropic_provider.py` (+4), `tests/ai/test_openai_provider.py` (+4), `tests/db/test_migrations.py` (+1) · C64, D36 · tm 81
- ✅ 11.7.2 kırpma, düzeltme, arka plan değişikliği yok: kontrol veri dizininde hiçbir baytı değiştirmez (`tests/pipeline/test_photo_check.py`); uçtan uca "iki kişi" ve "düşük çözünürlük" fotoğrafı dosyanın kayıtlı sahibi olsa da Unresolved'da, Inbox ve gömülü görüntü aynı, İK atamasında çıktı gömülü görüntünün kendisi (`tests/test_scenarios_s01_s05.py` +2); S3/S4 fotoğrafı kontrolden geçip Hazir'da gömülü görüntünün aynısı kaldı · tm 81
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3287 geçti, +89; 4 PG testi atlandı; iki ön plan koşusu — `tests/web` hariç 2740 ve `tests/web` 547, kapsam `--cov-append` ile birleşti), kapsam %99.86 (yeni/değişen modüller %100), temiz SQLite'ta `alembic upgrade head` (0001→0005), `import app.main` — hepsi exit 0; kapıdan sonra eklenen bir parametre (başarısız yeniden analiz saklı kontrolü boşaltır) ayrıca yeşil; 16 geçici kural bozmasının (unsure fail sayılır, değerlendirilmeyen kural geçer, kapalı kural okunur, hüküm plana girmez, tür süzgeci yok, kontrol çağrılmaz, sınır `>`, kontrol hatası yutulur, hata kaydı boşaltmaz, boş sayfa sorulur, çözünürlük yapay zekâya sorulur, EXIF yönelimi yok sayılır, render sayfası ölçülmüş sayılır, sorulmayan/eksik kural kabul edilir, kuralı kapalı tür sorulur) her biri testte kırmızı · tm 81

#### K11.8 — 11.8.1 · Fotoğraf örneklerinden öğrenme
- ✅ 11.8.1 kabul edilen fotoğraflar örnek işaretlenir ve açıklamayı besler: işaret `app/catalog/describe.py` `is_accepted_photo`/`accepted_photos` (fotoğraf türünün `active` çıktısı, her kaynak sayfada şu an açık her kural `pass`, yeniden eskiye; saklanmaz, kural setiyle değişir) + besleme `describe_type(photos=)` (örnek sayfalarla aynı istekte, sınır paylaşılır, "Fotoğraf türü: evet") + sözleşme `app/ai/type_description.py` `accepted_photo` → metinde "Kabul edilen fotoğraf: …" + talimat `app/ai/prompts/type_description.md` + panel `catalog_accepted_photos.html` / `app/web/routers/catalog.py` — test `tests/catalog/test_photo_learning.py` (50), `tests/web/test_accepted_photos_page.py` (8), `tests/test_scenarios_s01_s05.py` (+3, S4 uçtan uca: geçen fotoğraf örnek ve açıklamada, `unsure` ile İK'nın atadığı `fail` örnek değil), `tests/ai/test_type_description.py` (+5) · C65, D37 · tm 82
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3354 geçti; 4 PG testi atlandı; iki ön plan koşusu — `tests/web` hariç 2799 ve `tests/web` 555, kapsam `--cov-append` ile birleşti), kapsam %99.86 (`describe.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0005, göç yok), `import app.main` — hepsi exit 0; 15 geçici kural bozmasının (unsure kabul, değerlendirilmemiş kural kabul, kontrolsüz sayfa kabul, durum süzgeci yok, eskiden yeniye, açık kural yokken hepsi, tür süzgeci yok, sınır ayrılmaz, fotoğraf olmayan türe fotoğraf, fotoğraf olmayan türde tanım kabul, tanım metne girmez, "Fotoğraf türü" satırı yok, atlanan sınırı tüketir, rota fotoğrafları vermez, düğme yalnız örnekle) her biri testte kırmızı · tm 82

#### K12.1 — 12.1 · Bot iskeleti ve beyaz liste
- ✅ 12.1.1 bot ayrı servis olarak çalışır; geliştirmede polling, üretimde webhook — `app/telegram/bot.py` (`load_bot_config` mod seçimi ve ayar doğrulaması, `build_application`, `run`, `main`; `python -m app.telegram.bot`), ayarlar `app/config.py` (`TELEGRAM_*`), Compose `bot` servisi (`profiles: [telegram]`), `.env.example`, bağımlılık `python-telegram-bot[webhooks]` · test `tests/telegram/test_config_and_run.py` (30), `tests/telegram/test_polling_serving.py` (1: `run()` gerçek `run_polling`'e girer), `tests/telegram/test_webhook_serving.py` (1: gerçek webhook sunucusu yerel portta, gizli değersiz istek 403), `tests/test_config.py` (+3) · tm 83
- ✅ 12.1.2 listede olmayan kullanıcıya yanıt verilmez — `app/telegram/bot.py` `WhitelistGate` (grup -1, hata durumunda kapalı, yalnız özel sohbet), `is_whitelisted` (`telegram_users.allowed`) · test `tests/telegram/test_whitelist.py` (17) · tm 83
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3406 geçti, +52; 4 PG testi atlandı; iki ön plan koşusu — `tests/web` hariç 2851 ve `tests/web` 555, `COVERAGE_FILE=.pytest_cache/.coverage`, ikincisi `--cov-append`), kapsam %99.86 (`bot.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0005, göç yok), `import app.main`, `docker compose config` — hepsi exit 0; 13 geçici kural bozmasının (kapı durdurmaz, özel sohbet denetimi, hata durumunda açık, `allowed` süzgeci, token maskeleme, üretimde polling, https denetimi, kapı grubu, logda kimlik, webhook gizli değeri iletilmez, `httpx` susturma, hata metni logda, gizli değer zorunluluğu) her biri testte kırmızı · tm 83

#### K12.2 — 12.2.1, 12.2.2, 12.2.3 · Telegram üzerinden belge alma
- ✅ 12.2.1 gönderilen belge ve fotoğraf web ile aynı boru hattından işlenir — `app/telegram/handlers.py` (`DocumentIntake`: indirme → `store_upload` → `process_upload`; belge eki ve fotoğrafın en büyük boyutu, ad sadeleştirme), paylaşılan çekirdek `app/web/routers/uploads.py` `store_upload` (`create_upload` onu çağırır; kanal `telegram`, `uploaded_by` panel kullanıcı adı), bağlantı `app/telegram/bot.py` (`build_application(intake=)`, `main`) · test `tests/telegram/test_intake.py` (42: Inbox baytları aynı, olay zinciri, sağlayıcı kayıtlı, boyut sınırları, indirme/gönderim hataları, beyaz liste belgeleri de süzer, ad sadeleştirme), `tests/telegram/test_config_and_run.py` (`main` işleyiciyi bağlar), `tests/web/test_uploads.py` (çekirdek çıkarıldıktan sonra değişmedi) · tm 84
- ✅ 12.2.2 aynı medya grubundaki dosyalar tek parti sayılır — `app/telegram/handlers.py` `DocumentIntake.receive`/`_close_group` ((sohbet, `media_group_id`) anahtarı, sessizlik penceresi `GROUP_WAIT_SECONDS`, mesaj numarasıyla sıra, `unique_names` ad çakışması `-2`) · test `tests/telegram/test_intake.py` (albüm tek parti + tek özet, her dosyada bekleme yenilenir, geç dosya yeni parti, ayrı albümler ve tekil mesajlar ayrı parti, aynı ad numaralanır, fotoğraf albümü) · tm 84
- ✅ 12.2.3 işlem sonucu ve kuyruğa düşen öğeler kısa mesajla bildirilir — `app/telegram/handlers.py` `build_summary` (durum, `Hazır: N belge` tür + E numarası, `Kuyruğa düşen: N öğe` tür + gerekçe, tekrar sayısı; ad-soyad ve belge numarası yok; 10 öğe + "… ve N öğe daha"), "alındı" iletisi, sağlayıcı kurulamayınca "işlenmiyor" · test `tests/telegram/test_intake.py` (Hazır özeti kimlik taşımaz, Unresolved kuyruk özeti, uzun kuyruk/belge listesi kesilir, tekrar notu, kısmi ve başarısız parti, partiler arası sızıntı yok, gönderilemeyen bildirim işlemeyi geri almaz) · tm 84
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3448 geçti, +42; 4 PG testi atlandı; iki ön plan koşusu — `tests/web` hariç 2893 ve `tests/web` 555, `COVERAGE_FILE=.pytest_cache/.coverage`, ikincisi `--cov-append`), kapsam %99.86 (`handlers.py` ve `bot.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0005, göç yok), `import app.main` — hepsi exit 0 (`docker compose config` gerekmedi: compose değişmedi); 25 geçici kural bozmasının (albüm sırası yok, bekleme yenilenmez, albümler birleşir, en küçük fotoğraf, ad çakışması harfe duyarlı, kanal web, yükleyen yok, özet başka partinin belgesini/kuyruğunu sayar, ön boyut denetimi yok, liste sınırı yok (belge/kuyruk), alındı iletisi yok, kapı öncesi grup, yasak karakter sadeleştirme yok, hata metni loga girer (genel/indirme), indirilen bayt değişir, "too big" ayrımı yok, tekrar notu yok, store_upload'ta boyut sınırı yok, web kanalı bozulur, tekil mesaj albüm sayılır, gönderim hatası işlemeyi durdurur, sağlayıcı hatası yutulmaz) her biri testte kırmızı · tm 84

#### K12.3 — 12.3.1, 12.3.2, 12.3.3 · Doğal dil belge istekleri
- ✅ 12.3.1 "Ahmet Çakar'ın ehliyetini göster" isteği doğru belgeyi bulur: sözleşme `app/ai/document_query.py` (`DocumentQuery`, `validate_document_query`) + `app/ai/provider.py` `read_document_query`/`DocumentQueryRequest` (Anthropic/OpenAI zorlanmış `record_document_query`, görüntüsüz; kayıtlı yanıt sağlayıcısı aynı sıradan) + talimat `app/ai/prompts/document_query.md` + yürütme `app/telegram/intent.py` (`build_query_prompt`, `parse_person`, `find_employees` tam kelime/ad yazımı başına, `find_documents` etkin + tür + yeniden eskiye, `resolve_query`) + bağlantı `app/telegram/bot.py` (`build_application(document_requests=)`, `main`, yardım metni) — test `tests/telegram/test_s17_document_request.py` (1: S17 uçtan uca — ehliyet bota gönderilip boru hattından Hazir'a girer, istek dosyayı Hazir'daki baytlarla gönderir), `tests/telegram/test_document_requests.py` (52), `tests/ai/test_document_query.py` (45), `tests/ai/test_anthropic_provider.py` (+5), `tests/ai/test_openai_provider.py` (+5), `tests/telegram/test_config_and_run.py` (`main` metin ve düğme işleyicilerini bağlar) · C68, D40 · tm 85
- ✅ 12.3.2 birden fazla sonuçta kullanıcıdan seçim istenir: `resolve_documents`/`_employee_question` (önce çalışan, sonra belge; en çok 10 seçenek, fazlası notla) + `ChoiceStore` (rastgele belirteç, tek kullanımlık, sohbet ve kullanıcıya bağlı, 10 dk, sohbette yalnız son soru) + `DocumentRequests.choose` (düğmeler kaldırılır, geçersiz basış uyarı alır) — test S17 (ikinci ehliyet `-2` ekiyle gelince iki seçenekli soru, belge gitmez; seçilen gönderilir), `tests/telegram/test_document_requests.py` (iki belge, iki çalışan → belge, belgesi olmayan çalışan, türsüz istek, seçenek sınırı, tek kullanım, başka sohbet/kullanıcı, süre, yeni soru, erişilemeyen ileti) · tm 85
- ✅ 12.3.3 bot üzerinden gönderilen her belge erişim loguna yazılır: `DocumentRequests._release` göndermeden önce `record_access(user_id=telegram_users.user_id, action=download, channel=telegram)` + commit; kayıt yazılamazsa belge gitmez, gönderim başarısız olursa kayıt kalır; etkin olmayan, dosyası kayıp, veri dizini dışı, 50 MB üstü belge ve listeden çıkmış hesap için ne gönderim ne kayıt — test S17 (iki gönderim, iki kayıt), `tests/telegram/test_document_requests.py` (her gönderime tam bir kayıt, kayıt hatası gönderimi durdurur, gönderim hatası kaydı geri almaz, arşivlenen/kayıp/kaçan/büyük dosya, liste dışı hesap) · tm 85
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3556 geçti, +108; 4 PG testi atlandı; üç ön plan koşusu — `tests/web` hariç 3001, `tests/web` ilk 10 dosya 218, kalan 11 dosya 337; `COVERAGE_FILE=.pytest_cache/.coverage`, sonrakiler `--cov-append`), kapsam %99.87 (`intent.py`, `document_query.py`, `provider.py`, iki sağlayıcı, `bot.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0005, göç yok), `import app.main` — hepsi exit 0 (`docker compose config` gerekmedi: compose değişmedi); 40 geçici kural bozmasının (erişim kaydı yok, kanal web, eylem view, kayıt commit'siz, durum süzgeci yok, tür süzgeci yok, eskiden yeniye, alt dizgi eşleşme, yazımlar karışır, tekrar kelime tek sayılır, alias yok sayılır, ilk çalışan tahmini, ilk belge tahmini, numara ada uymasa da, tek kullanımlık değil, sohbet denetimi yok, süre denetimi yok, eski soru kalır, kapasite yok, arşivlenen gönderilir, boyut sınırı yok, liste dışı hesaba gider, ayraç kaçışı yok, katalog dışı tür tahmini, çok kişide ilk kişi, uzunluk sınırı yok, hata metni loga (iki yer), komut da istek, düğmeler kalır, bayt değişir, numara eki ada karışır, numara kelime içinde, sözleşmede other tutarlılığı/tekrar slug/katalog dışı slug/tür adısız slug denetimi yok, sağlayıcı katalog denetlemez, gönderim hatası sessiz, erişilemeyen ileti düzenlenir) her biri testte kırmızı · tm 85
