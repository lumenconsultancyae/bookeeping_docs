# Operational Release Runbook

## 1. Prerequisites

- **Target Host Environment**: Linux or macOS Docker host with Docker Engine (`>= 24.0`) and Docker Compose v2 (`docker compose`), plus Python `>= 3.11`, Playwright (`playwright>=1.40.0`), and Chromium for test execution.
- **Network & Ports**:
  - Host port `9091/tcp` available for the Nginx web application (`bookkeeping-web`).
  - Host port `3000/tcp` available for the containerized `agy` AI prediction service (`bookkeeping-agy-ai` running `agy_service.py`).
- **Source Paths**:
  - Application repository: `/workspace/projects/bookeeping_4affdf/default/bookkeeping-tool`
  - Deployment (local & prod), documentation & BDD suite repository: `/workspace/projects/bookeeping_4affdf/default/bookeeping_docs`
- **Production Cloud Authentication & Environment Variables (for `provision.sh` / `provision.py`)**:
  - **Recommended Browser-Based CLI Login**:
    - AWS CLI v2 session cache (`~/.aws/login/cache/*.json`) created via `aws login` (or `aws login --remote`).
    - Cloudflare Wrangler OAuth config (`~/.config/.wrangler/config/default.toml`) created via `npx wrangler login`.
  - **Alternative Explicit Environment Variables**:
    - `AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY` (created in AWS Console -> IAM -> Users -> Security credentials: `https://us-east-1.console.aws.amazon.com/iam/home#/users`)
    - `AWS_REGION` (e.g. `us-east-1`, `me-central-1`, `eu-west-1`)
    - `CLOUDFLARE_ACCOUNT_ID` (from `https://dash.cloudflare.com/` account overview URL)
    - `CLOUDFLARE_API_TOKEN` (created at `https://dash.cloudflare.com/profile/api-tokens`)
  - **Endpoint Security Shared Secret**:
    - `AGY_API_SECRET`: 256-bit shared secret verified via constant-time `hmac.compare_digest` between the Cloudflare Pages Function (`functions/api/[[path]].js`) and `agy_service.py` on AWS EC2.
- **Live Production Target Hosts**:
  - Production Custom Domain (`main` branch): `https://bookeeping.lumenconsultancy.net/` (and alias `https://bookkeeping.lumenconsultancy.net/`, bound via Cloudflare Worker Custom Domain `lumen-bookkeeping-prod`)
  - Cloudflare Pages Development / Preview Endpoint: `https://lumen-bookkeeping.pages.dev` (Account ID `971b7e8150db81f3cb98b2969c6286b2`, bound to Cloudflare D1 database `lumen-bookkeeping-db` as `LUMEN_DB` and Cloudflare R2 bucket `lumen-bookkeeping-attachments` as `LUMEN_ATTACHMENTS`)
  - Cloudflare Zero Trust Tunnel: `bookkeeping-prod` (`8e576b19-114e-40a5-9dd0-5a18074f166b`)
  - AWS EC2 Host (`us-east-1`): `i-09003c32e39617fea` (`ec2-100-59-208-234.compute-1.amazonaws.com` / `100.59.208.234`)

---

## 2. Sequential Execution Steps

1. **Verify Port Availability**:
   ```bash
   ss -tlnp | grep -E ':9091|:3000' || true
   ```
2. **Verify Latest Application & Deployment Repository State**:
   ```bash
   cd /workspace/projects/bookeeping_4affdf/default/bookkeeping-tool
   git status -s -b
   cd /workspace/projects/bookeeping_4affdf/default/bookeeping_docs
   git status -s -b
   ```
3. **Start the Local Application & `agy-ai` Stack via Docker Compose**:
   - **Option A (Local Docker Compose Stack in `bookeeping_docs` — Primary)**:
     ```bash
     cd /workspace/projects/bookeeping_4affdf/default/bookeeping_docs
     mkdir -p .agy_state/conversations .agy_state/brain
     docker compose up -d
     docker compose ps
     ```
   - **Option B (Production Provisioning to AWS EC2 + Cloudflare Pages & Tunnel)**:
     1. Authenticate via browser login (or export static environment variables):
        ```bash
        aws login --remote
        npx wrangler login
        export AGY_API_SECRET="$(openssl rand -hex 32)"
        ```
     2. Run the idempotent provisioning script:
        ```bash
        cd /workspace/projects/bookeeping_4affdf/default/bookeeping_docs
        ./provision.sh
        ```
     3. Authenticate `agy` once on the provisioned EC2 host (or sync `~/.gemini` to `/opt/bookkeeping/bookeeping_docs/.agy_state/gemini`):
        ```bash
        ssh -i artifacts/bookkeeping-agy-key.pem ubuntu@100.59.208.234
        sudo docker exec -it bookkeeping-agy-ai agy
        ```
     4. Deploy the static frontend + Edge Function proxy (`functions/api/[[path]].js`) to Cloudflare Pages:
        ```bash
        cd /workspace/projects/bookeeping_4affdf/default/bookkeeping-tool
        npx wrangler pages deploy . --project-name lumen-bookkeeping --branch main
        ```
   - **Option C (Standalone Local Fallback Server for Offline/Air-Gapped Runs Without Docker)**:
     ```bash
     python3 /workspace/projects/bookeeping_4affdf/default/bookeeping_docs/features/support_server.py &
     ```
