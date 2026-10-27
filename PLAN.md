# PLAN — Documania (neredeyiz?)

> Bu dosya projenin **durum haritasıdır**. Ne yapılacağı `urun-gereksinim-dokumani-PRD.md`'de,
> nasıl yapılacağı `MASTER-PROMPT.md`'de, "bitti"nin tanımı `CONVENTIONS.md`'dedir.
> Bu dosyayı bir izleme paneli ayrıştırır — biçim kuralları kesindir (§1).

## 0. Özet tablo

| Faz | PRD | Genel durum | Must sayacı | Kapanış |
| --- | --- | --- | --- | --- |
| Faz 0 — MVP | §5.1 | 107 ✅ · 0 ◐ · 0 ⬜ · 0 🔒 | 101/101 Must | ✅ → KF0 |
| Faz 1 — v1 | §5.2 | 102 ✅ · 0 ◐ · 1 ⬜ · 0 🔒 | 52/52 Must | AÇIK |
| Faz 2 — v2 | §5.3 | 30 ✅ · 0 ◐ · 0 ⬜ · 0 🔒 | 0/0 Must | ✅ → KF2 |
| Faz 3 — Enterprise | §5.4 | 10 ✅ · 0 ◐ · 0 ⬜ · 0 🔒 | 0/0 Must | ✅ → KF3 |

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
| FR-MOD-03 | Yapay zekâ analiz katmanı | 0, 1 | 14 |
| FR-MOD-04 | Karar motoru | 0 | 10 |
| FR-MOD-05 | Kimlik ve çalışan eşleştirme | 0 | 19 |
| FR-MOD-06 | Plan ve doğrulayıcılar | 0 | 10 |
| FR-MOD-07 | Uygulayıcı | 0 | 9 |
| FR-MOD-08 | Kuyruklar ve çözüm | 0 | 6 |
| FR-MOD-09 | Çalışan profili ve orkestrasyon | 0 | 10 |
| FR-MOD-10 | Web yönetim paneli | 1 | 54 |
| FR-MOD-11 | Belge türü kataloğu ve öğrenme | 1, 2 | 34 |
| FR-MOD-12 | Telegram botu | 2 | 26 |
| FR-MOD-13 | İşletme ve dayanıklılık | 3 | 11 |
| FR-MOD-14 | Belge grupları ve başvuru paketleri | 1 | 6 |
| FR-MOD-15 | Hazır şablonlar ve çıktı hazırlama | 1 | 11 |

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
| 03.3.1 | OpenAI sağlayıcı iskeleti | Should (v1) | ✅ → K03.3 |
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
| 05.2.2 | Latin ad ve orijinal yazım ayrımı | Must (MVP) | ✅ → K05.2 |
| 05.3.1 | MRZ ayrıştırma | Must (MVP) | ✅ → K05.3 |
| 05.3.2 | MRZ kontrol hanesi doğrulaması | Must (MVP) | ✅ → K05.3 |
| 05.3.3 | MRZ önceliği | Must (MVP) | ✅ → K05.3 |
| 05.4.1 | Kişi anahtarı | Must (MVP) | ✅ → K05.4 |
| 05.5.1 | Eşleştirme sırası | Must (MVP) | ✅ → K05.5 |
| 05.5.2 | Yalnız isim eşleşmesinin reddi (R8) | Must (MVP) | ✅ → K05.5 |
| 05.5.3 | Belirsiz eşleşme | Must (MVP) | ✅ → K05.5 |
| 05.5.4 | Doğum tarihi taşımayan belgenin tekil isim eşleşmesi (R8 istisnası) | Should (v1) | ✅ → K05.5 |
| 05.6.1 | Otomatik çalışan oluşturma (R9) | Must (MVP) | ✅ → K05.6 |
| 05.6.2 | Ad ve doğum tarihiyle otomatik çalışan oluşturma (R9) | Must (MVP) | ✅ → K05.6 |
| 05.7.1 | Onay bekleyen profil | Must (MVP) | ✅ → K05.7 |
| 05.7.2 | Alias ve numara birikimi | Must (MVP) | ✅ → K05.7 |
| 05.7.3 | Profil alanlarını belgelerden tamamlama | Must (MVP) | ✅ → K05.7 |
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
| 08.1.3 | Şifre yüzünden kopyalanamayan kaynak | Should (v1) | ✅ → K08.1 |
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
| 10.1.4 | Kullanıcı yönetimi | Should (v1) | ✅ → K10.1 |
| 10.1.5 | Panel sekme simgesi | Should (v1) | ✅ → K10.1 |
| 10.1.6 | Ülke başvuru verisi ve bayrak simgeleri | Should (v1) | ✅ → K10.1 |
| 10.1.7 | Panel teması: modern görünüm, açık ve koyu tema | Should (v1) | ✅ → K10.1 |
| 10.1.8 | Yetki seviyeleri: Root (gizli), İK, Kullanıcı | Should (v1) | ✅ → K10.1 |
| 10.1.9 | Erişim logu yalnız root | Should (v1) | ✅ → K10.1 |
| 10.1.10 | Yapay zekâ ayarları yalnız root | Must (v1) | ✅ → K10.1 |
| 10.1.11 | Giriş kaydı ve görünümü yalnız root | Should (v1) | ✅ → K10.1 |
| 10.1.12 | Erişilebilirlik: yaşlı ve az gören kullanıcı | Should (v1) | ✅ → K10.1 |
| 10.2.1 | Yükleme sayfası | Must (v1) | ✅ → K10.2 |
| 10.2.2 | İlerleme görünümü | Should (v1) | ✅ → K10.2 |
| 10.3.1 | Yükleme detay sayfası | Must (v1) | ✅ → K10.3 |
| 10.3.2 | Yeniden çalıştır / yeniden analiz | Should (v1) | ✅ → K10.3 |
| 10.3.3 | Yükleme listesi | Must (v1) | ✅ → K10.3 |
| 10.3.4 | Partiyi yoksay | Should (v1) | ✅ → K10.3 |
| 10.3.5 | Yoksanan partiyi geri alma | Should (v1) | ✅ → K10.7-d |
| 10.3.6 | Süren partiyi iptal et | Should (v1) | ✅ → K10.3 |
| 10.3.7 | Takılan partinin otomatik iptali (10 dk) | Should (v1) | ✅ → K10.3 |
| 10.4.1 | Çalışan listesi | Must (v1) | ✅ → K10.4 |
| 10.4.2 | Arama | Must (v1) | ✅ → K10.4 |
| 10.5.1 | Çalışan profili sayfası | Must (v1) | ✅ → K10.5 |
| 10.5.4 | Profil fotoğrafı yokluğu | Should (v1) | ✅ → K10.5 |
| 10.5.2 | Belge listesi ve açma | Must (v1) | ✅ → K10.5 |
| 10.5.3 | Profil sayfasından yükleme | Should (v1) | ✅ → K10.5 |
| 10.5.5 | Profilden yüklemede kişi denetimi | Must (v1) | ✅ → K10.5 |
| 10.5.6 | Çalışan profilini düzenleme | Must (v1) | ✅ → K10.5 |
| 10.5.7 | Çalışanı pasife alma ve yeniden etkinleştirme | Must (v1) | ✅ → K10.5 |
| 10.5.8 | Profil alt kayıtlarını kaldırma ve iletişim bilgisi ekleme | Should (v1) | ✅ → K10.5 |
| 10.5.9 | İki çalışanı birleştirme | Should (v1) | ✅ → K10.5 |
| 10.5.10 | Arşive taşıma ve arşivden geri alma profilde | Must (v1) | ✅ → K10.5 |
| 10.5.11 | Profilde uyruk bayrağı | Should (v1) | ✅ → K10.5 |
| 10.5.12 | Belgeyi kalıcı silme | Should (v1) | ✅ → K10.5 |
| 10.5.13 | Çalışanı kalıcı silme | Should (v1) | ✅ → K10.5 |
| 10.6.1 | Belge geçmişi | Must (v1) | ✅ → K10.6 |
| 10.7.1 | Kuyruk ekranları | Must (v1) | ✅ → K10.7-a |
| 10.7.2 | Kuyruktan çalışana atama | Must (v1) | ✅ → K10.7-b |
| 10.7.3 | Kuyruktan profil oluşturma | Must (v1) | ✅ → K10.7-c |
| 10.7.4 | Kuyruk öğesini kapatma ve yeniden açma | Must (v1) | ✅ → K10.7-d |
| 10.8.1 | İki aşamalı onay mekanizması | Must (v1) | ✅ → K10.8 |
| 10.8.2 | Belgeyi başka çalışana taşıma | Must (v1) | ✅ → K10.8 |
| 10.9.1 | İçerik düzenlemenin yokluğu (R12) | Must (v1) | ✅ → K10.9 |
| 10.9.2 | Görüntüleme ve indirme logu | Should (v1) | ✅ → K10.9 |
| 10.10.1 | Arayüz dili: İngilizce, Türkçe, Sırpça | Should (v1) | ✅ → K10.10 |
| 10.10.2 | Kullanıcının dil tercihi | Should (v1) | ✅ → K10.10 |
| 10.10.3 | Çeviri kapsamı ve bütünlüğü | Should (v1) | ✅ → K10.10 |
| 10.10.4 | Onay metinleri üç dilde | Should (v1) | ✅ → K10.10 |
| 10.10.5 | Ülke adları seçili dilde | Should (v1) | ✅ → K10.10 |
| 10.10.6 | Yapay zekâ çıktıları ve sistem gerekçeleri İngilizce | Should (v1) | ✅ → K10.10 |
| 10.11.1 | İşlem sonrası geçici bildirim | Should (v1) | ✅ → K10.11 |
| 10.11.2 | Bekleyen işte yol gösterme | Should (v1) | ✅ → K10.11 |
| 10.11.3 | Bildirim ve ipuçları seçili dilde | Should (v1) | ✅ → K10.11 |

### 4.2 FR-MOD-11 — Belge türü kataloğu ve öğrenme (Faz 1 kalemleri)

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 11.1.1 | Katalog yönetim ekranı | Must (v1) | ✅ → K11.1 |
| 11.1.2 | Katalog form doğrulaması | Must (v1) | ✅ → K11.1 |
| 11.1.3 | Kabul kriteri düzenleme | Should (v1) | ✅ → K11.1 |
| 11.1.4 | Katalog tablosu okunabilirliği | Must (v1) | ✅ → K11.1 |
| 11.1.5 | Ülkeye göre süzme | Must (v1) | ✅ → K11.1 |
| 11.1.6 | Türü arşivleme, geri alma ve toplu seçim | Should (v1) | ✅ → K11.1 |
| 11.1.7 | Ülke süzgecinde ve tabloda bayrak ile ülke adı | Should (v1) | ✅ → K11.1 |
| 11.1.8 | Belge Türleri'nde arama | Should (v1) | ✅ → K11.1 |
| 11.1.9 | Reddedilen adayı silme | Should (v1) | ✅ → K11.1 |
| 11.2.1 | Örnek belge yükleme | Should (v1) | ✅ → K11.2 |
| 11.3.1 | Tür açıklaması üretimi | Should (v1) | ✅ → K11.3 |
| 11.4.1 | Prompt derleyici | Must (v1) | ✅ → K11.4 |
| 11.4.2 | Token bütçesi | Should (v1) | ✅ → K11.4 |
| 11.4.3 | Ölçekli ve görünür katalog bütçesi | Should (v1) | ✅ → K11.4 |
| 11.5.1 | Aday tür listesi | Must (v1) | ✅ → K11.5 |
| 11.5.2 | Aday türü onaylama | Must (v1) | ✅ → K11.5 |
| 11.5.3 | Onay sonrası yeniden analiz | Should (v1) | ✅ → K11.5 |
| 11.5.4 | Aday türü reddetme | Should (v1) | ✅ → K11.5 |
| 11.5.5 | Aday tür incelemesi | Must (v1) | ✅ → K11.5 |
| 11.5.6 | Onay formu taslakla dolu açılır | Must (v1) | ✅ → K11.5 |
| 11.5.7 | Reddedilen adayı geri alma | Should (v1) | ✅ → K11.5 |
| 11.9.1 | Eğitim modu sekmesi | Must (v1) | ✅ → K11.9 |
| 11.9.2 | Mekanik tanıma | Must (v1) | ✅ → K11.9 |
| 11.9.3 | Yapay zekâ incelemesi ve "AI kararı" etiketi | Must (v1) | ✅ → K11.9 |
| 11.9.4 | Elle kontrol ikonu ve etiket kararı | Must (v1) | ✅ → K11.9 |
| 11.9.5 | Harita yükle ve toplu tarama | Must (v1) | ✅ → K11.9 |
| 11.9.6 | Eğitim temizliği: öğeyi yoksay, çalıştırmayı arşivle, katalog örneklerinin kaydı | Should (v1) | ✅ → K11.9 |
| 11.9.7 | Örnek önizlemeleri | Should (v1) | ✅ → K11.9 |
| 11.9.8 | Önizleme ön yükleme | Should (v1) | ✅ → K11.9 |
| 11.9.9 | Genel önizleme katmanı | Should (v1) | ✅ → K11.9 |

### 4.3 FR-MOD-14 — Belge grupları ve başvuru paketleri

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 14.1.1 | Belge grupları sekmesi | Must (v1) | ✅ → K14.1 |
| 14.1.2 | Grup kalemi: etiket ya da tür, ülkeden bağımsız eşleşme | Must (v1) | ✅ → K14.1 |
| 14.2.1 | Çalışana paket tanımlama | Must (v1) | ✅ → K14.2 |
| 14.2.2 | Karşılanma hesabı ve kademeli işaret | Must (v1) | ✅ → K14.2 |
| 14.2.3 | Paket tamamlanması ve iptali | Must (v1) | ✅ → K14.2 |
| 14.3.1 | Paket görünürlüğü listede | Should (v1) | ✅ → K14.2 |

### 4.4 FR-MOD-15 — Hazır şablonlar ve çıktı hazırlama (2026-10-23 açılışı; sözleşme §D123)

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 15.1.1 | Hazır Şablonlar sekmesi ve şablon yükleme | Must (v1) | ✅ → K15.1 |
| 15.1.2 | Yapay zekâ şablon incelemesi ve alan haritası önerisi | Must (v1) | ✅ → K15.1 |
| 15.1.3 | Harita önizleme ve onay | Must (v1) | ✅ → K15.1 |
| 15.1.4 | Şablon görüntüleme ve indirme | Should (v1) | ✅ → K15.1 |
| 15.1.5 | Arşivdeki şablonu silme | Should (v1) | ⬜ |
| 15.2.1 | Profilden "Çıktıya hazırla" | Must (v1) | ✅ → K15.2 |
| 15.2.2 | Üretilen belgeler bölümü | Must (v1) | ✅ → K15.2 |
| 15.2.3 | Adlandırma, konum ve yaşam döngüsü | Must (v1) | ✅ → K15.2 |
| 15.3.1 | Ek profil alanları | Must (v1) | ✅ → K15.3 |
| 15.3.2 | Ek alanların belgeden otomatik dolumu | Must (v1) | ✅ → K15.3 |
| 15.3.3 | Kişisel numaranın ülkeye göre yazımı | Should (v1) | ✅ → K15.3 |

### 4.5 FR-MOD-03 — Yapay zekâ analiz katmanı (Faz 1 kalemleri; 2026-10-23 açılışı; sözleşme §D124)

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 03.8.1 | Çalışma zamanı sağlayıcı seçimi | Must (v1) | ✅ → K03.8 |
| 03.8.2 | Model ve efor ayarı | Must (v1) | ✅ → K03.8 |

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
| 12.1.3 | Beyaz listeyi panelden yönetme | Should (v2) | ✅ → K12.1 |
| 12.1.4 | Telegram hesabını bağlantıyla otomatik bağlama | Should (v2) | ✅ → K12.1 |
| 12.1.5 | Yerel başlatıcıda bot | Should (v2) | ✅ → K12.1 |
| 12.1.6 | Bot yanıtları kullanıcının dilinde | Should (v2) | ✅ → K12.1 |
| 12.1.7 | Bot, bağlı olmayan kişiye Telegram kimliğini söyler | Should (v2) | ✅ → K12.1 |
| 12.1.8 | Telegram'ı yalnız hesabın sahibi bağlar | Should (v2) | ✅ → K12.1 |
| 12.1.9 | Botun mesajları sade, kısa ve teknik terimsiz | Should (v2) | ✅ → K12.1 |
| 12.1.10 | Telegram kaydını silme | Should (v2) | ✅ → K12.1 |
| 12.1.11 | Bot her mesaja yanıt verir | Should (v2) | ✅ → K12.1 |
| 12.1.12 | Bot, kişinin yazdığı dilde yanıt verir | Should (v2) | ✅ → K12.1 |
| 12.1.13 | Bot yalnız kendi konusunda konuşur | Should (v2) | ✅ → K12.1 |
| 12.2.1 | Belge alma | Should (v2) | ✅ → K12.2 |
| 12.2.2 | Çoklu mesaj grubu | Should (v2) | ✅ → K12.2 |
| 12.2.3 | Sonuç özeti | Should (v2) | ✅ → K12.2 |
| 12.3.1 | Belge isteme | Should (v2) | ✅ → K12.3 |
| 12.3.2 | Belirsizlikte seçim | Should (v2) | ✅ → K12.3 |
| 12.3.3 | Erişim kaydı | Should (v2) | ✅ → K12.3 |
| 12.3.4 | Tek mesajda birden çok belge türü | Should (v2) | ✅ → K12.3 |
| 12.3.5 | Önceki kişiye devam | Should (v2) | ✅ → K12.3 |
| 12.3.6 | Kişi bilgisi | Should (v2) | ✅ → K12.3 |
| 12.3.7 | Eksik belgeler | Should (v2) | ✅ → K12.3 |
| 12.3.8 | Profil sorusu ve karşılaştırma | Should (v2) | ✅ → K12.3 |
| 12.3.9 | Tek kişinin belgelerini dışa aktarma, toplu dışa aktarımın reddi | Should (v2) | ✅ → K12.3 |
| 12.4.1 | Kuyruk ve hata bildirimi | Could (v3) | ✅ → K12.4 |

## 6. FAZ 3 — Enterprise (PRD §5.4)

### 6.1 FR-MOD-13 — İşletme ve dayanıklılık

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 13.1.1 | Maliyet ölçümü | Could (v3) | ⛔ → K13.1 |
| 13.2.1 | Ucuz model ön eleme | Could (v3) | ✅ → K13.2 |
| 13.2.2 | Metin katmanı önceliği | Could (v3) | ✅ → K13.2 |
| 13.3.1 | Kalıcı işçi kuyruğu | Could (v3) | ✅ → K13.3 |
| 13.4.1 | Erişim logu görünümü | Could (v3) | ✅ → K13.4 |
| 13.4.2 | Yedekleme ve geri yükleme | Could (v3) | ✅ → K13.4 |
| 13.5.1 | Üretim dağıtımı | Could (v3) | ✅ → K13.5 |
| 13.5.2 | APP ve worker servislerinin ayrılması | Could (v3) | ✅ → K13.5-b |
| 13.5.3 | Şema ve kod sürümü uyuşmazlığı koruması | Should (v1) | ✅ → K13.5-c |
| 13.6.1 | İzleme ve uyarı | Could (v3) | ✅ → K13.6 |
| 13.7.1 | Büyük çekirdek modüllerin ayrıştırılması | Could (v3) | ✅ → K13.5-b |

## C. Varsayımlar

Onay beklemeden yapılan varsayımlar buraya numaralı olarak yazılır.

_Eski maddeler: docs/archive/plan-kanit/ — ara: grep -rn '^- \*\*[CD]<no>' docs/archive/plan-kanit_

