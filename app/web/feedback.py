"""İşlem sonrası geçici bildirim (PRD 10.11.1, 10.11.3; PLAN.md §D120).

Bir yazma işlemi sonuçlanınca kullanıcıya kısa, tek kullanımlık bir bildirim gösterilir. Bildirimin
metni bu modüldeki merkezi kayıttadır (`REGISTRY`): her kayıt bir anahtar, bir tür
(`FeedbackKind`) ve `N_()` ile işaretli, `{ad}` yer tutuculu Türkçe msgid taşır. Metin gösterildiği
isteğin dilinde biçimlenir (10.11.3); taşıyıcıda metin değil anahtar durur.

İki taşıyıcı (§D120 a):

- Tam sayfa yönlendirmesi (`POST` → 303 → `GET`): `flash(response, key, **params)` tek kullanımlık
  `documania_flash` çerezini yazar (HttpOnly, SameSite=Lax, Path=/, 60 sn). Çerezi bir sonraki
  sayfa çizimi okur ve aynı yanıtta siler (`pop_flash`; `app.web.templating.render_page`). Ara
  yönlendirme, dosya yanıtı ve HTMX parçası çizmediği için çerezi tüketmez.
- HTMX isteği: `hx_flash(response, key, **params)` bildirimi `HX-Trigger` başlığıyla
  (`documania:toast`) gönderir, çerez yazılmaz. İstemci betiği (`static/toast.js`) iki yolu aynı
  görünüme bağlar.

Parametreler yalnız kişisel olmayan değerlerdir (`PARAMETERS`): tam sayı, E numarası, parti kimliği,
tür slug'ı ve profil alanı **adları** (§8.7 `source`, virgülle; gösterimde isteğin diline
çevrilir, `app.output_templates.labels`). Ad-soyad, belge numarası, doğum tarihi parametre olamaz;
kayıt kurulurken her yer tutucunun izinli adlardan biri olduğu denetlenir. Çerezden okunan
bilinmeyen anahtar ya da izinsiz parametre sessizce yok sayılır: imza gerekmez, kullanıcı ancak
kendine sahte bir bildirim gösterebilir.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import string
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Any

from fastapi import Request, Response

from app.i18n import N_, gettext
from app.output_templates.labels import FIELD_LABELS, UNASSIGNED

FLASH_COOKIE = "documania_flash"
FLASH_MAX_AGE = 60
TOAST_EVENT = "documania:toast"
# Bir yanıtta en çok bu kadar bildirim taşınır (görünüm de en çok üçünü üst üste gösterir).
MAX_TOASTS = 3


class FeedbackKind(StrEnum):
    """Bildirimin türü: renk, simge ve kapanma davranışı buna göre (10.11.1)."""

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def role(self) -> str:
        """Ekran okuyucu rolü: başarı/bilgi `status`, uyarı/hata `alert`."""
        return "status" if self in (FeedbackKind.SUCCESS, FeedbackKind.INFO) else "alert"

    @property
    def persistent(self) -> bool:
        """Uyarı ve hata kullanıcı kapatana dek kalır; başarı ve bilgi kendiliğinden kapanır."""
        return self in (FeedbackKind.WARNING, FeedbackKind.ERROR)


class ParamKind(Enum):
    INT = "int"
    EMPLOYEE_ID = "employee_id"
    UPLOAD_ID = "upload_id"
    SLUG = "slug"
    FIELDS = "fields"


_EMPLOYEE_ID = re.compile(r"E[0-9]{4,12}")
_UPLOAD_ID = re.compile(r"u_[0-9]{8}_[0-9]{1,9}")
_SLUG = re.compile(r"[a-z][a-z0-9_]{0,63}")
_MAX_INT = 10**9

# İzinli parametre adları ve tipleri. Bir bildirim şablonundaki her yer tutucu buradan biridir;
# kişisel değer taşıyan ad (ad-soyad, belge numarası, doğum tarihi) bu listeye girmez.
PARAMETERS: dict[str, ParamKind] = {
    "count": ParamKind.INT,
    "skipped": ParamKind.INT,
    "version": ParamKind.INT,
    "previous": ParamKind.INT,
    "employee_id": ParamKind.EMPLOYEE_ID,
    "upload_id": ParamKind.UPLOAD_ID,
    "slug": ParamKind.SLUG,
    # 15.2.1: eksik ve taşan alanların adları (değer değil); gösterimde çevrilir.
    "fields": ParamKind.FIELDS,
    "overflow": ParamKind.FIELDS,
}


def _valid(kind: ParamKind, value: object) -> bool:
    if kind is ParamKind.INT:
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_INT
    if not isinstance(value, str):
        return False
    if kind is ParamKind.FIELDS:
        names = value.split(",")
        return all(name in FIELD_LABELS and name != UNASSIGNED for name in names)
    pattern = {
        ParamKind.EMPLOYEE_ID: _EMPLOYEE_ID,
        ParamKind.UPLOAD_ID: _UPLOAD_ID,
        ParamKind.SLUG: _SLUG,
    }[kind]
    return pattern.fullmatch(value) is not None


def placeholders(template: str) -> frozenset[str]:
    """Şablondaki `{ad}` yer tutucuları."""
    return frozenset(name for _, name, _, _ in string.Formatter().parse(template) if name)


@dataclass(frozen=True, slots=True)
class Feedback:
    """Merkezi kayıttaki bildirim: `template` `N_()` ile işaretli Türkçe msgid'dir."""

    key: str
    kind: FeedbackKind
    template: str

    @property
    def params(self) -> frozenset[str]:
        return placeholders(self.template)

    def accepts(self, params: dict[str, object]) -> bool:
        """Parametreler tam olarak şablonun yer tutucularıdır ve her biri izinli tiptedir."""
        return set(params) == self.params and all(
            name in PARAMETERS and _valid(PARAMETERS[name], value) for name, value in params.items()
        )


