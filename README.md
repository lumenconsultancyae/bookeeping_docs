# Lumen Accounting Suite — Deployment, Documentation & BDD E2E Test Suite (`bookeeping_docs`)

This repository contains the local and production deployment configurations, AWS + Cloudflare provisioning automation, product/architecture/operational documentation, and the Behavior-Driven Development (BDD) end-to-end browser verification suite for the **Lumen Accounting Suite** (`bookkeeping-tool`).

---

## 1. Repository Structure

```text
bookeeping_docs/
├── README.md                                        # Repository overview, deployment & test guide
├── docker-compose.yml                               # Local Docker Compose stack (bookkeeping-web + agy-ai + tunnels)
├── docker-compose.prod.yml                          # Production Docker Compose stack for AWS EC2 + Cloudflare Tunnel
├── Dockerfile.agy                                   # Production Dockerfile building agy-ai on AWS EC2
├── default.conf                                     # Nginx reverse-proxy configuration (/api/ & /__vendor__/)
├── agy_service.py                                   # HTTP prediction service wrapping the agy CLI
├── provision.py                                     # AWS EC2 + Cloudflare Tunnel provisioning CLI entrypoint
├── provision.sh                                     # Shell wrapper reading AWS & Cloudflare env vars
├── deploy/                                          # Layered AWS EC2 (SigV4) & Cloudflare API v4 provisioning modules
│   ├── config.py                                    # Typed environment variable validation & secret masking
│   ├── domain.py                                    # Domain error codes, specs & cloud-init UserData builder
│   ├── infrastructure.py                            # Cloudflare API v4 & AWS EC2 Query API (SigV4) adapters
│   └── service.py                                   # End-to-end provisioning orchestration service
├── tests/                                           # Unit, HTTP integration & behavioral JS test suite
│   ├── test_agy_service.py                          # Unit & HTTP integration tests for agy_service.py
│   ├── test_auth_and_welcome.py                     # Auth, multi-tenant isolation, plan gating & edge proxy tests
│   ├── test_faf_export.py                           # FTA VAT 201, FAF CSV, Credit Notes, PINT-AE XML & XSS tests
│   └── test_provisioning.py                         # Unit & CLI tests for AWS/Cloudflare provisioning
├── behave.ini                                       # Behave BDD runner configuration
├── requirements.txt                                 # Python BDD & WebDriver dependencies
├── docs/
│   ├── product/
│   │   ├── prd-product-requirements.md              # Product Requirements Document (PRD)
│   │   └── user-guide-and-release-notes.md          # Customer-facing User Guide & Release Notes
│   ├── technical/
│   │   ├── architecture-and-execution-flow.md       # Exhaustive 6-phase technical & schema breakdown
│   │   ├── sdd-system-design.md                     # Software Design Document (SDD) & Target Architecture
│   │   └── operational-runbook.md                   # Deployment, verification & rollback runbook
│   └── diagrams/
│       ├── system-architecture.drawio               # Normalized system & agy-ai proxy architecture diagram
│       └── data-flow-and-ledger.drawio              # Double-entry ledger & tax engine data-flow diagram
└── features/
    ├── config.py                                    # Centralized environment & timeout configuration
    ├── support_server.py                            # Standalone fallback HTTP server + offline vendor shims
    ├── environment.py                               # Behave hooks (health check, console check, teardown)
    ├── pages/                                       # Page Object Model (UI interactions & atomic waits)
    │   ├── base_page.py
    │   ├── dashboard_page.py
    │   ├── accounting_page.py
    │   ├── contacts_and_inventory_page.py
    │   ├── transactions_page.py
    │   ├── expenses_and_admin_page.py
    │   ├── payroll_and_assets_page.py
    │   └── reports_and_settings_page.py
    ├── steps/                                       # Step Definitions (assertions & Page Object orchestration)
    │   ├── common_steps.py
    │   ├── dashboard_steps.py
    │   ├── accounting_steps.py
    │   ├── contacts_and_inventory_steps.py
    │   ├── transactions_steps.py
    │   ├── expenses_and_admin_steps.py
    │   ├── payroll_and_assets_steps.py
    │   └── reports_and_settings_steps.py
    ├── dashboard_and_kpis.feature                   # Executive Dashboard KPIs & period filtering
    ├── chart_of_accounts_and_journals.feature       # COA, Manual Journals, Accruals, Deferred Revenue & Period Lock
    ├── contacts_and_inventory.feature               # Customers, Suppliers, Inventory, Stock Ledger & Cheques
    ├── commercial_transactions.feature              # Sales E-Invoices, Credit Notes, AI Bills, Expenses, Quotes, POs & Banking
    ├── payroll_and_assets.feature                   # Employees, UAE WPS Payroll, EOSB Gratuity & Fixed Assets
    └── reports_tax_and_settings.feature             # Trial Balance, P&L, Balance Sheet, Cash Flow, VAT 201, FAF, CT, FP&A & Admin
```

---

## 2. Documentation Index