- **C93** — Belge Türleri tablosu: slug sütunu kalkar, durum renkleri, ülke süzgeci (tm 122, 123; 11.1.4, 11.1.5): insan kararı (2026-09-28): "slug sütunu tabloda görünmesin (arka planda kalsın); Pasif hafif kırmızımsı, Etkin hafif yeşilimsi; ülkeye göre süzgeç — TR seçilince Türkiye türleri ve ülkeden bağımsız genel türler." **Slug:** `<th>Slug</th>` ve `<td><code>` kalkar; ad bağlantısı `title="{{ slug }}"` taşır, tür sayfası slug'ı göstermeye devam eder; `tests/web/test_catalog_page.py:99` (`<code>{slug}</code>` beklentisi) bilerek tersine döner; `panel.css` `.catalog-types` nth-child genişlikleri 9 sütuna göre yeniden dağıtılır (Ad 22 · Etiket 17 · Ülke 6 · Yüz 10 · Direkt 7 · Analiz 7 · Kriter 8 · Durum 10 · İşlem 13). **Renk:** `--success-soft` (yeni, `#e6f4ec`) ve `--danger-soft` (var) ile `.status-active { color: var(--success); background: var(--success-soft) }`, `.status-passive { color: var(--danger); background: var(--danger-soft) }` rozet biçiminde; metin "Etkin"/"Pasif" kalır (renk tek taşıyıcı değil). `type-passive` satır sınıfı kalır. `training_known.html`'deki Slug sütunu bu görevin dışındadır (insan istemedi). **Süzgeç:** `GET /document-types?country=<ISO2|general|all>` (varsayılan `all`); `<select name="country">` + otomatik gönderim (JavaScript'siz de çalışır: "Uygula" düğmesi). Seçenekler `list_types` çıktısından: "Hepsi (N)", "Genel — ülkesiz (N)", sonra ISO2 kodları alfabetik `TR (10)`. Kural: `country=TR` → `country == "TR" or country is None`; `general` → `country is None`. Süzgeç değeri satır bağlantılarında, `NOTICES` yönlendirmelerinde ve etkinleştir/pasifleştir formlarında (gizli alan) korunur. Tablonun üstünde "N tür gösteriliyor (toplam M)". Bütçe satırı (11.4.3) süzgeçten bağımsız kalır. Toplu seçim (11.1.6) bu süzgece dayanır ama tm 132'dedir. **Uygulama notu (tm 122):** 1400 px ölçümünde 22/17/…/10/13 dağılımı işlem sütununu 160 px'e düşürüp "Etkinleştir" düğmesini 29 px kesti; genişlikler §D63'e göre 22/16/6/10/7/7/8/8/16 uygulandı. Süzgeç (tm 123) sütun eklemezse bu dağılım aynen kalır. **Uygulama notu (tm 123):** süzgeç tabloya sütun eklemedi, dağılım aynen kaldı. Tür formunda `country` türün kendi alanı olduğundan listenin süzgeci orada gizli `list_country` alanıyla (tür sayfası ve "Yeni tür" adreste `?country=` ile) taşınır; fotoğraf kuralları ve örnek yükleme formları tür sayfasına döner ve süzgeci taşımaz (liste yönlendirmesi değiller). Durum (etkin/pasif) süzgeci, arama kutusu ve sayfalama eklenmedi (istenmedi).

## D. Sapmalar

PRD'den veya kilitli kararlardan her sapma buraya numaralı yazılır (D1, D2…).
Sapma yazmadan karar değiştirilmez.

Aşağıdaki üç sapma **ürünün ilk sözlü tanımına** göredir ve kurulum aşamasında,
kullanıcı onayıyla verilmiştir. PRD ve `MASTER-PROMPT.md` zaten sapılmış hâli yazar;
bu kayıt neden sapıldığının izlenebilir olması içindir.

_Eski maddeler: docs/archive/plan-kanit/ — ara: grep -rn '^- \*\*D<no>' docs/archive/plan-kanit_

- **D134 — Reddedilen adayı ve arşivdeki şablonu kalıcı silme (11.1.9, 15.1.5; tm 199, 200; insan isteği 2026-10-27).** İnsan isteği: "reddedilenler listesinde 'geri al' yanında 'sil' butonu da olsun. Arşivdekiler de silinebilsin" (ekran görüntüleri: Aday türler / Reddedilenler ve Hazır Şablonlar / Arşivde). Bu, projenin "silinmez" ilkesinin (CLAUDE.md, R11) bilinçli ve dar bir istisnasıdır: yalnız gösterim/yönetim nesnesi silinir, ÇALIŞAN BELGESİ ve üretilmiş belge silinmez. **(a) Kapsam ve koruma:** yalnız `rejected` aday (11.1.9) ve yalnız `archived` şablon (15.1.5) silinir; diğer durumlarda 409. Her ikisi yalnız yazma yetkisiyle (10.1.8) ve iki aşamalı onayla (`/confirm` sayfası + `POST`; mevcut `confirm` kalıbı, `tests/web/test_confirm.py` sözleşmesi) yapılır; onay sayfası ne silineceğini ve "geri alınamaz" uyarısını gösterir. **(b) Aday (tm 199):** aday kaydı ve yalnız ona ait görülme/örnek-sayfa kayıtları (`CandidateTypeSighting`) silinir; sayfaları, yüklemeleri ve belgeleri değişmez. Aday adı aynen yeniden önerilirse yeni aday olur. **(c) Şablon (tm 200):** şablon kaydı + alan haritası + `_sablonlar/<id>/` altındaki orijinal PDF ve önizleme görüntüleri + `cache/previews` karşılığı silinir. O şablondan üretilmiş belge varsa (`generated_documents`.template_id) silme ENGELLENİR ve neden gösterilir; üretilmiş belge dosyaları silinmez (15.2.3). Sıra: önce dosyalar, sonra veritabanı kaydı (dosya silinemezse kayıt kalır, yeniden denenebilir; yetim kayıt yetim dosyadan iyidir). **(d) Kayıt:** `CANDIDATE_TYPE_DELETED` ve `OUTPUT_TEMPLATE_DELETED` olayları (`app/events.py`; ad, sayısal özet, kullanıcı; içerik ve kişisel değer yok) ve olay günlüğü/erişim logu testleri. **(e) Arayüz:** satırda "Geri al"ın yanında "Sil" (tehlike görünümü, `docs/ARAYUZ-STANDARDI.md` bileşen sözlüğündeki düğme kalıbı; yeni sınıf yok), şablon satırında "Sil" yalnız Arşivde sekmesinde; 40 px hedef (§D126). **(f) Kapsam dışı:** toplu silme, arşivdeki BELGE TÜRLERİNİN (11.1.6) silinmesi (tür örnekleri ve belgeleri taşıdığı için ayrı karar ister), çöp kutusu/geri alma, çalışan belgesi silme.
- **D133 — Belge Türleri'nde arama (11.1.8; tm 198; insan isteği 2026-10-27).** İnsan isteği: Belge Türleri sayfasında "Ülke" süzgecinin bulunduğu kutuya bir arama butonu eklensin. Bugün sayfada yalnız ülke süzgeci var (`catalog.html`, `country-select.js`); 400'ü aşkın tür arasında ad ile bulmak elle kaydırmaktır. **(a) Sözleşme:** aynı `GET /document-types` formuna `q` alanı (en çok 100 karakter) ve "Ara" düğmesi eklenir; arama ad, dosya etiketi ve slug üzerinde alt dize, harf büyüklüğü/aksan/Türkçe i-İ duyarsız (`casefold` + aksan atma; `app.matching.names`'teki normalizasyon yeniden kullanılabilir); ülke süzgeciyle AND birleşir (`_filter_types` genişler, tür sayısı süzülmüş listeden yazılır). **(b) Arayüz:** mevcut `country-filter` formu (`hx-get`, `hx-select="#catalog-results"`, `hx-push-url`) aynı kalır; "Ülke" seçimi ile arama kutusu aynı kartta yan yana durur, `Ara` düğmesi Enter ile de çalışır, alan doluyken "Temizle" bağlantısı `q`'yu kaldırır; sonuç yoksa "Eşleşen tür yok." satırı. Yeni sınıf/satır içi stil yok: `docs/ARAYUZ-STANDARDI.md` bileşen sözlüğündeki alan, düğme ve `search` kalıpları kullanılır; 40 px hedef ve alan etiketi (§D126) korunur. **(c) Durum taşıma:** `q`, `country_query` gibi bağlantı soneklerinde, toplu işlem formlarının gizli alanlarında ve işlem sonrası yönlendirmelerde ülke ile birlikte korunur (11.1.5/11.1.6 kuralı); arşiv görünümünde (`archived=1`) de çalışır. **(d) Kapsam dışı:** sunucu tarafı tam metin dizini, yazarken anında arama (yalnız düğme/Enter), sayfalama, tür açıklaması içinde arama, diğer sayfalara (çalışanlar vb.) arama.
- **D132 — Genel önizleme katmanı: her belge kaynağı için küçük/büyük JPEG (11.9.9; tm 197; insan isteği 2026-10-27).** İnsan isteği: "Sadece uploads değil, sistemdeki bütün belgelerin küçük önizleme, büyük önizleme jpeg mantığı olsun; böylece kullanıcıya her sayfada akıcı bir kullanım sağlarız." Bugünkü durum (kodda doğrulandı): önizleme katmanı (`app/storage/previews.py`, §D130) yalnız eğitim ve katalog örneklerinde; yükleme (`/uploads/<id>/pages/<id>/image`), kuyruk (`queue_item`), geçmiş (`history`) ve katalog aday örnekleri tam çözünürlüklü sayfa görüntüsü kullanır; çalışan belgeleri (`/employees/<id>/documents/<id>/file`) ve üretilen belgeler (`/outputs/<id>/file`) orijinali satır içi verir; şablon sayfaları (`/output-templates/<id>/pages/<n>`) tek boyutlu JPEG'dir; profil fotoğrafı orijinaldir. Listelerde en ağır olan çalışan belgeleridir. **(a) Kaynak soyutlaması:** `app/storage/previews.py` bir `PreviewSource` (kimlik, dosya yolu, anahtar, kademe) kavramı alır; örnek, çalışan belgesi, yükleme sayfası, kuyruk/geçmiş sayfası, aday örneği, üretilen belge, şablon sayfası ve profil fotoğrafı aynı `ensure_preview(source, size)` üzerinden `small` (320 px) ve `large` (1280 px) JPEG üretir. Çıktı yolu `cache/previews/<kaynak>/<anahtar>-<boyut>.jpg` (yalnız `DataLayout` yöntemleriyle). Üretim sınırı (2 eşzamanlı yer, önizleme başına tek üretim), piksel sınırı, EXIF/GPS/ICC atma ve atomik yazım §D130/§D131'deki gibi aynen sürer. **(b) Uç ve yetki:** her kaynak türü kendi router'ında önizleme ucu alır (`.../previews/{small|large}`); uç, kaynağın MEVCUT yetki kuralını yeniden kullanır (çalışan belgesi için `documents/<id>/file`'ın kuralı, yükleme için mevcut yükleme erişimi vb.); yeni rol ya da izin eklenmez, yetkisiz istekte mevcut 404 davranışı korunur (belgenin varlığı sızmaz). Yol istekteki addan değil kimlikten çözülür. Belge erişimi `access_log`'a bugün hangi uçta yazılıyorsa yazılır: önizleme gösterimi "görüntüleme" sayılır, küçük resim listesi sayılmaz (liste açıldığında N satır yazılmaz); görüntüleme kaydının tam kuralı uygulayıcı tarafından erişim logu testleriyle sabitlenir ve burada değiştirilmez. **(c) İki kademeli önbellek:** (1) çalışan verisi olmayan kaynaklar (eğitim/katalog örneği, şablon): `private, max-age=31536000, immutable`, içeriğe bağlı adres (`?v=`); (2) gerçek çalışan belgesi içeren kaynaklar (çalışan belgesi, yükleme, kuyruk, geçmiş, üretilen belge, profil fotoğrafı): `private, max-age=900` + `ETag`/304; çıkışta `Clear-Site-Data: "cache"` (§D131 f4) hepsini temizler. Paylaşılan ve uç önbelleğe (Cloudflare) girmez (`private`). **(d) Arayüz:** her listede `<img src=küçük loading=lazy decoding=async width height>`; ada ya da küçük resme tıklayınca büyük önizleme; ayrı "İndir" düğmesi (`attachment`). Çok sayfalı PDF: küçük resim ilk sayfa; büyük önizleme sayfa sayfa (`?page=n`, sayfa sayısı sınırlı), her sayfa ayrı JPEG. Mevcut satır içi orijinal uçları (`/file`) kaldırılmaz ama arayüz artık onlara bağlanmaz; yalnız indirme olarak kalır (`/download` zaten var). Metin ve etiketler `docs/ARAYUZ-STANDARDI.md` bileşen sözlüğüne uyar; yeni sınıf eklenecekse sözlüğe ve `test_ui_standard.py`'ye işlenir. **(e) Ön yükleme (§D131) kapsamı:** giriş sonrası toplu ısıtma (aşama 1) yalnız kademe 1 kaynakları (örnek, şablon) için çalışır; çalışan belgesi kaynakları için toplu liste ucu YOKTUR (başkasının belgesini tarayıcıya yığmamak için): bu kaynaklarda yalnız aşama 2 — açık sayfanın belgelerinin büyükleri (`data-preview-large`) — ve sayfanın küçükleri (`<img loading=lazy>`) iner. `/previews/thumbs` ucu kademe 1 ile sınırlı kalır. **(f) Geçiş ve yedek:** mevcut sayfa görüntüleri (`cache/pages`) boru hattının girdisi olarak durur; önizleme onlardan değil KAYNAKTAN (orijinal dosya) üretilir, böylece analiz görüntüleri etkilenmez. `cache/previews` yedeğe girmez (§D129/§D130). Toplu ısıtma komutu (`python -m app.training previews`) yalnız kademe 1 için; kademe 2 tembel üretilir (ilk görüntülemede). **(g) Sınırlar:** ilk görüntülemede üretim gecikmesi olabilir (sınırlı eşzamanlılık, PDF çizimi); çok büyük PDF'lerde yalnız ilk N sayfa (uygulayıcı karar verir, varsayılan 20) önizlenir, gerisi İndir ile; büyük önizleme Pillow ile 1280 px'e küçüldüğü için ince yazı okunmayabilir (bu durumda İndir). Kapsam dışı: çalışan belgelerinin önceden toplu üretimi, harici CDN, istemci tarafı IndexedDB, ses/video, analiz için kullanılan `cache/pages` görüntülerinin değiştirilmesi.
- **D131 — Önizleme ön yükleme: küçükler giriş sonrası, büyükler sayfa girişinde, hepsi arka planda (11.9.8; tm 196; insan isteği 2026-10-27).** İnsan isteği: "Kullanıcı login olabildiğinde bütün küçük önizlemeler lazy olarak arka planda yavaşça iner; inince durur. Bir belgenin görünebileceği sayfaya gelirsek yalnız o sayfadaki belgelerin büyük önizlemeleri lazy insin" (örnekler: `/document-types/<slug>` örnek belgeler, `/uploads/<id>` belgeleri). Amaç: kullanıcıyı bekletmeden, performans kaybı olmadan tıklamaya hazır. §D130'un üzerine kurulur (11.9.7). **(a) Mekanizma — HTTP önbelleğini ısıtmak:** `app/web/static/preview-prefetch.js` (sürümlü, `base.html`'de `defer`) `fetch(url, {priority: 'low', credentials: 'same-origin'})` ile önizleme adreslerini ister; yanıtlar içeriğe bağlı adresli ve `private` önbellekli olduğu için sonraki `<img>`/açma istekleri ağa gitmez. Service worker ve Cache API KULLANILMAZ (ek yetki yüzeyi, sürüm/temizlik karmaşası; HTTP önbelleği yeter). **(b) Aşama 1 — küçükler:** giriş sonrası ilk sayfa `load` olup tarayıcı boşa düşünce (`requestIdleCallback`, yoksa 2 sn) başlar. Liste, sayfalı bir uçtan alınır (`GET /previews/thumbs?after=<imleç>&limit=200`, oturum şart, yalnız adres + sürüm dizgisi döner, yeni yetki yoktur); istemci aynı anda en çok 2 istek, istekler arasında ~150 ms bekleyerek iner, bitince `localStorage`'a yalnız sürüm dizgisini yazar (`previewWarm:v1` = liste sürümü, içerik yok) ve durur; sürüm değişmedikçe yeniden başlamaz, değişirse yalnız yeniler iner (yeni örnek eklendiyse). Yarıda kalırsa (sekme kapandı) imleç `sessionStorage`'da tutulur. **(c) Aşama 2 — sayfa büyükleri:** sayfa HTML'i o sayfadaki belgelerin büyük önizleme adreslerini `data-preview-large` ile taşır (ek uç gerekmez); script, `IntersectionObserver` ile görünüme yakın olandan uzağa sıralar ve aşama 1 sürerken bile bunları öne alır (kullanıcının bulunduğu sayfa önceliklidir). Yükleme sayfasında (`/uploads/<id>`) aynı yolla o partinin sayfa görüntüleri (`cache/pages`) ısıtılır. **(d) Kullanıcıyı bekletmeme:** `priority: 'low'` ve `loading=lazy` ile gösterilen görüntüler önce; kullanıcının tıkladığı ya da gezindiği anda bekleyen ön yükleme sırası `AbortController` ile iptal edilir (`pointerdown`, `htmx:beforeRequest`, `pagehide`). Sekme gizliyken (`document.hidden`), `navigator.connection.saveData` açıkken ve `effectiveType` `2g`/`slow-2g` iken çalışmaz; `429`/`503` + `Retry-After`'da geri çekilir (üstel bekleme, en çok 60 sn). **(e) Sunucu kaynak yönetimi:** üretim işi (Pillow/PDF çizimi) ayrı bir iş parçacığı havuzunda ve `asyncio.Semaphore(2)` ile sınırlıdır; sınır aşılınca üretim kuyruğa girmez, `503 Retry-After: 2` döner (ön yükleme geri çekilir, kullanıcı tıklaması ise sırayla bekler). Aynı önizleme için eşzamanlı istekler tek üretimi paylaşır (kilit). Isıtma toplu komutu (`python -m app.training previews`, §D130) ilk açılışta sunucu tarafında hepsini önceden üretir; böylece ilk kullanıcı üretim beklemez. **(f) Güvenlik:** (1) ön yükleme yeni veri açığa çıkarmaz: liste ucu ve önizleme uçları aynı oturum ve rol kuralındadır; (2) orijinal dosya hiçbir koşulda ön yüklenmez; (3) gerçek belge içeren yükleme önizlemeleri uzun önbelleklenmez: `Cache-Control: private, max-age=900` ve `ETag`; örnek önizlemeleri (örnek/specimen, çalışan verisi değil) §D130'daki gibi uzun; (4) çıkışta `Clear-Site-Data: "cache"` gönderilir — ortak bilgisayarda çıkıştan sonra önbellekte belge görüntüsü kalmaz (`login_log` çıkış kaydı aynen sürer); (5) `localStorage`/`sessionStorage`'a yalnız sürüm dizgisi ve imleç yazılır, belge adı, çalışan ya da içerik yazılmaz; (6) istek sayısı üst sınırlıdır (liste ucu sayfa başına 200, oturum başına hız sınırı) — ele geçirilmiş oturum bile sunucuyu zorlayamaz; (7) betik harici kaynak yüklemez, satır içi betik yoktur. **(g) Ölçüt:** ~2.200 küçük önizleme ≈ 30–50 MB; aşamalı ve düşük öncelikli indiği için ilk sayfa yüklemesini geciktirmez; ikinci oturumda ağdan hiçbir şey inmez. **(h) Kapsam dışı:** ses/video, `Employees` belge önizlemeleri, Service Worker/IndexedDB, sunucu itmesi (HTTP/2 push, 103 Early Hints), harici CDN.
- **D130 — Örnek önizlemeleri: küçük türetilmiş önizleme, orijinal yalnız İndir ile (11.9.7; tm 195; insan isteği 2026-10-27).** İnsan isteği: siteye girince örnek belgeler ve yüklemeler bazen görünüyor bazen görünmüyor; "çok basit bir önizleme ya da çerez" tutulsun, panele girince önizlemeler gelsin, ada tıklayınca önizleme görünsün, gerçek belge yalnız indirme düğmesiyle insin; lazy yükleme mi Cloudflare önbelleği mi karar bende; her şey güvenli olsun. **Kök neden (kodda doğrulandı):** `training_type.html` her örnek için orijinal dosyayı `<img src=…/examples/<ad> loading="lazy">` ile çeker (yüzlerce JPG/PNG, her biri MB düzeyinde, `FileResponse`, önbellek başlığı yok); tarayıcı aynı anda az bağlantı açar, tünelden (cloudflared) geçen büyük yanıtlar zaman aşımına girebilir ve her ziyaret baştan indirir — "bazen geliyor, bazen gelmiyor" budur. Yalnız tembel yükleme orijinalleri yine indirir; asıl çözüm indirilen baytı küçültmektir. **(a) Türetilmiş önizleme:** sunucu her örnekten bir kez iki JPEG üretir — liste küçük resmi (uzun kenar 320 px, kalite ~70, ~10–25 KB) ve büyük önizleme (1280 px, ~100–250 KB; PDF'de ilk sayfa, `app/pipeline/render.py` çizicisi yeniden kullanılır). Dosyalar `cache/previews/<tür_slug>/<içerik özeti>-<boyut>.jpg` altında durur (anahtar içerik SHA-256'sı ya da boyut+mtime; örnek değişirse yeni adres), atomik yazılır (`app/storage/atomic`), yol yalnız `DataLayout` yöntemleriyle kurulur (MASTER-PROMPT §4). Üretim tembeldir (ilk istekte) ve toplu ısıtma komutu vardır (`python -m app.training previews`, durdurulursa sürer). **(b) Güvenlik:** önizleme uçları oturum ister (mevcut rol kuralları, ek yetki yok); yol istekteki addan kurulmaz (`example_path` gibi listeden doğrulanır); Pillow ile açılır, `Image.MAX_IMAGE_PIXELS` sınırı konur ve `DecompressionBombError` yakalanır; çıktı yalnız yeniden kodlanmış JPEG'dir (EXIF, GPS, ICC taşımaz). "Sistem belgeyi değiştirmez" ilkesi bozulmaz: önizleme belge değil gösterim önbelleğidir, tıpkı `cache/pages`; orijinal bayt bayt aynı kalır. Bozuk ya da üretilemeyen dosyada yer tutucu döner ve İndir çalışır. Başlıklar: `X-Content-Type-Options: nosniff`, `Cache-Control: private, max-age=31536000, immutable` (adres içeriğe bağlı olduğu için güvenli), `ETag` ve koşullu istekte 304. `private`, paylaşılan ve uç önbelleğe girmesini engeller. **(c) Neden Cloudflare önbelleği değil:** yanıtlar oturumun arkasındadır; uçta önbellek yetki denetimini atlayıp kimlikli içeriği başkasına sunabilir. Cloudflare yalnız tüneldir; önbellek tarayıcıdadır (`private`): ilk ziyarette küçük baytlar iner, sonrakilerde ağdan hiçbir şey inmez. **(d) Arayüz:** `training_type.html` ve `catalog_examples.html` küçük resmi `<img loading="lazy" decoding="async" width height>` ile alır; ada tıklayınca büyük önizleme açılır (aynı sayfada iletişim kutusu ya da önizleme sayfası; uygulayan seçer); orijinal yalnız "İndir" düğmesiyle (`Content-Disposition: attachment`) iner. Mevcut `/examples/<ad>` ucu artık satır içi göstermez, yalnız indirir. Erişilebilirlik (§D126): alternatif metin, 40 px hedef, klavyeyle açılıp kapanır. **(e) Yedek:** `cache/previews` yedekten çıkarılır (kaynaktan yeniden üretilir; `backup.sh` hariç tutma listesi güncellenir, §D129). **(f) Kapsam:** eğitim bilinen belgeler (tür sayfası) ve katalog örnekleri sayfası. Yükleme/kuyruk sayfa görüntüleri zaten sayfa önbelleğinden (`cache/pages`) gelir; orada yalnız boyut ve önbellek başlıkları denetlenir, yeniden yazılmaz. Kapsam dışı: ses/video, çalışan belgelerinin (`Employees`) önizlemesi, harici CDN, istemci tarafı IndexedDB önbelleği.
- **D128 — Eğitimde çift inceleme: iki model aynı türü verirse örnek doğrudan "doğrulanmış" (11.9.3, 11.9.4; tm 193; insan isteği 2026-10-27).** İnsan isteği: "Belge türlerinde türünden emin olunamayanları ve 'AI kararı' olanları tekrar bi kontrol ettir… sistem gerçekten eminse belge türünü kaydetsin, insan onayına göndermesin, kendisi o an kararını verip kaydetsin. Önce sistemi buna hazırla, ardından eğitime gönder." İnsan kararları (soruya verilen cevaplar): eminlik = "Sonnet 5.5 low ve gpt 6.1 sol low ayrı ayrı kontrol yapsın, ikisi aynıysa güvenilir kabul edilir"; kapsam = "sadece AI kararı olanlara baksınlar" (Yerleştirilemedi ve Başarısız öğeler kapsam dışı); sonda her iki model için maliyet bilgisi. **(a) Çift:** `app/training/pair.py` — GPT-6.1 Sol (`low`, birinci, yerleştirmeyi yapan) ve Claude Sonnet 5.5 (`low`, ikinci, onaylayan); panelin "Yapay zekâ ayarları"ndaki etkin sağlayıcı/model bu işi etkilemez. Çift yalnız iki anahtar da `.env`'de tanımlıyken ve `TRAINING_AUTO_CONFIRM` (varsayılan `true`) kapalı değilken kurulur; yoksa eğitim eskisi gibi tek (etkin) sağlayıcıyla yürür. **(b) Yeni öğeler:** `TrainingClassificationJob` aynı isteği (render bir kez) iki modele sorar; birinci yanıt bugünkü gibi yerleştirir, ikinci yanıt `resolve_classification` ile eşlenir ve aynı bilinen türe iniyorsa örnek "AI kararı" yerine `verified` olur (`TRAINING_LABEL_VERIFIED`, aktör `system`, olay verisi `review: pair` + iki modelin adı, nota "Çift inceleme: … aynı türü verdi; doğrulandı."); ikinci yanıtın dökümü `checks_json["ai_review"]`'a yazılır. Farklı tür, belirleyemedi ya da hata → eskisi gibi ("AI kararı" elle kontrol; hata deneme/başarısız kuralı aynı). Beklenen türle çelişki (`conflict`) ve yerleşmeyen öğe yolu değişmedi. **(c) Mevcut "AI kararı" örnekleri:** `python -m app.training recheck [--limit N] [--dry-run] [--again] [--report YOL]` — her örneği iki modele ayrı ayrı sordurur: ikisi örneğin türünü verirse `verified`; ikisi aynı ama başka bir bilinen türü verirse `move_example` ile o türe taşınır ve `verified` olur (iki aşamalı insan onayı yerine iki modelin uzlaşması: insan kararı "ikisi aynıysa güvenilir"); farklıysalar ya da biri belirleyemezse örnek "AI kararı" kalır; hata → değişmez. Her örnek ayrı işlemde commit edilir; rapor JSON satırlarıdır (`<veri>/_egitim/cift_inceleme.jsonl`) ve durdurulan koşu kaldığı yerden sürer. **(d) Maliyet:** sağlayıcılar başarılı çağrıların belirteçlerini `usage` (`UsageTotals`) altında toplar; komut sonda model başına çağrı, girdi/çıktı belirteci ve liste fiyatıyla tahmini tutarı yazar. Fiyatlar (2026-10-27, resmi sayfalar): Sol 2 $ girdi / 10 $ çıktı, Sonnet 5.5 2 $ / 10 $ (milyon belirteç). Yerel 5 örnekli kuru koşu ~0,25 $ tuttu (örnek başına ≈ 0,05 $; 405 örnek için ≈ 20 $ tahmini). **(e) Sınırlar:** iki model aynı yanlışı yapabilir; ölçüm (D127) 14 belgede ikisi için de 0 yanlış gösterdi ama küçük örnektir — doğrulanan örneklerin ortak ikinci bakışı yoktur. Taşıma geri alınabilir (olay `TRAINING_EXAMPLE_MOVED` önceki türü taşır). Kapsam dışı: Yerleştirilemedi/Başarısız öğelerin yeniden incelenmesi, panelde "yeniden incele" düğmesi, çift için panelden model seçimi.

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
| 05.2-b | Latin ad ve orijinal yazım ayrımı | 05.2.2 | [OPUS-XHIGH] | 05.2, 05.7 | 0 |
| 05.3 | MRZ ayrıştırma ve kontrol haneleri | 05.3.1, 05.3.2, 05.3.3 | [OPUS-XHIGH] | 05.1 | 0 |
| 05.4 | Kişi anahtarı üretimi | 05.4.1 | [OPUS-XHIGH] | 05.2, 05.3 | 0 |
| 05.5 | Çalışan eşleştirme sırası | 05.5.1, 05.5.2, 05.5.3 | [OPUS-XHIGH] | 05.4 | 0 |
| 05.6 | Otomatik çalışan oluşturma | 05.6.1 | [OPUS-XHIGH] | 05.5 | 0 |
| 05.6-b | Ad ve doğum tarihiyle otomatik yeni çalışan | 05.6.2 | [OPUS-XHIGH] | 05.6, 05.7-b, 13.2 | 0 |
| 05.7 | Onay bekleyen profil ve alias birikimi | 05.7.1, 05.7.2 | [OPUS-XHIGH] | 05.5 | 0 |
| 05.7-b | Profil alanlarını belgelerden tamamlama | 05.7.3 | [OPUS-XHIGH] | 05.2-b, 05.8 | 0 |
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
| 10.3-b | Yükleme listesi | 10.3.3 | [SONNET-XHIGH] | 10.3 | 1 |
| 10.3-c | Partiyi yoksay | 10.3.4 | [OPUS-XHIGH] | 10.3-b, 10.8 | 1 |
| 10.4 | Çalışan listesi ve arama | 10.4.1, 10.4.2 | [SONNET-XHIGH] | 10.1, 09.1 | 1 |
| 10.5 | Çalışan profili sayfası | 10.5.1, 10.5.4, 10.5.2, 10.5.3 | [SONNET-XHIGH] | 10.4 | 1 |
| 10.5-b | Profilden yüklemede kişi denetimi | 10.5.5 | [OPUS-XHIGH] | 05.2-b, 10.5, 06.5 | 1 |
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
| 11.4-b | Ölçekli ve görünür katalog bütçesi | 11.4.3 | [OPUS-HIGH] | 11.4, 13.1, 11.9-d | 1 |
| 11.5 | Aday tür akışı ve onay | 11.5.1, 11.5.2, 11.5.3, 11.5.4 | [OPUS-XHIGH] | 11.1, 04.6, 10.7-c | 1 |
| 11.5-b | İşçi boş-zaman işleri çerçevesi | 11.5.5, 11.9.3 | [OPUS-HIGH] | 13.3, 13.5-b | 1 |
| 11.5-c | Tür taslağı sözleşmesi, talimatı ve sağlayıcılar | 11.5.5 | [OPUS-XHIGH] | 11.3, 03.2 | 1 |
| 11.5-d | Aday tür incelemesi: girdi, sızıntı denetimi, göç, işçi işi | 11.5.5 | [OPUS-XHIGH] | 11.5-b, 11.5-c, 11.5 | 1 |
| 11.5-e | Onay formu taslakla dolu ve "Yeniden incele" | 11.5.6 | [OPUS-HIGH] | 11.5-d, 11.9 | 1 |
| 11.6 | Profil fotoğrafı kural seti | 11.6.1 | [SONNET-XHIGH] | 11.1 | 2 |
| 11.7 | Profil fotoğrafı görsel kontrolü | 11.7.1, 11.7.2 | [OPUS-XHIGH] | 11.6, 03.7 | 2 |
| 11.8 | Fotoğraf örneklerinden öğrenme | 11.8.1 | [OPUS-XHIGH] | 11.7, 11.3 | 2 |
| 11.9 | Eğitim çekirdeği: önerilen tür kaydı, tablolar, yerleştirme, etiket deposu | 11.9.2 | [OPUS-XHIGH] | 11.2 | 1 |
| 11.9-b | Eğitim modu mekanik tanıma | 11.9.2 | [OPUS-XHIGH] | 11.9, 05.3 | 1 |
| 11.9-c | Eğitim yapay zekâ yolu ve "AI kararı" etiketi | 11.9.3 | [OPUS-XHIGH] | 11.5-b, 11.9-b | 1 |
| 11.9-d | Eğitim modu sekmesi, bilinen belgeler, türe yerleştir | 11.9.1 | [OPUS-HIGH] | 11.9-b, 11.9-c, 10.1 | 1 |
| 11.9-e | Etiket kararı: doğrula, taşı, çıkar, katalog ikonu | 11.9.4 | [OPUS-HIGH] | 11.9-d, 10.8, 11.3 | 1 |
| 11.9-f | Harita yükle ve toplu tarama | 11.9.5 | [OPUS-XHIGH] | 11.9-c, 11.9-d | 1 |
| 11.9-g | Eğitimde çift inceleme: Sol + Sonnet 5.5 (`low`) aynı türü verirse "doğrulanmış"; "AI kararı" örneklerini yeniden inceleme komutu ve maliyet raporu | 11.9.3, 11.9.4 | [OPUS-HIGH] | 11.9-c, 11.9-e, 03.3-b | 1 |
| 12.1 | Bot iskeleti ve beyaz liste | 12.1.1, 12.1.2 | [SONNET-XHIGH] | 09.2 | 2 |
| 12.2 | Telegram üzerinden belge alma | 12.2.1, 12.2.2, 12.2.3 | [SONNET-XHIGH] | 12.1, 01.1 | 2 |
| 12.3 | Doğal dil belge istekleri | 12.3.1, 12.3.2, 12.3.3 | [OPUS-MAX] | 12.1, 10.4 | 2 |
| 12.4 | Kuyruk ve hata bildirimleri | 12.4.1 | [SONNET-XHIGH] | 12.1, 08.1 | 2 |
| 13.1 | Maliyet ölçümü ve görünürlüğü | 13.1.1 | [SONNET-XHIGH] | 03.7, 10.1 | 3 |
| 13.2 | Ucuz model ön eleme | 13.2.1, 13.2.2 | [OPUS-XHIGH] | 13.1, 03.7 | 3 |
| 13.3 | Kalıcı işçi kuyruğu | 13.3.1 | [OPUS-XHIGH] | 09.2 | 3 |
| 13.4 | Erişim logu, yedekleme ve geri yükleme | 13.4.1, 13.4.2 | [SONNET-XHIGH] | 10.9 | 3 |
| 13.4-b | Eğitim malzemesi ayrı hacimlerde, gece arşivinin dışında ve artımlı yedekli | 13.4.2 | [SONNET-XHIGH] | 13.4, 11.9-g | 3 |
| 13.5 | Üretim dağıtımı | 13.5.1 | [SONNET-XHIGH] | 10.1 | 3 |
| 13.5-b | APP-worker ayrımı ve büyük çekirdek modülleri | 13.5.2, 13.7.1 | [OPUS-XHIGH] | 13.3, 13.5 | 3 |
| 13.6 | İzleme ve uyarılar | 13.6.1 | [SONNET-XHIGH] | 13.3, 12.4 | 3 |
| 11.1-b | Belge Türleri tablosu: slug sütunu kalkar, Durum renkli | 11.1.4 | [SONNET-XHIGH] | 11.4-b | 1 |
| 11.1-c | Belge Türleri: ülkeye göre süzme (genel türler dahil) | 11.1.5 | [SONNET-XHIGH] | 11.1-b | 1 |
| 14.1 | Belge grupları: tablolar, sekme, grup ve kalem yönetimi | 14.1.1, 14.1.2 | [OPUS-XHIGH] | 10.1, 11.1, 11.1-c | 1 |
| 14.2 | Çalışan profilinde belge paketleri: tanımlama, karşılanma, tamamlanma, iptal, liste | 14.2.1, 14.2.2, 14.2.3, 14.3.1 | [OPUS-XHIGH] | 14.1, 10.5, 09.1-b | 1 |
| 15.3-a | Ek profil alanları: sütunlar ve göç, profil kartı, düzenleme formu, profil.md, arama, birleştirme ve kalıcı silme | 15.3.1, 15.3.3 | [OPUS-HIGH] | 10.5-c, 10.5-f, 10.5-k | 1 |
| 15.3-b | Ek alanların belgeden dolumu: analiz şeması ve talimat, MRZ isteğe bağlı alan, 05.7.3 genişletmesi, geri dolum komutu, kayıtlı yanıtlar | 15.3.2 | [OPUS-HIGH] | 15.3-a, 05.7-b | 1 |
| 15.1-a | Hazır şablon deposu: tablolar ve göç, dizin, yükleme, liste, arşiv, görüntüleme/indirme, menü girdisi | 15.1.1, 15.1.4 | [OPUS-HIGH] | 10.1, 10.9, 02.1 | 1 |
| 15.1-b | Şablon incelemesi: alan haritası şeması, talimat, işçi işi, sürüm dondurma, kayıtlı yanıt testi | 15.1.2 | [OPUS-HIGH] | 15.1-a, 03.6 | 1 |
| 15.1-c | Harita önizleme ve onay ekranı: kutu çizimi, atama düzenleme, boş bırak, onay | 15.1.3 | [OPUS-HIGH] | 15.1-b | 1 |
| 15.2-a | Çıktıya hazırla: üretim (PyMuPDF), değer biçimleri, eksik alan uyarısı, adlandırma, kayıt, olaylar, profil bölümleri, aç/indir; S29 | 15.2.1, 15.2.2 | [OPUS-HIGH] | 15.1-c, 15.3-a | 1 |
| 15.2-b | Üretilen belge yaşam döngüsü: yeniden üretim ve eski sürüm, arşiv/geri al, yeniden adlandırma, birleştirme, kalıcı silme, profil.md | 15.2.3 | [OPUS-HIGH] | 15.2-a | 1 |
| 10.5-c | Çalışan profilini düzenleme (K8 yeniden adlandırma dahil) | 10.5.6 | [OPUS-XHIGH] | 10.5, 05.7-b, 09.1-b, 10.8 | 1 |
| 10.5-d | Çalışanı pasife alma ve yeniden etkinleştirme | 10.5.7 | [OPUS-XHIGH] | 10.5-c, 10.4, 10.7-b | 1 |
| 10.5-e | Profil alt kayıtları: alias, numara, iletişim kaldırma; iletişim ekleme | 10.5.8 | [OPUS-HIGH] | 10.5-c | 1 |
| 10.5-f | İki çalışanı birleştirme | 10.5.9 | [OPUS-XHIGH] | 10.5-d, 10.5-e, 14.2 | 1 |
| 10.5-g | Arşive taşı ve arşivden geri al profilde | 10.5.10 | [OPUS-HIGH] | 10.5, 10.8, 08.4, 14.2 | 1 |
| 10.7-d | Kuyruk öğesini kapatma ve yeniden açma; yoksanan partiyi geri alma | 10.7.4, 10.3.5 | [OPUS-XHIGH] | 10.7-a, 10.3-c, 10.8 | 1 |
| 11.1-d | Türü arşivleme, geri alma, toplu seçim, aktivasyon olayları; reddedilen adayı geri alma | 11.1.6, 11.5.7 | [OPUS-HIGH] | 11.1-c, 11.5, 11.9-d | 1 |
| 11.9-g | Eğitim temizliği: öğeyi yoksay/geri al, çalıştırmayı arşivle, katalog örneklerinin kaydı ve çıkarılması | 11.9.6 | [OPUS-HIGH] | 11.9-e, 11.9-f | 1 |
| 11.9-h | Örnek önizlemeleri: küçük türetilmiş önizleme (liste 320 px, büyük 1280 px), orijinal yalnız İndir düğmesiyle; `private` uzun önbellek | 11.9.7 | [OPUS-MEDIUM] | 11.9-d, 11.9-e | 1 |
| 11.9-i | Önizleme ön yükleme: giriş sonrası küçükler, sayfaya girince o sayfanın büyükleri; düşük öncelik, sunucuda sınırlı eşzamanlılık, çıkışta önbellek temizliği | 11.9.8 | [OPUS-MEDIUM] | 11.9-h | 1 |
| 11.9-j | Tüm belgeler için genel önizleme katmanı: çalışan belgeleri, yükleme, kuyruk, geçmiş, aday örnekleri, üretilen belgeler, şablonlar, profil fotoğrafı; kaynak başına yetki ve iki kademeli önbellek | 11.9.9 | [OPUS-MEDIUM] | 11.9-h, 11.9-i | 1 |
| 10.1-b | Kullanıcı yönetimi: liste, yeni kullanıcı, parola, pasife alma | 10.1.4 | [OPUS-HIGH] | 10.1 | 1 |
| 12.1-b | Telegram beyaz listesini panelden yönetme | 12.1.3 | [OPUS-HIGH] | 10.1-b, 12.1 | 2 |
| 00.6-b | Açılışta boş katalog tablosunu tohumdan yükleme: panel, işçi ve bot | 00.6.2, 00.6.3 | [OPUS-HIGH] | 00.6, 13.5-b | 0 |
| 01.3-b | AES şifreli (sahip parolalı) PDF: sayfa sayımı çökmez, uygulayıcı tanımlı hatayla reddeder | 01.3.1, 11.2.1 | [OPUS-HIGH] | 01.3, 07.2, 07.3, 11.2 | 0 |
| 10.5-h | Profil kartı tarih testi UTC'ye bağlanır | 10.5.6 | [SONNET-XHIGH] | 10.5-c | 1 |
| 10.1-c | Panel sekme simgesi | 10.1.5 | [SONNET-XHIGH] | 10.1 | 1 |
| 08.1-b | Şifre yüzünden kopyalanamayan kaynak Unreadable kuyruğuna | 08.1.3 | [OPUS-XHIGH] | 08.1, 01.3-b | 0 |
| 13.5-c | Şema ve kod sürümü uyuşmazlığı koruması | 13.5.3 | [OPUS-HIGH] | 13.5-b | 3 |
| 10.1-d | Ülke başvuru verisi ve bayrak simgeleri | 10.1.6 | [OPUS-HIGH] | 10.1-c | 1 |
| 11.1-e | Ülke süzgecinde ve tabloda bayrak ile ülke adı | 11.1.7 | [OPUS-HIGH] | 10.1-d, 11.1-c | 1 |
| 11.1-f | Belge Türleri tablosunun yerleşimi: ülke ve işlem hücreleri taşmaz, sütun oranları ve yazı boyutu yeniden ayarlanır | 11.1.4, 11.1.7 | [SONNET-XHIGH] | 11.1-e | 1 |
| 11.1-g | Belge Türleri: ülke süzgecinin yanına arama kutusu ve Ara düğmesi (ad, dosya etiketi, slug; ülke süzgeciyle birleşir) | 11.1.8 | [OPUS-MEDIUM] | 11.1-c, 11.1-e | 1 |
| 11.1-h | Reddedilen aday türü kalıcı sil: Reddedilenler sekmesinde Geri al yanında Sil, iki aşamalı onay, olay kaydı | 11.1.9 | [OPUS-MEDIUM] | 11.1-d | 1 |
| 15.1-d | Arşivdeki şablonu kalıcı sil: iki aşamalı onay, üretilmiş belge varsa engel, olay kaydı | 15.1.5 | [OPUS-MEDIUM] | 15.1-a | 1 |
| 13.1-b | Maliyet ölçümü ve panelinin kaldırılması | 13.1.1 | [OPUS-HIGH] | 13.1, 13.2 | 3 |
| 10.1-e | Menü sırası ve ana sayfa Çalışanlar | 10.1.1 | [SONNET-XHIGH] | 10.1 | 1 |
| 12.1-c | Telegram kimliğini @userinfobot'tan öğrenme rehberi ve kopyalanan satırı kabul | 12.1.3 | [SONNET-XHIGH] | 12.1-b | 2 |
| 12.1-d | Telegram hesabını bağlantıyla otomatik bağlama | 12.1.4 | [OPUS-XHIGH] | 12.1-c | 2 |
| 12.1-e | Yerel başlatıcıda bot | 12.1.5 | [SONNET-XHIGH] | 12.1 | 2 |
| 10.5-i | Profilde uyruk bayrağı | 10.5.11 | [SONNET-XHIGH] | 10.1-d, 10.5-c | 1 |
| 10.1-f | Ürün adı Documania (görünen ad; iç kimlikler korunur) | 10.1.5 | [SONNET-XHIGH] | 10.1-c | 1 |
| 10.10-a | Arayüz dili altyapısı: gettext/Babel kataloğu, istek dili, varsayılan İngilizce, iskelet sayfalar | 10.10.1, 10.10.3 | [OPUS-XHIGH] | 10.1-f | 1 |
| 10.10-b | Kullanıcının dil tercihi: hesapta saklama, dil seçici, girişte otomatik dil | 10.10.2 | [OPUS-HIGH] | 10.10-a | 1 |
| 10.10-c | Çeviri I: çalışanlar, profil, yükleme, yüklemeler, geçmiş, erişim logu, kullanıcılar, hesap | 10.10.3 | [OPUS-HIGH] | 10.10-b | 1 |
| 10.10-e | Onay metinleri üç dilde | 10.10.4 | [SONNET-XHIGH] | 10.10-a | 1 |
| 10.10-f | Ülke adları ve JavaScript metinleri seçili dilde | 10.10.5, 10.10.3 | [OPUS-HIGH] | 10.10-a | 1 |
| 10.10-d | Çeviri II: Belge Türleri, adaylar, Belge Grupları, Kuyruklar, Eğitim modu; bütün panelde kalıntı taraması | 10.10.3 | [OPUS-HIGH] | 10.10-c, 10.10-e, 10.10-f | 1 |
| 12.1-f | Bot yanıtları kullanıcının dilinde | 12.1.6 | [SONNET-XHIGH] | 10.10-b, 12.1-d | 2 |
| 12.1-h | Telegram'ı yalnız hesabın sahibi bağlar: Hesabım → Telegram sayfası; Kullanıcılar sayfasından başkasına bağlama kalkar | 12.1.8 | [OPUS-HIGH] | 12.1-d, 10.10-c | 2 |
| 12.1-g | Bot, bağlı olmayan kişiye Telegram kimliğini söyler | 12.1.7 | [SONNET-XHIGH] | 12.1-f, 12.1-h | 2 |
| 12.1-i | Botun mesajları sade, kısa ve teknik terimsiz; teknik uyarılar Telegram'a gitmez | 12.1.9, 12.4.1 | [OPUS-HIGH] | 12.1-g | 2 |
| 12.1-j | Telegram kaydını silme: Kullanıcılar ve Hesabım → Telegram; numara yeniden bağlanabilir | 12.1.10 | [OPUS-HIGH] | 12.1-h, 12.1-i | 2 |
| 12.3-b | Botla konuşma: birden çok tür, önceki kişiye devam, kişi bilgisi, eksik belgeler; her mesaja yanıt; yazılan dilde yanıt | 12.3.4, 12.3.5, 12.3.6, 12.3.7, 12.1.11, 12.1.12 | [OPUS-XHIGH] | 12.3, 12.1-i, 14.2 | 2 |
| 12.3-c | Profil sorusu ve karşılaştırma, tek kişilik dışa aktarım, konu dışı mesaj sayacı | 12.3.8, 12.3.9, 12.1.13 | [OPUS-XHIGH] | 12.3-b | 2 |
| 10.1-g | Panel teması: modern görünüm, açık ve koyu tema | 10.1.7 | [OPUS-HIGH] | 10.1 | 1 |
| 05.5-b | Doğum tarihi taşımayan belgenin tekil isim eşleşmesi; birikim yok, profilde etiket; S10 yeniden tanımı, S23 | 05.5.4 | [OPUS-XHIGH] | 05.5, 05.7-b, 10.5-d | 0 |
| 10.5-j | Belgeyi kalıcı silme: dosya, Alinan ve Inbox ölçütleri, iskelet kayıt, profil akışı; S24 | 10.5.12 | [OPUS-XHIGH] | 10.5-g, 10.8 | 1 |
| 10.5-k | Pasif çalışanı kalıcı silme: klasör, alt kayıtlar, sayfalar, planlar, olay temizliği, görünürlük; S25 | 10.5.13 | [OPUS-XHIGH] | 10.5-j, 10.5-d, 10.5-f | 1 |
| 10.3-d | Süren partiyi iptal et ve 10 dakikada çözülmeyeni otomatik iptal et; S26 | 10.3.6, 10.3.7 | [OPUS-HIGH] | 10.3-c, 13.3.1, 10.8 | 1 |
| 10.1-h | Yetki sistemi: root (gizli, tek Zvz), İK, Kullanıcı salt okunur; erişim logu yalnız root; S27 | 10.1.8, 10.1.9 | [OPUS-XHIGH] | 10.1, 10.9, 12.1 | 1 |
| 10.11-a | Geçici bildirim altyapısı: tek kullanımlık bildirim, dört tür, üç dil; sayfa içi `?notice=` bildirimlerinin taşınması, bildirimsiz yazma işlemlerine bildirim | 10.11.1, 10.11.3 | [OPUS-HIGH] | 10.10-f, 10.1-h | 1 |
| 10.11-b | Bekleyen işte yol gösterme: parti detayı kuyruk satırı bağlantıları, kuyruk türüne göre adımlar, aday tür onayı sonrası bildirim, boş durumlar, rol süzgeci; S28 | 10.11.2, 10.11.3 | [OPUS-HIGH] | 10.11-a, 11.5, 10.7-d | 1 |
| 10.10-g | Yapay zekâ serbest metinleri ve sistem gerekçeleri İngilizce; gerekçeler panelde kullanıcının dilinde | 10.10.6 | [OPUS-HIGH] | 10.10-f, 11.5 | 1 |
| 03.8-a | Çalışma zamanı yapay zekâ ayarı: `ai_settings` ve göç, tek etkin sağlayıcı, model listesi, efor her iki sağlayıcıda, modele göre istek biçimi, yeniden başlatmasız geçiş | 03.8.1, 03.8.2 | [OPUS-HIGH] | 03.2, 03.3, 03.6 | 1 |
| 10.1-i | Yapay zekâ ayarları sayfası yalnız root (gizli): anahtar durumu, etkin/pasif, model ve efor, olay | 10.1.10 | [OPUS-MEDIUM] | 03.8-a, 10.1-h | 1 |
| 10.1-j | Giriş kaydı (`login_log` ve göç; başarılı, başarısız + neden, çıkış; IP ve tarayıcı) ve erişim logunda "Girişler" sekmesi yalnız root: süzgeç, kullanıcı özeti | 10.1.11 | [OPUS-HIGH] | 10.1-h | 1 |
| 10.1-k | Erişilebilirlik: yazı ölçeği ve 40 px hedefler, kontrast, kalın odak halkası, altı çizili bağlantı, "Büyük yazı" düğmesi, "İçeriğe atla", yüksek kontrast tercihi | 10.1.12 | [FABLE-HIGH] | 10.1-g | 1 |
| 03.3-b | OpenAI sağlayıcısı Responses API'ye: GPT-6.1 Sol listede, Luna listeden çıktı, efor yalnız seçilince gider, eğitim sınıflandırması `notes` 250 | 03.3.1, 03.8.2 | [OPUS-HIGH] | 03.8-a | 1 |