@dataclass(frozen=True, slots=True)
class Toast:
    """Gösterime hazır bildirim: metin isteğin dilinde biçimlenmiştir."""

    kind: FeedbackKind
    text: str

    @property
    def role(self) -> str:
        return self.kind.role

    def as_event(self) -> dict[str, str]:
        return {"kind": self.kind.value, "text": self.text}


REGISTRY: dict[str, Feedback] = {}


def _register(key: str, kind: FeedbackKind, template: str) -> str:
    unknown = placeholders(template) - set(PARAMETERS)
    if unknown:
        raise ValueError(f"{key}: izinsiz bildirim parametresi {sorted(unknown)}")
    if key in REGISTRY:
        raise ValueError(f"{key}: bildirim anahtarı iki kez kayıtlı")
    REGISTRY[key] = Feedback(key, kind, template)
    return key


_OK, _INFO, _WARN, _ERR = (
    FeedbackKind.SUCCESS,
    FeedbackKind.INFO,
    FeedbackKind.WARNING,
    FeedbackKind.ERROR,
)

# --- genel: yetki ve hata yolları (10.1.8) -------------------------------------------------------
READ_ONLY = _register(
    "access.read_only", _ERR, N_("Hesabınız salt okunur: bu işlemi yapamazsınız.")
)
NOT_FOUND = _register("write.not_found", _ERR, N_("İşlem yapılamadı: kayıt bulunamadı."))
CONFLICT = _register(
    "write.conflict",
    _WARN,
    N_(
        "İşlem yapılamadı: kayıt bu durumda değiştirilemez ya da bu arada değişti. Ayrıntı sayfada."
    ),
)
INVALID = _register(
    "write.invalid", _WARN, N_("Kaydedilmedi: işaretli alanları düzeltip yeniden gönderin.")
)
TOO_LARGE = _register("write.too_large", _WARN, N_("Gönderilen dosya izin verilen sınırı aşıyor."))
FAILED = _register("write.failed", _ERR, N_("İşlem tamamlanamadı. Ayrıntı sayfada."))