| Document | Category | Description |
| :--- | :--- | :--- |
| [`docs/product/user-guide-and-release-notes.md`](docs/product/user-guide-and-release-notes.md) | Customer / Product | End-user workflow guide covering Dashboard, Sales, Credit Notes, Direct Expenses, Procurement, Inventory, Payroll, Tax Filing (VAT 201 & FAF), and Release Notes. |
| [`docs/product/prd-product-requirements.md`](docs/product/prd-product-requirements.md) | Product | Product Requirements Document detailing target personas, delivered functional capabilities, and target roadmap scope. |
| [`docs/technical/architecture-and-execution-flow.md`](docs/technical/architecture-and-execution-flow.md) | Engineering | Deep-dive technical documentation covering all 6 runtime phases, double-entry ledger math, multi-tenant storage, IndexedDB attachments, and PINT-AE XML / FAF / SIF schemas. |
| [`docs/technical/sdd-system-design.md`](docs/technical/sdd-system-design.md) | Engineering | Software Design Document covering modular subsystem boundaries, resolved architecture, and target cloud persistence roadmap. |
| [`docs/technical/operational-runbook.md`](docs/technical/operational-runbook.md) | Operations | Local and production (AWS EC2 + Cloudflare) deployment runbook with prerequisites, sequential execution commands, verification signals, and rollback steps. |
| [`docs/diagrams/system-architecture.drawio`](docs/diagrams/system-architecture.drawio) | Architecture Diagram | Normalized Draw.io system architecture diagram across Browser SPA, Cloudflare Edge (`functions/api/[[path]].js`), Nginx Proxy (`bookkeeping-web`), and `agy-ai` (`bookkeeping-agy-ai`) services. |
| [`docs/diagrams/data-flow-and-ledger.drawio`](docs/diagrams/data-flow-and-ledger.drawio) | Data-Flow Diagram | Normalized Draw.io transaction ingestion, double-entry ledger decomposition, and financial statement pipeline diagram. |

---

## 3. Local Deployment, Production Provisioning & Running the Test Suites

### Prerequisites
- Docker Engine (`>= 24.0`) and Docker Compose v2 (`docker compose`)
- Python 3.11+ with `behave` and `selenium` installed (`pip install -r requirements.txt`)
- Node.js (`>= 18`) for behavioral JavaScript module execution tests
- Chromium (`chromium`) and ChromeDriver (`chromedriver`)

### 1. Start the Local Docker Compose Stack (`bookkeeping-web` + `bookkeeping-agy-ai`)
```bash
mkdir -p .agy_state/gemini .agy_state/conversations .agy_state/brain
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml ps
```
> **Note**: Locally, `bookkeeping-web` is exposed on `http://localhost:9091` and `bookkeeping-agy-ai` builds from [`Dockerfile.agy`](Dockerfile.agy), binds host port `3000:3000`, and joins `lumen_default` with aliases `agy-ai` and `flowise` to replace the legacy Flowise container across all workspace services.

### 2. Provision Production Stack on AWS EC2 + Cloudflare (Pages & Zero Trust Tunnel)

You can authenticate with AWS and Cloudflare using either **browser-based OAuth sessions (recommended)** or **explicit environment variables**. [`provision.sh`](provision.sh) automatically detects cached browser login tokens before falling back to environment variables.

#### Option A: Browser-Based CLI Login (Recommended — No Long-Lived Static Keys)
1. **Authenticate with AWS via Browser (`aws login`)**:
   ```bash
   aws login
   # Or in a remote/containerized terminal:
   aws login --remote
   ```
   This stores short-lived session credentials in `~/.aws/login/cache/*.json`, which [`deploy/config.py`](deploy/config.py) (`resolve_aws_login_cache_credentials`) reads automatically.
2. **Authenticate with Cloudflare via Browser (`wrangler login`)**:
   ```bash
   npx wrangler login
   ```
   This stores an OAuth token in `~/.config/.wrangler/config/default.toml`, which [`deploy/config.py`](deploy/config.py) (`resolve_wrangler_oauth_token`) reads automatically.
3. **Run Provisioning**:
   ```bash
   export AGY_API_SECRET="<strong-random-shared-secret>"
   ./provision.sh
   ```

#### Option B: Explicit Environment Variables
If you prefer static IAM keys and a Cloudflare API token:
- **AWS Console**: Sign in at `https://console.aws.amazon.com/`, open **IAM -> Users -> Security credentials -> Create access key** (`https://us-east-1.console.aws.amazon.com/iam/home#/users`).
- **Cloudflare Dashboard**: Sign in at `https://dash.cloudflare.com/`, copy your **Account ID** from the account overview URL, and create an API Token at `https://dash.cloudflare.com/profile/api-tokens` with **Cloudflare Tunnel: Edit**, **Cloudflare Pages: Edit**, and **DNS: Edit** permissions.
```bash
export AWS_ACCESS_KEY_ID="<your-aws-access-key-id>"
export AWS_SECRET_ACCESS_KEY="<your-aws-secret-access-key>"
export AWS_REGION="us-east-1"
export CLOUDFLARE_ACCOUNT_ID="<your-cloudflare-account-id>"
export CLOUDFLARE_API_TOKEN="<your-cloudflare-api-token>"
export AGY_API_SECRET="<strong-random-shared-secret>"
# Optional custom domain in your Cloudflare account:
# export CLOUDFLARE_DOMAIN="bookkeeping.lumenconsultancy.net"

./provision.sh
```

