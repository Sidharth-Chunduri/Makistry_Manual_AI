# app/routes/account.py
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Literal
from app.services import storage_gcp as storage   # need direct access to collections
from app.services.auth import get_current_user
from app.core.config import settings
from google.cloud import storage as gcs
import tempfile, shutil, uuid
from app.services.storage_gcp import (
    TOKENS_PER_CREDIT, PROFIT_FACTOR, PLAN_CONFIG
)
from google.cloud import firestore
from zoneinfo import ZoneInfo
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
import datetime as _dt
import random

LOCAL_TZ = ZoneInfo("America/Chicago")

router = APIRouter(prefix="/account", tags=["account"])

# ---- Shared plan helpers (mirror storage_gcp) ----
def _today_local_iso() -> str:
    return _dt.datetime.now(LOCAL_TZ).date().isoformat()

def _month_key_from_day(day_iso: str) -> str:
    return f"m:{day_iso[:7]}"

def _credits_from_tokens(tokens: int | float) -> int:
    return int(round((float(tokens) * PROFIT_FACTOR) / TOKENS_PER_CREDIT))

def _prev_day_iso(day_iso: str) -> str:
    d = _dt.date.fromisoformat(day_iso)
    return (d - _dt.timedelta(days=1)).isoformat()

def _cap_username(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return str(s).strip()[:10] or None

def _month_end_iso(day_iso: str) -> str:
    d = _dt.date.fromisoformat(day_iso)
    nxt = _dt.date(d.year + (1 if d.month == 12 else 0), 1 if d.month == 12 else d.month + 1, 1)
    eom = nxt - _dt.timedelta(days=1)
    eom_midnight = _dt.datetime.combine(eom + _dt.timedelta(days=1), _dt.time.min, LOCAL_TZ)
    # keep YYYY-MM-DD for UI label
    return eom_midnight.date().isoformat()

def _identity_doc_by_userid(user_id: str):
    q = storage.C_IDENTITY.where("userID", "==", user_id).limit(1).get()
    if q:
        return q[0].reference, q[0].to_dict()
    # fallback if sub is an email
    if "@" in user_id:
        snap = storage.C_IDENTITY.document(user_id.lower()).get()
        if snap.exists:
            return snap.reference, snap.to_dict()
    raise HTTPException(404, f"User not found for sub='{user_id}'")


# ---- Notifications helper ----------------------------------------------------
def _notify(user_id: str, kind: str, title: str, body: str = "",
            data: Optional[Dict] = None, ttl_days: int = 14,
            dedupe_key: Optional[str] = None):
    try:
        storage.push_notification(
            user_id=user_id,
            kind=kind, title=title, body=body,
            data=data or {}, dedupe_key=dedupe_key, ttl_days=ttl_days,
        )
    except Exception as e:
        # Make failures visible in logs so we don't chase ghosts again
        print(f"[notifications] write failed for user_id={user_id}: {e}")
        raise


def _maybe_credit_threshold_notifs(user_id: str, *,
                                   scope: str,        # "daily" | "monthly"
                                   used: int,
                                   quota: int,
                                   period_key: str):  # e.g. day ISO or "m:YYYY-MM"
    """Emit 80/90/100% threshold notifs for credits."""
    if quota <= 0:
        return
    pct = int(round(100 * used / quota))
    for th in (75, 90, 100):
        if pct >= th:
            _notify(
                user_id,
                kind="credit_threshold",
                title=f"{th}% of {scope} credit limit reached",
                body=f"You used {used}/{quota} credits ({pct}%).",
                data={"scope": scope, "percent": pct, "used": used, "quota": quota},
                dedupe_key=f"credit:{scope}:{period_key}:{th}",
            )


def _maybe_action_threshold_notifs(user_id: str, *,
                                   key: str,         # "stl" | "step" | "projects"
                                   used: int,
                                   cap: Optional[int],
                                   reset_at_iso: Optional[str]):
    """Emit 80/90/100% threshold notifs for STL/STEP/projects action limits."""
    if cap is None or cap <= 0:
        return
    pct = int(round(100 * used / cap))
    # Use reset_at_iso to dedupe once per window
    period_key = reset_at_iso or "unknown"
    for th in (75, 90, 100):
        if pct >= th:
            _notify(
                user_id,
                kind="credit_threshold",
                title=f"{th}% of {key.upper()} limit reached",
                body=f"You used {used}/{cap} ({pct}%).",
                data={"scope": key, "percent": pct, "used": used, "cap": cap, "resetAtISO": reset_at_iso},
                dedupe_key=f"limit:{key}:{period_key}:{th}",
            )


# ---- Schemas ----
class ProfilePatch(BaseModel):
    username: Optional[str] = None
    photoUrl: Optional[str] = None

class ProgressEventIn(BaseModel):
    category: Literal["designs","remixes","likes","shares","exports"]
    amount: Optional[int] = 1
    unique_key: Optional[str] = Field(default=None, alias="uniqueKey")

class BankUseIn(BaseModel):
    source: Literal["rollover", "rewards"]

# ---- Progress ----
@router.post("/progress")
def record_progress_event(data: ProgressEventIn, user=Depends(get_current_user)):
    award = storage.record_progress(
        user["sub"], data.category, data.amount or 1, unique_key=data.unique_key
    )
    snap = storage.get_progress_snapshot(user["sub"])

    # NEW: notifications for badge level-ups and tier-ups
    try:
        if award and not award.get("skipped"):
            # Badge level (we don’t know badge name; use category + level)
            badge_level = int(award.get("badgeLevel") or 0)
            if badge_level > 0:
                _notify(
                    user["sub"],
                    kind="badge_level",
                    title=f"Badge level up: {data.category.title()} (Level {badge_level})",
                    body=f"You reached level {badge_level} in {data.category}.",
                    data={"category": data.category, "level": badge_level, "count": award.get("badgeCount")},
                    dedupe_key=f"badge:{data.category}:{badge_level}",
                )

            # Tier up (only when credits actually granted / tier advanced)
            tier_credit_delta = int(award.get("tierCreditDelta") or 0)
            if tier_credit_delta > 0:
                new_tier = award.get("newTier") or snap.get("tier") or "maker"
                _notify(
                    user["sub"],
                    kind="tier_up",
                    title=f"Tier up: {new_tier}",
                    body="You advanced to a higher tier.",
                    data={"tier": new_tier, "tierCreditDelta": tier_credit_delta},
                    dedupe_key=f"tier:{new_tier}",
                )
    except Exception:
        # Never fail the main request on notification write
        pass

    return {"ok": True, "award": award, "snapshot": snap}


# ---- Account snapshot ----
@router.get("/me")
def me(user=Depends(get_current_user)):
    ref, doc = _identity_doc_by_userid(user["sub"])
    snap = storage.get_progress_snapshot(user["sub"])

    action_limits = storage.action_usage_snapshot(user["sub"])

    plan = (doc.get("plan") or "free").lower()
    plan_meta = PLAN_CONFIG.get(plan, PLAN_CONFIG["free"])

    # plan caps
    daily_quota = int(doc.get("dailyQuota") or plan_meta["daily"])
    monthly_cap = int(doc.get("monthlyCredits") or plan_meta["monthly_cap"])
    bank_cap    = int(plan_meta["bank_cap"])

    # usage rollups
    tu = doc.get("tokenUsage") or {}
    day_iso  = _today_local_iso()
    mkey     = _month_key_from_day(day_iso)

    day_tokens = int((tu.get(day_iso) or {}).get("tokens", 0))
    mon_tokens = int((tu.get(mkey)    or {}).get("tokens", 0))

    day_credits_used = _credits_from_tokens(day_tokens)
    mon_credits_used = _credits_from_tokens(mon_tokens)
    credits_left     = max(0, daily_quota - day_credits_used)

        # NEW: opportunistic threshold notifications (idempotent via dedupe keys)
    try:
        _maybe_credit_threshold_notifs(
            user["sub"],
            scope="daily",
            used=day_credits_used,
            quota=daily_quota,
            period_key=day_iso,    # one per day per threshold
        )
        _maybe_credit_threshold_notifs(
            user["sub"],
            scope="monthly",
            used=mon_credits_used,
            quota=monthly_cap,
            period_key=mkey,       # one per month per threshold
        )

        # STL/STEP (monthly) and Projects (weekly) action limits
        if action_limits:
            month = action_limits.get("month", {})
            week = action_limits.get("week", {})

            stl = month.get("stl") or {}
            step = month.get("step") or {}
            projects = week.get("projects") or {}

            _maybe_action_threshold_notifs(
                user["sub"], key="stl",
                used=int(stl.get("used") or 0),
                cap=(stl.get("cap")),
                reset_at_iso=stl.get("resetAtISO"),
            )
            _maybe_action_threshold_notifs(
                user["sub"], key="step",
                used=int(step.get("used") or 0),
                cap=(step.get("cap")),
                reset_at_iso=step.get("resetAtISO"),
            )
            _maybe_action_threshold_notifs(
                user["sub"], key="projects",
                used=int(projects.get("used") or 0),
                cap=(projects.get("cap")),
                reset_at_iso=projects.get("resetAtISO"),
            )
    except Exception:
        pass

    # ── Rollover disabled for beta ───────────────────────────────────
    rollover_balance = 0
    updates = {}
    # (No accrual, no month change logic, no writes)
    bank_expiry_iso = _month_end_iso(day_iso)  # UI-only “Resets …” label

    uname_raw = doc.get("username") or (doc.get("email","").split("@")[0] if doc.get("email") else None)
    username  = _cap_username(uname_raw)

    # # Normalize bankMode but force disabled if it was left on
    # bank_mode = {"enabled": False, "source": None}
    # if doc.get("bankMode"):
    #     ref.set({"bankMode": bank_mode, "rolloverBalance": 0}, merge=True)

    bank_expiry_iso = _month_end_iso(day_iso)  # for UI subtitle (“Resets Aug 31”)

    # Normalize bankMode: support legacy string and new object shape
    raw_mode = doc.get("bankMode")
    if isinstance(raw_mode, str):
        bank_mode = {"enabled": True, "source": raw_mode}
    elif isinstance(raw_mode, dict):
        bank_mode = {
            "enabled": bool(raw_mode.get("enabled", False)),
            "source":  raw_mode.get("source"),
        }
    else:
        bank_mode = {"enabled": False, "source": None}

    return {
        "userID": doc.get("userID"),
        "email": doc.get("email"),
        "username": username,
        "photoUrl": doc.get("photoUrl"),
        "plan": plan,

        # daily + monthly
        "dailyQuota": daily_quota,
        "creditsLeft": credits_left,
        "creditsToday": day_credits_used,
        "monthlyCreditsCap": monthly_cap,
        "monthlyCreditsUsed": mon_credits_used,

        # Bank buckets
        "bankCap": bank_cap,
        "bankRollover": rollover_balance,               # monthly, expires
        "bankRewards":  int(snap.get("creditsBank", 0)),# lifetime, never expires
        "bankExpiryISO": bank_expiry_iso,               # YYYY-MM-DD
        "bankMode": bank_mode,                          # normalized: {enabled, source}

        # Progress
        "xp": snap.get("xp", 0),
        "tier": snap.get("tier", "apprentice"),
        "creditsBank": snap.get("creditsBank", 0),      # legacy field
        "streak": snap.get("streak", {"days":0,"best":0,"multiplier":1.0,"last":None}),
        "badges": snap.get("badges", {}),
        "nextTierXp": snap.get("nextTierXp"),
        "actionLimits": action_limits,
    }

# ---- Profile ----
@router.patch("/me")
def patch_me(data: ProfilePatch, user=Depends(get_current_user)):
    ref, _ = _identity_doc_by_userid(user["sub"])
    to_set: Dict = {}
    if data.username is not None:
        u = (data.username or "").strip()
        if len(u) > 10:
            # hard stop: don't allow >10
            raise HTTPException(status_code=400, detail="username_too_long_max_10")
        to_set["username"] = u
    if data.photoUrl is not None:
        to_set["photoUrl"] = data.photoUrl
    if to_set:
        ref.set(to_set, merge=True)
    return {"ok": True}

@router.post("/avatar")
def upload_avatar(file: UploadFile = File(...), user=Depends(get_current_user)):
    client = gcs.Client(project=settings.gcp_project)
    bucket = client.bucket(settings.gcs_bucket)
    ext = ".png" if (file.content_type or "").lower().endswith("png") else ".jpg"
    path = f"avatars/{user['sub']}/{uuid.uuid4().hex}{ext}"
    blob = bucket.blob(path)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp.flush()
        blob.upload_from_filename(tmp.name, content_type=file.content_type or "image/png")

    # Long-lived, cacheable avatar
    blob.cache_control = "public, max-age=31536000, immutable"
    blob.patch()
    try:
        blob.make_public()
        url = f"https://storage.googleapis.com/{settings.gcs_bucket}/{path}"
    except Exception:
        url = blob.generate_signed_url(version="v4", expiration=60*60*24*7, method="GET")

    ref, _ = _identity_doc_by_userid(user["sub"])
    ref.set({"photoUrl": url}, merge=True)
    return {"photoUrl": url}

# ---- Plan ----
class PlanIn(BaseModel):
    plan: str
    creditsPerMonth: Optional[int] = None

@router.post("/plan")
def set_plan(data: PlanIn, user=Depends(get_current_user)):
    ref, _ = _identity_doc_by_userid(user["sub"])
    plan = (data.plan or "").lower()
    if plan not in PLAN_CONFIG:
        raise HTTPException(400, "unknown plan")

    cfg = PLAN_CONFIG[plan]
    updates = {
        "plan": plan,
        "dailyQuota": int(cfg["daily"]),
        # keep legacy field name so existing UI keeps working
        "monthlyCredits": int(cfg["monthly_cap"]),
    }
    ref.set(updates, merge=True)
    return {"ok": True, "plan": plan}

# ---- Delete account ----
@router.delete("/me")
def delete_me(bg: BackgroundTasks, user=Depends(get_current_user)):
    ref, doc = _identity_doc_by_userid(user["sub"])
    projects = doc.get("projects", [])

    ref.delete()

    def _wipe():
        for pid in projects:
            try:
                storage.delete_project(pid)
            except Exception:
                pass
    bg.add_task(_wipe)

    return {"ok": True}

# ---- Bank mode: enable/disable ----
@router.post("/bank/use")
def bank_use(data: BankUseIn, user=Depends(get_current_user)):
    ref, doc = _identity_doc_by_userid(user["sub"])
    src = data.source

    # Validate availability
    if src == "rollover":
        bal = int(doc.get("rolloverBalance") or 0)
        if bal <= 0:
            raise HTTPException(status_code=400, detail="No rollover credits available")
    elif src == "rewards":
        bal = int(doc.get("creditsBank") or 0)
        if bal <= 0:
            raise HTTPException(status_code=400, detail="No reward credits available")

    # Enable persistent bank mode
    ref.set({"bankMode": {"enabled": True, "source": src}}, merge=True)

    return {"ok": True, "bankMode": {"enabled": True, "source": src}}

@router.post("/bank/clear")
def bank_clear(user=Depends(get_current_user)):
    ref, _ = _identity_doc_by_userid(user["sub"])
    ref.set({"bankMode": {"enabled": False, "source": None}}, merge=True)
    return {"ok": True, "bankMode": {"enabled": False, "source": None}}

# --- Notifications REST (polling) ------------------------------------------
from google.cloud import firestore as _fs_mod
from google.cloud.firestore_v1 import FieldFilter

@router.get("/notifications")
def list_notifications(
    only_unseen: bool = True,
    limit: int = 50,
    user = Depends(get_current_user),
):
    ref, _ = _identity_doc_by_userid(user["sub"])
    q = ref.collection("notifications")

    if only_unseen:
        q = q.where(filter=FieldFilter("seen", "==", False))

    q = q.order_by("ts", direction=_fs_mod.Query.DESCENDING).limit(max(1, min(limit, 100)))

    snaps = q.get()
    items = []
    purged = 0

    def _iso(v):
        try:
            return v.isoformat()
        except Exception:
            return None

    for s in snaps:
        d = s.to_dict() or {}
        # Opportunistic cleanup: drop notifications that are no longer relevant
        try:
            if _is_stale_notification_payload(d):
                try:
                    s.reference.delete()
                    purged += 1
                except Exception:
                    # best-effort; don't break listings if delete fails
                    pass
                continue  # skip adding to response
        except Exception:
            # If the checker itself fails, never block the response
            pass

        items.append({
            "id": s.id,
            "kind": d.get("kind"),
            "title": d.get("title"),
            "body": d.get("body"),
            "data": d.get("data") or {},
            "seen": bool(d.get("seen")),
            "ts": _iso(d.get("ts")),
            "expiresAt": _iso(d.get("expiresAt")),
        })

    # (Optional) include how many were purged for debugging; comment out if undesired
    # return {"items": items, "purged": purged}
    return {"items": items}


@router.post("/notifications/{nid}/seen")
def mark_notification_seen_api(nid: str, user = Depends(get_current_user)):
    ref, _ = _identity_doc_by_userid(user["sub"])
    nref = ref.collection("notifications").document(nid)
    if not nref.get().exists:
        raise HTTPException(404, "Notification not found")
    nref.update({"seen": True})
    return {"ok": True}

# Add this to your account.py file temporarily for testing

@router.post("/test-notification")
def create_test_notification(user=Depends(get_current_user)):
    """Create a test notification for debugging purposes."""
    import random
    
    # Create different types of test notifications
    notification_types = [
        {
            "kind": "message",
            "title": "Test Message Notification",
            "body": "This is a test message notification to verify the system works.",
        },
        {
            "kind": "credit_threshold", 
            "title": "80% of daily credit limit reached",
            "body": "You used 40/50 credits (80%).",
            "data": {"scope": "daily", "percent": 80, "used": 40, "quota": 50}
        },
        {
            "kind": "badge_level",
            "title": "Badge level up: Designs (Level 3)", 
            "body": "You reached level 3 in designs.",
            "data": {"category": "designs", "level": 3, "count": 25}
        },
        {
            "kind": "tier_up",
            "title": "Tier up: engineer",
            "body": "You advanced to a higher tier.",
            "data": {"tier": "engineer", "tierCreditDelta": 100}
        }
    ]
    
    # Pick a random notification type
    notif = random.choice(notification_types)
    
    try:
        _notify(
            user["sub"],
            kind=notif["kind"],
            title=notif["title"], 
            body=notif["body"],
            data=notif.get("data", {}),
            # Use a random dedupe key so we can create multiple test notifications
            dedupe_key=f"test-{random.randint(1000, 9999)}"
        )
        return {"ok": True, "message": "Test notification created", "type": notif["kind"]}
    except Exception as e:
        print(f"Error creating test notification: {e}")
        raise HTTPException(500, f"Failed to create test notification: {str(e)}")

@router.post("/test-notification-bulk")
def create_bulk_test_notifications(user=Depends(get_current_user)):
    """Create multiple test notifications at once."""
    notifications_created = []
    
    test_notifications = [
        ("message", "Welcome!", "Welcome to the notification system."),
        ("credit_threshold", "Credit Alert", "You're running low on credits.", 
         {"scope": "daily", "percent": 90, "used": 45, "quota": 50}),
        ("badge_level", "Achievement Unlocked!", "You earned a new badge level.",
         {"category": "designs", "level": 2, "count": 10}),
    ]
    
    for i, (kind, title, body, *data) in enumerate(test_notifications):
        try:
            _notify(
                user["sub"],
                kind=kind,
                title=title,
                body=body,
                data=data[0] if data else {},
                dedupe_key=f"bulk-test-{i}-{random.randint(1000, 9999)}"
            )
            notifications_created.append({"kind": kind, "title": title})
        except Exception as e:
            print(f"Error creating notification {i}: {e}")
    
    return {
        "ok": True, 
        "message": f"Created {len(notifications_created)} test notifications",
        "notifications": notifications_created
    }

# ---- Notification cleanup helpers ------------------------------------------
def _to_local_date(ts) -> _dt.date | None:
    """Best-effort convert Firestore timestamp/datetime to LOCAL date."""
    try:
        if isinstance(ts, DatetimeWithNanoseconds):
            # Treat as UTC if tz-naive, then convert to local
            t = ts
            if t.tzinfo is None:
                t = t.replace(tzinfo=_dt.timezone.utc)
            return t.astimezone(LOCAL_TZ).date()
        if isinstance(ts, _dt.datetime):
            t = ts
            if t.tzinfo is None:
                t = t.replace(tzinfo=_dt.timezone.utc)
            return t.astimezone(LOCAL_TZ).date()
    except Exception:
        pass
    return None

def _as_naive_utc(dt_like) -> _dt.datetime | None:
    """Return a naive-UTC datetime for simple comparisons."""
    try:
        if isinstance(dt_like, DatetimeWithNanoseconds) or isinstance(dt_like, _dt.datetime):
            if dt_like.tzinfo is None:
                return dt_like  # assume already naive UTC
            return dt_like.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    except Exception:
        pass
    return None

def _is_stale_notification_payload(d: dict) -> bool:
    """
    Decide if a notification is stale *based on its payload*.
    Rules:
      • TTL: expiresAt < now_utc → stale
      • credit_threshold(daily): if ts local-day != today → stale
      • credit_threshold(monthly): if ts local month != current month → stale
      • credit_threshold(stl/step/projects): if resetAtISO and now >= resetAtISO → stale
      • others: rely on TTL only
    """
    now_utc = _dt.datetime.utcnow().replace(tzinfo=None)
    today_local = _dt.datetime.now(LOCAL_TZ).date()

    kind = d.get("kind")
    data = d.get("data") or {}
    expires_at = d.get("expiresAt")
    ts = d.get("ts")

    # 1) TTL
    if expires_at:
        exp = _as_naive_utc(expires_at)
        if exp and exp < now_utc:
            return True

    # 2) Credit / action windows
    if kind == "credit_threshold":
        scope = (data or {}).get("scope")
        # For daily/monthly, use the notification's timestamp day/month in LOCAL time
        ts_day = _to_local_date(ts)
        if scope == "daily":
            if ts_day and ts_day != today_local:
                return True
        elif scope == "monthly":
            if ts_day and (ts_day.year != today_local.year or ts_day.month != today_local.month):
                return True
        elif scope in ("stl", "step", "projects"):
            # Action limits include resetAtISO in payload (local midnight ISO)
            reset_iso = (data or {}).get("resetAtISO")
            if reset_iso:
                try:
                    reset_dt = _dt.datetime.fromisoformat(reset_iso)
                    if reset_dt.tzinfo is None:
                        # treat as local if naive
                        reset_dt = reset_dt.replace(tzinfo=LOCAL_TZ)
                    now_local = _dt.datetime.now(LOCAL_TZ)
                    if now_local >= reset_dt:
                        return True
                except Exception:
                    # if parse fails, fall back to TTL only
                    pass
        else:
            # 'bank' and other scopes: TTL will handle them
            pass

    return False
