FROM python:3.12-slim

RUN groupadd -r taskit && useradd -r -g taskit -d /app -s /sbin/nologin taskit

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG TASKIT_VERSION=dev
ENV TASKIT_VERSION=${TASKIT_VERSION}
ENV GUNICORN_WORKERS=2

RUN chown -R taskit:taskit /app

USER taskit

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

CMD ["sh", "-c", "gunicorn -b 0.0.0.0:5000 -w ${GUNICORN_WORKERS:-2} --timeout 120 wsgi:app"]
