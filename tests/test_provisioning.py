"""Unit and CLI entrypoint tests for AWS + Cloudflare deployment provisioning (`provision.py` & `deploy/`)."""

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


class DeploymentFilesStructureTests(unittest.TestCase):
    """Verify both local and production deployment files exist in `bookeeping_docs`."""

    def test_local_and_prod_compose_and_config_files_exist_in_bookeeping_docs(self) -> None:
        required_files = [
            REPO_ROOT / "docker-compose.yml",
            REPO_ROOT / "docker-compose.prod.yml",
            REPO_ROOT / "default.conf",
            REPO_ROOT / "Dockerfile.agy",
            REPO_ROOT / "agy_service.py",
            REPO_ROOT / "provision.py",
            REPO_ROOT / "provision.sh",
        ]
        for path in required_files:
            self.assertTrue(path.is_file(), f"Expected deployment file missing: {path}")

        local_compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("bookkeeping-app:", local_compose)
        self.assertIn("agy-ai:", local_compose)
        self.assertIn("tunnel:", local_compose)

        prod_compose = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
        self.assertIn("bookkeeping-app:", prod_compose)
        self.assertIn("agy-ai:", prod_compose)
        self.assertIn("Dockerfile.agy", prod_compose)
        self.assertIn("CLOUDFLARE_TUNNEL_TOKEN", prod_compose)
        self.assertIn(":/root/.gemini", prod_compose)

        app_root = REPO_ROOT.parent / "bookkeeping-tool"
        for moved_file in ("docker-compose.yml", "default.conf", "agy_service.py"):
            self.assertFalse(
                (app_root / moved_file).exists(),
                f"Deployment file {moved_file} should live in bookeeping_docs, not bookkeeping-tool",
            )



