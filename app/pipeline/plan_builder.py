"""Plan JSON üretimi, belirleyicilik, işlem seçimi, Direkt Belge kuralı, dönüşüm izni, doğrulama,
profil fotoğrafı kuralları ve profilden yüklemede kişi denetimi — PRD 06.1.1, 06.1.2, 06.2.1,
06.3.1, 06.3.2, 06.4.1, 06.5.1, 06.5.2, 11.7.1, 10.5.5 (§8.5, §20.1.6, §20.1.7, §20.3, §20.4; K1,
K3, K9, K11, K12, R5, R10, R7; PLAN.md §C83).

Karar motorunun bir parti için verdiği bütün kararlar tek bir **Plan JSON**'da dondurulur (K9):
uygulayıcı (07.x) ve kuyruk (08.1) planı yürütür, yapay zekâya ya da eşleştirmeye yeniden sormaz.
`create_plan` partiyi gruplar (04.1–04.7), her öğenin kararını verir, planı `plans` tablosuna
hash'iyle yazar ve `PLAN_CREATED` olayını atar.

**Öğeler.** Plan partinin her dosyasını ve tekrar olmayan dosyaların her sayfasını tam bir öğeye
bağlar; hiçbir sayfa sessizce düşmez (R7):

- Her belge adayı (dosya içi ve dosyalar arası) bir öğedir. `sources` adayın sayfalarını dosya
  başına, belgedeki sırasıyla taşır — dosyalar arası adayda önce ön yüzün dosyası.
- Word/Excel eki (04.7.1) bir öğedir; dosya bütün olarak alınır (`pages: []`).
- Dosyanın boş sayfaları (02.4.1 ve analizcinin boş dediği sayfalar) tek bir `skip` öğesidir (S8).
- Dosyanın analizi yapılamamış sayfaları tek bir `unresolved` öğesidir: içerikleri bilinmez.
- Sayfası olmayan ve Word/Excel eki olarak tanınmayan dosya `unresolved` öğesidir.
- Tekrar yüklenen dosya (01.4.1) `skip` öğesidir; yeniden işlenmez (S2).

Öğeler dosya (`upload_files.id`) ve ilk sayfa sırasıyla dizilir; `item_id` bu sırayla `i1`, `i2`…
verilir ve kararlar da bu sırayla alınır: aynı partide açılan çalışan sonraki öğede bulunur.

**Rota.** Belge adayının hükümleri şu öncelikle okunur; ilk hüküm rotayı verir, kuyruğa gönderen
bütün hükümlerin gerekçeleri (`route_reason`) aynı sırayla birleşir:

1. Bilinmeyen tür (04.6.1) → `unknown`.
2. Yapısal hüküm — ardışıklık (04.2.1), belirsiz eşleştirme (04.3.2), yapı doğrulayıcıları: sayfa
   sayısı (`page_count`, 04.5.1) ve yüzler (`sides`) → `unresolved`. Yapısal hükümlü aday eksik ya
   da parça bir belgedir: okunaklılık kapısı, öteki doğrulayıcılar ve işlem seçimi ona uygulanmaz
   (yalnız arka yüzden oluşan parça "okunamayan alanlar" almaz).
3. Okunaklılık kapısı ve doğrulayıcılar (04.4, 06.5.1) — zorunlu alan okunmuyorsa
   (`required_fields`) `unreadable`; kabul kriteri karşılanmıyorsa, Direkt Belge tek kaynağın
   ardışık sayfaları değilse (`direct_single_source`), kaynak biçimi beklenmiyorsa (`file_type`;
   Direkt Belge'de 06.3.2), MRZ kontrol hanesi tutmuyorsa (`mrz_checksum`) ya da doğum tarihi
   inanılır değilse (`dob_plausible`) ya da bağlam çalışanlı yüklemede belge bağlam çalışanına ait
   görünmüyorsa (`context_person`, 10.5.5) `unresolved`. MRZ önceliği (05.3.3) kapıdan ve kişi
   anahtarından önce her sayfaya uygulanır. Fotoğraf türünde açık bir kural `fail` ya da
   değerlendirilmemişse (11.7.1) `unresolved`; gerekçesi doğrulayıcılarınkinden sonra gelir.
4. İşlem — işlem seçimi (06.2.1), Direkt Belge matrisi (06.3.1) ve dönüşüm izni (06.4.1): §20.3'te
   uyan satır yoksa (satır 7), matris işlemi yasaklıyorsa ya da dönüşüm türün
   `allowed_conversions`'ında değilse `unresolved`. Kaynak doğrulayıcılarından
   (`direct_single_source`, `file_type`) biri geçmeyen belgede işlem seçilmez.
5. Çalışan kararı (§20.2.2).

Hiçbir hüküm yoksa rota `hazir`dır.

**İşlem (06.2.1).** `select_operation` belge adayının ve Word/Excel ekinin fiziksel işlemini §20.3
karar tablosuyla seçer; satırlar sırayla denenir, ilk uyan kazanır:

1. Tek dosya, dosyanın tüm sayfaları, hedef biçim kaynağınki → `passthrough` (Word/Excel eki dahil).
2. Tek PDF, sayfalarının ardışık alt kümesi, hedef PDF → `extract`.
3. Birden çok dosya, hedef PDF → `merge`.
4. Tek JPEG/PNG, tek sayfa, hedef PDF → `wrap_image`.
5. Tek PDF, tek sayfa, hedef JPEG, sayfa tek tam sayfa gömülü görüntü (02.5.1) → `extract_image`.
6. Tek PDF, tek sayfa, hedef JPEG, gömülü tek görüntü yok → `render_image`.
7. Hiçbiri → işlem yok, `unresolved`; gerekçe kaynakları, kapsamayı ve hedef biçimi yazar.

Kaynak biçimi içerikten tespit edilir (01.2.1); istemcinin bildirdiği `mime`'a güvenilmez. Hedef
biçim türün `output_format`'ıdır; `keep` kaynakların ortak biçimidir — kaynaklar farklı biçimdeyse
ya da biçimi tanınmıyorsa hedef yoktur ve hiçbir satır uymaz. Kapsama dosyanın sayfa satırlarıyla
ve `page_count`'uyla ölçülür: dosyanın adayda olmayan tek bir sayfası (boş sayfa dahil) adayı alt
küme yapar, boş sayfa çıktıya girmez (S8). Ardışıklık K5'tir: alınan sayfaların arasında boş sayfa
dışında sayfa yoksa ardışıktır. Seçim okunaklılık kapısından sonra, çalışan kararından önce yapılır:
işlemi olmayan belgeden çalışan açılmaz, kimlik birikmez. İşlem ve hedef yalnız `hazir` öğede plana
girer; kuyruğa giden öğenin işlemi yoktur (§20.4: reddedilen işlem uygulanmaz).

**Direkt Belge (06.3.1, 06.3.2).** `direct: true` türün (K3) işlemi §20.4'ten geçer; belge adayı
da Word/Excel eki de. Önce format kontrolü (§20.4.1; türün `file_type` doğrulaması): kaynaklardan
birinin içerikten tespit edilen biçimi türün `expected_file_types`'ında yoksa — tanınmayan biçim de
yoktur — işlem seçilmez ve belge "Uygun formatta yeniden gönderin." gerekçesiyle Unresolved'a gider;
dönüştürülerek kurtarılmaz (S6).
Format tutarsa §20.3 işlemi seçer ve izin matrisi uygulanır: Direkt Belge'de yalnız `passthrough` ve
`extract` (tek kaynağın sayfaları olduğu gibi) izinlidir; `merge`, `wrap_image`, `extract_image` ve
`render_image` yasaktır, işlem plana girmez, belge Unresolved'a gider. İlk ret sonraki adımı keser:
format tutmayan belgede işlem seçilmez, uyan satırı olmayan belgede matris denenmez. Ret gerekçesi
okunaklılık gerekçelerinin ardından gelir ve `DIRECT_DOC_CHECK` olayına adayın ilk sayfasıyla (ekte
dosyayla) yazılır; izinli işlem olay atmaz, planda durur. `direct: false` sütununun "dönüşüm
izinliyse" şartı (`allowed_conversions`) 06.4.1'indir.

**Dönüşüm izni (06.4.1).** §20.3 satır 3–6'nın işlemleri — `merge`, `wrap_image`, `extract_image`,
`render_image` — dönüşümdür (K12) ve türün `allowed_conversions` listesinde bulunmak zorundadır;
`passthrough` ve `extract` dönüşüm değildir, her türde izinlidir. Kontrol matristen sonra yapılır
(Direkt Belge'nin listesi boştur ve matris dönüşümü zaten reddeder). Listede olmayan dönüşüm plana
girmez, başka bir satıra düşülmez — gömülü tek görüntülü sayfada izinsiz `extract_image` yerine
`render_image` denenmez (K12) — ve belge dönüştürülmeden gerekçesiyle Unresolved'a gider. Gerekçe
okunaklılık gerekçelerinin ardından gelir. Olay atılmaz: §8.3'te dönüşüm izni için tür yoktur, ret
planın gerekçesinde durur.

**Profil fotoğrafı (11.7.1, 11.7.2).** Kural seti olan türün (`PHOTO_RULE_TYPES`) belge adayı,
yapı doğrulamasından geçtiyse, türün **planlama anındaki** açık kurallarıyla (`enabled_photo_rules`)
değerlendirilir; kurallar adayın sayfalarına analizde saklanan kontrolden okunur
(`pages.photo_check_json`, `app.pipeline.analyze`) — yapay zekâya yeniden sorulmaz (K9).
`check_photo_rules`: bir sayfada `fail` olan kural ihlaldir; bir sayfada sonucu olmayan açık kural
(kontrol yok, okunamıyor ya da o kural sorulmamış) değerlendirilmemiştir — ikisi de belgeyi
Unresolved'a gönderir, emin olunamayan fotoğraf Hazir'a girmez. `unsure` yalnız nottur, rota
vermez; notu sayfanın kaydında durur. Kapalı kural, sonucu saklı olsa da okunmaz. Gerekçe kural
adlarını katalog sırasıyla yazar (ölçülen çözünürlük sistemin notuyla); yapay zekânın notu
gerekçeye girmez. Kuyruğa giden fotoğrafın sahibi aynı dosyadan alınmaz (aşağıda: belge düzeyindeki
ret). Fotoğraf kural yüzünden değiştirilmez: kırpma, düzeltme, arka plan değişikliği işlemi yoktur
(11.7.2, K11); Hazir'a giden fotoğrafın çıktısı §20.3'ün seçtiği işlemle kaynaktan üretilir. Olay
atılmaz (§8.3'te tür yok): hüküm planın gerekçesinde ve kuyruk olayında durur.

**Çalışan.** Her analizli adayın kişi anahtarı (05.4) kayıtlı çalışanlarla eşleştirilir (05.5).
Kararın yan etkileri yalnız belge düzeyinde kabul edilen adayda (1–4'te hükmü olmayan) yürür:
satır 1/3 eşleşmesinde yeni isim yazımı, temiz numara ve iletişim bilgisi çalışana eklenir (05.7.2,
05.8) ve boş profil alanları belgeden dolar (05.7.3); satır 5a'nın isim eşleşmesinde (05.5.4,
doğum tarihi taşımayan belge, tek etkin çalışan) belge Hazir'a `matched_by: name` ile gider ama
hiçbir şey birikmez; eşleşme yoksa satır 6'da (temiz numara) ya
da 6b'de (Latin ad-soyad + doğum tarihi, §20.2.4) çalışan açılır (05.6; alanlarının kaynağı belgeye
bağlanır, 05.7.3), satır 7'de profil onaya önerilir (05.7.1), satır 8 ve tablo dışı eksik kişi
Unresolved'a gider. Kuyruğa giden adaydan çalışan açılmaz, profil
önerilmez, kimlik, profil alanı ya da iletişim bilgisi birikmez — yapısı veya okunaklılığı kabul
edilmemiş belgenin okumasına güvenilmez. Eşleştirme hükmü o adayda yalnız kişi tahmini olarak kalır
(08.1.2): satır 1/3'te `match` ve çalışan, öteki hükümlerde (satır 5a'nın isim eşleşmesi dahil:
okunması kabul edilmemiş belgede isim yetmez, R8) `none`; eşleştirme hükmü de kuyruğa gönderiyorsa
(satır 2, 4, 5a'nın belirsizi, 5, çelişkili anahtar) gerekçesi eklenir. Satır 5a'nın pasif
çalışanı (10.5.7) kabul edilmiş belgede kişi tahminidir.

**Profilden yüklemede kişi denetimi (10.5.5, PLAN.md §C83).** Parti bir bağlam çalışanıyla
yüklendiyse (`uploads.context_employee_id`) yapı doğrulamasından geçen her analizli adayın kişi
anahtarı bağlam çalışanıyla karşılaştırılır (`app.matching.context`: temiz belge numarası → doğum
tarihi → ad). `different` hükmü `context_person` doğrulayıcısını geçirmez: öğe Unresolved'a gider,
çalışanı `none`dır — kişi tahmini de yoktur, eşleştirme başka bir çalışanı bulsa bile belge ona
otomatik gitmez —, çalışan açılmaz, profil önerilmez, isim yazımı, numara, iletişim bilgisi ve
profil alanı birikmez (05.7.2, 05.8.1, 05.7.3). Gerekçe uyuşmayan adımı yazar, değeri yazmaz;
geçmeyen doğrulama her doğrulayıcı gibi `VALIDATION_FAILED` olayına düşer. `same` ve `unknown`
akışı değiştirmez; bağlam K6'yı gevşetmez — bağlamlı yüklemede satır 5'in yalnız isim eşleşmesi
yine Unresolved'a gider, satır 5a bağlamsız yüklemedeki gibidir. Word/Excel eki (04.7.1) bu
denetime girmez.

**Kişi taşımayan belgenin sahibi (D29, §9 S3/S4).** Zorunlu alanı olmayan türün (profil
fotoğrafı) belge düzeyinde kabul edilmiş, satır 8'e düşen adayı — ne numara ne isim okunmuş —
aynı yüklenen dosyadaki kimlikli adaylardan sahip alır: o dosyanın sayfasını taşıyan, kişi anahtarı
bir şey okumuş adayların hepsi tek bir kayıtlı çalışana satır 1/3 ile bağlıysa (kuyruğa gidende kişi
tahmini) ve en az biri Hazir'a gidiyorsa öğe o çalışanla (`match`, `matched_by: null`) Hazir'a
gider. Yeni açılan çalışan (satır 6, 6b), onay bekleyen profil, belirsiz, yalnız isim ya da
çelişkili hüküm, satır 5a'nın isim eşleşmesi (05.5.4), ikinci bir çalışan, partinin başka dosyası
ve bağlam çalışanı sahip vermez; o zaman satır 8 (Unresolved) aynen kalır. Kural yalnız kişi
hükmünü değiştirir: belge düzeyindeki ret (işlem, dosya türü) onu ezer, kimlik ve iletişim bilgisi
birikmez, olay atılmaz. Sahip, kimlikli adayların hükmü belli olduktan sonra, ikinci geçişte
bulunur; öğe kimlikleri ve sırası değişmez.

Word/Excel ekinin sahibi partinin bağlam çalışanıdır (`match`, `matched_by: null`); bağlam yoksa ek
Unresolved'a gider (04.7.1). İşlemi olmayan ekte işlem gerekçesi sahiplik gerekçesinden önce gelir;
bağlam çalışanı kişi tahmini kalır.

**Hedef.** Yalnız `hazir` öğede dolar ve orada zorunludur. `target_format` seçilen işlemin hedef
biçimidir (yukarıda). `target_name` çalışan kaydının ad-soyadı ve türün `file_label`'ıyla K8 adıdır
(`Ad_Soyad-Passport.pdf`); sıra eki (`-2`) plana girmez, yazma anında diskte seçilir (00.4.3, 07.7).

**Doğrulama (06.5.1, 06.5.2).** Doğrulayıcılar `app/pipeline/validate.py`'dedir; sonuçları
öğenin `validations`'ına adı ve `ok` değeriyle, 06.5.1 sırasıyla (`ValidationName`) girer. Katalog
türündeki belge adayı önce yapı doğrulayıcılarından (`page_count`, `sides`) geçer: biri geçmezse
aday eksik ya da parça bir belgedir, öğe yalnız bu ikisini taşır ve sonraki adımlar uygulanmaz.
Geçerse yedisinin hepsinden — bağlam çalışanlı yüklemede sekizinci olarak `context_person`'dan da
— geçer; kaynak doğrulayıcıları (`direct_single_source`, `file_type`) işlem seçiminden önce
değerlendirilir. Word/Excel eki (K2: sayfası ve analizi yok) yalnız kaynak
doğrulayıcılarından geçer. Bilinmeyen tür, ardışıklık ya da belirsiz eşleştirme hükmü taşıyan aday
ile boş sayfa, analizsiz sayfa ve dosya öğeleri doğrulanmaz (`validations: []`). Geçmeyen doğrulama
öğeyi kuyruğa gönderir — `required_fields` Unreadable'a (K1), ötekiler Unresolved'a — ve
gerekçesi doğrulayıcı sırasıyla `route_reason`'a eklenir; kabul kriteri gerekçesi
`required_fields`'ınkinin hemen ardından, işlem gerekçesi doğrulayıcılarınkinden sonra gelir. Her
geçmeyen doğrulama `VALIDATION_FAILED` olayına öğenin ilk sayfasıyla (ekte dosyasıyla) yazılır:
mesaj gerekçe, veri `item_id`, `validation`, `document_type_slug`, `queue`. Direkt Belge'nin
`file_type` reddi §20.4.1'in gerekçesini ve `DIRECT_DOC_CHECK` olayını da taşır. Doğrulaması
geçmeyen belgeden çalışan açılmaz, kimlik ya da iletişim bilgisi birikmez (D13). `hazir` öğe
doğrulanmış öğedir: `validations` doludur ve hepsi `ok`; sözleşme aksini reddeder, uygulayıcı
doğrulanmamış öğeyi yürütmez.

**Belirleyicilik (06.1.2).** Plan yalnız kalıcı girdilerin işlevidir: saklanan sayfa analizleri,
güncel katalog, planlama anındaki çalışan kayıtları ve parti (bağlam çalışanı, dosyalar). Zaman
damgası, rastgele değer ve sözlük sırası plana girmez; MRZ doğum tarihinin yüzyılı (§20.1.6) saat
değil partinin alındığı gün ile seçilir. `plan_hash` planın kanonik JSON'unun (anahtarlar sıralı,
boşluksuz, UTF-8) SHA-256'sıdır: aynı analiz sonuçlarından iki kez üretilen plan aynı baytları ve
aynı hash'i verir. Planın kendi yan etkisi (açılan çalışan) sonraki bir planlamanın girdisini
değiştirir; bu yüzden mevcut plan yeniden üretilmez, yeniden çalıştırılır (06.6.1). Aynı partinin
yeni planı bir sonraki sürüm numarasını alır (K18, 06.6.2).
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import Catalog
from app.db.models import Plan, Upload
from app.events import EventType, event_context, record_event
from app.pipeline.group import group_upload
from app.storage import DataLayout

from .plan_models import PlanDocument
from .plan_planner import _Planner


def create_plan(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    *,
    catalog: Catalog,
    model: str | None = None,
    reference_date: date | None = None,
) -> Plan:
    """Partinin planını üretir, `plans` tablosuna dondurur ve `PLAN_CREATED` yazar (06.1.1).

    Kurallar modül açıklamasındadır. `catalog` güncel katalogdur (`export_catalog(session)`).
    `model` analizi yapan yapay zekâ modelidir (§8.5 `model`); plan üretimi yapay zekâ çağırmaz.
    `reference_date` MRZ doğum tarihinin yüzyılını seçer (§20.1.6); verilmezse partinin alındığı
    gündür (`uploads.created_at`, UTC) — saat plana girmez. Sürüm partinin son planının bir
    fazlasıdır (ilk plan 1). Olaylar (gruplama, eşleştirme, çalışan açma, `PLAN_CREATED`) partinin
    bağlamında yazılır; olay verisi kişisel değer taşımaz. Oturum commit edilmez.
    """
    session.flush()
    latest = session.scalar(select(func.max(Plan.version)).where(Plan.upload_id == upload.id))
    version = (latest or 0) + 1
    grouping = group_upload(session, upload, catalog=catalog, layout=layout)
    planner = _Planner(
        session,
        layout,
        upload,
        grouping,
        catalog=catalog,
        today=reference_date if reference_date is not None else upload.created_at.date(),
    )
    with event_context(upload_id=upload.id):
        document = PlanDocument(
            upload_id=upload.id, version=version, model=model, items=planner.items()
        )
        row = Plan(
            upload_id=upload.id,
            version=version,
            json=document.model_dump(mode="json"),
            model=model,
            plan_hash=document.plan_hash,
        )
        session.add(row)
        session.flush()
        routes = Counter(item.route.value for item in document.items)
        record_event(
            session,
            EventType.PLAN_CREATED,
            data={
                "plan_id": row.id,
                "version": version,
                "plan_hash": row.plan_hash,
                "model": model,
                "items": len(document.items),
                "routes": dict(sorted(routes.items())),
            },
        )
    return row
