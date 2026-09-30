FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LAB_DATA_DIR=/data
WORKDIR /app
# CI uses official sources; Lighthouse passes the measured Tencent mirror.
ARG LAB_USE_TENCENT_MIRRORS=false
RUN if [ "$LAB_USE_TENCENT_MIRRORS" = "true" ]; then \
      python -c "from pathlib import Path; p=Path('/etc/apt/sources.list.d/debian.sources'); s=p.read_text(); s=s.replace('http://deb.debian.org/debian-security','https://mirrors.cloud.tencent.com/debian-security').replace('https://deb.debian.org/debian-security','https://mirrors.cloud.tencent.com/debian-security').replace('http://deb.debian.org/debian','https://mirrors.cloud.tencent.com/debian').replace('https://deb.debian.org/debian','https://mirrors.cloud.tencent.com/debian'); p.write_text(s)"; \
    elif [ "$LAB_USE_TENCENT_MIRRORS" != "false" ]; then exit 1; fi
RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/* && useradd -u 10001 -m lab
COPY requirements.txt .
RUN if [ "$LAB_USE_TENCENT_MIRRORS" = "true" ]; then \
      pip install --no-cache-dir --timeout 30 --retries 2 --index-url https://mirrors.cloud.tencent.com/pypi/simple -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
COPY app ./app
COPY config ./config
COPY web ./web
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
# A single process owns the durable worker.
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-access-log"]