# --- Belge Türleri (11.1) ------------------------------------------------------------------------
TYPE_CREATED = _register("catalog.created", _OK, N_("Tür oluşturuldu: {slug}."))
TYPE_UPDATED = _register(
    "catalog.updated",
    _OK,
    N_("Tür güncellendi: {slug}. Değişiklik bir sonraki analizden itibaren geçerlidir."),
)
TYPE_DEACTIVATED = _register(
    "catalog.deactivated", _OK, N_("Tür pasifleştirildi: {slug}. Yeni belgelere atanmaz.")
)
TYPE_ACTIVATED = _register("catalog.activated", _OK, N_("Tür yeniden etkinleştirildi: {slug}."))
TYPE_ARCHIVED = _register(
    "catalog.archived",
    _OK,
    N_(
        "Tür arşivlendi: {slug}. Listeden, analiz talimatından ve tür seçicilerden kalktı; var "
        "olan belgeleri yerinde."
    ),
)
TYPE_RESTORED = _register(
    "catalog.restored",
    _OK,
    N_("Tür arşivden geri alındı: {slug}. Bir sonraki analizden itibaren yeniden geçerlidir."),
)
TYPE_NONE_SELECTED = _register(
    "catalog.none_selected",
    _WARN,
    N_("Tür seçilmedi: önce tablodan en az bir türü işaretleyin."),
)
TYPES_DEACTIVATED = _register(
    "catalog.bulk_deactivated", _OK, N_("Pasifleştirilen tür: {count}. Yeni belgelere atanmazlar.")
)
TYPES_ACTIVATED = _register(
    "catalog.bulk_activated", _OK, N_("Yeniden etkinleştirilen tür: {count}.")
)
TYPES_ARCHIVED = _register("catalog.bulk_archived", _OK, N_("Arşivlenen tür: {count}."))
TYPES_ARCHIVED_SKIPPED = _register(
    "catalog.bulk_archived_skipped",
    _OK,
    N_("Arşivlenen tür: {count}; atlanan korunan tür: {skipped}."),
)
PHOTO_RULES_SAVED = _register(
    "catalog.photo_rules", _OK, N_("Fotoğraf kuralları kaydedildi: {slug}.")
)
EXAMPLES_STORED = _register(
    "catalog.examples_stored",
    _OK,
    N_("Yüklenen örnek: {count}; zaten kayıtlı olduğu için atlanan: {skipped}."),
)
# 10.11.2: onay ve ret bağlı bekleyen Unknown öğelerini çözmez (`app.catalog.candidates`); bildirim
# kaç öğenin beklediğini ve sonraki adımı söyler (PLAN.md §D120 d).
CANDIDATE_APPROVED = _register(
    "catalog.candidate_approved",
    _OK,
    N_(
        "Aday tür standart türler arasına eklendi: {slug}. Bağlı bekleyen Unknown öğesi: {count}; "
        "öğeler kendiliğinden çözülmez — aşağıdan partilerini yeniden analiz edin."
    ),
)
CANDIDATE_APPROVED_ALONE = _register(
    "catalog.candidate_approved_alone",
    _OK,
    N_(
        "Aday tür standart türler arasına eklendi: {slug}. Bağlı bekleyen Unknown öğesi yok; tür "
        "bir sonraki analizden itibaren geçerlidir."
    ),
)
CANDIDATE_REJECTED = _register(
    "catalog.candidate_rejected",
    _OK,
    N_(
        "Aday tür reddedildi; bir daha listeye düşmez. Bağlı bekleyen Unknown öğesi: {count}; "
        "öğeler kendiliğinden kapanmaz — Kuyruklar'dan açıp kapatın."
    ),
)
CANDIDATE_REJECTED_ALONE = _register(
    "catalog.candidate_rejected_alone", _OK, N_("Aday tür reddedildi; bir daha listeye düşmez.")
)
CANDIDATE_RESTORED = _register(
    "catalog.candidate_restored", _OK, N_("Aday tür retten geri alındı; yeniden onay bekliyor.")
)
CANDIDATE_EXAMINED = _register("catalog.candidate_examined", _OK, N_("Aday yeniden incelendi."))
CANDIDATE_REANALYZED = _register(
    "catalog.candidate_reanalyzed", _OK, N_("Yeniden analiz edilen parti: {count}.")
)

# --- Belge Grupları (06.3) -----------------------------------------------------------------------
GROUP_CREATED = _register("groups.created", _OK, N_("Grup oluşturuldu. Şimdi kalemlerini ekleyin."))
GROUP_UPDATED = _register("groups.updated", _OK, N_("Grubun adı ve açıklaması güncellendi."))
GROUP_UNCHANGED = _register("groups.unchanged", _INFO, N_("Değişiklik yok."))
GROUP_ITEM_ADDED = _register("groups.item_added", _OK, N_("Kalem eklendi."))
GROUP_ITEM_REMOVED = _register("groups.item_removed", _OK, N_("Kalem kaldırıldı."))
GROUP_ARCHIVED = _register(
    "groups.archived", _OK, N_("Grup arşivlendi: yeni paket tanımlanamaz, açık paketler sürer.")
)
GROUP_RESTORED = _register("groups.restored", _OK, N_("Grup arşivden geri alındı."))

