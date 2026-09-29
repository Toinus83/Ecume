#!/bin/sh
set -eu

api_url=$(printf '%s' "${ECUME_API_URL:-/api}" | tr -d '\r\n')
escaped_api_url=$(printf '%s' "$api_url" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'window.__ECUME_CONFIG__ = { apiBaseUrl: "%s" };\n' "$escaped_api_url" \
  > /usr/share/nginx/html/config.js
