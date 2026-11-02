"""Domain value objects, error codes, and cloud-init UserData specification builders."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import shlex


class ProvisioningErrorCode(str, Enum):
    """Stable machine-readable error codes for AWS and Cloudflare provisioning."""

    MISSING_CREDENTIALS = "missing_credentials"
    INVALID_CONFIGURATION = "invalid_configuration"
    CLOUDFLARE_API_ERROR = "cloudflare_api_error"
    AWS_API_ERROR = "aws_api_error"
    BOOTSTRAP_ERROR = "bootstrap_error"


class ProvisioningError(Exception):
    """Domain exception carrying a stable error code and safe public message."""

    def __init__(
        self,
        code: ProvisioningErrorCode,
        message: str,
        *,
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = dict(context) if context else {}

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.context:
            payload["context"] = self.context
        return {"error": payload}


@dataclass(frozen=True)
class CloudflareTunnelSpec:
    """Value object representing a provisioned Cloudflare Zero Trust Tunnel and its routing."""

    tunnel_id: str
    tunnel_name: str
    tunnel_token: str
    public_hostname: str | None = None
    dns_record_id: str | None = None


@dataclass(frozen=True)
class CloudflarePagesSpec:
    """Value object representing a GitHub-connected Cloudflare Pages project (auto-deployed on git push)."""

    project_name: str
    pages_url: str
    github_owner: str
    github_repo: str
    production_branch: str



@dataclass(frozen=True)
class Ec2InstanceSpec:
    """Value object representing a provisioned AWS EC2 instance running the Docker Compose stack."""

    instance_id: str
    public_ip: str
    ami_id: str
    security_group_id: str
    key_name: str
    key_path: str | None = None


@dataclass(frozen=True)
class ProvisioningResult:
    """Immutable workflow result returned by `ProvisioningService.run()`."""

    dry_run: bool
    region: str
    cloudflare_account_id: str
    tunnel_id: str
    tunnel_name: str
    public_url: str
    instance_id: str
    public_ip: str
    ssh_command: str
    agy_login_command: str
    pages_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "region": self.region,
            "cloudflare_account_id": self.cloudflare_account_id,
            "tunnel_id": self.tunnel_id,
            "tunnel_name": self.tunnel_name,
            "public_url": self.public_url,
            "pages_url": self.pages_url,
            "instance_id": self.instance_id,
            "public_ip": self.public_ip,
            "ssh_command": self.ssh_command,
            "agy_login_command": self.agy_login_command,
        }



def build_ec2_user_data_script(
    *,
    cloudflare_tunnel_token: str,
    agy_model: str,
    app_repo_url: str,
    docs_repo_url: str,
    agy_api_secret: str | None = None,
    app_branch: str = "main",
    docs_branch: str = "main",
) -> str:
    """Build the idempotent Ubuntu cloud-init UserData script for the EC2 host.

    Installs Docker Engine and Docker Compose v2, clones `bookkeeping-tool` and
    `bookeeping_docs` into `/opt/bookkeeping`, creates the writable `/opt/bookkeeping/bookeeping_docs/.agy_state/gemini`
    directory for one-time interactive Google OAuth login (`docker exec -it bookkeeping-agy-ai agy`),
    writes `.env`, and starts `docker-compose.prod.yml`.
    """
    quoted_token = shlex.quote(cloudflare_tunnel_token)
    quoted_model = shlex.quote(agy_model)
    quoted_secret = shlex.quote(agy_api_secret or "")
    quoted_app_repo = shlex.quote(app_repo_url)
    quoted_docs_repo = shlex.quote(docs_repo_url)
    quoted_app_branch = shlex.quote(app_branch)
    quoted_docs_branch = shlex.quote(docs_branch)

    return f"""#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg git

if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
fi

mkdir -p /opt/bookkeeping
cd /opt/bookkeeping

if [ ! -d /opt/bookkeeping/bookkeeping-tool ]; then
    git clone --branch {quoted_app_branch} {quoted_app_repo} /opt/bookkeeping/bookkeeping-tool || git clone {quoted_app_repo} /opt/bookkeeping/bookkeeping-tool
fi

if [ ! -d /opt/bookkeeping/bookeeping_docs ]; then
    git clone --branch {quoted_docs_branch} {quoted_docs_repo} /opt/bookkeeping/bookeeping_docs || git clone {quoted_docs_repo} /opt/bookkeeping/bookeeping_docs
fi

cd /opt/bookkeeping/bookeeping_docs
mkdir -p /opt/bookkeeping/bookeeping_docs/.agy_state/gemini

cat > /opt/bookkeeping/bookeeping_docs/.env <<EOF
HOST_APP_DIR=/opt/bookkeeping/bookkeeping-tool
AGY_STATE_DIR=/opt/bookkeeping/bookeeping_docs/.agy_state
AGY_MODEL={quoted_model}
AGY_API_SECRET={quoted_secret}
AGY_REQUIRE_ORIGIN=true
CLOUDFLARE_TUNNEL_TOKEN={quoted_token}
EOF
chmod 600 /opt/bookkeeping/bookeeping_docs/.env

docker compose -f docker-compose.prod.yml up -d --build

cat > /etc/motd <<'MOTD'
=======================================================================
Lumen Bookkeeping App & agy-ai Stack
To complete the one-time Google account login for agy:
  sudo docker exec -it bookkeeping-agy-ai agy
=======================================================================
MOTD
"""