# --- Hazır Şablonlar (15.1.1, 15.1.2, 15.1.4) ---------------------------------------------------
TEMPLATE_UPLOADED = _register(
    "templates.uploaded",
    _OK,
    N_("Şablon yüklendi ({count} sayfa). Taslak olarak listede; alan haritası incelemeyle gelir."),
)
TEMPLATE_UPLOADED_UNEXAMINED = _register(
    "templates.uploaded_unexamined",
    _WARN,
    N_(
        "Şablon yüklendi ({count} sayfa), ancak yapay zekâ ayarlı olmadığı için incelenmedi; "
        "ayar yapılınca şablon sayfasından yeniden inceleyin."
    ),
)
TEMPLATE_EXAMINE_REQUESTED = _register(
    "templates.examine_requested",
    _OK,
    N_("İnceleme sıraya alındı; alan haritası hazır olunca yeni sürüm olarak görünür."),
)
TEMPLATE_EXAMINE_UNAVAILABLE = _register(
    "templates.examine_unavailable",
    _WARN,
    N_("Yapay zekâ ayarlı olmadığı için şablon incelenemedi."),
)
TEMPLATE_DUPLICATE = _register(
    "templates.duplicate",
    _WARN,
    N_("Bu dosya zaten bir şablon; aynı dosya ikinci kez yüklenmez."),
)
TEMPLATE_ARCHIVED = _register(
    "templates.archived",
    _OK,
    N_("Şablon arşivlendi: profilde seçilemez, üretilmiş belgeler yerinde kalır."),
)
TEMPLATE_RESTORED = _register("templates.restored", _OK, N_("Şablon arşivden geri alındı."))
# 15.1.3: alan haritası onayı.
TEMPLATE_MAP_APPROVED = _register(
    "templates.map_approved",
    _OK,
    N_("Alan haritası onaylandı (sürüm {version}); şablon hazır."),
)
TEMPLATE_MAP_APPROVED_EDITED = _register(
    "templates.map_approved_edited",
    _OK,
    N_(
        "Değişen {count} atama yeni sürüm olarak kaydedildi ve onaylandı (sürüm {version}); "
        "şablon hazır."
    ),
)
TEMPLATE_MAP_UNCHANGED = _register(
    "templates.map_unchanged", _INFO, N_("Bu sürüm zaten onaylı; değişiklik yok.")
)
TEMPLATE_MAP_NOTHING_BOUND = _register(
    "templates.map_nothing_bound",
    _ERR,
    N_("Harita onaylanmadı: en az bir kutu bir profil alanına bağlı olmalı."),
)
# 15.2.1: çıktıya hazırla. Eksik (profilde boş) ve taşan (kutuya sığmayıp kesilmeden yazılan)
# alanlar adlarıyla söylenir; değer yazılmaz.
OUTPUT_GENERATED = _register(
    "employees.output_generated", _OK, N_("Çıktı hazırlandı; {count} alan profilden dolduruldu.")
)
OUTPUT_GENERATED_MISSING = _register(
    "employees.output_generated_missing",
    _WARN,
    N_("Çıktı hazırlandı; profilde boş olan alanlar boş bırakıldı — eksik: {fields}."),
)
OUTPUT_GENERATED_OVERFLOW = _register(
    "employees.output_generated_overflow",
    _WARN,
    N_("Çıktı hazırlandı; kutusuna sığmayan alanlar kesilmeden yazıldı — taşan: {overflow}."),
)
OUTPUT_GENERATED_MISSING_OVERFLOW = _register(
    "employees.output_generated_missing_overflow",
    _WARN,
    N_(
        "Çıktı hazırlandı; profilde boş olan alanlar boş bırakıldı — eksik: {fields}. Kutusuna "
        "sığmayan alanlar kesilmeden yazıldı — taşan: {overflow}."
    ),
)
# 15.2.2: üretilen belgeyi arşivleme ve geri alma (tek adım).
OUTPUT_ARCHIVED = _register(
    "employees.output_archived",
    _OK,
    N_("Üretilen belge arşivlendi; dosya yerinde kalır, arşivdekiler bölümünden geri alınır."),
)
OUTPUT_RESTORED = _register(
    "employees.output_restored", _OK, N_("Üretilen belge arşivden geri alındı.")
)

# --- Çalışanlar (10.5) ---------------------------------------------------------------------------
PACKAGE_ASSIGNED = _register("employees.package_assigned", _OK, N_("Paket tanımlandı."))
PACKAGE_CANCELLED = _register("employees.package_cancelled", _OK, N_("Paket iptal edildi."))
PACKAGE_REOPENED = _register("employees.package_reopened", _OK, N_("Paket yeniden açıldı."))
FIELDS_CHANGED = _register("employees.fields_changed", _OK, N_("Profil bilgileri değiştirildi."))
FIELDS_RENAMED = _register(
    "employees.fields_renamed",
    _OK,
    N_("Profil bilgileri değiştirildi; klasör ve belge dosyaları yeni adla yeniden adlandırıldı."),
)
STATUS_INACTIVE = _register(
    "employees.status_inactive",
    _OK,
    N_("Çalışan pasife alındı; yeni belgeleri otomatik yerleşmeyecek."),
)
STATUS_ACTIVE = _register("employees.status_active", _OK, N_("Çalışan yeniden etkinleştirildi."))
MERGED = _register(
    "employees.merged",
    _OK,
    N_(
        "Kayıtlar birleştirildi; birleşen kaydın belgeleri, numaraları, isim yazımları, "
        "iletişim bilgileri ve belge paketleri bu profile taşındı."
    ),
)
RECORD_REMOVED = _register(
    "employees.record_removed",
    _OK,
    N_("Kayıt kaldırıldı; eşleştirmede ve aramada kullanılmayacak."),
)
RECORD_RESTORED = _register(
    "employees.record_restored",
    _OK,
    N_("Kayıt geri alındı; yeniden eşleştirmede ve aramada kullanılacak."),
)
CONTACT_ADDED = _register("employees.contact_added", _OK, N_("İletişim bilgisi eklendi."))
DOCUMENT_ARCHIVED = _register(
    "employees.document_archived",
    _OK,
    N_("Belge arşive taşındı; çalışanın Hazır klasöründen çıktı."),
)
DOCUMENT_UNARCHIVED = _register(
    "employees.document_unarchived",
    _OK,
    N_("Belge arşivden geri alındı; çalışanın Hazır klasörüne döndü."),
)
DOCUMENT_DELETED = _register(
    "employees.document_deleted",
    _OK,
    N_("Belge kalıcı olarak silindi; dosyaları diskten kaldırıldı."),
)
DOCUMENT_DELETED_PARTIAL = _register(
    "employees.document_deleted_partial",
    _WARN,
    N_(
        "Belge kalıcı olarak silindi, ancak bazı dosyaları diskten kaldırılamadı (açık ya da "
        "kilitli olabilir); sayısı olay logunda. Sistem yöneticisine bildirin."
    ),
)
DOCUMENT_MOVED = _register(
    "employees.document_moved", _OK, N_("Belge {employee_id} çalışanına taşındı.")
)
EMPLOYEE_DELETED = _register(
    "employees.deleted",
    _OK,
    N_("Çalışan kalıcı olarak silindi; klasörü ve belgeleri diskten kaldırıldı."),
)
EMPLOYEE_DELETED_PARTIAL = _register(
    "employees.deleted_partial",
    _WARN,
    N_(
        "Çalışan kalıcı olarak silindi, ancak bazı dosyaları diskten kaldırılamadı (açık ya da "
        "kilitli olabilir); sayısı olay logunda. Sistem yöneticisine bildirin."
    ),
)

