FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

# apt and many fetchers honor only the lowercase proxy variables.
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG http_proxy=""
ARG https_proxy=""

RUN proxy_http="${http_proxy:-$HTTP_PROXY}"; \
    proxy_https="${https_proxy:-$HTTPS_PROXY}"; \
    if [ -n "$proxy_https" ]; then \
      export http_proxy="$proxy_http" https_proxy="$proxy_https" \
             HTTP_PROXY="${proxy_http}" HTTPS_PROXY="$proxy_https"; \
    fi; \
    pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt

RUN proxy_http="${http_proxy:-$HTTP_PROXY}"; \
    proxy_https="${https_proxy:-$HTTPS_PROXY}"; \
    if [ -n "$proxy_https" ]; then \
      export http_proxy="$proxy_http" https_proxy="$proxy_https" \
             HTTP_PROXY="${proxy_http}" HTTPS_PROXY="$proxy_https"; \
    fi; \
    python -m playwright install-deps chromium || echo "playwright install-deps failed; continuing"; \
    ok=0; \
    i=0; \
    while [ "$i" -lt 5 ]; do \
      if python -m playwright install chromium; then ok=1; break; fi; \
      i=$((i + 1)); \
      echo "playwright chromium download failed (attempt $i); retrying"; \
      sleep 8; \
    done; \
    if [ "$ok" -ne 1 ]; then \
      echo "chromium download failed; the browser tool will be unavailable until browsers are installed"; \
    fi

COPY . .
# A Windows checkout can leave CRLF in the script. The kernel then looks for
# `/bin/sh\r` and fails with "no such file or directory".
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
