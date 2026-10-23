"""Alan haritasının profil alanı adları (§8.7 `source`; 15.1.3, 15.2.1).

Tek liste buradadır: şablon sayfasının açılır listesi (15.1.3), profilin "Üretilen belgeler"
bölümündeki eksik alanlar ve çıktı bildirimi (15.2.1, 10.11.1) aynı adları gösterir. Adlar `N_()`
ile işaretli Türkçe msgid'dir; gösterimde isteğin diline çevrilir (10.10.3). Sıra açılır listenin
sırasıdır, "boş bırak" (`unassigned`) en sonda.
"""

from __future__ import annotations

from app.i18n import N_

UNASSIGNED = "unassigned"

FIELD_LABELS = {
    "given_names": N_("Ad"),
    "surname": N_("Soyad"),
    "full_name": N_("Ad soyad"),
    "other_names": N_("Diğer isimler"),
    "original_script_name": N_("Orijinal yazım"),
    "date_of_birth": N_("Doğum tarihi"),
    "place_of_birth": N_("Doğum yeri"),
    "mother_name": N_("Anne adı"),
    "father_name": N_("Baba adı"),
    "personal_number": N_("Kişisel numara"),
    "passport_number": N_("Pasaport numarası"),
    "nationality": N_("Vatandaşlık"),
    "address": N_("Adres"),
    "phone": N_("Telefon"),
    "email": N_("E-posta"),
    "today": N_("Bugünün tarihi"),
    UNASSIGNED: N_("Boş bırak"),
}
