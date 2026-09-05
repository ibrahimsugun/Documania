# Ürün Gereksinim Dokümanı — Akıllı Çalışan Belge Yönetim ve Otomasyon Sistemi

| | |
|---|---|
| **Ürün kodu** | belgeee |
| **Sürüm** | 1.0 |
| **Tarih** | 2026-09-05 |
| **Durum** | Onaylı — otonom yapıma hazır |

> **Kural:** PRD kimliği olmayan iş yapılmaz. Bu belgedeki her gereksinim
> `<modül>.<özellik>.<alt>` biçiminde numaralıdır ve o numara PLAN.md, Task Master
> ve commit mesajlarına kadar taşınır.

---

## 1. Amaç

Çok sık personel işe alıp çıkaran uluslararası şirketlerde, çalışanlardan gelen belgelerin
otomatik olarak anlaşılması, sınıflandırılması, doğrulanmış bir dosya yapısında düzenlenmesi
ve hızlı erişilebilir hale getirilmesi.

Çalışanlar belgeleri çoğu zaman yanlış formatta gönderir: JPEG istenen fotoğraf PDF olarak
gelir, pasaport ve başka belgeler tek PDF'te birleşir, farklı çalışanlara ait belgeler aynı
dosyada bulunur. Sistem dosyanın adını, uzantısını veya düzenini doğru kabul etmek yerine
**içeriğini analiz ederek** belgenin ne olduğunu, kime ait olduğunu ve nasıl işlenmesi
gerektiğini belirler.

**Temel felsefe:** belgeyi değiştirmek değil, belgeyi anlamak ve doğru şekilde yönetmek.
Yapay zekâ belgenin içeriğini okuyarak karar verir; içeriğini asla yeniden üretmez. Yalnızca
fiziksel ve organizasyonel hatalar düzeltilir.

## 2. Kullanıcılar

| Kullanıcı | Kullanım biçimi | Beklentisi |
|---|---|---|
| İK uzmanı | Web paneli, günlük | Belgeyi yükle, doğru klasörde bulmasını bekle, gerekirse kuyruğu çöz |
| İK uzmanı (sahada) | Telegram botu | Telefondan belge gönder, belge iste |
| İK yöneticisi | Web paneli, haftalık | Çalışan profillerini gör, eksik belgeleri gör, maliyeti gör |

Sistemi çalışan (personelin kendisi) doğrudan kullanmaz. Belgeler İK'ya ulaşır, İK sisteme yükler.

## 3. Ürünün temel kuralları

Bu kurallar ürünün kimliğidir; teknik karşılıkları `MASTER-PROMPT.md` §3'te kilitlidir.

| No | Kural |
|----|-------|
| R1 | **Okunaklılık tek kabul ölçütüdür.** Belge türünün zorunlu alanlarının hepsi okunaklıysa belge kabul edilir. Bir tanesi bile okunamıyorsa belge Unreadable kuyruğuna gider ve hangi alanın okunamadığı yazılır. Ayrı bir "güven skoru" yoktur. |
| R2 | **Orijinal dokunulmazdır.** Yüklenen dosya hiçbir koşulda değiştirilmez. |
| R3 | **İçerik üretilmez.** Sistem isim, tarih, numara değiştirmez; form doldurmaz; eksik bilgi eklemez; belgedeki yazıyı yeniden üretmez. |
| R4 | **Yalnız fiziksel düzenleme.** İzinli işlemler: sayfa çıkarma, sayfa birleştirme, görüntüyü kayıpsız PDF'e sarma, gömülü görüntüyü kayıpsız çıkarma, sabit çözünürlükle görüntüye çevirme, yeniden adlandırma, kopyalama, taşıma. |
| R5 | **Direkt Belge bütünlüğü.** `direct` işaretli türlerde başka dosyayla birleştirme, format dönüştürme ve yeniden kodlama yasaktır; yalnız tek kaynaktan ardışık sayfa çıkarma serbesttir. |
| R6 | **Ardışıklık güvenliği.** Bir belgenin sayfaları arasına başka belgeye ait sayfa girmişse sistem bunları otomatik birleştirmez. |
| R7 | **Emin değilse kuyruğa.** Kişisi veya türü belirlenemeyen belge çalışan klasörüne rastgele yerleştirilmez; Unknown / Unreadable / Unresolved kuyruklarına alınır ve kullanıcı uyarılır. |
| R8 | **İsim tek başına kimlik değildir.** Yalnız ad-soyad eşleşmesi otomatik eşleştirme sayılmaz. |
| R9 | **Numarasız belgeden çalışan doğmaz.** Otomatik yeni çalışan profili yalnız temiz okunmuş bir belge numarası varsa açılır. |
| R10 | **Karar bir kez verilir.** Yapay zekâ analizi Plan JSON olarak dondurulur; fiziksel işlemler bu plandan yürütülür, yeniden yapay zekâya sorulmaz. |
| R11 | **Silme yoktur, arşiv vardır.** |
| R12 | **Manuel içerik düzenleme yoktur.** Kullanıcı belge içeriğini hiçbir arayüzden değiştiremez; yalnız belgenin hangi çalışana ait olduğunu iki aşamalı onayla değiştirebilir. |
| R13 | **Her işlem izlenebilir.** Üretilen her çıktı hangi kaynak dosyanın hangi sayfalarından üretildiğini taşır. |

## 4. Sözlük

