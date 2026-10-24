FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# eMudhra/emSign CA keys broken (2026-10-20). Debian trixie's ca-certificates
# still ships those roots, so distrust them in the OS store (used by curl and,
# via SSL_CERT_FILE below, httpx). The python check fails the build if any remain.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && sed -i -E 's|^(mozilla/emSign_.*)$|!\1|' /etc/ca-certificates.conf \
 && update-ca-certificates --fresh \
 && python -c "import ssl; c = ssl.create_default_context(cafile='/etc/ssl/certs/ca-certificates.crt'); bad = [x for x in c.get_ca_certs() if 'eMudhra' in str(x['subject'])]; assert not bad, bad" \
 && rm -rf /var/lib/apt/lists/*

# certifi (even 2026.10.23) still ships "emSign Root CA - G1". Point httpx at
# the cleaned OS bundle instead; httpx reads SSL_CERT_FILE when trust_env=True.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

COPY pyproject.toml ./
# pip vendors its own certifi; >=26.2.2 carries the eMudhra distrust.
RUN pip install --upgrade "pip>=26.2.2" \
 && pip install .

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY start.sh ./start.sh
RUN chmod +x /app/start.sh

ENV PORT=8000
EXPOSE 8000

CMD ["/app/start.sh"]
