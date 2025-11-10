# app/services/storage_gcp.py
"""
GCP storage backend for Makistry.

Drop‑in replacement for the current Azure-backed `app/services/storage.py`.
It keeps the *same public function names* so the rest of the codebase can
continue to `from app.services import storage` and work unchanged.

Backed by:
  • Firestore (Native mode) — collections: identity, operations, artifacts, chat_history
  • Cloud Storage — bucket for CAD files / large blobs

Notes
-----
• Firestore has no partitions; we model the same data using document fields
  and create composite indexes where needed.
• We store `version` as an integer for proper ordering. If a previous
  document has a non‑int version, we coerce to 0 when computing `next_version`.
• Timestamps: use Firestore `Timestamp` (serverTimestamp) in `ts` fields.
  For JSON returned to the UI, you may still format as ISO8601 if needed.
• Signed URLs: Cloud Storage V4 signed URLs, max 7 days validity. For STL
  viewers, 24 hours (86,400 s) is typical.
"""
from __future__ import annotations

import datetime as _dt
import json, uuid, bcrypt, tempfile
from pathlib import Path
from typing import Any, Dict, Optional, List
import gzip, shutil

import jwt  # PyJWT

from google.cloud import firestore  # type: ignore
from google.cloud import storage as gcs  # type: ignore
from google.api_core.datetime_helpers import DatetimeWithNanoseconds  # type: ignore
from app.services.auth import _sign
from app.services.gcp_clients import get_storage_client, get_firestore_client
import os
from google.auth import default as google_auth_default

from app.core.config import settings
import math
from google.cloud.firestore_v1 import FieldFilter
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("America/Chicago")

# ───────── Credits & usage constants ─────────
TOKENS_PER_CREDIT = 10_000
PROFIT_FACTOR     = 1.25  # multiply raw tokens by this before conversion

PLAN_CONFIG = {
    "free": {"daily": 5,  "monthly_cap": 50,  "bank_cap": 10},
    "plus": {"daily": 15, "monthly_cap": 200, "bank_cap": 30},
    "pro":  {"daily": 30, "monthly_cap": 500, "bank_cap": 50},
}

def _pct(n, d):
    try:
        return (float(n) / float(d)) * 100.0 if d else 0.0
    except Exception:
        return 0.0

def some_fn():
    db = get_firestore_client()
    bucket = get_storage_client().bucket("makistry")

def _today_local_iso() -> str:
    return _dt.datetime.now(LOCAL_TZ).date().isoformat() 

def _month_key_from_day(day_iso: str) -> str:
    return f"m:{day_iso[:7]}"

# ───────── Action caps (non-credit limits) ─────────
# None == Unlimited, 0 == Not allowed
ACTION_LIMITS = {
    "free": {"stl_monthly": 10, "step_monthly": 5,  "projects_weekly": 5,  "private_projects": False},
    "plus": {"stl_monthly": 20, "step_monthly": 10, "projects_weekly": 20, "private_projects": False},
    "pro":  {"stl_monthly": None, "step_monthly": None, "projects_weekly": None, "private_projects": True},
}

def _week_key_from_day(day_iso: str) -> str:
    d = _dt.date.fromisoformat(day_iso)
    y, w, _ = d.isocalendar()
    return f"w:{y}-{w:02d}"

def _next_local_monday_iso() -> str:
    now = _dt.datetime.now(LOCAL_TZ)
    # Monday=0 in weekday(); we want next Monday 00:00 local
    days_ahead = (7 - now.weekday()) % 7 or 7
    nxt = _dt.datetime.combine((now + _dt.timedelta(days=days_ahead)).date(), _dt.time.min, LOCAL_TZ)
    return nxt.isoformat()

def _action_caps_for_plan(plan: str) -> dict:
    return ACTION_LIMITS.get((plan or "free").lower(), ACTION_LIMITS["free"])

def action_usage_snapshot(user_id: str) -> dict:
    """Return monthly STL/STEP counts and weekly new-project count + caps + reset times."""
    ref_q = C_IDENTITY.where(filter=FieldFilter("userID", "==", user_id)).limit(1).get()
    if not ref_q:
        raise RuntimeError("Identity not found")
    doc = ref_q[0].to_dict() or {}

    day_iso = _today_local_iso()
    mkey    = _month_key_from_day(day_iso)
    wkey    = _week_key_from_day(day_iso)

    au = doc.get("actionUsage") or {}
    mon_entry  = dict(au.get(mkey) or {})
    week_entry = dict(au.get(wkey) or {})

    used_stl  = int(mon_entry.get("stl", 0))
    used_step = int(mon_entry.get("step", 0))
    used_proj = int(week_entry.get("projects", 0))

    plan = (doc.get("plan") or "free").lower()
    caps = _action_caps_for_plan(plan)

    def _cap(v):
        return None if v is None else int(v)

    return {
        "plan": plan,
        "month": {
            "stl":  {"used": used_stl,  "cap": _cap(caps["stl_monthly"]),  "resetAtISO": _month_end_local_iso(day_iso)},
            "step": {"used": used_step, "cap": _cap(caps["step_monthly"]), "resetAtISO": _month_end_local_iso(day_iso)},
        },
        "week": {
            "projects": {"used": used_proj, "cap": _cap(caps["projects_weekly"]), "resetAtISO": _next_local_monday_iso()},
        },
        "features": {"private_projects": bool(caps["private_projects"])},
    }

def check_action_allowed(user_id: str, action: str) -> tuple[bool, dict]:
    """
    action in {"export_stl", "export_step", "project_create"}
    Returns (allowed, snapshot_dict)
    """
    snap = action_usage_snapshot(user_id)

    if action == "export_stl":
        cap = snap["month"]["stl"]["cap"]
        return (True if cap is None else snap["month"]["stl"]["used"] < cap), snap

    if action == "export_step":
        cap = snap["month"]["step"]["cap"]
        return (True if cap is None else snap["month"]["step"]["used"] < cap), snap

    if action == "project_create":
        cap = snap["week"]["projects"]["cap"]
        return (True if cap is None else snap["week"]["projects"]["used"] < cap), snap

    return False, snap

@firestore.transactional
def _txn_apply_action_usage(txn, user_id: str, action: str, amount: int = 1):
    """Increment action counters atomically and bump usageTick so UI listeners refresh."""
    q = C_IDENTITY.where(filter=FieldFilter("userID", "==", user_id)).limit(1).stream(transaction=txn)
    snap = next(q, None)
    if not snap:
        return
    ref = snap.reference
    doc = snap.to_dict() or {}

    au = dict(doc.get("actionUsage") or {})
    day_iso = _today_local_iso()
    mkey    = _month_key_from_day(day_iso)
    wkey    = _week_key_from_day(day_iso)

    mon_entry  = dict(au.get(mkey) or {})
    week_entry = dict(au.get(wkey) or {})

    if action == "export_stl":
        mon_entry["stl"] = int(mon_entry.get("stl", 0)) + int(amount)
        au[mkey] = mon_entry
    elif action == "export_step":
        mon_entry["step"] = int(mon_entry.get("step", 0)) + int(amount)
        au[mkey] = mon_entry
    elif action == "project_create":
        week_entry["projects"] = int(week_entry.get("projects", 0)) + int(amount)
        au[wkey] = week_entry

    txn.update(ref, _fs_safe({
        "actionUsage": au,
        "usageTick": firestore.Increment(1),
        "lastUsageAt": _server_ts(),
    }))

def consume_action(user_id: str, action: str, amount: int = 1):
    _txn_apply_action_usage(firestore.Transaction(_fs), user_id, action, amount)


def _credits_from_tokens(tokens: int | float) -> int:
    # 1.15 profit factor applied BEFORE converting; round to nearest whole credit
    return int(round((float(tokens) * PROFIT_FACTOR) / TOKENS_PER_CREDIT))

