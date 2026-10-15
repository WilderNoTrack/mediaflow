import os
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Allowed image extensions
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def validate_image(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


@router.post("/images")
async def upload_images(images: List[UploadFile] = File(...)):
    uploaded_urls = []
    
    for image in images:
        if not image.filename:
            raise HTTPException(status_code=400, detail="Image filename is required")
        
        if not validate_image(image.filename):
            ext = os.path.splitext(image.filename)[1].lower()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {ext}. Allowed types: jpg, jpeg, png, gif, webp"
            )
        
        ext = os.path.splitext(image.filename)[1].lower()
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        try:
            content = await image.read()
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save image: {str(e)}")
        
        uploaded_urls.append(os.path.abspath(file_path))
    
    return {"success": True, "images": uploaded_urls}
