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



if __name__ == "__main__":
    unittest.main()
