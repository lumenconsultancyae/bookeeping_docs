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
from unittest.mock import create_autospec, patch

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

            from deploy.infrastructure import AwsEc2Client, CloudflareApiClient

            fake_cf = create_autospec(CloudflareApiClient, instance=True)
            fake_cf.ensure_tunnel.return_value = CloudflareTunnelSpec(
                tunnel_id="tun-live-1",
                tunnel_name="bookkeeping-prod",
                tunnel_token="tok-live-1",
                public_hostname="books.lumen.ae",
                dns_record_id="dns-live-1",
            )
            fake_cf.ensure_d1_database.return_value = "d1-live-uuid"
            fake_cf.ensure_r2_bucket.return_value = "lumen-bookkeeping-attachments"
            fake_cf.ensure_pages_project.return_value = CloudflarePagesSpec(
                project_name="lumen-bookkeeping",
                pages_url="https://lumen-bookkeeping.pages.dev",
                github_owner="lumenconsultancyae",
                github_repo="bookkeeping-tool",
                production_branch="main",
            )
            fake_ec2 = create_autospec(AwsEc2Client, instance=True)
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
            fake_cf.ensure_d1_database.assert_called_once_with(db_name="lumen-bookkeeping-db")
            fake_cf.ensure_r2_bucket.assert_called_once_with(
                bucket_name="lumen-bookkeeping-attachments"
            )
            fake_cf.ensure_pages_project.assert_called_once_with(
                project_name="lumen-bookkeeping",
                backend_url="https://books.lumen.ae",
                agy_api_secret="sec-xyz",
                d1_database_id="d1-live-uuid",
                r2_bucket_name="lumen-bookkeeping-attachments",
            )
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

    def test_cloudflare_d1_and_r2_provisioning_and_server_tenant_isolation(self) -> None:
        import agy_service
        from deploy.domain import ProvisioningError
        from deploy.infrastructure import CloudflareApiClient

        cf_responses = [
            {"success": True, "result": []},
            {"success": True, "result": {"uuid": "d1-uuid-777", "name": "lumen-bookkeeping-db"}},
            {"success": True, "result": [{"uuid": "d1-existing-888", "name": "lumen-bookkeeping-db"}]},
            {"success": True, "result": []},
            {"success": True, "result": {"name": "lumen-bookkeeping-db"}},
            {"success": True, "result": {"buckets": []}},
            {"success": True, "result": {"name": "lumen-bookkeeping-attachments"}},
            {"success": True, "result": {"buckets": [{"name": "lumen-bookkeeping-attachments"}]}},
            {"success": True, "result": []},
            {"success": True, "result": {"name": "lumen-bookkeeping", "subdomain": "lumen-bookkeeping.pages.dev"}},
        ]
        call_log: list[tuple[str, str, dict | None]] = []

        def fake_cf_transport(method: str, url: str, body: dict | None = None) -> dict:
            call_log.append((method, url, body))
            return cf_responses.pop(0)

        cf_client = CloudflareApiClient(account_id="acc", api_token="tok", transport=fake_cf_transport)
        d1_id = cf_client.ensure_d1_database(db_name="lumen-bookkeeping-db")
        self.assertEqual(d1_id, "d1-uuid-777")
        self.assertEqual(cf_client.ensure_d1_database(db_name="lumen-bookkeeping-db"), "d1-existing-888")
        with self.assertRaises(ProvisioningError):
            cf_client.ensure_d1_database(db_name="lumen-bookkeeping-db")
        r2_name = cf_client.ensure_r2_bucket(bucket_name="lumen-bookkeeping-attachments")
        self.assertEqual(r2_name, "lumen-bookkeeping-attachments")
        self.assertEqual(
            cf_client.ensure_r2_bucket(bucket_name="lumen-bookkeeping-attachments"),
            "lumen-bookkeeping-attachments",
        )
        pages_spec = cf_client.ensure_pages_project(
            project_name="lumen-bookkeeping",
            backend_url="https://books.lumen.ae",
            agy_api_secret="sec-123",
            d1_database_id=d1_id,
            r2_bucket_name=r2_name,
        )
        self.assertEqual(pages_spec.project_name, "lumen-bookkeeping")
        pages_post = [c for c in call_log if c[0] == "POST" and c[1].endswith("/pages/projects")][0]
        prod_cfg = pages_post[2]["deployment_configs"]["production"]
        self.assertEqual(prod_cfg["d1_databases"]["LUMEN_DB"]["id"], "d1-uuid-777")
        self.assertEqual(prod_cfg["r2_buckets"]["LUMEN_ATTACHMENTS"]["name"], "lumen-bookkeeping-attachments")

        # Verify backend LumenStateRepository enforces strict tenant scoping and server-side PBKDF2 auth
        with tempfile.TemporaryDirectory() as tmp:
            repo = agy_service.LumenStateRepository(Path(tmp) / "tenant_iso.sqlite3")
            repo.mutate_state({
                "lumen_accounts": json.dumps({
                    "acc-1": {"email": "t1@co.ae", "companyName": "Tenant 1", "plan": "basic", "salt": "0102030405060708090a0b0c0d0e0f10", "passwordHash": "secret-hash-1"},
                    "acc-2": {"email": "t2@co.ae", "companyName": "Tenant 2", "plan": "premium", "salt": "1112131415161718191a1b1c1d1e1f20", "passwordHash": "secret-hash-2"},
                }),
                "lumen_profiles": json.dumps([
                    {"id": "p1", "name": "Tenant 1", "accountId": "acc-1"},
                    {"id": "p2", "name": "Tenant 2", "accountId": "acc-2"},
                ]),
                "profile:p1::bookkeeping_history_v2": '[{"id":"inv-1"}]',
                "profile:p2::bookkeeping_history_v2": '[{"id":"inv-2"}]',
                "lumen_admin_credentials": '{"salt":"s","passwordHash":"h"}',
            })
            # Owner GET /api/v1/state must strip lumen_admin_credentials and account passwordHash/salt
            scoped_owner = repo.get_scoped_state("owner")
            self.assertNotIn("lumen_admin_credentials", scoped_owner)
            owner_accounts = json.loads(scoped_owner["lumen_accounts"])
            self.assertNotIn("passwordHash", owner_accounts["acc-1"])
            self.assertNotIn("salt", owner_accounts["acc-1"])

            # Unauthenticated GET /api/v1/state returns only public email/status directory
            scoped_unauth = repo.get_scoped_state(None)
            self.assertEqual(scoped_unauth["lumen_profiles"], "[]")
            self.assertNotIn("profile:p1::bookkeeping_history_v2", scoped_unauth)
            self.assertNotIn("lumen_admin_credentials", scoped_unauth)

            # Unauthenticated POST /api/v1/state must be rejected (0 updates)
            self.assertEqual(
                repo.mutate_scoped_state(None, {"profile:p1::bookkeeping_history_v2": '[{"id":"hack"}]'}),
                0,
            )

            scoped_t1 = repo.get_scoped_state("acc-1")
            self.assertIn("profile:p1::bookkeeping_history_v2", scoped_t1)
            self.assertNotIn("profile:p2::bookkeeping_history_v2", scoped_t1)
            self.assertNotIn("lumen_admin_credentials", scoped_t1)
            t1_accounts = json.loads(scoped_t1["lumen_accounts"])
            self.assertIn("acc-1", t1_accounts)
            self.assertNotIn("acc-2", t1_accounts)
            self.assertNotIn("passwordHash", t1_accounts["acc-1"])

            # Non-owner tenant cannot overwrite another tenant's profile, hijack profile ID p2, inject acc-evil, or escalate own plan
            repo.mutate_scoped_state(
                "acc-1",
                set_items={
                    "lumen_profiles": json.dumps([
                        {"id": "p1", "name": "Tenant 1", "accountId": "acc-1"},
                        {"id": "p2", "name": "Hijacked Tenant 2", "accountId": "acc-1"},
                    ]),
                    "profile:p2::bookkeeping_history_v2": '[{"id":"tampered"}]',
                    "profile:unregistered::bookkeeping_history_v2": '[{"id":"orphan"}]',
                    "lumen_admin_credentials": '{"tampered":true}',
                    "lumen_accounts": json.dumps({
                        "acc-1": {"email": "t1@co.ae", "plan": "premium"},
                        "acc-evil": {"email": "evil@co.ae", "plan": "premium"},
                    }),
                },
                remove_keys=["profile:p2::bookkeeping_history_v2"],
                clear_all=True,
            )
            full_state = repo.get_all_state()
            self.assertEqual(full_state["profile:p2::bookkeeping_history_v2"], '[{"id":"inv-2"}]')
            self.assertNotIn("profile:unregistered::bookkeeping_history_v2", full_state)
            self.assertEqual(full_state["lumen_admin_credentials"], '{"salt":"s","passwordHash":"h"}')
            accounts_after = json.loads(full_state["lumen_accounts"])
            self.assertEqual(accounts_after["acc-1"]["plan"], "basic")
            self.assertNotIn("acc-evil", accounts_after)

            # New non-owner registration cannot self-assign premium plan without admin approval
            repo.mutate_scoped_state(
                "acc-new",
                set_items={
                    "lumen_accounts": json.dumps({
                        "acc-new": {
                            "email": "new@co.ae",
                            "plan": "premium",
                            "salt": "s-new",
                            "passwordHash": "h-new",
                        }
                    }),
                },
            )
            new_acc = json.loads(repo.get_all_state()["lumen_accounts"])["acc-new"]
            self.assertEqual(new_acc["plan"], "basic")
            self.assertEqual(new_acc["requestedPlan"], "premium")

            # Owner updating lumen_profiles preserves tenant profiles
            repo.mutate_scoped_state(
                "owner",
                set_items={
                    "lumen_profiles": json.dumps([
                        {"id": "default", "name": "Owner Co", "accountId": "owner"}
                    ])
                },
            )
            profs_after_owner = json.loads(repo.get_all_state()["lumen_profiles"])
            prof_ids = {p["id"] for p in profs_after_owner}
            self.assertIn("default", prof_ids)
            self.assertIn("p1", prof_ids)
            self.assertIn("p2", prof_ids)

            # Tenant-scoped attachments: acc-1 can write/read p1::att1, but cannot read/overwrite p2::att1
            self.assertEqual(repo.put_attachments({"p1::att1": "data-p1"}, account_id="acc-1"), 1)
            self.assertEqual(repo.put_attachments({"p2::att1": "data-p2"}, account_id="acc-2"), 1)
            self.assertEqual(repo.get_attachment("p1::att1", account_id="acc-1"), "data-p1")
            self.assertIsNone(repo.get_attachment("p2::att1", account_id="acc-1"))
            self.assertIsNone(repo.get_attachment("p1::att1", account_id=None))
            self.assertEqual(repo.put_attachments({"p2::att1": "hacked"}, account_id="acc-1"), 0)
            self.assertEqual(repo.get_attachment("p2::att1", account_id="owner"), "data-p2")

            # Session token verification rejects forged tokens and cross-account spoofing
            tok_t1 = repo.issue_session_token("acc-1")
            self.assertEqual(repo.verify_session_token(tok_t1, "acc-1"), "acc-1")
            self.assertIsNone(repo.verify_session_token(tok_t1, "acc-2"))
            self.assertIsNone(repo.verify_session_token("sess.acc-1.bad.forged", "acc-1"))
            self.assertEqual(
                repo.resolve_caller_from_headers(account_header="acc-2", session_header=tok_t1),
                "unauthenticated",
            )


if __name__ == "__main__":
    unittest.main()
