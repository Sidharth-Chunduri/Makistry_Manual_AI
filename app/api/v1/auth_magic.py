# app/api/v1/auth_magic.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from urllib.parse import quote, urlparse, urlunparse
from app.core.config import settings
import os
import requests
import resend
import json
import logging
from firebase_admin import auth as fb_auth

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("auth_magic")

class MagicLinkIn(BaseModel):
    email: EmailStr
    next: str = "/"

# ---------------- helpers ----------------

def _safe_next(path: str) -> str:
    return path if (isinstance(path, str) and path.startswith("/")) else "/"

def _norm_host_to_localhost(url: str) -> str:
    """If the host is 127.0.0.1, rewrite to localhost (helps Firebase authorized domains)."""
    try:
        p = urlparse(url)
        host = p.hostname or ""
        if host == "127.0.0.1":
            new_netloc = p.netloc.replace("127.0.0.1", "localhost")
            return urlunparse((p.scheme, new_netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        pass
    return url

def _ui_origin_from_request(request: Request) -> str:
    """
    Prefer settings.ui_origin. If missing, infer from Origin/Referer, else fallback.
    """
    o = getattr(settings, "ui_origin", None) or os.getenv("UI_ORIGIN", "")
    if isinstance(o, str) and o.startswith("http"):
        return o.rstrip("/")

    # Infer from headers
    for h in ("x-ui-origin", "origin", "referer"):
        v = request.headers.get(h)
        if not v:
            continue
        try:
            p = urlparse(v)
            if p.scheme in ("http", "https") and p.netloc:
                return f"{p.scheme}://{p.netloc}".rstrip("/")
        except Exception:
            continue

    # Dev fallback
    return "http://localhost:5173"

def _render_magic_link_email(link: str) -> tuple[str, str]:
    # Optional socials
    social_x        = getattr(settings, "social_x_url", None)
    social_linkedin = "https://www.linkedin.com/company/makistry"
    social_youtube  = getattr(settings, "social_youtube_url", None)
    social_ig       = getattr(settings, "social_instagram_url", None)

    socials_html_parts = []
    if social_x:        socials_html_parts.append(f'<a href="{social_x}" target="_blank" style="color:#0B5FFF;text-decoration:none;">X</a>')
    if social_linkedin: socials_html_parts.append(f'<a href="{social_linkedin}" target="_blank" style="color:#0B5FFF;text-decoration:none;">LinkedIn</a>')
    if social_youtube:  socials_html_parts.append(f'<a href="{social_youtube}" target="_blank" style="color:#0B5FFF;text-decoration:none;">YouTube</a>')
    if social_ig:       socials_html_parts.append(f'<a href="{social_ig}" target="_blank" style="color:#0B5FFF;text-decoration:none;">Instagram</a>')
    socials_html = " · ".join(socials_html_parts)

    html = f"""\
<!doctype html>
<html>
  <head>
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>Sign in to Makistry</title>
  </head>
  <body style="margin:0;padding:0;background:#ffffff;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#ffffff;">
      <tr>
        <td align="left" style="padding:24px 12px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;">
            <tr>
              <td style="padding:0 4px 18px 4px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#111;">
                <h1 style="margin:0 0 8px 0;font-size:20px;line-height:28px;font-weight:600;">Sign in to Makistry</h1>
                <p style="margin:0 0 10px 0;font-size:14px;line-height:22px;color:#333;">
                  Click the button below to finish signing in. This link can be used once and expires after a short time.
                </p>
              </td>
            </tr>
            <tr>
              <td align="left" style="padding:0 4px 16px 4px;">
                <a href="{link}" target="_blank"
                   style="display:inline-block;padding:10px 14px;border-radius:5px;background:#FFCA85;color:#000;
                          font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:14px;line-height:20px;
                          text-decoration:none;border:1px solid #E0B875;">
                  Sign in
                </a>
              </td>
            </tr>
            <tr>
              <td style="padding:0 4px 22px 4px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#333;">
                <p style="margin:0 0 8px 0;font-size:13px;line-height:20px;">
                  If the button doesn’t work:
                  <a href="{link}" target="_blank" style="color:#0B5FFF;text-decoration:underline;">Use this link to sign in</a>.
                </p>
              </td>
            </tr>
            <tr><td style="padding:8px 0;"><hr style="border:none;border-top:1px solid #eee;margin:0;" /></td></tr>
            {""
              if not socials_html
              else f'''<tr>
                        <td align="left" style="padding:12px 4px 6px 4px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#666;">
                          <p style="margin:0;font-size:12px;line-height:18px;">{socials_html}</p>
                        </td>
                      </tr>'''
            }
            <tr>
              <td style="padding:6px 4px 0 4px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#666;">
                <p style="margin:0;font-size:12px;line-height:18px;">
                  Didn’t request this? You can safely ignore this email.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    text = [
        "Sign in to Makistry",
        "",
        "Use this link to sign in:",
        link,
        "",
        "Didn’t request this? You can ignore this email.",
    ]
    if social_x := getattr(settings, "social_x_url", None):
        text.extend(["", f"X: {social_x}"])
    text.append("LinkedIn: https://www.linkedin.com/company/makistry")
    if social_youtube := getattr(settings, "social_youtube_url", None):
        text.append(f"YouTube: {social_youtube}")
    if social_ig := getattr(settings, "social_instagram_url", None):
        text.append(f"Instagram: {social_ig}")
    return html, "\n".join(text)

def _firebase_api_key() -> str:
    for attr in ("firebase_api_key", "firebase_web_api_key"):
        v = getattr(settings, attr, None)
        if v:
            return v
    for envname in ("FIREBASE_API_KEY", "VITE_FIREBASE_API_KEY"):
        v = os.getenv(envname)
        if v:
            return v
    raise HTTPException(500, "Missing Firebase Web API key (set FIREBASE_API_KEY).")

def _send_oob_email_link(email: str, continue_url: str) -> str:
    """
    Call Identity Toolkit REST to get the magic link.
    Retries once with localhost-normalized continue_url if Firebase rejects it.
    """
    api_key = _firebase_api_key()
    endpoint = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"

    dld = getattr(settings, "firebase_dynamic_link_domain", None)

    def _call(url: str):
        payload = {
            "requestType": "EMAIL_SIGNIN",
            "email": email,
            "continueUrl": url,
            "canHandleCodeInApp": True,
            "returnOobLink": True,
        }
        if dld:
            payload["dynamicLinkDomain"] = dld

        resp = requests.post(endpoint, json=payload, timeout=20)
        txt = resp.text or ""
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code == 200:
            link = data.get("oobLink")
            if not link:
                raise HTTPException(500, "Firebase sendOobCode returned no oobLink")
            return link

        # Extract Firebase error code/message for debugging
        err_msg = (data.get("error") or {}).get("message") or txt[:300]
        log.error("[auth_magic] sendOobCode failed (%s): %s", resp.status_code, err_msg)
        raise HTTPException(500, f"Firebase sendOobCode failed: {err_msg}")

    # First try as-is
    try:
        return _call(continue_url)
    except HTTPException as e:
        msg = str(e.detail or "").upper()
        # Retry once if continue URL looks like 127.0.0.1 (often not in Authorized domains)
        if "INVALID_CONTINUE_URI" in msg or "INVALID_DYNAMIC_LINK_DOMAIN" in msg or "DOMAIN" in msg:
            alt = _norm_host_to_localhost(continue_url)
            if alt != continue_url:
                log.info("[auth_magic] Retrying sendOobCode with normalized continueUrl: %s", alt)
                return _call(alt)
        # Surface original error
        raise

# ---------------- route ----------------

@router.post("/magic_link")
def create_and_send_magic_link(body: MagicLinkIn, request: Request):
    email = body.email.lower()
    next_path = _safe_next(body.next)

    ui_origin = _ui_origin_from_request(request)
    # Prefer a stable configured origin to avoid header-caused domain mismatches
    cfg_origin = getattr(settings, "ui_origin", None)
    if isinstance(cfg_origin, str) and cfg_origin.startswith("http"):
        ui_origin = cfg_origin.rstrip("/")

    continue_url = f"{ui_origin}/finish-login?next={quote(next_path)}"

    # 1) Get the Firebase email link
    link = _send_oob_email_link(email, continue_url)

    # 2) Send via Resend (or return link if email isn't configured)
    resend_api_key = getattr(settings, "resend_api_key", None) or os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        # Dev mode: don't block — return the link so UI can show a copy button
        return {"ok": True, "link": link, "warn": "RESEND_API_KEY missing; email not sent"}

    try:
        resend.api_key = resend_api_key
        from_addr = (
            getattr(settings, "resend_from", None)
            or f"Makistry <contact@{getattr(settings, 'resend_domain', 'makistry.com')}>"
        )
        html, text = _render_magic_link_email(link)

        resend.Emails.send({
            "from": from_addr,
            "to": [email],
            "subject": "Sign in to Makistry",
            "html": html,
            "text": text,
        })
        return {"ok": True}
    except Exception as e:
        # Fail open: send the link back so flow can proceed
        log.error("[auth_magic] Resend failed: %s", e)
        return {"ok": True, "link": link, "warn": f"Email not sent: {e}"}

def _send_oob_email_link(email: str, continue_url: str) -> str:
    """
    Prefer Firebase Admin SDK to generate the passwordless sign-in link
    (no Web API key / API restrictions involved). Fall back to REST only if needed.
    """
    dld = getattr(settings, "firebase_dynamic_link_domain", None)

    # --- Try Admin SDK (recommended) ---
    try:
        acs = fb_auth.ActionCodeSettings(
            url=continue_url,
            handle_code_in_app=True,
            dynamic_link_domain=dld if dld else None,
        )
        link = fb_auth.generate_sign_in_with_email_link(email, acs)
        if not link:
            raise ValueError("Admin SDK returned empty link")
        return link
    except Exception as e:
        log.warning("[auth_magic] Admin SDK generate link failed: %s; falling back to REST", e)

    # --- Fallback: existing REST path (unchanged) ---
    return _send_oob_email_link_via_rest(email, continue_url)

# Rename your existing REST implementation to this helper:
def _send_oob_email_link_via_rest(email: str, continue_url: str) -> str:
    api_key = _firebase_api_key()
    endpoint = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"
    dld = getattr(settings, "firebase_dynamic_link_domain", None)

    def _call(url: str):
        payload = {
            "requestType": "EMAIL_SIGNIN",
            "email": email,
            "continueUrl": url,
            "canHandleCodeInApp": True,
            "returnOobLink": True,
        }
        if dld:
            payload["dynamicLinkDomain"] = dld

        resp = requests.post(endpoint, json=payload, timeout=20)
        txt = resp.text or ""
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code == 200:
            link = data.get("oobLink")
            if not link:
                raise HTTPException(500, "Firebase sendOobCode returned no oobLink")
            return link

        err_msg = (data.get("error") or {}).get("message") or txt[:300]
        log.error("[auth_magic] sendOobCode failed (%s): %s", resp.status_code, err_msg)
        raise HTTPException(500, f"Firebase sendOobCode failed: {err_msg}")

    # First try as-is, then retry with 127.0.0.1→localhost normalization
    try:
        return _call(continue_url)
    except HTTPException as e:
        msg = str(e.detail or "").upper()
        if "INVALID_CONTINUE_URI" in msg or "INVALID_DYNAMIC_LINK_DOMAIN" in msg or "DOMAIN" in msg:
            alt = _norm_host_to_localhost(continue_url)
            if alt != continue_url:
                log.info("[auth_magic] Retrying sendOobCode with normalized continueUrl: %s", alt)
                return _call(alt)
        raise