def _next_local_midnight_iso() -> str:
    now = _dt.datetime.now(LOCAL_TZ)
    nxt = _dt.datetime.combine(now.date() + _dt.timedelta(days=1), _dt.time.min, LOCAL_TZ)
    return nxt.isoformat()

def _month_end_local_iso(day_iso: str | None = None) -> str:
    d = _dt.date.fromisoformat(day_iso) if day_iso else _dt.datetime.now(LOCAL_TZ).date()
    nxt = _dt.date(d.year + (1 if d.month == 12 else 0), 1 if d.month == 12 else d.month + 1, 1)
    eom = nxt - _dt.timedelta(days=1)
    # return end-of-day midnight ISO in local tz for UI “resets at”
    eom_midnight = _dt.datetime.combine(eom + _dt.timedelta(days=1), _dt.time.min, LOCAL_TZ)
    return eom_midnight.isoformat()


_SIGN_TTL  = 7 * 24 * 3600          # 7 days
_REFRESH_IF_LEEWAY = 3600           # renew 1 h before expiry

# ───────── URL cache helpers ─────────
def _need_refresh(meta: dict) -> bool:
    """Return True if we must mint a new signed URL."""
    exp = meta.get("previewExp")
    if exp is None:
        return True                      # never signed before
    # `exp` is epoch seconds (int)
    return (int(_dt.datetime.utcnow().timestamp()) + _REFRESH_IF_LEEWAY) >= int(exp)

def _sign_thumbnail(project_id: str, path: str) -> tuple[str, int]:
    """Return (url, expires_epoch).  *No* network calls."""
    blob = _bucket.blob(path)
    url  = _signed_url_v4(blob, _SIGN_TTL, "GET")
    expires = int(_dt.datetime.utcnow().timestamp()) + _SIGN_TTL
    return url, expires

def _fs_safe(value):
    """Recursively convert value to Firestore-acceptable types."""
    # primitives
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value

    # ✅ Preserve Firestore server timestamp sentinel
    if value is firestore.SERVER_TIMESTAMP:
        return value

    # ✅ Preserve datetime / Firestore timestamp types
    if isinstance(value, (_dt.datetime, DatetimeWithNanoseconds)):
        return value

    # tuples -> lists, lists
    if isinstance(value, (list, tuple)):
        return [_fs_safe(v) for v in value]

    # dict / mapping
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            ks = str(k)
            if ks == "__name__":
                ks = "_name"
            out[ks] = _fs_safe(v)
        return out

    # numpy types (optional import)
    try:
        import numpy as np  # type: ignore
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            f = float(value)
            return None if math.isnan(f) or math.isinf(f) else f
        if isinstance(value, (np.ndarray,)):
            return [_fs_safe(x) for x in value.tolist()]
    except Exception:
        pass

    # fallback
    return str(value)


# ───────────────────────── Clients ─────────────────────────
# ADC is recommended. Ensure GOOGLE_APPLICATION_CREDENTIALS is set in env for local dev.
_fs: firestore.Client = get_firestore_client()
_gcs: gcs.Client = get_storage_client()
_bucket = _gcs.bucket(settings.gcs_bucket)

# Collections
C_IDENTITY = _fs.collection("identity")
C_OPER     = _fs.collection("operations")
C_ART      = _fs.collection("artifacts")
C_CHAT     = _fs.collection("chat_history")
C_META     = _fs.collection("projects_meta")

# ───────────────────────── Helpers ─────────────────────────
def LIKED_USERS(pid: str):
    return C_META.document(pid).collection("liked_users")

def _hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def _verify_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat()

def _server_ts():  # Firestore server timestamp sentinel
    return firestore.SERVER_TIMESTAMP

def _version_to_int(v) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        num = "".join(ch for ch in v if ch.isdigit())
        return int(num) if num else 0
    return 0

def _identity_ref_by_user_id(user_id: str):
    # First, try userID match
    q = C_IDENTITY.where(filter=FieldFilter("userID", "==", user_id)).limit(1).get()
    if q:
        return q[0].reference, q[0].to_dict() or {}
    # Fallback: if sub looks like an email, try the doc keyed by email
    if "@" in user_id:
        snap = C_IDENTITY.document(user_id.lower()).get()
        if snap.exists:
            return snap.reference, snap.to_dict() or {}
    raise RuntimeError(f"Identity not found for sub='{user_id}'")

def set_identity_fields(user_id: str, **updates):
    ref, _ = _identity_ref_by_user_id(user_id)
    ref.update({k: _fs_safe(v) for k, v in updates.items()})

def save_avatar(user_id: str, file_bytes: bytes, content_type: str) -> str:
    ext = "png" if "png" in content_type.lower() else "jpg"
    path = f"avatars/{user_id}/{uuid.uuid4().hex}.{ext}"
    blob = _bucket.blob(path)
    blob.upload_from_string(file_bytes, content_type=content_type)
    # Make it public so the URL is stable and cacheable
    url, exp = _sign_any(path)
    set_identity_fields(user_id, photoUrl=url, photoUrlPath=path, photoUrlExp=exp)
    return url

# --- Deterministic geometry paths (STL unchanged, STEP gains suffix) ---
def geometry_blob_path(project_id: str, version: int, ext: str = "stl") -> str:
    return f"cad-files/{project_id}/geometry/{int(version)}.{ext}"

def geometry_blob_path_step(project_id: str, version: int) -> str:
    """STEP lives at {ver}_step.step so STL and STEP never collide or confuse."""
    return f"cad-files/{project_id}/geometry/{int(version)}_step.step"

def stl_exists(project_id: str, version: int) -> bool:
    return _bucket.blob(geometry_blob_path(project_id, version, "stl")).exists()


@firestore.transactional
def _txn_toggle_like(txn, project_id: str, user_id: str) -> bool:
    liker_ref = C_META.document(project_id).collection("liked_users").document(user_id)
    meta_ref  = C_META.document(project_id)

    if liker_ref.get(transaction=txn).exists:
        txn.delete(liker_ref)
        txn.update(meta_ref, {"likesCount": firestore.Increment(-1)})
        return False
    else:
        txn.set(liker_ref, {})
        txn.update(meta_ref, {"likesCount": firestore.Increment(+1)})
        return True
    
