FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY bio_lookup ./bio_lookup
RUN pip install --no-cache-dir .

RUN useradd --system --uid 10001 app
USER app

# Most hosts inject $PORT; 8000 otherwise. 0.0.0.0 is needed inside a container.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/health', timeout=4)"
CMD ["sh", "-c", "uvicorn bio_lookup.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
