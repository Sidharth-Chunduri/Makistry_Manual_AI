# app/routes/thumbnails.py
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from app.services import storage
from app.services.auth import get_current_user
import tempfile, shutil, os, io
from google.cloud import firestore
from PIL import Image, ImageDraw, ImageFont
import requests

router = APIRouter(prefix="/thumbnail", tags=["thumbnail"])


def _is_stl_ver(pid: str, ver: int | None) -> bool:
    if ver is None:
        return False
    try:
        doc = storage.get_artifact(pid, f"cad_file_{int(ver)}_{pid}")
    except Exception:
        return False
    return bool(doc and (doc.get("data") or {}).get("export") == "stl")


def _latest_stl_ver(pid: str) -> int | None:
    try:
        docs = storage.list_artifacts(pid, "cad_file", latest=False) or []
    except Exception:
        return None
    stls = [d for d in docs if (d.get("data") or {}).get("export") == "stl"]
    if not stls:
        return None
    return max(int(d.get("version", 0)) for d in stls)


def _brain_for_cad_ver(pid: str, cad_ver: int | None) -> int | None:
    if cad_ver is None:
        return None
    try:
        bundles = storage.list_artifacts(pid, "version_bundle", latest=False) or []
    except Exception:
        return None
    best = None
    for b in bundles:
        data = b.get("data") or {}
        try:
            if int(data.get("cad_file_ver", -1)) == int(cad_ver):
                if (best is None) or int(b.get("version", 0)) > int(best.get("version", 0)):
                    best = b
        except Exception:
            continue
    if best:
        bv = (best.get("data") or {}).get("brainstorm_ver")
        return int(bv) if bv is not None else None
    return None


@router.post("")
async def upload_thumb(
    project_id: str = Form(...),
    version:   int   = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    # anybody with access can thumbnail – you may add owner check if needed
    fname = file.filename or "thumb.png"
    ext   = fname.split(".")[-1].lower()
    if ext not in {"png", "webp", "jpg", "jpeg"}:
        ext = "png"

    # save to tmp
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        url = storage.upload_thumbnail(tmp_path, project_id, version, ext)
        updates = {"preview": url, "updatedAt": firestore.SERVER_TIMESTAMP}

        try:
            if storage.stl_exists(project_id, int(version)):
                updates["cadVersion"] = int(version)
        except Exception:
            pass

        storage.C_META.document(project_id).update(updates)

        return {"url": url}
    finally:
        os.remove(tmp_path)


# NEW: GET endpoint for social media thumbnails
@router.get("/{project_id}/{version}")
async def get_social_thumbnail(project_id: str, version: int):
    """
    Generate or retrieve a thumbnail for social sharing.
    Returns a 1200x630 image (optimal for social media).
    
    Priority:
    1. User-uploaded thumbnail (if exists)
    2. Generated thumbnail with project info
    3. Default Makistry thumbnail
    """
    try:
        # First, check if user uploaded a custom thumbnail
        meta_doc = storage.C_META.document(project_id).get()
        if not meta_doc.exists:
            return await serve_default_thumbnail()
        
        meta = meta_doc.to_dict()
        
        # If user uploaded a thumbnail and it matches this version, use it
        user_thumbnail_url = storage.get_signed_preview(meta, project_id)
        if user_thumbnail_url and meta.get("cadVersion") == version:
            try:
                # Fetch the user's thumbnail and resize for social media
                response = requests.get(user_thumbnail_url, timeout=10)
                if response.status_code == 200:
                    user_img = Image.open(io.BytesIO(response.content))
                    social_img = resize_for_social_media(user_img)
                    
                    img_bytes = io.BytesIO()
                    social_img.save(img_bytes, format='PNG', optimize=True)
                    img_bytes.seek(0)
                    
                    return StreamingResponse(
                        io.BytesIO(img_bytes.getvalue()),
                        media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"}
                    )
            except Exception as e:
                print(f"Failed to fetch user thumbnail: {e}")
                # Fall through to generated thumbnail
        
        # Generate a branded thumbnail with project info
        title = meta.get("title", "Untitled Makistry Design")
        owner = meta.get("ownerID", "Anonymous")
        
        thumbnail = create_branded_thumbnail(title=title, owner=owner, version=version)
        
        img_bytes = io.BytesIO()
        thumbnail.save(img_bytes, format='PNG', optimize=True)
        img_bytes.seek(0)
        
        return StreamingResponse(
            io.BytesIO(img_bytes.getvalue()),
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Disposition": f"inline; filename=social_thumb_{project_id}_{version}.png"
            }
        )
        
    except Exception as e:
        print(f"Error generating social thumbnail: {e}")
        return await serve_default_thumbnail()


async def serve_default_thumbnail():
    """Serve the default Makistry thumbnail"""
    default_thumbnail = create_default_thumbnail()
    img_bytes = io.BytesIO()
    default_thumbnail.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return StreamingResponse(
        io.BytesIO(img_bytes.getvalue()),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"}
    )


