# app/routes/share.py - Updated to use your existing thumbnail endpoint
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google.cloud import firestore
from app.services.storage_gcp import (
    C_META, geometry_blob_path, sign_path, last_chat_messages, record_progress, fetch_identity_min
)
from app.services.auth import get_current_user
from app.core.config import settings
import secrets

router = APIRouter(prefix="/share", tags=["share"])

# ───────────────────── OWNER: generate link ─────────────────────────
class CreateOut(BaseModel):
    slug: str
    url:  str
    preview_url: str

@router.post("/{pid}", response_model=CreateOut)
def create_share_link(pid: str, request: Request, user=Depends(get_current_user)):
    meta_ref = C_META.document(pid)
    meta     = meta_ref.get().to_dict() or {}
    if meta.get("ownerID") != user["sub"]:
        raise HTTPException(403, "Not your project")

    slug = meta.get("shareSlug") or secrets.token_urlsafe(6)[:8]
    meta_ref.set(
        {
            "shareSlug": slug,
            # write only if we actually have versions
            **(
                {
                    "shareBrainVer": meta.get("brainVersion"),
                    "shareCadVer":   meta.get("cadVersion"),
                }
                if meta.get("brainVersion") and meta.get("cadVersion")
                else {}
            ),
            "shareTS": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )

    ui_url = f"{settings.ui_origin.rstrip('/')}/s/{slug}"
    # Force preview on makistry.ai (not the incoming host)
    preview_url = f"{settings.ui_origin.rstrip('/')}/share/{slug}/preview"

    return {"slug": slug, "url": ui_url, "preview_url": preview_url}

# ───────────────────── PUBLIC: fetch share (API) ─────────────────────────
class ShareOut(BaseModel):
    project_id: str
    title:      str | None
    owner:      str | None
    owner_username: str | None = None
    brain_ver:  int | None
    cad_ver:    int | None
    stl_url:    str
    chat:       list

# app/routes/share.py
@router.get("/{slug}", response_model=ShareOut)
def fetch_share_api(slug: str):
    """API endpoint for React app"""
    q = C_META.where("shareSlug", "==", slug).limit(1).get()
    if not q:
        raise HTTPException(404, "Shared project not found")

    doc  = q[0]
    meta = doc.to_dict() or {}
    pid  = doc.id

    # ── Resolve versions (fallback for older share docs) ──────────
    brain_ver = meta.get("shareBrainVer") or meta.get("brainVersion")
    cad_ver   = meta.get("shareCadVer")   or meta.get("cadVersion")
    if cad_ver is None:
        raise HTTPException(404, "Shared design not available")

    cad_ver_i   = int(cad_ver)
    brain_ver_i = int(brain_ver) if brain_ver is not None else None

    # ── Pre-sign STL from deterministic path ──────────────────────
    stl_path = geometry_blob_path(pid, cad_ver_i, "stl")
    stl_url  = sign_path(stl_path, ttl_sec=86_400)

    # ── Normalize chat (avoid shadowing 'meta') ───────────────────
    raw  = last_chat_messages(pid, limit=40)
    chat = []
    for i, msg in enumerate(raw):
        role = (msg.get("role") or "assistant").lower()
        chat.append({
            "id": msg.get("id") or f"m{i}",
            "isUser": (role == "user"),
            "content": msg.get("content", ""),
        })

    # ── Counters & share credit ───────────────────────────────────
    C_META.document(pid).update({"shareViewCount": firestore.Increment(1)})

    owner_id = meta.get("ownerID")
    owner_username = None
    if owner_id:
        try:
            ident = fetch_identity_min([owner_id]).get(owner_id) or {}
            owner_username = ident.get("username") or None
        except Exception:
            pass
        try:
            record_progress(owner_id, "shares", unique_key=pid)
        except Exception:
            pass

    return {
        "project_id":   pid,
        "title":        meta.get("title"),
        "owner":        owner_id,
        "owner_username": owner_username,
        "brain_ver":    brain_ver_i,
        "cad_ver":      cad_ver_i,
        "stl_url":      stl_url,
        "chat":         chat,
    }


# ───────────────────── HTML with meta tags for social sharing ─────────────────────────
@router.get("/{slug}/preview", response_class=HTMLResponse)
def share_preview_html(slug: str, request: Request):
    """
    HTML page with proper Open Graph meta tags for social media.
    This should be served at the same URL as your React app for social crawlers.
    """
    try:
        q = C_META.where("shareSlug", "==", slug).limit(1).get()
        if not q:
            raise HTTPException(404, "Shared project not found")
        
        doc = q[0]
        m = doc.to_dict()
        pid = doc.id
        
        # Get project details
        title = m.get("title", "Untitled Makistry Design")
        owner_id = m.get("ownerID", "Anonymous")
        owner_username = None
        try:
            if owner_id and owner_id != "Anonymous":
                owner_username = fetch_identity_min([owner_id]).get(owner_id, {}).get("username")
        except Exception:
            pass
        cad_version = m.get("shareCadVer", 1)
        
        # Create description
        description = "Check out this 3D design created on Makistry!"
        if owner_username:
            description = f"Check out this 3D design by {owner_username} on Makistry!"
        
        thumbnail_url = request.url_for("get_social_thumbnail", project_id=pid, version=cad_version)
        
        # Current URL - use the /s/ format for sharing, not /share/
        share_url = f"{settings.ui_origin.rstrip('/')}/s/{slug}"
        
        # Clean title and description for HTML
        title_clean = title.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        description_clean = description.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title_clean} | Makistry</title>
    <meta name="description" content="{description_clean}" />
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website" />
    <meta property="og:url" content="{share_url}" />
    <meta property="og:title" content="{title_clean}" />
    <meta property="og:description" content="{description_clean}" />
    <meta property="og:image" content="{thumbnail_url}" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:image:type" content="image/png" />
    <meta property="og:site_name" content="Makistry" />
    
    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:url" content="{share_url}" />
    <meta name="twitter:title" content="{title_clean}" />
    <meta name="twitter:description" content="{description_clean}" />
    <meta name="twitter:image" content="{thumbnail_url}" />
    <meta name="twitter:site" content="@makistry" />
    
    <!-- LinkedIn - uses Open Graph tags but sometimes needs these specific ones -->
    <meta property="linkedin:owner" content="Makistry" />
    
    <!-- Additional tags for better crawling -->
    <meta property="article:author" content="{owner_username or 'Makistry User'}" />
    <meta property="article:publisher" content="Makistry" />
    
    <!-- Canonical URL -->
    <link rel="canonical" href="{share_url}" />
    
    <!-- Favicon -->
    <link rel="icon" href="/favicon.ico" />
    
    <!-- Structured Data for better SEO -->
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "name": "{title_clean}",
        "description": "{description_clean}",
        "image": "{thumbnail_url}",
        "url": "{share_url}",
        "author": {{
            "@type": "Person",
            "name": "{owner_username or 'Makistry User'}"
        }},
        "publisher": {{
            "@type": "Organization",
            "name": "Makistry"
        }}
    }}
    </script>
    
    <!-- Redirect to React app after meta tags are read -->
    <script>
        // Add a small delay to ensure meta tags are processed
        setTimeout(function() {{
            // Real browsers get bounced back to the UI
            if (!/bot|crawler|spider|facebookexternalhit|twitterbot|linkedinbot|whatsapp/i.test(navigator.userAgent)) {{
                window.location.replace("{share_url}");
            }}
        }}, 100);
    </script>
    
    <!-- Fallback for users with JS disabled -->
    <noscript>
        <meta http-equiv="refresh" content="2; url={share_url}" />
    </noscript>