class ProvisioningConfigTests(unittest.TestCase):
    """Tests for reading and validating required AWS and Cloudflare environment variables."""

    REQUIRED_ENV = {
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "AWS_REGION": "me-central-1",
        "CLOUDFLARE_ACCOUNT_ID": "cf_account_1234567890abcdef",
        "CLOUDFLARE_API_TOKEN": "cf_token_secret_abcdef123456",
    }

    def test_from_env_loads_all_five_required_variables(self) -> None:
        from deploy.config import ProvisioningSettings

        with patch.dict(os.environ, self.REQUIRED_ENV, clear=True):
            settings = ProvisioningSettings.from_env()
            self.assertEqual(settings.aws_access_key_id, "AKIAIOSFODNN7EXAMPLE")
            self.assertEqual(
                settings.unwrap_aws_secret_access_key(),
                "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )
            self.assertEqual(settings.aws_region, "me-central-1")
            self.assertEqual(settings.cloudflare_account_id, "cf_account_1234567890abcdef")
            self.assertEqual(settings.unwrap_cloudflare_api_token(), "cf_token_secret_abcdef123456")

    def test_from_env_raises_missing_credentials_when_any_required_var_missing(self) -> None:
        from deploy.config import ProvisioningSettings
        from deploy.domain import ProvisioningError, ProvisioningErrorCode

        for missing_key in self.REQUIRED_ENV:
            partial_env = {k: v for k, v in self.REQUIRED_ENV.items() if k != missing_key}
            with patch.dict(os.environ, partial_env, clear=True):
                with self.assertRaises(ProvisioningError) as ctx:
                    ProvisioningSettings.from_env()
                self.assertEqual(ctx.exception.code, ProvisioningErrorCode.MISSING_CREDENTIALS)
                self.assertIn(missing_key, ctx.exception.message)

    def test_settings_repr_masks_secrets(self) -> None:
        from deploy.config import ProvisioningSettings

        with patch.dict(os.environ, self.REQUIRED_ENV, clear=True):
            settings = ProvisioningSettings.from_env()
            rendered = repr(settings)
            self.assertNotIn("wJalrXUtnFEMI", rendered)
            self.assertNotIn("cf_token_secret_abcdef123456", rendered)
            self.assertIn("***", rendered)

    def test_resolve_wrangler_oauth_token_reads_browser_login_config(self) -> None:
        from deploy.config import resolve_wrangler_oauth_token

        with tempfile.TemporaryDirectory() as tmp_home:
            home_path = Path(tmp_home)
            cfg_file = home_path / ".config" / ".wrangler" / "config" / "default.toml"
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            cfg_file.write_text(
                'oauth_token = "cf_oauth_browser_token_xyz"\nexpiration_time = "2026-11-03T05:00:00Z"\n',
                encoding="utf-8",
            )
            self.assertEqual(resolve_wrangler_oauth_token(home_path), "cf_oauth_browser_token_xyz")



class UserDataAndSigV4UnitTests(unittest.TestCase):
    """Tests for EC2 cloud-init UserData generation and AWS Signature V4 signing."""

    def test_build_ec2_user_data_includes_prod_compose_tunnel_token_and_agy_login_dir(self) -> None:
        from deploy.domain import build_ec2_user_data_script

        script = build_ec2_user_data_script(
            cloudflare_tunnel_token="eyJhIjoiTUNORUx9",
            agy_model="Gemini 4 Argon (High)",
            app_repo_url="https://github.com/lumenconsultancyae/bookkeeping-tool.git",
            docs_repo_url="https://github.com/lumenconsultancyae/bookeeping_docs.git",
        )
        self.assertTrue(script.startswith("#!/bin/bash"))
        self.assertIn("CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiTUNORUx9", script)
        self.assertIn("docker compose -f docker-compose.prod.yml up -d --build", script)
        self.assertIn(".agy_state/gemini", script)
        self.assertIn("docker exec -it bookkeeping-agy-ai agy", script)

    def test_aws_sigv4_headers_are_deterministic_and_include_authorization(self) -> None:
        from deploy.infrastructure import build_aws_sigv4_headers

        headers = build_aws_sigv4_headers(
            method="POST",
            host="ec2.me-central-1.amazonaws.com",
            region="me-central-1",
            service="ec2",
            payload="Action=DescribeRegions&Version=2016-11-15",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            amz_date="20261102T185000Z",
            session_token="AQoEXAMPLEH4aoAH0gNCAPyJxz4BlCFFxWNE1OPTgk5TthT",
        )
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20261102/me-central-1/ec2/aws4_request"))
        self.assertEqual(headers["X-Amz-Date"], "20261102T185000Z")
        self.assertEqual(headers["X-Amz-Security-Token"], "AQoEXAMPLEH4aoAH0gNCAPyJxz4BlCFFxWNE1OPTgk5TthT")


class CloudflareAndAwsProvisioningServiceTests(unittest.TestCase):
    """Tests for end-to-end Cloudflare Tunnel + AWS EC2 provisioning workflow with mocked HTTP adapters."""

    REQUIRED_ENV = {
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "AWS_REGION": "me-central-1",
        "CLOUDFLARE_ACCOUNT_ID": "cf_acc_999",
        "CLOUDFLARE_API_TOKEN": "cf_tok_999",
        "CLOUDFLARE_DOMAIN": "books.lumen.ae",
    }

    def test_cloudflare_client_creates_tunnel_configures_ingress_and_fetches_token(self) -> None:
        from deploy.infrastructure import CloudflareApiClient

        responses = [
            # 1. GET existing tunnels -> empty
            {"success": True, "result": []},
            # 2. POST create tunnel
            {"success": True, "result": {"id": "tun-uuid-1234", "name": "bookkeeping-prod"}},
            # 3. GET tunnel token
            {"success": True, "result": "eyJhIjoiTUNORUx_VE9LRU4ifQ=="},
            # 4. PUT tunnel configuration (ingress)
            {"success": True, "result": {"version": 1}},
            # 5. GET zones for domain
            {"success": True, "result": [{"id": "zone-uuid-5678", "name": "lumen.ae"}]},
            # 6. GET existing DNS records -> empty
            {"success": True, "result": []},
            # 7. POST create DNS CNAME record
            {"success": True, "result": {"id": "dns-1", "name": "books.lumen.ae"}},
        ]
        call_log: list[tuple[str, str, dict | None]] = []

        def fake_request(method: str, url: str, body: dict | None = None) -> dict:
            call_log.append((method, url, body))
            return responses.pop(0)

        client = CloudflareApiClient(
            account_id="cf_acc_999",
            api_token="cf_tok_999",
            transport=fake_request,
        )
        spec = client.ensure_tunnel(tunnel_name="bookkeeping-prod", hostname="books.lumen.ae")
        self.assertEqual(spec.tunnel_id, "tun-uuid-1234")
        self.assertEqual(spec.tunnel_token, "eyJhIjoiTUNORUx_VE9LRU4ifQ==")
        self.assertEqual(spec.public_hostname, "books.lumen.ae")
        self.assertEqual(spec.dns_record_id, "dns-1")

        # Verify ingress points to bookkeeping-app:80
        put_calls = [c for c in call_log if c[0] == "PUT"]
        self.assertEqual(len(put_calls), 1)
        ingress = put_calls[0][2]["config"]["ingress"]
        self.assertEqual(ingress[0]["hostname"], "books.lumen.ae")
        self.assertEqual(ingress[0]["service"], "http://bookkeeping-app:80")

    def test_cloudflare_client_creates_git_connected_pages_project_for_auto_deploy_on_push(self) -> None:
        from deploy.infrastructure import CloudflareApiClient

        responses = [
            # 1. GET existing pages projects -> not found (empty or 404 handled)
            {"success": True, "result": []},
            # 2. POST create pages project connected to GitHub repo
            {
                "success": True,
                "result": {
                    "name": "lumen-bookkeeping",
                    "subdomain": "lumen-bookkeeping.pages.dev",
                },
            },
        ]
        call_log: list[tuple[str, str, dict | None]] = []

        def fake_request(method: str, url: str, body: dict | None = None) -> dict:
            call_log.append((method, url, body))
            return responses.pop(0)

        client = CloudflareApiClient(
            account_id="cf_acc_999",
            api_token="cf_tok_999",
            transport=fake_request,
        )
        pages_spec = client.ensure_pages_project(
            project_name="lumen-bookkeeping",
            github_owner="lumenconsultancyae",
            github_repo="bookkeeping-tool",
            production_branch="main",
            backend_url="https://books.lumen.ae",
        )
        self.assertEqual(pages_spec.project_name, "lumen-bookkeeping")
        self.assertEqual(pages_spec.pages_url, "https://lumen-bookkeeping.pages.dev")
        post_calls = [c for c in call_log if c[0] == "POST"]
        self.assertEqual(len(post_calls), 1)
        self.assertEqual(post_calls[0][2]["source"]["type"], "github")
        self.assertEqual(post_calls[0][2]["source"]["config"]["repo_name"], "bookkeeping-tool")
        self.assertTrue(post_calls[0][2]["source"]["config"]["deployments_enabled"])


    def test_aws_ec2_client_provisions_sg_keypair_and_instance_idempotently(self) -> None:
        from deploy.infrastructure import AwsEc2Client

        xml_responses = [
            # 1. DescribeImages
            """<?xml version="1.0" encoding="UTF-8"?>
            <DescribeImagesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <imagesSet>
                    <item>
                        <imageId>ami-0123456789abcdef0</imageId>
                        <creationDate>2026-10-01T00:00:00.000Z</creationDate>
                    </item>
                </imagesSet>
            </DescribeImagesResponse>""",
            # 2. DescribeSecurityGroups -> empty
            """<?xml version="1.0" encoding="UTF-8"?>
            <DescribeSecurityGroupsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <securityGroupInfo/>
            </DescribeSecurityGroupsResponse>""",
            # 3. CreateSecurityGroup
            """<?xml version="1.0" encoding="UTF-8"?>
            <CreateSecurityGroupResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <groupId>sg-0abc123def456</groupId>
            </CreateSecurityGroupResponse>""",
            # 4. AuthorizeSecurityGroupIngress
            """<?xml version="1.0" encoding="UTF-8"?>
            <AuthorizeSecurityGroupIngressResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <return>true</return>
            </AuthorizeSecurityGroupIngressResponse>""",
            # 5. DescribeKeyPairs -> empty
            """<?xml version="1.0" encoding="UTF-8"?>
            <DescribeKeyPairsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <keySet/>
            </DescribeKeyPairsResponse>""",
            # 6. CreateKeyPair
            """<?xml version="1.0" encoding="UTF-8"?>
            <CreateKeyPairResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <keyName>bookkeeping-agy-key</keyName>
                <keyMaterial>-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----</keyMaterial>
            </CreateKeyPairResponse>""",
            # 7. DescribeInstances -> empty
            """<?xml version="1.0" encoding="UTF-8"?>
            <DescribeInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <reservationSet/>
            </DescribeInstancesResponse>""",
            # 8. RunInstances
            """<?xml version="1.0" encoding="UTF-8"?>
            <RunInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
                <instancesSet>
                    <item>
                        <instanceId>i-0987654321fedcba0</instanceId>
                        <ipAddress>3.29.100.55</ipAddress>
                    </item>
                </instancesSet>
            </RunInstancesResponse>""",
        ]

        def fake_ec2_transport(params: dict[str, str]) -> str:
            return xml_responses.pop(0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            key_out = Path(tmp_dir) / "bookkeeping-agy-key.pem"
            ec2 = AwsEc2Client(
                access_key_id="AKIAIOSFODNN7EXAMPLE",
                secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                region="me-central-1",
                transport=fake_ec2_transport,
            )
            instance = ec2.provision_instance(
                instance_name="bookkeeping-agy-prod",
                instance_type="t3.small",
                security_group_name="bookkeeping-agy-sg",
                key_name="bookkeeping-agy-key",
                key_output_path=key_out,
                user_data_script="#!/bin/bash\necho hello\n",
            )
            self.assertEqual(instance.instance_id, "i-0987654321fedcba0")
            self.assertEqual(instance.public_ip, "3.29.100.55")
            self.assertEqual(instance.ami_id, "ami-0123456789abcdef0")
            self.assertEqual(instance.security_group_id, "sg-0abc123def456")
            self.assertTrue(key_out.is_file())
            self.assertIn("BEGIN RSA PRIVATE KEY", key_out.read_text(encoding="utf-8"))

    def test_provisioning_service_dry_run_validates_env_and_outputs_plan(self) -> None:
        from deploy.config import ProvisioningSettings
        from deploy.service import ProvisioningService

        env = dict(self.REQUIRED_ENV)
        env["PROVISION_DRY_RUN"] = "true"
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, env, clear=True):
                settings = ProvisioningSettings.from_env(artifacts_dir=Path(tmp_dir))
                service = ProvisioningService(settings=settings)
                result = service.run()
                self.assertTrue(result.dry_run)
                self.assertEqual(result.region, "me-central-1")
                self.assertIn("docker exec -it bookkeeping-agy-ai agy", result.agy_login_command)

    def test_provision_cli_scripts_execute_dry_run_and_report_missing_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                **self.REQUIRED_ENV,
                "PROVISION_ARTIFACTS_DIR": tmp_dir,
            }
            proc_ok = subprocess.run(
                [str(REPO_ROOT / "provision.sh"), "--dry-run"],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc_ok.returncode, 0, proc_ok.stderr)
            self.assertIn("bookkeeping-agy-ai", proc_ok.stdout)

            proc_fail = subprocess.run(
                [str(REPO_ROOT / "provision.sh"), "--dry-run"],
                cwd=str(REPO_ROOT),
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "PROVISION_DISABLE_LOCAL_CACHE": "1",
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc_fail.returncode, 1)
            err_payload = json.loads(proc_fail.stderr)
            self.assertEqual(err_payload["error"]["code"], "missing_credentials")
            for key in (
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_REGION",
                "CLOUDFLARE_ACCOUNT_ID",
                "CLOUDFLARE_API_TOKEN",
            ):
                self.assertIn(key, err_payload["error"]["message"])

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

        # 1. ProvisioningError.to_dict with and without context
        err_no_ctx = ProvisioningError(ProvisioningErrorCode.BOOTSTRAP_ERROR, "Failed boot")
        self.assertEqual(err_no_ctx.to_dict(), {"error": {"code": "bootstrap_error", "message": "Failed boot"}})
        err_ctx = ProvisioningError(
            ProvisioningErrorCode.AWS_API_ERROR, "AWS fail", context={"status": "500"}
        )
        self.assertEqual(err_ctx.to_dict()["error"]["context"], {"status": "500"})

        # 2. resolve_aws_login_cache_credentials branches
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

        # 3. ProvisioningService.run() live (non-dry-run) branch with injected fake clients
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

            # 4. provision.main() in-process execution (dry-run & error path)
            with patch.dict(os.environ, {**env, "PROVISION_ARTIFACTS_DIR": tmp_dir}, clear=True):
                rc_ok = provision.main(["--dry-run"])
                self.assertEqual(rc_ok, 0)
            with patch.dict(os.environ, {}, clear=True):
                rc_err = provision.main(["--dry-run"])
                self.assertEqual(rc_err, 1)

    def test_cloudflare_and_ec2_idempotent_existing_resource_and_error_branches(self) -> None:
        from deploy.domain import ProvisioningError
        from deploy.infrastructure import AwsEc2Client, CloudflareApiClient

        # 1. Cloudflare existing tunnel, existing DNS record PUT, existing Pages project PATCH + custom_domain
        cf_responses = [
            # ensure_tunnel: existing tunnel found
            {"success": True, "result": [{"id": "tun-existing"}]},
            # get token
            {"success": True, "result": "tok-existing"},
            # put ingress
            {"success": True, "result": {"version": 2}},
            # get existing DNS record -> found
            {"success": True, "result": [{"id": "dns-existing"}]},
            # update existing DNS record via PUT
            {"success": True, "result": {"id": "dns-existing"}},
            # ensure_pages_project: existing project found
            {"success": True, "result": [{"name": "lumen-bookkeeping", "subdomain": "lumen-bookkeeping.pages.dev"}]},
            # PATCH project
            {"success": True, "result": {"name": "lumen-bookkeeping", "subdomain": "lumen-bookkeeping.pages.dev"}},
            # POST custom domain
            {"success": True, "result": {"name": "books.lumen.ae"}},
            # POST pages dns cname
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

        # Cloudflare API failure branch
        err_client = CloudflareApiClient(
            account_id="acc",
            api_token="tok",
            transport=lambda m, u, b=None: {"success": False, "errors": [{"message": "Bad token"}]},
        )
        with self.assertRaises(ProvisioningError):
            err_client.ensure_tunnel(tunnel_name="fail")

        # 2. AwsEc2Client existing SG, existing KeyPair, existing running instance, and error branches
        ec2_xml = [
            # DescribeImages
            """<DescribeImagesResponse><imagesSet><item><imageId>ami-exist</imageId><creationDate>2026-10-01</creationDate></item></imagesSet></DescribeImagesResponse>""",
            # DescribeSecurityGroups -> existing
            """<DescribeSecurityGroupsResponse><securityGroupInfo><item><groupId>sg-exist</groupId></item></securityGroupInfo></DescribeSecurityGroupsResponse>""",
            # DescribeKeyPairs -> existing
            """<DescribeKeyPairsResponse><keySet><item><keyName>key-exist</keyName></item></keySet></DescribeKeyPairsResponse>""",
            # DescribeInstances -> existing running
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

            # Invalid XML and empty AMI branches
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
        import io
        import urllib.error
        import urllib.request
        from deploy.domain import ProvisioningError
        from deploy.infrastructure import AwsEc2Client, CloudflareApiClient

        # 1. Cloudflare _default_http_transport success, HTTPError, and URLError
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

        # 2. Zone auto-discovery in _ensure_dns_cname & _ensure_pages_dns_cname + error tolerance
        zone_cf_responses = [
            {"success": True, "result": [{"id": "z-auto", "name": "lumen.ae"}]},
            {"success": True, "result": []},
            {"success": True, "result": {"id": "rec-created"}},
            {"success": True, "result": [{"id": "z-auto", "name": "lumen.ae"}]},
            {"success": True, "result": {"id": "pages-rec-created"}},
            # No matching zone -> returns None cleanly
            {"success": True, "result": [{"id": "z-other", "name": "other.com"}]},
            {"success": True, "result": [{"id": "z-other", "name": "other.com"}]},
            # Tunnel without hostname
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

        # 3. AwsEc2Client _default_ec2_transport success, HTTPError, URLError, and XML namespace stripping
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