| Terim | Anlamı |
|---|---|
| Yükleme partisi | Tek seferde, tek kanaldan gelen dosya grubu; bir `upload_id` alır |
| Kaynak dosya | Partideki tek bir orijinal dosya |
| Sayfa | Kaynak dosyanın tek sayfası; JPEG ve PNG tek sayfalı kaynak sayılır |
| Sayfa analizi | Yapay zekânın tek sayfa için ürettiği yapılandırılmış sonuç |
| Belge adayı | Karar motorunun aynı belgeye ait olduğuna hükmettiği sayfa grubu |
| Çıktı belgesi | Hazir klasörüne yazılan nihai dosya |
| Plan | Bir parti için dondurulmuş karar kümesi (JSON) |
| Bilinen belge türü | Katalogdaki, şirketin kabul ettiği belge türü |
| Aday belge türü | Sistemin önerdiği, henüz onaylanmamış tür |
| Zorunlu alan | Bir türün kabul edilmesi için okunaklı olması gereken alan |
| Kuyruk | Unknown, Unreadable, Unresolved |
| Köken | Bir çıktının kaynak dosya + sayfa aralığı bilgisi |
| Direkt Belge | Fiziksel bütünlüğü korunması gereken belge türü |

## 5. Fazlar

### 5.1 Faz 0 — MVP

**Hedef:** Bir dosya API'den girsin, doğru çalışanın `Hazir` klasöründen veya doğru kuyruktan
çıksın. Panel yok, Telegram yok.

Kapsam: FR-MOD-00 … FR-MOD-09.

**Kapanış ölçütü:** §9'daki S1–S15 ve S18 senaryoları otomatik testte geçiyor; bir partinin
olay logu baştan sona okunabiliyor; her çıktının kökeni yazılı; yeniden çalıştırma yapay zekâ
çağırmıyor.

### 5.2 Faz 1 — v1

**Hedef:** İK'nın günlük kullanabileceği web paneli ve kendini genişleten belge kataloğu.

Kapsam: FR-MOD-10, FR-MOD-11 (11.1–11.5).

**Kapanış ölçütü:** İK bir belgeyi yükleyip, kuyruğu çözüp, profilde görüp yeni sekmede
açabiliyor; katalog panelden yönetiliyor; yeni tür onayı uçtan uca çalışıyor.

### 5.3 Faz 2 — v2

**Hedef:** Telefondan kullanım ve profil fotoğrafı kalite kontrolü.

Kapsam: FR-MOD-12, FR-MOD-11 (11.6–11.8).

**Kapanış ölçütü:** Bot yalnız beyaz listeye yanıt veriyor; belge gönderme ve isteme uçtan uca
çalışıyor; kural ihlali olan fotoğraf Hazir'a girmiyor.

### 5.4 Faz 3 — Enterprise

**Hedef:** Sunucuda güvenli, ölçülebilir ve dayanıklı çalışma.

Kapsam: FR-MOD-13.

**Kapanış ölçütü:** Sunucuda alan adıyla çalışıyor; yedekten geri yükleme bir kez denendi;
maliyet paneli gerçek rakam gösteriyor.

---

## 6. Modüller ve gereksinimler

Öncelik sözleşmesi: **Must (MVP)** = Faz 0 zorunlu · **Must (v1)** = Faz 1 zorunlu ·
**Should (v1)** = Faz 1 iyi olur · **Should (v2)** / **Could (v3)** = sonraki fazlar.