def resize_for_social_media(img: Image.Image) -> Image.Image:
    """Resize user image to optimal social media dimensions (1200x630)"""
    target_width, target_height = 1200, 630
    
    # Calculate scaling to fit the image into the target size while maintaining aspect ratio
    img_ratio = img.width / img.height
    target_ratio = target_width / target_height
    
    if img_ratio > target_ratio:
        # Image is wider than target ratio
        new_width = target_width
        new_height = int(target_width / img_ratio)
    else:
        # Image is taller than target ratio
        new_height = target_height
        new_width = int(target_height * img_ratio)
    
    # Resize image
    resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Create final image with proper dimensions (center the resized image)
    final_img = Image.new('RGB', (target_width, target_height), color='#F8FAFC')
    
    # Center the resized image
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2
    final_img.paste(resized, (x_offset, y_offset))
    
    return final_img


def create_branded_thumbnail(title: str, owner: str, version: int) -> Image.Image:
    """Create a branded thumbnail with project title and owner info"""
    width, height = 1200, 630
    
    # Create base image with gradient background
    img = Image.new('RGB', (width, height), color='#F8FAFC')
    draw = ImageDraw.Draw(img)
    
    # Create subtle gradient
    for y in range(height):
        color_intensity = int(248 - (y / height) * 20)
        draw.line([(0, y), (width, y)], fill=(color_intensity, color_intensity, 252))
    
    # Try to load fonts (with fallbacks)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except:
        # Fallback fonts
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Truncate title if too long
    max_title_length = 50
    display_title = title[:max_title_length] + "..." if len(title) > max_title_length else title
    
    # Calculate text positions
    title_bbox = draw.textbbox((0, 0), display_title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_height = title_bbox[3] - title_bbox[1]
    
    # Center title
    title_x = (width - title_width) // 2
    title_y = height // 2 - 60
    
    # Draw title
    draw.text((title_x, title_y), display_title, fill='#031926', font=title_font)
    
    # Add "Created on Makistry" subtitle
    subtitle = "Created on Makistry"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (width - subtitle_width) // 2
    subtitle_y = title_y + title_height + 20
    
    draw.text((subtitle_x, subtitle_y), subtitle, fill='#64748B', font=subtitle_font)
    
    # Add owner info (if not "Anonymous")
    if owner and owner != "Anonymous":
        owner_text = f"by {owner}"
        owner_bbox = draw.textbbox((0, 0), owner_text, font=small_font)
        owner_width = owner_bbox[2] - owner_bbox[0]
        owner_x = (width - owner_width) // 2
        owner_y = subtitle_y + 50
        draw.text((owner_x, owner_y), owner_text, fill='#94A3B8', font=small_font)
    
    # Add version info
    version_text = f"v{version}"
    version_bbox = draw.textbbox((0, 0), version_text, font=small_font)
    version_width = version_bbox[2] - version_bbox[0]
    draw.text((width - version_width - 20, 20), version_text, fill='#94A3B8', font=small_font)
    
    # Add Makistry logo area (top-left)
    draw.text((20, 20), "Makistry", fill='#3B82F6', font=subtitle_font)
    
    # Add decorative elements
    # Top accent bar
    draw.rectangle([0, 0, width, 6], fill='#3B82F6')
    # Bottom accent bar
    draw.rectangle([0, height-6, width, height], fill='#3B82F6')
    
    return img


def create_default_thumbnail() -> Image.Image:
    """Create a default Makistry thumbnail"""
    width, height = 1200, 630
    
    # Create gradient background
    img = Image.new('RGB', (width, height), color='#3B82F6')
    draw = ImageDraw.Draw(img)
    
    # Create subtle gradient
    for y in range(height):
        blue_intensity = int(59 + (y / height) * 40)  # 59 to 99
        draw.line([(0, y), (width, y)], fill=(blue_intensity, 130, 246))
    
    try:
        logo_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 96)
        tagline_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        logo_font = ImageFont.load_default()
        tagline_font = ImageFont.load_default()
    
    # Main logo
    logo_text = "Makistry"
    logo_bbox = draw.textbbox((0, 0), logo_text, font=logo_font)
    logo_width = logo_bbox[2] - logo_bbox[0]
    logo_height = logo_bbox[3] - logo_bbox[1]
    
    logo_x = (width - logo_width) // 2
    logo_y = (height - logo_height) // 2 - 30
    
    draw.text((logo_x, logo_y), logo_text, fill='white', font=logo_font)
    
    # Tagline
    tagline = "3D Design Platform"
    tagline_bbox = draw.textbbox((0, 0), tagline, font=tagline_font)
    tagline_width = tagline_bbox[2] - tagline_bbox[0]
    tagline_x = (width - tagline_width) // 2
    tagline_y = logo_y + logo_height + 20
    
    draw.text((tagline_x, tagline_y), tagline, fill='#E5E7EB', font=tagline_font)
    
    return img
