import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

# PRD 10.10.1 (PLAN.md §D92 b): panelin açılış dili İngilizcedir. Testlerin büyük çoğunluğu Türkçe
# arayüz metnini denetler (kaynak dil, msgid'in kendisi); bu yüzden test sürecinde varsayılan dil
# Türkçedir. Dil davranışını sınayan testler ayarı açıkça verir (`tests/i18n`,
# `tests/web/test_interface_language.py`).
os.environ["PANEL_DEFAULT_LANGUAGE"] = "tr"

# tm 162 (PLAN.md §D99): test süreci deponun `.env` dosyasını okumaz — yerel makinede de temiz
# ortamdaki (cloud, CI) sonuç alınsın; bir testin ayara ihtiyacı varsa onu açıkça verir. `.env`
# okumayı sınayan testler dosyayı `_env_file=` ile kendileri gösterir.
Settings.model_config["env_file"] = None
get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