# --- Kuyruklar (10.7) ----------------------------------------------------------------------------
QUEUE_CLOSED = _register(
    "queue.closed",
    _OK,
    N_("Öğe kapatıldı; kuyruk klasöründeki kopya ve gerekçe dosyası yerinde kaldı."),
)
QUEUE_REOPENED = _register("queue.reopened", _OK, N_("Öğe yeniden açıldı."))
QUEUE_ASSIGNED = _register("queue.assigned", _OK, N_("Öğe {employee_id} çalışanına atandı."))
QUEUE_PROFILE_CREATED = _register(
    "queue.profile_created",
    _OK,
    N_("Çalışan profili oluşturuldu: {employee_id}. Belge çalışanın Hazır klasörüne yazıldı."),
)

# --- Yükleme ve partiler (10.2, 10.3) ------------------------------------------------------------
UPLOAD_RECEIVED = _register(
    "uploads.received", _OK, N_("Yükleme alındı: {upload_id}. İlerleme aşağıda izlenir.")
)
UPLOAD_RERUN = _register(
    "uploads.rerun", _OK, N_("Plan (sürüm {version}) yeniden uygulandı: {upload_id}.")
)
UPLOAD_REANALYZED = _register(
    "uploads.reanalyzed",
    _OK,
    N_(
        "Parti yeniden analiz edildi: {upload_id}, yeni plan sürümü {version} (önceki: {previous})."
    ),
)
UPLOAD_DISMISSED = _register(
    "uploads.dismissed", _OK, N_("Tarama yoksayıldı: {upload_id}. Kapanan kuyruk öğesi: {count}.")
)
UPLOAD_UNDISMISSED = _register(
    "uploads.undismissed",
    _OK,
    N_("Yoksayma geri alındı: {upload_id}. Yeniden açılan kuyruk öğesi: {count}."),
)
UPLOAD_CANCELLED = _register(
    "uploads.cancelled",
    _OK,
    N_("Parti iptal edildi: {upload_id}. Dosyalar ve üretilen belgeler yerinde kaldı."),
)

# --- Eğitim modu (11.9) --------------------------------------------------------------------------
TRAINING_UPLOADED = _register(
    "training.uploaded",
    _OK,
    N_(
        "Yükleme alındı ve mekanik tanıma bitti. Mekanik tanınmayan dosyaları işçi yapay zekâyla "
        "inceler; sonuçlar bu tabloda güncellenir."
    ),
)
TRAINING_PLACED = _register(
    "training.placed",
    _OK,
    N_("Öğe seçilen türe yerleşti; örnek doğrulanmış olarak kaydedildi."),
)
TRAINING_SKIPPED = _register(
    "training.skipped", _INFO, N_("Öğe yerleşmedi: aynı içerik bu türde zaten örnek.")
)
TRAINING_CONFLICT = _register(
    "training.conflict",
    _WARN,
    N_("Öğe yerleşmedi: aynı içerik başka bir türde örnek. Notu inceleyin."),
)
TRAINING_VERIFIED = _register(
    "training.verified",
    _OK,
    N_('Seçilen "AI kararı" örnekleri doğrulandı; elle kontrol ikonu kalktı.'),
)
TRAINING_VERIFY_NONE = _register(
    "training.verify_none",
    _WARN,
    N_('Doğrulanacak "AI kararı" örneği seçilmedi; hiçbir şey değişmedi.'),
)
TRAINING_MOVED = _register(
    "training.moved", _OK, N_("Örnek bu türe taşındı ve doğrulanmış olarak kaydedildi.")
)
TRAINING_REMOVED = _register(
    "training.removed",
    _OK,
    N_("Örnek örneklerden çıkarıldı: dosya silinmedi, eğitim arşivine taşındı."),
)
TRAINING_MAP_STARTED = _register(
    "training.map_started",
    _OK,
    N_(
        "Toplu tarama başladı. İşçi haritadaki dosyaları birer birer tarar; ilerleme bu tabloda "
        "güncellenir."
    ),
)
TRAINING_DISMISSED = _register(
    "training.dismissed",
    _OK,
    N_(
        "Öğe yoksayıldı: listeden kalktı, dosyası yerinde duruyor. Yoksayılanlar görünümünden geri "
        "alabilirsiniz."
    ),
)
TRAINING_RESTORED = _register(
    "training.restored",
    _OK,
    N_('Öğenin yoksayılması geri alındı; öğe "Yerleştirilemedi" listesinde bekliyor.'),
)
TRAINING_RUN_ARCHIVED = _register(
    "training.run_archived",
    _OK,
    N_("Çalıştırma arşivlendi: listeden ve sayaçlardan kalktı; öğeleri ve örnekleri değişmedi."),
)
TRAINING_RUN_RESTORED = _register(
    "training.run_restored", _OK, N_("Çalıştırma arşivden geri alındı.")
)