@firestore.transactional
def _txn_apply_token_usage(txn, user_id: str, raw_tokens_delta: int):
    # 1) fetch identity doc
    q = C_IDENTITY.where(filter=FieldFilter("userID", "==", user_id)).limit(1).stream(transaction=txn)
    snap = next(q, None)
    if not snap:
        return
    ref = snap.reference
    doc = snap.to_dict() or {}

    # 2) compute deltas (store RAW tokens; convert to credits only when needed)
    day_iso = _today_local_iso()
    mkey    = _month_key_from_day(day_iso)

    tu = dict(doc.get("tokenUsage") or {})
    day_entry = dict(tu.get(day_iso) or {})
    mon_entry = dict(tu.get(mkey)    or {})

    prev_day_tokens = int(day_entry.get("tokens", 0))
    prev_mon_tokens = int(mon_entry.get("tokens", 0))

    # apply RAW tokens
    add_tokens = int(raw_tokens_delta)
    day_entry["tokens"] = int(prev_day_tokens + add_tokens)
    mon_entry["tokens"] = int(prev_mon_tokens + add_tokens)
    tu[day_iso] = day_entry
    tu[mkey]    = mon_entry

    # credits totals (before/after) — PROFIT_FACTOR applied HERE (inside helper)
    prev_day_cr = _credits_from_tokens(prev_day_tokens)
    prev_mon_cr = _credits_from_tokens(prev_mon_tokens)
    new_day_cr  = _credits_from_tokens(day_entry["tokens"])
    new_mon_cr  = _credits_from_tokens(mon_entry["tokens"])

    # 3) plan caps
    plan = (doc.get("plan") or "free").lower()
    cfg  = PLAN_CONFIG.get(plan, PLAN_CONFIG["free"])
    daily_quota  = int(doc.get("dailyQuota") or cfg["daily"])
    monthly_cap  = int(doc.get("monthlyCredits") or cfg["monthly_cap"])

    # --- credit threshold notifications (atomic & de-duped) ---
    day_used_prev_pct = _pct(prev_day_cr, daily_quota)
    day_used_new_pct  = _pct(new_day_cr,  daily_quota)
    mon_used_prev_pct = _pct(prev_mon_cr, monthly_cap)
    mon_used_new_pct  = _pct(new_mon_cr,  monthly_cap)

    def _crossed(prev: float, new: float, th: int) -> bool:
        return (prev < th) and (new >= th)

    def _push_credit(kind: str, title: str, body: str, dkey: str, data: dict | None = None):
        try:
            _txn_push_notif(
                txn,
                user_id,
                _notif_payload(kind, title, body, data or {}),
                dedupe_key=dkey,
                identity_ref=ref,
            )
        except Exception:
            pass

    # Fire at 75/90/100% usage (once per day/month)
    thresholds = [75, 90, 100]
    day_iso = _today_local_iso()
    mkey    = _month_key_from_day(day_iso)

    for th in thresholds:
        if _crossed(day_used_prev_pct, day_used_new_pct, th):
            _push_credit(
                "credit_threshold",
                f"Daily credits {th}% used",
                f"You’ve used {int(round(day_used_new_pct))}% of today’s {daily_quota} credits.",
                dkey=f"credit:daily:{day_iso}:{th}",
                data={"scope": "daily", "percent": th, "used": new_day_cr, "quota": daily_quota},
            )

    for th in thresholds:
        if _crossed(mon_used_prev_pct, mon_used_new_pct, th):
            _push_credit(
                "credit_threshold",
                f"Monthly credits {th}% used",
                f"You’ve used {int(round(mon_used_new_pct))}% of this month’s {monthly_cap} credits.",
                dkey=f"credit:monthly:{mkey}:{th}",
                data={"scope": "monthly", "percent": th, "used": new_mon_cr, "cap": monthly_cap},
            )

    # 4) overage since last op (the part bank must cover)
    daily_over_before = max(0, prev_day_cr - daily_quota)
    daily_over_after  = max(0, new_day_cr  - daily_quota)
    mon_over_before   = max(0, prev_mon_cr - monthly_cap)
    mon_over_after    = max(0, new_mon_cr  - monthly_cap)

    overage_delta_daily = max(0, daily_over_after - daily_over_before)
    overage_delta_mon   = max(0, mon_over_after   - mon_over_before)
    # Charge at most once per credit — take the tighter constraint
    bank_charge = max(overage_delta_daily, overage_delta_mon)

    # 5) compute derived “remaining”
    credits_left_after      = max(0, daily_quota - new_day_cr)
    monthly_remaining_after = max(0, monthly_cap - new_mon_cr)

    # 6) maybe debit bank
    updates = {
        "tokenUsage":        tu,
        "creditsLeft":       credits_left_after,
        "monthlyUsed":       new_mon_cr,
        "monthlyRemaining":  monthly_remaining_after,
        "lastUsageAt":       _server_ts(),
        "usageTick":         firestore.Increment(1),
    }

    bm = (doc.get("bankMode") or {})
    bm_enabled = bool(bm.get("enabled"))
    bm_source  = (bm.get("source") or None)

    if bm_enabled and bank_charge > 0 and bm_source in ("rollover", "rewards"):
        if bm_source == "rollover":
            avail = int(doc.get("rolloverBalance") or 0)
            charge = min(bank_charge, avail)
            if charge > 0:
                updates["rolloverBalance"] = int(avail - charge)
                bank_charge -= charge
        else:
            avail = int(doc.get("creditsBank") or 0)
            charge = min(bank_charge, avail)
            if charge > 0:
                updates["creditsBank"] = int(avail - charge)
                bank_charge -= charge

        # If selected bank hits zero → auto-disable
        if bm_source == "rollover" and int(updates.get("rolloverBalance", doc.get("rolloverBalance", 0))) <= 0:
            bm_enabled = False
        if bm_source == "rewards" and int(updates.get("creditsBank", doc.get("creditsBank", 0))) <= 0:
            bm_enabled = False

    # 7) if both daily AND monthly have room again → auto-disable bank mode
    if bm_enabled and (credits_left_after > 0 and monthly_remaining_after > 0):
        bm_enabled = False

    # persist bankMode if changed
    if bm_enabled != bool((doc.get("bankMode") or {}).get("enabled", False)):
        updates["bankMode"] = {"enabled": bm_enabled, "source": bm_source}

    # --- bank debit / empty notifications (de-duped) ---
    try:
        debited_roll = 0
        debited_rwrd = 0

        # How much actually debited this op
        if bm_source == "rollover":
            before = int(doc.get("rolloverBalance") or 0)
            after  = int(updates.get("rolloverBalance", before))
            debited_roll = max(0, before - after)
        elif bm_source == "rewards":
            before = int(doc.get("creditsBank") or 0)
            after  = int(updates.get("creditsBank", before))
            debited_rwrd = max(0, before - after)

        total_debited = debited_roll + debited_rwrd
        if total_debited > 0:
            _txn_push_notif(
                txn,
                user_id,
                _notif_payload(
                    kind="credit_threshold",
                    title="Used bank credits",
                    body=f"Auto-used {total_debited} bank credits to keep things moving.",
                    data={
                        "scope": "bank",
                        "source": bm_source,
                        "debited": total_debited,
                        "rolloverDebited": debited_roll,
                        "rewardsDebited": debited_rwrd,
                    },
                ),
                dedupe_key=f"credit:bank:debit:{day_iso}:{int(new_day_cr)}",
                identity_ref=ref,
            )

        # Bank empty signals (once per month for rollover; once for rewards)
        if bm_source == "rollover":
            after = int(updates.get("rolloverBalance", doc.get("rolloverBalance", 0)) or 0)
            if after <= 0:
                _txn_push_notif(
                    txn,
                    user_id,
                    _notif_payload(
                        kind="credit_threshold",
                        title="Rollover bank empty",
                        body="Your monthly rollover bank is now empty.",
                        data={"scope": "bank", "source": "rollover"},
                    ),
                    dedupe_key=f"credit:bank:rollover:empty:{mkey}",
                    identity_ref=ref,
                )
        elif bm_source == "rewards":
            after = int(updates.get("creditsBank", doc.get("creditsBank", 0)) or 0)
            if after <= 0:
                _txn_push_notif(
                    txn,
                    user_id,
                    _notif_payload(
                        kind="credit_threshold",
                        title="Rewards bank empty",
                        body="Your lifetime rewards bank is now empty.",
                        data={"scope": "bank", "source": "rewards"},
                    ),
                    dedupe_key="credit:bank:rewards:empty",
                    identity_ref=ref,
                )
    except Exception:
        # Notifications must never break metering
        pass

    txn.update(ref, _fs_safe(updates))

def toggle_like(project_id: str, user_id: str) -> bool:
    """Transactionally toggle and return new like state. When liking, grant +1 'likes' to the LIKER (projects they've liked)."""
    txn = firestore.Transaction(_fs)
    liked = _txn_toggle_like(txn, project_id, user_id)

    if liked:
        try:
            # unique_key per (liker, project) — prevents double-award if they toggle repeatedly
            _record_progress_txn(txn, user_id, "likes", amount=1, unique_key=project_id)
        except Exception:
            pass
    return liked

