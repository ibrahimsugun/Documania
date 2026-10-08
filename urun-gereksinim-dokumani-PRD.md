# Ürün Gereksinim Dokümanı — Akıllı Çalışan Belge Yönetim ve Otomasyon Sistemi

| | |
|---|---|
| **Ürün kodu** | Documania (eski adı: belgeee) |
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
| İK yöneticisi | Web paneli, haftalık | Çalışan profillerini gör, eksik belgeleri gör |

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
| R8 | **İsim tek başına kimlik değildir.** Yalnız ad-soyad eşleşmesi otomatik eşleştirme sayılmaz. Tek istisna (05.5.4): doğum tarihi taşımayan belge (sözleşme, CV, diploma gibi) ad-soyadıyla **tek bir** etkin çalışana uyuyorsa o çalışana yerleşir; isim yoluyla eşleşen belge profile kimlik bilgisi (isim yazımı, belge numarası, profil alanı, iletişim) eklemez ve profilde "yalnız isimle eşleşti" diye görünür. |
| R9 | **Yalnız isimden çalışan doğmaz.** Kayıtlı çalışanla eşleşme yoksa otomatik yeni çalışan profili yalnız temiz okunmuş bir belge numarası varsa, ya da Latin harfli ad-soyad ile okunaklı doğum tarihi varsa (doğum tarihi türün zorunlu alanıysa) açılır. Yalnız ad-soyad okunduysa profil onaya düşer. |
| R10 | **Karar bir kez verilir.** Yapay zekâ analizi Plan JSON olarak dondurulur; fiziksel işlemler bu plandan yürütülür, yeniden yapay zekâya sorulmaz. |
| R11 | **Sistem kendiliğinden silmez; kalıcı silme yalnız İK'nın elindedir.** Günlük düzen arşivle yürür. İK bir belgeyi (10.5.12) ya da işten ayrılan, pasife alınmış bir çalışanı bütün belgeleriyle (10.5.13) iki aşamalı onayla kalıcı siler: dosyalar diskten, kişisel veriler veritabanından gider; kayıt iskeleti (E numarası, belge kimliği, tür, tarih, kim sildi) "silindi" durumuyla kalır, olay ve erişim logu kırılmaz. Telegram kimlik kaydı da silinebilir (12.1.10): numara başka hesaba bağlanabilsin diye kayıt silinir, izi olay logunda kalır. |
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
| Dosya etiketi | Türün ülkeden bağımsız adı (`file_label`, örn. Passport); çıktı adında (K8) ve belge grubu kalemi eşleşmesinde (14.1.2) kullanılır |
| Belge grubu | Bir süreç için gereken belge kalemlerinin adlandırılmış listesi (örn. "Sırbistan iş başvurusu": fotoğraf, pasaport, kimlik, çevirili diploma) |
| Belge paketi | Bir belge grubunun bir çalışana tanımlanmış örneği; kalemleri çalışanın etkin belgeleriyle karşılanır, hepsi karşılanınca paket tamamlanır |

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

Kapsam: FR-MOD-10, FR-MOD-11 (11.1–11.5, 11.9), FR-MOD-14.

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

**Kapanış ölçütü:** Sunucuda alan adıyla çalışıyor; yedekten geri yükleme bir kez denendi.

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
| 00.6.1 | Katalog şeması ve tutarlılık kuralı | §8.6'daki tüm alanlar tanımlıdır (`acceptance_criteria` dahil); `direct: true` olan türde dönüşüm listesi doluysa katalog yüklemesi reddedilir | Must (MVP) |
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
| 03.1.2 | Dil ve alfabe tespiti | Her sayfa için `language` (ISO 639-1) ve `script` (`latin`, `cyrillic`, `arabic`, `other`) alanları döner; tanımlı küme dışında değer reddedilir | Must (MVP) |
| 03.1.3 | Diğer isimler alanı | İkinci ad, baba adı gibi ek isimler `other_names` alanında ayrı olarak döner ve çalışan kaydına taşınır | Must (MVP) |
| 03.1.4 | İletişim bilgisi alanları | Belgede telefon, e-posta veya adres varsa `contact` alanında döner; yoksa `null`, uydurulmaz | Must (MVP) |
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
| 04.1.2 | Ön/arka yüz yapısı | `front_back` türlerde ön ve arka sayfa sıralı biçimde eşleşir; türün kabul ettiği düzende iki yüzü birlikte taşıyan tek sayfa (`front_and_back`) tek başına tam belgedir | Must (MVP) |
| 04.2.1 | Ardışıklık güvenlik kuralı (R6) | Araya başka belge girmiş parçalar otomatik birleştirilmez, gerekçesiyle Unresolved'a gider | Must (MVP) |
| 04.3.1 | Dosyalar arası gruplama | Yalnız `direct: false` türlerde, aynı partideki ayrı dosyalardaki ön ve arka yüz eşleştirilir | Must (MVP) |
| 04.3.2 | Belirsiz eşleştirmenin reddi | Aynı türden birden fazla ön yüz varsa eşleştirme yapılmaz, hepsi Unresolved'a gider | Must (MVP) |
| 04.4.1 | Zorunlu alan okunaklılık kapısı (R1) | Zorunlu alanların biri bile okunaksızsa aday Unreadable olur ve eksik alan adları gerekçeye yazılır | Must (MVP) |
| 04.4.2 | Kabul kriteri değerlendirmesi | Türün `acceptance_criteria` maddeleri varsa her biri değerlendirilir; karşılanmayan madde Unresolved gerekçesine madde adıyla yazılır. Liste boşsa tek ölçüt 04.4.1'dir | Should (v1) |
| 04.5.1 | Beklenen sayfa sayısı kontrolü | Aday, türün sayfa aralığı dışındaysa Unresolved olur | Must (MVP) |
| 04.6.1 | Bilinmeyen tür → aday öneri | Katalogda olmayan belge zorla bir türe atanmaz; aday tür olarak kaydedilir ve Unknown'a gider | Must (MVP) |
| 04.7.1 | Word/Excel yolu (Attachment) | Word ve Excel analiz edilmez, dönüştürülmez; bağlam çalışanı varsa Hazir'a olduğu gibi kaydedilir, yoksa Unresolved'a gider | Must (MVP) |

### FR-MOD-05 — Kimlik ve çalışan eşleştirme (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 05.1.1 | İsim normalizasyonu | Aksan, noktalama ve sıra farkları aynı anahtara iner | Must (MVP) |
| 05.2.1 | Harf çevirisi | Kiril ve Arap yazımlar Latin karşılığına çevrilir; orijinal yazım da saklanır | Must (MVP) |
| 05.2.2 | Latin ad ve orijinal yazım ayrımı | Çalışanın ad, soyad ve diğer isim alanları yalnız Latin harfleriyle tutulur ve listede, profilde, planda Latin görünür; ismin **belgede basılı hâli — alfabesi ne olursa olsun, Latin de dahil —** "Orijinal yazım"da birebir durur (belgedeki yazım, büyük/küçük harf ve alan sırası korunur). Latin yazım önce belgede basılı Latin addan, sonra geçerli MRZ'den, bunlar yoksa yalnız Kiril için kural tabanlı çeviriden alınır; Arap ve diğer alfabelerde tahminle çeviri yapılmaz | Must (MVP) |
| 05.3.1 | MRZ ayrıştırma | TD1, TD2, TD3 biçimleri ayrıştırılır | Must (MVP) |
| 05.3.2 | MRZ kontrol hanesi doğrulaması | Kontrol hanesi tutmayan MRZ geçersiz sayılır | Must (MVP) |
| 05.3.3 | MRZ önceliği | Görünen metinle MRZ çelişirse MRZ kazanır ve çelişki nota yazılır | Must (MVP) |
| 05.4.1 | Kişi anahtarı | Belge numaraları, normalize ad-soyad, doğum tarihi ve orijinal yazımdan oluşan anahtar üretilir | Must (MVP) |
| 05.5.1 | Eşleştirme sırası | Önce belge numarası, sonra normalize isim + doğum tarihi denenir | Must (MVP) |
| 05.5.2 | Yalnız isim eşleşmesinin reddi (R8) | Sadece isim eşleşmesi Unresolved'a gider, otomatik eşleştirme sayılmaz (05.5.4'ten beri: belgede doğum tarihi okunduysa ve çalışanınkiyle aynı değilse; doğum tarihi taşımayan belgenin tekil isim eşleşmesi 05.5.4'tedir) | Must (MVP) |
| 05.5.3 | Belirsiz eşleşme | Birden fazla çalışan eşleşirse Unresolved'a gider ve olay loguna yazılır | Must (MVP) |
| 05.5.4 | Doğum tarihi taşımayan belgenin tekil isim eşleşmesi (R8 istisnası) | Belge numarasıyla eşleşmeyen ve doğum tarihi okunmamış belgenin normalize ad-soyadı (§20.2.1) birleştirilmemiş tek bir çalışana uyuyorsa ve o çalışan etkinse belge o çalışanın Hazir'ına yerleşir (`matched_by: name`, §20.2.2 satır 5a). İsim birden çok çalışana uyarsa Unresolved (`PERSON_AMBIGUOUS`); çalışan pasifse 10.5.7 kuralı; belgede doğum tarihi okunduysa satır 3/5 geçerlidir. İsim yoluyla eşleşen belge çalışana isim yazımı, belge numarası, profil alanı ya da iletişim bilgisi eklemez (05.7.2, 05.7.3, 05.8.1 uygulanmaz) ve aynı dosyadaki kişisiz sayfalara sahip vermez. Profilin belge listesinde ve yükleme ayrıntısında bu belge "yalnız isimle eşleşti" etiketiyle görünür; yanlışsa İK 10.8.1 ile taşır. Kabul senaryosu S23 | Should (v1) |
| 05.6.1 | Otomatik çalışan oluşturma (R9) | Kayıtlı çalışanla eşleşmeyen kişide temiz okunmuş belge numarası varsa yeni çalışan ve klasörü açılır | Must (MVP) |
| 05.6.2 | Ad ve doğum tarihiyle otomatik çalışan oluşturma (R9) | Kayıtlı çalışanla eşleşmeyen kişide temiz numara yoksa, Latin harfli ad-soyad ve okunaklı, tekil, çelişkisiz doğum tarihi varsa ve doğum tarihi türün zorunlu alanıysa yeni çalışan ve klasörü açılır; belge numarası yazılmaz; olay kaydı açılış dayanağını (`document_number` / `name_dob`) taşır; ucuz ön eleme modelinin doğrulanmamış okuması bu yola dayanak olmaz (§20.2.4) | Must (MVP) |
| 05.7.1 | Onay bekleyen profil | Temiz numara yoksa ve 05.6.2 uymuyorsa (doğum tarihi yok, okunaksız ya da türün zorunlu alanı değil) profil önerisi Unresolved'a düşer; onaysız çalışan oluşmaz | Must (MVP) |
| 05.7.2 | Alias ve numara birikimi | Her eşleşmede görülen yeni isim yazımı ve belge numarası çalışana eklenir | Must (MVP) |
| 05.7.3 | Profil alanlarını belgelerden tamamlama | Eşleşen ya da yeni açılan çalışanın boş profil alanları (ad, soyad, diğer isimler, orijinal yazım, doğum tarihi, uyruk) belgede okunaklı okunan değerlerle doldurulur, MRZ önce gelir; dolu alan değiştirilmez, farklı değer profilde uyarı olarak görünür; her alanın kaynağı belgeye bağlanır | Must (MVP) |
| 05.8.1 | İletişim bilgisi saklama | Analiz edilen belgeden çıkan telefon, e-posta ve adres `employee_contacts` tablosuna kaynak belgesiyle birlikte yazılır | Must (MVP) |
| 05.8.2 | İletişim bilgisi çakışması | Aynı türden farklı bir değer geldiğinde eski kayıt silinmez; en son görülen `is_current` işaretlenir, öncekiler geçmiş olarak kalır | Must (MVP) |
| 05.8.3 | Dil ve alfabe kaydı | Belgeden okunan dil ve alfabe belge kaydında saklanır; çalışanın belgelerinde görülen alfabeler profilde listelenebilir | Should (v1) |

