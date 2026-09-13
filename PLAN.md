# PLAN — belgeee (neredeyiz?)

> Bu dosya projenin **durum haritasıdır**. Ne yapılacağı `urun-gereksinim-dokumani-PRD.md`'de,
> nasıl yapılacağı `MASTER-PROMPT.md`'de, "bitti"nin tanımı `CONVENTIONS.md`'dedir.
> Bu dosyayı bir izleme paneli ayrıştırır — biçim kuralları kesindir (§1).

## 0. Özet tablo

| Faz | PRD | Genel durum | Must sayacı | Kapanış |
| --- | --- | --- | --- | --- |
| Faz 0 — MVP | §5.1 | 4 ✅ · 0 ◐ · 98 ⬜ · 0 🔒 | 4/98 Must | AÇIK |
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
| 00.2.1 | Ortam değişkeni tabanlı yapılandırma | Must (MVP) | ⬜ |
| 00.2.2 | Eksik zorunlu ayarda anlaşılır hata | Must (MVP) | ⬜ |
| 00.3.1 | Veri modeli (§8'deki 15 tablo) | Must (MVP) | ⬜ |
| 00.3.2 | Göç altyapısı | Must (MVP) | ⬜ |
| 00.3.3 | Çalışan numarası üretici | Must (MVP) | ⬜ |
| 00.4.1 | Veri dizini otomatik oluşturma | Must (MVP) | ⬜ |
| 00.4.2 | İsim sadeleştirme (slug) | Must (MVP) | ⬜ |
| 00.4.3 | Çıktı adlandırma ve sıra eki | Must (MVP) | ⬜ |
| 00.4.4 | Bütünlük ve atomik yazma | Must (MVP) | ⬜ |
| 00.5.1 | Olay logu altyapısı | Must (MVP) | ⬜ |
| 00.5.2 | Olay bağlamı yöneticisi | Must (MVP) | ⬜ |
| 00.6.1 | Katalog şeması ve tutarlılık kuralı | Must (MVP) | ⬜ |
| 00.6.2 | Başlangıç belge türleri | Must (MVP) | ⬜ |
| 00.6.3 | Katalog YAML ↔ veritabanı eşitleme | Should (v1) | ⬜ |

### 3.2 FR-MOD-01 — Yükleme ve Inbox

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 01.1.1 | Çoklu dosya yükleme uç noktası | Must (MVP) | ⬜ |
| 01.1.2 | Bağlam çalışanı ile yükleme | Must (MVP) | ⬜ |
| 01.2.1 | İçerik tabanlı tür tespiti | Must (MVP) | ⬜ |
| 01.2.2 | Desteklenmeyen türün reddi | Must (MVP) | ⬜ |
| 01.3.1 | Boyut ve sayfa sınırı | Must (MVP) | ⬜ |
| 01.4.1 | Tekrar yükleme tespiti | Must (MVP) | ⬜ |
| 01.5.1 | Inbox'a değişmez yazma | Must (MVP) | ⬜ |
| 01.6.1 | Parti durumu sorgulama | Must (MVP) | ⬜ |

### 3.3 FR-MOD-02 — Sayfa üretimi

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 02.1.1 | PDF sayfa görüntüsü üretimi | Must (MVP) | ⬜ |
| 02.2.1 | PDF metin katmanı çıkarma | Must (MVP) | ⬜ |
| 02.3.1 | Görüntü dosyaları için analiz kopyası | Must (MVP) | ⬜ |
| 02.4.1 | Boş sayfa tespiti | Must (MVP) | ⬜ |
| 02.5.1 | Gömülü tek görüntü tespiti | Must (MVP) | ⬜ |

### 3.4 FR-MOD-03 — Yapay zekâ analiz katmanı

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 03.1.1 | Sayfa analizi şeması | Must (MVP) | ⬜ |
| 03.1.2 | Dil ve alfabe tespiti | Must (MVP) | ⬜ |
| 03.1.3 | Diğer isimler alanı | Must (MVP) | ⬜ |
| 03.1.4 | İletişim bilgisi alanları | Must (MVP) | ⬜ |
| 03.2.1 | Sağlayıcı soyutlaması | Must (MVP) | ⬜ |
| 03.2.2 | Anthropic sağlayıcı | Must (MVP) | ⬜ |
| 03.3.1 | OpenAI sağlayıcı iskeleti | Should (v1) | ⬜ |
| 03.4.1 | Analiz promptu disiplini | Must (MVP) | ⬜ |
| 03.5.1 | Yeniden deneme ve dayanıklılık | Must (MVP) | ⬜ |
| 03.6.1 | Kayıtlı yanıtla test sağlayıcısı | Must (MVP) | ⬜ |
| 03.7.1 | Sayfa analizi çalıştırıcı | Must (MVP) | ⬜ |
| 03.7.2 | Kısmi başarı davranışı | Must (MVP) | ⬜ |

### 3.5 FR-MOD-04 — Karar motoru

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 04.1.1 | Dosya içi gruplama | Must (MVP) | ⬜ |
| 04.1.2 | Ön/arka yüz yapısı | Must (MVP) | ⬜ |
| 04.2.1 | Ardışıklık güvenlik kuralı (R6) | Must (MVP) | ⬜ |
| 04.3.1 | Dosyalar arası gruplama | Must (MVP) | ⬜ |
| 04.3.2 | Belirsiz eşleştirmenin reddi | Must (MVP) | ⬜ |
| 04.4.1 | Zorunlu alan okunaklılık kapısı (R1) | Must (MVP) | ⬜ |
| 04.4.2 | Kabul kriteri değerlendirmesi | Should (v1) | ⬜ |
| 04.5.1 | Beklenen sayfa sayısı kontrolü | Must (MVP) | ⬜ |
| 04.6.1 | Bilinmeyen tür → aday öneri | Must (MVP) | ⬜ |
| 04.7.1 | Word/Excel yolu (Attachment) | Must (MVP) | ⬜ |

### 3.6 FR-MOD-05 — Kimlik ve çalışan eşleştirme

| PRD | Gereksinim | Öncelik | Durum |
| --- | --- | --- | --- |
| 05.1.1 | İsim normalizasyonu | Must (MVP) | ⬜ |
| 05.2.1 | Harf çevirisi | Must (MVP) | ⬜ |
| 05.3.1 | MRZ ayrıştırma | Must (MVP) | ⬜ |
| 05.3.2 | MRZ kontrol hanesi doğrulaması | Must (MVP) | ⬜ |
| 05.3.3 | MRZ önceliği | Must (MVP) | ⬜ |
| 05.4.1 | Kişi anahtarı | Must (MVP) | ⬜ |
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
