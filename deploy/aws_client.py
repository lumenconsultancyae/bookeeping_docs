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


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _derive_signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


def build_aws_sigv4_headers(
    *,
    method: str,
    host: str,
    region: str,
    service: str,
    payload: str,
    access_key: str,
    secret_key: str,
    amz_date: str | None = None,
    session_token: str | None = None,
    uri: str = "/",
) -> dict[str, str]:
    """Compute AWS Signature Version 4 headers for an `application/x-www-form-urlencoded` Query API call."""
    now_str = amz_date or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now_str[:8]
    content_type = "application/x-www-form-urlencoded; charset=utf-8"
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    canonical_headers_map = {
        "content-type": content_type,
        "host": host,
        "x-amz-date": now_str,
    }
    if session_token:
        canonical_headers_map["x-amz-security-token"] = session_token

    sorted_keys = sorted(canonical_headers_map.keys())
    canonical_headers = "".join(f"{k}:{canonical_headers_map[k]}\n" for k in sorted_keys)
    signed_headers = ";".join(sorted_keys)

    canonical_request = "\n".join(
        [
            method.upper(),
            uri,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            now_str,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _derive_signing_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Content-Type": content_type,
        "Host": host,
        "X-Amz-Date": now_str,
        "Authorization": authorization,
    }
    if session_token:
        headers["X-Amz-Security-Token"] = session_token
    return headers


class AwsEc2Client:
    """Dependency-free AWS EC2 Query API client using Signature Version 4."""

    def __init__(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        session_token: str | None = None,
        transport: Callable[[dict[str, str]], str] | None = None,
    ) -> None:
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._region = region
        self._session_token = session_token
        self._transport = transport or self._default_ec2_transport

    def _default_ec2_transport(self, params: dict[str, str]) -> str:
        query_params = {"Version": EC2_API_VERSION, **params}
        payload = urllib.parse.urlencode(sorted(query_params.items()))
        host = f"ec2.{self._region}.amazonaws.com"
        url = f"https://{host}/"
        headers = build_aws_sigv4_headers(
            method="POST",
            host=host,
            region=self._region,
            service="ec2",
            payload=payload,
            access_key=self._access_key_id,
            secret_key=self._secret_access_key,
            session_token=self._session_token,
        )
        req = urllib.request.Request(
            url,
            data=payload.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_xml = exc.read().decode("utf-8", errors="replace")
            raise ProvisioningError(
                ProvisioningErrorCode.AWS_API_ERROR,
                f"AWS EC2 API error ({exc.code}) on Action={params.get('Action')}",
                context={"status_code": str(exc.code), "detail": err_xml[:300]},
            ) from exc
        except urllib.error.URLError as exc:
            raise ProvisioningError(
                ProvisioningErrorCode.AWS_API_ERROR,
                f"AWS EC2 network error on Action={params.get('Action')}",
            ) from exc

    @staticmethod
    def _strip_ns(elem: ET.Element) -> ET.Element:
        for el in elem.iter():
            if "}" in el.tag:
                el.tag = el.tag.split("}", 1)[1]
        return elem

    def _call_xml(self, params: dict[str, str]) -> ET.Element:
        raw_xml = self._transport(params)
        try:
            root = ET.fromstring(raw_xml.strip())
            return self._strip_ns(root)
        except ET.ParseError as exc:
            raise ProvisioningError(
                ProvisioningErrorCode.AWS_API_ERROR,
                f"Invalid XML response from AWS EC2 Action={params.get('Action')}",
            ) from exc

    def resolve_ubuntu_ami(self) -> str:
        """Resolve the latest Canonical Ubuntu 24.04 LTS AMD64 Server AMI in the target region."""
        root = self._call_xml(
            {
                "Action": "DescribeImages",
                "Owner.1": CANONICAL_UBUNTU_OWNER_ID,
                "Filter.1.Name": "name",
                "Filter.1.Value.1": "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
                "Filter.2.Name": "state",
                "Filter.2.Value.1": "available",
            }
        )
        candidates: list[tuple[str, str]] = []
        for item in root.findall("./imagesSet/item"):
            image_id = (item.findtext("imageId") or "").strip()
            created_at = (item.findtext("creationDate") or "").strip()
            if image_id:
                candidates.append((created_at, image_id))
        if not candidates:
            raise ProvisioningError(
                ProvisioningErrorCode.AWS_API_ERROR,
                f"No Ubuntu 24.04 LTS AMI found in region {self._region}.",
            )
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return candidates[0][1]

    def ensure_security_group(self, group_name: str) -> str:
        """Find or create the security group allowing SSH (22) and web traffic (80, 9091)."""
        desc = self._call_xml(
            {
                "Action": "DescribeSecurityGroups",
                "Filter.1.Name": "group-name",
                "Filter.1.Value.1": group_name,
            }
        )
        existing_id = (desc.findtext("./securityGroupInfo/item/groupId") or "").strip()
        if existing_id:
            return existing_id

        created = self._call_xml(
            {
                "Action": "CreateSecurityGroup",
                "GroupName": group_name,
                "GroupDescription": "Lumen Bookkeeping App and agy-ai production host",
            }
        )
        group_id = (created.findtext("groupId") or "").strip()
        if not group_id:
            raise ProvisioningError(
                ProvisioningErrorCode.AWS_API_ERROR,
                f"Failed to create security group {group_name}.",
            )

        self._call_xml(
            {
                "Action": "AuthorizeSecurityGroupIngress",
                "GroupId": group_id,
                "IpPermissions.1.IpProtocol": "tcp",
                "IpPermissions.1.FromPort": "22",
                "IpPermissions.1.ToPort": "22",
                "IpPermissions.1.IpRanges.1.CidrIp": "0.0.0.0/0",
                "IpPermissions.2.IpProtocol": "tcp",
                "IpPermissions.2.FromPort": "80",
                "IpPermissions.2.ToPort": "80",
                "IpPermissions.2.IpRanges.1.CidrIp": "0.0.0.0/0",
                "IpPermissions.3.IpProtocol": "tcp",
                "IpPermissions.3.FromPort": "9091",
                "IpPermissions.3.ToPort": "9091",
                "IpPermissions.3.IpRanges.1.CidrIp": "0.0.0.0/0",
            }
        )
        return group_id

    def ensure_key_pair(self, key_name: str, key_output_path: Path) -> str:
        """Find or create the SSH key pair for one-time `agy` server login."""
        desc = self._call_xml(
            {
                "Action": "DescribeKeyPairs",
                "Filter.1.Name": "key-name",
                "Filter.1.Value.1": key_name,
            }
        )
        existing = (desc.findtext("./keySet/item/keyName") or "").strip()
        if existing:
            return existing

        created = self._call_xml(
            {
                "Action": "CreateKeyPair",
                "KeyName": key_name,
            }
        )
        material = created.findtext("keyMaterial") or ""
        if material:
            key_output_path.parent.mkdir(parents=True, exist_ok=True)
            key_output_path.write_text(material, encoding="utf-8")
            key_output_path.chmod(0o600)
        return key_name

    def provision_instance(
        self,
        *,
        instance_name: str,
        instance_type: str,
        security_group_name: str,
        key_name: str,
        key_output_path: Path,
        user_data_script: str,
    ) -> Ec2InstanceSpec:
        """Idempotently find or launch the EC2 instance running `docker-compose.prod.yml`."""
        ami_id = self.resolve_ubuntu_ami()
        sg_id = self.ensure_security_group(security_group_name)
        resolved_key = self.ensure_key_pair(key_name, key_output_path)

        existing = self._call_xml(
            {
                "Action": "DescribeInstances",
                "Filter.1.Name": "tag:Name",
                "Filter.1.Value.1": instance_name,
                "Filter.2.Name": "instance-state-name",
                "Filter.2.Value.1": "running",
                "Filter.2.Value.2": "pending",
            }
        )
        existing_item = existing.find("./reservationSet/item/instancesSet/item")
        if existing_item is not None:
            inst_id = (existing_item.findtext("instanceId") or "").strip()
            pub_ip = (existing_item.findtext("ipAddress") or "pending").strip()
            return Ec2InstanceSpec(
                instance_id=inst_id,
                public_ip=pub_ip,
                ami_id=ami_id,
                security_group_id=sg_id,
                key_name=resolved_key,
                key_path=str(key_output_path) if key_output_path.is_file() else None,
            )

        encoded_user_data = base64.b64encode(user_data_script.encode("utf-8")).decode("ascii")
        launched = self._call_xml(
            {
                "Action": "RunInstances",
                "ImageId": ami_id,
                "InstanceType": instance_type,
                "MinCount": "1",
                "MaxCount": "1",
                "KeyName": resolved_key,
                "SecurityGroupId.1": sg_id,
                "UserData": encoded_user_data,
                "BlockDeviceMapping.1.DeviceName": "/dev/sda1",
                "BlockDeviceMapping.1.Ebs.VolumeSize": "30",
                "BlockDeviceMapping.1.Ebs.VolumeType": "gp3",
                "TagSpecification.1.ResourceType": "instance",
                "TagSpecification.1.Tag.1.Key": "Name",
                "TagSpecification.1.Tag.1.Value": instance_name,
            }
        )
        item = launched.find("./instancesSet/item")
        instance_id = (item.findtext("instanceId") if item is not None else "") or ""
        public_ip = (item.findtext("ipAddress") if item is not None else "") or "pending"
        if not instance_id:
            raise ProvisioningError(
                ProvisioningErrorCode.AWS_API_ERROR,
                "AWS EC2 RunInstances did not return an instanceId.",
            )

        instance_id = instance_id.strip()
        public_ip = public_ip.strip()
        if public_ip == "pending" and self._transport == self._default_ec2_transport:
            for _ in range(12):
                time.sleep(3)
                polled = self._call_xml(
                    {
                        "Action": "DescribeInstances",
                        "InstanceId.1": instance_id,
                    }
                )
                polled_ip = (polled.findtext("./reservationSet/item/instancesSet/item/ipAddress") or "").strip()
                if polled_ip:
                    public_ip = polled_ip
                    break

        return Ec2InstanceSpec(
            instance_id=instance_id,
            public_ip=public_ip,
            ami_id=ami_id,
            security_group_id=sg_id,
            key_name=resolved_key,
            key_path=str(key_output_path) if key_output_path.is_file() else None,
        )