### FR-MOD-06 — Plan ve doğrulayıcılar (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 06.1.1 | Plan JSON üretimi (R10) | Her belge adayı için kaynak, işlem, hedef, çalışan ve rota taşıyan plan öğesi üretilir | Must (MVP) |
| 06.1.2 | Plan determinizmi | Aynı analiz sonuçlarından iki kez üretilen plan aynı hash'i verir | Must (MVP) |
| 06.2.1 | İşlem seçimi | passthrough / extract / merge / wrap_image / extract_image / render_image doğru koşullarda seçilir | Must (MVP) |
| 06.3.1 | Direkt Belge kuralı (R5) | Direkt türlerde birleştirme, sarma ve render yasaklanır; sayfa çıkarma serbesttir | Must (MVP) |
| 06.3.2 | Direkt Belge format kontrolü | Kaynak türü beklenen dosya türleri arasında değilse Unresolved ve "uygun formatta yeniden gönderin" notu | Must (MVP) |
| 06.4.1 | Dönüşüm izni kontrolü | Türün izinli dönüşüm listesinde olmayan dönüşüm plana girmez | Must (MVP) |
| 06.5.1 | Doğrulayıcı seti | required_fields, page_count, sides, direct_single_source, file_type, mrz_checksum, dob_plausible doğrulayıcıları çalışır; bağlam çalışanlı yüklemede context_person da (10.5.5) | Must (MVP) |
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
| 08.1.3 | Şifre yüzünden kopyalanamayan kaynak | Uygulayıcı kaynağın sayfalarını şifre yüzünden kopyalayamazsa (sahip parolalı AES ya da parola korumalı PDF'ten çıkarma/birleştirme) parti `failed` olmaz: öğe kaynak kopyası ve gerekçesiyle (dosya, istenen işlem, "şifreli PDF, sayfalar kopyalanamıyor") Unreadable kuyruğuna yönlendirilir, partinin diğer öğeleri uygulanır; şifre kaldırılmaz (K11) | Should (v1) |
| 08.2.1 | Kuyruk öğesini çalışana atama | Atama sonrası çıktı üretilir ve yapay zekâ çağrılmaz | Must (MVP) |
| 08.3.1 | Onay bekleyen profili onaylama | Onay sonrası çalışan oluşur ve belge ona bağlanır | Must (MVP) |
| 08.4.1 | Arşive taşıma (R11) | Belge silinmez, `Archive/<yyyy-mm>/` altına taşınır ve durumu güncellenir | Must (MVP) |

### FR-MOD-09 — Çalışan profili ve orkestrasyon (Faz 0)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 09.1.1 | profil.md üretimi | YAML ön blok + kimlik tablosu + belge listesi içerir; her değişiklikten sonra yeniden üretilir | Must (MVP) |
| 09.1.2 | Orijinal yazım gösterimi | Her isimde hem Latin yazım hem belgedeki orijinal yazım görünür | Must (MVP) |
| 09.1.3 | Profil içeriği eksiksizliği | profil.md şunların hepsini taşır: ad, soyad, diğer isimler, orijinal yazım, vatandaşlık, doğum tarihi ve hesaplanan yaş, belge numaraları, iletişim bilgileri, belge listesi | Must (MVP) |
| 09.2.1 | Parti durum makinesi | received → rendering → analyzing → planning → executing → done/partial/failed geçişleri izlenebilir | Must (MVP) |
| 09.2.2 | Uçtan uca orkestrasyon | Tek çağrıyla parti baştan sona işlenir | Must (MVP) |
| 09.2.3 | Hata dayanıklılığı | Beklenmeyen hatada parti `failed` olur, dosyalar Inbox'ta kalır, hata loglanır | Must (MVP) |
| 09.3.1 | Sentetik belge üreteci | Testler gerçek belge kullanmadan çalışır; kontrol hanesi geçerli sahte MRZ dahil belge üretilir | Must (MVP) |
| 09.3.2 | Kabul senaryoları S1–S5 | §9'daki S1, S2, S3, S4, S5 otomatik test olarak vardır ve geçer | Must (MVP) |
| 09.3.3 | Kabul senaryoları S6–S10 | §9'daki S6, S7, S8, S9, S10 otomatik test olarak vardır ve geçer | Must (MVP) |
| 09.3.4 | Kabul senaryoları S11–S15 ve S18 | §9'daki S11, S12, S13, S14, S15, S18 otomatik test olarak vardır ve geçer | Must (MVP) |

### FR-MOD-10 — Web yönetim paneli (Faz 1)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 10.1.1 | Panel iskeleti ve gezinme | Çalışanlar, Yükle, Belge Türleri, Belge Grupları, Kuyruklar, Yüklemeler, Eğitim modu, Kullanıcılar menüleri bu sırayla açılır; panelin ana sayfası (`/`) Çalışanlar'dır | Must (v1) |
| 10.1.2 | Oturum tabanlı giriş | Girişsiz hiçbir panel yolu açılmaz | Must (v1) |
| 10.1.3 | İlk kullanıcı oluşturma | Komut satırından ilk yönetici oluşturulabilir | Must (v1) |
| 10.1.4 | Kullanıcı yönetimi | Panelde "Kullanıcılar" sayfası (yalnız yönetici): kullanıcı listesi; yeni kullanıcı (kullanıcı adı, parola, rol); kendi parolasını değiştirme; başka kullanıcının parolasını sıfırlama; pasife alma ve yeniden etkinleştirme. Pasif kullanıcı giriş yapamaz ve açık oturumları kapanır; son etkin yönetici pasife alınamaz, kullanıcı kendini pasife alamaz; kullanıcı silinmez. Her işlem kullanıcı adıyla olaya yazılır, parola hiçbir olaya girmez | Should (v1) |
| 10.1.5 | Panel sekme simgesi | Giriş dahil her panel sayfası tarayıcı sekmesinde Documania simgesini gösterir; simge dosyaları oturumsuz sunulur | Should (v1) |
| 10.1.6 | Ülke başvuru verisi ve bayrak simgeleri | Depoda ülke başvuru verisi bulunur: ISO 3166-1 alfa-2 ve alfa-3 kodu, Türkçe ülke adı ve ICAO 9303 MRZ uyruk kodlarının ülkeye eşlemesi (`D` → Almanya, `GBD`/`GBN`/`GBO`/`GBP`/`GBS` → Birleşik Krallık gibi istisnalar dahil); her ülkenin küçük bayrak simgesi (SVG) panelin statik dosyalarındadır; kaynak, lisans ve indirme tarihi depoda kayıtlıdır. Panel tek bir yardımcıyla alfa-2, alfa-3 ya da MRZ kodundan bayrak + Türkçe ad üretir; tanınmayan ya da ülke olmayan kod (vatansız `XXA`/`XXB`/`XXC`/`XXX`, BM belgeleri `UNO`/`UNA`/`UNK`) bayraksız, kodun kendisiyle gösterilir | Should (v1) |
| 10.1.7 | Panel teması: modern görünüm, açık ve koyu tema | Panelin bütün sayfaları tek bir tema dosyasıyla modern bir görünüm taşır: yumuşak degrade zemin, cam görünümlü yapışkan üst çubuk, yuvarlak köşeli kartlar ve tablolar, degrade birincil düğmeler, belirgin odak halkası, hap biçimli rozet ve sekmeler. Üst çubuktaki düğmeyle açık ve koyu tema arasında geçilir; seçim tarayıcıda hatırlanır, ilk açılışta sistem tercihi kullanılır ve sayfa yanlış temayla yanıp sönmez. Giriş sayfası kendi koyu degrade zeminini taşır. Hareket azaltma tercihi olan kullanıcıda geçiş animasyonları kapanır. Tema yalnız görünümü değiştirir; yerleşim, metin ve davranış aynı kalır | Should (v1) |
| 10.2.1 | Yükleme sayfası | Sürükle-bırak çoklu yükleme çalışır; isteğe bağlı çalışan seçilebilir | Must (v1) |
| 10.2.2 | İlerleme görünümü | Yükleme sonrası parti durumu canlı yenilenir | Should (v1) |
| 10.3.1 | Yükleme detay sayfası | Sayfa küçük resimleri, plan öğeleri, çıktılar ve olay zaman çizelgesi tek sayfada görünür | Must (v1) |
| 10.3.2 | Yeniden çalıştır / yeniden analiz | İki işlem panelden tetiklenir; yeniden analiz iki aşamalı onay ister | Should (v1) |
| 10.3.3 | Yükleme listesi | Yüklemeler menüsü partileri en yeni üstte listeler: tarih, kanal, yükleyen, bağlam çalışanı, dosya ve sayfa sayısı, durum ve kuyruğa düşen belge sayısı; durum ve tarihe göre süzülür, sayfalanır; satırdan parti detayına gidilir | Must (v1) |
| 10.3.4 | Partiyi yoksay | Yükleme detayının İşlemler bölümünde "Yeniden çalıştır" ve "Yeniden analiz et" düğmelerinin yanında "Taramayı yoksay" vardır; iki aşamalı onaydan sonra partinin bekleyen kuyruk öğeleri kapanır, parti yükleme listesinde ve kuyruklarda görünmez. Dosya, olay ve üretilmiş çıktı silinmez. Yoksayma **çalışma yüzeyinden kaldırır, öğrenileni silmez**: partinin sayfaları aday tür görülmelerinde ve örneklerinde kalır (11.5.1), sonraki tür eğitimi bu birikime dayanır | Should (v1) |
| 10.3.5 | Yoksanan partiyi geri alma | Yoksanan partinin detay sayfasındaki bildirimin yanında "Yoksaymayı geri al" vardır; tek adımda partiyi listeye geri getirir ve yoksaymayla kapanan kuyruk öğelerini yeniden açar (başka yolla çözülmüş öğe açılmaz); olay kullanıcı adıyla yazılır | Should (v1) |
| 10.4.1 | Çalışan listesi | Ad, orijinal yazım, uyruk, belge sayısı ve durum listelenir | Must (v1) |
| 10.4.2 | Arama | Ad, alias, orijinal yazım, belge numarası ve belge türü üzerinde arama çalışır | Must (v1) |
| 10.5.1 | Çalışan profili sayfası | CV benzeri kart şunların hepsini gösterir: profil fotoğrafı, ad, soyad, diğer isimler, orijinal yazım, vatandaşlık, doğum tarihi ve yaş, iletişim bilgileri, belge numaraları. Bilinmeyen alan "—" olarak görünür, gizlenmez | Must (v1) |
| 10.5.4 | Profil fotoğrafı yokluğu | Çalışanın Profile-Picture belgesi yoksa kart yer tutucu gösterir ve eksik belge olarak işaretler | Should (v1) |
| 10.5.2 | Belge listesi ve açma | Belgeye tıklayınca yeni sekmede açılır; indirilebilir; düzenlenemez | Must (v1) |
| 10.5.3 | Profil sayfasından yükleme | Yükleme bağlam çalışanıyla yapılır | Should (v1) |
| 10.5.5 | Profilden yüklemede kişi denetimi | Bağlam çalışanıyla yapılan yüklemede her belgenin kişisi profille karşılaştırılır (belge numarası, harf çevirili ad, doğum tarihi); başka kişiye ait görünen belge profile uygulanmaz, Unresolved'a gider ve yükleme ile parti ekranında büyük uyarı gösterilir | Must (v1) |
| 10.5.6 | Çalışan profilini düzenleme | Profil sayfasındaki "Profili düzenle" formu ad, soyad, diğer isimler, orijinal yazım, doğum tarihi ve uyruğu değiştirir; ad ve soyad yalnız Latin harfli olabilir (05.2.2); kaydetme iki aşamalı onay ister (K16, §D61). Ad ya da soyad değişince çalışan klasörü ve `Hazir/`, `Alinan/` altındaki dosyalar K8 adına yeniden adlandırılır, belge kayıtlarının yolu güncellenir, köken bilgisi ve E numarası değişmez; yeniden adlandırma yarıda kesilirse hiçbir şey değişmiş görünmez. Elle girilen alan "elle" kaynağıyla işaretlenir ve sonraki belge dolgusu (05.7.3) onu ezmez; olay değişen alan adlarını taşır, değerleri taşımaz; profil.md yeniden üretilir; belge içeriğine dokunulmaz (R12) | Must (v1) |
| 10.5.7 | Çalışanı pasife alma ve yeniden etkinleştirme | Profilde "Pasife al" (pasif çalışanda "Yeniden etkinleştir") iki aşamalı onayla çalışanın durumunu değiştirir; klasör, belgeler ve olaylar yerinde kalır. Pasif çalışan listede varsayılan olarak görünmez (süzgeç: Aktif / Pasif / Hepsi), profil sayfası pasif bildirimi gösterir ve profilden yükleme kapanır. Pasif çalışanla eşleşen yeni belge otomatik yerleşmez, "pasif çalışan" gerekçesiyle Unresolved'a düşer; İK öğeyi atar ya da çalışanı etkinleştirir. Olaylar kullanıcı adıyla yazılır | Must (v1) |
| 10.5.8 | Profil alt kayıtlarını kaldırma ve iletişim bilgisi ekleme | Profil sayfası görülen isim yazımlarını (alias), belge numaralarını ve iletişim bilgilerini kaynağıyla listeler; her biri iki aşamalı onayla "kaldırılır": kayıt silinmez, kaldırılmış işaretlenir, eşleştirme ve aramada kullanılmaz, "Kaldırılanlar" altında görünür ve tek adımda geri alınır. İletişim bilgisi (telefon, e-posta, adres) elle eklenebilir; elle eklenen kayıt "elle" kaynağını ve ekleyeni taşır. Olaylar kayıt türünü ve kimliğini taşır, değeri taşımaz | Should (v1) |
| 10.5.9 | İki çalışanı birleştirme | Profil sayfasındaki "Başka kayıtla birleştir" aramayla ikinci çalışanı seçtirir; İK hangi kaydın kalacağını seçer; iki aşamalı onay ister. Birleşen kaydın belgeleri kalan çalışana K8 adıyla taşınır (10.8.2 ile aynı fiziksel kural), `Alinan/` kopyaları taşınır; numaraları, isim yazımları, iletişim bilgileri, alan kaynakları ve belge paketleri kalan kayda bağlanır (aynı değer tek kalır). Birleşen kayıt `merged` durumuyla ve kalan kaydın numarasıyla kalır, listede görünmez, adresi kalan profile yönlendiren bildirim gösterir; klasörü silinmez, içinde yalnız yönlendirme notu taşıyan profil.md kalır. İşlem geri alınamaz ve ikinci onay bunu söyler; olay iki numarayı ve taşınan belge kimliklerini taşır | Should (v1) |
| 10.5.10 | Arşive taşıma ve arşivden geri alma profilde | Profil belge listesinde etkin belge için "Arşive taşı" (08.4.1, §20.6 metinleri), arşivdeki belge için "Arşivden geri al" vardır; ikisi de iki aşamalı onaylıdır. Geri alma dosyayı `Archive/<yyyy-mm>/` altından çalışanın `Hazir/` klasörüne K8 adıyla taşır (ad çakışırsa sıradaki sıra ekini alır), durumu etkin yapar, köken bilgisini korur ve olay yazar; belge içeriği değişmez | Must (v1) |
| 10.5.11 | Profilde uyruk bayrağı | Çalışan profilindeki "Vatandaşlık" satırı uyruk kodunun yanında bayrağı ve Türkçe ülke adını gösterir (örn. `RUS` → bayrak + "Rusya (RUS)"); tanınmayan kodda yalnız kod yazılır; alanın kaynak bilgisi (10.5.6) değişmez | Should (v1) |
| 10.5.12 | Belgeyi kalıcı silme | Profilin belge listesinde etkin ve arşivdeki her belge için "Kalıcı sil" iki aşamalı onayla (§20.6) çalışır. Belgenin dosyası (Hazir ya da Archive) diskten silinir; belgenin `Alinan` kopyaları, o kopyalar çalışanın başka bir belgesine kaynak değilse silinir; Inbox'taki yüklenen orijinal yalnız hiçbir başka belgeye, açık kuyruk öğesine ya da başka çalışana kaynak değilse silinir, aksi hâlde kalır ve ikinci onay metni bunu sayıyla söyler. Veritabanında belge satırı `deleted` durumuna geçer, dosya yolu ve kişisel alanları boşaltılır; kimliği, türü, çalışanı, tarihleri ve silen kalır. Belge listelerden, aramalardan, paket tiklerinden (14.x), bottan (12.3) ve dosya açma yolundan kalkar (404). Olay `DOCUMENT_DELETED` kullanıcı adıyla, kişisel değer olmadan yazılır. Geri alma yoktur. Kabul senaryosu S24 | Should (v1) |
| 10.5.13 | Çalışanı kalıcı silme | Yalnız pasif (10.5.7) çalışanın profilinde "Çalışanı kalıcı sil" iki aşamalı onayla (§20.6) çalışır; etkin ve birleştirilmiş kayıtta düğme yoktur, istek reddedilir. Çalışanın bütün belgeleri 10.5.12 kuralıyla silinir; çalışan klasörü (`Hazir`, `Alinan`, `profil.md`) diskten kalkar; isim yazımları, belge numaraları, iletişim bilgileri, profil alanı gözlemleri ve paketleri silinir; çalışanın belgelerinin kaynağı olan sayfa görüntüleri ve sayfa analizleri, başka bir çalışana ya da açık kuyruk öğesine kaynak değilse silinir/boşaltılır; çalışandan türetilmiş kabul edilmiş fotoğraf örnekleri (11.8.1) kalkar. Çalışan satırı `deleted` durumuna geçer: E numarası, oluşturma ve silme tarihi, silen kalır; ad, soyad, doğum tarihi, uyruk, klasör adı boşaltılır; E numarası yeniden verilmez (K8). Bu çalışana bağlı olayların mesajı ve verisindeki kişisel değerler temizlenir, olay satırı kalır. Silinen çalışan listede, aramada, eşleştirmede (05.5) ve botta görünmez; profil adresi "silindi" sayfası döner. Olay `EMPLOYEE_DELETED` kullanıcı adıyla ve yalnız sayılarla (belge, dosya) yazılır. Yedeklerdeki kopyalar yedeğin kendi süresiyle gider (kapsam dışı). Geri alma yoktur. Kabul senaryosu S25 | Should (v1) |
| 10.6.1 | Belge geçmişi | Bir çıktının kaynak dosya ve sayfaları tıklanarak izlenir | Must (v1) |
| 10.7.1 | Kuyruk ekranları | Üç kuyruk sekmesi, sayaçlar, öğe detayı ve sayfa görüntüleri | Must (v1) |
| 10.7.2 | Kuyruktan çalışana atama | Arama ile çalışan seçilir, iki aşamalı onayla atanır | Must (v1) |
| 10.7.3 | Kuyruktan profil oluşturma | Önerilen profil düzenlenip onaylanabilir; belge içeriği düzenlenemez | Must (v1) |
| 10.7.4 | Kuyruk öğesini kapatma ve yeniden açma | Kuyruk öğesi detayında "Öğeyi kapat" iki aşamalı onayla öğeyi çözülmüş sayar; gerekçe seçilir (belge değil / zaten var / diğer + not). Kuyruk klasöründeki kopya ve gerekçe dosyası silinmez, aday tür görülmeleri kalır (10.3.4 ile aynı kural). Kapatılan öğe "Çözülenler" görünümünde gerekçesiyle listelenir ve "Yeniden aç" ile tek adımda açılır. İki olay da kullanıcı adıyla yazılır | Must (v1) |
| 10.8.1 | İki aşamalı onay mekanizması | Onay metinleri §20.6'daki tablodan **birebir** kullanılır; sunucu tek kullanımlık belirteç ister ve belirteçsiz isteği reddeder | Must (v1) |
| 10.8.2 | Belgeyi başka çalışana taşıma | İki onay verilmeden işlem gerçekleşmez; iki profil de güncellenir; olay kullanıcı adıyla loglanır | Must (v1) |
| 10.9.1 | İçerik düzenlemenin yokluğu (R12) | Panelde belge içeriği düzenleyen hiçbir yol yoktur | Must (v1) |
| 10.9.2 | Görüntüleme ve indirme logu | Her açma ve indirme kullanıcı ve zamanla kaydedilir | Should (v1) |
| 10.10.1 | Arayüz dili: İngilizce, Türkçe, Sırpça | Panelin bütün görünen metinleri üç dilde sunulur: English (`en`), Türkçe (`tr`), Srpski (`sr`, Latin alfabesi). Giriş sayfası ve oturumsuz sayfalar İngilizce açılır; tarayıcının dil ayarı dikkate alınmaz. Sayfanın `<html lang>` özniteliği seçili dili taşır (`en`, `tr`, `sr-Latn`) | Should (v1) |
| 10.10.2 | Kullanıcının dil tercihi | Üst çubukta ve giriş sayfasında dil seçici vardır; dil adları kendi dilinde yazılır (English · Türkçe · Srpski). Girişli kullanıcı dili değiştirince seçim hesabına kaydedilir, olaya yazılır ve aynı sayfada kalınır; sonraki her girişte, hangi cihazdan olursa olsun, panel kullanıcının seçtiği dilde açılır. Tercihi olmayan hesap İngilizce açılır; giriş sayfasında seçilmiş dil, tercihi olmayan hesaba girişte kaydedilir | Should (v1) |
| 10.10.3 | Çeviri kapsamı ve bütünlüğü | Menü, sayfa ve tablo başlıkları, düğmeler, form etiketleri ve yardım metinleri, durum adları, hata ve uyarı mesajları, boş durum metinleri ve istemci tarafı (JavaScript) metinleri seçili dilde görünür; İngilizce ve Sırpça çeviri kataloğunda eksik, bulanık (fuzzy) ya da yer tutucusu kaynağıyla uyuşmayan metin bulunmaz (test). İngilizce panelde Türkçe arayüz metni kalmaz (test). Veri çevrilmez: belge türü adları ve tanımları, çalışan bilgileri, belge içeriği, dosya ve klasör adları, profil.md, olay logu ve uygulama logları, komut satırı metinleri, JSON API yanıtları. Tarih ve sayı biçimi dilden bağımsızdır | Should (v1) |
| 10.10.4 | Onay metinleri üç dilde | İki aşamalı onay metinleri (§20.6) seçili dilde gösterilir; İngilizce ve Sırpça karşılıklar §20.6.3 tablosundan **birebir** kullanılır, yer tutucular aynıdır; onay olayı (`USER_CONFIRMED`) değişmez | Should (v1) |
| 10.10.5 | Ülke adları seçili dilde | Ülke adları (10.1.6, 10.5.11, 11.1.7) seçili dilde gösterilir (CLDR `en`, `tr`, `sr-Latn`); ülke süzgecinde sıralama ve yazarak arama seçili dile göre çalışır, Türkçe ve Sırpça harfler aksansız yazılınca da bulunur | Should (v1) |

### FR-MOD-11 — Belge türü kataloğu ve öğrenme (Faz 1 · Faz 2)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 11.1.1 | Katalog yönetim ekranı | Tür oluşturma, düzenleme ve pasifleştirme panelden yapılır | Must (v1) |
| 11.1.2 | Katalog form doğrulaması | Direkt türde dönüşüm listesi boş; front_back türde en az bir düzen seçili ve sayfa aralığı seçilen düzenlerden türetilir (ayrı sayfalar 2, tek sayfa 1) | Must (v1) |
| 11.1.3 | Kabul kriteri düzenleme | Tür formunda `acceptance_criteria` maddeleri eklenip çıkarılabilir; değişiklik bir sonraki analizde geçerli olur | Should (v1) |
| 11.1.4 | Katalog tablosu okunabilirliği | Belge Türleri tablosunda slug sütunu yoktur; slug tür sayfasında ve satır bağlantısında kalır. Durum hücresi "Etkin" için yeşilimsi, "Pasif" için kırmızımsı yumuşak tonla renklenir ve metni de yazar (yalnız renge dayanmaz); "Tutarsız kayıt" rozeti kalır | Must (v1) |
| 11.1.5 | Ülkeye göre süzme | Belge Türleri sayfasında "Ülke" süzgeci vardır: bir ülke seçilince o ülkenin türleri **ve** ülkeden bağımsız (ülkesi boş) türler listelenir; "Genel" yalnız ülkesiz türleri, "Hepsi" tümünü gösterir; seçenekler katalogdaki ülkelerden tür sayısıyla üretilir; seçim bağlantılarda ve işlem sonrası yönlendirmelerde korunur; gösterilen tür sayısı yazılır; token göstergesi (11.4.3) süzgeçten etkilenmez | Must (v1) |
| 11.1.6 | Türü arşivleme, geri alma ve toplu seçim | Tür iki aşamalı onayla "arşivlenir": listeden, analiz talimatından, tür seçicilerden ve eğitim modunun bilinen türlerinden kalkar; tür kaydı ve o türe bağlı belgeler yerinde kalır, belge listeleri tür adını göstermeye devam eder; boru hattının kullandığı korunan türler (ek, profil fotoğrafı ve kodun adıyla andığı öteki sluglar) arşivlenemez. "Arşivlenen türler" görünümünden tek adımda geri alınır. Tabloda satır seçimiyle toplu "Pasifleştir / Etkinleştir / Arşivle" yapılır (arşivleme yine iki aşamalı). Etkinleştirme, pasifleştirme, arşivleme ve geri alma kullanıcı adıyla olaya yazılır | Should (v1) |
| 11.1.7 | Ülke süzgecinde ve tabloda bayrak ile ülke adı | Belge Türleri'ndeki "Ülke" süzgecinin seçenekleri bayrak + Türkçe ülke adı + tür sayısıyla, Türkçe ada göre sıralı görünür ("Hepsi" ve "Genel — ülkesiz" başta kalır); JavaScript kapalıyken süzgeç düz listeyle çalışmaya devam eder; tablodaki "Ülke" sütunu kod yerine bayrak + ad gösterir; seçim 11.1.5'teki gibi uygulanır | Should (v1) |
| 11.2.1 | Örnek belge yükleme | Türe örnek yüklenir; örnekler çalışan verisinden ayrı tutulur ve aramada görünmez. Tür sayfasından el ile yükleme olay yazmaz; Eğitim modunun (11.9) yerleştirmeleri olay yazar | Should (v1) |
| 11.3.1 | Tür açıklaması üretimi | Örneklerden yapılandırılmış tür açıklaması üretilir ve düzenlenebilir | Should (v1) |
| 11.4.1 | Prompt derleyici | Aktif türler kompakt katalog metnine derlenir | Must (v1) |
| 11.4.2 | Token bütçesi | Katalog metni sınırı aşarsa açıklamalar kısaltılır ve uyarı loglanır | Should (v1) |
| 11.4.3 | Ölçekli ve görünür katalog bütçesi | Bütçe ortam değişkeniyle ayarlanır (`CATALOG_TOKEN_BUDGET`) ve varsayılanı aktif tür sayısıyla ölçeklenir; hedef, her aktif türün analizci açıklamasının kesilmeden talimata girmesidir. Belge Türleri sayfası aktif tür sayısını, katalog metninin tahmini token sayısını ve kaç türün tanımının kesildiğini gösterir; kesilme varsa uyarı çıkar. | Should (v1) |
| 11.5.1 | Aday tür listesi | Aday türler adı, görülme sayısı ve örnek sayfalarıyla listelenir | Must (v1) |
| 11.5.2 | Aday türü onaylama | Onay sonrası tür katalogda; iki aşamalı onay istenir | Must (v1) |
| 11.5.3 | Onay sonrası yeniden analiz | Aday ile ilişkili Unknown öğeleri toplu yeniden analiz edilebilir | Should (v1) |
| 11.5.4 | Aday türü reddetme | Reddedilen aday tekrar listeye düşmez | Should (v1) |
| 11.5.5 | Aday tür incelemesi | Sistem her bekleyen adayın örnek sayfalarını (arka yüzler dahil) inceler ve tam tür taslağı üretir: ad, dosya etiketi, ülke, açıklama, dosya türleri, sayfa sayısı, yüz yapısı ve düzenleri, Direkt Belge, zorunlu alanlar (standart alan adlarıyla), kabul kriterleri (sayfada denetlenebilir, Türkçe) ve analizci için açıklama; dosya türü ve yüz yapısı gözlenen örneklerden gelir; taslakta örneklerdeki kişiye ait değer bulunursa taslak saklanmaz; inceleme yükleme işlerini bekletmez | Must (v1) |
| 11.5.6 | Onay formu taslakla dolu açılır | Aday onay formu taslaktaki bütün alanlarla açılır, İK düzeltip iki aşamalı onayla kaydeder; taslağın form doğrulamasından geçmeyen alanı boş kalır ve adıyla bildirilir; katalogdaki bir türle çakışma uyarılır; "Yeniden incele" taslağı yeniler | Must (v1) |
| 11.5.7 | Reddedilen adayı geri alma | Aday türler sayfası reddedilenleri ayrı görünümde listeler; "Geri al" adayı tek adımda yeniden bekleyen yapar ve olay yazar | Should (v1) |
| 11.9.1 | Eğitim modu sekmesi | Panelde "Eğitim modu" sekmesinden PDF/JPEG/PNG yüklenir (isteğe bağlı beklenen tür seçilir); her dosyanın sonucu (tür, yöntem, not, etiket) listelenir; eğitim yüklemesi hiçbir çalışan, kişi eşleştirmesi, kuyruk öğesi, yükleme partisi ya da çıktı belgesi oluşturmaz; yalnız bilinen belgelerin örneklerini besler | Must (v1) |
| 11.9.2 | Mekanik tanıma | Yapay zekâ çağrılmadan önce dosya türü, SHA-256 (bilinen örnekler ve envanter), beklenen/harita türünün yapı kuralları (katalog türünde dosya türü ve sayfa sayısı) ve PDF metin katmanındaki MRZ ile tanınan belge notuyla `KnownDocuments/examples/<slug>/`'a kaydedilir ve etiket almaz; aynı türde aynı dosya ikinci kez eklenmez | Must (v1) |
| 11.9.3 | Yapay zekâ incelemesi ve "AI kararı" etiketi | Mekanik tanınmayan belge yapay zekâyla sınıflandırılır ve bilinen türe (katalog türleri + hazır önerilen türler) "AI kararı" etiketiyle yerleşir; beklenen türle çelişen ya da hiçbir türe yerleşemeyen belge "Yerleştirilemedi" listesinde bekler; inceleme yükleme işlerini bekletmez | Must (v1) |
| 11.9.4 | Elle kontrol ikonu ve etiket kararı | "AI kararı" etiketli örnek eğitim sekmesinde ve tür sayfasının örnek listesinde "elle kontrol gerekli" ikonuyla görünür; İK örneği doğrular (tek ya da toplu), başka türe taşır ya da örneklerden çıkarır (silinmez, eğitim arşivine taşınır); taşıma ve çıkarma iki aşamalı onaylıdır; doğrulanmamış "AI kararı" örneği tür açıklaması üretimine girmez | Must (v1) |
| 11.9.5 | Harita yükle ve toplu tarama | Eğitim sekmesinde "Harita yükle" ile CSV (envanter ve önerilen tür biçimleri ya da slug + yol sütunlu CSV) yüklenir; önizleme satır, dosya, atlanan, mekanik hazır ve yapay zekâ gerekebilecek sayılarını gösterir; iki aşamalı onayla toplu tarama başlar ve ilerlemesi görünür; yollar yalnız izinli kökler altında çözülür; aynı harita yeniden taranınca kayıtlı dosya atlanır | Must (v1) |
| 11.9.6 | Eğitim temizliği: öğeyi yoksay, çalıştırmayı arşivle, katalog örneklerinin kaydı | "Yerleştirilemedi", çelişki ve inceleme öğeleri notla tek adımda "yoksayılır" (durum `dismissed`, geri alınabilir) ve listede varsayılan olarak görünmez; çalıştırma arşivlenebilir (listeden ve sayaçlardan kalkar, öğeleri ve örnekleri değişmez). Tür sayfasından el ile yüklenen örnek de `example_files` kaydı alır (yöntem elle, etiket doğrulanmış); kayıtsız eski örnek dosyaları bir kez kaydedilir; katalog örnek listesi 11.9.4'teki taşı/çıkar işlemlerine bağlanır | Should (v1) |
| 11.6.1 | Profil fotoğrafı kural seti | Kurallar katalogda tutulur ve panelden açılıp kapatılabilir | Should (v2) |
| 11.7.1 | Fotoğraf görsel kontrolü | Her kural pass/fail/unsure olarak değerlendirilir; fail varsa Unresolved | Should (v2) |
| 11.7.2 | Fotoğrafta içerik korunması | Kırpma, düzeltme ve arka plan değiştirme yapılmaz | Should (v2) |
| 11.8.1 | Fotoğraf örneklerinden öğrenme | Kabul edilen fotoğraflar örnek işaretlenir ve açıklamayı besler | Could (v3) |

### FR-MOD-12 — Telegram botu (Faz 2)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 12.1.1 | Bot iskeleti | Bot ayrı servis olarak çalışır; geliştirmede polling, üretimde webhook | Should (v2) |
| 12.1.2 | Kullanıcı beyaz listesi | Listede olmayan kullanıcıya yanıt verilmez; tek istisna kodsuz `/start`'a verilen kimlik yanıtıdır (12.1.7) | Should (v2) |
| 12.1.3 | Beyaz listeyi panelden yönetme | Kullanıcı yönetimi sayfasında (10.1.4) her panel kullanıcısına Telegram kimliği eklenir (12.1.8'den beri kimlik yalnız kullanıcının kendi hesabına, Hesabım → Telegram sayfasından eklenir; yönetici izni kapatıp açar), izni kapatılıp açılır; bot yalnız izinli kimliğe yanıt verir; değişiklik kullanıcı adıyla olaya yazılır; kayıt silinmez. Sayfa kimliğin telefon numarası değil Telegram hesap kimliği olduğunu ve @userinfobot'tan nasıl öğrenileceğini söyler; @userinfobot yanıtından kopyalanan `Id: 123456789` satırı da kabul edilir | Should (v2) |
| 12.1.4 | Telegram hesabını bağlantıyla otomatik bağlama | Kullanıcılar sayfasında bir kullanıcı için (12.1.8'den beri yalnız kullanıcının kendisi için, Hesabım → Telegram sayfasında) "Telegram'ı bağla" kişiye özel, tek kullanımlık ve 10 dakika geçerli bir bot bağlantısı (`https://t.me/<bot>?start=<kod>`) üretir; kişi bağlantıyı açıp "Başlat"a basınca bot gönderenin Telegram kimliğini o kullanıcıya izinli olarak kendisi kaydeder ve "bağlandı" der, kimlik panelde görünür; elle kimlik girme yedek yol olarak kalır. Kod yalnız bir kez ve süresi içinde çalışır, yeni kod öncekini geçersiz kılar, başka kullanıcıya bağlı ya da engellenmiş kimlik bu yolla açılmaz; geçersiz kodla gelen kişiye tek bir genel yanıt verilir, kodsuz yabancıya yalnız kimlik yanıtı verilir (12.1.7); üretim ve bağlama kullanıcı adıyla olaya yazılır; kod ve kimlik loga yazılmaz | Should (v2) |
| 12.1.5 | Yerel başlatıcıda bot | `baslat.bat` `.env`'de `TELEGRAM_BOT_TOKEN` doluysa botu (geliştirmede polling) panelle birlikte ayrı pencerede başlatır; boşsa botsuz açılır ve bunu söyler | Should (v2) |
| 12.1.6 | Bot yanıtları kullanıcının dilinde | Bot, mesajı gönderen izinli kimliğin bağlı olduğu panel kullanıcısının dilinde (10.10.2) yanıt verir; tercihi olmayan kullanıcıya İngilizce. Bağlantıyla bağlamada (12.1.4) yanıt bağlanan kullanıcının dilindedir; geçersiz bağlantı gibi kişisi bilinmeyen genel yanıtlar İngilizcedir. Belge türü ve çalışan adları çevrilmez (12.1.12'den beri kişinin bota yazdığı dil önce gelir) | Should (v2) |
| 12.1.7 | Bot, bağlı olmayan kişiye Telegram kimliğini söyler | Özel sohbette kodsuz `/start` gönderen ve izinli olmayan kişiye (kimliği kayıtlı değil, izni kapalı ya da bağlı olduğu panel kullanıcısı pasif) bot tek bir yanıt verir: sade bir cümleyle bu Telegram'ın henüz Documania'ya bağlı olmadığını ve panelde Hesabım → Telegram'dan bağlanacağını söyler, kişinin Telegram numarasını da son satırda yalnız rakamlarla verir (uzun basınca tek başına kopyalanır, panele yapıştırılır; 12.1.9). Yanıt kayıtsız, engelli ve pasif durumlarını birbirinden ayırmaz; panel kullanıcısı, çalışan, belge ya da kurum bilgisi içermez; İngilizcedir (12.1.6). `/start` dışındaki mesajlara, gruplara ve kanallara yine yanıt verilmez; aynı sohbete en çok saatte bir kimlik yanıtı gider. İzinli kişinin `/start` yanıtı ve bağlantıyla bağlamanın (12.1.4) "bağlandı" yanıtı da numarayı söyler. Kimlik loga ve olaya yazılmaz | Should (v2) |
| 12.1.8 | Telegram'ı yalnız hesabın sahibi bağlar | Telegram bağlama oturumdaki kullanıcının kendi hesabına özeldir: "Hesabım → Telegram" sayfası (`/account/telegram`, her girişli kullanıcıya açık) kullanıcının bağlı kimliklerini izin durumlarıyla gösterir, kendisi için "Telegram'ı bağla" bağlantısını (12.1.4) üretir, botun söylediği kimliğin (12.1.7) elle eklenmesini kabul eder ve kendi kimliğinin iznini kapatıp açtırır. Kullanıcılar sayfasında başka bir kullanıcıya kimlik ekleme ya da bağlantı üretme yolu yoktur; böyle bir istek reddedilir. Yönetici Kullanıcılar sayfasında başka kullanıcıların kimliklerini görür ve izni kapatıp açabilir (kaybolan telefon). Daha önce bağlanmış kimlikler geçerli kalır. Her değişiklik yapanın kendi adıyla olaya yazılır | Should (v2) |
| 12.1.9 | Botun mesajları sade, kısa ve teknik terimsiz | Bot, teknik bilgisi olmayan bir İK çalışanının ilk okuyuşta anlayacağı dille yazar: her mesaj kısa (liste dışında en çok dört satır, listede en çok beş öğe), günlük sözcüklerle ve tek bir şey söyler; yapılacak bir şey varsa onu tek cümleyle söyler. Mesajlarda parti numarası, "parti", "kuyruk", Unknown/Unreadable/Unresolved, "aşama", "yapay zekâ", "sağlayıcı", "işleyici", "katalog", "eşik", dosya boyutu birimi, yüzde, çalışan numarası, hata adı ya da yapay zekânın gerekçe metni geçmez; çalışan adıyla, belge türü adıyla anılır. Teknik durumlar Telegram'a ayrıntıyla gitmez: izleme uyarıları (13.6.1) ve toplu "parti işlenemedi" bildirimi hiç gönderilmez (panelde ve logda kalır); belgeyi gönderen kişiye yapay zekâya ulaşılamaması, işin başka işleyiciye geçmesi ya da beklenmeyen hata için yalnız "belgeleriniz kaydedildi, şu an işlenemedi" gibi tek sade cümle gider. Kural üç dildeki (10.10, 12.1.6) bütün bot metinleri için geçerlidir | Should (v2) |
| 12.1.10 | Telegram kaydını silme | Kullanıcılar sayfasında yönetici herhangi bir kullanıcının, Hesabım → Telegram sayfasında kişi kendi Telegram kimlik kaydını tek adımda siler. Kayıt veritabanından kalkar (R11'in tek istisnası); aynı numara hemen ardından aynı ya da başka bir hesaba bağlantıyla (12.1.4) veya elle (12.1.8) yeniden eklenebilir. Silinen kimliğe bot artık yanıt vermez (bağlı değil yanıtı, 12.1.7). Silme, yapanın adıyla ve silinen numarayla olaya yazılır; olay geçmişi ve kullanılmış bağlantı kodları değişmez | Should (v2) |
| 12.1.11 | Bot her mesaja yanıt verir | Bot işleyemediği mesajı sessiz geçmez: sesli mesaj ve ses dosyasına "sesli mesajları dinleyemiyorum, yazarak sorun", video, çıkartma, konum, kişi kartı, anket gibi öteki mesajlara "bunu açamıyorum; belgeyi dosya olarak gönderin ya da sorunuzu yazın" der; bilinmeyen komuta yardım metni gider. Bot bir yazılı isteği işlerken sohbette "yazıyor…" görünür. Yanıtlar 12.1.9 sade dil kuralına uyar | Should (v2) |
| 12.1.12 | Bot, kişinin yazdığı dilde yanıt verir | Kişi bota Türkçe, İngilizce ya da Sırpça yazarsa yanıt o dildedir (panel tercihi başka olsa da); bu dil bot yeniden başlayana dek o kişinin sonraki yanıtlarında da (belge alma özeti, seçim düğmeleri, yardım) kullanılır. Dil anlaşılamazsa ya da kişi henüz yazmadıysa 12.1.6 geçerlidir. Kuyruk bildirimi (12.4.1) panel tercihindedir. Belge türü ve çalışan adları veridir, çevrilmez | Should (v2) |
| 12.1.13 | Bot yalnız kendi konusunda konuşur | Bot çalışanlar, belgeleri, profilleri ve bu sistemle ilgisiz mesajlara (hava durumu, fıkra, genel bilgi, kişisel sohbet…) kısa ve kibar bir retle yanıt verir. Art arda ikinci konu dışı mesajda yine reddeder ve bunun son uyarı olduğunu söyler; art arda üçüncüsünde "Seninle konuşmuyorum." der ve o kişiye 30 dakika hiçbir mesajına yanıt vermez (gönderdiği dosyalar yine alınır, belge kaybolmaz). Süre bitince sayaç sıfırlanır; arada sistemle ilgili bir mesaj sayacı sıfırlar. Sayaç bot sürecinin belleğindedir | Should (v2) |
| 12.2.1 | Belge alma | Gönderilen belge web ile aynı boru hattından işlenir | Should (v2) |
| 12.2.2 | Çoklu mesaj grubu | Aynı medya grubundaki dosyalar tek parti sayılır | Should (v2) |
| 12.2.3 | Sonuç özeti | İşlem sonucu ve kuyruğa düşen öğeler kısa mesajla bildirilir | Should (v2) |
| 12.3.1 | Belge isteme | "Ahmet Çakar'ın ehliyetini göster" isteği doğru belgeyi bulur | Should (v2) |
| 12.3.2 | Belirsizlikte seçim | Birden fazla sonuçta kullanıcıdan seçim istenir | Should (v2) |
| 12.3.3 | Erişim kaydı | Bot üzerinden gönderilen her belge erişim loguna yazılır | Should (v2) |
| 12.3.4 | Tek mesajda birden çok belge türü | "Ahmet Çakar'ın ehliyeti ve CV'si var mı?" gibi bir mesajda her tür ayrı satırda yanıtlanır: var (birden çoksa sayısıyla) ya da yok; bilinmeyen tür kendi satırında söylenir. Tek belgesi olan türün belgesi gönderilir (erişim kaydıyla, 12.3.3); birden çok belgesi olan tür için kişiye o türü ayrıca istemesi söylenir. En çok 5 tür | Should (v2) |
| 12.3.5 | Önceki kişiye devam | Kişi adı yazılmadan gelen istek ("Ehliyeti de", "peki CV?", "kaç yaşında?") aynı sohbette son 10 dakikada sonuç verilen tek kişiye uygulanır; böyle bir kişi yoksa kişinin adı sorulur. Bağlam bot sürecinin belleğindedir, kişi başınadır; tahmin edilmez (birden çok kişi bulunan istekten sonra bağlam yoktur) | Should (v2) |
| 12.3.6 | Kişi bilgisi | "Ahmet Çakar kaç yaşında?", "Ahmet Çakar'ın hangi belgeleri var?" gibi sorulara bot kişinin kısa özetini verir: doğum tarihi ve yaşı, uyruğu, etkin belgelerinin türleri (en çok 5, fazlası sayıyla) ve eksik zorunlu belgesi olan paketleri. Bilinmeyen alan "kayıtlı değil" diye yazılır; belge gönderilmez; hiçbir şey değişmez. Birden çok kişi uyarsa 12.3.2 gibi seçim istenir | Should (v2) |
| 12.3.7 | Eksik belgeler | "Ahmet Çakar adres kaydı için hangi belgeleri tamamlamalı?" sorusunda mesajdaki süreç adına karşılık gelen belge grubu (14.1.1) bulunur ve kişinin o gruptaki eksik zorunlu kalemleri (en çok 5) ve varsa isteğe bağlı eksikleri sayıyla söylenir; eksik yoksa "eksik belge yok" denir. Kişiye o gruptan paket tanımlıysa paket, değilse grubun kalemleri kişinin etkin belgeleriyle 14.1.2 kuralına göre karşılaştırılır — paket tanımlanmaz, hiçbir şey yazılmaz. Süreç adı söylenmezse kişinin açık paketlerinin eksikleri; tanınmayan süreç adı söylenir | Should (v2) |
| 12.3.8 | Profil sorusu ve karşılaştırma | "Mehmet ile Ayşe'den hangisi daha yaşlı?", "Mehmet'in pasaportu ne zaman bitiyor?" gibi sorularda sistem kişileri (en çok 5) kendisi bulur ve yalnız onların profil.md içeriğini soruyla birlikte yapay zekâya verir; yanıt yalnız bu profillerden, kısa ve sade yazılır, profilde olmayan bilgi uydurulmaz, çalışan numarası yazılmaz. Bir ad birden çok kişiye uyarsa adın ayrıntılandırılması istenir. Profiller kişisel veri olarak sağlayıcıya gider (insan kararı) | Should (v2) |
| 12.3.9 | Tek kişinin belgelerini dışa aktarma, toplu dışa aktarımın reddi | "Mehmet'in bütün belgelerini gönder" isteğinde o kişinin etkin belgeleri (en çok 20; fazlası için panel söylenir) erişim kaydıyla gönderilir. Aynı anda yalnız bir kişinin belgeleri dışa aktarılır: birden çok kişinin ya da herkesin belgelerini isteyen mesaj ("herkesin pasaportunu gönder") reddedilir ve hiçbir belge gitmez | Should (v2) |
| 12.4.1 | Kuyruk ve hata bildirimi | Kuyruğa yeni öğe düşünce ve parti başarısız olunca bildirim gider (12.1.9'dan beri Telegram'a yalnız kontrol bekleyen belge bildirimi sade dille gider; parti hatası ve izleme uyarıları Telegram'a gitmez, panelde ve logda kalır) | Could (v3) |

### FR-MOD-13 — İşletme ve dayanıklılık (Faz 3)

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 13.1.1 | Maliyet ölçümü (kaldırıldı) | Kaldırıldı (2026-10-01, insan kararı): token ve maliyet ne tutulur ne gösterilir; bkz. §10 ve PLAN §D84 | Kapsam dışı |
| 13.2.1 | Ucuz model ön eleme | Kolay sayfalar ucuz modele yönlendirilir; test matrisi doğruluğu düşmez | Could (v3) |
| 13.2.2 | Metin katmanı önceliği | Metin katmanı olan sayfalarda görüntü çözünürlüğü düşürülür | Could (v3) |
| 13.3.1 | Kalıcı işçi kuyruğu | Uygulama yeniden başlayınca yarım kalan parti kaybolmaz | Could (v3) |
| 13.4.1 | Erişim logu görünümü | Çalışan bazında kim ne zaman baktı görülebilir | Could (v3) |
| 13.4.2 | Yedekleme ve geri yükleme | Gece yedeği alınır; geri yükleme prosedürü bir kez denenmiştir | Could (v3) |
| 13.5.1 | Üretim dağıtımı | Alan adı ve HTTPS ile tek komutla dağıtım yapılır | Could (v3) |
| 13.5.2 | APP ve worker servislerinin ayrılması | Compose'ta HTTP uygulaması ve kalıcı işçi kuyruğu ayrı servislerdir; aynı imajı, üretimde aynı PostgreSQL bağlantısını ve kalıcı veri hacmini kullanırlar; ikisi de göçün başarıyla bitmesini bekler. Uygulama worker döngüsü başlatmaz; `/upload` yalnız işi kuyruğa yazar, provider kurmaz ve işi tüketmez; worker HTTP portu yayınlamaz. Geliştirme ve production profilleri için `docker compose config` geçer | Could (v3) |
| 13.5.3 | Şema ve kod sürümü uyuşmazlığı koruması | Panel, işçi ve bot açılışta veritabanının göç sürümünü koddaki son sürümle karşılaştırır; eskiyse açılmaz ve "önce `alembic upgrade head` (ya da `baslat.bat`)" diyen anlaşılır hata verir. Çalışan panel, diskteki kod ya da şablonlar açılıştan sonra değişmişse her sayfanın üstünde "Sunucu eski sürümle çalışıyor — yeniden başlatın" uyarısı gösterir; `/health` kod ve şema sürümünü döner | Should (v1) |
| 13.6.1 | İzleme ve uyarı | Hata, disk doluluğu ve kuyruk uzunluğu için uyarı üretilir | Could (v3) |
| 13.7.1 | Büyük çekirdek modüllerin ayrıştırılması | `app/pipeline/plan.py` ve `app/pipeline/execute.py` sorumluluklarına göre alt modüllere ayrılır; mevcut `app.pipeline.plan` ve `app.pipeline.execute` import yüzeyleri korunur; davranış değişikliği olmadan ilgili ve tam test takımı geçer | Could (v3) |

### FR-MOD-14 — Belge grupları ve başvuru paketleri (Faz 1)

İK bir süreç için gereken belgeleri (örn. Sırbistan iş başvurusu) grup olarak tanımlar, çalışana paket
olarak atar ve belgeler geldikçe kalemlerin karşılandığını görür. Paket belge üretmez, belgeyi
değiştirmez, boru hattına karışmaz; yalnız çalışanın etkin belgelerine bakar.

| ID | Gereksinim | Kabul kriteri | Öncelik |
|---|---|---|---|
| 14.1.1 | Belge grupları sekmesi | Panelde "Belge Grupları" menüsü: grup listesi (ad, açıklama, kalem sayısı, açık paket sayısı, durum); yeni grup (ad tekil, açıklama); grup sayfasında ad/açıklama değişir, kalem eklenir ve çıkarılır; grup tek adımda arşivlenir (yeni paket tanımlanamaz, açık paketler sürer) ve geri alınır; grup silinmez. Kalem değişikliği açık paketlere anında yansır ve grup sayfası açık paket sayısıyla uyarır | Must (v1) |
| 14.1.2 | Grup kalemi: etiket ya da tür, ülkeden bağımsız eşleşme | Kalem ya bir **dosya etiketiyle** (katalogdaki `file_label` değerleri, örn. Passport) ya da belirli bir **türle** (slug) tanımlanır. Etiketli kalemi, ülkesi ne olursa olsun aynı etiketli her türden etkin belge karşılar (Rus ya da Türk pasaportu "Passport" kalemini karşılar); türlü kalemi yalnız o tür karşılar. Kalem zorunlu ya da isteğe bağlıdır. Etiket seçici katalogdaki etiketleri tür sayısıyla listeler | Must (v1) |
| 14.2.1 | Çalışana paket tanımlama | Profil sayfasındaki "Belge paketleri" bölümünde arşivlenmemiş bir grup seçilip paket tanımlanır; aynı çalışana birden çok paket, aynı gruptan ikinci paket (uyarıyla) tanımlanabilir; tanımlayan kullanıcı ve zaman kaydedilir, olay yazılır | Must (v1) |
| 14.2.2 | Karşılanma hesabı ve kademeli işaret | Paket kalemleri profilde liste hâlinde görünür; kalem, çalışanın etkin bir belgesi 14.1.2 kuralıyla eşleşiyorsa tik alır ve karşılayan belgeye bağlanır. Hesap her görüntülemede belgelerden yapılır; ayrıca belge yazma, taşıma, arşivleme, geri alma ve çalışan birleştirme noktalarında paket durumu yenilenir; belge arşivlenince tik kalkar. Eğitim modu örnekleri, eski sürüm ve arşivdeki belgeler kalem karşılamaz | Must (v1) |
| 14.2.3 | Paket tamamlanması ve iptali | Zorunlu kalemlerin hepsi karşılanınca paket "Tamamlandı — başvuru başlatılabilir" olur, tamamlanma zamanı ve olay yazılır; sonradan eksik oluşursa paket açığa döner ve olay yazılır. Paket notla tek adımda iptal edilir ve "Yeniden aç" ile geri alınır; iptal edilen paket profilde katlanmış listede kalır, silinmez | Must (v1) |
| 14.3.1 | Paket görünürlüğü listede | Çalışan listesinde açık paket sayısı ve eksik kalem sayısı görünür; "eksik paketi olanlar" süzgeci vardır; profil.md "Belge paketleri" bölümünü taşır | Should (v1) |

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
| `employees` | Çalışan ana kaydı | id (E0001), folder_name, given_names, surname, original_script_name, date_of_birth, nationality, status (`active`, `inactive`, `merged` — 10.5.7, 10.5.9), merged_into_id, created_at |
| `employee_identifiers` | Belge numaraları | employee_id, kind, value, source_document_id, removed_at, removed_by (10.5.8) |
| `employee_aliases` | Görülen isim yazımları | employee_id, raw_name, normalized_name, script, removed_at, removed_by (10.5.8) |
| `employee_contacts` | İletişim bilgileri | employee_id, kind (`phone`, `email`, `address`), value, source_document_id, first_seen_at, last_seen_at, is_current, added_by, removed_at, removed_by (10.5.8) |
| `uploads` | Yükleme partisi | id, channel, uploaded_by, context_employee_id, status, created_at |
| `upload_files` | Kaynak dosyalar | id, upload_id, original_name, stored_path, sha256, mime, page_count, is_duplicate_of |
| `pages` | Sayfalar | id, file_id, index, image_path, text_layer, is_blank, has_single_embedded_image, analysis_json, analysis_status |
| `plans` | Dondurulmuş planlar | id, upload_id, version, json, model, plan_hash, created_at, executed_at |
| `documents` | Çıktı belgeleri | id, employee_id, type_slug, path, format, sequence_no, plan_id, source_refs_json, status, created_at |
| `queue_items` | Kuyruk öğeleri | id, upload_id, plan_item_id, kind, reason, payload_json, resolved_at, resolved_by, resolution (`dismissed`, `closed`), resolution_note (10.7.4) |
| `known_document_types` | Katalog | slug, name, file_label, country, description, expected_file_types, expected_pages_min, expected_pages_max, sides, direct, analyze, required_fields, allowed_conversions, output_format, prompt_description, photo_rules, active, archived_at, archived_by (11.1.6) |
| `candidate_document_types` | Aday türler | id, proposed_name, normalized_name, description, first_seen_upload_id, sample_page_ids, seen_count, status, proposal_json, proposal_status, proposal_generated_at (11.5.5) |
| `training_runs` | Eğitim modu çalıştırması (11.9) | id, kind (`upload`, `map`), created_by, created_at, map_name, status, sayaçlar, archived_at (11.9.6) |
| `training_items` | Eğitim modunda işlenen dosya (11.9) | id, run_id, row_number, original_name, source_ref, staged_path, sha256, file_kind, page_count, hint_slug, result_slug, method (`mechanical`, `ai`, `manual`), status, note, checks_json, decided_by, decided_at |
| `example_files` | Örnek dosyası kaydı ve etiketi (11.9) | id, type_slug, name, sha256, method, label (`ai_decision`, `verified`), note, training_item_id, created_at |
| `events` | Olay logu | id, ts, upload_id, file_id, page_index, document_id, employee_id, actor, type, message, data_json |
| `access_log` | Görüntüleme ve indirme | ts, user_id, document_id, action, channel |
| `users` | Panel kullanıcıları | id, username, password_hash, role, active (10.1.4), language (10.10.2: `en`, `tr`, `sr`; boş = tercih yok) |
| `telegram_users` | Beyaz liste | telegram_id, user_id, allowed |
| `document_groups` | Belge grubu (14.1.1) | id, name, normalized_name (tekil), description, created_by, created_at, archived_at, archived_by |
| `document_group_items` | Grup kalemi (14.1.2) | id, group_id, position, match_kind (`label`, `type`), file_label, type_slug, required, note |
| `employee_packages` | Çalışana tanımlı paket (14.2) | id, employee_id, group_id, status (`open`, `completed`, `cancelled`), requested_by, requested_at, completed_at, cancelled_at, cancelled_by, note |

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
      _egitim/gelen/<run>/        eğitim modunda yüklenen dosyaların kopyası (11.9)
      _egitim/haritalar/          yüklenen harita CSV'leri (11.9.5)
      _egitim/cikarilan/<tur_slug>/  örneklerden çıkarılanlar; silinmez (11.9.4)
  cache/pages/<file_id>/          analiz için üretilmiş sayfa görüntüleri
```

### 8.3 Olay türleri

FILE_UPLOADED · FILE_DUPLICATE · PAGE_RENDERED · PAGE_BLANK · PAGE_ANALYZED ·
PAGE_ANALYSIS_FAILED · PAGE_UNREADABLE · DOC_TYPE_DETERMINED · DOC_TYPE_UNKNOWN ·
CANDIDATE_TYPE_PROPOSED · PERSON_IDENTIFIED · PERSON_MATCHED · PERSON_NOT_MATCHED ·
PERSON_AMBIGUOUS · EMPLOYEE_CREATED · EMPLOYEE_PENDING · EMPLOYEE_FIELD_FILLED · PLAN_CREATED · VALIDATION_FAILED ·
DIRECT_DOC_CHECK · PAGE_EXTRACTED · PAGES_MERGED · IMAGE_WRAPPED · IMAGE_EXTRACTED ·
IMAGE_RENDERED · OUTPUT_SAVED · OUTPUT_SKIPPED · QUEUED_UNKNOWN · QUEUED_UNREADABLE ·
QUEUED_UNRESOLVED · MANUAL_MOVE · MANUAL_ASSIGN · MANUAL_APPROVE · TYPE_APPROVED ·
TYPE_REJECTED · USER_CONFIRMED · PLAN_RERUN · PLAN_REANALYZED · ARCHIVED · UPLOAD_DISMISSED ·
PIPELINE_FAILED · CANDIDATE_TYPE_EXAMINED · TRAINING_EXAMPLE_PLACED · TRAINING_ITEM_UNPLACED ·
TRAINING_LABEL_VERIFIED · TRAINING_EXAMPLE_MOVED · TRAINING_EXAMPLE_REMOVED · TRAINING_MAP_STARTED ·
EMPLOYEE_EDITED · EMPLOYEE_DEACTIVATED · EMPLOYEE_REACTIVATED · EMPLOYEE_MERGED ·
PROFILE_RECORD_REMOVED · PROFILE_RECORD_RESTORED · CONTACT_ADDED · UNARCHIVED ·
QUEUE_ITEM_CLOSED · QUEUE_ITEM_REOPENED · UPLOAD_RESTORED · TYPE_ACTIVATED · TYPE_DEACTIVATED ·
TYPE_ARCHIVED · TYPE_RESTORED · CANDIDATE_TYPE_RESTORED · TRAINING_ITEM_DISMISSED ·
TRAINING_ITEM_RESTORED · TRAINING_RUN_ARCHIVED · USER_CREATED · USER_DEACTIVATED ·
USER_REACTIVATED · USER_PASSWORD_CHANGED · USER_LANGUAGE_CHANGED · TELEGRAM_USER_CHANGED · TELEGRAM_LINK_CREATED · GROUP_CHANGED ·
PACKAGE_ASSIGNED · PACKAGE_COMPLETED · PACKAGE_REOPENED · PACKAGE_CANCELLED · DOCUMENT_DELETED ·
EMPLOYEE_DELETED

`DOCUMENT_DELETED` (10.5.12) verisi: `document_id`, `document_type_slug`, `previous_status` (`active` /
`archived` / `superseded`), silinen ve korunan dosya sayıları (`files_deleted`, `files_kept`). `EMPLOYEE_DELETED`
(10.5.13) verisi: silinen belge, dosya, sayfa ve alt kayıt sayıları. İkisi de kişisel değer taşımaz ve `actor`
olarak kullanıcı adını taşır.

`EMPLOYEE_CREATED` olayının verisi açılış dayanağını taşır: `basis` = `document_number` (§20.2.2
satır 6) ya da `name_dob` (satır 6b).

2026-09-28 açılışının olayları (10.1.4, 10.3.5, 10.5.6–10.5.10, 10.7.4, 11.1.6, 11.5.7, 11.9.6, 12.1.3,
14.x) kişisel değer taşımaz: alan **adları**, kayıt türü ve kimlikleri, sayılar ve gerekçe kodları yazılır;
isim, numara, tarih, parola ve iletişim değeri yazılmaz. Hepsi `actor` olarak kullanıcı adını taşır.

`USER_LANGUAGE_CHANGED` (10.10.2) verisi: `target_user_id`, `language` (`en`/`tr`/`sr`) ve `via` (`selector` — dil seçici, `login` — giriş sayfasında seçilmiş dilin tercihi olmayan hesaba girişte kaydı); `actor` kullanıcının kendisidir.

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
    "mrz_lines": ["...", "..."],
    "contact": {
      "phone": null,
      "email": null,
      "address": "ул. Ленина, д. 5, кв. 12, Москва"
    }
  },
  "fields": {
    "surname": {"value": "VASILIEV", "legible": true},
    "document_number": {"value": "71 1234567", "legible": true},
    "expiry_date": {"value": null, "legible": false}
  },
  "notes": "Alt kenar hafif bulanık."
}
```

`side`: front · back · front_and_back · single · unknown. `front_and_back`: `front_back` türde
aynı kartın iki yüzü tek sayfada; başka kişiye ya da başka belgeye ait yüz de varsa `unknown`. `document_type_slug` katalogda bir slug veya null.
`candidate_type_name` yalnız slug null iken dolar.

`language`: ISO 639-1 kodu (`tr`, `ru`, `sr`, `es`, `en`, `ar` …). `script`: `latin`,
`cyrillic`, `arabic` veya `other`. `contact`: belgede **açıkça yazılı** iletişim bilgisi;
yoksa alanlar `null` kalır — çıkarım yapılmaz, uydurulmaz (gereksinim 03.1.4).

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
  front_back_layouts: []
  direct: true
  analyze: true
  required_fields: [surname, given_names, date_of_birth, document_number, expiry_date]
  allowed_conversions: []
  output_format: keep
  acceptance_criteria:
    - "Kimlik sayfası tam görünür olmalı, kenarlar kesilmemiş"
    - "MRZ iki satırı da okunabilir olmalı"
  prompt_description: >
    Kiril ve Latin çift yazımlı kimlik sayfası, sağ altta iki satır MRZ.
```

`acceptance_criteria`: şirketin o belge türü için aradığı, **zorunlu alan okunaklılığının
ötesindeki** koşullar (orijinal tanımdaki "Kabul Kriterleri"). Serbest metin maddeleridir;
analizciye tür açıklamasıyla birlikte verilir ve karşılanmayan madde `unresolved` gerekçesine
yazılır. Boş bırakılabilir — o zaman tek ölçüt K1'dir (zorunlu alan okunaklılığı).

`front_back_layouts`: `front_back` türün kabul ettiği düzenler — `separate` (ön ve arka ayrı
sayfalarda, 2 sayfa) ve/veya `combined` (iki yüz tek sayfada, 1 sayfa). `front_back` türde en az
biri seçilir, tek yüzlü türde boştur. `expected_pages` bu türde düzenlerden türetilir: yalnız
`separate` → 2–2, yalnız `combined` → 1–1, ikisi → 1–2. Tek sayfadaki iki yüz ayrılmaz, kırpılmaz;
sayfa olduğu gibi çıktı olur.

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
| S10 | Belge isimle mevcut çalışanla eşleşiyor ama belgedeki doğum tarihi çalışanınkinden farklı | Unresolved; otomatik eşleştirme ve yeni çalışan yok (doğum tarihi taşımayan belgenin tekil isim eşleşmesi S23'tür) |
| S11 | Temiz pasaport numarası; kayıtlı çalışan yok | Yeni çalışan, klasör ve profil.md; belge Hazir'da |
| S12 | Aynı isimli iki çalışan; doğum tarihi birine uyuyor | O çalışana eşleşir; her ikisine veya hiçbirine uymuyorsa Unresolved |
| S13 | Kiril isimli belge | Latin dosya adı + orijinal yazım profilde |
| S14 | Katalogda olmayan tür (Peru diploması) | Unknown + aday tür; onay ve yeniden analizden sonra Hazir |
| S15 | Word CV: profil sayfasından / genel yüklemeden | `Hazir/...Attachment...docx` değişmeden / Unresolved |
| S16 | Manuel taşıma tek onayla / iki onayla | Değişiklik yok / taşınır, iki profil güncellenir, olay kullanıcı adıyla |
| S17 | Telegram: iki ehliyet / tek ehliyet | Seçim sorusu / dosya gönderilir |
| S18 | Mevcut plandan yeniden çalıştırma | Aynı çıktılar; sağlayıcı çağrılmaz; ikinci dosya yok |
| S19 | Numarasız belge (zorunlu alanı ad, soyad, doğum tarihi); ad-soyad ve doğum tarihi okunaklı; kayıtlı çalışan yok | Yeni çalışan (`basis: name_dob`), klasör ve profil.md; belge numarası yazılmaz; belge Hazir'da. Doğum tarihi okunamıyorsa onay bekleyen profil (Unresolved) |
| S20 | Eğitim modunda pasaport yükleniyor; ikinci dosya hiçbir türe uymuyor | Pasaport örneklere girer (mekanik ya da "AI kararı" etiketli); ikincisi "Yerleştirilemedi"de; çalışan, kuyruk öğesi, yükleme partisi ve çıktı belgesi oluşmaz |
| S21 | "Sırbistan iş başvurusu" grubu (Passport etiketi, Profile Picture etiketi, çevirili diploma türü) çalışana paket olarak tanımlı; önce Rus pasaportu, sonra fotoğraf ve çevirili diploma yükleniyor | Pasaport kalemi ülkeye bakılmadan tik alır; üç belge Hazir'a girince paket "Tamamlandı — başvuru başlatılabilir", olay yazılır; diploma arşivlenince paket açığa döner ve olay yazılır |
| S22 | Pasif çalışanın pasaport numarasıyla yeni belge geliyor | Belge çalışanın klasörüne otomatik girmez; Unresolved'da "pasif çalışan" gerekçesiyle bekler; çalışan etkinleştirilip öğe atanınca Hazir'a girer |
| S23 | Doğum tarihi taşımayan çalışma izni (ya da sözleşme) genel yüklemeyle geliyor; ad-soyad tek bir etkin çalışana uyuyor, numarası kayıtlı değil / aynı adda iki çalışan var | O çalışanın Hazir'ına `matched_by: name` ile girer; çalışana isim yazımı, numara, alan ve iletişim eklenmez; profilde "yalnız isimle eşleşti" etiketi / Unresolved (`PERSON_AMBIGUOUS`), yeni çalışan yok |
| S24 | Çalışanın tek kaynaklı pasaportu ve arşivdeki eski pasaportu kalıcı siliniyor: tek onayla / iki onayla | Değişiklik yok / iki dosya, `Alinan` kopyaları ve Inbox orijinali diskten kalkar; belge satırları `deleted`, dosya adresi 404, paket tiki düşer; başka belgeye kaynak olan orijinal kalır; `DOCUMENT_DELETED` kullanıcı adıyla |
| S25 | Pasif çalışan kalıcı siliniyor; bir yüklemesi yalnız ona, öbürü onunla başka bir çalışana ait | Çalışan klasörü, belgeleri, alt kayıtları, yalnız ona ait yüklemenin orijinali ve sayfa görüntüleri silinir; ortak yüklemenin orijinali ve öbür çalışanın sayfaları kalır; çalışan satırı `deleted`, kişisel alanları boş; aynı kişinin yeni belgesi eski kayda eşleşmez; olaylarda isim kalmaz; etkin çalışanda istek reddedilir |

S19 gereksinim 05.6.2'nin (Faz 0), S20 gereksinim 11.9.1'in (Faz 1) kabul senaryosudur; ikisi de
kendi gereksinimini karşılayan görevde otomatik test olur. S21 gereksinim 14.2.2–14.2.3'ün, S22
gereksinim 10.5.7'nin (ikisi de Faz 1) kabul senaryosudur; aynı kuralla kendi görevlerinde test olur.
S23 gereksinim 05.5.4'ün, S24 10.5.12'nin, S25 10.5.13'ün kabul senaryosudur (2026-10-08 açılışı); aynı
kuralla kendi görevlerinde test olur. S10'un yeni tanımı 05.5.4 görevinde testine yansır.

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
- Başvuru sürecinin kendisi (kurum başvurusu, form, randevu, sonuç takibi); belge paketi (FR-MOD-14)
  yalnız belgelerin hazır olup olmadığını izler.
- Maliyet ölçümü ve paneli: yapay zekâ çağrılarının token sayısı ve maliyeti tutulmaz, hiçbir
  sayfada gösterilmez (13.1.1 kaldırıldı). Olay logu yalnız sağlayıcı ve model adını taşır.
- Arayüz dilinde (10.10.x): Kiril alfabesiyle Sırpça, tarayıcı diline göre kendiliğinden dil seçimi, adreste dil öneki
  (`/en/...`), yöneticinin başka kullanıcının dilini ayarlaması, verinin (belge türü, çalışan, belge, dosya adı, olay)
  çevirisi ve botun doğal dil isteklerini (12.3) başka dillerde anlaması.
- Kendiliğinden ya da toplu kalıcı silme: sistem hiçbir varlığı kendisi silmez, süre dolunca otomatik silme ve
  toplu silme yoktur. Kalıcı silme yalnız İK'nın tek belge (10.5.12) ve pasif çalışan (10.5.13) için iki aşamalı
  onayla yaptığı işlemdir; tür, grup, kullanıcı ve olay silinmez (R11). Telegram kimlik kaydı da silinebilir
  (12.1.10); silinen kaydın izi olay logunda kalır. Yedeklerden silme bu ürünün işi değildir.

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
| 12.3.1 | Doğal dil isteğinin araç çağrılarına çevrilmesi belirsizlik yönetimi ister |

Bu dört kalemin ortak özelliği: **parçalara ayrılırsa yargı yok olmaz, birleştirme adımına
taşınır** — ve o adım en az bağlama sahip olandır. Bu yüzden bölünmezler.

Diğer tüm işler `xhigh` seviyesindedir.

### 11.1 Zorluğu spesifikasyona taşınan işler

Aşağıdaki işler ilk değerlendirmede en yüksek eforda görünüyordu. Zorlukları **belirsizlikten
değil, kararın yazılmamış olmasından** geliyordu. Kararlar §20'deki tablolara yazıldığı için
artık `xhigh` seviyesinde uygulanabilirler:

| İş | Kararın yazıldığı yer |
|---|---|
| 05.3 MRZ ayrıştırma | §20.1 — alan yerleşimi, kontrol hanesi algoritması, yüzyıl kuralı |
| 05.5, 05.6, 05.7 eşleştirme ve profil açma | §20.2 — normalizasyon + 8 satırlık karar tablosu |
| 06.2 işlem seçimi | §20.3 — 7 satırlık karar tablosu |
| 06.3 Direkt Belge kuralı | §20.4 — izin matrisi + format kontrolü |
| 07.1–07.6 dosya işlemleri | §20.5 — işlem başına kayıpsızlık sözleşmesi |
| 09.3 kabul senaryoları | Üreteç + üç senaryo grubuna bölündü (09.3.1–09.3.4) |
| 10.7 kuyruk ekranları | Üç bağımsız çözüm akışına bölündü (10.7.1–10.7.3) |

Orta zorlukta ama dikkat isteyen işler: 00.4.2 (üç alfabede slug), 02.1.1 (DPI ve maliyet
dengesi), 03.4.1 (prompt disiplini), 06.1.2 (plan determinizmi).

**Model seçimi.** Zorluk yalnız eforu değil, işi yapacak **modeli** de belirler. Kapsamı net
ve kabul kriteri ölçülebilir mekanik işler daha küçük bir modele verilebilir; belge
bütünlüğü, kişi eşleştirme, Direkt Belge kuralı, kayıpsız PDF işlemleri ve kimlik doğrulama
asla verilmez. Etiket biçimi ve tam dağılım `MASTER-PROMPT.md` §6'dadır.

---

## 20. Karar tabloları (uygulama sözleşmeleri)

> **Bu bölüm neden var.** Otonom yapımda her görev, önceki hiçbir şeyi hatırlamayan temiz bir
> pencerede çalışır. Kararı kodlama anında verdirmek, her pencerede farklı karar verilmesi
> demektir. Bu yüzden karar burada **bir kez** verilir ve yazılır; pencere yalnız uygular.
>
> Tabloları okumadan ilgili kodu yazma. Tabloda karşılığı olmayan bir durumla karşılaşırsan
> **uydurma**: `PLAN.md` §D'ye sapma olarak yaz, en güvenli davranışı seç (belgeyi kuyruğa al)
> ve devam et.

---

### 20.1 MRZ okuma ve doğrulama (gereksinim 05.3.1, 05.3.2, 05.3.3)

MRZ (Machine Readable Zone), ICAO Doc 9303 ile standartlaşmış makine-okunur alandır. Görünen
metinden **daha güvenilirdir** çünkü kontrol haneleri taşır: okuma hatası sessizce geçmez.

#### 20.1.1 Biçimler

| Biçim | Satır × karakter | Nerede kullanılır |
|---|---|---|
| TD1 | 3 × 30 | Kimlik kartları, oturum kartları |
| TD2 | 2 × 36 | Eski tip seyahat belgeleri, bazı kimlikler |
| TD3 | 2 × 44 | Pasaportlar |

Biçim, satır sayısı ve satır uzunluğundan belirlenir. Hiçbirine uymuyorsa MRZ yok sayılır
(hata değil — belgede MRZ olmayabilir).

#### 20.1.2 Karakter kümesi

İzinli karakterler: `A-Z`, `0-9`, `<`. Küçük harf, boşluk veya başka karakter varsa satır
önce büyük harfe çevrilir; hâlâ izinsiz karakter kalıyorsa MRZ **geçersizdir**.

`<` dolgu karakteridir. İsim alanında: `<` tek başına kelime ayracı, `<<` soyad ile ad
arasındaki ayraçtır.

Örnek isim alanı: `VASILIEV<<DMITRY<IVANOVICH<<<<<<<<<<<<<<`
→ soyad `VASILIEV`, verilen adlar `DMITRY IVANOVICH`.

#### 20.1.3 Alan yerleşimi

**TD3 (pasaport, 2 satır × 44).** Satır 1: `1` belge kodu (`P`), `2` isteğe bağlı,
`3-5` veren devlet, `6-44` isim alanı (39 karakter).

Satır 2 — konumlar birebir:

| Konum | Alan |
|---|---|
| 1–9 | Belge numarası |
| 10 | Belge numarası kontrol hanesi |
| 11–13 | Uyruk |
| 14–19 | Doğum tarihi (YYMMDD) |
| 20 | Doğum tarihi kontrol hanesi |
| 21 | Cinsiyet (`M`, `F` veya `<`) |
| 22–27 | Son geçerlilik tarihi (YYMMDD) |
| 28 | Son geçerlilik kontrol hanesi |
| 29–42 | İsteğe bağlı veri (kişisel numara vb.) |
| 43 | İsteğe bağlı veri kontrol hanesi |
| 44 | Bileşik (composite) kontrol hanesi |

**TD2 (2 satır × 36).** Satır 1: `1` belge kodu, `2` isteğe bağlı, `3-5` veren devlet,
`6-36` isim alanı (31 karakter). Satır 2: `1-9` belge no, `10` kontrol hanesi, `11-13` uyruk,
`14-19` doğum tarihi, `20` kontrol hanesi, `21` cinsiyet, `22-27` son geçerlilik,
`28` kontrol hanesi, `29-35` isteğe bağlı veri, `36` bileşik kontrol hanesi.

**TD1 (3 satır × 30).** Satır 1: `1-2` belge kodu, `3-5` veren devlet, `6-14` belge numarası,
`15` kontrol hanesi, `16-30` isteğe bağlı veri. Satır 2: `1-6` doğum tarihi,
`7` kontrol hanesi, `8` cinsiyet, `9-14` son geçerlilik, `15` kontrol hanesi,
`16-18` uyruk, `19-29` isteğe bağlı veri, `30` bileşik kontrol hanesi.
Satır 3: isim alanı (30 karakter).

#### 20.1.4 Kontrol hanesi algoritması

Tek bir algoritma, her alan için aynı:

1. Karakter değerleri: `0-9` → sayısal değeri · `A-Z` → `10 + (harf - 'A')`, yani `A`=10 …
   `Z`=35 · `<` → `0`.
2. Ağırlıklar soldan sağa **7, 3, 1** dizisini tekrarlar (1. karakter 7, 2. karakter 3,
   3. karakter 1, 4. karakter yine 7 …).
3. Her karakterin değeri ağırlığıyla çarpılır, hepsi toplanır.
4. Kontrol hanesi = toplam **mod 10**.

**Zorunlu birim testleri** — bu üç örnek testte birebir bulunmalıdır (ICAO belgelerindeki
standart örneklerden alınmıştır ve algoritmayı sabitler):

| Girdi | Beklenen kontrol hanesi |
|---|---|
| `L898902C3` (belge numarası) | `6` |
| `690806` (doğum tarihi) | `1` |
| `940623` (son geçerlilik) | `6` |

İlk örneğin açılımı: `L`=21×7=147, `8`×3=24, `9`×1=9, `8`×7=56, `9`×3=27, `0`×1=0,
`2`×7=14, `C`=12×3=36, `3`×1=3 → toplam 316 → 316 mod 10 = **6**.

#### 20.1.5 Bileşik kontrol hanesi

Bileşik hane, satırın birden çok alanını birlikte doğrular. Hesaplanan karakter dizisi
**bitişik olarak** birleştirilir, sonra 12.1.4 uygulanır.

| Biçim | Bileşik hanenin kapsadığı konumlar |
|---|---|
| TD3 | Satır 2: 1–10, 14–20, 22–43 |
| TD2 | Satır 2: 1–10, 14–20, 22–35 |
| TD1 | Satır 1: 6–30 · Satır 2: 1–7, 9–15, 19–29 |

> **Dikkat — en sık yapılan hata budur.** Aralıklar bitişik değildir; cinsiyet hanesi ve
> alan kontrol haneleri bilinçli olarak dışarıda/içeride bırakılmıştır. Uygulamayı yazdıktan
> sonra üreteçle (09.3.1) üretilmiş bir MRZ üzerinde ileri-geri doğrula: üreteç yazar, ayrıştırıcı
> okur, iki taraf da aynı haneyi bulmalıdır.

#### 20.1.6 Tarih ve yüzyıl kuralı

Tarihler `YYMMDD`'dir; yüzyıl yazmaz. Kural:

- **Son geçerlilik tarihi:** her zaman `20YY`.
- **Doğum tarihi:** önce `20YY` denenir; sonuç **gelecekte** kalıyorsa `19YY` alınır. Elde
  edilen tarih 06.5'teki `dob_plausible` doğrulayıcısına da girer (geçmişte ve 16–90 yaş).
- `MM` 01–12, `DD` 01–31 aralığında değilse ve takvimde geçerli bir gün değilse alan
  **okunamadı** sayılır (`legible: false`), MRZ tümüyle geçersiz sayılmaz.

#### 20.1.7 Geçersizlik ve öncelik

- Bir alanın kontrol hanesi tutmuyorsa **o alan** geçersizdir (`legible: false`); MRZ'nin
  tamamı atılmaz, diğer alanlar kullanılabilir.
- Bileşik hane tutmuyorsa MRZ **bütün olarak şüphelidir**: alanlar kullanılabilir ama
  `document_number` "temiz" sayılmaz (bkz. §20.2.3) — yani ondan yeni çalışan açılamaz.
- İsteğe bağlı veri alanı tamamen dolgu (`<`) ise kontrol hanesi `<` veya `0` olabilir;
  ikisi de geçerlidir, hata sayılmaz.
- MRZ ile görünen metin çelişirse **MRZ kazanır**, çelişki `notes` alanına yazılır
  (gereksinim 05.3.3). Bu bir doğrulama hatası değildir, bilgi notudur.

---

### 20.2 Çalışan eşleştirme ve profil açma (gereksinim 05.5.1–05.5.3, 05.6.1, 05.6.2, 05.7.1)

#### 20.2.1 Normalizasyon

Karşılaştırmadan önce iki normalizasyon uygulanır.

**Belge numarası normalizasyonu:** büyük harfe çevir, boşluk / tire / nokta / eğik çizgi
karakterlerini sil. `71 1234567` ve `71-1234567` aynı anahtara iner.

**İsim normalizasyonu (05.1, 05.2):** küçük harfe çevir → aksanları kaldır → Türkçe
karakterleri karşılıklarına indir (`ç→c`, `ş→s`, `ğ→g`, `ı→i`, `ö→o`, `ü→u`) → Kiril ve Arap
yazımı ICAO çeviri tablosuyla Latin'e çevir → noktalama ve çoklu boşlukları sadeleştir →
kelimeleri alfabetik sırala (ad sırası farkı eşleşmeyi bozmasın).

`Дмитрий Васильев`, `VASILIEV DMITRY` ve `Dmitry Vasiliev` aynı anahtara inmelidir.

#### 20.2.2 Karar tablosu

Sırayla değerlendirilir; **ilk uyan satır kazanır**, alttakilere bakılmaz.

| # | Koşul | `employee.action` | `matched_by` | Rota |
|---|---|---|---|---|
| 1 | Normalize belge numarası `employee_identifiers` içinde **tam** eşleşiyor ve **tek** çalışana ait | `match` | `document_number` | `hazir` |
| 2 | Aynı numara **birden fazla** çalışana ait | `none` | — | `unresolved` + `PERSON_AMBIGUOUS` |
| 3 | Numara eşleşmedi; normalize ad-soyad `employee_aliases` içinde eşleşiyor **ve** doğum tarihi eşit, **tek** çalışan | `match` | `name_dob` | `hazir` |
| 4 | İsim + doğum tarihi **birden fazla** çalışana uyuyor | `none` | — | `unresolved` + `PERSON_AMBIGUOUS` |
| 5a | Numara eşleşmedi; belgede doğum tarihi **okunmadı**; normalize ad-soyad birleştirilmemiş **tek** çalışana uyuyor (05.5.4) | `match` | `name` | `hazir` (çalışan pasifse 10.5.7 kuralıyla `unresolved`) |
| 5 | Yalnız isim eşleşti ve satır 5a uymuyor (belgedeki doğum tarihi farklı ya da çalışanın doğum tarihi kayıtlı değil) | `none` | — | `unresolved`, gerekçe: "İsim eşleşti ama doğum tarihi veya belge numarası doğrulanamadı" |
| 6 | Hiç eşleşme yok **ve** temiz belge numarası **var** (§20.2.3) | `create` | — | `hazir` |
| 6b | Hiç eşleşme yok, temiz numara **yok**, ama ad-soyad ve doğum tarihi §20.2.4'e uyuyor | `create` | — | `hazir` |
| 7 | Hiç eşleşme yok, satır 6 ve 6b uymuyor, ama ad-soyad okunabildi | `pending` | — | `unresolved`, payload'da önerilen profil |
| 8 | Kişi hiç tespit edilemedi (ne isim ne numara) | `none` | — | `unresolved` |

Satır 1 ve 3'te eşleşme başarılıysa: belgedeki yeni isim yazımı `employee_aliases`'a, yeni
belge numarası `employee_identifiers`'a eklenir (gereksinim 05.7.2). Satır 5a'da hiçbir şey birikmez:
isim yazımı, numara, profil alanı ve iletişim bilgisi eklenmez; kişisiz sayfalara sahip verilmez (05.5.4).
Satır 5a'nın "tek çalışan" sayımı birleştirilmemiş ve silinmemiş (`active` ve `inactive`) kayıtlar
üzerindedir. Doğum tarihi okunmamış belgenin adı birden çok böyle kayda uyuyorsa (biri pasif biri etkin olsa da)
rota `unresolved` + `PERSON_AMBIGUOUS`'tır (satır 4 gibi); satır 5'in gerekçesine düşmez.

**Pasif çalışan (gereksinim 10.5.7).** Tablo pasif (`inactive`) çalışanı da arar ve bulur — kimlik
gerçektir, sıra değişmez. Satır 1 ya da 3 pasif bir çalışanı bulursa belge otomatik yerleşmez: rota
`unresolved` olur, gerekçe `inactive_employee` kodunu ve çalışanın E numarasını taşır, çalışan kişi
tahmini olarak kalır; isim yazımı, numara, profil alanı ve iletişim bilgisi birikmez. İK öğeyi atar ya
da çalışanı yeniden etkinleştirip partiyi yeniden analiz eder.

#### 20.2.3 "Temiz belge numarası" tanımı

Satır 6'nın kapısı budur; yanlış tanımlanırsa hayalet çalışan doğar. Bir belge numarası
**ancak** şu üç koşulun hepsi sağlanırsa temizdir:

1. Türün `required_fields` listesinde `document_number` **var** (yani bu tür için numara
   beklenen bir alan).
2. Alan `legible: true` ve normalize edildikten sonra **en az 5 karakter**.
3. MRZ'den geldiyse: hem alan kontrol hanesi hem **bileşik** kontrol hanesi tutuyor
   (§20.1.7). MRZ yoksa bu koşul atlanır.

Üçünden biri sağlanmıyorsa numara temiz değildir → satır 6b denenir; o da uymuyorsa satır 7 (onay
bekleyen profil) uygulanır.

#### 20.2.4 Ad ve doğum tarihiyle açılış (satır 6b, gereksinim 05.6.2)

Satır 6b'nin kapısı budur (insan kararı 2026-09-26). Şu koşulların **hepsi** sağlanmalıdır:

1. Türün `required_fields` listesinde `date_of_birth` **var** (doğum tarihi bu tür için beklenen
   bir alan; çocuk doğum belgesi gibi başkasının doğum tarihini taşıyan tür bu yolu kullanmaz).
2. Ad-soyad klasör adı verecek biçimde Latin harfleriyle okunmuş (05.2.2); Latin yazım yoksa satır 7.
3. Doğum tarihi `legible: true`, anahtarda tek değer, sayfalar arasında çelişkisiz ve makul yaş
   doğrulamasından geçmiş.
4. Doğum tarihi ya ana modelin okumasıdır ya da kontrol haneleri tutan MRZ'den gelir; ucuz ön
   eleme modelinin doğrulanmamış okuması bu satıra dayanak olmaz (ön eleme, türün zorunlu
   alanlarında `date_of_birth` bulunan MRZ'siz sayfayı kolay saymaz, ana modele yükseltir).

Satır 6b'de temiz olmayan belge numarası `employee_identifiers`'a yazılmaz. Olay verisi
`basis: name_dob` taşır.

---

### 20.3 İşlem seçimi (gereksinim 06.2.1)

Bir belge adayı için hangi fiziksel işlemin uygulanacağı burada belirlenir. Girdi değişkenleri:

- **kaynak sayısı** — adayın sayfaları kaç ayrı dosyadan geliyor
- **kapsama** — tek kaynağın *tüm* sayfaları mı, yoksa alt kümesi mi
- **kaynak biçim** — PDF / JPEG / PNG / Office
- **hedef biçim** — türün `output_format` alanı (`keep` = kaynak biçimi koru)
- **gömülü görüntü** — sayfa tek bir tam sayfa görüntüden mi oluşuyor (02.5.1'in çıktısı)

Sırayla değerlendirilir; **ilk uyan satır kazanır**.

| # | Kaynak | Kapsama | Kaynak → hedef biçim | Seçilen işlem |
|---|---|---|---|---|
| 1 | Tek dosya | Tüm sayfalar | Aynı biçim (veya `output_format: keep`) | `passthrough` |
| 2 | Tek PDF | Alt küme, **ardışık** | PDF → PDF | `extract` |
| 3 | Birden çok dosya (aynı parti) | — | → PDF | `merge` |
| 4 | Tek JPEG/PNG | Tek sayfa | Görüntü → PDF | `wrap_image` |
| 5 | Tek PDF | Tek sayfa | PDF → JPEG, sayfada gömülü tek görüntü **var** | `extract_image` |
| 6 | Tek PDF | Tek sayfa | PDF → JPEG, gömülü tek görüntü **yok** | `render_image` |
| 7 | Yukarıdakilerin hiçbiri | — | — | işlem yok → `unresolved`, gerekçe yazılır |

Seçilen işlem sonra **§20.4'teki izin matrisinden** geçirilir. Matris reddederse rota
`unresolved` olur; işlem uygulanmaz.

Ayrıca 3, 4, 5 ve 6 numaralı satırlar için seçilen işlem türün `allowed_conversions`
listesinde bulunmak zorundadır (gereksinim 06.4.1); yoksa `unresolved`.

Satır 2'deki **ardışıklık** şartı K5'tir: sayfalar arasında başka belgeye ait sayfa varsa
bu satır uygulanmaz, aday zaten karar motorunda (04.2.1) bölünmüş olmalıdır.

---

### 20.4 Direkt Belge izin matrisi (gereksinim 06.3.1, 06.3.2)

`known_document_types.direct` bayrağı bir belge türünün fiziksel bütünlüğünün korunması
gerektiğini söyler (K3). Matris kesindir:

| İşlem | `direct: true` | `direct: false` |
|---|---|---|
| `passthrough` | izinli | izinli |
| `extract` (tek kaynak, ardışık sayfalar) | **izinli** | izinli |
| `merge` | yasak | izinli (dönüşüm izinliyse) |
| `wrap_image` | yasak | izinli (dönüşüm izinliyse) |
| `extract_image` | yasak | izinli (dönüşüm izinliyse) |
| `render_image` | yasak | izinli (dönüşüm izinliyse) |

Yasak bir işlem seçilmişse: rota `unresolved`, gerekçe "Direkt Belge: `<işlem>` bu tür için
yapılamaz", olay `DIRECT_DOC_CHECK`.

**`extract` neden izinli?** Bir dosyanın içinden sayfa çıkarmak belgeye bir şey eklemez ve
içeriğini değiştirmez — yalnız fazlalığı ayırır. Yasak olan, belgeyi **başka kaynaklardan
kurmak**tır.

#### 20.4.1 Format kontrolü

Direkt türlerde işlemden önce ayrıca şu kontrol yapılır (gereksinim 06.3.2):

Kaynak dosyanın biçimi türün `expected_file_types` listesinde **yoksa** hiçbir işlem
uygulanmaz. Rota `unresolved`, gerekçe: `"Direkt Belge: beklenen dosya türü <liste>, gelen
<biçim>. Uygun formatta yeniden gönderin."`

Bu, sistemin dönüştürerek "kurtarmaya" çalışmasını engeller — dönüştürme bir pasaportun
bütünlüğünü bozar (K3).

---

### 20.5 Dosya işlemlerinde kayıpsızlık sözleşmesi (gereksinim 07.1.1–07.6.1)

Her işlem için **hangi yöntemin kullanılacağı** ve **neyin kesinlikle yapılmayacağı**
aşağıdadır. Ortak kural: hiçbir işlem görüntüyü yeniden kodlamaz, hiçbir işlem sayfa
içeriğini yeniden çizmez (K11).

#### `passthrough` (07.1.1)

Kaynak dosya **bayt bayt** kopyalanır. Yeniden yazma, yeniden kaydetme, kütüphaneden geçirme
yoktur. Doğrulama: çıktının SHA-256'sı kaynağınkine **eşit** olmalıdır.

#### `extract` (07.2.1)

`pypdf` ile: kaynak `PdfReader`'dan hedef `PdfWriter`'a **sayfa nesnesi** eklenir
(`writer.add_page(reader.pages[i])`). Sayfa nesnesi kopyalandığı için içerik akışı,
gömülü fontlar ve görüntüler olduğu gibi taşınır.

**Yapılmayacaklar:** içerik akışını sıkıştırma/yeniden yazma (`compress_content_streams`
çağrılmaz), sayfayı görüntüye çevirip yeniden PDF'e koyma, sayfa boyutu/döndürme değiştirme.

Doğrulama: çıktının sayfa sayısı beklenen kadar olmalı **ve** her çıktı sayfasının çıkarılan
metin katmanı, kaynaktaki karşılık gelen sayfanın metin katmanıyla **birebir aynı** olmalıdır.

#### `merge` (07.3.1)

`extract` ile aynı yöntem, tek fark birden çok kaynaktan sırayla sayfa alınması. Sıra, plan
öğesindeki `sources` dizisinin sırasıdır — yeniden sıralama yapılmaz. Yalnız `direct: false`
türlerde çalışır (§20.4).

#### `wrap_image` (07.4.1)

`img2pdf.convert()` kullanılır. JPEG girdide görüntü verisi PDF içine **yeniden kodlanmadan**
gömülür; bu, `Pillow` ile açıp kaydetmenin aksine kayıpsızdır.

**Bilinen tuzak:** `img2pdf` alfa kanalı (şeffaflık) içeren PNG'leri reddeder. Bu durumda
görüntü kayıpsız biçimde alfasız RGB'ye düzleştirilir (beyaz zemin) ve bu işlem olay loguna
yazılır. Alfa dışında hiçbir piksel dönüşümü yapılmaz.

#### `extract_image` (07.5.1)

`PyMuPDF` ile: sayfadaki görüntü nesnesinin `xref`'i bulunur, `doc.extract_image(xref)`
çağrılır. Dönen sözlükteki `image` alanı **orijinal gömülü baytlardır**; `ext` alanı gerçek
biçimi verir. Bu baytlar diske olduğu gibi yazılır.

**Yapılmayacaklar:** `Pillow` ile açıp kaydetme, yeniden boyutlandırma, kalite ayarı.
Çıkan biçim JPEG değilse (örn. PNG) dosya uzantısı `ext`'e göre yazılır.

Bu işlem yalnız 02.5.1'in sayfayı "tek tam sayfa görüntü" olarak işaretlediği durumda seçilir.

#### `render_image` (07.6.1)

Gömülü görüntü yoksa son çare budur ve **kayıplıdır**: sayfa `page.get_pixmap(dpi=…)` ile
sabit çözünürlükte rasterleştirilip JPEG olarak kaydedilir. DPI ve JPEG kalitesi yapılandırma
değeridir, görev içinde sabit yazılmaz.

Yalnız türün `allowed_conversions` listesinde `pdf_to_jpeg` varsa seçilebilir (§20.3 satır 6).

#### Ortak: çıktı yazma (07.7.1)

Tüm işlemler çıktıyı **atomik** yazar (geçici dosyaya yaz, sonra yeniden adlandır — 00.4.4).
Yazma tamamlandıktan sonra `documents` kaydına kaynak dosya kimliği ve sayfa aralığı
(`source_refs_json`) işlenir; `OUTPUT_SAVED` olayı bu köken bilgisiyle loglanır (K15, R13).

---

### 20.6 İki aşamalı onay metinleri (gereksinim 10.8.1, 10.8.2, 10.7.2, 10.7.3, 08.4.1, 11.5.2, 10.3.4, 10.5.6, 10.5.7, 10.5.8, 10.5.9, 10.5.10, 10.7.4, 10.10.4)

K16'daki manuel işlemler iki aşamalı onay ister (salt geri alma işlemleri tek adımdır, K16). Metinler **birebir** aşağıdaki
gibidir; pencere kendi cümlesini yazmaz. `<…>` yer tutucuları çalışma zamanında doldurulur.

| İşlem | Birinci onay | İkinci onay |
|---|---|---|
| Belgeyi başka çalışana taşı | `Bu belgeyi başka bir çalışana taşımak üzeresiniz. Emin misiniz?` | `Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?` |
| Kuyruk öğesini çalışana ata | `Bu belgeyi <Ad Soyad> çalışanına atamak üzeresiniz. Emin misiniz?` | `Bu işlem sistemdeki belge organizasyonunu değiştirecektir. Son kararınız mı?` |
| Onay bekleyen profili onayla | `<Ad Soyad> için yeni bir çalışan profili oluşturmak üzeresiniz. Emin misiniz?` | `Bu işlem sistemde kalıcı bir çalışan kaydı oluşturacaktır. Son kararınız mı?` |
| Yeni belge türünü onayla | `<Tür adı> belge türünü standart türler arasına eklemek üzeresiniz. Emin misiniz?` | `Bu işlem bundan sonraki tüm belge analizlerini etkileyecektir. Son kararınız mı?` |
| Belgeyi arşive taşı | `Bu belgeyi arşive taşımak üzeresiniz. Emin misiniz?` | `Belge çalışanın Hazır klasöründen çıkacaktır. Son kararınız mı?` |
| Taramayı yoksay | `Bu taramayı yoksaymak üzeresiniz. Emin misiniz?` | `Parti ve bekleyen <N> kuyruk öğesi listelerden kalkacaktır; üretilmiş <M> belge yerinde kalır. Son kararınız mı?` |
| Çalışan profilini düzenle | `Bu çalışanın profil bilgilerini değiştirmek üzeresiniz. Emin misiniz?` | `Ad ya da soyad değiştiyse klasör ve <N> belge dosyası yeniden adlandırılacaktır. Son kararınız mı?` |
| Çalışanı pasife al | `<Ad Soyad> çalışanını pasife almak üzeresiniz. Emin misiniz?` | `Bu çalışana gelen yeni belgeler otomatik yerleşmeyecek, kuyruğa düşecektir. Son kararınız mı?` |
| Çalışanı yeniden etkinleştir | `<Ad Soyad> çalışanını yeniden etkinleştirmek üzeresiniz. Emin misiniz?` | `Çalışan listeye dönecek ve yeni belgeleri yeniden otomatik yerleşecektir. Son kararınız mı?` |
| Profil alt kaydını kaldır | `Bu kaydı çalışan profilinden kaldırmak üzeresiniz. Emin misiniz?` | `Kayıt eşleştirmede ve aramada kullanılmayacak, geçmişte kalacaktır. Son kararınız mı?` |
| İki çalışanı birleştir | `<Birleşen Ad Soyad> kaydını <Kalan Ad Soyad> kaydıyla birleştirmek üzeresiniz. Emin misiniz?` | `<N> belge taşınacak ve birleşen kayıt kapanacaktır; bu işlem geri alınamaz. Son kararınız mı?` |
| Belgeyi arşivden geri al | `Bu belgeyi arşivden geri almak üzeresiniz. Emin misiniz?` | `Belge çalışanın Hazır klasörüne dönecektir. Son kararınız mı?` |
| Kuyruk öğesini kapat | `Bu kuyruk öğesini kapatmak üzeresiniz. Emin misiniz?` | `Öğe çözülmüş sayılacak, dosya kopyası ve gerekçesi yerinde kalacaktır. Son kararınız mı?` |

İlk iki satırdaki metinler ürün tanımında birebir bu şekilde yazılmıştır; **değiştirilmez**.
Kalan satırlar aynı kalıptan türetilmiştir: birinci cümle *ne yapılacağını*, ikinci cümle
*geri dönüşü olmayan sonucu* söyler.

#### 20.6.1 Sunucu tarafı mekanizma

Onay metinlerini göstermek tek başına yeterli değildir — istemci atlanabilir. Akış:

1. İstemci **birinci** onayı aldıktan sonra sunucuya "hazırlık" isteği gönderir.
2. Sunucu tek kullanımlık bir **onay belirteci** üretir: rastgele, tahmin edilemez, işlemin
   kimliğine (işlem türü + hedef kayıt) bağlı ve **10 dakika** geçerli.
3. İstemci **ikinci** onayı aldıktan sonra asıl isteği bu belirteçle gönderir.
4. Sunucu belirteci doğrular ve **tüketir** (aynı belirteçle ikinci istek reddedilir).
5. Belirteçsiz, süresi geçmiş veya başka bir işleme ait belirteçle gelen istek `400` ile
   reddedilir; işlem yapılmaz.

Onay tamamlandığında `USER_CONFIRMED` olayı yazılır: kullanıcı adı, işlem türü, hedef kayıt,
birinci ve ikinci onayın zaman damgaları. Ardından işlemin kendi olayı (`MANUAL_MOVE`,
`MANUAL_ASSIGN`, `MANUAL_APPROVE`, `TYPE_APPROVED`, `ARCHIVED`, `UPLOAD_DISMISSED`,
`EMPLOYEE_EDITED`, `EMPLOYEE_DEACTIVATED`, `EMPLOYEE_REACTIVATED`, `PROFILE_RECORD_REMOVED`,
`EMPLOYEE_MERGED`, `UNARCHIVED`, `QUEUE_ITEM_CLOSED`)
düşülür.

#### 20.6.2 Testte doğrulanacak davranış

- Yalnız birinci onayla gönderilen istek **hiçbir değişiklik yapmaz** (S16).
- Aynı belirteçle ikinci kez gönderilen istek reddedilir.
- Süresi geçmiş belirteçle gelen istek reddedilir.
- Başarılı işlemde olay logunda kullanıcı adı ve iki zaman damgası bulunur.

#### 20.6.3 İngilizce ve Sırpça karşılıklar (gereksinim 10.10.4)

Yukarıdaki tablo kaynaktır; İngilizce (`en`) ve Sırpça (`sr`, Latin) panelde metinler **birebir** aşağıdaki gibidir.
Yer tutucular (`<Ad Soyad>`, `<Birleşen Ad Soyad>`, `<Kalan Ad Soyad>`, `<Tür adı>`, `<N>`, `<M>`) her dilde aynı
yazılır ve aynı değerle doldurulur. Sayı alan cümleler sayının çoğul uyumunu gerektirmeyecek biçimde kurulmuştur
("… (<N>) …"). `Hazir`, çalışanın fiziksel klasörünün adıdır; çevrilmez.

| İşlem | Birinci onay (en) | İkinci onay (en) | Birinci onay (sr) | İkinci onay (sr) |
|---|---|---|---|---|
| Belgeyi başka çalışana taşı | `You are about to move this document to another employee. Are you sure?` | `This action will change the document organization in the system. Is this your final decision?` | `Upravo ćete premestiti ovaj dokument drugom zaposlenom. Da li ste sigurni?` | `Ova radnja će promeniti organizaciju dokumenata u sistemu. Da li je to vaša konačna odluka?` |
| Kuyruk öğesini çalışana ata | `You are about to assign this document to employee <Ad Soyad>. Are you sure?` | `This action will change the document organization in the system. Is this your final decision?` | `Upravo ćete dodeliti ovaj dokument zaposlenom <Ad Soyad>. Da li ste sigurni?` | `Ova radnja će promeniti organizaciju dokumenata u sistemu. Da li je to vaša konačna odluka?` |
| Onay bekleyen profili onayla | `You are about to create a new employee profile for <Ad Soyad>. Are you sure?` | `This action will create a permanent employee record in the system. Is this your final decision?` | `Upravo ćete kreirati novi profil zaposlenog za <Ad Soyad>. Da li ste sigurni?` | `Ova radnja će kreirati trajni zapis o zaposlenom u sistemu. Da li je to vaša konačna odluka?` |
| Yeni belge türünü onayla | `You are about to add the document type <Tür adı> to the standard types. Are you sure?` | `This action will affect all future document analyses. Is this your final decision?` | `Upravo ćete dodati tip dokumenta <Tür adı> među standardne tipove. Da li ste sigurni?` | `Ova radnja će uticati na sve buduće analize dokumenata. Da li je to vaša konačna odluka?` |
| Belgeyi arşive taşı | `You are about to move this document to the archive. Are you sure?` | `The document will leave the employee's Hazir folder. Is this your final decision?` | `Upravo ćete premestiti ovaj dokument u arhivu. Da li ste sigurni?` | `Dokument će biti uklonjen iz fascikle Hazir zaposlenog. Da li je to vaša konačna odluka?` |
| Taramayı yoksay | `You are about to dismiss this scan. Are you sure?` | `The batch and its pending queue items (<N>) will be removed from the lists; generated documents (<M>) stay in place. Is this your final decision?` | `Upravo ćete zanemariti ovo skeniranje. Da li ste sigurni?` | `Serija i njene stavke reda na čekanju (<N>) biće uklonjene sa spiskova; generisani dokumenti (<M>) ostaju na mestu. Da li je to vaša konačna odluka?` |
| Çalışan profilini düzenle | `You are about to change this employee's profile information. Are you sure?` | `If the first or last name changed, the folder and the document files (<N>) will be renamed. Is this your final decision?` | `Upravo ćete izmeniti podatke profila ovog zaposlenog. Da li ste sigurni?` | `Ako je ime ili prezime promenjeno, fascikla i datoteke dokumenata (<N>) biće preimenovane. Da li je to vaša konačna odluka?` |
| Çalışanı pasife al | `You are about to deactivate employee <Ad Soyad>. Are you sure?` | `New documents for this employee will not be placed automatically; they will go to the queue. Is this your final decision?` | `Upravo ćete deaktivirati zaposlenog <Ad Soyad>. Da li ste sigurni?` | `Novi dokumenti za ovog zaposlenog neće se automatski raspoređivati, već će ići u red. Da li je to vaša konačna odluka?` |
| Çalışanı yeniden etkinleştir | `You are about to reactivate employee <Ad Soyad>. Are you sure?` | `The employee will return to the list and new documents will again be placed automatically. Is this your final decision?` | `Upravo ćete ponovo aktivirati zaposlenog <Ad Soyad>. Da li ste sigurni?` | `Zaposleni će se vratiti na spisak, a novi dokumenti će se ponovo automatski raspoređivati. Da li je to vaša konačna odluka?` |
| Profil alt kaydını kaldır | `You are about to remove this record from the employee profile. Are you sure?` | `The record will no longer be used for matching or search and will remain in the history. Is this your final decision?` | `Upravo ćete ukloniti ovaj zapis iz profila zaposlenog. Da li ste sigurni?` | `Zapis se više neće koristiti za uparivanje i pretragu i ostaće u istoriji. Da li je to vaša konačna odluka?` |
| İki çalışanı birleştir | `You are about to merge the record <Birleşen Ad Soyad> into the record <Kalan Ad Soyad>. Are you sure?` | `The documents (<N>) will be moved and the merged record will be closed; this action cannot be undone. Is this your final decision?` | `Upravo ćete spojiti zapis <Birleşen Ad Soyad> sa zapisom <Kalan Ad Soyad>. Da li ste sigurni?` | `Dokumenti (<N>) biće premešteni, a spojeni zapis biće zatvoren; ova radnja se ne može poništiti. Da li je to vaša konačna odluka?` |
| Belgeyi arşivden geri al | `You are about to restore this document from the archive. Are you sure?` | `The document will return to the employee's Hazir folder. Is this your final decision?` | `Upravo ćete vratiti ovaj dokument iz arhive. Da li ste sigurni?` | `Dokument će se vratiti u fasciklu Hazir zaposlenog. Da li je to vaša konačna odluka?` |
| Kuyruk öğesini kapat | `You are about to close this queue item. Are you sure?` | `The item will be considered resolved; its file copy and reason will stay in place. Is this your final decision?` | `Upravo ćete zatvoriti ovu stavku reda. Da li ste sigurni?` | `Stavka će se smatrati rešenom; kopija datoteke i obrazloženje ostaju na mestu. Da li je to vaša konačna odluka?` |
