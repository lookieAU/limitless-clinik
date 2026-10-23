#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && exit 0
cp .env.example .env
put() { sed -i "s|^$1=.*|$1=$2|" .env; }
for key in OPENROUTER_API_KEY ANTHROPIC_API_KEY LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET; do
  if [ -n "${!key:-}" ]; then put "$key" "${!key}"; fi
done
for key in CLINIC_API_KEY WEBHOOK_SECRET SESSION_SECRET; do put "$key" "$(openssl rand -hex 24)"; done
if [ -n "${CODESPACE_NAME:-}" ]; then
  put REPLAY_URL "https://${CODESPACE_NAME}-8002.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/replay"
fi
chmod 600 .env