# --- Kullanıcılar ve Hesabım (10.1.4, 12.1) ------------------------------------------------------
USER_CREATED = _register("users.created", _OK, N_("Kullanıcı oluşturuldu."))
USER_PASSWORD_RESET = _register(
    "users.password_reset", _OK, N_("Parola sıfırlandı; kullanıcının açık oturumları kapatıldı.")
)
USER_DEACTIVATED = _register(
    "users.deactivated", _OK, N_("Kullanıcı pasife alındı; açık oturumları kapatıldı.")
)
USER_REACTIVATED = _register("users.reactivated", _OK, N_("Kullanıcı yeniden etkinleştirildi."))
USER_ROLE_CHANGED = _register(
    "users.role_changed", _OK, N_("Kullanıcının rolü değişti; bir sonraki isteğinde geçerli olur.")
)
OWN_PASSWORD = _register(
    "users.own_password", _OK, N_("Parolanız değiştirildi; diğer oturumlarınız kapatıldı.")
)
TELEGRAM_ADDED = _register(
    "users.telegram_added", _OK, N_("Telegram kimliği eklendi ve izni açıldı.")
)
TELEGRAM_ALLOWED = _register("users.telegram_allowed", _OK, N_("Telegram kimliğinin izni açıldı."))
TELEGRAM_BLOCKED = _register(
    "users.telegram_blocked",
    _OK,
    N_("Telegram kimliğinin izni kapatıldı; bot bu kimliğe yanıt vermeyecek."),
)
TELEGRAM_REMOVED = _register(
    "users.telegram_removed",
    _OK,
    N_("Telegram kaydı silindi. Bu numara artık yeniden bağlanabilir; bot ona yanıt vermeyecek."),
)
TELEGRAM_LINK_CREATED = _register(
    "users.telegram_link", _OK, N_("Bağlantı kodu oluşturuldu; ekrandaki adımları izleyin.")
)

# --- Yapay zekâ ayarları (10.1.10; yalnız root görür, PLAN.md §D124 e) --------------------------
AI_SETTINGS_SAVED = _register(
    "ai_settings.saved",
    _OK,
    N_("Yapay zekâ ayarı kaydedildi; bir sonraki yapay zekâ çağrısında geçerli olur."),
)
AI_SETTINGS_UNCHANGED = _register(
    "ai_settings.unchanged", _INFO, N_("Değişiklik yok; ayar olduğu gibi kaldı.")
)


# --- Yol gösterme ipuçları (10.11.2; PLAN.md §D120 d) --------------------------------------------
# Bekleyen bir kararın yanında duran tek cümlelik "ne yapmalı" metni. Bildirim değildir (taşıyıcısı
# yok, sayfada çizilir), ama bildirimler gibi bu kayıttan gelir ve isteğin dilinde gösterilir.
# Yazma yetkisi gerektiren adım salt okunur Kullanıcı'ya gösterilmez; o, `reader` ipucunu görür
# (10.1.8). Hiçbir ipucu belge içeriğini değiştiren bir yol önermez (R12, K17).

HINTS: dict[str, str] = {}


def _hint(key: str, template: str) -> str:
    if placeholders(template):
        raise ValueError(f"{key}: ipucu yer tutucu taşımaz")
    if key in HINTS:
        raise ValueError(f"{key}: ipucu anahtarı iki kez kayıtlı")
    HINTS[key] = template
    return key


