#!/usr/bin/env bash
# Run on the VPS from the repository root:
#   DOMAIN=example.com GUARD_DEMO_KEY=$(openssl rand -hex 12) bash deploy/deploy.sh
set -euo pipefail
: "${DOMAIN:?set DOMAIN, e.g. DOMAIN=example.com}"
: "${GUARD_DEMO_KEY:?set GUARD_DEMO_KEY (keep it secret; the attack script needs it)}"
if ! command -v docker >/dev/null; then
  echo "Docker is not installed. Use Hostinger's Docker VPS template or install Docker first." >&2
  exit 1
fi
export DOMAIN GUARD_DEMO_KEY
docker compose -f deploy/docker-compose.yml up -d --build
echo
echo "Started. Check in a minute (certificates need the DNS records first):"
echo "  https://$DOMAIN          tools"
echo "  https://trial.$DOMAIN    the free-trial site"
echo "  https://guard.$DOMAIN    the live dashboard"
echo "Attack from a laptop on another network:"
echo "  python3 scripts/attack_demo.py https://trial.$DOMAIN --key \$GUARD_DEMO_KEY"
