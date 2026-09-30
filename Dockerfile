FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY carecost/ carecost/
RUN pip install '.[ocr]' && useradd --create-home --uid 10001 carecost
COPY --chown=carecost:carecost . .
RUN mkdir -p data/processed && chown -R carecost:carecost /app
USER carecost
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"
CMD ["sh", "-c", "(test -f data/processed/boston.sqlite || carecost ingest config/boston_sources.json --download) && streamlit run app.py --server.address=0.0.0.0 --server.headless=true"]