def increment_view(project_id: str):
    C_META.document(project_id).update({"viewCount": firestore.Increment(1)})

def get_community_feed(limit: int = 30, sign_previews: bool = False):
    """
    Return up to `limit` *original* projects (skip remixes).
    Firestore doesn’t let us do “!= remix” + `order_by(updatedAt)` cleanly,
    so we over-fetch then filter in Python.
    """
    candidates = (
        C_META.where(filter=FieldFilter("cadVersion", ">", 0))
              .order_by("cadVersion")
              .limit(limit * 3)
              .get()
    )

    items: list[dict] = []
    for s in candidates:
        d = s.to_dict()

        # ─── skip remixes ──────────────────────────────────────────────
        if d.get("origin") == "remix":
            continue
        if d.get("private") is True:
            continue

        # only originals past this point
        d["id"] = s.id
        if sign_previews:
            d["preview"] = get_signed_preview(d, s.id)  # may sign once
        else:
            # reuse if still fresh; else leave None (front-end can fetch on demand)
            now = int(_dt.datetime.utcnow().timestamp())
            if d.get("previewSigned") and d.get("previewExp") and \
               (now + _REFRESH_IF_LEEWAY) < int(d["previewExp"]):
                d["preview"] = d["previewSigned"]
            else:
                d["preview"] = None

        if d.get("cadVersion"):
            items.append(d)
            if len(items) == limit:         # stop once we hit the quota
                break
    return items

def has_liked(project_id: str, user_id: str) -> bool:
    doc = C_META.document(project_id) \
            .collection("liked_users") \
            .document(user_id) \
            .get()
    return doc.exists

def copy_blob(src_path: str, dst_path: str) -> str:
    """Server-side copy within the same bucket; returns dst_path."""
    src_blob = _bucket.blob(src_path)
    _bucket.copy_blob(src_blob, _bucket, dst_path)
    return dst_path

def list_my_projects(owner_id: str):
    """Return meta docs for all projects owned by user."""
    snaps = C_META.where(filter=FieldFilter("ownerID", "==", owner_id)).get()
    return [s.to_dict() | {"id": s.id} for s in snaps]

# ───────────────────────── Identity ─────────────────────────
def identity_exists(email: str):
    return C_IDENTITY.document(email).get().exists

def signup(email: str, password: str) -> str:
    email = email.lower()
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    cfg = PLAN_CONFIG["free"]
    C_IDENTITY.document(email).set({
        "userID": user_id,
        "email": email,
        "password": _hash_pw(password),
        "createdAt": _server_ts(),
        "projects": [],
        "tokenUsage": {},
        # NEW defaults
        "username": email.split("@")[0][:10],
        "photoUrl": None,
        "plan": "free",          # "free" | "pro"
        "dailyQuota": cfg["daily"],
        "creditsLeft": cfg["daily"],
        "monthlyCredits": cfg["monthly_cap"], 
        "rolloverBalance": 0,                   # monthly rollover bucket
        "rolloverMonth": _today_local_iso()[:7],      # "YYYY-MM" that this rollover belongs to
        "lastRolloverDay": _today_local_iso(),        # last day we reconciled daily rollover

        # NEW — Progress defaults
        "xp": 0,
        "tier": "apprentice",
        "creditsBank": 0,
        "bankMode": {"enabled": False, "source": None},
        "streak": {"consecutiveDays": 0, "best": 0, "last": None, "multiplier": 1.0},
        "badges": {
            "designs":  {"count": 0, "level": 0},
            "remixes":  {"count": 0, "level": 0},
            "likes":    {"count": 0, "level": 0},
            "shares":   {"count": 0, "level": 0},
            "exports":  {"count": 0, "level": 0},
        },
    })
    return user_id

def login(email: str, password: str) -> str | None:
    email = email.lower()
    snap = C_IDENTITY.document(email).get()
    if not snap.exists:
        return None
    doc = snap.to_dict() or {}
    if not _verify_pw(password, doc.get("password", "")):
        return None
    # update lastLogin
    C_IDENTITY.document(email).update({"lastLogin": _server_ts()})
    return _sign(doc["userID"], email, settings.access_ttl_h)

# ───────────────────────── Projects & artifacts ─────────────────────────
def create_project(user_id: str) -> str:
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    # add to user's list (best‑effort)
    try:
        q = C_IDENTITY.where(filter=FieldFilter("userID", "==", user_id)).limit(1).get()
        if q:
            ref = q[0].reference
            data = q[0].to_dict() or {}
            projects: List[str] = data.get("projects", [])
            if project_id not in projects:
                projects.append(project_id)
                ref.update({"projects": projects})
    except Exception:
        pass
    return project_id


def upsert_project_meta(
    project_id: str,
    owner_id: str,
    title: str | None = None,
    preview_url: str | None = None,
    **extra, 
):
    """
    Create or update the lightweight record used by /projects & community feed.
    Pass any additional fields (brainVersion, cadVersion, etc.) via **extra.
    """
    doc = {
        "ownerID": owner_id,
        "title": title or "Untitled project",
        "updatedAt": _server_ts(),
    }
    if preview_url:                      # add/replace *only* when non-null
        doc["preview"] = preview_url
    # copy only non-None extras
    doc.update({k: v for k, v in extra.items() if v is not None})

    C_META.document(project_id).set(doc, merge=True)

def put_artifact(
    project_id: str,
    user_id: str,
    session_id: str,
    art_type: str,
    data: Dict[str, Any],
    version: int | None = None,
    parent_id: str | None = None,
    blob_url: str | None = None,
    tags: Optional[list[str]] = None,
):
    if version is None:
        version = next_version(project_id, art_type)
    art_id = f"{art_type}_{version}_{project_id}"
    data_safe = _fs_safe(data)
    tags = tags or []
    tags_safe = _fs_safe(tags)
    C_ART.document(art_id).set({
        "projectID": project_id,
        "userID": user_id,
        "sessionID": session_id,
        "type": art_type,
        "version": int(version),
        "parentID": parent_id,
        "createdAt": _server_ts(),
        "blobUrl": blob_url,
        "tags": tags_safe,
        "data": data_safe,
    })
    return art_id

def get_artifact(project_id: str, art_id: str) -> Optional[Dict[str, Any]]:
    snap = C_ART.document(art_id).get()
    if not snap.exists:
        return None
    doc = snap.to_dict() or {}
    if doc.get("projectID") != project_id:
        return None
    doc["id"] = art_id
    return doc

def list_artifacts(project_id: str, art_type: str | None = None, latest: bool = False):
    """
    List artifacts with fallback when composite index is building.
    Uses simple queries that don't require composite indexes.
    """
    try:
        # Try the original complex query first
        if art_type:
            snaps = (
                C_ART.where(filter=FieldFilter("projectID", "==", project_id))
                     .where(filter=FieldFilter("type", "==", art_type))
                     .order_by("version", direction=firestore.Query.DESCENDING)
                     .get()
            )
        else:
            snaps = (
                C_ART.where(filter=FieldFilter("projectID", "==", project_id))
                     .order_by("version", direction=firestore.Query.DESCENDING)
                     .get()
            )
        
        items = [s.to_dict() for s in snaps if s.exists]
        if latest and items:
            return items[0]
        return items
        
    except Exception as e:
        # Fallback: use simple projectID-only query when index is building
        print(f"[Warning] Composite index building, using fallback query for {art_type} in {project_id}: {e}")
        
        try:
            # Simple query by projectID only (this index exists)
            snaps = C_ART.where(filter=FieldFilter("projectID", "==", project_id)).get()
            
            # Filter and sort in memory
            items = []
            for s in snaps:
                if not s.exists:
                    continue
                doc = s.to_dict()
                if art_type and doc.get("type") != art_type:
                    continue
                items.append(doc)
            
            # Sort by version descending
            items.sort(key=lambda x: int(x.get("version", 0)), reverse=True)
            
            if latest and items:
                return items[0]
            return items
            
        except Exception as e2:
            print(f"[Error] Even fallback query failed for {art_type} in {project_id}: {e2}")
            if latest:
                return None
            return []

