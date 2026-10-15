from datetime import datetime, timedelta
from typing import Optional
import uuid
import hashlib
import jwt
import os
import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User
from services.ai_service import AIService
from services.email_service import EmailService

# Load environment variables
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "mediaflow-secret-key-change-in-production")
ALGORITHM = "HS256"
MCP_PUBLISH_URL = "http://localhost:18060/api/v1/publish"

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "媒力 MediaFlow")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.utcnow() + timedelta(days=30)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")




def get_ai_service():
    """Get AI Service instance."""
    return AIService()


def get_email_service():
    """Get Email Service instance."""
    return EmailService()
