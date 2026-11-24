"""Multi-tenant SQLite state and attachment repository with PBKDF2-HMAC-SHA256 authentication."""

from __future__ import annotations

import atexit
import json
import os
import sqlite3
import sys
import tempfile
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from state_auth_billing import (
    ADMIN_EMAIL,
    AI_ELIGIBLE_PLANS,
    DEFAULT_ADMIN_HASH,
    DEFAULT_ADMIN_SALT,
    LOCAL_ONLY_KEYS,
    PBKDF2_ITERATIONS,
    PLAN_ALIASES,
    PLAN_PRICES,
    PLAN_USER_LIMITS,
    PLATFORM_INTEGRATIONS_KEY,
    PLATFORM_SECRETS_KEY,
    VALID_TEAM_ROLES,
    CallerContext,
    collect_reserved_emails,
    compute_password_hash,
    confirm_password_reset_impl,
    is_excluded_state_key,
    is_valid_entity_id,
    issue_session_token,
    max_team_users_for_plan,
    merge_team_users,
    merge_unauth_registration,
    normalize_plan_id,
    process_trial_renewal_impl,
    request_password_reset_impl,
    safe_json,
    save_payment_method_impl,
    send_trial_reminder_impl,
    strip_account_secrets,
    strip_team_user_secrets,
    verify_login_impl,
    verify_password_hash,
    verify_recaptcha_token,
    verify_session_token_identity,
)

__all__ = [
    "ADMIN_EMAIL",
    "AI_ELIGIBLE_PLANS",
    "DEFAULT_ADMIN_HASH",
    "DEFAULT_ADMIN_SALT",
    "LOCAL_ONLY_KEYS",
    "PBKDF2_ITERATIONS",
    "PLAN_ALIASES",
    "PLAN_PRICES",
    "PLAN_USER_LIMITS",
    "PLATFORM_INTEGRATIONS_KEY",
    "PLATFORM_SECRETS_KEY",
    "VALID_TEAM_ROLES",
    "CallerContext",
    "LumenStateRepository",
    "compute_password_hash",
    "is_excluded_state_key",
    "max_team_users_for_plan",
    "merge_team_users",
    "normalize_plan_id",
    "resolve_default_state_db_path",
    "safe_json",
    "strip_account_secrets",
    "strip_team_user_secrets",
    "verify_password_hash",
    "verify_recaptcha_token",
]

_MIGRATION_SQL_PATH = Path(__file__).resolve().parent / "migrations" / "0001_initial_schema.sql"