def next_version(project_id: str, art_type: str) -> int:
    """Get next version number with fallback when index is building."""
    try:
        # Try the original complex query first
        snaps = (
            C_ART.where(filter=FieldFilter("projectID", "==", project_id))
                 .where(filter=FieldFilter("type", "==", art_type))
                 .order_by("version", direction=firestore.Query.DESCENDING)
                 .limit(1)
                 .get()
        )
        if not snaps:
            return 1
        v = snaps[0].to_dict().get("version", 0)
        try:
            return int(v) + 1
        except Exception:
            return 1
            
    except Exception as e:
        # Fallback: use simple query when index is building
        print(f"[Warning] Composite index building, using fallback for next version {art_type} in {project_id}: {e}")
        
        try:
            # Simple query by projectID only, then filter in memory
            snaps = C_ART.where(filter=FieldFilter("projectID", "==", project_id)).get()
            
            max_version = 0
            for s in snaps:
                if not s.exists:
                    continue
                doc = s.to_dict()
                if doc.get("type") != art_type:
                    continue
                try:
                    version = int(doc.get("version", 0))
                    max_version = max(max_version, version)
                except Exception:
                    continue
            
            return max_version + 1
            
        except Exception as e2:
            print(f"[Warning] Even fallback failed for next version {art_type} in {project_id}: {e2}")
            return 1

# ───────────────────────── Chat & ops ─────────────────────────
def last_chat_messages(project_id: str, limit: int = 20):
    snaps = (
        C_CHAT.where(filter=FieldFilter("projectID", "==", project_id))
              .order_by("ts", direction=firestore.Query.DESCENDING)
              .limit(limit)
              .get()
    )
    items = [s.to_dict() for s in snaps]
    items.reverse()  # oldest first
    return items

def log_operation(
    user_id: str,
    project_id: str,
    session_id: str,
    op_type: str,
    agent: str,
    tokens_prompt: int = 0,
    tokens_comp: int = 0,
    latency_ms: int = 0,
    status: str = "success",
    error: Optional[str] = None,
    design_stage: Optional[str] = None,
    retry: int = 0,
):
    total_tokens = int(tokens_prompt + tokens_comp)

    doc_id = f"{op_type}:{project_id}:{uuid.uuid4().hex[:8]}"
    C_OPER.document(doc_id).set({
        "userID": user_id,
        "projectID": project_id,
        "sessionID": session_id,
        "ts": _server_ts(),
        "operationType": op_type,
        "agent": agent,
        "tokens": {
            "prompt": tokens_prompt,
            "completion": tokens_comp,
            "total": total_tokens,
        },
        "latency": latency_ms,
        "status": status,
        "error": error,
        "retryAttempts": retry,
        "designStage": design_stage,
    })

    # NEW: aggregate usage counters (adjust tokens, roll up day/month, recompute credits)
    try:
        _txn_apply_token_usage(firestore.Transaction(_fs), user_id, total_tokens)
    except Exception:
        # never fail the caller because of metering
        pass


def add_chat_message(
    project_id: str,
    session_id: str,
    user_id: str,
    role: str,  # "user" or "assistant"
    content: str,
    agent: Optional[str] = None,
    op_id: Optional[str] = None,
    tokens_prompt: int = 0,
    tokens_comp: int = 0,
    design_stage: Optional[str] = None,
):
    chat_id = f"{role}_{project_id}:{uuid.uuid4().hex[:8]}"
    C_CHAT.document(chat_id).set({
        "projectID": project_id,
        "sessionID": session_id,
        "userID": user_id,
        "role": role,
        "agent": agent,
        "content": content,
        "tokens": {
            "prompt": tokens_prompt,
            "completion": tokens_comp,
            "total": tokens_prompt + tokens_comp,
        },
        "designStage": design_stage,
        "relatedOp": op_id,
        "ts": _server_ts(),
    })

# ───────────────────────── Cloud Storage ─────────────────────────
def upload_blob(local_path: str, project_id: str, subdir: str, ttl_sec: int = 3600) -> str:
    file_name = Path(local_path).name
    blob_path = f"cad-files/{project_id}/{subdir}/{file_name}"
    blob = _bucket.blob(blob_path)

    # content type
    ctype = "application/octet-stream"
    if file_name.endswith(".stl"):
        ctype = "model/stl"
    elif file_name.endswith(".obj"):
        ctype = "text/plain"

    blob.upload_from_filename(local_path, content_type=ctype)

    url = _signed_url_v4(blob, ttl_sec, "GET")
    return url

def download_blob_to_temp(blob_url: str) -> str:
    """Download *any* HTTPS URL to a temp file. Works for signed URLs.
    We don't attempt to parse bucket/blob from the URL — just stream bytes.
    """
    import requests  # lazy import to keep dependency optional
    resp = requests.get(blob_url, timeout=120)
    resp.raise_for_status()
    ext = Path(blob_url.split("?")[0]).suffix or ""
    fd, path = tempfile.mkstemp(suffix=ext)
    with open(path, "wb") as f:
        f.write(resp.content)
    return path

def upload_geometry(local_path: str, project_id: str, version: int,
                    ext: str = "stl", ttl_sec: int = 86_400) -> tuple[str, str]:
    """
    Upload the STL to a deterministic location and return (signed_url, blob_path).
    """
    blob_path = geometry_blob_path(project_id, version, ext)
    blob = _bucket.blob(blob_path)

    # content type
    ext_l = ext.lower()
    if ext_l == "stl":
        ctype = "model/stl"
    elif ext_l in ("step", "stp"):
        ctype = "application/step"
    else:
        ctype = "application/octet-stream"
    blob.upload_from_filename(local_path, content_type=ctype)

    url = _signed_url_v4(blob, ttl_sec, "GET")
    return url, blob_path

def upload_step_gz(local_path: str, project_id: str, version: int,
                   ttl_sec: int = 86_400) -> tuple[str, str]:
    """
    Gzip a .step/.stp and upload it at path ending with *{ver}_step.step*
    with Content-Encoding: gzip.
    """
    gz_path = f"{local_path}.gz"
    with open(local_path, "rb") as fin, gzip.open(gz_path, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)

    blob_path = geometry_blob_path_step(project_id, version)  # ← <ver>_step.step
    blob = _bucket.blob(blob_path)
    blob.upload_from_filename(gz_path, content_type="application/step")
    blob.content_encoding = "gzip"
    blob.patch()

    url = _signed_url_v4(blob, ttl_sec, "GET")
    return url, blob_path


def sign_path(blob_path: str, ttl_sec: int = 86_400) -> str:
    """Mint a fresh V4 signed URL for an existing object path."""
    blob = _bucket.blob(blob_path)
    return _signed_url_v4(blob, ttl_sec, "GET")

# ───────── Thumbnails ─────────
def image_blob_path(project_id: str, version: int, ext: str = "png") -> str:
    return f"cad-files/{project_id}/images/{version}.{ext}"

def signed_thumbnail_url(
    project_id: str,
    version: int | str | None,
    ttl_sec: int = 86_400,
) -> str | None:
    if version is None:
        return None
    ver = int(version)
    for ext in ("png", "webp", "jpg", "jpeg"):
        path = image_blob_path(project_id, ver, ext)
        blob = _bucket.blob(path)
        if blob.exists():
            return _signed_url_v4(blob, ttl_sec, "GET")
    return None          # nothing in bucket

