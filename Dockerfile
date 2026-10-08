FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Bağımlılıklar `uv.lock`'taki sürüm ve hash'lerle kurulur: her yapı aynı paketleri alır, PyPI'de
# yeni bir sürüm çıktı diye imaj sessizce değişmez. Kilit pyproject.toml ile uyuşmuyorsa
# (`--locked`) yapı durur; çözüm `uv lock` ve kilidin commit'idir. uv yalnız bu adımda kullanılır,
# imaja girmez. Katman yalnız kilit değişince yeniden kurulur.
RUN --mount=from=ghcr.io/astral-sh/uv:0.12.18,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv export --locked --no-dev --no-emit-project --format requirements-txt -o /tmp/requirements.txt \
    && pip install --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Uygulamanın kendisi; bağımlılıkları yukarıda kilitten kuruldu.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-deps .

# Şema göçleri (13.5.1): uygulama şemayı kendisi kurmaz; Compose'taki `migrate` adımı bu imajdan
# `alembic upgrade head` çalıştırır.
COPY alembic.ini ./
COPY alembic ./alembic

# Veri dizini (PRD §8.2) açılışta uygulama kullanıcısıyla kurulur; kök sahipliği burada verilir.
RUN useradd --create-home --uid 10001 belgeee \
    && mkdir /srv/data \
    && chown belgeee:belgeee /srv/data
USER belgeee
ENV DATA_DIR=/srv/data

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