## K. Kanıt Geçmişi (evidence log)

Her kapanış, kapattığı gereksinimin `#### K<kod>` bloğuna madde ekler. Blok yoksa açılır;
var olan maddeler silinmez. Biçim:

```
#### K99.9 — <PRD kodu> · <kısa başlık>        <-- ÖRNEK, gerçek kod değil
- ✅ <ne yapıldı> — `<dosya>` · test `<test dosyası>` (n) · tm <id>
```

#### K00.1 — 00.1.1–00.1.4 · Uygulama iskeleti, test ve kapsayıcı altyapısı
- ✅ `ruff check .` exit 0 · `ruff format --check .` exit 0 · compileall exit 0 · kapsam %100 — `pyproject.toml` [tool.ruff] · tm 1

_Önceki maddeler: docs/archive/plan-kanit/ (#### K00.1)_
#### K00.2 — 00.2.1, 00.2.2 · Ortam değişkeni tabanlı yapılandırma
- ✅ pydantic-settings tabanlı `Settings` (`.env` + ortam değişkeni, zorunlu `database_url`, varsayılanlı `app_env`/`data_dir`); eksik zorunlu değişkende değişken adını söyleyen `RuntimeError` — `app/config.py` · `.env.example` · test `tests/test_config.py` (4) · tm 2

#### K00.3 — 00.3.1, 00.3.2, 00.3.3 · Veri modeli ve göç altyapısı
- ✅ `allocate_employee_number`: `E0001` biçimi, sayısal artış (`E9999 → E10000`), eşzamanlı 50 çağrıda çakışma yok (SQLite `BEGIN IMMEDIATE`, PG advisory kilit; kilitsiz kontrol denemesinde PG 46/50, SQLite 21/50 çakıştı) — `app/db/models.py` · test `tests/db/test_employee_number.py` (12; PG eşzamanlılık testi PG 16'da yeşil) · tm 3

_Önceki maddeler: docs/archive/plan-kanit/ (#### K00.3)_
#### K00.4 — 00.4.1–00.4.4 · Depolama katmanı: yol, slug, adlandırma, atomik yazma
- ✅ 00.4.4 SHA-256 yazarken hesaplanır (`sha256_file` ile eşit); istisna, `KeyboardInterrupt`, `fsync`/yayın hatası ve **öldürülen alt süreçte** hedef adda yarım dosya kalmaz, geçici dosya silinir/açılışta temizlenir; `replace_file` kesilirse eski içerik korunur; POSIX yolu (`os.link` + dizin `fsync`) Linux kapsayıcısında elle doğrulandı — `app/storage/atomic.py` · test `tests/storage/test_atomic.py` · tm 4

_Önceki maddeler: docs/archive/plan-kanit/ (#### K00.4)_
#### K00.5 — 00.5.1, 00.5.2 · Olay logu altyapısı
- ✅ 00.5.2 `event_context` (contextvar tabanlı, iç içe kullanımda belirtilmeyen alanları dıştan miras alır) içinde atılan olaylar upload/file/page alanlarını açıkça verilmedikçe otomatik taşır — `app/events.py` · test `tests/test_events.py` (7) · tm 5

_Önceki maddeler: docs/archive/plan-kanit/ (#### K00.5)_
#### K00.6 — 00.6.1, 00.6.2, 00.6.3 · Belge türü kataloğu ve başlangıç tohumu
- ✅ 00.6.2/00.6.3 taze kurulumda katalog tablosu açılışta dolar (tm 136, §D76): `app/catalog/bootstrap.py` (`load_catalog_on_startup`, `seed_empty_catalog`: tohum dosyası yoksa yazılır, tablo boşsa dosya yüklenir, doluysa dokunulmaz; şemasız DB, geçersiz dosya ve eşzamanlı açılış süreci durdurmaz), çağıranlar `app/main.py`, `app/worker/__main__.py`, `app/telegram/bot.py` · test `tests/catalog/test_bootstrap.py` (9), `tests/catalog/test_fresh_install.py` (2: `alembic upgrade head` + panel/işçi açılışı), `tests/telegram/test_config_and_run.py` (+1), `tests/worker/test_runtime.py` güncellendi · kural bozmasında 6 test kırmızı · `pytest -q -m "not live" --cov=app` sekiz paralel grupta 5886 geçti, 5 atlandı, 1 kırmızı (tarih testi, tm 138 düzeltti, dosyası 18/18 yeşil; sonra eklenen 1 `pdfinfo` testi dosyasında yeşil), `coverage combine` + `report --fail-under=70` exit 0, birleşik kapsam %99 (`bootstrap.py`, `pdfinfo.py` %100) · tm 136

_Önceki maddeler: docs/archive/plan-kanit/ (#### K00.6)_
#### K01.1 — 01.1.1, 01.1.2 · Yükleme uç noktası ve parti oluşturma
- ✅ Yükleme ön denetimi — adı doğrulama (tm 94, 01.1.1 sağlamlığı): `_validated_name` yol ayracı/`..`'a ek olarak Inbox'a yazılamayan adı 400 ve anlaşılır mesajla reddeder — `<` `>` `:` `"` `|` `?` `*`, denetim karakterleri (NUL dahil), sondaki nokta/boşluk (Windows sessizce atar: kayıtlı ad ile diskteki ad ayrışırdı), 255 baytı aşan ad; küme platformdan bağımsızdır (§D47), Windows'ta 500 veren `os.link` WinError 123 yolu artık hiç çalışmaz; ad denetimi hep-ya-hiçtir (parti, `upload_files` satırı, olay, iş ve Inbox dizini oluşmaz), sıradan Türkçe adlar (`Çağla Özgür - Pasaport (1).pdf`) kabul edilir — `app/web/routers/uploads.py` · test `tests/web/test_uploads.py` (+30: 6 HTTP ad, 17 çekirdek ad, 1 toplu ret, 5 sıradan ad, 1 uzunluk sınırı), `tests/web/test_upload_page.py` (+1) · D47 · tm 94

_Önceki maddeler: docs/archive/plan-kanit/ (#### K01.1)_
#### K01.2 — 01.2.1, 01.2.2 · İçerik tabanlı dosya türü tespiti
- ✅ Yükleme ön denetimi — desteklenmeyen türün reddi (tm 94): `store_upload` her dosyanın içeriğini `detect_file_kind` ile denetler (uzantıya bakılmaz, 01.2.1); yedi türün dışındaki içerik 400 ve `'<ad>': Desteklenmeyen dosya türü. Yalnız PDF, JPEG, PNG, DOC, DOCX, XLS, XLSX kabul edilir.` iletisiyle reddedilir — hangi dosya olduğu adıyla söylenir, 01.3.1 emsaliyle hep-ya-hiç (tek dosya desteklenmese bile parti, `upload_files` satırı, olay, iş ve Inbox dizini oluşmaz); tür denetimi boyut/sayfa sınırından önce gelir (dosyayı bölmek onu desteklenen tür yapmaz) ve sayfa sayımı aynı tespitin sonucunu kullanır (`_pdf_page_count` artık türü yeniden aramaz); denetim web (`POST /api/uploads`, `/upload`) ve Telegram (`store_upload` ortak çekirdeği) için ortaktır; `/upload` sayfası 4xx iletisini `role="alert"` içinde gösterir (ad HTML'e kaçırılır); yedi türün her biri kabul edilir; yedi türe uymayan baytla (`b"1"`, `b"0123456789A"`) POST eden sekiz mevcut test sentetik geçerli içerikle (`make_pdf_bytes`, `%PDF-` imzası) güncellendi, beklentileri değişmedi — `app/web/routers/uploads.py` (`_supported_kind`) · test `tests/web/test_uploads.py` (+17: 7 desteklenmeyen içerik, 1 toplu ret, 7 kabul edilen tür, 1 uzantı/içerik, 1 tür-boyut sırası), `tests/web/test_upload_page.py` (+1) · D47 · tm 94

_Önceki maddeler: docs/archive/plan-kanit/ (#### K01.2)_
#### K01.3 — 01.3.1 · Boyut ve sayfa sınırı denetimi
- ✅ 01.3.1 AES şifreli (sahip parolalı) PDF'te sayfa sınırı çökmeden denetlenir (tm 137, §D76): `app/storage/pdfinfo.py` `count_pdf_pages` (pypdf, AES çözülemezse MuPDF; açma parolalı/okunamayan → `None`), `app/web/routers/uploads.py` onu kullanır; eskiden `DependencyError` 500 veriyordu · test `tests/storage/test_pdfinfo.py` (7), `tests/web/test_uploads.py` (+1: 3 sayfa 400, 2 sayfa 201) · uygulayıcı `app/pipeline/execute_pdf.py` `_read_pdf` çıkarma/birleştirmede `şifreli (AES)` tanımlı hatası (`tests/pipeline/test_execute.py` +2 parametre); şifre kaldırılmaz (K11) · `pytest -q -m "not live" --cov=app` sekiz paralel grupta 5886 geçti, 5 atlandı, 1 kırmızı (tarih testi, tm 138 düzeltti, dosyası 18/18 yeşil; sonra eklenen 1 `pdfinfo` testi dosyasında yeşil), `coverage combine` + `report --fail-under=70` exit 0, birleşik kapsam %99 (`bootstrap.py`, `pdfinfo.py` %100) · tm 137

_Önceki maddeler: docs/archive/plan-kanit/ (#### K01.3)_
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
- ✅ 03.1.4 `person.contact` `phone`/`email`/`address` belgede yazılıysa döner, yoksa `null` (anahtar zorunlu, `contact: null` veya boş metin reddedilir); alan adları `ContactKind` değerleriyle birebir aynı (05.8.1 doğrudan eşler) — `app/ai/schemas.py` · test `tests/ai/test_schemas.py` · tm 18

_Önceki maddeler: docs/archive/plan-kanit/ (#### K03.1)_
#### K03.2 — 03.2.1–03.2.2 · Sağlayıcı soyutlaması ve Anthropic sağlayıcı
- ✅ 03.2.2 `AnthropicProvider` — Messages API'ye önce base64 sayfa görüntüsü (JPEG/PNG), sonra sayfa metni, `system` talimatı; zorlanmış tek `record_page_analysis` aracı (`input_schema` = `PageAnalysis.model_json_schema()`, düşünme kapalı) ile yapılandırılmış çıktı alınır ve doğrulanmış `PageAnalysis` döner; kesik/ret/araçsız/çok çağrılı yanıt ve şemaya uymayan araç girdisi reddedilir, 429 → `ProviderRateLimitError`, 5xx/529 → `ProviderServerError`, bağlantı/zaman aşımı → `ProviderConnectionError`, SDK yeniden denemesi kapalı (tek HTTP isteği doğrulandı); gerçek SDK istemcisi `httpx2.MockTransport` ile ağsız sınandı, canlı test `live` işaretli ve anahtar yokken atlanır (bu pencerede koşulmadı) — `app/ai/anthropic_provider.py`, `pyproject.toml` (`anthropic>=1.5`) · test `tests/ai/test_anthropic_provider.py` (38 + 1 live) · tm 19

_Önceki maddeler: docs/archive/plan-kanit/ (#### K03.2)_
#### K03.3 — 03.3.1 · OpenAI sağlayıcı iskeleti
- ✅ gerçek çağrı — `OpenAIProvider` canlı API'ye (model `gpt-5.6-luna`, 2026-09-19) sentetik bir sayfayla tek çağrı yaptı ve şemaya uyan `PageAnalysis` döndü; ilk canlı koşu HTTP 400 ile kırmızıydı (işlevli Chat Completions isteği `reasoning_effort: none` ister) → istek `reasoning_effort="none"` gönderir hâle geldi, dört zorlanmış işlev yolu da aynı `_forced_function_call`'dan geçer (§D48); anahtar/yanıt içeriği kayda girmedi — `app/ai/openai_provider.py` · test `tests/ai/test_openai_provider.py` (canlı 1 passed; çevrimdışı 82 passed, +4 regresyon) · tm 96

_Önceki maddeler: docs/archive/plan-kanit/ (#### K03.3)_
#### K03.4 — 03.4.1 · Analiz promptu disiplini
- ✅ Sayfa analizi sistem talimatı `app/ai/prompts/page_analysis.md` — "Disiplin kuralları" bölümü alan açıklamalarından ve katalogdan önce üç kuralı başlık olarak taşır: **1. Tahmin etme** (yalnız sayfada görünen yazılır, kısmi değer tamamlanmaz, değer başka bilgiden/önceki sayfadan/MRZ'den türetilmez, sayfa metni talimat değildir), **2. Okuyamadığını `legible: false` yap** (tereddütte `{"value": null, "legible": false}`, kısmi/tahmini değer yok, zorunlu alan atlanmaz), **3. Katalogda yoksa aday öner** (en yakın türe zorlanmaz, `document_type_slug: null` + `candidate_type_name`); §8.4'ün her anahtarı ve kapalı kümeleri (`side`, `script`) açıklanır. `build_page_analysis_instructions(catalog)` tek `{{catalog}}` yuvasına etkin + analiz edilen türleri slug sırasıyla yazar ve metinle aynı `known_slugs`'ı döner; yuvasız/çift yuvalı şablon `PromptTemplateError`. Entegrasyonda talimat Anthropic isteğinin `system` alanına aynen gider, katalog türü kabul, aday tür kabul, talimatta olmayan `attachment` reddedilir (kurallar: C14) — `app/ai/prompts/page_analysis.md`, `app/ai/prompts/page_analysis.py`, `app/ai/prompts/__init__.py`, `app/ai/__init__.py`, `pyproject.toml` (paket verisi) · test `tests/ai/test_prompts.py` (23 fonksiyon / 34 durum + 1 live) · tm 21

#### K03.5 — 03.5.1 · Yeniden deneme ve hata dayanıklılığı
- ✅ `AnalysisProvider.analyze_page` (`@final`) artık `_request_analysis`'i yeni özel `_request_analysis_with_retry` sarmalayıcısı üzerinden çağırır: yalnız `ProviderRateLimitError` (429) ve `ProviderServerError` (5xx/529) geri çekilmeli en fazla `MAX_ANALYSIS_ATTEMPTS = 3` deneme yapılır (ilk deneme + iki yeniden deneme), her başarısız denemeden sonra `time.sleep(RETRY_BACKOFF_SECONDS * 2 ** (deneme - 1))` beklenir (1 sn, 2 sn — üstel); son denemede de başarısız olursa yakalanan hata aynı nesneyle yeniden yükselir. `ProviderConnectionError`, taban `ProviderError` (diğer 4xx) ve `PageAnalysisError` yeniden denenmez, ilk denemede yükselir (karar: C15). Somut sağlayıcılar değişmedi, hâlâ tek HTTP isteği atar. Anthropic entegrasyonunda hız sınırı/5xx'in tüm alt durumları (429/500/503/504/529) hem "ikinci denemede kurtarma" hem "üç denemede pes etme" senaryolarıyla, 4xx'in kalanı (400/401/403/404/413) tek denemeyle doğrulandı; `httpx2.MockTransport` sıralı yanıt kuyruğu kullanıldı, ağ çağrısı yok. Testte `time.sleep` `tests/ai/conftest.py`'deki `no_sleep` fixture'ıyla (`app.ai.provider.time.sleep` monkeypatch) kaydedilir, gerçekten beklenmez — `app/ai/provider.py` · test `tests/ai/test_provider.py` (44, +6), `tests/ai/test_anthropic_provider.py` (44, +5), `tests/ai/conftest.py` (yeni) · tm 22

#### K03.6 — 03.6.1 · Kayıtlı yanıt sağlayıcısı (test altyapısı)
- ✅ `RecordingProvider` (`app/ai/recording_provider.py`) — `AnalysisProvider`'ı ağsız uygular: `_request_analysis` `tests/fixtures/ai/recordings/<senaryo>/<sıra>.json` dosyasını (`0.json`, `1.json`, ...) ayrıştırmadan okuyup döner, ortak `validate_page_analysis` yanıtı doğrular. `from_directory` dosya adına göre sıralı yükler; kayıttan fazla istek `RecordingExhaustedError`, boş/yok dizin `RecordingNotFoundError`. `PROVIDER_FACTORIES`'e eklenmedi (C16) — test doğrudan `RecordingProvider.from_directory(...)` çağırır. İki sentetik kayıt: `russian_passport/0.json` (tek sayfa), `serbian_residence_card/{0,1}.json` (ön/arka). Kurallar ve gerekçe: C16 — `app/ai/recording_provider.py` · `tests/fixtures/ai/recordings/russian_passport/0.json` · `tests/fixtures/ai/recordings/serbian_residence_card/{0,1}.json` · test `tests/ai/test_recording_provider.py` (8 fonksiyon) · tm 23

#### K03.7 — 03.7.1–03.7.2 · Sayfa analizi çalıştırıcı
- ✅ 03.7.2 Sayfa hatası (`PageAnalysisError` şemaya uymayan kayıt, 3 denemeden sonra `ProviderServerError`, `ProviderConnectionError`, eksik/üretilmemiş/geçersiz sayfa görüntüsü) yalnız o sayfayı `failed` yapar (`analysis_json` boşaltılır, `PAGE_ANALYSIS_FAILED` sağlayıcı/model/hata türü/HTTP durumuyla), kalan sayfalar tamamlanır ve parti `partial` olur; tüm sayfalar başarılıysa parti durumu değişmez; beklenmeyen hata (`RecordingExhaustedError`) yutulmaz, parti `partial` işaretlenmez (09.2.3'e kalır) — `app/pipeline/analyze.py` · test `tests/pipeline/test_analyze.py` · tm 24

_Önceki maddeler: docs/archive/plan-kanit/ (#### K03.7)_
#### K03.8 — 03.8.1, 03.8.2 · Çalışma zamanı yapay zekâ ayarı, model ve efor
- ✅ `ai_settings` tek satır (göç 0033), `app/ai/runtime.py` etkin ayar + kayıt (tek sağlayıcı, anahtarsız sağlayıcı reddi), `app/ai/model_list.py` (kaynak + tarih, efor kümesi, istek biçimi), Anthropic `output_config.effort` + modele göre zorlanmış/auto+strict, OpenAI `reasoning_effort`, panel/bot/işçi yeniden başlatmasız geçiş, olayda `effort` — test `tests/ai/test_ai_settings.py` (11), `tests/ai/test_request_format.py` (15), `tests/db/test_migrations.py` (+1), `tests/db/test_models.py` · tm 188
- ✅ OpenAI Responses API + GPT-6.1 Sol (tm 192, §D127): `app/ai/openai_provider.py` `responses.create` (düz işlev aracı, `reasoning.effort` yalnız seçilince, `max_output_tokens` ≥ 16000, `incomplete`/ret reddi), `app/ai/model_list.py` (Sol `low`–`max`, Luna çıktı), `notes` 250; ölçüm 14 belge: Luna `none` 9/14 + 3 yanlış, Sonnet 5.5 ve Sol `low`/`medium` 11/14 + 0 yanlış; test `tests/ai/test_openai_provider.py` (106) · `tests/ai` + ayar sayfası + config + olay + arayüz standardı + göç 962 geçti · gerçek sağlayıcı sondası Sol `low` + Sonnet (notes 216 kabul) · tm 192

#### K04.1 — 04.1.1, 04.1.2 · Dosya içi gruplama ve ön/arka eşleşmesi
- ✅ Kapı (tm 103): commit içeriğinin birebir kopyası olan geçici çalışma ağacında (insanın commit edilmemiş değişiklikleri dışarıda): ruff check/format, compileall, `coverage run -m pytest -q -m "not live"` (4144 geçti, +72; 5 PG atlandı) + `coverage report --fail-under=70` (%99.88; `schema.py`, `form.py`, `group.py`, `validate.py`, `prompt_builder.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0007), `import app.main` — hepsi exit 0. pytest-cov'lu koşu da bütün testleri geçti ama kapsam dosyasını yeniden adlandırırken WinError 5 ile exit 3 verdi (bu makinenin bilinen sorunu); kapı bu yüzden `coverage run` ile yeniden koşuldu. tm 91'in zamanlamaya bağlı testi (`test_a_repeated_file_is_reported_as_a_duplicate`) yük altındaki, yarıda kesilen ilk koşuda bir kez kırmızı oldu; tek başına üç kez ve sonraki iki tam koşuda yeşil. 10 geçici kural bozmasının 10'u testte kırmızı. Canlı yapay zekâ çağrısı ve gerçek belge yok.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K04.1)_
#### K04.2 — 04.2.1 · Ardışıklık güvenlik kuralı (R6)
- ✅ S3: 6 sayfalık sentetik PDF (ehliyet ön, foto, başka belge, oturum ön, oturum arka, ehliyet arka) gerçek render/metin/boş sayfa adımlarından ve yeni kayıtlı yanıtlarla `analyze_upload` → `group_upload`: adaylar (0'dan sıra) [0] [1] [2] [3, 4] [5]; oturum izni [3, 4] (front, back) ve foto [1] işaretsiz, sayfa 3 ([2]) katalog türünde (`work_permit`) `DOC_TYPE_DETERMINED`, katalog dışı türde `DOC_TYPE_UNKNOWN` ile işaretsiz; ehliyet 1 ve 6 ([0], [5]) birleştirilmez, ikisi de R6 ile Unresolved (karşı parça birbirleri, araya giren [1, 2, 3, 4]) ve olay mesajı gerekçedir; ön ve arka yüz ayrı dosyalardaysa kural uygulanmaz (04.3) — `tests/fixtures/ai/recordings/s3_interleaved_pdf/{0..5}.json` · test `tests/pipeline/test_group.py` · tm 26

_Önceki maddeler: docs/archive/plan-kanit/ (#### K04.2)_
#### K04.3 — 04.3.1, 04.3.2 · Dosyalar arası gruplama ve belirsiz eşleştirmenin reddi
- ✅ S5: aynı partide `on.jpg` (ehliyet ön) ve `arka.jpg` (ehliyet arka) sentetik JPEG, gerçek görüntü analiz kopyası adımından ve yeni kayıtlı yanıtlarla `analyze_upload` → `group_upload`: iki yükleme sırasında da tek `serbian_driving_license` adayı (Driving License, `direct: false`) — sayfalar (on.jpg, 0) front, (arka.jpg, 0) back; dosya adaylarında yüz kalmaz, tek `DOC_TYPE_DETERMINED` olayı ön yüzün dosyasına `sources` ile yazılır, kişisel değer yok. Kayıpsız sarma ve birleştirme (çıktı PDF) 06.2/07.3/07.4'ün işi — `tests/fixtures/ai/recordings/s5_front_back_images/{0,1}.json` · test `tests/pipeline/test_group.py` · tm 27

_Önceki maddeler: docs/archive/plan-kanit/ (#### K04.3)_
#### K04.4 — 04.4.1, 04.4.2 · Zorunlu alan okunaklılık kapısı ve kabul kriteri değerlendirmesi
- ✅ S9: tek sayfalık sentetik PDF gerçek render/metin/boş sayfa adımlarından ve yeni kayıtlı yanıtla (belge numarası `legible: false`, MRZ okunamıyor ve MRZ maddesi notta) `analyze_upload` → `group_upload` → `check_legibility`: `russian_passport` adayı Unreadable, gerekçe tam olarak `Okunamayan alanlar: document_number`; MRZ kabul kriteri ayrıca karşılanmamış olarak nesnede; gerekçelerde kişisel değer yok. Kayıtlı pasaport yanıtı kenar maddesiyle Unresolved, notsuz kabul; S5 dosyalar arası ehliyet kartı ön yüzdeki okumalarla kabul — `tests/fixtures/ai/recordings/s9_blurred_passport/0.json` · test `tests/pipeline/test_legibility.py` · tm 28

_Önceki maddeler: docs/archive/plan-kanit/ (#### K04.4)_
#### K04.5 — 04.5.1 · Beklenen sayfa sayısı kontrolü
- ✅ 04.5.1 dosya içi ve dosyalar arası gruplama bittikten sonra `group_across_files` (`app/pipeline/group.py`, `group_upload` üzerinden) başka bir kuralla (04.2.1/04.3.2) zaten işaretlenmemiş ve katalogda türü belirlenmiş her adayın sayfa sayısını türün `expected_pages` aralığıyla karşılaştırır; dışındaysa `DocumentCandidate.page_count_violation` (`PageCountViolation`: `queue = unresolved`, sayfalar + beklenen aralık, değer taşımayan `reason`) ile Unresolved'a gider — eşleşebilecek karşı yüzü partide hiç olmayan tek ön/arka yüz (04.3.2'nin hüküm vermediği durum) ve bitişik ama araya belge girmemiş eksik parçalar burada yakalanır; aralık tanımsız (`expected_pages: null`), katalog dışı/türü belirlenemeyen aday ya da zaten R6/04.3.2 ile işaretli aday yargılanmaz (iki gerekçe eklenmez). Hüküm adayın `DOC_TYPE_DETERMINED` olayına `page_count_violation` verisi ve `message = reason` olarak yazılır, kişisel değer yok. `group_file_pages` tek başına sayfa sayısıyla bölmez (04.1.2 notu); sınır yalnız `group_across_files`/`group_upload` çıktısında uygulanır — `app/pipeline/group.py` · test `tests/pipeline/test_group.py` (78 fonksiyon / 145 durum, +11 / +13) · tm 29

#### K04.6 — 04.6.1 · Bilinmeyen tür ve aday tür önerisi
- ✅ S14: tek sayfalık sentetik PDF gerçek render/metin/boş sayfa adımlarından ve yeni kayıtlı yanıtla (Peru diploması: slug `null`, `candidate_type_name: "Peruvian Diploma"`) `analyze_upload` → `group_upload`: aday Unknown (slug boş, gerekçede önerilen aday tür), `candidate_document_types`'ta `Peruvian Diploma` (`pending`, `seen_count` 1, örnek sayfa diplomanın sayfası), `DOC_TYPE_UNKNOWN` ardından `CANDIDATE_TYPE_PROPOSED`, `DOC_TYPE_DETERMINED` yok; aynı parti yeniden gruplanınca sayı artmaz, başka partideki iki diploma (başka yazımla) aynı kayıtta 3'e çıkar; tür kataloğa eklenip sayfa yeniden analiz edilince (K18) aday `peruvian_diploma` ile `DOC_TYPE_DETERMINED` alır, Unknown'dan çıkar ve kayıt yeniden sayılmaz. Onay akışı (11.5.2) ve Hazir çıktısı (06–07) sonraki görevlerin — `tests/fixtures/ai/recordings/s14_peruvian_diploma/0.json` · test `tests/pipeline/test_group.py` · tm 30

_Önceki maddeler: docs/archive/plan-kanit/ (#### K04.6)_
#### K04.7 — 04.7.1 · Word/Excel (Attachment) yolu
- ✅ S15: Word CV (`.docx`, gerçek OOXML imzası) bağlam çalışanıyla (profil sayfası benzeri yükleme, 10.5.3) yüklenince attachment aday `unresolved` boş kalır ve olduğu gibi Hazir'a hazır işaretlenir; bağlam çalışanı olmadan (genel yükleme) yüklenince `AttachmentWithoutContext` ile Unresolved'a gider. Legacy Word/Excel (OLE imzası) ve OOXML Excel de aynı `attachment` türüne eşlenir; sayfa tabanlı bir pasaport adayıyla aynı partide birlikte var olabilirler — `tests/fixtures/gen.py` (`make_docx_bytes`, `make_xlsx_bytes`, `make_legacy_doc_bytes`, `make_legacy_xls_bytes`) · test `tests/pipeline/test_group.py` · tm 31

_Önceki maddeler: docs/archive/plan-kanit/ (#### K04.7)_
#### K05.1 — 05.1.1 · İsim normalizasyonu
- ✅ 05.1.1 `normalize_name(*parts)` (`app/matching/names.py`) isim parçalarını §20.2.1 sırasıyla tek eşleştirme anahtarına indirir: Unicode uyumluluk katlaması (NFKD + casefold) ve `Mn`/`Me` işaretlerinin atılması (aksan), Türkçe harfler (`ç ş ğ ı ö ü`) ve ayrışmayan Latin harfleri (`ł ø æ đ þ`…) tabloyla, kesme işaretleri ve görünmez biçim karakterleri kelimeyi bölmeden silinir, diğer noktalama ve çoklu boşluk tek ayırıcı olur, kelimeler alfabetik sıralanıp tek boşlukla birleşir. `José Müller`/`JOSE MULLER`, `IŞIK`/`Işık`/`İŞIK`/`isik`, `O'Brien`/`O´Brien`/`OBRIEN`, `Jean-Pierre Dupont`/`DUPONT<<JEAN<PIERRE`, `Dmitry Vasiliev`/`VASILIEV, DMITRY` ve parça sırası (`("Dmitry", "Vasiliev")`) aynı anahtara iner; farklı isimler (`Yılmaz`/`Yılmazer`, `Ali Ali Veli`/`Ali Veli`, `Ana-Maria`/`Anamaria`) ayrı kalır, anahtar idempotenttir, kelimesiz isim `EmptyNameError` verir. Latin dışı harfler düşürülmez, çeviri 05.2'nin (bkz. C23). 11 kural bozulması (sıralama, Türkçe/Latin tablo, iki kesme işareti silme adımı, `Cf`, çift katlama, `combining` yerine kategori, casefold, boş anahtar, kelime tekrarı) geçici olarak denendi, her biri testte kırmızı — `app/matching/names.py` · test `tests/matching/test_names.py` (14 fonksiyon / 44 durum) · tm 32

#### K05.2 — 05.2.1 · Harf çevirisi
- ✅ 05.2.2 görünüm ve onarım: profil kartı Latin alanında Latin olmayan harf kalırsa "Latin yazım eksik" gösterir (`app/web/routers/employees.py`, `profile.html`); kuyruk profil formu Latin ipucu verir, Latin olmayan adı her adımda 422 ile reddeder (`app/web/routers/queue.py`); liste, plan Çalışan sütunu, kuyruk ve Telegram çalışan kaydının Latin adını gösterir. `python -m app.profiles repair-latin-names [--dry-run]` (`app/profiles/latin_names.py`, `__main__.py`) eski kayıtları tekrar çalıştırılabilir onarır: Latin olmayan yazım boşsa orijinal yazıma taşınır, Latin yazım Latin alias'tan ya da Kiril çevirisinden (dil çalışanın Kiril sayfalarından) bulunur, bulunamazsa alan değişmez; alan başına `EMPLOYEE_FIELD_FILLED` (alan ve kaynak, değer yok), `profil.md` yeniden üretilir, klasör adı değişmez. Yerel veride E0001 (Rusça, ICAO) onarıma uygundur; komut insan tarafından çalıştırılır — test `tests/profiles/test_latin_repair.py` (12), `tests/web/test_profile.py` (+4), `tests/web/test_queue_new_profile.py` (+3), `tests/test_events.py` · tm 106

_Önceki maddeler: docs/archive/plan-kanit/ (#### K05.2)_
#### K05.3 — 05.3.1, 05.3.2, 05.3.3 · MRZ ayrıştırma, kontrol haneleri ve MRZ önceliği
- ✅ 05.3.3 `apply_mrz_priority(analysis, *, today)` MRZ'nin altı alanını `person` ve `fields` okumalarıyla karşılaştırır: aynı anahtara inen görünen yazım olduğu gibi kalır (`00 0000001`, tireli/aksanlı isim, `other_names`'te ayrı okunmuş baba adı, sayfa diliyle çevrilen Ukraynaca Kiril ad); çelişkide MRZ değeri iki yere de yazılır ve `notes`'a `MRZ ile görünen metin çelişiyor, MRZ değeri kullanıldı: <alanlar>.` eklenir (alan adı, kişisel değer yok; analizci notu başta korunur; ikinci uygulama sonucu değiştirmez); okunamayan görünen okuma MRZ'den notsuz doldurulur; MRZ'nin okunamadı saydığı alan görünen okuma okunaklı olsa da `legible: false`. Biçime uymayan MRZ yok sayılır, izinsiz karakterli MRZ kullanılmaz (ikisi de bilgi notuyla), boş/okunamaz sayfanın MRZ'sine güvenilmez; `MrzResolution.allows_clean_document_number` §20.2.3'ün üçüncü koşulunu verir. Entegrasyon: bütün kayıtlı yanıtlardaki MRZ'ler (dört hatalı hanesi düzeltilen `russian_passport` ve S13) geçerli ve görünen metinle çelişmiyor; kayıtlı pasaportun numara hanesi bozulunca 04.4 kapısı `Okunamayan alanlar: document_number` verir, görünen numarası bulanık pasaport geçerli MRZ'den okunup kapıdan geçer. 26 kural bozulması (ağırlık dizisi, dolgu değeri, üç biçimin bileşik aralıkları, TD2 uyruk konumu, dolgu hanesi, doğum yüzyılı sınırı, son geçerlilik yüzyılı, büyük harf, isim ayracı, isimde rakam, MRZ'nin kazanması, geçersiz alanın yazılması, baba adı, numara normalizasyonu, not tekrarı, güvenilmeyen sayfa, geçersiz ve bileşik hanesi tutmayan MRZ'de temiz numara, karışık satır uzunluğu, `<` hanesi, boş numara, uyruk biçimi, görünmeyen okumanın doldurulması, isim dili) geçici olarak denendi, her biri testte kırmızı — `app/matching/mrz.py`, `tests/fixtures/ai/recordings/russian_passport/0.json` · test `tests/matching/test_mrz.py` (50 fonksiyon / 182 durum) · tm 34

_Önceki maddeler: docs/archive/plan-kanit/ (#### K05.3)_
#### K05.4 — 05.4.1 · Kişi anahtarı
- ✅ 05.4.1 `build_person_key(analyses, *, today)` (`app/matching/match.py`) belge adayının sayfa analizlerinden `PersonKey` üretir: belge numaraları (§20.2.1 `normalize_document_number`, tekrarsız, sayfa sırasıyla, numara başına okunaklı `fields` okumasından gelip gelmediği), normalize ad-soyad (`given_names` + `surname`, sayfanın diliyle; `other_names` girmez), doğum tarihi, orijinal yazım (`TransliteratedName` + normalize anahtar), `name_keys`, `mrz_allows_clean_document_number` (§20.2.3 koşul 3, bütün sayfalar) ve sayfalar arası çelişen alanlar (`conflicts`; tekil alan `None` olur). MRZ önce okunur (K6): her sayfaya `apply_mrz_priority` uygulanır ve MRZ'si alanı taşıyan sayfa varsa alan yalnız oradan okunur — arka yüz MRZ'si ön yüzün görünen metnini yener, MRZ'nin taşımadığı alan (hanesi tutmayan numara, `<<`'süz ad) bütün sayfalardan okunur; boş/okunamaz sayfaya güvenilmez, sayfanın okunamadı dediği `person` değeri girmez. Kayıtlı yanıtlar: S13 Kiril pasaportu tam anahtar (`000000013`, `iulia shchelkina testova`, 1992-03-15, `Тестова-Щёлкина Юлья` → `Testova-Shchelkina Iulia`); `group_file_pages` ile gruplanan Sırp oturum kartı ön+arka ve `group_across_files` ile eşlenen S5 ehliyet yüzleri tek anahtar verir. Ukraynaca Kiril parça MRZ yazımıyla aynı anahtara iner, D7 yazımında iki isim anahtarı çıkar, `today` MRZ doğum yüzyılını seçer. 22 kural bozulması (sayfalar arası MRZ önceliği, okunamadı vetosu, güvenilmeyen sayfa, MRZ önceliğinin hiç uygulanmaması, `today`, isim/çeviri dili, `legible` birikimi (iki biçim), çelişkide ilk değer (doğum, orijinal yazım), çelişki eşiği, bayrağın yalnız güvenilir sayfalardan hesaplanması, numara ayırıcı kümesi, büyük harf, boş numara/isim, ISO tarih katılığı, `name_keys` tekrarı, MRZ'nin değer taşıması koşulu, `person` önceliği, tek parçalı ad) geçici olarak denendi, her biri testte kırmızı (kurallar: C26) — `app/matching/match.py` · test `tests/matching/test_person_key.py` (35 fonksiyon / 50 durum) · tm 35

#### K05.5 — 05.5.1, 05.5.2, 05.5.3, 05.5.4 · Çalışan eşleştirme sırası
- ✅ 05.5.4 / S23 (§D109): §20.2.2 satır 5a — numara eşleşmeyen, doğum tarihi okunmamış belgenin adı birleştirilmemiş tek çalışana uyuyorsa `MatchRule.NAME`/`MatchedBy.NAME` (`PERSON_MATCHED`), birden çok kayda uyuyorsa `name_ambiguous` + Unresolved (`PERSON_AMBIGUOUS`), aynı çalışanın iki yazımı tek kayıt — `app/matching/match.py`; planlayıcı Hazir'a `matched_by: name` koyar, pasif çalışanda 10.5.7, kabul edilmemiş belgede kişi tahmini yok, isim eşleşmesi kişisiz sayfaya sahip vermez (`_OWNING_MATCHES`) — `app/pipeline/plan_planner.py`; birikim yok (`accumulate_identity` reddeder, alan/iletişim çağrılmaz, `fill_profile_fields` atlar — `app/profiles/field_fill.py`); "Yalnız isimle eşleşti" etiketi profil belge listesinde ve yükleme ayrıntısının plan/çıktı satırında, İK taşıyınca kalkar (`name_matched_documents`, `app/pipeline/plan_models.py`; üç dil); S10 `dogum-tarihi-farkli` ile kalır · test `tests/test_scenario_s23.py` (5), `tests/matching/test_employee_match.py` (+9), `tests/pipeline/test_plan.py` (+5), `tests/test_scenarios_s06_s10.py` · 5 kural bozmasının 5'i kırmızı · tm 165

_Önceki maddeler: docs/archive/plan-kanit/ (#### K05.5)_
#### K05.6 — 05.6.1, 05.6.2 · Otomatik çalışan oluşturma
- ✅ 05.6.2 satır 6b (§20.2.4): `resolve_unmatched`/`can_create_employee`/`create_employee` temiz numara yokken Latin ad-soyad + türün zorunlu alanı olan, okunaklı (`PersonKey.date_of_birth_legible`), tekil, çelişkisiz, `dob_plausible`'dan geçen doğum tarihiyle çalışanı açar (`UnmatchedResolution.basis`, `CreationBasis`); `employee_identifiers` yazılmaz, `EMPLOYEE_CREATED` verisinde `basis` (`document_number`/`name_dob`); hüküm veritabanında yeniden değerlendirilir, R8 (satır 5) değişmedi; onay 6b anahtarlı eski öneriyi kabul eder (§D59); ön elemede `unverified_date_of_birth` (§C71, §C84) — `app/matching/match.py`, `app/pipeline/plan_planner.py`, `app/pipeline/analyze.py`, `app/pipeline/validate.py` · test `tests/matching/test_name_dob_creation.py` (35), `tests/test_scenario_s19.py` (4, S19), `tests/pipeline/test_prescreen.py` (+4), `tests/pipeline/test_prescreen_matrix.py` (S19 partisi, doğum tarihini yanlış okuyan ucuz model), `tests/matching/test_person_key.py` (+7), 05.6.1/05.7 fixture'ları doğum tarihsiz ya da doğum tarihi zorunlu olmayan türle · tm 110

_Önceki maddeler: docs/archive/plan-kanit/ (#### K05.6)_
#### K05.7 — 05.7.1, 05.7.2, 05.7.3 · Onay bekleyen profil, alias birikimi ve profil alanları
- ✅ 05.7.3 `complete_profile_fields(session, key, *, employee_id, file_id, page_index, document_id=None, actor, created=False)` (`app/matching/fields.py`) satır 1/3 eşleşmesinde `accumulate_identity`'nin yanında ve satır 6 açılışında (`app/pipeline/plan.py`) kişi anahtarının Latin/okunaklı/MRZ-önce değerleriyle boş alanı doldurur, dolu alanı hiç değiştirmez (§20.2.1 normalizasyonuyla aynı → `same`, farklı → `conflict`); yeni tablo `employee_field_observations` (değersiz; çalışan, alan, belgenin ilk kaynak sayfası, sonuç, zaman; bir alan bir kaynaktan bir kez) + göç `0008`; doldurulan her alan için `EMPLOYEE_FIELD_FILLED` (`field`, `source: document`, `rule: 05.7.3`); profil kartı alan başına "Kaynak" bağlantısı ve "<alan>: belgede farklı değer okundu" uyarısı (`app/web/routers/employees.py`, `profile.html`); geçmiş veri `python -m app.profiles fill-fields [--dry-run] [--actor]` (`app/profiles/field_fill.py`, etkin belgeler en eski önce, tekrar çalıştırılabilir) · test `tests/matching/test_profile_fields.py` (16), `tests/profiles/test_field_fill.py` (17), `tests/web/test_profile.py` (+10), `tests/pipeline/test_plan.py` (3 güncellendi), `tests/db/test_migrations.py` (+1), `tests/test_scenarios_s01_s05.py` (S1 zinciri) · tm 107

_Önceki maddeler: docs/archive/plan-kanit/ (#### K05.7)_
#### K05.8 — 05.8.1, 05.8.2, 05.8.3 · İletişim bilgisi, dil ve alfabe kaydı
- ✅ 05.8.3 `employee_aliases.script` artık dolu: `_detect_script(text)` (`app/matching/match.py`) yazımın ilk harfinin Unicode adına bakar (`LATIN`/`CYRILLIC`/`ARABIC` önekiyle başlıyorsa o alfabe, harf varsa ama önek tutmuyorsa `other`, hiç harf yoksa `None`); `create_employee` ve `accumulate_identity` her alias yazarken bunu kullanır. Sayfa kaydının dili ve alfabesi (`pages.analysis_json.language`/`.script`) 03.1.2 ile zaten saklanıyordu — bu görev yalnız çalışan düzeyinde (`employee_aliases`) alfabe bilgisini ekledi ki 09.1 profil üretimi çalışanın belgelerinde görülen alfabeleri listeleyebilsin. İlk harften önceki rakam/noktalama atlanır (`007 BOND` → `latin`), hiç harf yoksa `None` (`007 1990`) — `app/matching/match.py` · test `tests/matching/test_employee_creation.py` (+4: iki alfabe + iki kenar durumu), `tests/matching/test_pending_profile_and_aliases.py` (güncellenen `script` beklentisi) · tm 39

_Önceki maddeler: docs/archive/plan-kanit/ (#### K05.8)_
#### K06.1 — 06.1.1, 06.1.2 · Plan JSON üretimi ve determinizm
- ✅ 06.1.2 `plan_hash` kanonik JSON'un (sıralı anahtar, boşluksuz, UTF-8) SHA-256'sı: geri alınıp aynı analizlerden yeniden üretilen plan ve ayrı veritabanında anahtar sırası değiştirilmiş analizlerden üretilen plan aynı bayt ve hash'i verir, analiz değişince hash değişir; MRZ yüzyılı saat değil partinin alındığı günle seçilir; `read_plan` saklanan planı sözleşme, parti/sürüm/model ve hash ile doğrular (`PlanIntegrityError`); `plan.py` satır+dal kapsamı %100, 22 kural bozulması geçici olarak denendi, her biri testte kırmızı — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` · tm 40

_Önceki maddeler: docs/archive/plan-kanit/ (#### K06.1)_
#### K06.2 — 06.2.1 · İşlem seçimi
- ✅ 06.2.1 `select_operation(sources, *, output_format)` §20.3 karar tablosunu sırayla uygular (ilk uyan satır): tek dosyanın tüm sayfaları aynı biçimde (ya da `keep`) `passthrough` (S1, Word/Excel eki S15), tek PDF'in ardışık alt kümesi — boş sayfa arada ya da dışarıda kalabilir — `extract` (S4, S7, S8), birden çok dosya → PDF `merge` (S5), tek JPEG/PNG → PDF `wrap_image`, tek PDF sayfası → JPEG gömülü tek görüntüde `extract_image`, yoksa `render_image` (gerçek PDF'ten 02.5.1 işaretiyle); uyan satır yoksa `NoApplicableOperation` Unresolved gerekçesi (dosya, sayfa, biçim, kapsama, hedef; kişisel değer yok). Planlayıcı kapsamayı sayfa satırları ∪ `page_count`'la, boş sayfaları gruplamadan, biçimi içerikten okur; seçim yapısal hükümlü adaya uygulanmaz, okunaklılıktan sonra ve çalışan kararından önce yürür (işlemi olmayan belgeden çalışan açılmaz); `hazir` öğede `operation`/hedef zorunlu, kuyruk öğesinde `operation` boş (C31, D15). `plan.py` satır+dal kapsamı %100, 21 kural bozulması geçici olarak denendi, her biri testte kırmızı — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` (109, +42) · tm 41

#### K06.3 — 06.3.1, 06.3.2 · Direkt Belge kuralı
- ✅ 06.3.2 `check_direct_file_types(sources, *, entry)` §20.4.1'i işlem seçiminden önce uygular: Direkt türde içerikten tespit edilen kaynak biçimi `expected_file_types`'ta yoksa (tanınmayan biçim dahil) işlem seçilmez, gerekçe "Direkt Belge: beklenen dosya türü pdf, gelen jpeg. Uygun formatta yeniden gönderin.", rota Unresolved, `DIRECT_DOC_CHECK`. S6: yalnız PDF bekleyen pasaport JPEG geldi → Unresolved, dönüşüm yok, işlem/hedef yok, çalışan açılmaz, kayıtlı çalışan yalnız kişi tahmini; format gerekçesi okunaklılık gerekçesinin ardından gelir ve satır 7'yi keser. `plan.py` satır+dal kapsamı %100, 14 kural bozulması geçici olarak denendi, 13'ü testte kırmızı (kalan eşdeğer: ret varken seçimi taşımak öğeyi değiştirmez) — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` · tm 42

_Önceki maddeler: docs/archive/plan-kanit/ (#### K06.3)_
#### K06.4 — 06.4.1 · Dönüşüm izni kontrolü
- ✅ 06.4.1 `check_conversion(operation, *, entry)` §20.3 satır 3–6'nın işlemlerini (`CONVERSION_OPERATIONS`: `merge`, `wrap_image`, `extract_image`, `render_image`, katalogdaki `Conversion` adları) türün `allowed_conversions`'ında arar; listede yoksa `ConversionNotAllowed` ("Dönüşüm izni yok (06.4.1): <işlem> bu türün izinli dönüşümleri arasında değil (allowed_conversions: merge). Belge dönüştürülmez."), `passthrough`/`extract` boş listede de izinli. Planlayıcı kontrolü Direkt Belge matrisinden sonra uygular, ilk ret keser: izinsiz dönüşüm plana girmez, belge Unresolved'a gider, çalışan açılmaz, kimlik ve iletişim bilgisi birikmez, kayıtlı çalışan kişi tahmini kalır, olay yok (C33). Gerçek dosyalarla: `merge`'e izinli çalışma izni JPEG'i sarılmaz, `wrap_image`'a izinli oturum kartının ayrı yüzleri birleştirilmez, tohum katalogdaki `wrap_image` izni Hazir'a gider; JPEG çıktılı türde gömülü tek görüntülü sayfanın izinsiz `extract_image`'ı `render_image`'a düşmez, görüntüsüz sayfanın `render_image`'ı kendi iznini ister; gerekçe okunaklılık gerekçesinin ardından gelir. `plan.py` satır+dal kapsamı %100, 9 kural bozulması (kontrolün kaldırılması, matrisle sıra, liste ayırıcısı, boş liste yazımı, eksik dönüşüm, `passthrough`/`extract`'ın dönüşüm sayılması, listedekinin reddi, gerekçedeki liste, kuyruk) geçici olarak denendi, her biri testte kırmızı — `app/pipeline/plan.py` · test `tests/pipeline/test_plan.py` (147, +18) · tm 43

#### K06.5 — 06.5.1, 06.5.2 · Doğrulayıcı seti
- ✅ 06.5.1 sekizinci doğrulayıcı `context_person` (10.5.5, PRD 06.5.1 satırına eklendi): yalnız bağlam çalışanlı yüklemede, yapı doğrulamasından geçen adayda; kişi karşılaştırmasının `different` hükmü geçmez → Unresolved, gerekçe uyuşmayan adımı yazar (belge numarası başka çalışanda · doğum tarihi uyuşmuyor · ad uyuşmuyor); bağlamsız partinin öğeleri yedi doğrulamada kalır — `app/pipeline/validate.py` · test `tests/pipeline/test_validate.py` (+6) · tm 108

_Önceki maddeler: docs/archive/plan-kanit/ (#### K06.5)_
#### K06.6 — 06.6.1, 06.6.2 · Yeniden çalıştırma ve yeniden analiz
- ✅ Kapı: 1824 geçti (+21), kapsam %99.72 (`orchestrate.py` ve `uploads.py` %100); 11 kural bozulması (bütünlükten önce olay, durum/parti filtresi, `executed_at`, en eski plan, işaretleme yok, planı sormadan analiz, yeniden planlama, rerun'da sağlayıcı bağımlılığı, commit yok, model) geçici olarak denendi, her biri testte kırmızı · tm 45

_Önceki maddeler: docs/archive/plan-kanit/ (#### K06.6)_
#### K07.1 — 07.1.1 · passthrough işlemi
- ✅ `execute_passthrough(source, destination)` (`app/pipeline/execute.py`) kaynağı `copy_file` ile bayt bayt, atomik olarak hedefe kopyalar (yeniden yazma/yeniden kodlama yok, K10/K11); yayınlanan dosyanın SHA-256'sı kopyadan önce hesaplanan kaynak hash'iyle karşılaştırılır, eşleşmezse `PassthroughIntegrityError` — hedef zaten varsa `copy_file`'ın `FileExistsError`'ı olduğu gibi yükselir (üzerine yazma yok). Yalnız işlemin çekirdeği: çıktı yazma, köken kaydı, `documents`/`OUTPUT_SAVED` ve `Alinan` kopyası 07.7'nindir; işlem seçimi ve izinleri planlayıcının (06.2–06.4), bu görev planı yeniden sormaz. `execute.py` satır+dal kapsamı %100 — `app/pipeline/execute.py` · test `tests/pipeline/test_execute.py` (4) · tm 46

#### K07.2 — 07.2.1 · extract işlemi
- ✅ `execute_extract(source, destination, *, pages)` (`app/pipeline/execute.py`) kaynak PDF'in `PlanSource.pages` sayfalarını pypdf sayfa nesnesi kopyasıyla (`writer.add_page(reader.pages[i])`, `compress_content_streams` yok) yeni PDF'e çıkarır; sayfa render edilmez, içerik akışı ve gömülü görüntü baytları, boyut, `/Rotate` ve sayfa ağacından kalıtılan özellikler aynen taşınır (K3/K11). Doğrulama yayından önce bellekte: çıktı sayfa sayısı `len(pages)` ve her sayfanın MuPDF metin katmanı kaynağındakiyle birebir aynı, değilse `ExtractIntegrityError` ve hedefe yazma yok; geçen çıktı `write_file` ile atomik, üzerine yazma yok. PDF olmayan/bozuk/parolalı kaynak, olmayan sayfa ve okuyucular arası sayfa sayısı farkı `ExtractSourceError`, geçersiz sayfa seçimi `ValueError` (C36). S7 işlem katmanında: 4 sayfalık sentetik PDF'in pasaport sayfası tek sayfa çıkarılır — metin katmanı eşit, içerik akışı ve JPEG ham baytları kaynağınkiyle aynı (render yok); uçtan uca S7 09.3-c'nin. `execute.py` satır+dal kapsamı %100; 11 kural bozulması (sıkıştırma, yeniden sıralama, döndürmeyi içeriğe aktarma, metin/sayfa sayısı/okuyucu uyumu/aralık/tür/negatif/sıra denetimini kaldırma, doğrulamadan önce yayın) geçici olarak denendi, her biri testte kırmızı — `app/pipeline/execute.py` · test `tests/pipeline/test_execute.py` (31, +27) · tm 47

#### K07.3 — 07.3.1 · merge işlemi
- ✅ Kapı: `execute.py` satır+dal kapsamı %100; 16 kural bozulması (Direkt Belge bekçisi, tek kaynak, yol adına göre sıralama, okuduktan sonra sayfa denetimi, sıkıştırma, EXIF'i yok sayma, EXIF'i uygulamama, görüntüyü Pillow ile yeniden kodlama, tür denetimi, sarma hatasını yakalamama, sayfa aralığı, çıktı doğrulaması, okuyucu uyumu, mesajda kaynak konumu, hata sınıfı, metin katmanı denetimi) geçici olarak denendi, her biri yalnız `merge` testleriyle kırmızı · tm 48

_Önceki maddeler: docs/archive/plan-kanit/ (#### K07.3)_
#### K07.4 — 07.4.1 · wrap_image işlemi
- ✅ `execute_wrap_image(source, destination)` (`app/pipeline/execute.py`) kaynak JPEG/PNG'yi `img2pdf.convert()` ile kayıpsız tek sayfalık PDF'e sarar; JPEG akışı yeniden kodlanmadan gömülür, PNG pikselleri kayıpsız taşınır, EXIF yönelimi yalnız `/Rotate`'e yazılır (piksel döndürülmez). Yöntem `merge`'ün görüntü sarma yoluyla ortak çekirdekte (`_wrap_image_to_pdf`) paylaşılır — D17'nin kararı ikisine birden uygulanır. Kaynak JPEG/PNG değilse ya da img2pdf'in yedi hata sınıfından biriyle sarılamıyorsa (açılamayan/bozuk görüntü, aynalı/geçersiz EXIF, >8 bit alfa → `AlphaChannelError`) `WrapImageSourceError`; hedefe hiçbir şey yazılmaz, belge kuyruğa gider (tahmin edilmez). **D18:** §20.5 alfa reddinde beyaz zemine düzleştirmeyi ister; bu bir piksel dönüşümüdür ve K11'in izinli işlemler listesinde yoktur — `MASTER-PROMPT.md` §2 çelişki sırasında (bu dosya > PRD) kilitli kural kazanır, düzleştirme uygulanmadı; >8 bit alfalı PNG de öteki sarılamayan görüntüler gibi `WrapImageSourceError` ile kuyruğa gider. 8 bit alfalı PNG (yaygın durum) img2pdf tarafından zaten reddedilmediği için D17'deki gibi `/SMask` olarak kayıpsız saklanmaya devam eder. `execute.py` satır+dal kapsamı %100 — `app/pipeline/execute.py` · test `tests/pipeline/test_execute.py` (75, +13) · tm 49

#### K07.5 — 07.5.1 · extract_image işlemi
- ✅ Kapı: 13 kural bozulması (ham akış karşılaştırması, uzantı, 02.5.1 kuralı, 8 bit sınırı, PNG piksel denetimi, bayt imzası, gri→RGB kanal denetimi, boyut denetimi, JPEG 2000 reddi, PDF imzası, sayfa aralığı, MuPDF hatası, negatif sayfa) geçici olarak denendi, her biri `extract_image` testleriyle kırmızı · tm 50

_Önceki maddeler: docs/archive/plan-kanit/ (#### K07.5)_
#### K07.6 — 07.6.1 · render_image işlemi
- ✅ `execute_render_image(source, destination, *, page, dpi, jpeg_quality)` (`app/pipeline/execute.py`) gömülü tek görüntü yoksa son çare: `document[page].get_pixmap(dpi=dpi, alpha=False)` ile sayfayı sabit çözünürlükte rasterleştirir, `pixmap.tobytes("jpeg", jpg_quality=jpeg_quality)` ile kayıplı JPEG yazar (§20.5, kabul kriteri). `dpi`/`jpeg_quality` planlayıcı gibi çağırana bırakılan yapılandırma değeridir — görevde sabit yazılmaz; `Settings.render_image_dpi`/`render_image_jpeg_quality` (varsayılan 200/90, `RENDER_IMAGE_DPI`/`RENDER_IMAGE_JPEG_QUALITY`) analiz önbelleğinin (`page_render_*`, 02.1.1) ayarından bağımsız yeni alanlardır (bkz. PLAN.md §C10). Kaynak PDF değilse, açılamıyorsa (bozuk, sahip parolalı açılır ama kullanıcı parolalı `parola korumalı` reddedilir) ya da sayfa kaynakta yoksa `RenderImageSourceError`, hedefe hiçbir şey yazılmaz; negatif sayfa `ValueError`; hedef varsa `write_file`'ın `FileExistsError`'ı. Dosya çok sayfalı olabilir (S3/S4), yalnız planlanan sayfa okunur — iki farklı geometrili sayfa içeren sentetik PDF ile sayfa seçiminin karıştırılmadığı kanıtlandı; DPI/kalite ayarının pikselde ve dosya boyutunda etkisi bağımsız `page.get_pixmap`/dosya boyutu karşılaştırmasıyla doğrulandı. Plan → uygulayıcı: JPEG çıktılı türde gömülü görüntüsü olmayan (02.5.1 işaretsiz) sayfanın `render_image` öğesi planın sayfasını rasterleştirir (`test_planned_render_image_item_yields_a_raster_of_the_planned_page`). `execute.py` satır+dal kapsamı %100 — `app/pipeline/execute.py` · `app/config.py` (`render_image_dpi`, `render_image_jpeg_quality`) · `.env.example` · test `tests/pipeline/test_execute.py` (125, +16) · tm 51

#### K07.7 — 07.7.1, 07.7.2 · Çıktı yazma, köken kaydı ve Alinan kopyası
- ✅ Kapı: 2007 geçti (+58; 4 PG testi atlandı), kapsam %99 (`execute.py`, `received.py`, `layout.py`, `naming.py` %100); 12 kural bozulması (Alinan tekilliği, köken sırası, K10 hash denetimi, PNG uzantısı, advisory kilit koşulu, işlem olayı, beklenen hash, dosyanın partisi, passthrough yayın öncesi hash, `direct` bayrağı, Alinan kopyası, olay sayfası) her biri testte kırmızı · tm 52

_Önceki maddeler: docs/archive/plan-kanit/ (#### K07.7)_
#### K07.8 — 07.8.1 · Uygulayıcı idempotenliği
- ✅ Kapı: 2049 geçti (+42; 4 PG testi atlandı), kapsam %99.71 (`execute.py` %100); 11 kural bozulması (denetimsiz uygulama, benimsemesiz yeniden yazım, kayıtlı dosyayı benimseme, pikepdf yazıcısı, `nodate`'siz sarım, pikepdf+`nodate`, atlama olayı, durum süzgeci, sahip süzgeci, kilitten önce denetim, atlamada kaynak okuma) her biri testte kırmızı · tm 53

_Önceki maddeler: docs/archive/plan-kanit/ (#### K07.8)_
#### K08.1 — 08.1.1, 08.1.2, 08.1.3 · Kuyruğa yönlendirme ve gerekçe dosyası
- ✅ Kapı (tm 140): ruff check/format, compileall, `import app.main`, temiz SQLite'ta `alembic upgrade head` (→0022, göç yok) exit 0; `pytest -q -m "not live" --cov=app` on iki ön plan grubunda 5911 geçti (+22), 5 PG atlandı, `coverage combine` + `report --fail-under=70` exit 0, birleşik kapsam %99 (`execute_pdf.py`, `execute_errors.py`, `route.py`, `orchestrate.py`, `execute.py` %100); 13 geçici kural bozmasının 13'ü kırmızı · tm 140

_Önceki maddeler: docs/archive/plan-kanit/ (#### K08.1)_
#### K08.2 — 08.2.1 · Kuyruk öğesini çalışana atama
- ✅ Kapı: 2097 geçti (+33), kapsam %99.72 (`route.py`, `queue.py`, `execute.py`, `plan.py` %100) — test `tests/pipeline/test_route_assign.py` (25: Unreadable öğe atanınca çıktı + köken + `MANUAL_ASSIGN` ve sağlayıcıya istek yok/analiz ve plan değişmedi, boş sayfalı kartta `extract` (S8), bağlamsız Word eki `passthrough` (S15), `reason.json` işaretlemesi, yeniden yönlendirmede yeni yazım yok, bilinmeyen tür/S6/§20.3 satır 7/tanınmayan biçim/planlamadan sonra Direkt Belge ya da dönüşüm izni değişen katalog/katalogda olmayan tür/işlem hatası/Inbox değişmiş reddi ve hiçbir şey yazılmaması, çözülmüş/çıktısı olan/eski sürüm/plansız/planla uyuşmayan kayıt, değişmiş plan, bilinmeyen öğe/çalışan, boş kullanıcı adı, işlem sınırı çağıranda) · `tests/web/test_queue.py` (8: onaysız 503 ve değişiklik yok, 200 + commit + sağlayıcı kurulmadı, ikinci atama 409, türsüz öğe 409, 404 ×2, 422 ×2); 9 kural bozulması geçici olarak denendi, her biri testte kırmızı · tm 55.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K08.2)_
#### K08.3 — 08.3.1 · Onay bekleyen profili onaylama
- ✅ Kapı: 2131 geçti (+34; 4 PG testi atlandı), kapsam %99.72 (`route.py` satır+dal %100, `match.py` yeni kod %100) — test `tests/pipeline/test_route_approve.py` (19: onay sonrası çalışan + çıktı + köken + iletişim bilgisi + `EMPLOYEE_CREATED`/`OUTPUT_SAVED`/`MANUAL_APPROVE` ve sağlayıcıya istek yok/analiz ve plan değişmedi, boş sayfalı kartta `extract`, aynı kişinin ikinci önerisinin reddi ve yeni çalışana atanması, öneriden sonra kaydedilen kişi, Unreadable ve yalnız isim öğesinin reddi, dönüşüm izni ve Inbox değişikliğinde çalışan açılmaması, analiz yok/başarısız/şemaya uymuyor, işlem hatasında çağıranın geri alması, çözülmüş/yeniden yönlendirilmiş/eski sürüm/bilinmeyen öğe, boş kullanıcı adı ×2, işlem sınırı çağıranda) · `tests/matching/test_profile_approval.py` (15: profilden çalışan, sıradaki E numarası, satır 7 dışı yedi hükmün reddi, ikinci onayın reddi ×2, boş kullanıcı adı ×2, commit yok, kayıtlı yanıtlı pasaport önerisinin onayı); 6 kural bozulması (pending denetimi, yeniden değerlendirme, denetimlerin çalışandan sonra yapılması, iletişim bilgisi, olay türü, `actor`) geçici olarak denendi, her biri testte kırmızı · tm 56

_Önceki maddeler: docs/archive/plan-kanit/ (#### K08.3)_
#### K08.4 — 08.4.1 · Arşive taşıma
- ✅ Kapı: 2143 geçti (+12), kapsam %99.73 (`archive.py`, `queue.py` %100) — test `tests/storage/test_archive.py` (8: arşive taşıma + durum/yol güncellemesi + kaynağın silinmesi + `ARCHIVED` olayı, bulunamayan belge, eski sürüm/zaten arşivlenmiş belgenin reddi ×2, ikinci arşivlemenin reddi, boş kullanıcı adı ×2, işlem sınırı çağıranda) · `tests/web/test_queue.py` (+4: onaysız 503 ve değişiklik yok, 200 + durum/dosya taşınması + olay, ikinci arşivleme 409, bilinmeyen belge 404) · tm 57

_Önceki maddeler: docs/archive/plan-kanit/ (#### K08.4)_
#### K09.1 — 09.1.1, 09.1.2, 09.1.3 · profil.md üretimi
- ✅ Kapı (tm 93): ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2911 geçti, +7; 4 PG testi atlandı), kapsam %99.81, temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0 (kapı `COVERAGE_FILE=.pytest_cache/.coverage` ile koşuldu) · tm 93

_Önceki maddeler: docs/archive/plan-kanit/ (#### K09.1)_
#### K09.2 — 09.2.1, 09.2.2, 09.2.3 · Orkestrasyon ve parti durum makinesi
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2184 geçti, +27; 4 PG testi atlandı), kapsam %99.74 (`orchestrate.py` %100, `uploads.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0; 8 kural bozulması (dış hata metni, geri alma, render reddi, `partial`, profil, geçiş commit'i, skip izi, tekrar dosyası) testte kırmızı · tm 59

_Önceki maddeler: docs/archive/plan-kanit/ (#### K09.2)_
#### K09.3-a — 09.3.1 · Sentetik belge üreteci
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2254 geçti, +70; 4 PG testi atlandı), kapsam %99.74, temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0 · tm 60

_Önceki maddeler: docs/archive/plan-kanit/ (#### K09.3-a)_
#### K09.3-b — 09.3.2 · Kabul senaryoları S1–S5
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2833 geçti, +15; xfail 2 → 0; 4 PG testi atlandı), kapsam %99.80 (`plan.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 9 geçici bozmanın (koşul 1 kişisiz tür, koşul 2 satır 8, aynı dosya, tek çalışan, en az biri Hazir, yalnız satır 1/3, kuyruktaki kişi, belge düzeyi kabul, ikinci geçiş) her biri testte kırmızı · tm 95

_Önceki maddeler: docs/archive/plan-kanit/ (#### K09.3-b)_
#### K09.3-c — 09.3.3 · Kabul senaryoları S6–S10
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2270 geçti, +9; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.78, temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0 · tm 62

_Önceki maddeler: docs/archive/plan-kanit/ (#### K09.3-c)_
#### K09.3-d — 09.3.4 · Kabul senaryoları S11–S15 ve S18
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2283 geçti, +13; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.74, temiz SQLite'ta `alembic upgrade head` (0001→0002, göç yok), `import app.main` — hepsi exit 0 · tm 63

_Önceki maddeler: docs/archive/plan-kanit/ (#### K09.3-d)_
#### K10.1 — 10.1.1, 10.1.2, 10.1.3, 10.1.4, 10.1.5, 10.1.6 · Panel iskeleti, giriş, kullanıcı yönetimi ve ülke verisi
- ✅ 10.1.10 yapay zekâ ayarları yalnız root: `/ai-settings` (sağlayıcı kartı: anahtar tanımlı/tanımsız, tek etkin radyo, model + efor, `.env` notu), tek adımlı kayıt + 422 doğrulama, `AI_SETTINGS_CHANGED` {alan: from/to}, bildirim, root gezinmesinde simgeli bağlantı, İK/Kullanıcı'ya `GET`/`POST`/alt yol bilinmeyen yolla aynı 404, üç dil — `app/web/routers/ai_settings.py`, `app/web/templates/ai_settings.html` · test `tests/web/test_ai_settings_page.py` (19) · kapı 7191 geçti, kapsam %98,73 · tm 189
- ✅ 10.1.11 giriş kaydı: `login_log` (göç 0034; `ts`, `user_id` dizinli; neden yalnız `failed`), `check_login` nedeni iletir (tek hata metni ve 401 aynı, sahte özet korunur), `record_login` savepoint'te (hata girişi engellemez), IP vekil kuralı `client_ip` + `TRUSTED_PROXIES` (compose özel ağlar, Caddy `CF-Connecting-IP`'yi siler), çıkış kaydı; `/access-log/logins` sekmesi (sonuç + kullanıcı süzgeci, 50'lik sayfa, kullanıcı özeti, bilinmeyen adlar tek satır), iki sayfada `nav.tabs`, üç dil — `app/web/auth.py`, `app/web/routers/auth.py`, `app/web/routers/access_log.py`, `app/web/templates/access_log_logins.html` · test `tests/web/test_login_log.py` (14) + `test_migrations` / `test_roles` / `test_production_deployment` ekleri · kapı 7207 geçti, 6 atlandı, %98,73 · tm 190
- ✅ 10.1.12 erişilebilirlik (tm 191): yazı ölçeği 16/13 px, `--target` 40 px, `--muted-ink` ≥ 5:1, `--focus-ring` 3 px, altı çizili metin bağlantısı, `th` normal yazı + zebra, `.text-toggle` → `html[data-text="large"]` %120 (theme-init.js/theme.js, `documania-text`), `a.skip-link` → `#content-start`, `prefers-contrast: more`; üç dil — `app/web/static/panel.css`, `theme.css`, `theme-init.js`, `theme.js`, `templates/base.html`; `tests/web/test_theme.py` (+3). Kapı: ruff check/format, compileall, `import app.main`, `python -m app.i18n check`, `git diff --check` exit 0; `tests/web` + `tests/i18n` yeşil (tam kapı `--cov` koşulmadı: yalnız stil/şablon/betik değişti, insan kuralı).
_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.1)_
#### K10.2 — 10.2.1, 10.2.2 · Yükleme sayfası ve ilerleme görünümü
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2370 geçti, +31; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.74 (`upload_page.py` %100), temiz SQLite'ta `alembic upgrade head`, `import app.main` — hepsi exit 0; 6 geçici kural bozulmasının (boş çalışan dizesi, son durumda yenileme, arka plan işleyicisi, boş adlı parça, `failed` aşama şeridi, başkasının aldığı parti) her biri testte kırmızı

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.2)_
#### K10.3 — 10.3.1, 10.3.2 · Yükleme detay sayfası ve yeniden çalıştır / yeniden analiz
- ✅ Kapı (tm 168): ruff check, ruff format --check, compileall, `import app.main`, temiz SQLite'ta `alembic upgrade head` (→0027), i18n check exit 0; tam paralel kapı (`-n 12 --cov`, dil seçici WIP'i olmayan ayrı worktree'de) 6874 geçti, 5 atlandı, kapsam %99,04, 14 dk 57 sn; 7 geçici kural bozmasının 7'si kırmızı (tek onay, son durum, 9 dk, işleyici failed, tekrar sayımı, silme, hata oranı)

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.3)_
#### K10.4 — 10.4.1, 10.4.2 · Çalışan listesi ve arama
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2465 geçti, +60; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.75 (`employees.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 12 geçici kural bozulmasının (belge sayısı eski/arşiv dahil, tür araması eski sürüm dahil, alias anahtarı yok, LIKE kaçışı yok, terimler VEYA, numara normalize yok, `Vary` yok, geçmiş geri yüklemesi parça alır, sayfa kelepçesi yok, harf duyarlı sıra, tür katlaması yok, terim sınırı yok) her biri testte kırmızı · tm 67

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.4)_
#### K10.5 — 10.5.1, 10.5.4, 10.5.2, 10.5.3 · Çalışan profili sayfası
- ✅ 10.5.13 pasif çalışanı kalıcı silme (tm 167, §D110, §D116): göç `alembic/versions/0026_employee_deletion.py` (`deleted_at`, `deleted_by`, `status` CHECK), çekirdek `app/storage/delete_employee.py` (`plan_employee_deletion`, `delete_employee`, `remove_employee_files`; birlikte planlama `app/storage/delete.py` `plan_documents_files`), kişisel anahtar listesi `app/events.py` `PERSONAL_DATA_KEYS`, `EMPLOYEE_DELETED`, `Operation.DELETE_EMPLOYEE` + §20.6/§20.6.3 satırları (`app/web/confirm.py`, PRD), yollar `app/web/routers/employees.py` (`/employees/{id}/delete/confirm|prepare`, `POST …/delete`, `reject_deleted_employee` → 410 `employee_deleted.html`), görünürlük (`app/matching/match.py`, `records.py`, `status.py`, `edit.py`, `merge.py`, `app/telegram/intent.py`, `handlers.py`, `app/pipeline/route.py`, `orchestrate.py`, `app/storage/move.py`, `app/groups/packages.py`, `app/profiles/render.py`, `app/web/routers/uploads.py`, `queue.py`, `upload_page.py`), README silme bölümü · test `tests/storage/test_delete_employee.py` (12), `tests/web/test_employee_delete.py` (12), `tests/test_scenario_s25.py` (1, S25), `tests/web/test_confirm.py` (+3), `tests/db/test_migrations.py` (+1), `tests/web/test_translation_sweep.py`, `tests/web/test_access_log.py`, `tests/test_events.py`, `tests/matching/test_employee_status.py`, `tests/web/test_profile.py`; tam paralel kapı (`-n 12 --cov`, yalnız bu görevin ağacı) 6821 geçti, 5 atlandı, %99,08 — tek kırmızı `tests/telegram/test_intake.py::test_a_summary_only_counts_its_own_batch` (`pause=0.3` zamanlaması, yeniden koşuda yeşil) · tm 167

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.5)_
#### K10.6 — 10.6.1 · Belge geçmişi görünümü
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2520 geçti, +29; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.76 (`documents.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 9 geçici kural bozulmasının (alınmayan sayfalar da izde, bütün dosya boş liste, dosya bölümü çapası yok, olaylar süzülmemiş, görüntüsüz sayfa bağlantılı, sayfa bağlantısı yanlış partiye, `bool` dosya kimliği kabul, kaynak sırası ters, kayıp çıktıya açma bağlantısı) her biri testte kırmızı · tm 69

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.6)_
#### K10.7-a — 10.7.1 · Kuyruk ekranları ve öğe detayı
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2542 geçti, +22; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.77 (`queue.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 8 geçici kural bozulmasının (bekleyen güncel plana bakmıyor, çözülen süzgeci ters, plansız öğe eski sürüm sayılmıyor, sayfa sınırı yok, olaylar öğeye süzülmemiş, bekleyen sırası ters, sayaç seçili durumdan okunuyor, güncel plan yönü ters) her biri testte kırmızı. Tarayıcıda çizim görülmedi (yalnız `TestClient`) · tm 70

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.7-a)_
#### K10.7-b — 10.7.2 · Kuyruktan çalışana atama
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2569 geçti, +27; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.77 (`queue.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 6 geçici kural bozulmasının (belirteç denetlenmiyor, birinci metin değişik, belirteç çalışana bağlı değil, türsüz öğe reddedilmiyor, `USER_CONFIRMED` yazılmıyor, eski sürüm reddedilmiyor) her biri testte kırmızı · tm 71

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.7-b)_
#### K10.7-c — 10.7.3 · Kuyruktan profil oluşturma
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2623 geçti, +54; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.78 (`queue.py`, `match.py`, `route.py` %100), temiz SQLite'ta `alembic upgrade head` (göç yok), `import app.main` — hepsi exit 0; 7 geçici kural bozulmasının her biri testte kırmızı · tm 72

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.7-c)_
#### K10.7-d — 10.7.4, 10.3.5 · Kuyruk öğesini kapatma ve yeniden açma; yoksanan partiyi geri alma
- ✅ Kapı (tm 131): ruff check/format, compileall, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0019) exit 0; `pytest -q -m "not live" --cov=app` sekiz ön plan grubunda 5691 geçti (+62), 5 PG atlandı, `coverage report --fail-under=70` exit 0, birleşik kapsam %99 (`queue_close.py`, `queue.py`, `confirm.py` %100); 8 geçici kural bozmasının 8'i kırmızı · tm 131

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.7-d)_
#### K10.8 — 10.8.1, 10.8.2 · İki aşamalı onay ve manuel taşıma
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2691 geçti, +68; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.79 (`confirm.py`, `move.py`, `documents.py`, `queue.py`, `upload_page.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004), `import app.main` — hepsi exit 0; 12 geçici kural bozulmasının (tek kullanımlık değil, oturuma/hedefe bağlı değil, süre denetimi yok, metin birebir değil, taşımada belirteç denetimi yok, eski dosya silinmiyor, profiller güncellenmiyor, Alinan kopyası yok, etkin olmayan belge taşınıyor, API arşivi belirteçsiz, hazırlık belirteci saklamıyor) her biri testte kırmızı · tm 73

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.8)_
#### K10.9 — 10.9.1, 10.9.2 · İçerik düzenleme yokluğu ve erişim logu
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (2712 geçti, +21; 2 beklenen xfail D12; 4 PG testi atlandı), kapsam %99.79 (`access.py`, `employees.py`, `documents.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 5 geçici kural bozulmasının (indirme `view` yazılıyor, log hiç yazılmıyor, kullanıcı sabit, PUT yolu, `contenteditable`) her biri testte kırmızı · tm 74

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.9)_
#### K11.1 — 11.1.1, 11.1.2, 11.1.3, 11.1.4, 11.1.5 · Katalog yönetim ekranı
- ✅ 11.1.4/11.1.7 tablo yerleşimi (tm 145, §D83): `app/web/static/panel.css` Belge Türleri bloğu (oranlar, `.catalog.catalog-types` yazı ve iç boşluk, `.catalog-types .country` ve `.doc-actions` satır kırar), `app/web/templates/catalog.html` "Yüz" hücresinden `cell-nowrap` kalktı · test `tests/web/test_catalog_page.py` (+2: hücreler satır kırar, Yüz kırar/Durum kırmaz; sütun testi on sütun/%100 hâlâ yeşil) · ölçüm: 415 satır, 1280/1440 px taşma 0, çakışma 0, işlem bağlantısı alt satıra inmedi · `pytest -q -m "not live" --cov=app` sekiz paralel grupta 6337 geçti, 6 atlandı, 0 kırmızı, `coverage combine` + `report --fail-under=70` exit 0, birleşik kapsam %99 · tm 145

- ✅ 11.1.8 Belge Türleri'nde arama (tm 198, §D133): `app/web/routers/catalog.py` (`q` ≤100, `_search_key` Türkçe ı/İ + casefold + aksan atma + noktalama boşluk, ad/dosya etiketi/slug alt dize, `_filter_types` ülke ile AND; `q` `_list_url`/`_redirect`/`_country_suffix`, toplu işlem, tekil etkinleştir/pasifleştir/arşiv/geri al ve tür formunda `list_q` ile taşınır), `catalog.html` (ülke seçiminin yanında etiketli `type=search` + "Ara", sonuç satırında "Temizle", "Eşleşen tür yok."; htmx kalıbı aynı), `catalog_archive_step.html`, `catalog_form.html`, en/sr çeviri · test `tests/web/test_catalog_search.py` (21) · tm 198
- ✅ 11.1.9 reddedilen adayı kalıcı silme (tm 199, §D134): `app/db/models.py` `delete_rejected_candidate_type` (koşullu silme, yalnız `rejected`), `app/catalog/candidates.py` `delete_candidate_type` (`CANDIDATE_TYPE_DELETED` {aday, ad, görülme}), `app/web/routers/catalog.py` `…/delete/confirm|prepare|delete` (yazma yetkisi; belirteç aday + görülme sayısına bağlı, `Operation.CANDIDATE_DELETE`; bekleyen/onaylı 409), `catalog_candidates.html` Reddedilenler'de "Geri al" yanında `button.danger` "Sil", `catalog_candidate_step.html` onay adımı, en/sr · test `tests/web/test_candidate_delete.py` (6), `test_access_log.py`, `test_roles.py`, `test_translation_sweep.py`, `tests/test_events.py` · tm 199

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.1)_
#### K11.2 — 11.2.1 · Örnek belge yükleme
- ✅ 11.2.1 sahip parolalı PDF örnek olarak kabul edilir ve bayt bayt saklanır, açma parolalı reddedilir; eğitim yerleştirmesi sayfa sayar (tm 137, §D76): `app/storage/examples.py` `_is_readable`, `app/training/placement.py` `_page_count` → `count_pdf_pages` · test `tests/storage/test_examples.py` (+2), `tests/catalog/test_describe.py` (+1) · tm 137

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.2)_
#### K11.3 — 11.3.1 · Tür açıklaması üretimi
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3130 geçti, +118; 4 PG testi atlandı; suite iki ön plan koşusuna bölündü — `tests/web` ve geri kalanı, kapsam `--cov-append` ile birleşti), kapsam %99.85 (`type_description.py`, `describe.py`, `provider.py`, `anthropic_provider.py`, `openai_provider.py`, `recording_provider.py`, `render.py`, `routers/catalog.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 10 geçici kural bozmasının her biri testte kırmızı; 10.9.1 kilidine (`tests/web/test_access_log.py`) bir yeni POST yolu eklendi · tm 77

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.3)_
#### K11.4 — 11.4.1, 11.4.2, 11.4.3 · Prompt derleyici ve token bütçesi
- ✅ Kapı (tm 121): ruff check/format, compileall, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (0001→0013, göç yok) exit 0; `coverage run -p -m pytest -q -m "not live"` dört ön plan grubunda 5265 geçti (+31), 5 PG testi atlandı; `coverage report --fail-under=70` %99

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.4)_
#### K11.5 — 11.5.1, 11.5.2, 11.5.3, 11.5.4, 11.5.5, 11.5.6 · Aday tür akışı ve onay
- ✅ 11.5.7 reddedilen adayı geri alma: `app/db/models.py` `reopen_rejected_candidate_type` (koşullu güncelleme, yalnız `rejected` → `pending`), `app/catalog/candidates.py` `restore_candidate_type` (`CANDIDATE_TYPE_RESTORED` {candidate_type_id, candidate_type_name} kullanıcı adıyla; bekleyen/onaylanmış `CandidateNotRejectedError` → 409), panel `GET /document-types/candidate-types?status=rejected` (liste sayfasında "Bekleyenler · Reddedilenler" sekmeleri, satırda "Geri al"), `POST …/candidate-types/{id}/restore` tek adım, aday detayında "Retten geri al" — §C92-b, §D72 · test `tests/web/test_candidate_types_page.py` (+3), `tests/catalog/test_archive.py` · tm 132

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.5)_
#### K11.6 — 11.6.1 · Profil fotoğrafı kural seti
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3198 geçti, +68; 4 PG testi atlandı; suite iki ön plan koşusuna bölündü — `tests/web` hariç 2651 ve `tests/web` 547, kapsam `--cov-append` ile birleşti), kapsam %99.85 (`photo_rules.py`, `manage.py`, `routers/catalog.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0004, göç yok), `import app.main` — hepsi exit 0; 10.9.1 kilidine (`tests/web/test_access_log.py`) bir yeni POST yolu eklendi; 9 geçici kural bozmasının (baş örtüsü varsayılan açık, piksel üst sınırı yok, bir kural hep açık, tür formu kuralı eziyor, `set_photo_rules` ve router'da tür denetimi yok, commit yok, işaret kutusu ters, kapalı kural da sorulur) her biri testte kırmızı · tm 80

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.6)_
#### K11.7 — 11.7.1, 11.7.2 · Profil fotoğrafı görsel kontrolü
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3287 geçti, +89; 4 PG testi atlandı; iki ön plan koşusu — `tests/web` hariç 2740 ve `tests/web` 547, kapsam `--cov-append` ile birleşti), kapsam %99.86 (yeni/değişen modüller %100), temiz SQLite'ta `alembic upgrade head` (0001→0005), `import app.main` — hepsi exit 0; kapıdan sonra eklenen bir parametre (başarısız yeniden analiz saklı kontrolü boşaltır) ayrıca yeşil; 16 geçici kural bozmasının (unsure fail sayılır, değerlendirilmeyen kural geçer, kapalı kural okunur, hüküm plana girmez, tür süzgeci yok, kontrol çağrılmaz, sınır `>`, kontrol hatası yutulur, hata kaydı boşaltmaz, boş sayfa sorulur, çözünürlük yapay zekâya sorulur, EXIF yönelimi yok sayılır, render sayfası ölçülmüş sayılır, sorulmayan/eksik kural kabul edilir, kuralı kapalı tür sorulur) her biri testte kırmızı · tm 81

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.7)_
#### K11.8 — 11.8.1 · Fotoğraf örneklerinden öğrenme
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3354 geçti; 4 PG testi atlandı; iki ön plan koşusu — `tests/web` hariç 2799 ve `tests/web` 555, kapsam `--cov-append` ile birleşti), kapsam %99.86 (`describe.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0005, göç yok), `import app.main` — hepsi exit 0; 15 geçici kural bozmasının (unsure kabul, değerlendirilmemiş kural kabul, kontrolsüz sayfa kabul, durum süzgeci yok, eskiden yeniye, açık kural yokken hepsi, tür süzgeci yok, sınır ayrılmaz, fotoğraf olmayan türe fotoğraf, fotoğraf olmayan türde tanım kabul, tanım metne girmez, "Fotoğraf türü" satırı yok, atlanan sınırı tüketir, rota fotoğrafları vermez, düğme yalnız örnekle) her biri testte kırmızı · tm 82

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.8)_
#### K11.9 — 11.9.1, 11.9.2, 11.9.3, 11.9.4, 11.9.5, 11.9.6, 11.9.7, 11.9.8, 11.9.9 · Eğitim modu
- ✅ Örnek önizlemeleri (tm 195, §D130): `app/storage/previews.py` (320/1280 px JPEG, PDF ilk sayfa `render_pdf_images`, piksel sınırı + bomba uyarısı hata, EXIF/ICC yok, atomik, ad+boyut+mtime anahtarı, `warm_previews`), `DataLayout.preview_path` (`cache/previews/<slug>/`), `app/web/previews.py` (`?v=` güncelse `private, max-age=31536000, immutable`, ETag/304, `nosniff`; yer tutucu `no-store`; orijinal `attachment`), eğitim + katalog `…/previews/{small|large}/{ad}` uçları, iki şablonda küçük resim + büyük önizleme + İndir, `python -m app.training previews`, `backup.sh` `cache/previews`'ı hariç tutar · test `tests/storage/test_previews.py` (13), `tests/web/test_example_previews.py` (19), `tests/scripts/test_backup_material.py` (+1) · kapı: ruff, compileall, `import app.main`, temiz SQLite `alembic upgrade head`, i18n check; tests/web+storage+scripts+i18n+training (-n 6) yeşil; tam `--cov` koşulmadı (insan kuralı)
- ✅ Önizleme ön yükleme (tm 196, §D131): `app/web/static/preview-prefetch.js` (girişli `base.html`'de `defer`; boşta küçükler, `data-preview-large` sayfa büyükleri önde, 2 işçi + 150 ms, `priority: "low"`, `pointerdown`/`htmx:beforeRequest`/`pagehide` ile `AbortController` iptali, gizli sekme/saveData/2g'de durur, 429/503 `Retry-After` üstel ≤60 sn, `localStorage` yalnız sürüm, `sessionStorage` yalnız sürüm:sıra), `GET /previews/thumbs` (`app/web/routers/previews.py`; oturum + rol kapısı, sayfa ≤200, sayısal imleç, liste sürümü, oturum başına 30/dk → 429), `ensure_preview` en çok 2 üretim + önizleme başına tek üretim kilidi, ön yükleme işaretli istek yer bulamazsa `503 Retry-After: 2`, yükleme sayfa görüntüsü `private, max-age=900` + ETag/304, çıkışta `Clear-Site-Data: "cache"`, ARAYUZ-STANDARDI betik özniteliği · test `tests/web/test_preview_prefetch.py` (16), `tests/storage/test_previews.py` (+3), `tests/web/test_upload_detail.py` (+başlık/304), `tests/web/test_country_language.py` (betik), `tests/web/test_translation_sweep.py` (NOT_HTML) · kapı: tests/web+storage+scripts+i18n+training (-n 6) 2431 geçti · headless Chrome + CDP ağ günlüğü: en çok 2 eşzamanlı, orijinale istek yok, ikinci açılışta yalnız liste ucu + sayfa büyükleri, tıklamada etkin istekler iptal · tm 196
- ✅ Genel önizleme katmanı (tm 197, §D132): `PreviewSource` + `ensure_source_preview` (`app/storage/previews.py`; istenen PDF sayfası tek başına `render_pdf_page_image`, en çok 20 sayfa, `cache/previews/<kaynak-turu>/` `DataLayout.source_preview_path`), `source_preview_response` kademe 1 `immutable` / kademe 2 `private, max-age=900` + ETag/304 (`app/web/previews.py`), uçlar: çalışan belgesi `…/documents/<id>/previews/{small|large}?page=` + önizleme sayfası `…/preview` (`view` kaydı, JPEG'ler kayıt yazmaz), fotoğraf, yükleme sayfası (orijinalden; yükleme/kuyruk/geçmiş/aday örnekleri), üretilen belge, şablon sayfası; `document_preview.html`, `.doc-thumb`/`.preview-pages`; arayüz `/file`'a bağlanmaz · test `tests/storage/test_source_previews.py` (7), `tests/web/test_document_previews.py` (8), `tests/web/test_outputs.py` (+1), güncellenen 12 web testi · kapı: ruff, compileall, `import app.main`, temiz SQLite `alembic upgrade head`, i18n check; tests/web+storage+scripts+i18n+training+pipeline (-n 6) 3596 geçti; tam `--cov` koşulmadı (insan kuralı)

_Önceki maddeler: docs/archive/plan-kanit/ (#### K11.9)_
#### K12.1 — 12.1 · Bot iskeleti ve beyaz liste
- ✅ Kapı (tm 161): ruff check/format (432 dosya), compileall, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0024, göç yok), `python -m app.i18n check` exit 0; `pytest -q -m "not live" --cov=app` yedi ön plan grubunda 6644 geçti, 11 atlandı, 0 kırmızı, `coverage report --fail-under=70` %99; 8 geçici kural bozmasının 8'i kırmızı.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K12.1)_
#### K12.2 — 12.2.1, 12.2.2, 12.2.3 · Telegram üzerinden belge alma
- ✅ Kapı (tm 173): ruff check, ruff format --check (460), compileall, `import app.main`, temiz SQLite'ta `alembic upgrade head` (→0028), `git diff --check` exit 0; tam paralel kapı (`-n 12 --dist worksteal --cov=app`) art arda iki koşu: 6919 geçti, 5 atlandı (PostgreSQL), %99,02, exit 0 (14 dk 49 sn ve 14 dk 47 sn) · tm 173

_Önceki maddeler: docs/archive/plan-kanit/ (#### K12.2)_
#### K12.3 — 12.3.1, 12.3.2, 12.3.3 · Doğal dil belge istekleri
- ✅ 12.3.8 profil sorusu ve karşılaştırma, 12.3.9 tek kişilik dışa aktarım ve toplu reddi (tm 165, §D110): `app/ai/profile_answer.py`, `app/ai/prompts/profile_answer.md`, sağlayıcılarda `_request_profile_answer`, `app/telegram/intent.py` (`AskProfiles`, `_compare`, `export_documents`, `build_profile_prompt`) · test `tests/telegram/test_bot_conversation.py` (+14) · tm 165

_Önceki maddeler: docs/archive/plan-kanit/ (#### K12.3)_
#### K12.4 — 12.4.1 · Kuyruk ve hata bildirimleri
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3587 geçti, +31; 4 PG testi atlandı; üç ön plan koşusu — `tests/web` hariç 3032, `tests/web` ilk 10 dosya 218, kalan 11 dosya 337; `COVERAGE_FILE=.pytest_cache/.coverage`, sonrakiler `--cov-append`), kapsam %99.87 (`notify.py` ve `bot.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0005, göç yok), `import app.main` — hepsi exit 0 (`docker compose config` gerekmedi: compose değişmedi); 20 geçici kural bozmasının (kuyruk/hata türü düşer, tekilleştirme yok, başlangıç noktası yok, pencere yok, `allowed` süzgeci yok, gruplama yok, alıcı yokken olay tüketilmez, bellek budanmaz, durdurma iptal etmez, hata metni mesaja girer, 10 satır sınırı yok, gerekçe kısaltılmaz, aşama etiketi yok, döngü hatada ölür, hata metni loga yazılır, gönderim hatası ötekileri durdurur, ikinci başlatma, oluşturucu kancaları düşer) her biri testte kırmızı; ilk turda sağ kalan iki bozmadan biri (bellek budaması) için test eklendi, öteki (ulaşılamaz mesaj sınırı) ölü kod çıktığı için silindi. Canlı Telegram çağrısı yok.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K12.4)_
#### K13.1 — 13.1.1 · Maliyet ölçümü ve görünürlüğü
- ⛔ 13.1.1 maliyet ölçümü ve paneli kaldırıldı (tm 146, §D84, insan kararı 2026-10-01): silinenler `app/ai/usage.py`, `app/ai/pricing.py`, `app/ai/model_prices.yaml`, `app/web/routers/metrics.py`, `metrics.html`, `metrics_upload.html`, `_prices.html`, `Settings.ai_model_prices`; sağlayıcılarda token bildirimi, olaylarda `usage`/`usage_by_model`/`catalog_tokens` ve `run_idle_unit` geri çağrılarında `meter` kalktı; `ai_call_event_data` yalnız `provider` ve `model` yazar · silinen testler `tests/ai/test_usage.py`, `tests/ai/test_pricing.py`, `tests/web/test_metrics.py`, `tests/pipeline/test_analyze_usage.py`; uyarlananlar sağlayıcı, ön eleme, katalog inceleme, eğitim sınıflandırma, boş-zaman ve ayar testleri · `pytest -q -m "not live" --cov=app` sekiz paralel grupta 6160 geçti, 6 atlandı, 0 kırmızı, `coverage combine` + `report --fail-under=70` exit 0, birleşik kapsam %99 · tm 146

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.1)_
#### K13.2 — 13.2.1, 13.2.2 · Ucuz model ön eleme ve metin katmanı önceliği
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3725 geçti, +71; 4 PG testi atlandı; üç ön plan koşusu — `tests/web` hariç 3144, `tests/web` ilk 11 dosya 247, kalan 11 dosya 334; `COVERAGE_FILE=.pytest_cache/.coverage`, sonrakiler `--cov-append`; ardından eklenen tek test `test_metrics.py` ile ayrıca 27/27), kapsam %99.87, temiz SQLite'ta `alembic upgrade head` (0001→0005, göç yok), `import app.main` — hepsi exit 0. 25 geçici kural bozmasının (kimlik/not/zorunlu alan/boş/okunamaz/tür/MRZ çelişkisi ve hanesi denetimi, her ucuz yanıtı kabul, ucuz hatası sayfayı düşürür, yeniden analizde ön eleme, fotoğraf kontrolü ucuz modelle, olay modeli, model dağılımı ve payı, metrik dağılımı ve toplam denetimi, metin katmanı sınırı/büyütme/ayar bağı, sağlayıcı kopyası ve ayarları, aynı model, talimat zorunlu alanları) her biri testte kırmızı; ilk turda hayatta kalan tek bozma (bileşik MRZ hanesi) için test eklendi. Gerçek sağlayıcı çağrısı yok.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.2)_
#### K13.3 — 13.3.1 · Kalıcı işçi kuyruğu
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3808 geçti, +82; 5 PG testi atlandı; üç ön plan koşusu — `tests/web` hariç 3223, `tests/web` ilk 11 dosya 247, kalan 11 dosya 338; `COVERAGE_FILE=.pytest_cache/.coverage`, sonrakiler `--cov-append`), kapsam %99.87 (`runner.py`, `orchestrate.py`, `uploads.py`, `upload_page.py`, `handlers.py`, `main.py`, `config.py` %100; `queue.py` %99), temiz SQLite'ta `alembic upgrade head` (0001→0006), `import app.main` — hepsi exit 0 (`docker compose config` gerekmedi: compose değişmedi); 25 geçici kural bozmasının (yürütmede yeniden planlama, `partial` yok sayılır, iş açılmaz, kirası dolan alınmaz, deneme sınırı yok, bayat sahiplik, iş bitirilmez, geri çekilme hata sayılır, kalp atışı boş, açılışta döngü yok, bot işi almaz, bot işi geri koymaz, vazgeçmede parti kalır, göç bitmiş partilere iş açar, çalışan iş yeniden alınır, deneme sayılmaz, kanca kirayı yenilemez, kira kaybı yakalanmaz, döngü vazgeçmez, bitmiş partinin işi bitirilmez, web arka plan işi kuyruğu atlar, ara durum sürdürülmez, geri koyma sahibi silmez, hata kaydı kancasız) her biri testte kırmızı; ilk turda hayatta kalan tek bozma (bayat sahiplik) için test, iş nesnesini oturumda tutacak biçimde güçlendirildi. Gerçek sağlayıcı çağrısı yok.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.3)_
#### K13.4 — 13.4.1, 13.4.2 · Erişim logu görünümü, yedekleme ve geri yükleme
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3852 geçti, +44; 5 PG testi atlandı; üç ön plan koşusu — `tests/web` hariç 3250, `tests/web` ilk 11 dosya 235, kalan 12 dosya 367; `COVERAGE_FILE=.pytest_cache/.coverage`, sonrakiler `--cov-append`), kapsam %99 (`access_log.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0006, göç yok), `import app.main` — hepsi exit 0 (`docker compose config` gerekmedi: compose ve Dockerfile değişmedi); 9 geçici kural bozmasının (erişim sırası ters, kullanıcı özeti yalnız indirme sayar, sayfa boyutu taşar, yedek canlı db'yi ham kopyalar, restore arşiv özetini denetlemez, restore dolu hedefi reddetmez, `--force` mevcut veriyi siler, budama yedek dışı dosyaları da siler, parola komut satırına konur) her biri testte kırmızı. Gerçek sağlayıcı, Telegram ya da uzak sunucu çağrısı yok.
- ✅ Eğitim malzemesi ayrı (tm 194, §D129): Compose `known_examples` + `known_training` hacimleri, `backup.sh` malzemeyi arşivden çıkarır (`material=excluded`, `BACKUP_INCLUDE_MATERIAL`), `scripts/backup-material.sh` (rsync, artımlı, `--delete` yok, `--restore`) · test `tests/scripts/test_backup_material.py` (8; rsync'li 4'ü rsync yoksa atlanır), `tests/deploy` · tests/scripts + tests/deploy 76 geçti · YanPC geçişi yapılmadı · tm 194

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.4)_
#### K13.5 — 13.5.1 · Üretim dağıtımı
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3890 geçti, +38; 5 PG testi atlandı; üç ön plan koşusu — `tests/web` hariç 3288 (`tests/telegram/test_intake.py::test_a_repeated_file_is_reported_as_a_duplicate` ilk koşuda yük altında kırmızıydı, tek başına 3/3 ve `tests/telegram` bütün olarak 177 yeşil), `tests/web` ilk 11 dosya 235, kalan 12 dosya 367; `COVERAGE_FILE=.pytest_cache/.coverage`, sonrakiler `--cov-append`), kapsam %99.87 (uygulama kodu değişmedi), temiz SQLite'ta `alembic upgrade head` (0001→0006, göç yok), `import app.main`, `docker compose config` (geliştirme + `--profile production`) — hepsi exit 0; 17 geçici kural bozmasının (panel/db dışarıya açık, sabit parola, `preflight` `APP_ENV`/URL denetimi yok, `app` göçü beklemiyor, `db` profilsiz, Caddyfile salt-okunur değil, sertifika hacmi yok, bot yalnız loopback dinler, alan adı koda yazılı, `Server` başlığı açık, webhook yolu yok, HTTPS kapalı, imajda göç yok, üretim ayarı `.env.example`'da açık, README'de tek komut yok) her biri testte kırmızı. Gerçek sağlayıcı, Telegram ya da uzak sunucu çağrısı yok.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.5)_
#### K13.6 — 13.6.1 · İzleme ve uyarılar
- ✅ Kapı: ruff check/format, compileall, `pytest -q -m "not live" --cov=app --cov-fail-under=70` (3936 geçti, +46; 5 PG testi atlandı; üç ön plan koşusu — `tests/web` hariç 3334, `tests/web` ilk 12 dosya 264, kalan 11 dosya 338; `COVERAGE_FILE=.pytest_cache/.coverage`, sonrakiler `--cov-append`), kapsam %99 (`monitor.py`, `notify.py`, `bot.py`, `runner.py`, `config.py` %100), temiz SQLite'ta `alembic upgrade head` (0001→0006, göç yok), `import app.main` — hepsi exit 0; Compose ve Dockerfile değişmedi (`docker compose config` gerekmedi); 14 geçici kural bozmasının her biri testte kırmızı (eşik `>`, giderme oranı, olay türü süzgeci, pencere, eski plan öğesi, canlı işleyicideki iş, `df` formülü, hatırlatma, ölçüm aralığı, alıcısız ölçüm, mesajın düşmesi, `Worker`'da ölçümün kalkması, hata metninin loga yazılması, botta izleyicinin kalkması). **Gerçek Telegram çağrısı ve gerçek dolu disk yok.**

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.6)_
#### K13.5-b — 13.5.2, 13.7.1 · APP-worker ayrımı ve büyük çekirdek modüller
- ✅ Kapı: `ruff check .`, `ruff format --check .` (294 dosya), `compileall -q app`, `import app.main`, temiz SQLite `alembic upgrade head` (0001→0009), Compose varsayılan + production profili `config`, `docker compose build app worker` ve final image'da `python -m app.profiles --help` + worker entrypoint/startup gate import smoke testleri başarılı. Son tamamlanmış ana suite (yedekleme dosyası hariç): 4432 geçti, 5 atlandı, 3 deselected (451.16s); `pytest tests/scripts/test_backup_restore.py -q --tb=short`: 24 geçti. Windows Git Bash `/c/...` staging yolu native Python'a çevrilmediği için görülen SQLite `/tmp` erişim hatası düzeltildi: `backup-lib.sh` `native_path()` ile Python'a verilen yolları `cygpath -m` üzerinden dönüştürüyor; Linux'ta no-op. Windows test fixture'ı geçici staging'i kendi fixture alanına yönlendiriyor. Düzeltme sonrası tüm-suite denemesi araç zaman aşımına uğradı; sonuç iddia edilmiyor. Ruff check/format, compileall, `git diff --check`, APP/worker image build başarılı. Kullanıcı kapsamı yerel çalışma olarak netleştirdi: production deploy yapılmıyor; Docker Compose config + APP/worker build + image smoke testleri başarılı. `run --rm` smoke testleri sonrası boş `belgeee_data` volume'u silindi; uzun çalışan Compose servisleri başlatılmadı.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.5-b)_
#### K14.1 — 14.1.1, 14.1.2 · Belge grupları: tablolar, sekme, grup ve kalem yönetimi
- ✅ Kapı: ruff check/format (350 dosya), compileall, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (0013→0014) exit 0; `pytest -q -m "not live" --cov=app` sekiz ön plan grubunda 5353 geçti (+64), 5 PG testi atlandı; `COVERAGE_FILE` ile birleşik kapsam %99 (`app/groups` ve `routers/groups.py` %100). 11 geçici kural bozmasının 11'i kırmızı (etiket `casefold`'u, ad sadeleştirmesinin küçültmesi, arşiv süzgeci, kalemin silinmesi, tekil kalem, arşiv olayı, bilinmeyen etiket, tür kalemi eşleşmesi ×2, menü girişi, `<textarea>`). Başsız Chrome 1400 px'te liste ve grup sayfası düzgün.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K14.1)_
#### K14.2 — 14.2.1, 14.2.2, 14.2.3, 14.3.1 · Çalışan profilinde belge paketleri
- ✅ Kapı: ruff check/format (355 dosya), compileall, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (0014→0015) exit 0; `pytest -q -m "not live" --cov=app` dokuz ön plan grubunda 5395 geçti (+42), 5 PG testi atlandı; sonra eklenen üç test (render, atama yenilemesi, GET yazmaz) kendi dosyalarında yeşil; birleşik kapsam %99 (`app/groups`, `routers/employees.py`, `routers/groups.py` %100). 18 geçici kural bozmasının 18'i kırmızı (arşivli belge karşılar, en eski belge, arşivli gruba paket, uyarısız ikinci paket, neden olaya girer, zorunlu sayımı, arşiv/taşıma/boru hattı/atama/grup kalemi yenilemesi, GET yazar, profil.md bölümü, açık paket sayımı, liste hücresi, neden zorunluluğu, yeniden açmada değerlendirme, `<textarea>`).

_Önceki maddeler: docs/archive/plan-kanit/ (#### K14.2)_
#### K13.5-c — 13.5.3 · Şema ve kod sürümü uyuşmazlığı koruması
- ✅ Kapı: ruff check/format (406 dosya), compileall, `import app.main`, temiz SQLite'ta `alembic upgrade head` (→0022, göç yok) exit 0. `pytest -q -m "not live" --cov=app` ön plan gruplarında 5962 geçti (+51), 5 PG atlandı. `coverage combine` + `report --fail-under=70` exit 0, kapsam %99, yeni modüller %100. 14 geçici kural bozmasının 13'ü kırmızı. Yeşil kalan `__pycache__` süzgeci ölü koddu ve kaldırıldı. Lifespan'i ya da giriş noktasını koşan 11 mevcut test uyarlandı: 8'i denetimi kapatır, 1'i şemayı göçle kurar, 2'si denetimi taklit eder (§D79d). `/health`'in 2 testi yeni gövdeye göre güncellendi. `test_intake.py`'nin zamanlamaya bağlı iki testi yük altında birer kez düştü; tek başına 3/3 ve `tests/telegram` yüksüz koşuda 214/214 yeşil. Bot alım koduna dokunulmadı.

_Önceki maddeler: docs/archive/plan-kanit/ (#### K13.5-c)_
#### K10.10 — 10.10.1, 10.10.2, 10.10.3, 10.10.4, 10.10.5, 10.10.6 · Arayüz dili: İngilizce, Türkçe, Sırpça
- ✅ 10.10.6 yapay zekâ serbest metinleri İngilizce (§D121 a): `app/ai/prompts/page_analysis.md` (`notes`, `Unmet acceptance criterion:` kalıbı, madde katalog dilinde), `photo_check.md`, `training_classification.md`, `type_description.md`, `type_proposal.md` — kural ve örnek değerler İngilizce, uzunluk sınırları aynı; kayıtlı yanıtlar ve sabitler (`tests/fixtures/ai/…`, `tests/ai/payloads.py`) İngilizce — test `tests/ai/test_output_language.py` (11), `tests/ai/test_type_proposal.py`, `tests/ai/test_type_description.py` · tm 177
- ✅ 10.10.6 sistem gerekçeleri kayıtta İngilizce, panelde kullanıcının dilinde (§D121 uygulama kararları a–e): `app/i18n/recorded.py` (`record_text`, `recall_texts`, `append_text`, `before_flush`), `RecordedText` + göç `alembic/versions/0029_recorded_texts.py`, `app/i18n` `join_text`; gerekçeler `Translatable` — `app/pipeline/group.py`, `validate.py`, `legibility.py`, `plan_rules.py`, `plan_planner.py`, `route.py`, `analyze.py`, `app/matching/match.py`, `status.py`, `mrz.py`, `app/training/*`, `app/storage/map_paths.py`; panel `recorded()`/`recorded_attrs` — `history.html`, `queue.html`, `queue_close_step.html`, `queue_item.html`, `training_results.html`, `training_type.html`, `upload_detail.html`; en/sr `.po` dolu (179 yeni msgid) — test `tests/i18n/test_recorded.py` (12), `tests/web/test_recorded_reasons.py` (5: bilinmeyen tür gerekçesi her kayıtta İngilizce, parti detayı ve kuyruk öğesi en/tr/sr, eski Türkçe kayıt olduğu gibi ve `translate="no"`), yardımcı `tests/recorded.py` · tm 177
- ✅ Kapı (tm 177): ruff check/format, `python -m compileall -q app tests`, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0029), `python -m app.i18n check` exit 0; `pytest -q -m "not live" -n 12 --cov=app` tek paralel koşuda 7007 geçti, 5 atlandı, kapsam %99,00 exit 0. Geçici bozmalar kırmızıya döndü: talimat Türkçe ister (1 test), kayıt dili Türkçe (8 test), panel çevirmez (Sırpça/İngilizce parti detayında Türkçe gerekçe, 2 test) · tm 177

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.10)_
#### K10.11 — 10.11.1, 10.11.2, 10.11.3 · Geri bildirim ve yol gösterme
- ✅ 10.11.3: ipuçları ve yeni bildirimler en/tr/sr (34 yeni msgid, `.mo` derlendi), `python -m app.i18n check` exit 0; dil taramasına aday tür onay/ret bildirimleri (`FLASH_PAGES`) ve salt okunur görünüm (parti detayı, üç tür kuyruk öğesi, sekmeler) eklendi — test `tests/web/test_translation_sweep.py` (`test_the_read_only_view_of_pending_work_speaks_the_chosen_language`), `tests/web/test_guidance.py::test_every_hint_speaks_the_chosen_language` · tm 176
- ✅ S28 kabul senaryosu: CV aday türü partiden onaya, onay bildirimi (bağlı öğe 1, sonraki adım), pasife alma bildirimi tek kullanımlık ve Sırpça, ipuçları Sırpça, Kullanıcı onay bağlantısı görmez — test `tests/test_scenario_s28.py` (1) · tm 176
- ✅ Kapı (tm 176): ruff check/format, `python -m compileall -q app tests`, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0028, göç yok), `python -m app.i18n check` exit 0. Geçici kural bozmaları kırmızıya döndü (Kullanıcı onay bağlantısı görür, eski sürüm satırı bağlantılı, Sırpça istekte Türkçe ipucu, kapalı öğe adım gösterir). `pytest -q -m "not live" -n 12 --dist worksteal --cov=app` 10 dk ön plan sınırı yüzünden dört parçada `--cov-append` ile: 6979 geçti, 5 atlandı (PostgreSQL), kapsam %99,01, `--cov-fail-under=70` exit 0 · tm 176

_Önceki maddeler: docs/archive/plan-kanit/ (#### K10.11)_
#### K15.1 — 15.1.1, 15.1.2, 15.1.3, 15.1.4 · Hazır şablon deposu, incelemesi ve harita onayı
- ✅ Görüntüleme (15.1.4): orijinal yeni sekmede/indirme, erişim kaydı `template_id` ile önce yazılır; önizleme görüntüsü kayda girmez; Kullanıcı listeyi ve önizlemeyi görür, yazma 403; menü "Hazır Şablonlar" (Belge Grupları'ndan sonra, simgeli), üç dil — `app/web/templates/output_templates.html`, `output_template.html` · test `tests/web/test_output_templates.py`, `test_auth.py`, `test_roles.py`, `test_translation_sweep.py`, `test_ui_standard.py`, `test_access_log.py` · tm 182
- ✅ İnceleme (15.1.2): `TemplateFieldMap` §8.7 şeması (`kind`/`source` kuralı, kutu ∈ [0,1], sayfa sınırı), talimat `template_map.md` (sabit metin yok, imza/kaşe/logo/fotoğraf/çerçeve `kind`, `notes` İngilizce), `examine_template` üç sağlayıcıda; göç 0032 kuyruk + boş-zaman işi, harita sürümü `map_hash`, `examine_error` kodu listede/sayfada, "Yeniden incele", `TEMPLATE_EXAMINED` — `app/output_templates/examine.py` · test `tests/ai/test_template_map.py` (19), `tests/worker/test_template_examination.py` (5), `tests/web/test_output_templates.py` (+2) · tm 183
- ✅ Önizleme ve onay (15.1.3): kutular sayfa görüntüsünün üstünde SVG (`viewBox` = görüntü ölçüsü, `style=` yok), `text`/`date` kutusunda §8.7 `source` listesi + "Boş bırak", imza/kaşe/logo/fotoğraf/çerçeve seçimsiz; `POST …/maps/{version}/approve` düz form: bilinmeyen/eksik/doldurulamaz atama 422, bağlı kutu yoksa 422 + bildirim (seçimler korunur), eski sürüm ya da arşiv 409; değişen atama yeni sürüm (`map_hash`), şablon `ready`, `TEMPLATE_MAP_APPROVED`; Kullanıcı yalnız onaylı haritayı salt okunur görür; üç dil — `app/output_templates/approve.py`, `app/web/routers/output_templates.py`, `output_template.html`, `panel.css` · test `tests/web/test_output_template_map.py` (7), `test_ui_standard.py`, `test_translation_sweep.py`, `test_roles.py`, `test_access_log.py` · tm 184

_Önceki maddeler: docs/archive/plan-kanit/ (#### K15.1)_
#### K15.2 — 15.2.1, 15.2.2, 15.2.3 · Çıktıya hazırla ve üretilen belgeler
- ✅ Yaşam döngüsü (15.2.2, 15.2.3): yeniden üretim aynı şablonun etkin belgesini `superseded` yapar (dosya silinmez, adı değişmez, açılır; `OUTPUT_GENERATED.superseded`); arşivle/geri al tek adım, `OUTPUT_ARCHIVED`/`OUTPUT_RESTORED` (geri alınan, daha yeni belge varsa `superseded`); 10.5.6 `Uretilen/` dosyaları K8 adıyla yeniden adlandırılır (`path`/`sequence_no`, yarıda kalırsa geri alınır, `EMPLOYEE_EDITED.outputs`); 10.5.9 kalanın `Uretilen/`'ine K8 adı + kalanın sırasından sonraki ek (`EMPLOYEE_MERGED.outputs`); 10.5.13 dosyalar diskten, satırlar `deleted` (yol boş), `EMPLOYEE_DELETED.outputs` + `files_deleted` — `app/output_templates/lifecycle.py`, `generate.py`, `app/storage/rename.py`, `app/storage/merge.py`, `app/storage/delete_employee.py`, `app/matching/merge.py`, `app/matching/edit.py` · test `tests/output_templates/test_lifecycle.py` (6) · tm 186
- ✅ Panel ve profil.md (15.1.4, 15.2.2, S29): satırda "Arşivle", arşivdekiler katlanmış `details.archived-outputs` bölümünde "Geri al" (yazma yetkisi; `POST …/outputs/{id}/archive|restore`), arşivdeki şablonun üretilmiş belgeleri yerinde; `profil.md` "Üretilen belgeler" tablosu (şablon, dosya, durum, tarih; `deleted` yok), her çıktı yazmasından sonra yeniden üretilir; üç dil; S29 tam (yeniden üretim `-2` + `superseded`, kalıcı silmede iki dosya gider, satırlar `deleted`, olaylar değersiz) — `app/web/routers/generated_documents.py`, `profile.html`, `app/profiles/render.py`, `app/web/feedback.py` · test `tests/web/test_outputs.py` (+2), `tests/test_scenario_s29.py` (1), `tests/profiles/test_render.py`, `test_access_log.py`, `test_profile.py`, `test_roles.py` · tm 186
- ✅ Kapı (tm 186): ruff check/format, compileall, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0032, göç yok), `python -m app.i18n check` exit 0; `pytest -q -m "not live" -n 6 --dist worksteal --cov=app --cov-fail-under=70` 7143 geçti, 6 atlandı, %98,77 — 2 kırmızı (`…plan_d58_verbatim`) önceki görevlerdeki gibi ilgisiz · tm 186

_Önceki maddeler: docs/archive/plan-kanit/ (#### K15.2)_
#### K15.3 — 15.3.1, 15.3.2, 15.3.3 · Ek profil alanları ve kişisel numara
- ✅ Ek profil alanları: `employees` beş sütun + gözlem CHECK'i (göç 0030), `ProfileField` dört üye, profil kartı (dört alan + pasaport numarası, "—", kaynak/çelişki), düzenleme formu (elle kaynağı, `EMPLOYEE_EDITED` alan adları; ülke `personal_number` gözlemiyle), `profil.md` ön blok + kimlik tablosu, birleştirme (boş alan dolar, numara ülkesiyle), kalıcı silme (boşaltır, olay temizliği değerleri atar) — `alembic/versions/0030_employee_detail_fields.py`, `app/web/routers/employees.py`, `app/matching/edit.py`, `app/matching/merge.py`, `app/storage/delete_employee.py`, `app/profiles/render.py`, `app/matching/records.py:passport_number` · test `tests/db/test_migrations.py` (1), `tests/web/test_profile.py` (2), `tests/web/test_employee_fields.py` (6), `tests/matching/test_merge.py` (2), `tests/web/test_employee_merge.py` (1), `tests/storage/test_delete_employee.py` (1), `tests/web/test_employee_delete.py` (1), `tests/profiles/test_render.py` (2), `tests/test_scenario_s25.py` · tm 180
- ✅ Kişisel numara (15.3.3): olduğu gibi saklanır; karşılaştırma ve arama boşluk/tire/nokta ve harf büyüklüğünü yok sayar, doğrulama yok, değer olaya yazılmaz — `app/matching/numbers.py` · test `tests/matching/test_numbers.py` (8), `tests/web/test_employees.py` (6) · tm 180
- ✅ Belgeden dolum (15.3.2): `PagePerson` beş isteğe bağlı alan (eski yanıt `null`, sağlayıcı şeması hepsini ister), talimat yalnız açıkça yazılı değer; TD1 isteğe bağlı verisinden kişisel numara (bileşik + belge no hanesi tutarsa, ülke = veren devlet) görünen metinden önce; `PersonKey` ek alanlar, 05.7.3 dolumu (ülke numarayla), 05.5.4 doldurmaz, `fill-fields` yeni alanlar; PRD §20.1.3 eki — `app/ai/schemas.py`, `app/ai/prompts/page_analysis.md`, `app/matching/mrz.py`, `app/matching/match.py`, `app/matching/fields.py` · test `tests/matching/test_mrz.py` (3), `test_person_key.py` (3), `test_profile_fields.py` (2), `tests/ai/test_schemas.py` (2), `tests/profiles/test_field_fill.py` (1), `tests/test_detail_fields_upload.py` (1) · tm 181

#### KF0 — PRD §5.1 · Faz 0 — MVP kapanış ölçütü
- ✅ Kapı (tm 170): senaryo dosyaları (`test_scenarios_s01_s05/s06_s10/s11_s18`, `test_scenario_s23`) ayrı koşuda 40 geçti (S1–S15, S18, S23 her biri en az bir PASSED; skip/xfail yok); ruff check/format (459 dosya), `python -m compileall -q app tests`, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0028), `python -m app.i18n check` exit 0; `pytest -q -m "not live" -n 12 --dist worksteal --cov=app --cov-fail-under=70` 6913 geçti, 5 atlandı, 0 kırmızı, %99,03; 2 geçici kural bozmasının 2'si kırmızı (satır 5a doğum tarihi farklıyken de eşleştirir, yalnız isim eşleşmesi satır 6'ya iner — ikisinde de S10 ve S12 `hicbirine-uymuyor` kırmızı); `app/` değişmedi · tm 170

_Önceki maddeler: docs/archive/plan-kanit/ (#### KF0)_
#### KF1 — PRD §5.2 · Faz 1 — v1 kapanış ölçütü
- ✅ Yeniden kapanış — S16 ve roller: taşımanın sonucu bildirim (yalnız E numarası, ad yok) + parçada yeni dosya adı; iki profil sayfası güncellendi, olay kullanıcı adıyla; yolculuk, katalog, aday tür ve S16 yine `role="hr"` (`tests/web/conftest.py` `SIGNED_IN`); salt okunur Kullanıcı'nın 90'dan fazla yazma isteği 403 ve `{"detail": …}` gövdesiyle reddedilir, veri anlık görüntüsü değişmez (tm 175'in 403 bildirimi kodu ve gövdeyi korur) — test `tests/web/test_document_move.py::test_s16_one_confirmation_changes_nothing`, `::test_s16_two_confirmations_move_the_document_update_both_profiles_and_log_the_user`, `tests/web/test_roles.py::test_a_read_only_user_gets_403_on_every_writing_route_and_nothing_changes` · tm 178
- ✅ Yeniden kapanış — ek kanıt S24–S28 (ölçütte yok, bu fazın senaryoları; S28 yeni) yeşil — test `tests/test_scenario_s24.py`, `tests/test_scenario_s25.py`, `tests/test_scenario_s26.py`, `tests/test_scenario_s27.py`, `tests/test_scenario_s28.py` · tm 178
- ✅ Kapı (tm 178): yolculuk + katalog + aday tür + S16 + roller + gerekçeler + `test_scenarios_s11_s18` (S14) + S24–S28 ayrı koşuda 206 geçti (yolculuk, S14, S16, S24–S28 her biri en az bir PASSED; skip/xfail yok); ruff check/format (472 dosya), `python -m compileall -q app tests`, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0029), `python -m app.i18n check` exit 0; `pytest -q -m "not live" -n 12 --dist worksteal --cov=app --cov-fail-under=70` 7007 geçti, 5 atlandı (yalnız PostgreSQL), 0 kırmızı, %99,00, 14 dk 7 sn; 4 geçici kural bozmasının 4'ü kırmızı (atama bildirimi çıkar ama atama yazılmaz → yolculuk Unresolved sayacında, eski sayaç assert'i bu bozmada geçiyordu; gerekçenin kaynağı geri çağrılmaz → yolculuk gerekçe assert'inde; aday onayı bildirimi çıkar ama tür kataloğa girmez → onay, toplu yeniden analiz ve S28; tür oluşturma bildirimi çıkar ama tür kaydedilmez → oluşturma testi); `app/` değişmedi, `tests/web/test_phase1_closure.py` güçlendirildi (açık sekmenin sayacı, gerekçenin dili) · tm 178

_Önceki maddeler: docs/archive/plan-kanit/ (#### KF1)_
#### KF2 — PRD §5.3 · Faz 2 — v2 kapanış ölçütü
- ✅ Kapı (tm 172): `tests/telegram` + fotoğraf testleri + S4 fotoğraf senaryosu + `tests/web/test_telegram_delete.py` ayrı koşuda 501 geçti, 0 atlandı; ruff check/format (460 dosya), `python -m compileall -q app tests`, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0028), `python -m app.i18n check` exit 0; `pytest -q -m "not live" -n 12 --dist worksteal --cov=app --cov-fail-under=70` 6919 geçti, 5 atlandı (yalnız PostgreSQL), 0 kırmızı, %99,02 (ilk koşuda kanıt dışı kararsız `tests/telegram/test_intake.py::test_a_summary_only_counts_its_own_batch` kırmızı, tek başına yeşil; düzeltmesi tm 173); 5 geçici kural bozmasının 5'i kırmızı (istek işleyicisi kapıdan önce, yedek işleyici kapıdan önce, susturulanın dosyası da durur, Kullanıcı belge isteyemez, Kullanıcı belge gönderebilir); `app/` değişmedi, `tests/telegram/test_phase2_closure.py` eklendi (6) · tm 172

_Önceki maddeler: docs/archive/plan-kanit/ (#### KF2)_
#### KF3 — PRD §5.4 · Faz 3 — Enterprise kapanış ölçütü
- ✅ Kapı (tm 174): `tests/scripts` ayrı koşuda 27 geçti, 0 atlandı (iki prova testi PASSED, skip/xfail yok); ruff check/format (460 dosya), `python -m compileall -q app tests`, `import app.main`, `git diff --check`, temiz SQLite'ta `alembic upgrade head` (→0028), `python -m app.i18n check` exit 0; `pytest -q -m "not live" -n 12 --dist worksteal --cov=app --cov-fail-under=70` 6919 geçti, 5 atlandı (yalnız PostgreSQL), 0 kırmızı, %99,02; sunucuda yalnız `docker compose ps` ve `sha256sum` koşuldu; `app/`, `tests/`, `scripts/`, `docs/` değişmedi · tm 174
_Önceki maddeler: docs/archive/plan-kanit/ (#### KF3)_
