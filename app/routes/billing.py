# app/routes/billing.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict
import os
import stripe
from app.services.auth import get_current_user
from app.core.config import settings
from app.services import storage_gcp as storage
import sys

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key or None

if not stripe.api_key or stripe.api_key.startswith("pk_"):
    raise RuntimeError(
        "Invalid STRIPE_SECRET_KEY: must be a secret key starting with 'sk_'. "
        "Check your .env."
    )

# Map our internal plan keys → Stripe price IDs
PRICE_IDS = {
    "plus": settings.stripe_price_plus_monthly,
    "pro":  settings.stripe_price_pro_monthly,
}

def _stripe_mode(k: str) -> str:
    if not k or not k.startswith("sk_"): return "invalid"
    return "live" if k.startswith("sk_live_") else "test"

# After stripe.api_key = settings.stripe_secret_key or None
MODE = _stripe_mode(settings.stripe_secret_key or "")
print(f"[Stripe] key_mode={MODE} "
      f"PLUS={'ok' if (settings.stripe_price_plus_monthly or '').startswith('price_') else 'missing'} "
      f"PRO={'ok' if (settings.stripe_price_pro_monthly or '').startswith('price_') else 'missing'}",
      file=sys.stderr)

@router.get("/_diag")
def diag(user=Depends(get_current_user)):
    # non-sensitive health info
    return {
        "mode": MODE,
        "has_plus_price": bool((settings.stripe_price_plus_monthly or "").startswith("price_")),
        "has_pro_price":  bool((settings.stripe_price_pro_monthly  or "").startswith("price_")),
        "ui_origin": settings.ui_origin,
    }

class CheckoutIn(BaseModel):
    plan: str  # "plus" | "pro"

def _ensure_price(plan: str) -> str:
    pid = PRICE_IDS.get((plan or "").lower())
    if not pid or not str(pid).startswith("price_"):
        raise HTTPException(500, "Stripe price ID not configured. Set STRIPE_PRICE_* env vars.")
    return pid

@router.post("/portal")
def create_billing_portal_session(user=Depends(get_current_user)):
    # Get identity doc (you already do this pattern in /checkout)
    ref, doc = storage._identity_ref_by_user_id(user["sub"])
    customer_id = doc.get("stripeCustomerId") or _get_or_create_customer(doc)

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.ui_origin.rstrip('/')}/settings?plan=sub#billing"
    )
    return {"url": session.url}

def _get_or_create_customer(user_doc: Dict) -> str:
    """
    Reuse stripeCustomerId on the identity doc when present.
    Else create a new customer and persist the id.
    """
    stripe_cid = user_doc.get("stripeCustomerId")
    if stripe_cid:
        return stripe_cid

    email = user_doc.get("email") or None
    username = user_doc.get("username") or None
    customer = stripe.Customer.create(
        email=email,
        name=username or email or None,
        metadata={"userID": user_doc.get("userID") or ""},
    )
    # persist to identity
    try:
        customer = stripe.Customer.create(
            email=email,
            name=username or email or None,
            metadata={"userID": user_doc.get("userID") or ""},
        )
    except stripe.error.AuthenticationError as e:
        # 99% of "Invalid API Key" cases land here
        raise HTTPException(
            500,
            "Stripe authentication failed. Check STRIPE_SECRET_KEY and that it matches your price IDs' mode "
            "(test vs live). If running locally, ensure config.py loads .env with override=True."
        ) from e

@router.post("/checkout")
def create_checkout_session(data: CheckoutIn, user=Depends(get_current_user)):
    """
    Returns a Stripe-hosted Checkout URL for upgrading the current user
    to the requested plan.
    """
    if not stripe.api_key:
        raise HTTPException(500, "Stripe not configured")

    ref, doc = storage._identity_ref_by_user_id(user["sub"])  # raises if missing
    price_id = _ensure_price(data.plan)
    customer_id = _get_or_create_customer(doc)

    success_url = f"{settings.ui_origin.rstrip('/')}/settings?plan=sub#billing&status=success"
    cancel_url  = f"{settings.ui_origin.rstrip('/')}/settings?plan=sub#billing&status=cancel"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            allow_promotion_codes=True,
            client_reference_id=doc.get("userID") or user["sub"],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"plan": data.plan.lower(), "userID": doc.get("userID") or user["sub"]},
        )
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")

    return {"url": session.url}

# ---- Webhook ---------------------------------------------------------------

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handles Stripe events and updates the user's plan.
    IMPORTANT: configure your Stripe endpoint to POST here:
      https://<your-domain>/api/billing/webhook
    """
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise HTTPException(500, "Webhook not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    # Minimal, robust handlers
    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        # Only act for subscriptions
        if sess.get("mode") == "subscription":
            plan = (sess.get("metadata", {}) or {}).get("plan")
            user_id = (sess.get("metadata", {}) or {}).get("userID") or sess.get("client_reference_id")
            customer_id = sess.get("customer")
            subscription_id = sess.get("subscription")

            if user_id and plan in ("plus", "pro"):
                try:
                    # Persist Stripe ids
                    storage.set_identity_fields(
                        user_id,
                        stripeCustomerId=customer_id,
                        stripeSubscriptionId=subscription_id,
                    )
                except Exception:
                    pass
                # Upgrade plan immediately
                try:
                    storage.set_plan_for_user(user_id, plan)
                except Exception:
                    # Don't fail the webhook; Stripe will retry on 5xx
                    pass

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.created"):
        sub = event["data"]["object"]
        # If user id not in metadata, we can try to look up by customer id
        customer_id = sub.get("customer")
        # Resolve user by browsing identity collection for this customer id
        try:
            # Small helper: query identity where stripeCustomerId == customer_id
            snaps = storage.C_IDENTITY.where(filter=storage.FieldFilter("stripeCustomerId", "==", customer_id)).limit(1).get()
            if snaps:
                ref = snaps[0].reference
                doc = snaps[0].to_dict() or {}
                user_id = doc.get("userID")
            else:
                user_id = None
        except Exception:
            user_id = None

        # If price changed (upgrade/downgrade), set plan from price → our plan key
        try:
            items = sub.get("items", {}).get("data", [])
            price_id = items[0]["price"]["id"] if items else None
            plan = None
            if price_id == os.getenv("STRIPE_PRICE_PLUS_MONTHLY"): plan = "plus"
            if price_id == os.getenv("STRIPE_PRICE_PRO_MONTHLY"):  plan = "pro"
            if user_id and plan:
                storage.set_plan_for_user(user_id, plan)
                storage.set_identity_fields(user_id, stripeSubscriptionId=sub.get("id"))
        except Exception:
            pass

        # If cancel_at_period_end flips, you might want to store it for UI:
        # storage.set_identity_fields(user_id, cancelAt=sub.get("cancel_at_period_end"))

    elif event["type"] in ("customer.subscription.deleted", "invoice.payment_failed"):
        # Downgrade to free when subscription is deleted (or payment failed persistently)
        obj = event["data"]["object"]
        customer_id = obj.get("customer")
        try:
            snaps = storage.C_IDENTITY.where(filter=storage.FieldFilter("stripeCustomerId", "==", customer_id)).limit(1).get()
            if snaps:
                user_id = (snaps[0].to_dict() or {}).get("userID")
                if user_id:
                    storage.set_plan_for_user(user_id, "free")
        except Exception:
            pass

    # Always 200 to acknowledge receipt
    return {"received": True}
