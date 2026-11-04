"""Extended unit and CLI entrypoint tests for AWS + Cloudflare deployment provisioning (`provision.py` & `deploy/`)."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent


class CloudflareAndAwsExtendedProvisioningTests(unittest.TestCase):
    """Extended unit tests for provision.py CLI, idempotent existing resources, and error branches."""

    REQUIRED_ENV = {
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "AWS_REGION": "me-central-1",
        "CLOUDFLARE_ACCOUNT_ID": "cf_acc_999",
        "CLOUDFLARE_API_TOKEN": "cf_tok_999",
        "CLOUDFLARE_DOMAIN": "books.lumen.ae",
    }

    def test_provision_py_main_and_live_provisioning_service_branches(self) -> None:
        from deploy.config import ProvisioningSettings, resolve_aws_login_cache_credentials
        from deploy.domain import (
            CloudflarePagesSpec,
            CloudflareTunnelSpec,
            Ec2InstanceSpec,
            ProvisioningError,
            ProvisioningErrorCode,
        )
        from deploy.service import ProvisioningService
        import provision

        err_no_ctx = ProvisioningError(ProvisioningErrorCode.BOOTSTRAP_ERROR, "Failed boot")
        self.assertEqual(err_no_ctx.to_dict(), {"error": {"code": "bootstrap_error", "message": "Failed boot"}})
        err_ctx = ProvisioningError(
            ProvisioningErrorCode.AWS_API_ERROR, "AWS fail", context={"status": "500"}
        )
        self.assertEqual(err_ctx.to_dict()["error"]["context"], {"status": "500"})

        with tempfile.TemporaryDirectory() as tmp_home:
            home_path = Path(tmp_home)
            cache_dir = home_path / ".aws" / "login" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / "01_corrupt.json").write_text("{bad json", encoding="utf-8")
            (cache_dir / "02_valid.json").write_text(
                json.dumps(
                    {
                        "signInRegion": "me-central-1",
                        "accessToken": {
                            "accessKeyId": "ASIA123",
                            "secretAccessKey": "SECRET456",
                            "sessionToken": "TOKEN789",
                        },
                    }
                ),
                encoding="utf-8",
            )
            creds = resolve_aws_login_cache_credentials(home_path)
            self.assertIsNotNone(creds)
            self.assertEqual(creds["AWS_ACCESS_KEY_ID"], "ASIA123")
            self.assertEqual(creds["AWS_SESSION_TOKEN"], "TOKEN789")
            self.assertEqual(creds["AWS_REGION"], "me-central-1")

        with tempfile.TemporaryDirectory() as tmp_dir:
            env = dict(self.REQUIRED_ENV)
            env["AGY_API_SECRET"] = "sec-xyz"
            settings = ProvisioningSettings.from_env(env, artifacts_dir=Path(tmp_dir))
            self.assertEqual(settings.unwrap_agy_api_secret(), "sec-xyz")
            self.assertIsNone(settings.unwrap_aws_session_token())

            fake_cf = MagicMock()
            fake_cf.ensure_tunnel.return_value = CloudflareTunnelSpec(
                tunnel_id="tun-live-1",
                tunnel_name="bookkeeping-prod",
                tunnel_token="tok-live-1",
                public_hostname="books.lumen.ae",
                dns_record_id="dns-live-1",
            )
            fake_cf.ensure_pages_project.return_value = CloudflarePagesSpec(
                project_name="lumen-bookkeeping",
                pages_url="https://lumen-bookkeeping.pages.dev",
                github_owner="lumenconsultancyae",
                github_repo="bookkeeping-tool",
                production_branch="main",
            )
            fake_ec2 = MagicMock()
            fake_ec2.provision_instance.return_value = Ec2InstanceSpec(
                instance_id="i-live123",
                public_ip="54.1.2.3",
                ami_id="ami-live",
                security_group_id="sg-live",
                key_name="bookkeeping-agy-key",
            )

            svc = ProvisioningService(
                settings=settings, cloudflare_client=fake_cf, ec2_client=fake_ec2
            )
            res = svc.run()
            self.assertFalse(res.dry_run)
            self.assertEqual(res.public_url, "https://books.lumen.ae")
            self.assertEqual(res.pages_url, "https://lumen-bookkeeping.pages.dev")
            self.assertIn("54.1.2.3", res.ssh_command)
            summary_path = Path(tmp_dir) / "provisioning_result.json"
            self.assertTrue(summary_path.is_file())

            with patch.dict(os.environ, {**env, "PROVISION_ARTIFACTS_DIR": tmp_dir}, clear=True):
                rc_ok = provision.main(["--dry-run"])
                self.assertEqual(rc_ok, 0)
            with patch.dict(os.environ, {"PROVISION_DISABLE_LOCAL_CACHE": "1"}, clear=True):
                rc_err = provision.main(["--dry-run"])
                self.assertEqual(rc_err, 1)

    def test_cloudflare_and_ec2_idempotent_existing_resource_and_error_branches(self) -> None:
        from deploy.domain import ProvisioningError
        from deploy.infrastructure import AwsEc2Client, CloudflareApiClient

        cf_responses = [
            {"success": True, "result": [{"id": "tun-existing"}]},
            {"success": True, "result": "tok-existing"},
            {"success": True, "result": {"version": 2}},
            {"success": True, "result": [{"id": "dns-existing"}]},
            {"success": True, "result": {"id": "dns-existing"}},
            {"success": True, "result": [{"name": "lumen-bookkeeping", "subdomain": "lumen-bookkeeping.pages.dev"}]},
            {"success": True, "result": {"name": "lumen-bookkeeping", "subdomain": "lumen-bookkeeping.pages.dev"}},
            {"success": True, "result": {"name": "books.lumen.ae"}},
            {"success": True, "result": {"id": "dns-pages-1"}},
        ]
        cf_client = CloudflareApiClient(
            account_id="acc",
            api_token="tok",
            transport=lambda m, u, b=None: cf_responses.pop(0),
        )
        tun = cf_client.ensure_tunnel(
            tunnel_name="bookkeeping-prod", hostname="books.lumen.ae", zone_id="zone-explicit"
        )
        self.assertEqual(tun.tunnel_id, "tun-existing")
        self.assertEqual(tun.dns_record_id, "dns-existing")

        pages = cf_client.ensure_pages_project(
            project_name="lumen-bookkeeping",
            backend_url="https://books.lumen.ae",
            agy_api_secret="sec",
            custom_domain="books.lumen.ae",
            zone_id="zone-explicit",
        )
        self.assertEqual(pages.pages_url, "https://books.lumen.ae")

        err_client = CloudflareApiClient(
            account_id="acc",
            api_token="tok",
            transport=lambda m, u, b=None: {"success": False, "errors": [{"message": "Bad token"}]},
        )
        with self.assertRaises(ProvisioningError):
            err_client.ensure_tunnel(tunnel_name="fail")

        ec2_xml = [
            """<DescribeImagesResponse><imagesSet><item><imageId>ami-exist</imageId><creationDate>2026-10-01</creationDate></item></imagesSet></DescribeImagesResponse>""",
            """<DescribeSecurityGroupsResponse><securityGroupInfo><item><groupId>sg-exist</groupId></item></securityGroupInfo></DescribeSecurityGroupsResponse>""",
            """<DescribeKeyPairsResponse><keySet><item><keyName>key-exist</keyName></item></keySet></DescribeKeyPairsResponse>""",
            """<DescribeInstancesResponse><reservationSet><item><instancesSet><item><instanceId>i-exist</instanceId><ipAddress>1.2.3.4</ipAddress></item></instancesSet></item></reservationSet></DescribeInstancesResponse>""",
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            ec2 = AwsEc2Client(
                access_key_id="AKIA",
                secret_access_key="SECRET",
                region="us-east-1",
                transport=lambda p: ec2_xml.pop(0),
            )
            spec = ec2.provision_instance(
                instance_name="prod",
                instance_type="t3.small",
                security_group_name="sg",
                key_name="key-exist",
                key_output_path=Path(tmp_dir) / "k.pem",
                user_data_script="#!/bin/bash",
            )
            self.assertEqual(spec.instance_id, "i-exist")
            self.assertEqual(spec.public_ip, "1.2.3.4")

            bad_xml_ec2 = AwsEc2Client(
                access_key_id="AKIA",
                secret_access_key="SECRET",
                region="us-east-1",
                transport=lambda p: "<unclosed",
            )
            with self.assertRaises(ProvisioningError):
                bad_xml_ec2.resolve_ubuntu_ami()

            no_ami_ec2 = AwsEc2Client(
                access_key_id="AKIA",
                secret_access_key="SECRET",
                region="us-east-1",
                transport=lambda p: "<DescribeImagesResponse><imagesSet/></DescribeImagesResponse>",
            )
            with self.assertRaises(ProvisioningError):
                no_ami_ec2.resolve_ubuntu_ami()

    def test_urllib_default_transports_zone_discovery_and_xml_namespaces(self) -> None:
        import urllib.error
        import urllib.request
        from deploy.domain import ProvisioningError
        from deploy.infrastructure import AwsEc2Client, CloudflareApiClient

        cf = CloudflareApiClient(account_id="acc", api_token="tok")

        class FakeHttpResp:
            def __init__(self, body: str) -> None:
                self._body = body.encode("utf-8")

            def read(self) -> bytes:
                return self._body

            def __enter__(self) -> "FakeHttpResp":
                return self

            def __exit__(self, *args: object) -> None:
                pass

        with patch.object(urllib.request, "urlopen", return_value=FakeHttpResp('{"success": true, "result": {"id": "1"}}')):
            res = cf._default_http_transport("POST", "https://api.cloudflare.com/client/v4/test", {"a": 1})
            self.assertTrue(res["success"])

        http_err = urllib.error.HTTPError(
            url="https://api.cloudflare.com/client/v4/test",
            code=403,
            msg="Forbidden",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"errors":[{"message":"denied"}]}'),
        )
        with patch.object(urllib.request, "urlopen", side_effect=http_err):
            with self.assertRaises(ProvisioningError):
                cf._default_http_transport("GET", "https://api.cloudflare.com/client/v4/test")

        with patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(ProvisioningError):
                cf._default_http_transport("GET", "https://api.cloudflare.com/client/v4/test")

        zone_cf_responses = [
            {"success": True, "result": [{"id": "z-auto", "name": "lumen.ae"}]},
            {"success": True, "result": []},
            {"success": True, "result": {"id": "rec-created"}},
            {"success": True, "result": [{"id": "z-auto", "name": "lumen.ae"}]},
            {"success": True, "result": {"id": "pages-rec-created"}},
            {"success": True, "result": [{"id": "z-other", "name": "other.com"}]},
            {"success": True, "result": [{"id": "z-other", "name": "other.com"}]},
            {"success": True, "result": [{"id": "tun-nohost"}]},
            {"success": True, "result": "tok-nohost"},
            {"success": True, "result": {"version": 1}},
        ]
        zone_cf = CloudflareApiClient(
            account_id="acc",
            api_token="tok",
            transport=lambda m, u, b=None: zone_cf_responses.pop(0),
        )
        cname_id = zone_cf._ensure_dns_cname(tunnel_id="tun-1", hostname="books.lumen.ae")
        self.assertEqual(cname_id, "rec-created")
        pages_cname_id = zone_cf._ensure_pages_dns_cname(
            pages_subdomain="lumen.pages.dev", hostname="books.lumen.ae"
        )
        self.assertEqual(pages_cname_id, "pages-rec-created")
        self.assertIsNone(zone_cf._ensure_dns_cname(tunnel_id="tun-1", hostname="books.lumen.ae"))
        self.assertIsNone(
            zone_cf._ensure_pages_dns_cname(pages_subdomain="lumen.pages.dev", hostname="books.lumen.ae")
        )
        tun_nohost = zone_cf.ensure_tunnel(tunnel_name="nohost")
        self.assertIsNone(tun_nohost.public_hostname)

        ec2 = AwsEc2Client(
            access_key_id="AKIA",
            secret_access_key="SECRET",
            region="me-central-1",
            session_token="SESS",
        )
        ns_xml = '<DescribeImagesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/"><imagesSet><item><imageId>ami-ns</imageId><creationDate>2026-10-01</creationDate></item></imagesSet></DescribeImagesResponse>'
        with patch.object(urllib.request, "urlopen", return_value=FakeHttpResp(ns_xml)):
            self.assertEqual(ec2.resolve_ubuntu_ami(), "ami-ns")

        ec2_http_err = urllib.error.HTTPError(
            url="https://ec2.me-central-1.amazonaws.com/",
            code=400,
            msg="Bad Request",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b"<Response><Errors><Error><Message>Invalid</Message></Error></Errors></Response>"),
        )
        with patch.object(urllib.request, "urlopen", side_effect=ec2_http_err):
            with self.assertRaises(ProvisioningError):
                ec2._default_ec2_transport({"Action": "DescribeImages"})

        with patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError("net down")):
            with self.assertRaises(ProvisioningError):
                ec2._default_ec2_transport({"Action": "DescribeImages"})

    def test_both_repositories_enforce_gitignore_dockerignore_and_zero_tracked_junk(self) -> None:
        app_root = REPO_ROOT.parent / "bookkeeping-tool"
        for repo in (REPO_ROOT, app_root):
            self.assertTrue((repo / ".gitignore").is_file(), f"Missing .gitignore in {repo}")
            self.assertTrue((repo / ".dockerignore").is_file(), f"Missing .dockerignore in {repo}")

        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=str(app_root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        self.assertFalse(any(f.startswith("node_modules/") for f in tracked), "node_modules must not be tracked")
        self.assertFalse(any(f.startswith("docs/") for f in tracked), "duplicate docs/ must not be tracked in app repo")
        self.assertFalse(any(f.startswith("patch_") for f in tracked), "patch_*.py scratch scripts must not be tracked")
        self.assertFalse(any(f.startswith("test_") for f in tracked), "scratch test_* files must not be tracked in app repo")


if __name__ == "__main__":
    unittest.main()
