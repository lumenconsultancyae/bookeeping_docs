"""Application service orchestrating Cloudflare Tunnel and AWS EC2 provisioning."""

from __future__ import annotations

import json

from deploy.config import ProvisioningSettings
from deploy.domain import (
    ProvisioningResult,
    build_ec2_user_data_script,
)
from deploy.infrastructure import AwsEc2Client, CloudflareApiClient


class ProvisioningService:
    """Orchestrates end-to-end Cloudflare Tunnel + AWS EC2 provisioning."""

    def __init__(
        self,
        *,
        settings: ProvisioningSettings,
        cloudflare_client: CloudflareApiClient | None = None,
        ec2_client: AwsEc2Client | None = None,
    ) -> None:
        self._settings = settings
        self._cloudflare = cloudflare_client or CloudflareApiClient(
            account_id=settings.cloudflare_account_id,
            api_token=settings.unwrap_cloudflare_api_token(),
        )
        self._ec2 = ec2_client or AwsEc2Client(
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.unwrap_aws_secret_access_key(),
            region=settings.aws_region,
            session_token=settings.unwrap_aws_session_token(),
        )

    def run(self) -> ProvisioningResult:
        """Execute (or dry-run) Cloudflare and AWS provisioning and persist a summary artifact."""
        s = self._settings
        s.artifacts_dir.mkdir(parents=True, exist_ok=True)
        key_path = s.artifacts_dir / f"{s.ec2_key_name}.pem"

        if s.dry_run:
            public_url = f"https://{s.cloudflare_domain}" if s.cloudflare_domain else f"https://{s.cloudflare_tunnel_name}.cfargotunnel.com"
            result = ProvisioningResult(
                dry_run=True,
                region=s.aws_region,
                cloudflare_account_id=s.cloudflare_account_id,
                tunnel_id="dry-run-tunnel-id",
                tunnel_name=s.cloudflare_tunnel_name,
                public_url=public_url,
                instance_id="dry-run-instance-id",
                public_ip="0.0.0.0",
                ssh_command=f"ssh -i {key_path} ubuntu@<EC2_PUBLIC_IP>",
                agy_login_command="sudo docker exec -it bookkeeping-agy-ai agy",
                pages_url=f"https://{s.cloudflare_pages_project}.pages.dev",
            )
            self._write_summary(result)
            return result

        tunnel_spec = self._cloudflare.ensure_tunnel(
            tunnel_name=s.cloudflare_tunnel_name,
            hostname=s.cloudflare_domain,
            zone_id=s.cloudflare_zone_id,
        )

        user_data = build_ec2_user_data_script(
            cloudflare_tunnel_token=tunnel_spec.tunnel_token,
            agy_model=s.agy_model,
            app_repo_url=s.app_repo_url,
            docs_repo_url=s.docs_repo_url,
            agy_api_secret=s.unwrap_agy_api_secret(),
        )

        instance_spec = self._ec2.provision_instance(
            instance_name=s.ec2_instance_name,
            instance_type=s.ec2_instance_type,
            security_group_name=s.ec2_security_group_name,
            key_name=s.ec2_key_name,
            key_output_path=key_path,
            user_data_script=user_data,
        )

        public_url = (
            f"https://{tunnel_spec.public_hostname}"
            if tunnel_spec.public_hostname
            else f"http://{instance_spec.public_ip}:9091"
        )
        d1_database_id = self._cloudflare.ensure_d1_database(
            db_name=s.cloudflare_d1_database_name,
        )
        r2_bucket_name = self._cloudflare.ensure_r2_bucket(
            bucket_name=s.cloudflare_r2_bucket_name,
        )
        pages_spec = self._cloudflare.ensure_pages_project(
            project_name=s.cloudflare_pages_project,
            backend_url=public_url,
            agy_api_secret=s.unwrap_agy_api_secret(),
            d1_database_id=d1_database_id,
            r2_bucket_name=r2_bucket_name,
        )
        ssh_target = instance_spec.public_ip if instance_spec.public_ip != "pending" else "<EC2_PUBLIC_IP>"
        result = ProvisioningResult(
            dry_run=False,
            region=s.aws_region,
            cloudflare_account_id=s.cloudflare_account_id,
            tunnel_id=tunnel_spec.tunnel_id,
            tunnel_name=tunnel_spec.tunnel_name,
            public_url=public_url,
            instance_id=instance_spec.instance_id,
            public_ip=instance_spec.public_ip,
            ssh_command=f"ssh -i {key_path} ubuntu@{ssh_target}",
            agy_login_command="sudo docker exec -it bookkeeping-agy-ai agy",
            pages_url=pages_spec.pages_url,
        )

        self._write_summary(result)
        return result

    def _write_summary(self, result: ProvisioningResult) -> None:
        summary_file = self._settings.artifacts_dir / "provisioning_result.json"
        summary_file.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