# Parti detayındaki "Kuyruğa alınanlar" tablosunun "Çözüm" sütunu: bekleyen öğede yapılacak iş.
RESOLVE_UNKNOWN_CANDIDATE = _hint(
    "resolve.unknown_candidate", N_("Aday türü onaylayın ya da öğeyi kapatın.")
)
RESOLVE_UNKNOWN_APPROVED = _hint(
    "resolve.unknown_approved",
    N_("Aday tür onaylandı: partiyi yeniden analiz edin ya da öğeyi kapatın."),
)
RESOLVE_UNKNOWN = _hint(
    "resolve.unknown",
    N_("Türü kataloğa ekleyip partiyi yeniden analiz edin ya da öğeyi kapatın."),
)
RESOLVE_UNREADABLE = _hint(
    "resolve.unreadable",
    N_("Daha net bir kopyayı yeniden yükleyin, öğeyi çalışana atayın ya da kapatın."),
)
RESOLVE_UNRESOLVED_PROFILE = _hint(
    "resolve.unresolved_profile",
    N_("Önerilen profili onaylayın, öğeyi çalışana atayın ya da kapatın."),
)
RESOLVE_UNRESOLVED = _hint("resolve.unresolved", N_("Çalışana atayın ya da öğeyi kapatın."))
RESOLVE_UNRESOLVED_TYPELESS = _hint(
    "resolve.unresolved_typeless",
    N_("Belgeyi uygun biçimde yeniden yükleyin ya da öğeyi kapatın."),
)
RESOLVE_READER = _hint(
    "resolve.reader", N_("İK'nın kararını bekliyor; bir sorun görürseniz İK'ya bildirin.")
)
RESOLVE_SUPERSEDED = _hint("resolve.superseded", N_("Eski sürüm: işlem gerekmez."))

# Kuyruk öğesi sayfasının "Önerilen adımlar" kutusu: kuyruk türüne göre sıralı adımlar.
STEP_CANDIDATE_APPROVE = _hint(
    "step.candidate_approve", N_("Önerilen aday türü inceleyip onaylayın.")
)
STEP_CANDIDATE_REANALYZE = _hint(
    "step.candidate_reanalyze",
    N_("Onaydan sonra aday türün sayfasından bu partiyi yeniden analiz edin."),
)
STEP_CANDIDATE_APPROVED = _hint(
    "step.candidate_approved",
    N_("Aday tür onaylandı: aday türün sayfasından bu partiyi yeniden analiz edin."),
)
STEP_TYPE_ADD = _hint(
    "step.type_add", N_("Tür katalogda yoksa Belge Türleri'nden yeni tür olarak ekleyin.")
)
STEP_UPLOAD_REANALYZE = _hint(
    "step.upload_reanalyze", N_("Ardından parti sayfasından partiyi yeniden analiz edin.")
)
STEP_SOURCES = _hint("step.sources", N_("Gerekçede okunamayan alan yazar; kaynak sayfalara bakın."))
STEP_PROFILE = _hint("step.profile", N_("Önerilen profili gözden geçirip onaylayın."))
STEP_ASSIGN = _hint("step.assign", N_("Belgenin sahibi kayıtlı bir çalışansa ona atayın."))
STEP_REUPLOAD = _hint(
    "step.reupload", N_("Daha net ya da uygun biçimde bir kopya gerekiyorsa yeniden yükleyin.")
)
STEP_CLOSE = _hint(
    "step.close", N_("Belge değilse ya da sistemde zaten varsa öğeyi gerekçeyle kapatın.")
)
STEP_READER = _hint(
    "step.reader",
    N_(
        "Bu öğe İK'nın kararını bekliyor. Hesabınız salt okunur; bir sorun görürseniz İK'ya "
        "bildirin."
    ),
)

# Kuyruklar listesinde her sekmenin başındaki tek cümle.
TAB_UNKNOWN = _hint(
    "tab.unknown",
    N_(
        "Türü katalogda olmayan belgeler: öğeyi açıp önerilen aday türü onaylayın ya da belge "
        "değilse kapatın."
    ),
)
TAB_UNREADABLE = _hint(
    "tab.unreadable",
    N_(
        "Zorunlu alanı okunamayan belgeler: öğeyi açıp çalışana atayın ya da daha net kopya "
        "yüklendiyse kapatın."
    ),
)
TAB_UNRESOLVED = _hint(
    "tab.unresolved",
    N_(
        "Sahibi belirlenemeyen belgeler: öğeyi açıp çalışana atayın, önerilen profili onaylayın "
        "ya da kapatın."
    ),
)
TAB_UNKNOWN_READER = _hint(
    "tab.unknown_reader",
    N_(
        "Türü katalogda olmayan belgeler İK'nın kararını bekler; bir sorun görürseniz İK'ya "
        "bildirin."
    ),
)
TAB_UNREADABLE_READER = _hint(
    "tab.unreadable_reader",
    N_(
        "Zorunlu alanı okunamayan belgeler İK'nın kararını bekler; bir sorun görürseniz İK'ya "
        "bildirin."
    ),
)
TAB_UNRESOLVED_READER = _hint(
    "tab.unresolved_reader",
    N_(
        "Sahibi belirlenemeyen belgeler İK'nın kararını bekler; bir sorun görürseniz İK'ya "
        "bildirin."
    ),
)


