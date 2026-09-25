"""13.5.1 — üretim dağıtımı: alan adı ve HTTPS ile tek komut.

Dağıtım `docker-compose.yml`'in `production` profili + `Caddyfile` ile tarif edilir. Burada dosyalar
gerçekten okunur ve sözleşmeleri sınanır: dışarıya yalnız Caddy'nin 80/443'ü açılır, uygulama ve
veritabanı yalnız yerel arayüze yayınlanır, şema göçü uygulamadan önce çalışır, alan adı ve
parolalar koda yazılmaz, ayar denetimi (`preflight`) hatalı ayarda durur. Docker kuruluysa
`docker compose config` (ve yerel Caddy görüntüsü varsa `caddy validate`) da koşar. Ağ, Docker
daemon'u ve gerçek alan adı gerekmez.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.config import Settings
from tests.scripts.conftest import _bash_candidates, _usable

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
CADDYFILE = ROOT / "Caddyfile"

PRODUCTION_ENV = {
    "DOMAIN": "belge.example.com",
    "ACME_EMAIL": "ik@example.com",
    "POSTGRES_PASSWORD": "abc123def456",
    "APP_ENV": "production",
    "APP_DATABASE_URL": "postgresql+psycopg://belgeee:abc123def456@db:5432/belgeee",
}


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def services(compose: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return compose["services"]


@pytest.fixture(scope="module")
def caddyfile() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


def _published(service: dict[str, Any]) -> list[str]:
    return [str(port) for port in service.get("ports", [])]


def _env(service: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in service.get("environment", {}).items()}


# --- profiller: geliştirme akışı bozulmaz, üretim ayrı profildir ---------------------------------


def test_production_services_sit_behind_the_production_profile(
    services: dict[str, dict[str, Any]],
) -> None:
    production = {
        name for name, service in services.items() if "production" in service.get("profiles", [])
    }

    assert production == {"preflight", "db", "caddy"}


def test_default_development_flow_starts_migrate_app_and_worker(
    services: dict[str, dict[str, Any]],
) -> None:
    # `docker compose up` (profilsiz) HTTPS/PostgreSQL istemez: DOMAIN vb. olmadan da açılır.
    default = {name for name, service in services.items() if not service.get("profiles")}

    assert default == {"migrate", "app", "worker"}


def test_bot_stays_an_optional_telegram_profile_service(
    services: dict[str, dict[str, Any]],
) -> None:
    assert services["bot"]["profiles"] == ["telegram"]


def test_worker_is_a_separate_queue_only_service(
    services: dict[str, dict[str, Any]],
) -> None:
    worker = services["worker"]

    assert worker["command"] == ["python", "-m", "app.worker"]
    assert worker["build"] == services["app"]["build"]
    assert worker["image"] == services["app"]["image"]
    assert worker.get("profiles", []) == []
    assert _published(worker) == []
    assert worker["healthcheck"] == {"disable": True}
    assert worker["restart"] == "unless-stopped"
    assert worker["stop_grace_period"] == "2m"


# --- ağ yüzeyi -----------------------------------------------------------------------------------


def test_only_caddy_publishes_ports_to_the_outside(services: dict[str, dict[str, Any]]) -> None:
    for name, service in services.items():
        for port in _published(service):
            if name == "caddy":
                continue
            assert port.startswith("127.0.0.1:"), f"{name} {port} dışarıya açık"


def test_caddy_publishes_http_https_and_http3(services: dict[str, dict[str, Any]]) -> None:
    assert set(_published(services["caddy"])) == {"80:80", "443:443", "443:443/udp"}


def test_panel_is_never_published_without_https(services: dict[str, dict[str, Any]]) -> None:
    assert _published(services["app"]) == ["127.0.0.1:8000:8000"]


def test_database_is_published_to_loopback_only_for_the_host_backup(
    services: dict[str, dict[str, Any]],
) -> None:
    assert _published(services["db"]) == ["127.0.0.1:5432:5432"]


# --- sıra: ayar denetimi → veritabanı → göç → uygulama → Caddy ----------------------------------


def _depends(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return service.get("depends_on", {})


def test_startup_order_preflight_db_migrate_app_caddy(services: dict[str, dict[str, Any]]) -> None:
    assert _depends(services["db"])["preflight"]["condition"] == "service_completed_successfully"
    migrate = _depends(services["migrate"])
    assert migrate["db"]["condition"] == "service_healthy"
    assert migrate["preflight"]["condition"] == "service_completed_successfully"
    assert _depends(services["app"])["migrate"]["condition"] == "service_completed_successfully"
    assert _depends(services["worker"])["migrate"]["condition"] == "service_completed_successfully"
    assert _depends(services["bot"])["migrate"]["condition"] == "service_completed_successfully"
    caddy = _depends(services["caddy"])
    assert caddy["app"]["condition"] == "service_healthy"
    assert caddy["preflight"]["condition"] == "service_completed_successfully"


def test_production_only_dependencies_are_optional_in_development(
    services: dict[str, dict[str, Any]],
) -> None:
    # Geliştirmede `preflight` ve `db` yoktur; göç adımı onları beklemeye çalışıp düşmemeli.
    migrate = _depends(services["migrate"])

    assert migrate["preflight"]["required"] is False
    assert migrate["db"]["required"] is False


def test_migrate_applies_the_schema_once_and_is_not_restarted(
    services: dict[str, dict[str, Any]],
) -> None:
    migrate = services["migrate"]

    assert migrate["command"] == ["alembic", "upgrade", "head"]
    assert migrate["restart"] == "no"


def test_dockerfile_ships_the_migrations_the_migrate_step_runs() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert re.search(r"^COPY alembic\.ini\b", dockerfile, re.MULTILINE)
    assert re.search(r"^COPY alembic \./alembic$", dockerfile, re.MULTILINE)


# --- veritabanı ve ortak ortam -------------------------------------------------------------------


def test_database_is_postgres_16_with_a_health_check(services: dict[str, dict[str, Any]]) -> None:
    db = services["db"]

    assert db["image"].startswith("postgres:16")
    assert "pg_isready" in " ".join(db["healthcheck"]["test"])
    assert db["restart"] == "unless-stopped"


def test_app_migrate_worker_and_bot_share_one_database_and_data_volume(
    services: dict[str, dict[str, Any]],
) -> None:
    names = ("app", "migrate", "worker", "bot")
    urls = {name: _env(services[name])["DATABASE_URL"] for name in names}

    assert len(set(urls.values())) == 1
    # Varsayılan (geliştirme) SQLite; üretimde `.env`'deki APP_DATABASE_URL.
    assert urls["app"] == "${APP_DATABASE_URL:-sqlite:////srv/data/belgeee.db}"
    for name in names:
        assert "data:/srv/data" in services[name]["volumes"]
        assert _env(services[name])["APP_ENV"] == "${APP_ENV:-development}"


def test_dev_env_file_settings_cannot_leak_a_host_database_path_into_containers(
    services: dict[str, dict[str, Any]],
) -> None:
    # env_file `.env`'i konteynere taşır; geliştirme `.env`'indeki SQLite yolu ve DATA_DIR baskın
    # `environment` değerleriyle ezilmeli.
    for name in ("app", "migrate", "worker", "bot"):
        env = _env(services[name])
        assert "DATABASE_URL" in env
        assert env["DATA_DIR"] == "/srv/data"
        assert services[name]["env_file"] == [{"path": ".env", "required": False}]


def test_no_secret_is_written_into_the_compose_file(services: dict[str, dict[str, Any]]) -> None:
    for name in ("db", "caddy", "preflight"):
        for key, value in _env(services[name]).items():
            if key.endswith(("PASSWORD", "EMAIL", "DOMAIN")) or key == "APP_DATABASE_URL":
                assert value.startswith("${"), f"{name}.{key} sabit değer taşıyor"


def test_bot_webhook_defaults_to_the_domain_and_the_path_caddy_routes(
    services: dict[str, dict[str, Any]], caddyfile: str
) -> None:
    bot = _env(services["bot"])

    assert bot["TELEGRAM_WEBHOOK_URL"].endswith("/telegram/webhook}")
    assert "${DOMAIN:-localhost}" in bot["TELEGRAM_WEBHOOK_URL"]
    assert bot["TELEGRAM_WEBHOOK_LISTEN"] == "0.0.0.0"
    assert (
        int(bot["TELEGRAM_WEBHOOK_PORT"]) == Settings.model_fields["telegram_webhook_port"].default
    )
    assert re.search(r"handle /telegram/\*\s*\{\s*reverse_proxy bot:8443\s*\}", caddyfile)


# --- Caddy: alan adı, HTTPS, vekil ---------------------------------------------------------------


def test_caddy_reads_domain_and_email_from_the_environment(
    services: dict[str, dict[str, Any]], caddyfile: str
) -> None:
    caddy = _env(services["caddy"])

    assert caddy == {"DOMAIN": "${DOMAIN:-}", "ACME_EMAIL": "${ACME_EMAIL:-}"}
    assert re.search(r"^\{\$DOMAIN\} \{$", caddyfile, re.MULTILINE)
    assert "email {$ACME_EMAIL}" in caddyfile


def test_caddyfile_hard_codes_no_domain_and_never_turns_https_off(caddyfile: str) -> None:
    code = "\n".join(line for line in caddyfile.splitlines() if not line.lstrip().startswith("#"))

    assert not re.search(r"\b[a-z0-9-]+\.(com|net|org|io|tr)\b", code)
    assert "auto_https" not in code
    assert "tls internal" not in code
    assert not re.search(r"^\s*http://", code, re.MULTILINE)


def test_caddyfile_proxies_the_panel_and_sets_transport_security_headers(
    services: dict[str, dict[str, Any]], caddyfile: str
) -> None:
    assert re.search(r"handle\s*\{\s*reverse_proxy app:8000\s*\}", caddyfile)
    assert "Strict-Transport-Security" in caddyfile
    assert 'X-Content-Type-Options "nosniff"' in caddyfile
    assert "-Server" in caddyfile
    # Panel çerezi yalnız HTTPS'te gider (10.1.2); vekil uygulamayla aynı portu hedeflemeli.
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8000" in dockerfile
    assert "127.0.0.1:8000:8000" in _published(services["app"])


def test_caddy_mounts_its_config_read_only_and_keeps_certificates_on_a_volume(
    services: dict[str, dict[str, Any]], compose: dict[str, Any]
) -> None:
    volumes = services["caddy"]["volumes"]

    assert "./Caddyfile:/etc/caddy/Caddyfile:ro" in volumes
    assert "caddy_data:/data" in volumes
    assert {"data", "pgdata", "caddy_data", "caddy_config"} <= set(compose["volumes"])


def test_production_cookie_is_secure_only_because_app_env_is_production() -> None:
    # Vekilin arkasında uygulama HTTPS'i bilmez; Secure çerez APP_ENV'e bağlıdır — preflight bunu
    # zorunlu kılar (aşağıda).
    source = (ROOT / "app" / "web" / "auth.py").read_text(encoding="utf-8")

    assert 'secure=settings.app_env == "production"' in source


# --- preflight: eksik ya da tutarsız üretim ayarında dur -----------------------------------------


@pytest.fixture(scope="module")
def bash() -> str:
    for candidate in _bash_candidates():
        if _usable(candidate):
            return candidate
    pytest.skip("GNU tar'lı bir bash bulunamadı (Windows'ta Git for Windows gerekir)")


def _preflight_script(services: dict[str, dict[str, Any]]) -> str:
    entrypoint = services["preflight"]["entrypoint"]
    assert entrypoint[:2] == ["sh", "-c"]
    # Compose'ta `$$` düz `$` olur.
    return entrypoint[2].replace("$$", "$")


def _run_preflight(
    bash: str, script: str, **overrides: str | None
) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in PRODUCTION_ENV}
    env.update({**PRODUCTION_ENV, **{k: v for k, v in overrides.items() if v is not None}})
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
    return subprocess.run(
        [bash, "-c", script], env=env, capture_output=True, text=True, timeout=60, check=False
    )


def test_preflight_passes_with_complete_consistent_production_settings(
    bash: str, services: dict[str, dict[str, Any]]
) -> None:
    result = _run_preflight(bash, _preflight_script(services))

    assert result.returncode == 0, result.stderr
    assert "belge.example.com" in result.stdout


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"DOMAIN": ""}, "DOMAIN"),
        ({"ACME_EMAIL": ""}, "ACME_EMAIL"),
        ({"POSTGRES_PASSWORD": ""}, "POSTGRES_PASSWORD"),
        ({"APP_ENV": "development"}, "APP_ENV=production"),
        ({"APP_ENV": ""}, "APP_ENV=production"),
        ({"APP_DATABASE_URL": ""}, "APP_DATABASE_URL"),
        ({"APP_DATABASE_URL": "sqlite:////srv/data/belgeee.db"}, "APP_DATABASE_URL"),
        (
            {"APP_DATABASE_URL": "postgresql+psycopg://belgeee:baska@db:5432/belgeee"},
            "APP_DATABASE_URL",
        ),
        (
            {"APP_DATABASE_URL": "postgresql+psycopg://belgeee:abc123def456@baska-sunucu:5432/x"},
            "APP_DATABASE_URL",
        ),
    ],
)
def test_preflight_refuses_missing_or_inconsistent_settings_with_a_clear_error(
    bash: str, services: dict[str, dict[str, Any]], overrides: dict[str, str], message: str
) -> None:
    result = _run_preflight(bash, _preflight_script(services), **overrides)

    assert result.returncode != 0
    assert message in result.stderr
    assert ".env.example" in result.stderr
    # Parola hata çıktısına yazılmaz.
    assert PRODUCTION_ENV["POSTGRES_PASSWORD"] not in result.stderr + result.stdout


# --- belgeler ------------------------------------------------------------------------------------


def test_env_example_documents_every_variable_the_compose_file_reads() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example, re.MULTILINE))
    code = [
        line
        for line in COMPOSE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    used = set(re.findall(r"\$\{([A-Z][A-Z0-9_]+)", "\n".join(code)))

    assert used - documented == set()
    assert {"DOMAIN", "ACME_EMAIL", "POSTGRES_PASSWORD", "APP_DATABASE_URL"} <= documented


def test_env_example_keeps_the_production_block_commented_out() -> None:
    # Geliştirici `cp .env.example .env` yapınca üretim ayarları devreye girmemeli.
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for name in ("DOMAIN", "ACME_EMAIL", "POSTGRES_PASSWORD", "APP_DATABASE_URL"):
        assert not re.search(rf"^{name}=", example, re.MULTILINE), name
        assert re.search(rf"^# {name}=", example, re.MULTILINE), name


def test_readme_documents_the_single_command_and_the_production_settings() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Üretim dağıtımı" in readme
    assert "docker compose --profile production up -d --build" in readme
    for name in (
        "DOMAIN",
        "ACME_EMAIL",
        "POSTGRES_PASSWORD",
        "APP_DATABASE_URL",
        "APP_ENV=production",
    ):
        assert name in readme, name
    assert "create-admin" in readme
    assert "-v` vermeyin" in readme


def test_backup_doc_explains_the_compose_deployment() -> None:
    doc = (ROOT / "docs" / "YEDEKLEME.md").read_text(encoding="utf-8")

    assert "Docker Compose üretim dağıtımında" in doc
    assert "127.0.0.1:5432" in doc
    assert "docker volume inspect" in doc


# --- Docker kuruluysa gerçek doğrulayıcılar ------------------------------------------------------


def _docker_compose(*args: str, **env: str) -> subprocess.CompletedProcess[str] | None:
    docker = shutil.which("docker")
    if docker is None:
        return None
    try:
        return subprocess.run(
            [docker, "compose", *args],
            cwd=ROOT,
            env={**{k: v for k, v in os.environ.items() if k not in PRODUCTION_ENV}, **env},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _skip_without_compose(result: subprocess.CompletedProcess[str] | None) -> None:
    if result is None or "is not a docker command" in result.stderr:
        pytest.skip("docker compose kurulu değil")


@pytest.fixture
def empty_env_file(tmp_path: Path) -> str:
    # Makinedeki gerçek `.env` sonucu etkilemesin.
    path = tmp_path / "empty.env"
    path.write_text("", encoding="utf-8")
    return str(path)


def test_docker_compose_config_is_valid_in_development_without_production_settings(
    empty_env_file: str,
) -> None:
    result = _docker_compose("--env-file", empty_env_file, "config", "--services")
    _skip_without_compose(result)

    assert result.returncode == 0, result.stderr
    assert set(result.stdout.split()) == {"migrate", "app", "worker"}


def test_docker_compose_config_is_valid_for_the_production_profile(empty_env_file: str) -> None:
    result = _docker_compose(
        "--env-file",
        empty_env_file,
        "--profile",
        "production",
        "config",
        "--format",
        "json",
        **PRODUCTION_ENV,
    )
    _skip_without_compose(result)

    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert set(config["services"]) == {"preflight", "db", "migrate", "app", "worker", "caddy"}
    assert (
        config["services"]["app"]["environment"]["DATABASE_URL"]
        == PRODUCTION_ENV["APP_DATABASE_URL"]
    )
    assert config["services"]["app"]["environment"]["APP_ENV"] == "production"
    assert config["services"]["caddy"]["environment"]["DOMAIN"] == "belge.example.com"


def test_caddyfile_is_valid_and_formatted_for_the_real_caddy() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker kurulu değil")
    image = "caddy:2-alpine"
    try:
        present = subprocess.run(
            [docker, "image", "inspect", image], capture_output=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("docker kullanılamıyor")
    if present.returncode != 0:
        pytest.skip(f"{image} yerelde yok (test görüntü indirmez)")

    mount = f"{CADDYFILE}:/etc/caddy/Caddyfile:ro"
    validate = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-e",
            "DOMAIN=belge.example.com",
            "-e",
            "ACME_EMAIL=ik@example.com",
            "-v",
            mount,
            image,
            "caddy",
            "validate",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert validate.returncode == 0, validate.stderr
    assert "Valid configuration" in validate.stderr + validate.stdout
