FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
RUN if [ -n "$HTTPS_PROXY" ]; then export HTTP_PROXY HTTPS_PROXY; fi; \
    pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .
# A Windows checkout can leave CRLF in the script. The kernel then looks for
# `/bin/sh\r` and fails with "no such file or directory".
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