### FR-MOD-00 — Altyapı ve iskelet (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 00.1.1 | Python 3.12 + FastAPI uygulama iskeleti | `GET /health` 200 ve `{"status":"ok"}` döner | Must (MVP) |
| 00.1.2 | Bağımlılık yönetimi ve test komutu | `pytest` tek komutla çalışır ve yeşil biter | Must (MVP) |
| 00.1.3 | Docker Compose ile ayağa kalkma | `docker compose up` sonrası `/health` 200 döner | Must (MVP) |
| 00.1.4 | Lint ve biçim kapısı | `ruff check .` exit 0 | Must (MVP) |
| 00.2.1 | Ortam değişkeni tabanlı yapılandırma | Tüm ayarlar `.env` ile değişir; kodda sabit yol/model adı yoktur | Must (MVP) |
| 00.2.2 | Eksik zorunlu ayarda anlaşılır hata | Zorunlu değişken yoksa açılışta hangi değişkenin eksik olduğunu söyleyen hata verilir | Must (MVP) |
| 00.3.1 | Veri modeli (§8'deki 15 tablo) | Tüm tablolar SQLAlchemy modeli olarak vardır ve ilişkiler testte doğrulanır | Must (MVP) |
| 00.3.2 | Göç altyapısı | `alembic upgrade head` hem SQLite hem PostgreSQL üzerinde temiz çalışır | Must (MVP) |
| 00.3.3 | Çalışan numarası üretici | `E0001` biçiminde artan, tekil; eşzamanlı 50 çağrıda çakışma yok | Must (MVP) |
| 00.4.1 | Veri dizini otomatik oluşturma | Uygulama açılışında §8.2'deki ağaç eksiksiz oluşur | Must (MVP) |
| 00.4.2 | İsim sadeleştirme (slug) | Türkçe, Kiril ve Arap isimler `[A-Za-z0-9_-]` kümesine iner; testte üç alfabe için doğrulanır | Must (MVP) |
| 00.4.3 | Çıktı adlandırma ve sıra eki | Aynı türden ikinci belge `-2`, üçüncü `-3` eki alır; mevcut dosyanın üzerine yazılmaz | Must (MVP) |
| 00.4.4 | Bütünlük ve atomik yazma | SHA-256 hesaplanır; yazma kesilirse yarım dosya kalmaz (testle doğrulanır) | Must (MVP) |
| 00.5.1 | Olay logu altyapısı | §8.3'teki olay türleri sabit listedir; her olay veritabanına yazılır | Must (MVP) |
| 00.5.2 | Olay bağlamı yöneticisi | Bağlam içinde atılan olaylar upload/file/page alanlarını otomatik taşır | Must (MVP) |
| 00.6.1 | Katalog şeması ve tutarlılık kuralı | `direct: true` olan türde dönüşüm listesi doluysa katalog yüklemesi reddedilir | Must (MVP) |
| 00.6.2 | Başlangıç belge türleri | En az 8 tür yüklüdür: Russian/Turkish/Serbian Passport, Serbian Residence Card, Serbian Driving License, Work Permit, Profile Picture, Attachment | Must (MVP) |
| 00.6.3 | Katalog YAML ↔ veritabanı eşitleme | YAML tohumdan yükleme ve veritabanından dışa aktarma iki yönlü çalışır | Should (v1) |

### FR-MOD-01 — Yükleme ve Inbox (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 01.1.1 | Çoklu dosya yükleme uç noktası | `POST /api/uploads` birden çok dosyayı tek parti olarak kabul eder ve `upload_id` döner | Must (MVP) |
| 01.1.2 | Bağlam çalışanı ile yükleme | İstek `context_employee_id` taşıyabilir; taşıyorsa sahibi belirsiz dosyalar bu çalışana atanır | Must (MVP) |
| 01.2.1 | İçerik tabanlı tür tespiti | Uzantısı `.jpg` olan PDF içerikli dosya PDF olarak tanınır | Must (MVP) |
| 01.2.2 | Desteklenmeyen türün reddi | PDF/JPEG/PNG/DOC/DOCX/XLS/XLSX dışındaki dosya anlaşılır mesajla reddedilir | Must (MVP) |
| 01.3.1 | Boyut ve sayfa sınırı | Sınırı aşan dosya reddedilir ve kullanıcıya bölmesi söylenir | Must (MVP) |
| 01.4.1 | Tekrar yükleme tespiti | Aynı SHA-256 ikinci kez geldiğinde analiz edilmez, olay loguna yazılır | Must (MVP) |
| 01.5.1 | Inbox'a değişmez yazma | Dosya `Inbox/<upload_id>/` altına orijinal adıyla yazılır ve bir daha değiştirilmez | Must (MVP) |
| 01.6.1 | Parti durumu sorgulama | `GET /api/uploads/{id}` durum, dosyalar ve ilerleme döner | Must (MVP) |

### FR-MOD-02 — Sayfa üretimi (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 02.1.1 | PDF sayfa görüntüsü üretimi | Her sayfa yapılandırılmış DPI'da render edilir, uzun kenar sınırına küçültülür | Must (MVP) |
| 02.2.1 | PDF metin katmanı çıkarma | Metin katmanı olan sayfada metin çıkarılır ve saklanır; taranmış sayfada boş kalır | Must (MVP) |
| 02.3.1 | Görüntü dosyaları için analiz kopyası | EXIF yönelimi uygulanmış kopya üretilir; orijinal değişmez | Must (MVP) |
| 02.4.1 | Boş sayfa tespiti | Boş sayfa işaretlenir, analizciye gönderilmez, hata sayılmaz | Must (MVP) |
| 02.5.1 | Gömülü tek görüntü tespiti | Sayfa tek tam-sayfa görüntüden oluşuyorsa işaretlenir (kayıpsız çıkarma için) | Must (MVP) |

### FR-MOD-03 — Yapay zekâ analiz katmanı (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 03.1.1 | Sayfa analizi şeması | Model çıktısı §8.4'teki şemaya uyar; uymayan yanıt reddedilir | Must (MVP) |
| 03.2.1 | Sağlayıcı soyutlaması | Sağlayıcı `.env` ile değişir; boru hattı kodu değişmez | Must (MVP) |
| 03.2.2 | Anthropic sağlayıcı | Görüntü + metin girdisiyle şemaya uygun yapılandırılmış çıktı üretir | Must (MVP) |
| 03.3.1 | OpenAI sağlayıcı iskeleti | Aynı arayüzü uygular ve en az bir gerçek çağrıyla doğrulanır | Should (v1) |
| 03.4.1 | Analiz promptu disiplini | Prompt "tahmin etme", "okuyamadığını `legible:false` yap", "katalogda yoksa aday öner" kurallarını içerir | Must (MVP) |
| 03.5.1 | Yeniden deneme ve dayanıklılık | Hız sınırı ve 5xx durumunda geri çekilmeli üç deneme yapılır | Must (MVP) |
| 03.6.1 | Kayıtlı yanıtla test sağlayıcısı | Testler ağ erişimi olmadan çalışır ve deterministik sonuç verir | Must (MVP) |
| 03.7.1 | Sayfa analizi çalıştırıcı | Sayfalar sırayla, önceki sayfa özetiyle analiz edilir | Must (MVP) |
| 03.7.2 | Kısmi başarı davranışı | Bir sayfanın analizi başarısız olursa parti `partial` olur, diğer sayfalar tamamlanır | Must (MVP) |

### FR-MOD-04 — Karar motoru (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 04.1.1 | Dosya içi gruplama | Ardışık, aynı tür ve aynı kişiye ait sayfalar tek belge adayı olur | Must (MVP) |
| 04.1.2 | Ön/arka yüz yapısı | `front_back` türlerde ön ve arka sayfa sıralı biçimde eşleşir | Must (MVP) |
| 04.2.1 | Ardışıklık güvenlik kuralı (R6) | Araya başka belge girmiş parçalar otomatik birleştirilmez, gerekçesiyle Unresolved'a gider | Must (MVP) |
| 04.3.1 | Dosyalar arası gruplama | Yalnız `direct: false` türlerde, aynı partideki ayrı dosyalardaki ön ve arka yüz eşleştirilir | Must (MVP) |
| 04.3.2 | Belirsiz eşleştirmenin reddi | Aynı türden birden fazla ön yüz varsa eşleştirme yapılmaz, hepsi Unresolved'a gider | Must (MVP) |
| 04.4.1 | Zorunlu alan okunaklılık kapısı (R1) | Zorunlu alanların biri bile okunaksızsa aday Unreadable olur ve eksik alan adları gerekçeye yazılır | Must (MVP) |
| 04.5.1 | Beklenen sayfa sayısı kontrolü | Aday, türün sayfa aralığı dışındaysa Unresolved olur | Must (MVP) |
| 04.6.1 | Bilinmeyen tür → aday öneri | Katalogda olmayan belge zorla bir türe atanmaz; aday tür olarak kaydedilir ve Unknown'a gider | Must (MVP) |
| 04.7.1 | Word/Excel yolu (Attachment) | Word ve Excel analiz edilmez, dönüştürülmez; bağlam çalışanı varsa Hazir'a olduğu gibi kaydedilir, yoksa Unresolved'a gider | Must (MVP) |

### FR-MOD-05 — Kimlik ve çalışan eşleştirme (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 05.1.1 | İsim normalizasyonu | Aksan, noktalama ve sıra farkları aynı anahtara iner | Must (MVP) |
| 05.2.1 | Harf çevirisi | Kiril ve Arap yazımlar Latin karşılığına çevrilir; orijinal yazım da saklanır | Must (MVP) |
| 05.3.1 | MRZ ayrıştırma | TD1, TD2, TD3 biçimleri ayrıştırılır | Must (MVP) |
| 05.3.2 | MRZ kontrol hanesi doğrulaması | Kontrol hanesi tutmayan MRZ geçersiz sayılır | Must (MVP) |
| 05.3.3 | MRZ önceliği | Görünen metinle MRZ çelişirse MRZ kazanır ve çelişki nota yazılır | Must (MVP) |
| 05.4.1 | Kişi anahtarı | Belge numaraları, normalize ad-soyad, doğum tarihi ve orijinal yazımdan oluşan anahtar üretilir | Must (MVP) |
| 05.5.1 | Eşleştirme sırası | Önce belge numarası, sonra normalize isim + doğum tarihi denenir | Must (MVP) |
| 05.5.2 | Yalnız isim eşleşmesinin reddi (R8) | Sadece isim eşleşmesi Unresolved'a gider, otomatik eşleştirme sayılmaz | Must (MVP) |
| 05.5.3 | Belirsiz eşleşme | Birden fazla çalışan eşleşirse Unresolved'a gider ve olay loguna yazılır | Must (MVP) |
| 05.6.1 | Otomatik çalışan oluşturma (R9) | Yalnız temiz okunmuş belge numarası varsa yeni çalışan ve klasörü açılır | Must (MVP) |
| 05.7.1 | Onay bekleyen profil | Numara yoksa profil önerisi Unresolved'a düşer; onaysız çalışan oluşmaz | Must (MVP) |
| 05.7.2 | Alias ve numara birikimi | Her eşleşmede görülen yeni isim yazımı ve belge numarası çalışana eklenir | Must (MVP) |

### FR-MOD-06 — Plan ve doğrulayıcılar (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 06.1.1 | Plan JSON üretimi (R10) | Her belge adayı için kaynak, işlem, hedef, çalışan ve rota taşıyan plan öğesi üretilir | Must (MVP) |
| 06.1.2 | Plan determinizmi | Aynı analiz sonuçlarından iki kez üretilen plan aynı hash'i verir | Must (MVP) |
| 06.2.1 | İşlem seçimi | passthrough / extract / merge / wrap_image / extract_image / render_image doğru koşullarda seçilir | Must (MVP) |
| 06.3.1 | Direkt Belge kuralı (R5) | Direkt türlerde birleştirme, sarma ve render yasaklanır; sayfa çıkarma serbesttir | Must (MVP) |
| 06.3.2 | Direkt Belge format kontrolü | Kaynak türü beklenen dosya türleri arasında değilse Unresolved ve "uygun formatta yeniden gönderin" notu | Must (MVP) |
| 06.4.1 | Dönüşüm izni kontrolü | Türün izinli dönüşüm listesinde olmayan dönüşüm plana girmez | Must (MVP) |
| 06.5.1 | Doğrulayıcı seti | required_fields, page_count, sides, direct_single_source, file_type, mrz_checksum, dob_plausible doğrulayıcıları çalışır | Must (MVP) |
| 06.5.2 | Doğrulama başarısızlığı | Başarısız doğrulama rotayı Unresolved yapar ve gerekçe yazılır | Must (MVP) |
| 06.6.1 | Planı yeniden çalıştırma | Mevcut plan yeniden uygulanır; yapay zekâ çağrılmaz; ikinci kopya üretilmez | Must (MVP) |
| 06.6.2 | Yeniden analiz ve sürüm | Yeniden analiz yeni plan sürümü açar; eski çıktılar silinmez, "eski sürüm" işaretlenir | Must (MVP) |

### FR-MOD-07 — Uygulayıcı (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 07.1.1 | passthrough | Kaynak dosya bayt bayt kopyalanır; hash aynı kalır | Must (MVP) |
| 07.2.1 | extract | Sayfa nesneleri yeniden render edilmeden kopyalanır; metin katmanı korunur | Must (MVP) |
| 07.3.1 | merge | Yalnız `direct: false` türlerde, birden çok kaynaktan sayfa sırayla birleştirilir | Must (MVP) |
| 07.4.1 | wrap_image | JPEG/PNG kayıpsız biçimde PDF'e sarılır; görüntü yeniden kodlanmaz | Must (MVP) |
| 07.5.1 | extract_image | PDF sayfasındaki gömülü görüntü orijinal baytlarıyla çıkarılır | Must (MVP) |
| 07.6.1 | render_image | Yalnız izinli türlerde, sabit çözünürlükle JPEG üretilir | Must (MVP) |
| 07.7.1 | Çıktı yazma ve köken (R13) | Çıktı `Hazir/` altına atomik yazılır; kaynak dosya ve sayfa aralığı kaydedilir | Must (MVP) |
| 07.7.2 | Alinan kopyası | Kaynak dosya çalışanın `Alinan/` klasörüne kopyalanır; aynı hash tekrar kopyalanmaz | Must (MVP) |
| 07.8.1 | İdempotenlik | Aynı plan ikinci kez uygulanınca ikinci dosya üretilmez | Must (MVP) |

### FR-MOD-08 — Kuyruklar ve çözüm (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 08.1.1 | Kuyruğa yönlendirme (R7) | Unknown/Unreadable/Unresolved klasörüne kaynak kopyası ve gerekçe dosyası yazılır | Must (MVP) |
| 08.1.2 | Gerekçe içeriği | Gerekçe hangi sayfalar, hangi kural, hangi tür ve kişi tahmini olduğunu içerir | Must (MVP) |
| 08.2.1 | Kuyruk öğesini çalışana atama | Atama sonrası çıktı üretilir ve yapay zekâ çağrılmaz | Must (MVP) |
| 08.3.1 | Onay bekleyen profili onaylama | Onay sonrası çalışan oluşur ve belge ona bağlanır | Must (MVP) |
| 08.4.1 | Arşive taşıma (R11) | Belge silinmez, `Archive/<yyyy-mm>/` altına taşınır ve durumu güncellenir | Must (MVP) |

### FR-MOD-09 — Çalışan profili ve orkestrasyon (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 09.1.1 | profil.md üretimi | YAML ön blok + kimlik tablosu + belge listesi içerir; her değişiklikten sonra yeniden üretilir | Must (MVP) |
| 09.1.2 | Orijinal yazım gösterimi | Latin olmayan isimlerde hem Latin hem orijinal yazım görünür | Must (MVP) |
| 09.2.1 | Parti durum makinesi | received → rendering → analyzing → planning → executing → done/partial/failed geçişleri izlenebilir | Must (MVP) |
| 09.2.2 | Uçtan uca orkestrasyon | Tek çağrıyla parti baştan sona işlenir | Must (MVP) |
| 09.2.3 | Hata dayanıklılığı | Beklenmeyen hatada parti `failed` olur, dosyalar Inbox'ta kalır, hata loglanır | Must (MVP) |
| 09.3.1 | Sentetik belge üreteci | Testler gerçek belge kullanmadan çalışır; sahte MRZ dahil belge üretilir | Must (MVP) |
| 09.3.2 | Kabul senaryosu testleri | §9'daki S1–S15 ve S18 otomatik test olarak vardır ve geçer | Must (MVP) |

### FR-MOD-10 — Web yönetim paneli (Faz 1)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 10.1.1 | Panel iskeleti ve gezinme | Yükle, Çalışanlar, Kuyruklar, Belge Türleri, Yüklemeler menüleri açılır | Must (v1) |
| 10.1.2 | Oturum tabanlı giriş | Girişsiz hiçbir panel yolu açılmaz | Must (v1) |
| 10.1.3 | İlk kullanıcı oluşturma | Komut satırından ilk yönetici oluşturulabilir | Must (v1) |
| 10.2.1 | Yükleme sayfası | Sürükle-bırak çoklu yükleme çalışır; isteğe bağlı çalışan seçilebilir | Must (v1) |
| 10.2.2 | İlerleme görünümü | Yükleme sonrası parti durumu canlı yenilenir | Should (v1) |
| 10.3.1 | Yükleme detay sayfası | Sayfa küçük resimleri, plan öğeleri, çıktılar ve olay zaman çizelgesi tek sayfada görünür | Must (v1) |
| 10.3.2 | Yeniden çalıştır / yeniden analiz | İki işlem panelden tetiklenir; yeniden analiz iki aşamalı onay ister | Should (v1) |
| 10.4.1 | Çalışan listesi | Ad, orijinal yazım, uyruk, belge sayısı ve durum listelenir | Must (v1) |
| 10.4.2 | Arama | Ad, alias, orijinal yazım, belge numarası ve belge türü üzerinde arama çalışır | Must (v1) |
| 10.5.1 | Çalışan profili sayfası | CV benzeri kart: fotoğraf, kimlik bilgileri, belge numaraları | Must (v1) |
| 10.5.2 | Belge listesi ve açma | Belgeye tıklayınca yeni sekmede açılır; indirilebilir; düzenlenemez | Must (v1) |
| 10.5.3 | Profil sayfasından yükleme | Yükleme bağlam çalışanıyla yapılır | Should (v1) |
| 10.6.1 | Belge geçmişi | Bir çıktının kaynak dosya ve sayfaları tıklanarak izlenir | Must (v1) |
| 10.7.1 | Kuyruk ekranları | Üç kuyruk sekmesi, sayaçlar, öğe detayı ve sayfa görüntüleri | Must (v1) |
| 10.7.2 | Kuyruktan çalışana atama | Arama ile çalışan seçilir, iki aşamalı onayla atanır | Must (v1) |
| 10.7.3 | Kuyruktan profil oluşturma | Önerilen profil düzenlenip onaylanabilir; belge içeriği düzenlenemez | Must (v1) |
| 10.8.1 | İki aşamalı onay mekanizması | Birinci ve ikinci onay metinleri gösterilir; sunucu tek kullanımlık belirteç ister | Must (v1) |
| 10.8.2 | Belgeyi başka çalışana taşıma | İki onay verilmeden işlem gerçekleşmez; iki profil de güncellenir; olay kullanıcı adıyla loglanır | Must (v1) |
| 10.9.1 | İçerik düzenlemenin yokluğu (R12) | Panelde belge içeriği düzenleyen hiçbir yol yoktur | Must (v1) |
| 10.9.2 | Görüntüleme ve indirme logu | Her açma ve indirme kullanıcı ve zamanla kaydedilir | Should (v1) |

### FR-MOD-11 — Belge türü kataloğu ve öğrenme (Faz 1 · Faz 2)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 11.1.1 | Katalog yönetim ekranı | Tür oluşturma, düzenleme ve pasifleştirme panelden yapılır | Must (v1) |
| 11.1.2 | Katalog form doğrulaması | Direkt türde dönüşüm listesi boş, front_back türde sayfa aralığı 2 olmalı | Must (v1) |
| 11.2.1 | Örnek belge yükleme | Türe örnek yüklenir; örnekler çalışan verisinden ayrı tutulur ve aramada görünmez | Should (v1) |
| 11.3.1 | Tür açıklaması üretimi | Örneklerden yapılandırılmış tür açıklaması üretilir ve düzenlenebilir | Should (v1) |
| 11.4.1 | Prompt derleyici | Aktif türler kompakt katalog metnine derlenir | Must (v1) |
| 11.4.2 | Token bütçesi | Katalog metni sınırı aşarsa açıklamalar kısaltılır ve uyarı loglanır | Should (v1) |
| 11.5.1 | Aday tür listesi | Aday türler adı, görülme sayısı ve örnek sayfalarıyla listelenir | Must (v1) |
| 11.5.2 | Aday türü onaylama | Onay sonrası tür katalogda; iki aşamalı onay istenir | Must (v1) |
| 11.5.3 | Onay sonrası yeniden analiz | Aday ile ilişkili Unknown öğeleri toplu yeniden analiz edilebilir | Should (v1) |
| 11.5.4 | Aday türü reddetme | Reddedilen aday tekrar listeye düşmez | Should (v1) |
| 11.6.1 | Profil fotoğrafı kural seti | Kurallar katalogda tutulur ve panelden açılıp kapatılabilir | Should (v2) |
| 11.7.1 | Fotoğraf görsel kontrolü | Her kural pass/fail/unsure olarak değerlendirilir; fail varsa Unresolved | Should (v2) |
| 11.7.2 | Fotoğrafta içerik korunması | Kırpma, düzeltme ve arka plan değiştirme yapılmaz | Should (v2) |
| 11.8.1 | Fotoğraf örneklerinden öğrenme | Kabul edilen fotoğraflar örnek işaretlenir ve açıklamayı besler | Could (v3) |

### FR-MOD-12 — Telegram botu (Faz 2)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 12.1.1 | Bot iskeleti | Bot ayrı servis olarak çalışır; geliştirmede polling, üretimde webhook | Should (v2) |
| 12.1.2 | Kullanıcı beyaz listesi | Listede olmayan kullanıcıya yanıt verilmez | Should (v2) |
| 12.2.1 | Belge alma | Gönderilen belge web ile aynı boru hattından işlenir | Should (v2) |
| 12.2.2 | Çoklu mesaj grubu | Aynı medya grubundaki dosyalar tek parti sayılır | Should (v2) |
| 12.2.3 | Sonuç özeti | İşlem sonucu ve kuyruğa düşen öğeler kısa mesajla bildirilir | Should (v2) |
| 12.3.1 | Belge isteme | "Ahmet Çakar'ın ehliyetini göster" isteği doğru belgeyi bulur | Should (v2) |
| 12.3.2 | Belirsizlikte seçim | Birden fazla sonuçta kullanıcıdan seçim istenir | Should (v2) |
| 12.3.3 | Erişim kaydı | Bot üzerinden gönderilen her belge erişim loguna yazılır | Should (v2) |
| 12.4.1 | Kuyruk ve hata bildirimi | Kuyruğa yeni öğe düşünce ve parti başarısız olunca bildirim gider | Could (v3) |

### FR-MOD-13 — İşletme, maliyet ve dayanıklılık (Faz 3)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 13.1.1 | Maliyet ölçümü | Sayfa, parti ve ay bazında token ve maliyet görünür | Could (v3) |
| 13.2.1 | Ucuz model ön eleme | Kolay sayfalar ucuz modele yönlendirilir; test matrisi doğruluğu düşmez | Could (v3) |
| 13.2.2 | Metin katmanı önceliği | Metin katmanı olan sayfalarda görüntü çözünürlüğü düşürülür | Could (v3) |
| 13.3.1 | Kalıcı işçi kuyruğu | Uygulama yeniden başlayınca yarım kalan parti kaybolmaz | Could (v3) |
| 13.4.1 | Erişim logu görünümü | Çalışan bazında kim ne zaman baktı görülebilir | Could (v3) |
| 13.4.2 | Yedekleme ve geri yükleme | Gece yedeği alınır; geri yükleme prosedürü bir kez denenmiştir | Could (v3) |
| 13.5.1 | Üretim dağıtımı | Alan adı ve HTTPS ile tek komutla dağıtım yapılır | Could (v3) |
| 13.6.1 | İzleme ve uyarı | Hata, disk doluluğu ve kuyruk uzunluğu için uyarı üretilir | Could (v3) |

---

## 7. Fonksiyonel olmayan gereksinimler

| ID | Gereksinim | Kabul kriteri |
|---|---|---|
| NFR-01 | Gizlilik | Gerçek çalışan belgesi hiçbir zaman depoya girmez; testler sentetik belgelerle çalışır |
| NFR-02 | İzlenebilirlik | Her çıktı için kaynak dosya ve sayfa aralığı sorgulanabilir |
| NFR-03 | Determinizm | Karar dışı tüm işlemler aynı girdiyle aynı çıktıyı üretir |
| NFR-04 | Çok dillilik | Latin, Kiril ve Arap alfabeli belgeler işlenir |
| NFR-05 | Taşınabilirlik | Geliştirmede SQLite, üretimde PostgreSQL aynı kodla çalışır |
| NFR-06 | Test edilebilirlik | Yapay zekâ çağrıları kayıtlı yanıtlarla değiştirilebilir |
| NFR-07 | Kurtarılabilirlik | Orijinal dosyalar korunduğu için her çıktı yeniden üretilebilir |

---

## 8. Veri modeli

### 8.1 Tablolar

| Tablo | Amaç | Önemli alanlar |
|---|---|---|
| `employees` | Çalışan ana kaydı | id (E0001), folder_name, given_names, surname, original_script_name, date_of_birth, nationality, status, created_at |
| `employee_identifiers` | Belge numaraları | employee_id, kind, value, source_document_id |
| `employee_aliases` | Görülen isim yazımları | employee_id, raw_name, normalized_name, script |
| `uploads` | Yükleme partisi | id, channel, uploaded_by, context_employee_id, status, created_at |
| `upload_files` | Kaynak dosyalar | id, upload_id, original_name, stored_path, sha256, mime, page_count, is_duplicate_of |
| `pages` | Sayfalar | id, file_id, index, image_path, text_layer, is_blank, has_single_embedded_image, analysis_json, analysis_status |
| `plans` | Dondurulmuş planlar | id, upload_id, version, json, model, plan_hash, created_at, executed_at |
| `documents` | Çıktı belgeleri | id, employee_id, type_slug, path, format, sequence_no, plan_id, source_refs_json, status, created_at |
| `queue_items` | Kuyruk öğeleri | id, upload_id, plan_item_id, kind, reason, payload_json, resolved_at, resolved_by |
| `known_document_types` | Katalog | slug, name, file_label, country, description, expected_file_types, expected_pages_min, expected_pages_max, sides, direct, analyze, required_fields, allowed_conversions, output_format, prompt_description, photo_rules, active |
| `candidate_document_types` | Aday türler | id, proposed_name, normalized_name, description, first_seen_upload_id, sample_page_ids, seen_count, status |
| `events` | Olay logu | id, ts, upload_id, file_id, page_index, document_id, employee_id, actor, type, message, data_json |
| `access_log` | Görüntüleme ve indirme | ts, user_id, document_id, action, channel |
| `users` | Panel kullanıcıları | id, username, password_hash, role |
| `telegram_users` | Beyaz liste | telegram_id, user_id, allowed |

### 8.2 Veri dizini

```
data/
  Inbox/<upload_id>/              orijinaller, değişmez
  Employees/<Ad_Soyad_E0001>/
      Alinan/                     bu çalışana ait orijinallerin kopyası
      Hazir/                      çıktı belgeleri ve Attachment dosyaları
      profil.md                   sistem üretir, elle düzenlenmez
  Unknown/<upload_id>/            kaynak kopyası + reason.json
  Unreadable/<upload_id>/         kaynak kopyası + reason.json
  Unresolved/<upload_id>/         kaynak kopyası + reason.json
  Archive/<yyyy-mm>/              arşive taşınanlar
  KnownDocuments/
      catalog.yaml                tohum ve dışa aktarım
      examples/<tur_slug>/        örnek belgeler
  cache/pages/<file_id>/          analiz için üretilmiş sayfa görüntüleri
```

### 8.3 Olay türleri

FILE_UPLOADED · FILE_DUPLICATE · PAGE_RENDERED · PAGE_BLANK · PAGE_ANALYZED ·
PAGE_ANALYSIS_FAILED · PAGE_UNREADABLE · DOC_TYPE_DETERMINED · DOC_TYPE_UNKNOWN ·
CANDIDATE_TYPE_PROPOSED · PERSON_IDENTIFIED · PERSON_MATCHED · PERSON_NOT_MATCHED ·
PERSON_AMBIGUOUS · EMPLOYEE_CREATED · EMPLOYEE_PENDING · PLAN_CREATED · VALIDATION_FAILED ·
DIRECT_DOC_CHECK · PAGE_EXTRACTED · PAGES_MERGED · IMAGE_WRAPPED · IMAGE_EXTRACTED ·
IMAGE_RENDERED · OUTPUT_SAVED · OUTPUT_SKIPPED · QUEUED_UNKNOWN · QUEUED_UNREADABLE ·
QUEUED_UNRESOLVED · MANUAL_MOVE · MANUAL_ASSIGN · MANUAL_APPROVE · TYPE_APPROVED ·
TYPE_REJECTED · USER_CONFIRMED · PLAN_RERUN · PLAN_REANALYZED · ARCHIVED · PIPELINE_FAILED

### 8.4 Sayfa analizi şeması

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
    "mrz_lines": ["...", "..."]
  },
  "fields": {
    "surname": {"value": "VASILIEV", "legible": true},
    "document_number": {"value": "71 1234567", "legible": true},
    "expiry_date": {"value": null, "legible": false}
  },
  "notes": "Alt kenar hafif bulanık."
}
```

`side`: front · back · single · unknown. `document_type_slug` katalogda bir slug veya null.
`candidate_type_name` yalnız slug null iken dolar.

### 8.5 Plan JSON şeması

```json
{
  "upload_id": "u_20260905_0001",
  "version": 1,
  "model": "claude-sonnet-5",
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
      "validations": [{"name": "required_fields", "ok": true}]
    }
  ]
}
```

`operation`: passthrough · extract · merge · wrap_image · extract_image · render_image.
`route`: hazir · unknown · unreadable · unresolved · skip.
`employee.action`: match · create · pending · none.

### 8.6 Katalog kaydı

```yaml
- slug: russian_passport
  name: Russian Passport
  file_label: Passport
  country: RU
  expected_file_types: [pdf, jpeg]
  expected_pages: {min: 1, max: 1}
  sides: single
  direct: true
  analyze: true
  required_fields: [surname, given_names, date_of_birth, document_number, expiry_date]
  allowed_conversions: []
  output_format: keep
  prompt_description: >
    Kiril ve Latin çift yazımlı kimlik sayfası, sağ altta iki satır MRZ.