def upload_thumbnail(local_path: str, project_id: str, version: int,
                     ext: str = "png", ttl_sec: int = 86_400) -> str:
    path = image_blob_path(project_id, version, ext)
    blob = _bucket.blob(path)

    # if already exists → skip
    if blob.exists():
        return _signed_url_v4(blob, ttl_sec, "GET")

    blob.upload_from_filename(local_path, content_type=f"image/{ext}")

    url, exp = _sign_thumbnail(project_id, path)

    # persist for reuse
    C_META.document(project_id).set({
        "previewPath": path,
        "previewSigned": url,
        "previewExp": exp,
    }, merge=True)

    return url

# ───────── Signed-URL cache helper ─────────
def get_signed_preview(meta: dict, project_id: str) -> str | None:
    """
    Return a signed thumbnail URL, creating or refreshing it only when required.

    Works for **both** new and legacy documents:
    • If previewPath/Signed/Exp exist → use & refresh when close to expiry
    • Else (old doc) → derive path from cadVersion, verify it exists once,
      then cache the new fields for future calls.
    """
    now_epoch = int(_dt.datetime.utcnow().timestamp())

    # 1) If we already know the blob path
    if meta_path := meta.get("previewPath"):
        # Need a new URL?
        if meta.get("previewSigned") and meta.get("previewExp"):
            if (now_epoch + _REFRESH_IF_LEEWAY) < int(meta["previewExp"]):
                return meta["previewSigned"]          # still fresh

        # (re)-sign locally, no network
        url, exp = _sign_thumbnail(project_id, meta_path)
        C_META.document(project_id).update({
            "previewSigned": url,
            "previewExp":    exp,
        })
        return url

    # 2) Legacy doc – try to discover the file once (any supported ext)
    ver = meta.get("cadVersion")
    if ver is None:
        return None  # no CAD yet → no thumbnail

    for ext in ("png", "webp", "jpg", "jpeg"):
        path = image_blob_path(project_id, int(ver), ext)
        blob = _bucket.blob(path)
        if blob.exists():                    # single HEAD per ext until found
            url, exp = _sign_thumbnail(project_id, path)
            C_META.document(project_id).update({
                "previewPath":   path,
                "previewSigned": url,
                "previewExp":    exp,
            })
            return url

    # No image in bucket
    return None

# ───────── Project DELETER ─────────
def delete_project(project_id: str):
    """
    Hard-delete:
      • projects_meta doc (+ liked_users sub-col)
      • all artifacts / chat / operations docs for this project
      • every object under cad-files/<project_id>/ in GCS
    """
    # 1) Meta & liked_users
    meta_ref = C_META.document(project_id)

    # delete liked_users subcollection (batched)
    liked_stream = meta_ref.collection("liked_users").stream()
    batch = _fs.batch(); count = 0
    for s in liked_stream:
        batch.delete(s.reference); count += 1
        if count == 400:
            batch.commit(); batch = _fs.batch(); count = 0
    if count:
        batch.commit()

    # delete the meta doc itself
    meta_ref.delete()

    # 2) Other top-level collections
    for col in (C_ART, C_CHAT, C_OPER):
        snaps = col.where(filter=FieldFilter("projectID", "==", project_id)).stream()
        batch = _fs.batch(); count = 0
        for s in snaps:
            batch.delete(s.reference); count += 1
            if count == 400:  # Firestore batch limit
                batch.commit(); batch = _fs.batch(); count = 0
        if count:
            batch.commit()

    # 3) GCS blobs
    prefix = f"cad-files/{project_id}/"
    for blob in _bucket.list_blobs(prefix=prefix):
        blob.delete()

def set_plan_for_user(user_id: str, plan: str, credits_per_month: int | None = None):
    ref, doc = _identity_ref_by_user_id(user_id)
    plan = (plan or "free").lower()
    cfg = PLAN_CONFIG.get(plan, PLAN_CONFIG["free"])
    updates = {
        "plan": plan,
        "dailyQuota": int(cfg["daily"]),
        "monthlyCredits": int(cfg["monthly_cap"]),
    }
    ref.update(updates)
    return updates["plan"]

#--------------------UX stuff--------------------
# ───────── Progress (XP / Tiers / Streak / Badges) ─────────
# Badge categories: designs, remixes, likes, shares, exports, versions, edits
_BADGE_THRESHOLDS: dict[str, list[int]] = {
    "designs":  [1, 5, 20, 50],
    "remixes":  [1, 5, 15, 30],
    "likes":    [10, 50, 100, 500],
    "shares":   [1, 5, 15, 30],
    "exports":  [1, 5, 15, 50],
}
_BADGE_XP = [100, 500, 2500, 5000]  # per level

_TIER_ORDER = ["apprentice", "maker", "engineer", "innovator", "inventor"]
# XP thresholds are inclusive of lower bound; upper bound is next-1 (except last)
# Apprentice: 0–500, Maker: 501–2000, Engineer: 2001–10000, Innovator: 10001–50000, Inventor: 50001+
def _tier_for_xp(xp: int) -> str:
    if xp < 500:        return "apprentice"
    if xp < 2000:       return "maker"
    if xp < 10000:      return "engineer"
    if xp < 50000:      return "innovator"
    return "inventor"

def _next_tier_cutoff(xp: int) -> int | None:
    # returns XP needed to reach next tier (absolute threshold), or None if top tier
    if xp < 500:    return 500
    if xp < 2000:   return 2000
    if xp < 10000:  return 10000
    if xp < 50000:  return 50000
    return None

_TIER_CREDIT_REWARD = {
    "maker": 5,
    "engineer": 10,
    "innovator": 20,
    "inventor": 50,
}

# Streak multipliers:
# 3 days → 1.5x, 1 week → 2x, 2 weeks → 4x, 3 weeks → 8x, 4+ weeks → 16x (cap)
_STREAK_CAP = 16.0
def _streak_multiplier(days: int) -> float:
    if days >= 28: return float(min(_STREAK_CAP, 16))
    if days >= 21: return 8.0
    if days >= 14: return 4.0
    if days >= 7:  return 2.0
    if days >= 3:  return 1.5
    return 1.0

def _ensure_progress_defaults(doc: dict) -> dict:
    badges = doc.get("badges") or {}
    def slot():
        return {"count": 0, "level": 0}
    for k in ("designs", "remixes", "likes", "shares", "exports"):
        badges.setdefault(k, {"count": 0, "level": 0})
    streak = doc.get("streak") or {"consecutiveDays": 0, "best": 0, "last": None, "multiplier": 1.0}
    tier  = doc.get("tier") or "apprentice"
    xp    = int(doc.get("xp") or 0)
    credits_bank = int(doc.get("creditsBank") or 0)
    doc.update({"badges": badges, "streak": streak, "tier": tier, "xp": xp, "creditsBank": credits_bank})
    return doc

def get_progress_snapshot(user_id: str) -> dict:
    """Return progress info for UI."""
    _, doc = _identity_ref_by_user_id(user_id)
    if not doc: return {}
    doc = _ensure_progress_defaults(doc)
    xp = int(doc["xp"])
    tier = _tier_for_xp(xp)
    next_cut = _next_tier_cutoff(xp)
    streak = doc["streak"]
    return {
        "xp": xp,
        "tier": tier,
        "creditsBank": int(doc.get("creditsBank", 0)),
        "streak": {
            "days": int(streak.get("consecutiveDays", 0)),
            "best": int(streak.get("best", 0)),
            "multiplier": float(streak.get("multiplier", 1.0)),
            "last": streak.get("last"),
        },
        "badges": doc["badges"],
        "nextTierXp": next_cut,
    }