#### One-Time `agy` Google OAuth Session on AWS EC2
Once the EC2 instance boots, either sync your local `~/.gemini` session directory or SSH in once to authenticate `agy` with your Google account (persisted in `/opt/bookkeeping/bookeeping_docs/.agy_state/gemini`):
```bash
ssh -i artifacts/bookkeeping-agy-key.pem ubuntu@<EC2_PUBLIC_IP>
sudo docker exec -it bookkeeping-agy-ai agy
```

#### Live Provisioned Production & Development Environments
- **Production Custom Domain (`main` branch)**: `https://bookeeping.lumenconsultancy.net/` (and alias `https://bookkeeping.lumenconsultancy.net/`), routed via Cloudflare Worker Custom Domain (`lumen-bookkeeping-prod` on zone `lumenconsultancy.net`)
- **Cloudflare Pages Development / Preview URL**: `https://lumen-bookkeeping.pages.dev` (with Edge Function proxy [`bookkeeping-tool/functions/api/[[path]].js`](../bookkeeping-tool/functions/api/[[path]].js))
- **Cloudflare Zero Trust Tunnel**: `bookkeeping-prod` (`8e576b19-114e-40a5-9dd0-5a18074f166b`)
- **AWS EC2 Instance (`us-east-1`)**: `i-09003c32e39617fea` (`ec2-100-59-208-234.compute-1.amazonaws.com` / `100.59.208.234`)

---

## 4. `agy-ai` Prediction Endpoint Security Architecture

To prevent unauthorized external users or third-party websites from invoking the `/api/v1/prediction/*` service, a three-layer security gate is enforced across the frontend SPA, the Cloudflare Edge (`lumen-bookkeeping-prod` Worker & Pages Function), and [`agy_service.py`](agy_service.py):

1. **Origin & Referer Allowlist (`HTTP 403 forbidden_origin`)**:
   - Both [`bookkeeping-tool/functions/api/[[path]].js`](../bookkeeping-tool/functions/api/[[path]].js) and [`agy_service.py`](agy_service.py) (`_is_allowed_origin`) validate the request `Origin` (and `Referer` fallback) against trusted application origins (`https://bookeeping.lumenconsultancy.net`, `https://bookkeeping.lumenconsultancy.net`, `https://lumen-bookkeeping.pages.dev`, `https://*.lumen-bookkeeping.pages.dev`, `http://localhost:9091`, `http://127.0.0.1:9091`, `http://bookkeeping-web`).
   - Wildcard CORS (`Access-Control-Allow-Origin: *`) is disabled; CORS headers are only emitted for verified allowlisted origins, blocking any cross-origin browser requests at preflight (`OPTIONS`).
2. **Application Handshake Header (`X-Lumen-Client: lumen-bookkeeping-web` — `HTTP 401 unauthorized`)**:
   - All 5 AI extraction `fetch()` calls across [`bookkeeping-tool/script.js`](../bookkeeping-tool/script.js) and [`bookkeeping-tool/expenses.js`](../bookkeeping-tool/expenses.js) attach `'X-Lumen-Client': 'lumen-bookkeeping-web'`.
   - Requests missing this header (such as direct `curl` probes or generic scanners) are rejected with `401 Unauthorized` and also forced through CORS preflight in browsers.
3. **Edge-to-Origin Shared Secret (`X-Agy-Proxy-Secret` / `AGY_API_SECRET` — `HTTP 401 unauthorized`)**:
   - The Cloudflare Pages Function [`functions/api/[[path]].js`](../bookkeeping-tool/functions/api/[[path]].js) validates both `GET` and `POST` requests (rejecting other HTTP methods with `405 Method Not Allowed`), fails closed (`503 Service Unavailable`) if `AGY_BACKEND_URL` is unconfigured, and injects `X-Agy-Proxy-Secret` from the server-side `AGY_API_SECRET` environment secret when forwarding validated requests to AWS EC2.
   - [`agy_service.py`](agy_service.py) (`_verify_prediction_request_security`) verifies `X-Agy-Proxy-Secret` using constant-time `hmac.compare_digest`. Any direct request to the AWS EC2 IP/hostname that bypasses the Cloudflare Pages Function is immediately rejected with `401 Unauthorized`, even if `Origin` and `X-Lumen-Client` headers are spoofed.

---

## 5. Running the Test Suites

### 1. Run In-Process Unit, HTTP Integration & Behavioral JS Tests
```bash
python3 -B -m unittest discover -s tests -v
```

### 2. Execute the Behave BDD E2E Suite
```bash
# Run all 32 scenarios across all 6 features
behave

# Run only @smoke tagged scenarios
behave --tags=@smoke
```
