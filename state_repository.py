"""Multi-tenant SQLite state and attachment repository with PBKDF2-HMAC-SHA256 authentication."""

from __future__ import annotations

import atexit
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading

LOCAL_ONLY_KEYS = frozenset({
    "lumen_lang",
    "lumen_sidebar_collapsed",
    "probe",
    "lumen_current_account",
    "lumen_active_profile",
    "lumen_session_token",
    "lumen.advisorOrigin",
    "lumen.returnView",
})

ADMIN_EMAIL = "admin@lumenconsultancy.net"
PBKDF2_ITERATIONS = 120000
DEFAULT_ADMIN_SALT = "4c756d656e41646d696e53616c743236"
DEFAULT_ADMIN_HASH = (
    "pbkdf2_sha256$120000$70663afeba18d22eefd9f653155db1ccbb1a28718290cb662da2a408aceee2b4"
)

_MIGRATION_SQL_PATH = Path(__file__).resolve().parent / "migrations" / "0001_initial_schema.sql"


def is_excluded_state_key(key: str) -> bool:
    """Return True if `key` belongs strictly to browser-local UI config or session pointers."""
    return (
        not isinstance(key, str)
        or not key
        or key in LOCAL_ONLY_KEYS
        or key.startswith("lumen_table_page_size:")
    )


