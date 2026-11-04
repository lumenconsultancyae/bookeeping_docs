"""Infrastructure adapters for Cloudflare REST API v4 and AWS EC2 Query API (SigV4)."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from deploy.domain import (
    CloudflarePagesSpec,
    CloudflareTunnelSpec,
    Ec2InstanceSpec,
    ProvisioningError,
    ProvisioningErrorCode,
)

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
EC2_API_VERSION = "2016-11-15"
CANONICAL_UBUNTU_OWNER_ID = "099720109477"


class CloudflareApiClient:
    """Adapter for Cloudflare REST API v4 Zero Trust Tunnels and DNS records."""

    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        transport: Callable[[str, str, dict | None], dict] | None = None,
    ) -> None:
        self._account_id = account_id
        self._api_token = api_token
        self._transport = transport or self._default_http_transport

    def _default_http_transport(self, method: str, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "wrangler/3.114.17",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"success": True, "result": None}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise ProvisioningError(
                ProvisioningErrorCode.CLOUDFLARE_API_ERROR,
                f"Cloudflare API HTTP {exc.code} on {method} {url}",
                context={"status_code": str(exc.code), "detail": err_body[:300]},
            ) from exc
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ProvisioningError(
                ProvisioningErrorCode.CLOUDFLARE_API_ERROR,
                f"Cloudflare API communication error on {method} {url}",
            ) from exc

    def _request(self, method: str, path: str, body: dict | None = None) -> object:
        url = f"{CLOUDFLARE_API_BASE}{path}"
        payload = self._transport(method, url, body)
        if not payload.get("success", False):
            errors = payload.get("errors") or []
            first_msg = errors[0].get("message", "Unknown Cloudflare error") if errors else "Request failed"
            raise ProvisioningError(
                ProvisioningErrorCode.CLOUDFLARE_API_ERROR,
                f"Cloudflare API rejected {method} {path}: {first_msg}",
            )
        return payload.get("result")

    def ensure_tunnel(
        self,
        *,
        tunnel_name: str,
        hostname: str | None = None,
        zone_id: str | None = None,
    ) -> CloudflareTunnelSpec:
        """Find or create a Named Cloudflare Tunnel, configure ingress to `bookkeeping-app:80`, and wire DNS."""
        encoded_name = urllib.parse.quote(tunnel_name)
        existing = self._request(
            "GET",
            f"/accounts/{self._account_id}/cfd_tunnel?name={encoded_name}&is_deleted=false",
        )
        if isinstance(existing, list) and existing:
            tunnel_id = str(existing[0]["id"])
        else:
            created = self._request(
                "POST",
                f"/accounts/{self._account_id}/cfd_tunnel",
                {"name": tunnel_name, "config_src": "cloudflare"},
            )
            if not isinstance(created, dict) or "id" not in created:
                raise ProvisioningError(
                    ProvisioningErrorCode.CLOUDFLARE_API_ERROR,
                    "Cloudflare tunnel creation response did not include a tunnel ID.",
                )
            tunnel_id = str(created["id"])

        token_res = self._request("GET", f"/accounts/{self._account_id}/cfd_tunnel/{tunnel_id}/token")
        tunnel_token = str(token_res or "")
        if not tunnel_token:
            raise ProvisioningError(
                ProvisioningErrorCode.CLOUDFLARE_API_ERROR,
                "Cloudflare tunnel token response was empty.",
            )

        ingress_rules: list[dict[str, str]] = []
        if hostname:
            ingress_rules.append({"hostname": hostname, "service": "http://bookkeeping-app:80"})
        ingress_rules.append({"service": "http://bookkeeping-app:80"})

        self._request(
            "PUT",
            f"/accounts/{self._account_id}/cfd_tunnel/{tunnel_id}/configurations",
            {"config": {"ingress": ingress_rules}},
        )

        dns_record_id: str | None = None
        if hostname:
            dns_record_id = self._ensure_dns_cname(
                tunnel_id=tunnel_id,
                hostname=hostname,
                explicit_zone_id=zone_id,
            )

        return CloudflareTunnelSpec(
            tunnel_id=tunnel_id,
            tunnel_name=tunnel_name,
            tunnel_token=tunnel_token,
            public_hostname=hostname,
            dns_record_id=dns_record_id,
        )

    def _ensure_dns_cname(
        self,
        *,
        tunnel_id: str,
        hostname: str,
        explicit_zone_id: str | None = None,
    ) -> str | None:
        resolved_zone_id = explicit_zone_id
        if not resolved_zone_id:
            zones = self._request("GET", "/zones")
            if isinstance(zones, list):
                for z in zones:
                    z_name = str(z.get("name") or "")
                    if z_name and (hostname == z_name or hostname.endswith("." + z_name)):
                        resolved_zone_id = str(z["id"])
                        break

        if not resolved_zone_id:
            return None

        target = f"{tunnel_id}.cfargotunnel.com"
        encoded_host = urllib.parse.quote(hostname)
        try:
            records = self._request(
                "GET",
                f"/zones/{resolved_zone_id}/dns_records?type=CNAME&name={encoded_host}",
            )
        except ProvisioningError:
            return None
        record_payload = {
            "type": "CNAME",
            "name": hostname,
            "content": target,
            "proxied": True,
            "ttl": 1,
        }

        if isinstance(records, list) and records:
            rec_id = str(records[0]["id"])
            try:
                self._request("PUT", f"/zones/{resolved_zone_id}/dns_records/{rec_id}", record_payload)
            except ProvisioningError:
                return rec_id
            return rec_id

        try:
            created_rec = self._request("POST", f"/zones/{resolved_zone_id}/dns_records", record_payload)
        except ProvisioningError:
            return None
        if isinstance(created_rec, dict) and "id" in created_rec:
            return str(created_rec["id"])
        return None

    def ensure_pages_project(
        self,
        *,
        project_name: str,
        github_owner: str = "lumenconsultancyae",
        github_repo: str = "bookkeeping-tool",
        production_branch: str = "main",
        backend_url: str | None = None,
        agy_api_secret: str | None = None,
        custom_domain: str | None = None,
        zone_id: str | None = None,
    ) -> CloudflarePagesSpec:
        """Create or update a GitHub-connected Cloudflare Pages project that auto-deploys on `git push`."""
        projects = self._request("GET", f"/accounts/{self._account_id}/pages/projects")
        existing_project: dict | None = None
        if isinstance(projects, list):
            for proj in projects:
                if isinstance(proj, dict) and proj.get("name") == project_name:
                    existing_project = proj
                    break

        env_vars = {}
        if backend_url:
            env_vars["AGY_BACKEND_URL"] = {"type": "plain_text", "value": backend_url}
        if agy_api_secret:
            env_vars["AGY_API_SECRET"] = {"type": "secret_text", "value": agy_api_secret}

        project_payload: dict[str, object] = {
            "name": project_name,
            "production_branch": production_branch,
            "source": {
                "type": "github",
                "config": {
                    "owner": github_owner,
                    "repo_name": github_repo,
                    "production_branch": production_branch,
                    "pr_comments_enabled": True,
                    "deployments_enabled": True,
                    "production_deployments_enabled": True,
                },
            },
            "build_config": {
                "build_command": "",
                "destination_dir": ".",
                "root_dir": "",
            },
        }
        if env_vars:
            project_payload["deployment_configs"] = {
                "production": {"env_vars": env_vars},
                "preview": {"env_vars": env_vars},
            }

        fallback_payload: dict[str, object] = {
            "name": project_name,
            "production_branch": production_branch,
        }
        if env_vars:
            fallback_payload["deployment_configs"] = {
                "production": {"env_vars": env_vars},
                "preview": {"env_vars": env_vars},
            }

        if existing_project is None:
            try:
                result = self._request(
                    "POST",
                    f"/accounts/{self._account_id}/pages/projects",
                    project_payload,
                )
            except ProvisioningError:
                result = self._request(
                    "POST",
                    f"/accounts/{self._account_id}/pages/projects",
                    fallback_payload,
                )
        else:
            try:
                result = self._request(
                    "PATCH",
                    f"/accounts/{self._account_id}/pages/projects/{project_name}",
                    project_payload,
                )
            except ProvisioningError:
                result = existing_project

        subdomain = (
            str(result.get("subdomain"))
            if isinstance(result, dict) and result.get("subdomain")
            else f"{project_name}.pages.dev"
        )
        if custom_domain:
            try:
                self._request(
                    "POST",
                    f"/accounts/{self._account_id}/pages/projects/{project_name}/domains",
                    {"name": custom_domain},
                )
            except ProvisioningError:
                pass
            self._ensure_pages_dns_cname(
                pages_subdomain=subdomain,
                hostname=custom_domain,
                explicit_zone_id=zone_id,
            )

        return CloudflarePagesSpec(
            project_name=project_name,
            pages_url=f"https://{custom_domain}" if custom_domain else f"https://{subdomain}",
            github_owner=github_owner,
            github_repo=github_repo,
            production_branch=production_branch,
        )

    def _ensure_pages_dns_cname(
        self,
        *,
        pages_subdomain: str,
        hostname: str,
        explicit_zone_id: str | None = None,
    ) -> str | None:
        resolved_zone_id = explicit_zone_id
        if not resolved_zone_id:
            try:
                zones = self._request("GET", "/zones")
            except ProvisioningError:
                zones = None
            if isinstance(zones, list):
                for z in zones:
                    z_name = str(z.get("name") or "")
                    if z_name and (hostname == z_name or hostname.endswith("." + z_name)):
                        resolved_zone_id = str(z["id"])
                        break
        if not resolved_zone_id:
            return None
        record_payload = {
            "type": "CNAME",
            "name": hostname,
            "content": pages_subdomain,
            "proxied": True,
            "ttl": 1,
        }
        try:
            created = self._request("POST", f"/zones/{resolved_zone_id}/dns_records", record_payload)
            if isinstance(created, dict) and "id" in created:
                return str(created["id"])
        except ProvisioningError:
            return None
        return None