# Bir POST isteği hata koduyla sayfa çizdiğinde (`render_page`) kendiliğinden verilen özet
# bildirim; form alanı hataları sayfada yerinde kalır (10.11.1).
STATUS_FEEDBACK: dict[int, str] = {
    400: INVALID,
    403: READ_ONLY,
    404: NOT_FOUND,
    409: CONFLICT,
    413: TOO_LARGE,
    422: INVALID,
}


def status_feedback(status_code: int) -> str | None:
    """Hata kodunun özet bildirim anahtarı; 2xx/3xx ve oturumsuzluk (401: giriş formu kendi
    hatasını gösterir) için `None`."""
    if status_code < 400 or status_code == 401:
        return None
    return STATUS_FEEDBACK.get(status_code, FAILED)


def _feedback(key: str, params: dict[str, object]) -> Feedback:
    feedback = REGISTRY.get(key)
    if feedback is None:
        raise ValueError(f"kayıtlı olmayan bildirim anahtarı: {key!r}")
    if not feedback.accepts(params):
        raise ValueError(f"{key}: bildirim parametreleri geçersiz: {sorted(params)}")
    return feedback


def _shown(params: dict[str, Any]) -> dict[str, Any]:
    """Parametrelerin gösterim değeri: alan adı listesi isteğin dilinde etiketlere çevrilir."""
    return {
        name: ", ".join(gettext(FIELD_LABELS[field]) for field in value.split(","))
        if PARAMETERS.get(name) is ParamKind.FIELDS
        else value
        for name, value in params.items()
    }


def render(key: str, **params: object) -> Toast:
    """Bildirimi bu isteğin dilinde biçimler (10.11.3); bilinmeyen anahtar ya da geçersiz
    parametre programlama hatasıdır."""
    feedback = _feedback(key, params)
    return Toast(feedback.kind, gettext(feedback.template).format(**_shown(params)))


def _encode(items: list[dict[str, Any]]) -> str:
    raw = json.dumps(items, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(value: str) -> list[dict[str, Any]]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        items = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return []
    return items if isinstance(items, list) else []


def flash(response: Response, key: str, **params: object) -> None:
    """Tam sayfa yönlendirmesinin bildirimi: tek kullanımlık çerez yalnız anahtarı ve kişisel
    olmayan parametreleri taşır. Bir sonraki sayfa çizimi gösterir ve siler."""
    _feedback(key, params)
    response.set_cookie(
        FLASH_COOKIE,
        _encode([{"k": key, "p": params}]),
        max_age=FLASH_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
    )


def hx_flash(response: Response, key: str, **params: object) -> None:
    """HTMX isteğinin bildirimi: `HX-Trigger` başlığıyla (`documania:toast`), çerez yazılmaz."""
    add_toasts(response, [render(key, **params)])


def add_toasts(response: Response, toasts: list[Toast]) -> None:
    """Hazır bildirimleri `HX-Trigger` başlığına ekler (varsa öncekilerin ardına)."""
    if not toasts:
        return
    triggers: dict[str, Any] = {}
    existing = response.headers.get("HX-Trigger")
    if existing:
        try:
            parsed = json.loads(existing)
        except ValueError:
            parsed = {existing: None}
        if isinstance(parsed, dict):
            triggers = parsed
    previous = triggers.get(TOAST_EVENT, {}).get("toasts", []) if triggers.get(TOAST_EVENT) else []
    items = [*previous, *(toast.as_event() for toast in toasts)][:MAX_TOASTS]
    triggers[TOAST_EVENT] = {"toasts": items}
    # Başlık ASCII taşır; Türkçe ve Sırpça harfler JSON kaçışıyla gider, istemci çözer.
    response.headers["HX-Trigger"] = json.dumps(triggers, ensure_ascii=True)


def read_flash(request: Request) -> list[Toast]:
    """Çerezdeki bildirimleri bu isteğin dilinde biçimler; bilinmeyen anahtar, izinsiz ya da
    eksik parametre yok sayılır."""
    value = request.cookies.get(FLASH_COOKIE)
    if not value:
        return []
    toasts: list[Toast] = []
    for item in _decode(value)[:MAX_TOASTS]:
        if not isinstance(item, dict):
            continue
        key, params = item.get("k"), item.get("p", {})
        feedback = REGISTRY.get(key) if isinstance(key, str) else None
        if feedback is None or not isinstance(params, dict) or not feedback.accepts(params):
            continue
        toasts.append(Toast(feedback.kind, gettext(feedback.template).format(**_shown(params))))
    return toasts


def clear_flash(response: Response) -> None:
    response.delete_cookie(FLASH_COOKIE, path="/", httponly=True, samesite="lax")


def pop_flash(request: Request, response: Response) -> list[Toast]:
    """Çerezdeki bildirimleri okur ve aynı yanıtta siler (tek kullanımlık)."""
    if FLASH_COOKIE not in request.cookies:
        return []
    toasts = read_flash(request)
    clear_flash(response)
    return toasts


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"