def compute_password_hash(password: str, salt: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Derive a salted PBKDF2-HMAC-SHA256 digest formatted as `pbkdf2_sha256$<iterations>$<hex>`."""
    clean_iters = max(int(iterations), 1)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        str(salt or "").encode("utf-8"),
        clean_iters,
    ).hex()
    return f"pbkdf2_sha256${clean_iters}${derived}"


def verify_password_hash(password: str, salt: str, stored_hash: str) -> bool:
    """Verify `password` against `stored_hash` (PBKDF2-HMAC-SHA256 or legacy salted SHA-256)."""
    if not stored_hash or not salt:
        return False
    target = str(stored_hash)
    clean_salt = str(salt)
    if target.startswith("pbkdf2_sha256$"):
        parts = target.split("$")
        iters = int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else PBKDF2_ITERATIONS
        expected = compute_password_hash(password, clean_salt, iters)
    else:
        expected = hashlib.sha256(f"{clean_salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected.encode("utf-8"), target.encode("utf-8"))


def strip_account_secrets(acc: Mapping[str, object]) -> dict[str, object]:
    """Return a shallow copy of an account dictionary with `passwordHash` and `salt` removed."""
    return {k: v for k, v in acc.items() if k not in ("passwordHash", "salt")}


def safe_json(raw: str | None, fallback: object) -> object:
    """Parse JSON string `raw`, returning `fallback` on empty or malformed JSON."""
    try:
        return json.loads(raw or "") if raw else fallback
    except json.JSONDecodeError:
        return fallback


class LumenStateRepository:
    """Thread-safe SQLite repository for multi-tenant bookkeeping state, auth verification, and attachments."""

    def __init__(self, db_path: Path, *, session_secret: str | None = None) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        raw_secret = session_secret or f"lumen-session-key-{DEFAULT_ADMIN_SALT}"
        self._session_secret = raw_secret.encode("utf-8")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_sql = _MIGRATION_SQL_PATH.read_text(encoding="utf-8")
        with self._lock, self._connect() as conn:
            conn.executescript(schema_sql)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def issue_session_token(self, account_id: str) -> str:
        """Issue an HMAC-SHA256 signed session token bound to `account_id`."""
        clean_acc = str(account_id or "").strip()
        nonce = secrets.token_hex(12)
        mac = hmac.new(self._session_secret, f"{clean_acc}:{nonce}".encode("utf-8"), hashlib.sha256).hexdigest()
        return f"sess.{clean_acc}.{nonce}.{mac}"

    def verify_session_token(self, token: str | None, claimed_account: str | None = None) -> str | None:
        """Verify an HMAC-signed session token and return its bound account ID (or None if invalid)."""
        parts = str(token or "").strip().split(".")
        if len(parts) != 4 or parts[0] != "sess" or not parts[1] or not parts[2] or not parts[3]:
            return None
        _, token_acc, nonce, provided_mac = parts
        expected_mac = hmac.new(self._session_secret, f"{token_acc}:{nonce}".encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided_mac.encode("utf-8"), expected_mac.encode("utf-8")):
            return None
        if claimed_account and claimed_account != "unauthenticated":
            if token_acc != claimed_account and token_acc != "owner":
                return None
        return token_acc

    def _read_all_from_conn(self, conn: sqlite3.Connection) -> dict[str, str]:
        return {
            str(k): str(v)
            for k, v in conn.execute("SELECT key, value FROM app_state").fetchall()
            if not is_excluded_state_key(k)
        }

    def get_all_state(self) -> dict[str, str]:
        """Return all stored state keys (for internal/repository inspection)."""
        with self._lock, self._connect() as conn:
            return self._read_all_from_conn(conn)

    def _parse_accounts_and_profiles(self, state: Mapping[str, str]) -> tuple[dict[str, dict], list[dict]]:
        accs = safe_json(state.get("lumen_accounts"), {})
        profs = safe_json(state.get("lumen_profiles"), [])
        clean_accs = {str(k): v for k, v in accs.items() if isinstance(v, dict)} if isinstance(accs, dict) else {}
        clean_profs = [p for p in profs if isinstance(p, dict)] if isinstance(profs, list) else []
        return clean_accs, clean_profs

    def _profile_ownership_sets(self, profiles: list[dict], caller: str) -> tuple[set[str], set[str]]:
        other_ids = {str(p.get("id") or "") for p in profiles if (p.get("accountId") or "owner") != caller} | {"default"}
        owned_ids = (
            {str(p.get("id") or "") for p in profiles if (p.get("accountId") or "owner") == caller}
            | {caller, f"tenant-{caller}"}
        ) - other_ids
        return owned_ids, other_ids

    def resolve_caller_from_headers(
        self,
        *,
        cf_email: str | None = None,
        account_header: str | None = None,
        session_header: str | None = None,
    ) -> str:
        """Resolve the authenticated caller account ID from Zero Trust or request headers."""
        with self._lock, self._connect() as conn:
            full = self._read_all_from_conn(conn)
        accounts, _ = self._parse_accounts_and_profiles(full)

        clean_cf_email = str(cf_email or "").strip().lower()
        if clean_cf_email:
            if clean_cf_email == ADMIN_EMAIL:
                return "owner"
            for acc_id, acc in accounts.items():
                if str(acc.get("email") or "").strip().lower() == clean_cf_email:
                    return acc_id if acc.get("status") != "suspended" else "unauthenticated"
            return "unauthenticated"

        claimed = str(account_header or "").strip() or "unauthenticated"
        clean_sess = str(session_header or "").strip()
        if clean_sess and not self.verify_session_token(clean_sess, claimed):
            return "unauthenticated"
        return claimed

    def resolve_session(
        self,
        *,
        cf_email: str | None = None,
        account_header: str | None = None,
        session_header: str | None = None,
    ) -> dict[str, object]:
        """Return `/api/v1/auth/session` payload for Cloudflare Zero Trust Access or active session."""
        caller = self.resolve_caller_from_headers(
            cf_email=cf_email, account_header=account_header, session_header=session_header
        )
        if not caller or caller == "unauthenticated":
            return {"status": "ok", "authenticated": False, "accountId": None}
        return {
            "status": "ok",
            "authenticated": True,
            "accountId": caller,
            "sessionToken": self.issue_session_token(caller),
        }

    def get_scoped_state(self, account_id: str | None = None) -> dict[str, str]:
        """Return state scoped to `account_id`, always stripping `passwordHash` and `salt`."""
        caller = str(account_id or "").strip() or "unauthenticated"
        full = self.get_all_state()
        accounts, profiles = self._parse_accounts_and_profiles(full)

        if caller == "owner":
            out = {k: v for k, v in full.items() if k != "lumen_admin_credentials"}
            if "lumen_accounts" in out:
                out["lumen_accounts"] = json.dumps({k: strip_account_secrets(v) for k, v in accounts.items()})
            return out

        if caller == "unauthenticated":
            public_accs = {
                k: {"id": k, "email": v.get("email", ""), "status": v.get("status", "active")}
                for k, v in accounts.items()
                if v.get("email")
            }
            return {"lumen_accounts": json.dumps(public_accs), "lumen_profiles": "[]"}

        owned_profiles = [p for p in profiles if (p.get("accountId") or "owner") == caller]
        owned_ids, _ = self._profile_ownership_sets(profiles, caller)
        scoped = {
            "lumen_accounts": json.dumps(
                {caller: strip_account_secrets(accounts[caller])} if caller in accounts else {}
            ),
            "lumen_profiles": json.dumps(owned_profiles),
        }
        for k, v in full.items():
            if k.startswith("profile:") and k[len("profile:") :].split("::", 1)[0] in owned_ids:
                scoped[k] = v
        return scoped

    def mutate_state(
        self,
        set_items: Mapping[str, str] | None = None,
        remove_keys: list[str] | None = None,
        *,
        clear_all: bool = False,
    ) -> int:
        """Low-level state mutation helper for direct repository manipulation."""
        now = datetime.now(timezone.utc).isoformat()
        updated = 0
        with self._lock, self._connect() as conn:
            if clear_all:
                conn.execute("DELETE FROM app_state")
            for k in remove_keys or []:
                if isinstance(k, str):
                    conn.execute("DELETE FROM app_state WHERE key = ?", (k,))
            for k, v in (set_items or {}).items():
                if not is_excluded_state_key(k) and v is not None:
                    conn.execute(
                        "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                        (str(k), str(v), now),
                    )
                    updated += 1
        return updated

    def mutate_scoped_state(
        self,
        account_id: str | None,
        set_items: Mapping[str, str] | None = None,
        remove_keys: list[str] | None = None,
        *,
        clear_all: bool = False,
    ) -> int:
        """Atomically validate and apply tenant-scoped state mutations in a single SQLite transaction."""
        caller = str(account_id or "").strip() or "unauthenticated"
        if caller == "unauthenticated":
            return 0
        is_owner = caller == "owner"
        now = datetime.now(timezone.utc).isoformat()
        updated = 0

        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            full = self._read_all_from_conn(conn)
            existing_accounts, existing_profiles = self._parse_accounts_and_profiles(full)
            owned_prof_ids, other_prof_ids = self._profile_ownership_sets(existing_profiles, caller)

            raw_set = dict(set_items or {})
            if "lumen_profiles" in raw_set and raw_set["lumen_profiles"] is not None:
                incoming_profs = safe_json(str(raw_set["lumen_profiles"]), None)
                if isinstance(incoming_profs, list):
                    for p in incoming_profs:
                        if isinstance(p, dict) and (p.get("accountId") or "owner") == caller:
                            pid = str(p.get("id") or "")
                            if pid and pid not in other_prof_ids:
                                owned_prof_ids.add(pid)

            safe_set: dict[str, str] = {}
            for k, raw_val in raw_set.items():
                if is_excluded_state_key(k) or raw_val is None:
                    continue
                if not is_owner and k in ("lumen_admin_credentials", "lumen_account_plan"):
                    continue
                val_str = str(raw_val)
                if k == "lumen_accounts":
                    incoming = safe_json(val_str, None)
                    if not isinstance(incoming, dict):
                        continue
                    merged = dict(existing_accounts)
                    for acc_id, acc_obj in incoming.items():
                        if not isinstance(acc_obj, dict) or (not is_owner and acc_id != caller):
                            continue
                        prev = existing_accounts.get(acc_id)
                        nxt = {**(prev if isinstance(prev, dict) else {}), **acc_obj}
                        if isinstance(prev, dict):
                            for sec_key in ("passwordHash", "salt"):
                                if not acc_obj.get(sec_key) and prev.get(sec_key):
                                    nxt[sec_key] = prev[sec_key]
                            if not is_owner:
                                nxt["plan"] = prev.get("plan", "basic")
                                nxt["status"] = prev.get("status", "active")
                        elif not is_owner:
                            req_plan = str(acc_obj.get("plan") or "basic").strip().lower()
                            if req_plan in ("advance", "premium") and not nxt.get("requestedPlan"):
                                nxt["requestedPlan"] = req_plan
                            nxt["plan"] = "basic"
                            nxt["status"] = "active"
                        merged[acc_id] = nxt
                    safe_set[k] = json.dumps(merged)
                elif k == "lumen_profiles":
                    incoming_profs = safe_json(val_str, None)
                    if not isinstance(incoming_profs, list):
                        continue
                    if not is_owner:
                        others = [p for p in existing_profiles if (p.get("accountId") or "owner") != caller]
                        mine = [
                            p
                            for p in incoming_profs
                            if isinstance(p, dict)
                            and (p.get("accountId") or "owner") == caller
                            and str(p.get("id") or "")
                            and str(p.get("id") or "") not in other_prof_ids
                        ]
                        safe_set[k] = json.dumps([*others, *mine])
                    else:
                        inc_clean = [p for p in incoming_profs if isinstance(p, dict)]
                        inc_ids = {str(p.get("id") or "") for p in inc_clean}
                        preserved_tenants = (
                            []
                            if clear_all
                            else [
                                p
                                for p in existing_profiles
                                if (p.get("accountId") or "owner") != "owner"
                                and str(p.get("id") or "") not in inc_ids
                            ]
                        )
                        safe_set[k] = json.dumps([*inc_clean, *preserved_tenants])
                elif not is_owner:
                    if k.startswith("profile:"):
                        prof_id = k[len("profile:") :].split("::", 1)[0]
                        if prof_id in owned_prof_ids and prof_id not in other_prof_ids:
                            safe_set[k] = val_str
                else:
                    safe_set[k] = val_str

            safe_remove = [
                str(k)
                for k in (remove_keys or [])
                if isinstance(k, str)
                and (
                    is_owner
                    or (
                        k.startswith("profile:")
                        and k[len("profile:") :].split("::", 1)[0] in owned_prof_ids
                        and k[len("profile:") :].split("::", 1)[0] not in other_prof_ids
                    )
                )
            ]

            if clear_all and is_owner:
                conn.execute("DELETE FROM app_state")
            for k in safe_remove:
                conn.execute("DELETE FROM app_state WHERE key = ?", (k,))
            for k, v in safe_set.items():
                conn.execute(
                    "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                    (k, v, now),
                )
                updated += 1
        return updated

    def verify_login(self, email: str, password: str) -> dict[str, object]:
        """Verify email and password against stored PBKDF2-HMAC-SHA256 credentials."""
        clean_email = str(email or "").strip().lower()
        pwd = str(password or "")
        if not clean_email or not pwd:
            return {"ok": False, "error": "Invalid credentials."}
        full = self.get_all_state()
        if clean_email == ADMIN_EMAIL:
            adm = safe_json(full.get("lumen_admin_credentials"), {})
            has_custom = isinstance(adm, dict) and adm.get("salt") and adm.get("passwordHash")
            salt = str(adm["salt"]) if has_custom else DEFAULT_ADMIN_SALT
            target_hash = str(adm["passwordHash"]) if has_custom else DEFAULT_ADMIN_HASH
            if verify_password_hash(pwd, salt, target_hash):
                return {"ok": True, "accountId": "owner", "sessionToken": self.issue_session_token("owner")}
            return {"ok": False, "error": "Invalid admin credentials."}

        accounts, _ = self._parse_accounts_and_profiles(full)
        for acc_id, acc in accounts.items():
            if str(acc.get("email") or "").strip().lower() == clean_email:
                if acc.get("status") == "suspended":
                    return {"ok": False, "error": "Account is suspended."}
                if verify_password_hash(pwd, str(acc.get("salt") or ""), str(acc.get("passwordHash") or "")):
                    return {"ok": True, "accountId": acc_id, "sessionToken": self.issue_session_token(acc_id)}
                return {"ok": False, "error": "Incorrect email or password."}
        return {"ok": False, "error": "Incorrect email or password."}

    def _can_access_attachment(self, conn: sqlite3.Connection, att_key: str, account_id: str | None) -> bool:
        clean_key = str(att_key or "").strip()
        caller = str(account_id or "").strip() or "unauthenticated"
        if not clean_key or caller == "unauthenticated":
            return False
        if caller == "owner":
            return True
        prof_id = clean_key.split("::", 1)[0]
        if prof_id == "default":
            return False
        row = conn.execute("SELECT value FROM app_state WHERE key = 'lumen_profiles'").fetchone()
        raw_profs = safe_json(str(row[0]) if row else "[]", [])
        profiles = [p for p in raw_profs if isinstance(p, dict)] if isinstance(raw_profs, list) else []
        owned_prof_ids, other_prof_ids = self._profile_ownership_sets(profiles, caller)
        return prof_id in owned_prof_ids and prof_id not in other_prof_ids

    def get_attachment(self, key: str, account_id: str | None = "owner") -> str | None:
        """Return base64 attachment payload if `account_id` is authorized to read `key`."""
        if not key:
            return None
        with self._lock, self._connect() as conn:
            if not self._can_access_attachment(conn, str(key), account_id):
                return None
            row = conn.execute("SELECT data FROM attachments WHERE key = ?", (str(key),)).fetchone()
            return str(row[0]) if row else None

    def put_attachments(
        self,
        items: Mapping[str, str] | None = None,
        remove_keys: list[str] | None = None,
        account_id: str | None = "owner",
    ) -> int:
        """Store or remove attachments scoped to `account_id`."""
        now = datetime.now(timezone.utc).isoformat()
        updated = 0
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for k in remove_keys or []:
                if isinstance(k, str) and self._can_access_attachment(conn, k, account_id):
                    conn.execute("DELETE FROM attachments WHERE key = ?", (k,))
            for k, data in (items or {}).items():
                if isinstance(k, str) and k and isinstance(data, str) and data:
                    if self._can_access_attachment(conn, k, account_id):
                        conn.execute(
                            "INSERT INTO attachments (key, data, updated_at) VALUES (?, ?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
                            (k, data, now),
                        )
                        updated += 1
        return updated


def resolve_default_state_db_path(explicit_path: str | None = None) -> Path:
    """Resolve the SQLite database file path without side effects."""
    cleaned = (explicit_path or "").strip()
    if cleaned:
        return Path(cleaned)
    if any(m in sys.modules for m in ("unittest", "pytest", "behave")):
        tmp_db = Path(tempfile.gettempdir()) / f"lumen_books_test_{os.getpid()}.sqlite3"
        atexit.register(lambda p=tmp_db: p.unlink(missing_ok=True))
        return tmp_db
    prod_dir = Path("/root/.gemini")
    base = prod_dir if prod_dir.is_dir() and os.access(prod_dir, os.W_OK) else Path(tempfile.gettempdir())
    return base / "lumen_books_state.sqlite3"