@firestore.transactional
def _record_progress_txn(txn, user_id: str, category: str, amount: int = 1, unique_key: str | None = None):
    """
    Atomically:
      • (optionally) enforce uniqueness via `unique_key` (category + key)
      • update streak (day-based)   [only if not skipped]
      • increment badge counter for `category`
      • if a new badge level is reached → grant XP * streak multiplier
      • recompute tier and grant tier credits if tier increased
    """
    assert category in _BADGE_THRESHOLDS, f"unknown category: {category}"

    # Load doc
    q = C_IDENTITY.where(filter=FieldFilter("userID", "==", user_id)).limit(1).stream(transaction=txn)
    snap = next(q, None)
    if not snap:
        raise RuntimeError("Identity not found for user")
    ref = snap.reference
    doc = _ensure_progress_defaults(snap.to_dict() or {})

    # ── Uniqueness gate (per-user) ─────────────────────────────────
    # If `unique_key` is provided and we already awarded it once, skip.
    if unique_key:
        award_ref = ref.collection("progress_awards").document(f"{category}:{unique_key}")
        if award_ref.get(transaction=txn).exists:
            # do nothing if duplicate
            return {
                "awardedXp": 0,
                "multiplier": float(doc["streak"].get("multiplier", 1.0)),
                "newTier": doc.get("tier", "apprentice"),
                "tierCreditDelta": 0,
                "badgeLevel": int(doc["badges"][category].get("level", 0)),
                "badgeCount": int(doc["badges"][category].get("count", 0)),
                "skipped": "duplicate",
            }
        # reserve the award id
        txn.set(award_ref, {"ts": _server_ts()})

    # --- update streak ---
    today = _today_local_iso()
    last  = doc["streak"].get("last")
    consec = int(doc["streak"].get("consecutiveDays", 0))
    if last == today:
        pass
    else:
        if last:
            prev = _dt.date.fromisoformat(last)
            nowd = _dt.date.fromisoformat(today)
            delta = (nowd - prev).days
            consec = (consec + 1) if (delta == 1) else 1
        else:
            consec = 1
        doc["streak"]["last"] = today
    doc["streak"]["consecutiveDays"] = consec
    if consec > int(doc["streak"].get("best", 0)):
        doc["streak"]["best"] = consec
    mult = _streak_multiplier(consec)
    doc["streak"]["multiplier"] = mult

    # --- badge progress ---
    bslot = doc["badges"][category]
    prev_count = int(bslot.get("count", 0))
    new_count  = prev_count + int(amount)
    bslot["count"] = new_count

    thresholds = _BADGE_THRESHOLDS[category]
    prev_level = int(bslot.get("level", 0))
    new_level  = prev_level
    for idx, th in enumerate(thresholds, start=1):
        if new_count >= th:
            new_level = idx

    award_xp = 0
    if new_level > prev_level:
        for level in range(prev_level + 1, new_level + 1):
            award_xp += _BADGE_XP[level - 1]
        if mult and mult > 1.0:
            award_xp = int(round(award_xp * mult))
        bslot["level"] = new_level

        # Enhanced badge notification with debug logging
        try:
            print(f"DEBUG: Creating badge notification for user {user_id}, category {category}, level {new_level}")
            
            badge_payload = _notif_payload(
                kind="badge_level",
                title=f"New {category} badge!",
                body=f"You reached level {new_level} in {category}.",
                data={"category": category, "level": new_level, "count": new_count},
            )
            
            _txn_push_notif(
                txn,
                user_id,
                badge_payload,
                dedupe_key=f"badge:{category}:{new_level}",
                identity_ref=ref,
            )
            
            print(f"DEBUG: Badge notification queued successfully")
            
        except Exception as e:
            print(f"ERROR creating badge notification: {e}")
            import traceback
            traceback.print_exc()

    # --- XP + tier + credits ---
    old_xp   = int(doc["xp"])
    new_xp   = old_xp + int(award_xp)
    old_tier = _tier_for_xp(old_xp)
    new_tier = _tier_for_xp(new_xp)

    credit_delta = 0
    if _TIER_ORDER.index(new_tier) > _TIER_ORDER.index(old_tier):
        credit_delta = _TIER_CREDIT_REWARD.get(new_tier, 0)
        doc["creditsBank"] = int(doc.get("creditsBank", 0)) + credit_delta

        try:
            print(f"DEBUG: Creating tier-up notification for user {user_id}, new tier {new_tier}")
            
            tier_payload = _notif_payload(
                kind="tier_up",
                title=f"Tier up: {new_tier.title()}!",
                body=f"You advanced to {new_tier} and earned +{credit_delta} bank credits.",
                data={"tier": new_tier, "credit_bonus": credit_delta},
            )
            
            _txn_push_notif(
                txn,
                user_id,
                tier_payload,
                dedupe_key=f"tier:{new_tier}",
                identity_ref=ref,
            )
            
            print(f"DEBUG: Tier-up notification queued successfully")
            
        except Exception as e:
            print(f"ERROR creating tier-up notification: {e}")
            import traceback
            traceback.print_exc()

    doc["xp"] = new_xp
    doc["tier"] = new_tier


    txn.update(ref, _fs_safe({
        "badges": doc["badges"],
        "streak": doc["streak"],
        "xp": doc["xp"],
        "tier": doc["tier"],
        "creditsBank": doc["creditsBank"],
        "lastProgressAt": _server_ts(),
    }))

    return {
        "awardedXp": award_xp,
        "multiplier": mult,
        "newTier": new_tier,
        "tierCreditDelta": credit_delta,
        "badgeLevel": new_level,
        "badgeCount": new_count,
    }

def record_progress(user_id: str, category: str,
                    amount: int = 1, unique_key: str | None = None):
    txn = firestore.Transaction(_fs)
    return _record_progress_txn(txn, user_id, category, amount=amount, unique_key=unique_key)

# ───────── Avatars: stabilize to public URLs ─────────
def _ensure_avatar_url(user_id: str, doc: dict) -> str | None:
    """
    Return a stable public URL for the user's avatar and update Firestore if needed.
    Accepts existing public URLs, or signed URLs (which we convert to public).
    Also honors/sets photoUrlPath for future re-use.
    """
    # 1) Prefer explicit path if present
    path = doc.get("photoUrlPath")

    # 2) Else try to parse path from a signed/public URL
    url = doc.get("photoUrl")
    if not path and url and "storage.googleapis.com" in url:
        try:
            path = url.split(".com/")[1].split("?")[0]  # strip query if present
        except Exception:
            path = None

    if not path:
        return url
    now = int(_dt.datetime.utcnow().timestamp())
    exp = doc.get("photoUrlExp")
    # Fresh enough? reuse existing signed URL
    if url and exp and (now + _REFRESH_IF_LEEWAY) < int(exp):
        return url
    # Mint/refresh signed URL
    signed, new_exp = _sign_any(path)
    try:
        set_identity_fields(user_id, photoUrl=signed, photoUrlPath=path, photoUrlExp=new_exp)
    except Exception:
        pass
    return signed


def fetch_identity_min(user_ids: list[str]) -> dict[str, dict]:
    """
    Batch fetch lightweight identity (username, photoUrl) for given user_ids.
    Ensures avatar URLs are public/stable.
    Firestore 'in' queries allow up to ~10 values per call, so we chunk.
    """
    out: dict[str, dict] = {}
    if not user_ids:
        return out

    # de-dupe while preserving order
    seen = set()
    ordered = []
    for u in user_ids:
        if u and u not in seen:
            ordered.append(u); seen.add(u)

    chunk_size = 10
    for i in range(0, len(ordered), chunk_size):
        chunk = ordered[i:i + chunk_size]
        snaps = C_IDENTITY.where(filter=FieldFilter("userID", "in", chunk)).get()
        for s in snaps:
            d = s.to_dict() or {}
            uid = d.get("userID")
            if not uid:
                continue
            # Ensure defaults, then compute tier from xp (keeps legacy-safe)
            doc = _ensure_progress_defaults(d)
            xp = int(doc.get("xp", 0))
            tier = _tier_for_xp(xp)

            username = d.get("username")
            photo = _ensure_avatar_url(uid, d) or d.get("photoUrl")
            out[uid] = {"username": username, "photoUrl": photo, "tier": tier,}
    return out