class LumenStateRepository:
    """Thread-safe SQLite repository for multi-tenant bookkeeping state, auth verification, and attachments."""

    def __init__(self, db_path: Path, *, session_secret: str | None = None) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        raw_secret = session_secret or f"lumen-session-key-{DEFAULT_ADMIN_SALT}"
        self._session_secret = raw_secret.encode()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_sql = _MIGRATION_SQL_PATH.read_text(encoding="utf-8")
        with self._lock, self._connect() as conn:
            conn.executescript(schema_sql)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def issue_session_token(self, account_id: str, *, team_user_id: str | None = None) -> str:
        """Issue an HMAC-SHA256 signed session token bound to `account_id` and optional `team_user_id`."""
        return issue_session_token(self._session_secret, account_id, team_user_id=team_user_id)

    def verify_session_token(self, token: str | None, claimed_account: str | None = None) -> str | None:
        """Verify an HMAC-signed session token and return its bound account ID (or None if invalid)."""
        identity = verify_session_token_identity(self._session_secret, token, claimed_account)
        return identity[0] if identity else None

    def _read_all_from_conn(self, conn: sqlite3.Connection) -> dict[str, str]:
        return {str(k): str(v) for k, v in conn.execute("SELECT key, value FROM app_state").fetchall() if not is_excluded_state_key(k)}

    def get_all_state(self) -> dict[str, str]:
        """Return all stored state keys (for internal/repository inspection)."""
        with self._lock, self._connect() as conn:
            return self._read_all_from_conn(conn)

    def _parse_accounts_and_profiles(self, state: Mapping[str, str]) -> tuple[dict[str, dict], list[dict]]:
        accs, profs = safe_json(state.get("lumen_accounts"), {}), safe_json(state.get("lumen_profiles"), [])
        clean_accs = {str(k): v for k, v in accs.items() if isinstance(v, dict) and not v.get("_deleted")} if isinstance(accs, dict) else {}
        clean_profs = [p for p in profs if isinstance(p, dict) and not p.get("_deleted")] if isinstance(profs, list) else []
        return clean_accs, clean_profs

    def _profile_ownership_sets(
        self, profiles: list[dict], caller: str, allowed_profile_ids: tuple[str, ...] | None = None,
    ) -> tuple[set[str], set[str]]:
        other_ids = {str(p.get("id") or "") for p in profiles if (p.get("accountId") or "owner") != caller} | {"default"}
        owned_ids = ({str(p.get("id") or "") for p in profiles if (p.get("accountId") or "owner") == caller} | {caller, f"tenant-{caller}"}) - other_ids
        if caller != "owner" and allowed_profile_ids:
            owned_ids &= set(allowed_profile_ids)
        return owned_ids, other_ids

    def _context_for_account(self, account_id: str | None) -> CallerContext:
        caller = str(account_id or "").strip() or "unauthenticated"
        if caller == "unauthenticated":
            return CallerContext("unauthenticated", role="unauthenticated")
        return CallerContext(caller, role="owner" if caller == "owner" else "admin")

    def resolve_caller_context(
        self, *, cf_email: str | None = None, account_header: str | None = None, session_header: str | None = None,
    ) -> CallerContext:
        """Resolve the authenticated caller identity, RBAC role, and profile scope from headers."""
        accounts, _ = self._parse_accounts_and_profiles(self.get_all_state())
        clean_cf_email = str(cf_email or "").strip().lower()
        if clean_cf_email:
            if clean_cf_email == ADMIN_EMAIL:
                return CallerContext("owner", role="owner")
            for acc_id, acc in accounts.items():
                if str(acc.get("email") or "").strip().lower() == clean_cf_email:
                    return CallerContext("unauthenticated", role="unauthenticated") if acc.get("status") == "suspended" else CallerContext(acc_id, role="admin")
            for acc_id, acc in accounts.items():
                for tu in acc.get("teamUsers") or []:
                    if isinstance(tu, dict) and str(tu.get("email") or "").strip().lower() == clean_cf_email:
                        if acc.get("status") == "suspended" or tu.get("status") == "suspended":
                            return CallerContext("unauthenticated", role="unauthenticated")
                        tu_role = str(tu.get("role") or "accountant").lower()
                        raw_pids = tuple(str(x).strip() for x in (tu.get("profileIds") or []) if str(x).strip()) if isinstance(tu.get("profileIds"), list) else ()
                        return CallerContext(acc_id, team_user_id=str(tu.get("id") or ""), role=tu_role if tu_role in VALID_TEAM_ROLES else "accountant", profile_ids=raw_pids or None)
            return CallerContext("unauthenticated", role="unauthenticated")
        clean_sess = str(session_header or "").strip()
        if not clean_sess:
            return CallerContext("unauthenticated", role="unauthenticated")
        identity = verify_session_token_identity(self._session_secret, clean_sess, str(account_header or "").strip() or "unauthenticated")
        if not identity:
            return CallerContext("unauthenticated", role="unauthenticated")
        acc_id, tu_id = identity
        if acc_id == "owner":
            return CallerContext("unauthenticated", role="unauthenticated") if tu_id else CallerContext("owner", role="owner")
        acc = accounts.get(acc_id)
        if not acc or acc.get("status") == "suspended":
            return CallerContext("unauthenticated", role="unauthenticated")
        if tu_id:
            if not acc:
                return CallerContext("unauthenticated", role="unauthenticated")
            for tu in acc.get("teamUsers") or []:
                if isinstance(tu, dict) and str(tu.get("id") or "") == tu_id:
                    if tu.get("status") == "suspended":
                        return CallerContext("unauthenticated", role="unauthenticated")
                    tu_role = str(tu.get("role") or "accountant").lower()
                    raw_pids = tuple(str(x).strip() for x in (tu.get("profileIds") or []) if str(x).strip()) if isinstance(tu.get("profileIds"), list) else ()
                    return CallerContext(acc_id, team_user_id=tu_id, role=tu_role if tu_role in VALID_TEAM_ROLES else "accountant", profile_ids=raw_pids or None)
            return CallerContext("unauthenticated", role="unauthenticated")
        return CallerContext(acc_id, role="admin")

    def resolve_caller_from_headers(self, *, cf_email: str | None = None, account_header: str | None = None, session_header: str | None = None) -> str:
        """Resolve the authenticated caller account ID from Zero Trust or request headers."""
        return self.resolve_caller_context(cf_email=cf_email, account_header=account_header, session_header=session_header).account_id

    def is_account_ai_enabled(self, account_id: str | None, *, raw_account_header: str | None = None) -> bool:
        """Return True if the resolved account is entitled to AI features (Advance, Pro, Managed Books, Owner, or Add-on)."""
        caller = str(account_id or "").strip() or "unauthenticated"
        if caller == "owner":
            return True
        if caller == "unauthenticated":
            return False
        accounts, _ = self._parse_accounts_and_profiles(self.get_all_state())
        acc = accounts.get(caller) if isinstance(accounts.get(caller), dict) else None
        if not acc:
            return False
        return normalize_plan_id(acc.get("plan") or "basic") in AI_ELIGIBLE_PLANS or bool(acc.get("aiAddon"))

    def resolve_session(self, *, cf_email: str | None = None, account_header: str | None = None, session_header: str | None = None) -> dict[str, object]:
        """Return `/api/v1/auth/session` payload preserving teamUser metadata when active."""
        ctx = self.resolve_caller_context(cf_email=cf_email, account_header=account_header, session_header=session_header)
        if not ctx.account_id or ctx.account_id == "unauthenticated":
            return {"status": "ok", "authenticated": False, "accountId": None}
        payload: dict[str, object] = {
            "status": "ok",
            "authenticated": True,
            "accountId": ctx.account_id,
            "sessionToken": self.issue_session_token(ctx.account_id, team_user_id=ctx.team_user_id),
        }
        if ctx.team_user_id:
            payload["teamUser"] = {"id": ctx.team_user_id, "role": ctx.role, "profileIds": list(ctx.profile_ids or ())}
        return payload

    def get_scoped_state(self, account_id: str | None = None, *, caller_context: CallerContext | None = None) -> dict[str, str]:
        """Return state scoped to caller account and team-user profile scope, stripping secrets."""
        ctx = caller_context or self._context_for_account(account_id)
        caller = ctx.account_id
        full = self.get_all_state()
        accounts, profiles = self._parse_accounts_and_profiles(full)
        if caller == "owner":
            out = {k: v for k, v in full.items() if k != "lumen_admin_credentials"}
            if "lumen_accounts" in out:
                out["lumen_accounts"] = json.dumps({k: strip_account_secrets(v) for k, v in accounts.items()})
            if "lumen_profiles" in out:
                out["lumen_profiles"] = json.dumps(profiles)
            return out
        if caller == "unauthenticated":
            return {"lumen_accounts": json.dumps({k: {"id": k, "email": v.get("email", ""), "status": v.get("status", "active")} for k, v in accounts.items() if v.get("email")}), "lumen_profiles": "[]"}
        owned_ids, other_ids = self._profile_ownership_sets(profiles, caller, ctx.profile_ids)
        owned_profiles = [
            p for p in profiles
            if (p.get("accountId") or "owner") == caller and (not ctx.profile_ids or str(p.get("id") or "") in owned_ids)
        ]
        scoped = {"lumen_accounts": json.dumps({caller: strip_account_secrets(accounts[caller])} if caller in accounts else {}), "lumen_profiles": json.dumps(owned_profiles)}
        if PLATFORM_INTEGRATIONS_KEY in full:
            scoped[PLATFORM_INTEGRATIONS_KEY] = full[PLATFORM_INTEGRATIONS_KEY]
        for k, v in full.items():
            if k.startswith("profile:"):
                prof_id = k[len("profile:") :].split("::", 1)[0]
                if prof_id in owned_ids and prof_id not in other_ids:
                    scoped[k] = v
        return scoped

    def mutate_state(self, set_items: Mapping[str, str] | None = None, remove_keys: list[str] | None = None, *, clear_all: bool = False) -> int:
        """Low-level state mutation helper for direct repository manipulation."""
        now, updated = datetime.now(UTC).isoformat(), 0
        with self._lock, self._connect() as conn:
            if clear_all:
                conn.execute("DELETE FROM app_state")
            for k in remove_keys or []:
                if isinstance(k, str):
                    conn.execute("DELETE FROM app_state WHERE key = ?", (k,))
            for k, v in (set_items or {}).items():
                if not is_excluded_state_key(k) and v is not None:
                    conn.execute("INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at", (str(k), str(v), now))
                    updated += 1
        return updated

    def mutate_scoped_state(
        self, account_id: str | None, set_items: Mapping[str, str] | None = None, remove_keys: list[str] | None = None,
        *, clear_all: bool = False, caller_context: CallerContext | None = None, captcha_attestation: str | None = None,
    ) -> int:
        """Atomically validate and apply tenant- and role-scoped state mutations."""
        ctx = caller_context or self._context_for_account(account_id)
        caller, raw_set, raw_rem = ctx.account_id, dict(set_items or {}), [str(k) for k in (remove_keys or []) if isinstance(k, str)]
        if caller == "unauthenticated":
            if raw_set.get("lumen_accounts") is None:
                return 0
            with self._lock, self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing_accounts, _ = self._parse_accounts_and_profiles(self._read_all_from_conn(conn))
                if (safe_acc := merge_unauth_registration(existing_accounts, str(raw_set["lumen_accounts"]), self._session_secret, captcha_attestation)) is None:
                    return 0
                conn.execute("INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at", ("lumen_accounts", safe_acc, datetime.now(UTC).isoformat()))
            return 1
        if ctx.role == "viewer":
            raise PermissionError("Read-only viewer role cannot modify workspace data.")
        is_owner = caller == "owner" and ctx.role == "owner"
        is_admin = ctx.role in ("owner", "admin")
        if not is_admin and any(k in ("lumen_accounts", "lumen_profiles") for k in (*raw_set.keys(), *raw_rem)):
            raise PermissionError("Accountant role cannot modify account or profile settings.")
        if not is_owner and any(k in (PLATFORM_INTEGRATIONS_KEY, PLATFORM_SECRETS_KEY) for k in (*raw_set.keys(), *raw_rem)):
            raise PermissionError("Only Super-Admin may modify platform integration settings.")
        now, updated = datetime.now(UTC).isoformat(), 0
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            full = self._read_all_from_conn(conn)
            existing_accounts, existing_profiles = self._parse_accounts_and_profiles(full)
            owned_prof_ids, other_prof_ids = self._profile_ownership_sets(existing_profiles, caller, ctx.profile_ids)
            deleted_acc_ids: set[str] = set()
            deleted_prof_ids: set[str] = set()
            if is_owner and "lumen_accounts" in raw_set and raw_set["lumen_accounts"] is not None:
                inc_accs = safe_json(str(raw_set["lumen_accounts"]), None)
                if isinstance(inc_accs, dict):
                    deleted_acc_ids = {str(aid) for aid, obj in inc_accs.items() if obj is None or (isinstance(obj, dict) and obj.get("_deleted"))}
                    deleted_prof_ids = {str(p.get("id")) for p in existing_profiles if str(p.get("accountId") or "") in deleted_acc_ids and p.get("id")}
            if "lumen_profiles" in raw_set and raw_set["lumen_profiles"] is not None:
                incoming_profs = safe_json(str(raw_set["lumen_profiles"]), None)
                if isinstance(incoming_profs, list):
                    for p in incoming_profs:
                        if not isinstance(p, dict) or not (pid := str(p.get("id") or "")):
                            continue
                        if is_owner and (p.get("_deleted") or str(p.get("accountId") or "") in deleted_acc_ids) or not is_owner and p.get("_deleted") and pid in owned_prof_ids and pid not in other_prof_ids:
                            deleted_prof_ids.add(pid)
                        elif (p.get("accountId") or "owner") == caller and pid not in other_prof_ids and (not ctx.profile_ids or pid in ctx.profile_ids):
                            owned_prof_ids.add(pid)
            safe_set: dict[str, str] = {}
            for k, raw_val in raw_set.items():
                if is_excluded_state_key(k) or raw_val is None:
                    continue
                if not is_owner and k in ("lumen_admin_credentials", "lumen_account_plan", PLATFORM_INTEGRATIONS_KEY, PLATFORM_SECRETS_KEY):
                    continue
                val_str = str(raw_val)
                if k == "lumen_accounts":
                    safe_acc = self._merge_accounts_mutation(existing_accounts, val_str, caller, is_owner, captcha_attestation)
                    if safe_acc is not None:
                        safe_set[k] = safe_acc
                elif k == "lumen_profiles":
                    safe_profs = self._merge_profiles_mutation(existing_profiles, val_str, caller, is_owner, clear_all, deleted_acc_ids, deleted_prof_ids, other_prof_ids)
                    if safe_profs is not None:
                        safe_set[k] = safe_profs
                elif not is_owner:
                    if k.startswith("profile:"):
                        prof_id = k[len("profile:") :].split("::", 1)[0]
                        if prof_id in owned_prof_ids and prof_id not in other_prof_ids and prof_id not in deleted_prof_ids:
                            safe_set[k] = val_str
                        elif ctx.profile_ids:
                            raise PermissionError("Access denied to unassigned company profile.")
                elif not (k.startswith("profile:") and k[len("profile:") :].split("::", 1)[0] in deleted_prof_ids):
                    safe_set[k] = val_str
            if is_owner and (deleted_acc_ids or deleted_prof_ids) and "lumen_profiles" not in safe_set:
                safe_set["lumen_profiles"] = json.dumps([p for p in existing_profiles if str(p.get("id") or "") not in deleted_prof_ids and str(p.get("accountId") or "") not in deleted_acc_ids])
            safe_remove = []
            for rk in raw_rem:
                if is_owner:
                    safe_remove.append(rk)
                elif rk.startswith("profile:"):
                    pid = rk[len("profile:") :].split("::", 1)[0]
                    if pid in owned_prof_ids and pid not in other_prof_ids:
                        safe_remove.append(rk)
                    elif ctx.profile_ids:
                        raise PermissionError("Access denied to unassigned company profile.")
            if deleted_prof_ids:
                for fk in full:
                    if fk.startswith("profile:") and fk[len("profile:") :].split("::", 1)[0] in deleted_prof_ids:
                        safe_remove.append(fk)
                        safe_set.pop(fk, None)
                for pid in deleted_prof_ids:
                    conn.execute("DELETE FROM attachments WHERE key LIKE ?", (f"{pid}::%",))
            if clear_all and is_owner:
                conn.execute("DELETE FROM app_state")
            for k in safe_remove:
                conn.execute("DELETE FROM app_state WHERE key = ?", (k,))
            for k, v in safe_set.items():
                conn.execute("INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at", (k, v, now))
                updated += 1
        return updated

    def _merge_accounts_mutation(
        self, existing_accounts: dict[str, dict], val_str: str, caller: str, is_owner: bool, captcha_attestation: str | None,
    ) -> str | None:
        incoming = safe_json(val_str, None)
        if not isinstance(incoming, dict):
            return None
        merged = dict(existing_accounts)
        for acc_id, acc_obj in incoming.items():
            if is_owner and (acc_obj is None or (isinstance(acc_obj, dict) and acc_obj.get("_deleted"))):
                merged.pop(acc_id, None)
                continue
            if not isinstance(acc_obj, dict) or acc_obj.get("_deleted") or (not is_owner and acc_id != caller):
                continue
            prev = existing_accounts.get(acc_id)
            if not isinstance(prev, dict) and (not is_owner or not is_valid_entity_id(acc_id, allow_owner=True)):
                continue
            nxt = {**(prev if isinstance(prev, dict) else {}), **acc_obj}
            nxt.pop("captchaAttestation", None)
            if isinstance(prev, dict):
                for sec_key in ("passwordHash", "salt"):
                    if (not is_owner or not acc_obj.get(sec_key)) and prev.get(sec_key):
                        nxt[sec_key] = prev[sec_key]
                if not is_owner:
                    for srv_key in ("email", "plan", "aiAddon", "addons", "status", "locked", "failedAttempts", "resetCodeHash", "resetRequestedAt", "billingStatus", "lastChargedAmount", "lastChargedAt", "trialStartedAt", "trialEndsAt", "renewalReminderSentAt", "renewalReminderMessage"):
                        if srv_key in prev:
                            nxt[srv_key] = prev[srv_key]
                        else:
                            nxt.pop(srv_key, None)
                    if isinstance(acc_obj.get("autoRenew"), bool):
                        nxt["autoRenew"] = acc_obj["autoRenew"]
                        nxt["billingStatus"] = ("active_paid" if prev.get("billingStatus") == "active_paid" or prev.get("lastChargedAt") else "trial") if acc_obj["autoRenew"] else "canceled_at_period_end"
                elif "email" in nxt and nxt["email"] is not None:
                    clean_em = str(nxt.get("email") or "").strip().lower()
                    if clean_em and clean_em in collect_reserved_emails(merged, exclude_acc_id=acc_id):
                        if "email" in prev:
                            nxt["email"] = prev["email"]
                        else:
                            nxt.pop("email", None)
                    else:
                        nxt["email"] = clean_em
            elif "email" in nxt and nxt["email"] is not None:
                clean_em = str(nxt.get("email") or "").strip().lower()
                if clean_em and clean_em in collect_reserved_emails(merged, exclude_acc_id=acc_id):
                    continue
                nxt["email"] = clean_em
            if "teamUsers" in acc_obj or (isinstance(prev, dict) and "teamUsers" in prev):
                eff_plan = nxt.get("plan") or (prev.get("plan") if isinstance(prev, dict) else "basic")
                nxt["teamUsers"] = merge_team_users(
                    prev.get("teamUsers") if isinstance(prev, dict) else [],
                    acc_obj.get("teamUsers") if "teamUsers" in acc_obj else (prev.get("teamUsers") if isinstance(prev, dict) else []),
                    eff_plan, is_owner=is_owner, blocked_emails=collect_reserved_emails(merged, exclude_acc_id=acc_id, own_email=nxt.get("email")),
                )
            merged[acc_id] = nxt
        return json.dumps(merged)

    def _merge_profiles_mutation(
        self, existing_profiles: list[dict], val_str: str, caller: str, is_owner: bool,
        clear_all: bool, deleted_acc_ids: set[str], deleted_prof_ids: set[str], other_prof_ids: set[str],
    ) -> str | None:
        incoming_profs = safe_json(val_str, None)
        if not isinstance(incoming_profs, list):
            return None
        if not is_owner:
            others = [p for p in existing_profiles if (p.get("accountId") or "owner") != caller]
            mine = [p for p in incoming_profs if isinstance(p, dict) and not p.get("_deleted") and (p.get("accountId") or "owner") == caller and str(p.get("id") or "") and str(p.get("id") or "") not in deleted_prof_ids and str(p.get("id") or "") not in other_prof_ids]
            return json.dumps([*others, *mine])
        inc_all = [p for p in incoming_profs if isinstance(p, dict)]
        del_ids = deleted_prof_ids | {str(p.get("id") or "") for p in inc_all if p.get("_deleted") or str(p.get("accountId") or "") in deleted_acc_ids}
        deleted_prof_ids.update(del_ids)
        inc_clean = [p for p in inc_all if not p.get("_deleted") and str(p.get("id") or "") not in del_ids and str(p.get("accountId") or "") not in deleted_acc_ids]
        inc_ids = {str(p.get("id") or "") for p in inc_clean} | del_ids
        preserved = [] if clear_all else [p for p in existing_profiles if (p.get("accountId") or "owner") != "owner" and str(p.get("id") or "") not in inc_ids and str(p.get("accountId") or "") not in deleted_acc_ids]
        return json.dumps([*inc_clean, *preserved])

    def verify_login(self, email: object, password: object) -> dict[str, object]:
        """Verify email and password against stored PBKDF2-HMAC-SHA256 credentials with 3x lockout."""
        full = self.get_all_state()
        accounts, _ = self._parse_accounts_and_profiles(full)
        return verify_login_impl(full, accounts, email, password, self._session_secret, lambda m: self.mutate_state({"lumen_accounts": json.dumps(m)}))

    def request_password_reset(self, email: object) -> dict[str, object]:
        """Generate a 6-digit password reset code for primary account or team user."""
        accounts, _ = self._parse_accounts_and_profiles(self.get_all_state())
        return request_password_reset_impl(accounts, email, lambda m: self.mutate_state({"lumen_accounts": json.dumps(m)}))

    def confirm_password_reset(self, email: object, code: object, new_password: object) -> dict[str, object]:
        """Verify reset code, update PBKDF2-SHA256 password hash, and unlock the account or team user."""
        accounts, _ = self._parse_accounts_and_profiles(self.get_all_state())
        return confirm_password_reset_impl(accounts, email, code, new_password, lambda m: self.mutate_state({"lumen_accounts": json.dumps(m)}))

    def save_payment_method(self, email: object, *, caller_account: str | None = "owner", caller_context: CallerContext | None = None, **kwargs: object) -> dict[str, object]:
        """Store masked payment card metadata for an account and process payment if trial ended."""
        accounts, _ = self._parse_accounts_and_profiles(self.get_all_state())
        ctx = caller_context or self._context_for_account(caller_account)
        return save_payment_method_impl(accounts, email, ctx, lambda m: self.mutate_state({"lumen_accounts": json.dumps(m)}), **kwargs)

    def send_trial_renewal_reminder(self, email: object, caller_account: str | None = "owner", *, caller_context: CallerContext | None = None) -> dict[str, object]:
        """Dispatch a pre-renewal email notification for an active 15-day free trial account."""
        accounts, _ = self._parse_accounts_and_profiles(self.get_all_state())
        ctx = caller_context or self._context_for_account(caller_account)
        return send_trial_reminder_impl(accounts, email, ctx, lambda m: self.mutate_state({"lumen_accounts": json.dumps(m)}))

    def process_trial_renewal(self, email: object, caller_account: str | None = "owner", *, caller_context: CallerContext | None = None) -> dict[str, object]:
        """Auto-deduct subscription fee on stored payment method when trial completes and autoRenew is active."""
        accounts, _ = self._parse_accounts_and_profiles(self.get_all_state())
        ctx = caller_context or self._context_for_account(caller_account)
        return process_trial_renewal_impl(accounts, email, ctx, lambda m: self.mutate_state({"lumen_accounts": json.dumps(m)}))

    def _can_access_attachment(self, conn: sqlite3.Connection, att_key: str, caller_ctx: CallerContext) -> bool:
        clean_key, caller = str(att_key or "").strip(), caller_ctx.account_id
        if not clean_key or caller == "unauthenticated":
            return False
        if caller == "owner" and caller_ctx.role == "owner":
            return True
        prof_id = clean_key.split("::", 1)[0]
        if prof_id == "default":
            return False
        row = conn.execute("SELECT value FROM app_state WHERE key = 'lumen_profiles'").fetchone()
        raw_profs = safe_json(str(row[0]) if row else "[]", [])
        profiles = [p for p in raw_profs if isinstance(p, dict) and not p.get("_deleted")] if isinstance(raw_profs, list) else []
        owned_ids, other_ids = self._profile_ownership_sets(profiles, caller, caller_ctx.profile_ids)
        return prof_id in owned_ids and prof_id not in other_ids

    def get_attachment(self, key: str, account_id: str | None = "owner", *, caller_context: CallerContext | None = None) -> str | None:
        """Return base64 attachment payload if caller is authorized to read `key`."""
        if not key:
            return None
        ctx = caller_context or self._context_for_account(account_id)
        with self._lock, self._connect() as conn:
            if not self._can_access_attachment(conn, str(key), ctx):
                return None
            row = conn.execute("SELECT data FROM attachments WHERE key = ?", (str(key),)).fetchone()
            return str(row[0]) if row else None

    def put_attachments(self, items: Mapping[str, str] | None = None, remove_keys: list[str] | None = None, account_id: str | None = "owner", *, caller_context: CallerContext | None = None) -> int:
        """Store or remove attachments scoped to caller account and profile scope."""
        ctx = caller_context or self._context_for_account(account_id)
        if ctx.role == "viewer":
            raise PermissionError("Read-only viewer role cannot modify attachments.")
        now, updated = datetime.now(UTC).isoformat(), 0
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for k in remove_keys or []:
                if isinstance(k, str) and self._can_access_attachment(conn, k, ctx):
                    conn.execute("DELETE FROM attachments WHERE key = ?", (k,))
            for k, data in (items or {}).items():
                if isinstance(k, str) and k and isinstance(data, str) and data and self._can_access_attachment(conn, k, ctx):
                    conn.execute("INSERT INTO attachments (key, data, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at", (k, data, now))
                    updated += 1
        return updated

    def submit_einvoice(self, payload: Mapping[str, object], caller_account: str | None = "owner", *, caller_context: CallerContext | None = None) -> dict[str, object]:
        """Validate and clear an outbound PINT-AE UBL 2.1 E-Invoice (380) or Credit Note (381)."""
        import einvoice_service
        return einvoice_service.submit_einvoice(self, payload, caller_account=caller_account, caller_context=caller_context)

    def handle_einvoice_webhook(self, payload: Mapping[str, object]) -> dict[str, object]:
        """Process an asynchronous delivery / FTA clearance webhook notification from the Peppol ASP."""
        import einvoice_service
        return einvoice_service.handle_einvoice_webhook(self, payload)

    def receive_inbound_einvoice(self, payload: Mapping[str, object], caller_account: str | None = "owner", *, caller_context: CallerContext | None = None) -> dict[str, object]:
        """Parse an inbound Peppol PINT-AE UBL 2.1 supplier invoice XML and save it into the tenant's ledger."""
        import einvoice_service
        return einvoice_service.receive_inbound_einvoice(self, payload, caller_account=caller_account, caller_context=caller_context)


def resolve_default_state_db_path(explicit_path: str | None = None) -> Path:
    """Resolve the SQLite database file path without side effects."""
    if cleaned := (explicit_path or "").strip():
        return Path(cleaned)
    if any(m in sys.modules for m in ("unittest", "pytest", "behave")):
        tmp_db = Path(tempfile.gettempdir()) / f"lumen_books_test_{os.getpid()}.sqlite3"
        atexit.register(lambda p=tmp_db: p.unlink(missing_ok=True))
        return tmp_db
    prod_dir = Path("/root/.gemini")
    return (prod_dir if prod_dir.is_dir() and os.access(prod_dir, os.W_OK) else Path(tempfile.gettempdir())) / "lumen_books_state.sqlite3"
