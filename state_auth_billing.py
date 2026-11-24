"""Authentication, signed session tokens, reCAPTCHA attestation, and trial billing helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

LOCAL_ONLY_KEYS = frozenset({
    "lumen_lang", "lumen_sidebar_collapsed", "probe", "lumen_current_account",
    "lumen_current_user", "lumen_active_profile", "lumen_session_token",
    "lumen.advisorOrigin", "lumen.returnView",
})
PLATFORM_INTEGRATIONS_KEY = "lumen_platform_integrations"
PLATFORM_SECRETS_KEY = "lumen_platform_secrets"

PLAN_ALIASES: dict[str, str] = {
    "free": "basic", "trial": "basic", "basic": "basic",
    "advance": "advance",
    "pro": "premium", "premium": "premium", "enterprise": "premium",
    "managed": "managed", "bookkeeping": "managed", "concierge": "managed",
}
PLAN_USER_LIMITS: dict[str, int | None] = {
    "basic": 2, "advance": 5, "premium": None, "managed": None,
}
PLAN_PRICES: dict[str, int] = {
    "basic": 69, "advance": 129, "premium": 199, "managed": 1450,
}
AI_ELIGIBLE_PLANS = frozenset({"advance", "premium", "managed"})
VALID_TEAM_ROLES = frozenset({"admin", "accountant", "viewer"})
VALID_ENTITY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RESERVED_ENTITY_IDS = frozenset({"owner", "unauthenticated", "default", "__proto__", "constructor", "prototype"})


def is_valid_entity_id(value: object, *, allow_owner: bool = False) -> bool:
    """Validate that an account or team-user identifier uses safe characters and is not reserved."""
    clean = str(value or "").strip()
    if not VALID_ENTITY_ID_RE.match(clean):
        return False
    return (allow_owner and clean == "owner") or clean.lower() not in RESERVED_ENTITY_IDS


def collect_reserved_emails(
    accounts: Mapping[str, Mapping[str, Any]], *, exclude_acc_id: str | None = None, own_email: object = "",
) -> set[str]:
    """Return all lowercase emails already reserved by admin, other accounts, or own primary email."""
    blocked = {ADMIN_EMAIL}
    if clean_own := str(own_email or "").strip().lower():
        blocked.add(clean_own)
    for acc_id, acc in (accounts or {}).items():
        if not isinstance(acc, Mapping) or acc.get("_deleted") or (exclude_acc_id and acc_id == exclude_acc_id):
            continue
        if em := str(acc.get("email") or "").strip().lower():
            blocked.add(em)
        for tu in acc.get("teamUsers") or []:
            if isinstance(tu, Mapping) and not tu.get("_deleted") and (tu_em := str(tu.get("email") or "").strip().lower()):
                blocked.add(tu_em)
    return blocked

ADMIN_EMAIL = "admin@lumenconsultancy.net"
PBKDF2_ITERATIONS = 120000
DEFAULT_ADMIN_SALT = "4c756d656e41646d696e53616c743236"
DEFAULT_ADMIN_HASH = "pbkdf2_sha256$120000$70663afeba18d22eefd9f653155db1ccbb1a28718290cb662da2a408aceee2b4"


@dataclass(frozen=True)
class CallerContext:
    """Resolved authenticated caller identity, RBAC role, and optional profile scope."""

    account_id: str
    team_user_id: str | None = None
    role: str = "unauthenticated"
    profile_ids: tuple[str, ...] | None = None


def normalize_plan_id(plan_id: object) -> str:
    """Return canonical plan id (`basic`, `advance`, `premium`, or `managed`)."""
    return PLAN_ALIASES.get(str(plan_id or "").strip().lower(), "basic")


def max_team_users_for_plan(plan_id: object) -> int | None:
    """Return max additional team users allowed for a plan, or None for unlimited."""
    total_limit = PLAN_USER_LIMITS.get(normalize_plan_id(plan_id), 2)
    return None if total_limit is None else max(total_limit - 1, 0)


def is_excluded_state_key(key: str) -> bool:
    """Return True if `key` belongs strictly to browser-local UI config or session pointers."""
    return not isinstance(key, str) or not key or key in LOCAL_ONLY_KEYS or key.startswith("lumen_table_page_size:")


def compute_password_hash(password: str, salt: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Derive a salted PBKDF2-HMAC-SHA256 digest formatted as `pbkdf2_sha256$<iterations>$<hex>`."""
    clean_iters = max(int(iterations), 1)
    derived = hashlib.pbkdf2_hmac("sha256", str(password or "").encode(), str(salt or "").encode(), clean_iters).hex()
    return f"pbkdf2_sha256${clean_iters}${derived}"


