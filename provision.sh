#!/usr/bin/env bash
# Provision AWS EC2 (`agy-ai` + `bookkeeping-web`) and Cloudflare Zero Trust Tunnel.
# Supports browser-based CLI login sessions OR explicit environment variables:
#   - AWS: `aws login` (`~/.aws/login/cache/*.json` or `aws configure export-credentials`),
#          or AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
#   - Cloudflare: `npx wrangler login` (`~/.config/.wrangler/config/default.toml`),
#                 or CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${PROVISION_DISABLE_LOCAL_CACHE:-}" ]; then
    if command -v aws >/dev/null 2>&1; then
        eval "$(aws configure export-credentials --format env 2>/dev/null || true)"
        if [ -z "${AWS_REGION:-}" ]; then
            AWS_REGION="$(aws configure get region 2>/dev/null || echo "")"
            export AWS_REGION
        fi
    fi
    if [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
        eval "$(PYTHONPATH="${SCRIPT_DIR}" python3 -c '
import shlex
from deploy.config import resolve_aws_login_cache_credentials
creds = resolve_aws_login_cache_credentials() or {}
for k, v in creds.items():
    print(f"export {k}={shlex.quote(v)}")
' 2>/dev/null || true)"
    fi
fi

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] && [ -z "${PROVISION_DISABLE_LOCAL_CACHE:-}" ]; then
    WRANGLER_TOKEN="$(PYTHONPATH="${SCRIPT_DIR}" python3 -c 'from deploy.config import resolve_wrangler_oauth_token; print(resolve_wrangler_oauth_token() or "")' 2>/dev/null || true)"
    if [ -n "${WRANGLER_TOKEN}" ]; then
        export CLOUDFLARE_API_TOKEN="${WRANGLER_TOKEN}"
    fi
fi

if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ] && [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
    CF_ACC_ID="$(python3 -c '
import json, os, urllib.request
tok = os.environ["CLOUDFLARE_API_TOKEN"]
req = urllib.request.Request(
    "https://api.cloudflare.com/client/v4/accounts",
    headers={"Authorization": "Bearer " + tok, "Accept": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        res = data.get("result") or []
        if res and isinstance(res, list) and "id" in res[0]:
            print(res[0]["id"])
except Exception:
    pass
' 2>/dev/null || true)"
    if [ -n "${CF_ACC_ID}" ]; then
        export CLOUDFLARE_ACCOUNT_ID="${CF_ACC_ID}"
    fi
fi


exec python3 "${SCRIPT_DIR}/provision.py" "$@"
