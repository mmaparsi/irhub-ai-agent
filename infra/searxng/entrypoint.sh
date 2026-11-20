#!/bin/sh
# Generate SearXNG settings so outgoing requests can use an HTTP proxy.
# SEARXNG_PROXY empty means direct connections.
set -eu

OUT="${SEARXNG_SETTINGS_PATH_OVERRIDE:-/tmp/irhub-searxng-settings.yml}"
cp /etc/searxng/settings.yml "$OUT"

cat >> "$OUT" <<'EOF'

outgoing:
  request_timeout: 8.0
  max_request_timeout: 20.0
EOF

if [ -n "${SEARXNG_PROXY:-}" ]; then
  cat >> "$OUT" <<EOF
  proxies:
    all://:
      - ${SEARXNG_PROXY}
EOF
fi

export SEARXNG_SETTINGS_PATH="$OUT"

if [ -x /usr/local/searxng/entrypoint.sh ]; then
  exec /usr/local/searxng/entrypoint.sh "$@"
fi
exec "$@"
