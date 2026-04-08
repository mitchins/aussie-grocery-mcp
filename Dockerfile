FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md .
COPY main.py cache.py woolworths.py .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

CMD ["python", "main.py"]
