import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

# PRD 10.10.1 (PLAN.md §D92 b): panelin açılış dili İngilizcedir. Testlerin büyük çoğunluğu Türkçe
# arayüz metnini denetler (kaynak dil, msgid'in kendisi); bu yüzden test sürecinde varsayılan dil
# Türkçedir. Dil davranışını sınayan testler ayarı açıkça verir (`tests/i18n`,
# `tests/web/test_interface_language.py`).
os.environ["PANEL_DEFAULT_LANGUAGE"] = "tr"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
