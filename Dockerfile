FROM python:3.12-slim
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/app/model-cache
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN if [ "$TARGETARCH" = "amd64" ]; then pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu; fi && pip install --no-cache-dir .
RUN useradd --uid 10001 --create-home app && mkdir -p /app/data /app/storage /app/model-cache && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')"
CMD ["eve-ah", "serve", "--host", "0.0.0.0"]
