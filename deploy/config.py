"""Typed environment configuration for AWS EC2 and Cloudflare provisioning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from deploy.domain import ProvisioningError, ProvisioningErrorCode

WRANGLER_OAUTH_CLIENT_ID = "54d11594-84e4-41aa-b438-e81b8fa78ee7"
WRANGLER_OAUTH_TOKEN_URL = "https://dash.cloudflare.com/oauth2/token"

REQUIRED_ENV_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
)


def resolve_aws_login_cache_credentials(home_dir: Path | None = None) -> dict[str, str] | None:
    """Read short-lived AWS credentials from `~/.aws/login/cache/*.json` created by `aws login`."""
    base_home = home_dir or Path.home()
    candidates = [
        base_home / ".aws" / "login" / "cache",
        Path(__file__).resolve().parent.parent / ".agy_state" / "aws_home" / "login" / "cache",
    ]
    for cache_dir in candidates:
        if not cache_dir.is_dir():
            continue
        for json_file in sorted(cache_dir.glob("*.json")):
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            token_obj = payload.get("accessToken")
            if isinstance(token_obj, dict):
                ak = str(token_obj.get("accessKeyId") or "").strip()
                sk = str(token_obj.get("secretAccessKey") or "").strip()
                st = str(token_obj.get("sessionToken") or "").strip()
                region = str(payload.get("signInRegion") or "us-east-1").strip()
                if ak and sk:
                    result = {
                        "AWS_ACCESS_KEY_ID": ak,
                        "AWS_SECRET_ACCESS_KEY": sk,
                        "AWS_REGION": region,
                    }
                    if st:
                        result["AWS_SESSION_TOKEN"] = st
                    return result
    return None


def _refresh_cloudflare_oauth_token(refresh_token: str) -> dict[str, object]:
    """Exchange a Wrangler OAuth `refresh_token` for a fresh `access_token`."""
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": WRANGLER_OAUTH_CLIENT_ID,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        WRANGLER_OAUTH_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "wrangler/3.114.17",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}


def _is_wrangler_token_expired(expiration_raw: str) -> bool:
    if not expiration_raw:
        return False
    try:
        normalized = expiration_raw.replace("Z", "+00:00")
        exp_dt = datetime.fromisoformat(normalized)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return exp_dt <= (datetime.now(timezone.utc) + timedelta(seconds=60))
    except ValueError:
        return False


def resolve_wrangler_oauth_token(
    home_dir: Path | None = None,
    *,
    token_refresher: Callable[[str], dict[str, object]] | None = None,
) -> str | None:
    """Read (and automatically refresh if expired) the Cloudflare OAuth token saved by `wrangler login`."""
    base_home = home_dir or Path.home()
    repo_cf_home = Path(__file__).resolve().parent.parent / ".agy_state" / "cf_home"
    candidates = (
        base_home / ".config" / ".wrangler" / "config" / "default.toml",
        base_home / ".wrangler" / "config" / "default.toml",
        base_home / "Library" / "Preferences" / ".wrangler" / "config" / "default.toml",
        repo_cf_home / ".config" / ".wrangler" / "config" / "default.toml",
    )
    refresher = token_refresher or _refresh_cloudflare_oauth_token

    for cfg in candidates:
        if not cfg.is_file():
            continue
        try:
            content = cfg.read_text(encoding="utf-8")
        except OSError:
            continue
        tok_match = re.search(r'^\s*oauth_token\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
        exp_match = re.search(r'^\s*expiration_time\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
        ref_match = re.search(r'^\s*refresh_token\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
        oauth_token = tok_match.group(1).strip() if tok_match else ""
        expiration_raw = exp_match.group(1).strip() if exp_match else ""
        refresh_token = ref_match.group(1).strip() if ref_match else ""

        if refresh_token and (not oauth_token or _is_wrangler_token_expired(expiration_raw)):
            try:
                refreshed = refresher(refresh_token)
                new_access = str(refreshed.get("access_token") or "").strip()
                new_refresh = str(refreshed.get("refresh_token") or refresh_token).strip()
                expires_in = int(refreshed.get("expires_in") or 3600)
                if new_access:
                    new_exp = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
                    updated = re.sub(
                        r'(^\s*oauth_token\s*=\s*)"[^"]*"',
                        f'\\1"{new_access}"',
                        content,
                        flags=re.MULTILINE,
                    )
                    updated = re.sub(
                        r'(^\s*refresh_token\s*=\s*)"[^"]*"',
                        f'\\1"{new_refresh}"',
                        updated,
                        flags=re.MULTILINE,
                    )
                    updated = re.sub(
                        r'(^\s*expiration_time\s*=\s*)"[^"]*"',
                        f'\\1"{new_exp}"',
                        updated,
                        flags=re.MULTILINE,
                    )
                    try:
                        cfg.write_text(updated, encoding="utf-8")
                    except OSError:
                        pass
                    return new_access
            except Exception:
                pass

        if oauth_token:
            return oauth_token
    return None



@dataclass(frozen=True)
class ProvisioningSettings:
    """Validated configuration loaded from environment variables with masked secret fields."""

    aws_access_key_id: str
    _aws_secret_access_key: str = field(repr=False)
    aws_region: str
    cloudflare_account_id: str
    _cloudflare_api_token: str = field(repr=False)
    _aws_session_token: str | None = field(default=None, repr=False)
    cloudflare_tunnel_name: str = "bookkeeping-prod"
    cloudflare_pages_project: str = "lumen-bookkeeping"
    cloudflare_d1_database_name: str = "lumen-bookkeeping-db"
    cloudflare_r2_bucket_name: str = "lumen-bookkeeping-attachments"
    cloudflare_domain: str | None = None

    cloudflare_zone_id: str | None = None
    ec2_instance_name: str = "bookkeeping-agy-prod"
    ec2_instance_type: str = "t3.small"
    ec2_security_group_name: str = "bookkeeping-agy-sg"
    ec2_key_name: str = "bookkeeping-agy-key"
    agy_model: str = "Gemini 4 Argon (High)"
    _agy_api_secret: str | None = field(default=None, repr=False)
    app_repo_url: str = "https://github.com/lumenconsultancyae/bookkeeping-tool.git"
    docs_repo_url: str = "https://github.com/lumenconsultancyae/bookeeping_docs.git"
    dry_run: bool = False
    artifacts_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "artifacts")

    def __repr__(self) -> str:
        return (
            "ProvisioningSettings("
            f"aws_access_key_id={self.aws_access_key_id!r}, "
            "aws_secret_access_key='***', "
            f"aws_region={self.aws_region!r}, "
            f"cloudflare_account_id={self.cloudflare_account_id!r}, "
            "cloudflare_api_token='***', "
            f"cloudflare_tunnel_name={self.cloudflare_tunnel_name!r}, "
            f"cloudflare_domain={self.cloudflare_domain!r}, "
            f"ec2_instance_type={self.ec2_instance_type!r}, "
            f"dry_run={self.dry_run!r})"
        )

    def unwrap_aws_secret_access_key(self) -> str:
        return self._aws_secret_access_key

    def unwrap_cloudflare_api_token(self) -> str:
        return self._cloudflare_api_token

    def unwrap_aws_session_token(self) -> str | None:
        return self._aws_session_token

    def unwrap_agy_api_secret(self) -> str | None:
        return self._agy_api_secret

    @classmethod
    def from_env(
        cls,
        environ: dict[str, str] | None = None,
        *,
        artifacts_dir: Path | None = None,
    ) -> ProvisioningSettings:
        env = environ if environ is not None else os.environ
        missing = [key for key in REQUIRED_ENV_VARS if not (env.get(key) or "").strip()]
        if missing:
            raise ProvisioningError(
                ProvisioningErrorCode.MISSING_CREDENTIALS,
                f"Missing required environment variables: {', '.join(missing)}",
                context={"missing_variables": ", ".join(missing)},
            )

        dry_run_raw = (env.get("PROVISION_DRY_RUN") or env.get("DRY_RUN") or "").strip().lower()
        dry_run = dry_run_raw in ("1", "true", "yes")

        resolved_artifacts = artifacts_dir or Path(
            env.get("PROVISION_ARTIFACTS_DIR") or (Path(__file__).resolve().parent.parent / "artifacts")
        )

        return cls(
            aws_access_key_id=env["AWS_ACCESS_KEY_ID"].strip(),
            _aws_secret_access_key=env["AWS_SECRET_ACCESS_KEY"].strip(),
            aws_region=env["AWS_REGION"].strip(),
            cloudflare_account_id=env["CLOUDFLARE_ACCOUNT_ID"].strip(),
            _cloudflare_api_token=env["CLOUDFLARE_API_TOKEN"].strip(),
            _aws_session_token=(env.get("AWS_SESSION_TOKEN") or "").strip() or None,
            cloudflare_tunnel_name=(env.get("CLOUDFLARE_TUNNEL_NAME") or "bookkeeping-prod").strip(),
            cloudflare_pages_project=(env.get("CLOUDFLARE_PAGES_PROJECT") or "lumen-bookkeeping").strip(),
            cloudflare_d1_database_name=(env.get("CLOUDFLARE_D1_DATABASE_NAME") or "lumen-bookkeeping-db").strip(),
            cloudflare_r2_bucket_name=(env.get("CLOUDFLARE_R2_BUCKET_NAME") or "lumen-bookkeeping-attachments").strip(),
            cloudflare_domain=(env.get("CLOUDFLARE_DOMAIN") or "").strip() or None,

            cloudflare_zone_id=(env.get("CLOUDFLARE_ZONE_ID") or "").strip() or None,
            ec2_instance_name=(env.get("EC2_INSTANCE_NAME") or "bookkeeping-agy-prod").strip(),
            ec2_instance_type=(env.get("EC2_INSTANCE_TYPE") or "t3.small").strip(),
            ec2_security_group_name=(env.get("EC2_SECURITY_GROUP_NAME") or "bookkeeping-agy-sg").strip(),
            ec2_key_name=(env.get("EC2_KEY_NAME") or "bookkeeping-agy-key").strip(),
            agy_model=(env.get("AGY_MODEL") or "Gemini 4 Argon (High)").strip(),
            _agy_api_secret=(env.get("AGY_API_SECRET") or "").strip() or None,
            app_repo_url=(
                env.get("APP_REPO_URL") or "https://github.com/lumenconsultancyae/bookkeeping-tool.git"
            ).strip(),
            docs_repo_url=(
                env.get("DOCS_REPO_URL") or "https://github.com/lumenconsultancyae/bookeeping_docs.git"
            ).strip(),
            dry_run=dry_run,
            artifacts_dir=resolved_artifacts,
        )