</head>
<body style="margin: 0; padding: 50px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; text-align: center;">
    <div style="max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <img src="{thumbnail_url}" alt="{title_clean}" style="max-width: 100%; height: auto; border-radius: 8px; margin-bottom: 20px;" />
        <h1 style="color: #031926; margin-bottom: 16px; font-size: 2rem;">{title_clean}</h1>
        <p style="color: #64748b; margin-bottom: 24px; font-size: 1.1rem;">{description_clean}</p>
        <a href="{share_url}" style="display: inline-block; background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 500;">View Design on Makistry →</a>
        
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 0.9rem;">
            <p>Makistry - 3D Design Platform</p>
        </div>
    </div>
</body>
</html>"""
        
        return HTMLResponse(content=html_content, headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "X-Robots-Tag": "index, follow"
        })
        
    except Exception as e:
        print(f"Error generating share preview: {e}")
        # Fallback HTML for errors
        fallback_url = f"{settings.ui_origin.rstrip('/')}/s/{slug}"
        fallback_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Makistry Design</title>
    <meta name="description" content="3D design sharing platform" />
    <meta property="og:title" content="Makistry Design" />
    <meta property="og:description" content="3D design sharing platform" />
    <meta property="og:image" content="{settings.ui_origin}/thumbnail/default/1" />
    <meta property="og:url" content="{fallback_url}" />
    <meta http-equiv="refresh" content="0; url={fallback_url}" />
</head>
<body>
    <p><a href="{fallback_url}">View on Makistry</a></p>
</body>
</html>"""
        return HTMLResponse(content=fallback_html, status_code=404)