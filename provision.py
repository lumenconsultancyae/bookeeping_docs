#!/usr/bin/env python3
"""Provision the Lumen Bookkeeping App and `agy-ai` backend across AWS EC2 and Cloudflare.

Reads the required environment variables:
  - AWS_ACCESS_KEY_ID
  - AWS_SECRET_ACCESS_KEY
  - AWS_REGION
  - CLOUDFLARE_ACCOUNT_ID
  - CLOUDFLARE_API_TOKEN

Optional environment variables:
  - AWS_SESSION_TOKEN
  - CLOUDFLARE_DOMAIN        (e.g. books.yourdomain.com)
  - CLOUDFLARE_ZONE_ID       (optional explicit Cloudflare Zone ID)
  - CLOUDFLARE_TUNNEL_NAME   (default: bookkeeping-prod)
  - EC2_INSTANCE_TYPE        (default: t3.small)
  - EC2_KEY_NAME             (default: bookkeeping-agy-key)
  - PROVISION_DRY_RUN        (set to "true" to validate env & generate dry-run plan)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from deploy.config import ProvisioningSettings
from deploy.domain import ProvisioningError
from deploy.service import ProvisioningService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision AWS EC2 (`agy-ai` + `bookkeeping-web`) and Cloudflare Zero Trust Tunnel."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate environment variables and emit provisioning plan without calling live cloud APIs.",
    )
    args = parser.parse_args(argv)

    env = dict(os.environ)
    if args.dry_run:
        env["PROVISION_DRY_RUN"] = "true"

    try:
        settings = ProvisioningSettings.from_env(env)
        service = ProvisioningService(settings=settings)
        result = service.run()
    except ProvisioningError as exc:
        print(json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), indent=2))
    print("\n--- Next Step: One-Time Google Account Login for agy ---")
    print(f"1. SSH into the EC2 host:\n   {result.ssh_command}")
    print(f"2. Run the interactive Google login inside the container:\n   {result.agy_login_command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