def verify_password_hash(password: str, salt: str, stored_hash: str) -> bool:
    """Verify `password` against `stored_hash` (PBKDF2-HMAC-SHA256 or legacy salted SHA-256)."""
    if not stored_hash or not salt:
        return False
    target, clean_salt = str(stored_hash), str(salt)
    if target.startswith("pbkdf2_sha256$"):
        parts = target.split("$")
        iters = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else PBKDF2_ITERATIONS
        expected = compute_password_hash(password, clean_salt, iters)
    else:
        expected = hashlib.sha256(f"{clean_salt}:{password}".encode()).hexdigest()
    return hmac.compare_digest(expected.encode(), target.encode())


def strip_team_user_secrets(user: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of a team user dictionary with credential secrets removed."""
    return {k: v for k, v in user.items() if k not in ("passwordHash", "salt", "resetCodeHash")}


def strip_account_secrets(acc: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of an account dictionary with credential hashes removed (including teamUsers)."""
    cleaned = {k: v for k, v in acc.items() if k not in ("passwordHash", "salt", "resetCodeHash")}
    raw_team = cleaned.get("teamUsers")
    if isinstance(raw_team, list):
        cleaned["teamUsers"] = [strip_team_user_secrets(u) for u in raw_team if isinstance(u, Mapping)]
    return cleaned


def safe_json(raw: str | None, fallback: object) -> object:
    """Parse JSON string `raw`, returning `fallback` on empty or malformed JSON."""
    try:
        return json.loads(raw or "") if raw else fallback
    except json.JSONDecodeError:
        return fallback


def merge_team_users(
    prev_users: object, incoming_users: object, plan_id: object, *, is_owner: bool = False, blocked_emails: set[str] | frozenset[str] | None = None,
) -> list[dict[str, object]]:
    """Merge incoming teamUsers with prior credentials preserved and plan seat limits enforced."""
    if not isinstance(incoming_users, list):
        return list(prev_users) if isinstance(prev_users, list) else []
    prev_by_id = {str(u["id"]): u for u in (prev_users or []) if isinstance(u, dict) and u.get("id")} if isinstance(prev_users, list) else {}
    seen_emails: set[str] = set()
    merged: list[dict[str, object]] = []
    max_additional = None if is_owner else max_team_users_for_plan(plan_id)
    for item in incoming_users:
        if not isinstance(item, dict) or item.get("_deleted"):
            continue
        uid = str(item.get("id") or "").strip()
        email = str(item.get("email") or "").strip().lower()
        if not is_valid_entity_id(uid) or not email or email in seen_emails or email == ADMIN_EMAIL or (blocked_emails and email in blocked_emails):
            continue
        prev = prev_by_id.get(uid)
        nxt: dict[str, object] = {**(prev if isinstance(prev, dict) else {}), **item, "id": uid, "email": email}
        role = str(nxt.get("role") or "accountant").strip().lower()
        nxt["role"] = role if role in VALID_TEAM_ROLES else "accountant"
        nxt["status"] = "suspended" if str(nxt.get("status") or "active").strip().lower() == "suspended" else "active"
        if isinstance(prev, dict):
            for sec_key in ("passwordHash", "salt", "resetCodeHash"):
                if not item.get(sec_key) and prev.get(sec_key):
                    nxt[sec_key] = prev[sec_key]
        elif not (nxt.get("passwordHash") and nxt.get("salt")):
            continue
        seen_emails.add(email)
        merged.append(nxt)
        if max_additional is not None and len(merged) >= max_additional:
            break
    return merged


def merge_unauth_registration(
    existing_accounts: dict[str, dict], val_str: str, session_secret: bytes, captcha_attestation: str | None,
) -> str | None:
    """Allow an unauthenticated caller to self-register at most one brand-new sanitized basic account."""
    incoming = safe_json(val_str, None)
    if not isinstance(incoming, dict):
        return None
    existing_emails = collect_reserved_emails(existing_accounts)
    require_captcha = bool(os.environ.get("RECAPTCHA_SECRET_KEY", "").strip())
    for acc_id, acc_obj in incoming.items():
        if not is_valid_entity_id(acc_id) or acc_id in existing_accounts or not isinstance(acc_obj, dict) or acc_obj.get("_deleted"):
            continue
        email = str(acc_obj.get("email") or "").strip().lower()
        if not email or "@" not in email or email in existing_emails or not (acc_obj.get("passwordHash") and acc_obj.get("salt")):
            continue
        att = captcha_attestation or (str(acc_obj.get("captchaAttestation") or "") if isinstance(acc_obj.get("captchaAttestation"), str) else "")
        if require_captcha and not verify_captcha_attestation(session_secret, att):
            raise PermissionError("Captcha verification is required before account registration.")
        nxt = {**acc_obj, "email": email, "plan": "basic", "status": "active", "aiAddon": False, "locked": False, "failedAttempts": 0, "teamUsers": []}
        for drop_k in ("captchaAttestation", "addons", "resetCodeHash", "resetRequestedAt", "lastChargedAt", "lastChargedAmount", "renewalReminderSentAt", "renewalReminderMessage"):
            nxt.pop(drop_k, None)
        if normalize_plan_id(acc_obj.get("plan") or "basic") != "basic" and not nxt.get("requestedPlan"):
            nxt["requestedPlan"] = normalize_plan_id(acc_obj.get("plan"))
        if acc_obj.get("aiAddon") is True or acc_obj.get("requestedAiAddon") is True:
            nxt["requestedAiAddon"] = True
        if nxt.get("billingStatus") == "active_paid":
            nxt["billingStatus"] = "trial" if nxt.get("cardLast4") else "active"
        return json.dumps({**existing_accounts, acc_id: nxt})
    return None


def issue_session_token(secret: bytes, account_id: str, team_user_id: str | None = None) -> str:
    """Issue an HMAC-SHA256 signed session token bound to `account_id` and optional `team_user_id`."""
    clean_acc = str(account_id or "").strip()
    clean_tu = str(team_user_id or "").strip()
    if not is_valid_entity_id(clean_acc, allow_owner=not clean_tu):
        raise ValueError("Invalid session account id.")
    if clean_tu and not is_valid_entity_id(clean_tu):
        raise ValueError("Invalid session team user id.")
    nonce = secrets.token_hex(12)
    msg = f"tu:{clean_acc}:{clean_tu}:{nonce}" if clean_tu else f"acc:{clean_acc}:{nonce}"
    mac = hmac.new(secret, msg.encode(), hashlib.sha256).hexdigest()
    return f"sess.{clean_acc}.{clean_tu}.{nonce}.{mac}" if clean_tu else f"sess.{clean_acc}.{nonce}.{mac}"


def verify_session_token_identity(
    secret: bytes, token: str | None, claimed_account: str | None = None,
) -> tuple[str, str | None] | None:
    """Verify signed session token and return `(account_id, team_user_id)` or None."""
    parts = str(token or "").strip().split(".")
    if len(parts) == 4 and parts[0] == "sess" and all(parts[1:]):
        _, token_acc, nonce, provided_mac = parts
        if not is_valid_entity_id(token_acc, allow_owner=True):
            return None
        token_tu: str | None = None
        msg = f"acc:{token_acc}:{nonce}"
    elif len(parts) == 5 and parts[0] == "sess" and all(parts[1:]):
        _, token_acc, token_tu, nonce, provided_mac = parts
        if token_acc == "owner" or not is_valid_entity_id(token_acc) or not is_valid_entity_id(token_tu):
            return None
        msg = f"tu:{token_acc}:{token_tu}:{nonce}"
    else:
        return None
    expected_mac = hmac.new(secret, msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_mac.encode(), expected_mac.encode()):
        return None
    if claimed_account and claimed_account != "unauthenticated" and token_acc not in (claimed_account, "owner"):
        return None
    return token_acc, token_tu


def issue_captcha_attestation(secret: bytes) -> str:
    """Create a short-lived HMAC-signed attestation token proving server captcha verification."""
    exp_epoch = int(time.time()) + 600
    nonce = secrets.token_hex(8)
    mac = hmac.new(secret, f"cap:{exp_epoch}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return f"cap.{exp_epoch}.{nonce}.{mac}"


def verify_captcha_attestation(secret: bytes, token: object) -> bool:
    """Validate an HMAC-signed captcha attestation token and check its expiry."""
    parts = str(token or "").strip().split(".")
    if len(parts) != 4 or parts[0] != "cap" or not parts[1].isdigit() or not parts[2] or not parts[3]:
        return False
    exp_epoch = int(parts[1])
    if exp_epoch < int(time.time()):
        return False
    expected = hmac.new(secret, f"cap:{exp_epoch}:{parts[2]}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(parts[3].encode(), expected.encode())


def _is_local_origin(origin: str | None) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin.strip())
    host = (parsed.hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "bookkeeping-web")


def verify_recaptcha_token(
    token: object, *, secret: str, session_secret: bytes, origin: str | None = None,
) -> dict[str, object]:
    """Verify a Google reCAPTCHA v2 token; fail closed on non-local origins if unconfigured."""
    clean_token = str(token or "").strip()
    if not clean_token:
        return {"ok": False, "error": 'Please complete the "I\'m not a robot" verification.'}
    clean_secret = str(secret or "").strip()
    if clean_secret:
        try:
            body = urlencode({"secret": clean_secret, "response": clean_token}).encode()
            req = Request(
                "https://www.google.com/recaptcha/api/siteverify",
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            if not isinstance(data, dict) or not data.get("success"):
                return {"ok": False, "error": "reCAPTCHA verification failed. Please try again."}
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            return {"ok": False, "status_code": 502, "error": "Unable to verify reCAPTCHA right now. Please try again."}
    elif not _is_local_origin(origin):
        return {"ok": False, "status_code": 503, "error": "Captcha verification is not configured on this server."}
    return {
        "ok": True,
        "provider": "recaptcha",
        "verifiedAt": datetime.now(UTC).isoformat(),
        "captchaAttestation": issue_captcha_attestation(session_secret),
    }


def _account_amount(acc: Mapping[str, object]) -> int:
    plan = normalize_plan_id(acc.get("plan") or "advance")
    return PLAN_PRICES.get(plan, 129) * (10 if acc.get("billing") == "yearly" else 1)


def _match_account_for_billing(
    accounts: dict[str, dict], email: object, caller_ctx: CallerContext,
) -> tuple[str | None, dict | None, dict[str, object] | None]:
    if caller_ctx.role not in ("owner", "admin"):
        return None, None, {"ok": False, "status_code": 403, "error": "Forbidden."}
    if not isinstance(email, str):
        return None, None, {"ok": False, "status_code": 400, "error": "Account not found."}
    clean_email = email.strip().lower()
    if not clean_email:
        return None, None, {"ok": False, "error": "Account not found."}
    for acc_id, acc in accounts.items():
        if str(acc.get("email") or "").strip().lower() == clean_email or str(acc_id).lower() == clean_email:
            if caller_ctx.account_id not in ("owner", acc_id):
                return None, None, {"ok": False, "status_code": 403, "error": "Forbidden."}
            return acc_id, acc, None
    return None, None, {"ok": False, "error": "Account not found."}


def verify_login_impl(
    full_state: dict[str, str], accounts: dict[str, dict], email: object, password: object,
    session_secret: bytes, save_accounts: Callable[[dict[str, dict]], Any],
) -> dict[str, object]:
    """Verify email/password across admin, primary accounts, and teamUsers with 3x lockout."""
    if not isinstance(email, str) or not isinstance(password, str):
        return {"ok": False, "status_code": 400, "error": "Invalid credentials."}
    clean_email, pwd = email.strip().lower(), password
    if not clean_email or not pwd:
        return {"ok": False, "error": "Invalid credentials."}
    if clean_email == ADMIN_EMAIL:
        adm = safe_json(full_state.get("lumen_admin_credentials"), {})
        has_custom = isinstance(adm, dict) and adm.get("salt") and adm.get("passwordHash")
        salt, target = (str(adm["salt"]), str(adm["passwordHash"])) if has_custom else (DEFAULT_ADMIN_SALT, DEFAULT_ADMIN_HASH)
        return (
            {"ok": True, "accountId": "owner", "sessionToken": issue_session_token(session_secret, "owner")}
            if verify_password_hash(pwd, salt, target)
            else {"ok": False, "error": "Invalid admin credentials."}
        )
    for acc_id, acc in accounts.items():
        if str(acc.get("email") or "").strip().lower() == clean_email:
            if acc.get("status") == "suspended":
                return {"ok": False, "error": "Account is suspended."}
            attempts = int(acc.get("failedAttempts") or 0)
            if acc.get("locked") or attempts >= 3:
                return {"ok": False, "locked": True, "failedAttempts": max(attempts, 3), "error": "Account locked after 3 failed attempts. Please reset your password."}
            if verify_password_hash(pwd, str(acc.get("salt") or ""), str(acc.get("passwordHash") or "")):
                if attempts > 0 or acc.get("locked"):
                    acc["failedAttempts"], acc["locked"] = 0, False
                    save_accounts(accounts)
                return {"ok": True, "accountId": acc_id, "sessionToken": issue_session_token(session_secret, acc_id)}
            attempts += 1
            acc["failedAttempts"], acc["locked"] = attempts, attempts >= 3
            save_accounts(accounts)
            return {"ok": False, "locked": True, "failedAttempts": attempts, "error": "Account locked after 3 failed attempts. Please reset your password."} if acc["locked"] else {"ok": False, "failedAttempts": attempts, "error": "Incorrect email or password."}
    for acc_id, acc in accounts.items():
        for tu in acc.get("teamUsers") or []:
            if not isinstance(tu, dict) or str(tu.get("email") or "").strip().lower() != clean_email:
                continue
            if acc.get("status") == "suspended":
                return {"ok": False, "error": "Account is suspended."}
            if tu.get("status") == "suspended":
                return {"ok": False, "error": "User access is suspended."}
            attempts = int(tu.get("failedAttempts") or 0)
            if tu.get("locked") or attempts >= 3:
                return {"ok": False, "locked": True, "failedAttempts": max(attempts, 3), "error": "Account locked after 3 failed attempts. Please reset your password."}
            if verify_password_hash(pwd, str(tu.get("salt") or ""), str(tu.get("passwordHash") or "")):
                if attempts > 0 or tu.get("locked"):
                    tu["failedAttempts"], tu["locked"] = 0, False
                    save_accounts(accounts)
                tu_id = str(tu.get("id") or "")
                return {
                    "ok": True,
                    "accountId": acc_id,
                    "sessionToken": issue_session_token(session_secret, acc_id, team_user_id=tu_id),
                    "teamUser": {
                        "id": tu_id, "name": tu.get("name") or "", "email": clean_email,
                        "role": tu.get("role") or "accountant",
                        "profileIds": tu.get("profileIds") if isinstance(tu.get("profileIds"), list) else [],
                    },
                }
            attempts += 1
            tu["failedAttempts"], tu["locked"] = attempts, attempts >= 3
            save_accounts(accounts)
            return {"ok": False, "locked": True, "failedAttempts": attempts, "error": "Account locked after 3 failed attempts. Please reset your password."} if tu["locked"] else {"ok": False, "failedAttempts": attempts, "error": "Incorrect email or password."}
    return {"ok": False, "error": "Incorrect email or password."}


def request_password_reset_impl(
    accounts: dict[str, dict], email: object, save_accounts: Callable[[dict[str, dict]], Any],
) -> dict[str, object]:
    """Generate a 6-digit password reset code for primary account or team user."""
    if not isinstance(email, str):
        return {"ok": False, "status_code": 400, "error": "Please enter a valid email address."}
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        return {"ok": False, "error": "Please enter a valid email address."}
    for target in (
        *[acc for acc in accounts.values() if isinstance(acc, dict)],
        *[u for acc in accounts.values() if isinstance(acc, dict) for u in (acc.get("teamUsers") or []) if isinstance(u, dict)],
    ):
        if str(target.get("email") or "").strip().lower() == clean_email:
            code = f"{secrets.randbelow(900000) + 100000:06d}"
            target["resetCodeHash"] = hashlib.sha256(f"{clean_email}:{code}".encode()).hexdigest()
            target["resetRequestedAt"] = datetime.now(UTC).isoformat()
            save_accounts(accounts)
            return {"ok": True, "sentTo": clean_email, "resetCode": code, "message": f"Password reset instructions have been sent to {clean_email}."}
    return {"ok": False, "error": "No account found with this email address."}


def confirm_password_reset_impl(
    accounts: dict[str, dict], email: object, code: object, new_password: object, save_accounts: Callable[[dict[str, dict]], Any],
) -> dict[str, object]:
    """Verify reset code and update password hash for primary account or team user."""
    if not isinstance(email, str) or not isinstance(code, str) or not isinstance(new_password, str):
        return {"ok": False, "status_code": 400, "error": "Invalid password reset parameters."}
    clean_email, clean_code, pwd = email.strip().lower(), code.strip(), new_password
    if not clean_email or "@" not in clean_email:
        return {"ok": False, "error": "Please enter a valid email address."}
    if len(pwd) < 8:
        return {"ok": False, "error": "Password must be at least 8 characters."}
    if not (any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd)):
        return {"ok": False, "error": "Password must contain letters and numbers."}
    if not clean_code:
        return {"ok": False, "error": "Invalid or expired reset code."}
    expected_hash = hashlib.sha256(f"{clean_email}:{clean_code}".encode()).hexdigest()
    for acc_id, acc in accounts.items():
        if str(acc.get("email") or "").strip().lower() == clean_email:
            stored = str(acc.get("resetCodeHash") or "")
            if not stored or not hmac.compare_digest(stored, expected_hash):
                return {"ok": False, "error": "Invalid or expired reset code."}
            new_salt = secrets.token_hex(16)
            acc["salt"], acc["passwordHash"], acc["failedAttempts"], acc["locked"] = new_salt, compute_password_hash(pwd, new_salt), 0, False
            acc.pop("resetCodeHash", None)
            save_accounts(accounts)
            return {"ok": True, "accountId": acc_id}
    for acc_id, acc in accounts.items():
        for tu in acc.get("teamUsers") or []:
            if not isinstance(tu, dict) or str(tu.get("email") or "").strip().lower() != clean_email:
                continue
            stored = str(tu.get("resetCodeHash") or "")
            if not stored or not hmac.compare_digest(stored, expected_hash):
                return {"ok": False, "error": "Invalid or expired reset code."}
            new_salt = secrets.token_hex(16)
            tu["salt"], tu["passwordHash"], tu["failedAttempts"], tu["locked"] = new_salt, compute_password_hash(pwd, new_salt), 0, False
            tu.pop("resetCodeHash", None)
            save_accounts(accounts)
            return {"ok": True, "accountId": acc_id, "teamUserId": tu.get("id")}
    return {"ok": False, "error": "No account found with this email address."}


def save_payment_method_impl(
    accounts: dict[str, dict], email: object, caller_ctx: CallerContext,
    save_accounts: Callable[[dict[str, dict]], Any], *,
    card_holder_name: object = "", card_brand: object = "Card", card_last4: object = "",
    card_expiry: object = "", payment_method_token: object = "", pay_now: object = False,
) -> dict[str, object]:
    """Store masked card metadata and charge if trial has ended or pay_now is requested."""
    if caller_ctx.role not in ("owner", "admin"):
        return {"ok": False, "status_code": 403, "error": "Forbidden."}
    holder = str(card_holder_name or "").strip()
    last4 = "".join(ch for ch in str(card_last4 or "") if ch.isdigit())[-4:]
    exp = str(card_expiry or "").strip()
    brand = str(card_brand or "Card").strip() or "Card"
    if not holder or len(last4) != 4 or len(exp) != 5 or exp[2] != "/" or not (exp[:2].isdigit() and 1 <= int(exp[:2]) <= 12 and exp[3:].isdigit()):
        return {"ok": False, "error": "Please enter valid credit card details."}
    acc_id, acc, err = _match_account_for_billing(accounts, email, caller_ctx)
    if err or not acc_id or acc is None:
        return err or {"ok": False, "error": "Account not found."}
    amt = _account_amount(acc)
    trial_ended = False
    if raw_end := str(acc.get("trialEndsAt") or "").strip():
        try:
            trial_end_dt = datetime.fromisoformat(raw_end)
            if trial_end_dt.tzinfo is None:
                trial_end_dt = trial_end_dt.replace(tzinfo=UTC)
            trial_ended = trial_end_dt <= datetime.now(UTC)
        except ValueError:
            trial_ended = False
    should_charge = bool(pay_now) or trial_ended
    acc.update({
        "cardHolderName": holder, "cardBrand": brand, "cardLast4": last4, "cardExpiry": exp,
        "paymentMethodToken": str(payment_method_token or f"pm_lumen_{last4}_{secrets.token_hex(4)}"),
        "cardDeferred": False, "autoRenew": True, "status": "active",
    })
    if should_charge:
        acc["billingStatus"], acc["lastChargedAmount"], acc["lastChargedAt"] = "active_paid", amt, datetime.now(UTC).isoformat()
    elif acc.get("billingStatus") != "active_paid":
        acc["billingStatus"] = "trial"
    save_accounts(accounts)
    return {
        "ok": True, "accountId": acc_id, "cardBrand": brand, "cardLast4": last4,
        "cardExpiry": exp, "billingStatus": acc.get("billingStatus"), "chargedAmount": amt if should_charge else 0,
    }


def send_trial_reminder_impl(
    accounts: dict[str, dict], email: object, caller_ctx: CallerContext,
    save_accounts: Callable[[dict[str, dict]], Any],
) -> dict[str, object]:
    """Dispatch a 15-day trial renewal reminder for an account."""
    acc_id, acc, err = _match_account_for_billing(accounts, email, caller_ctx)
    if err or not acc_id or acc is None:
        return err or {"ok": False, "error": "Account not found."}
    amt = _account_amount(acc)
    raw_end = str(acc.get("trialEndsAt") or "")[:10]
    end_disp = f"{raw_end[8:10]}/{raw_end[5:7]}/{raw_end[2:4]}" if len(raw_end) == 10 and raw_end[4] == "-" and raw_end[7] == "-" else (raw_end or "soon")
    if acc.get("cardLast4"):
        msg = f"Reminder sent to {acc.get('email')}: Your 15-day free trial ends on {end_disp}. Unless canceled, AED {amt} will be auto-deducted on {acc.get('cardBrand') or 'Card'} •••• {acc.get('cardLast4')}."
    else:
        msg = f"Reminder sent to {acc.get('email')}: Your 15-day free trial ends on {end_disp}. Please log in and enter your credit card for payment (AED {amt})."
    acc["renewalReminderSentAt"], acc["renewalReminderMessage"] = datetime.now(UTC).isoformat(), msg
    save_accounts(accounts)
    return {"ok": True, "accountId": acc_id, "sentTo": acc.get("email"), "message": msg}


def process_trial_renewal_impl(
    accounts: dict[str, dict], email: object, caller_ctx: CallerContext,
    save_accounts: Callable[[dict[str, dict]], Any],
) -> dict[str, object]:
    """Auto-deduct subscription fee on stored payment method when trial completes and autoRenew is active."""
    acc_id, acc, err = _match_account_for_billing(accounts, email, caller_ctx)
    if err or not acc_id or acc is None:
        return err or {"ok": False, "error": "Account not found."}
    if str(acc.get("status") or "active") == "suspended":
        return {"ok": False, "error": "Account is suspended."}
    if not acc.get("cardLast4"):
        return {"ok": False, "error": "No credit card on file. User must enter a credit card for payment."}
    if acc.get("autoRenew") is False or acc.get("billingStatus") == "canceled_at_period_end":
        return {"ok": False, "error": "Auto-renewal is canceled for this subscription."}
    amt = _account_amount(acc)
    acc["billingStatus"], acc["lastChargedAmount"], acc["lastChargedAt"], acc["status"] = "active_paid", amt, datetime.now(UTC).isoformat(), "active"
    save_accounts(accounts)
    return {"ok": True, "accountId": acc_id, "chargedAmount": amt, "billingStatus": "active_paid", "cardLast4": acc.get("cardLast4") or "0000"}