```

---

## 9. Kabul senaryoları

Her senaryo Faz 0'da otomatik test olur (09.3.2). "Beklenen" sütunu tartışmasızdır.

| No | Senaryo | Beklenen |
|----|---------|----------|
| S1 | Tek sayfalık Rus pasaportu PDF; numara kayıtlı çalışanla eşleşiyor | `Hazir/Ad_Soyad-Passport.pdf` passthrough; Alinan'a kopya; olay zinciri tam |
| S2 | S1 dosyası ikinci kez yükleniyor | Tekrar tespit edilir; ikinci çıktı üretilmez; analiz çağrısı yok |
| S3 | 6 sayfalık PDF: ehliyet ön, foto, başka belge, oturum ön, oturum arka, ehliyet arka | Residence-Card.pdf (4-5); Profile-Picture.jpeg (2); ehliyet 1 ve 6 Unresolved (R6); sayfa 3 türüne göre Hazir veya Unknown |
| S4 | 5 sayfalık sıralı PDF: ehliyet ön, ehliyet arka, foto, oturum ön, oturum arka | Üç bağımsız çıktı üretilir |
| S5 | Aynı partide `on.jpg` ve `arka.jpg` ehliyet (direkt kapalı) | Tek Driving-License.pdf; kayıpsız sarma ve birleştirme |
| S6 | Pasaport (direkt açık) JPEG geldi; katalog yalnız PDF bekliyor | Unresolved; "uygun formatta yeniden gönderin"; dönüşüm yapılmaz |
| S7 | Pasaport sayfası çok sayfalı PDF içinde | Tek sayfa extract ile Passport.pdf; render yok |
| S8 | PDF ortasında boş sayfa | Atlanır; hata değil |
| S9 | Bulanık pasaport; belge numarası okunamıyor | Unreadable; "Okunamayan alanlar: document_number" |
| S10 | Belge yalnız isimle mevcut çalışanla eşleşiyor | Unresolved; otomatik eşleştirme ve yeni çalışan yok |
| S11 | Temiz pasaport numarası; kayıtlı çalışan yok | Yeni çalışan, klasör ve profil.md; belge Hazir'da |
| S12 | Aynı isimli iki çalışan; doğum tarihi birine uyuyor | O çalışana eşleşir; her ikisine veya hiçbirine uymuyorsa Unresolved |
| S13 | Kiril isimli belge | Latin dosya adı + orijinal yazım profilde |
| S14 | Katalogda olmayan tür (Peru diploması) | Unknown + aday tür; onay ve yeniden analizden sonra Hazir |
| S15 | Word CV: profil sayfasından / genel yüklemeden | `Hazir/...Attachment...docx` değişmeden / Unresolved |
| S16 | Manuel taşıma tek onayla / iki onayla | Değişiklik yok / taşınır, iki profil güncellenir, olay kullanıcı adıyla |
| S17 | Telegram: iki ehliyet / tek ehliyet | Seçim sorusu / dosya gönderilir |
| S18 | Mevcut plandan yeniden çalıştırma | Aynı çıktılar; sağlayıcı çağrılmaz; ikinci dosya yok |

---

## 10. Kapsam dışı

Aşağıdakiler bu üründe **yapılmayacaktır**:

- Belge içeriğini düzenleme, doldurma, imzalama veya damgalama.
- Sahtecilik tespiti ve belge doğrulama (resmî kurum sorgusu). İlk aşamada gelen belgenin
  içerik olarak doğru olduğu varsayılır.
- Görüntü iyileştirme: kırpma, döndürme (EXIF dışında), kontrast düzeltme, arka plan temizleme.
- Word ve Excel içeriğinin analizi veya başka formata dönüştürülmesi.
- Optik karakter tanıma için ayrı bir OCR altyapısı kurulması (analiz çok modlu modelle yapılır).
- Çalışanın kendi kendine belge yüklemesi için portal.
- Bordro, izin, performans gibi İK süreçleri.
- Mobil uygulama.
- Çoklu şirket (multi-tenant) mimarisi.
- Uygulama düzeyinde dosya şifreleme (disk şifreleme sunucu düzeyinde yapılır).

---

## 11. Karmaşıklık değerlendirmesi

`[MAX]` etiketi alacak işler — yüksek belirsizlik, çok sayıda kenar durum veya geri alınması
pahalı kararlar içerdiği için en yüksek efor seviyesinde çalıştırılmalıdır:

| Gereksinim | Neden zor |
|---|---|
| 04.1.1, 04.2.1, 04.3.1 | Gruplama ve ardışıklık kuralı boru hattının en kritik mantığı; yanlış birleştirme belge bütünlüğünü bozar |
| 05.3.1, 05.3.2 | MRZ üç ayrı biçim ve kontrol hanesi aritmetiği içerir |
| 05.5.1, 05.5.2, 05.6.1 | Eşleştirme sırası yanlış kurulursa hayalet çalışan veya yanlış birleştirme doğar |
| 06.2.1, 06.3.1 | İşlem seçimi ile Direkt Belge kuralının kesişimi çok sayıda kombinasyon üretir |
| 07.2.1, 07.3.1, 07.5.1 | PDF sayfa nesnesi kopyalama ve gömülü görüntü çıkarma kayıpsız olmak zorunda |
| 10.7.1, 10.7.2, 10.7.3 | Kuyruk ekranları üç farklı çözüm akışını ve iki aşamalı onayı birleştirir |
| 12.3.1 | Doğal dil isteğinin araç çağrılarına çevrilmesi belirsizlik yönetimi ister |

Diğer tüm işler `[XHIGH]` seviyesindedir.

Orta zorlukta ama dikkat isteyen işler: 00.4.2 (üç alfabede slug), 02.1.1 (DPI ve maliyet
dengesi), 03.4.1 (prompt disiplini), 06.1.2 (plan determinizmi), 09.3.1 (sentetik belge üreteci).