# ───────── Generic signer (any blob path) ─────────
from google.auth.transport.requests import Request
from google.auth.iam import Signer
from google.oauth2 import service_account
from google.auth import default as google_auth_default

# The service account that will sign URLs (can move to settings/env if you prefer).
SIGNING_SA = os.getenv(
    "SIGNING_SA_EMAIL",
    "makistry@indigo-night-463419-r0.iam.gserviceaccount.com",
)

def _build_signing_creds():
    """
    Prefer a local service-account key (GOOGLE_APPLICATION_CREDENTIALS) that
    *matches* SIGNING_SA for V4 URL signing. Fall back to IAM Signer only if
    no matching key is available.
    """
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if path:
        try:
            key_creds = service_account.Credentials.from_service_account_file(path)
            if key_creds.service_account_email == SIGNING_SA:
                return key_creds
        except Exception:
            pass

    # Fallback: IAMCredentials Signer (requires roles/iam.serviceAccountTokenCreator on SIGNING_SA)
    base_creds, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    signer = Signer(Request(), base_creds, SIGNING_SA)
    return service_account.Credentials(
        signer=signer,
        service_account_email=SIGNING_SA,
        token_uri="https://oauth2.googleapis.com/token",
    )

_SIGNING_CREDS = _build_signing_creds()

def _signed_url_v4(blob, ttl_seconds: int, method: str = "GET"):
    return blob.generate_signed_url(
        version="v4",
        expiration=_dt.timedelta(seconds=ttl_seconds),
        method=method,
        credentials=_SIGNING_CREDS,
    )


def _sign_any(path: str) -> tuple[str, int]:
    blob = _bucket.blob(path)
    url  = _signed_url_v4(blob, _SIGN_TTL, "GET")
    expires = int(_dt.datetime.utcnow().timestamp()) + _SIGN_TTL
    return url, expires

def usage_snapshot(user_id: str) -> dict:
    ref_q = C_IDENTITY.where(filter=FieldFilter("userID", "==", user_id)).limit(1).get()
    if not ref_q:
        raise RuntimeError("Identity not found")
    doc = ref_q[0].to_dict() or {}

    raw_mode = doc.get("bankMode")
    if isinstance(raw_mode, str):
        norm_mode = {"enabled": True, "source": raw_mode}
    elif isinstance(raw_mode, dict):
        norm_mode = {"enabled": bool(raw_mode.get("enabled")), "source": raw_mode.get("source")}
    else:
        norm_mode = {"enabled": False, "source": None}

    day_iso = _today_local_iso()
    mkey    = _month_key_from_day(day_iso)
    tu      = doc.get("tokenUsage") or {}

    day_tokens = int((tu.get(day_iso) or {}).get("tokens", 0))
    mon_tokens = int((tu.get(mkey)    or {}).get("tokens", 0))

    day_used   = _credits_from_tokens(day_tokens)
    mon_used   = _credits_from_tokens(mon_tokens)

    plan = (doc.get("plan") or "free").lower()
    cfg  = PLAN_CONFIG.get(plan, PLAN_CONFIG["free"])
    daily_quota = int(doc.get("dailyQuota") or cfg["daily"])
    monthly_cap = int(doc.get("monthlyCredits") or cfg["monthly_cap"])

    snap = {
        "plan": plan,
        "dailyQuota": daily_quota,
        "creditsToday": day_used,
        "creditsLeft": max(0, daily_quota - day_used),
        "monthlyCap": monthly_cap,
        "monthlyUsed": mon_used,
        "monthlyRemaining": max(0, monthly_cap - mon_used),
        "dayResetAtISO": _next_local_midnight_iso(),
        "monthResetAtISO": _month_end_local_iso(day_iso),

        # NEW: bank view & mode
        "bank": {
            "rollover": int(doc.get("rolloverBalance", 0)),
            "rewards":  int(doc.get("creditsBank", 0)),
            "mode":     norm_mode,
        },
    }
    return snap

def check_ai_allowed(user_id: str) -> tuple[bool, dict]:
    s = usage_snapshot(user_id)
    base_allowed = (s["creditsLeft"] > 0) and (s["monthlyRemaining"] > 0)

    if base_allowed:
        # If bank was on, kill it silently now that normal credits are back.
        try:
            ref, _ = _identity_ref_by_user_id(user_id)
            ref.update({"bankMode.enabled": False})
        except Exception:
            pass
        return True, s

    # fallback to bank mode
    bm = (s.get("bank") or {}).get("mode") or {}
    if bm.get("enabled") and bm.get("source") in ("rollover", "rewards"):
        bal = int((s["bank"]["rollover"] if bm["source"] == "rollover" else s["bank"]["rewards"]) or 0)
        if bal > 0:
            return True, s

    return False, s

# --- Notifications ----------------------------------------------------
def _utc_now() -> _dt.datetime:
    # naive UTC (what Firestore client expects)
    return _dt.datetime.utcnow().replace(tzinfo=None)

def _notif_payload(kind: str, title: str, body: str, data: dict | None = None, ttl_days: int = 14):
    now = _utc_now()                                # naive UTC
    expires = now + _dt.timedelta(days=ttl_days)    # naive UTC
    return {
        "kind": kind,                       # 'credit_threshold' | 'badge_level' | 'tier_up' | 'like' | 'remix' | 'message'
        "title": title,
        "body": body,
        "data": _fs_safe(data or {}),
        "seen": False,
        "ts": _server_ts(),                # server timestamp sentinel (leave as-is)
        "expiresAt": expires,              # naive UTC
    }


def _notif_doc_id(dedupe_key: str | None = None) -> str:
    return dedupe_key or f"n_{uuid.uuid4().hex[:12]}"

def _txn_push_notif(
    txn,
    user_id: str,
    payload: dict,
    dedupe_key: str | None = None,
    *,
    identity_ref,
):
    """Write a notification within a transaction, de-duped by key.
       If the doc already exists, preserve 'seen' and 'ts' so the UI
       does not re-show or reorder previously seen notifications."""
    nref = identity_ref.collection("notifications").document(_notif_doc_id(dedupe_key))
    if dedupe_key:
        snap = nref.get(transaction=txn)
        if snap.exists:
            # Preserve existing 'seen' and 'ts'
            p = dict(payload)
            p.pop("seen", None)
            p.pop("ts", None)
            txn.set(nref, _fs_safe(p), merge=True)
        else:
            txn.set(nref, _fs_safe(payload))
    else:
        txn.set(nref, _fs_safe(payload))
    return True

def push_notification(user_id, kind, title, body, data=None, dedupe_key=None, ttl_days=14):
    ref, _ = _identity_ref_by_user_id(user_id)
    nref = ref.collection("notifications").document(_notif_doc_id(dedupe_key))
    payload = _fs_safe(_notif_payload(kind, title, body, data, ttl_days))

    if dedupe_key:
        snap = nref.get()
        if snap.exists:
            # Preserve existing 'seen' and 'ts' on updates
            p = dict(payload)
            p.pop("seen", None)
            p.pop("ts", None)
            nref.set(_fs_safe(p), merge=True)
        else:
            nref.set(payload)
    else:
        nref.set(payload)
    return True