4. **Configure Custom Prediction Endpoint (If Non-Default)**:
   - By default, Nginx (`default.conf`) routes `/api/v1/prediction/*` directly to `http://agy-ai:3000/api/v1/prediction/*`.
   - To override the endpoint in the UI, open `http://localhost:9091`, navigate to **Settings**, enter the custom endpoint URL under **AI Integration Settings**, and click **Save AI Settings**.

---

## 3. Verification Signals

1. **Web Application HTTP Readiness Check**:
   ```bash
   curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:9091/
   ```
   - **Expected Output**: `200`
2. **`agy-ai` Service & Reverse-Proxy Readiness Check**:
   ```bash
   curl -fsS http://localhost:3000/health
   curl -fsS http://localhost:9091/api/v1/ping
   ```
   - **Expected Output**: `{"status": "ok", "engine": "agy", "model": "Gemini 4 Argon (High)"}`
3. **Static Assets & Vendor Shims Delivery Check**:
   ```bash
   curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:9091/script.js
   curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:9091/style.css
   curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:9091/__vendor__/chart.js
   curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:9091/__vendor__/pdf.min.js
   ```
   - **Expected Output**: `200` for all assets.
4. **Production Security Gate Verification (`401` / `403` / `200`)**:
   ```bash
   # 1. Direct external call without headers -> Must return 401 Unauthorized
   curl -s -o /dev/null -w "%{http_code}\n" -X POST https://lumen-bookkeeping.pages.dev/api/v1/prediction/test \
     -H "Content-Type: application/json" -d '{"question":"ping"}'

   # 2. Cross-origin call from untrusted domain -> Must return 403 Forbidden
   curl -s -o /dev/null -w "%{http_code}\n" -X POST https://lumen-bookkeeping.pages.dev/api/v1/prediction/test \
     -H "Content-Type: application/json" -H "X-Lumen-Client: lumen-bookkeeping-web" \
     -H "Origin: https://evil.example.com" -d '{"question":"ping"}'

   # 3. Direct call to EC2 bypassing Cloudflare Pages (missing X-Agy-Proxy-Secret) -> Must return 401 Unauthorized
   curl -s -o /dev/null -w "%{http_code}\n" -X POST http://ec2-100-59-208-234.compute-1.amazonaws.com/api/v1/prediction/test \
     -H "Content-Type: application/json" -H "X-Lumen-Client: lumen-bookkeeping-web" \
     -H "Origin: https://lumen-bookkeeping.pages.dev" -d '{"question":"ping"}'
   ```
5. **Provisioning Dry-Run & In-Process Unit + Automated BDD E2E Verification**:
   ```bash
   cd /workspace/projects/bookeeping_4affdf/default/bookeeping_docs
   python3 -B -m unittest discover -s tests -v
   behave
   ```
   - **Expected Output**: 100% passing unit, HTTP integration, and browser DOM behavioral tests (`tests/test_agy_service.py`, `tests/test_provisioning.py`, `tests/test_provisioning_clients.py`, `tests/test_auth_and_welcome.py`, `tests/test_faf_export.py`, `tests/test_ledger_and_timesheet_deletion.py`, `tests/test_payslip_and_timesheet_filter.py`, `tests/test_react_migration.py`, `tests/test_uae_compliance.py`, `tests/test_ui_feedback_and_forms.py`, `tests/test_ui_tables_and_layout.py`, and `tests/test_whatsapp_workflows.py`), 8 features passed (43 scenarios) in `behave`, zero failed assertions, and zero `SEVERE` browser console errors.

---

## 4. Rollback Plan

### Rollback Criteria
Trigger an immediate rollback if any of the following conditions occur during or after release:
- `http://localhost:9091/` or `http://localhost:3000/health` returns non-`200` HTTP status codes.
- Uncaught JavaScript `SyntaxError` or `TypeError` logs appear in the browser console on startup.
- Any unit test in `bookeeping_docs/tests/` or scenario in the `bookeeping_docs` `behave` BDD regression suite fails.

### Rollback Steps
1. **Revert to Previous Known-Good Commit**:
   ```bash
   cd /workspace/projects/bookeeping_4affdf/default/bookeeping_docs
   git checkout <previous-known-good-sha>
   ```
2. **Recreate and Restart the Docker Compose Stack**:
   ```bash
   cd /workspace/projects/bookeeping_4affdf/default/bookeeping_docs
   docker compose up -d --force-recreate bookkeeping-app agy-ai
   ```
3. **Confirm Recovery**:
   ```bash
   curl -fsS http://localhost:9091/api/v1/ping
   cd /workspace/projects/bookeeping_4affdf/default/bookeeping_docs && behave --tags=@smoke
   ```
