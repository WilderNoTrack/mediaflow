from datetime import datetime, timedelta
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models import User, Subscription, EmailVerificationCode, SubscriptionPlan, SubscriptionStatus
from dependencies import (
    hash_password, create_token, get_email_service
)
from services.email_service import EmailService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def generate_verification_code() -> str:
    """Generate a 6-digit verification code."""
    import random
    return "".join([str(random.randint(0, 9)) for _ in range(6)])


class LoginRequest(BaseModel):
    phone: str | None = None
    email: str | None = None
    password: str


class RegisterRequest(BaseModel):
    phone: str | None = None
    email: str | None = None
    password: str
    nickname: str | None = None
    code: str | None = None


class SendCodeRequest(BaseModel):
    email: str
    purpose: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if not req.phone and not req.email:
        raise HTTPException(status_code=400, detail="Phone or email required")
    
    if req.email and req.code:
        now = datetime.utcnow()
        verification = db.query(EmailVerificationCode).filter(
            EmailVerificationCode.email == req.email,
            EmailVerificationCode.code == req.code,
            EmailVerificationCode.purpose == "register",
            EmailVerificationCode.used == False,
            EmailVerificationCode.expires_at > now
        ).first()
        
        if not verification:
            raise HTTPException(status_code=400, detail="Invalid or expired verification code")
        
        verification.used = True  # type: ignore  # type: ignore
        db.commit()
    elif req.email and not req.code:
        raise HTTPException(status_code=400, detail="Verification code is required for email registration")
    
    existing = None
    if req.phone:
        existing = db.query(User).filter(User.phone == req.phone).first()
    if not existing and req.email:
        existing = db.query(User).filter(User.email == req.email).first()
    
    if existing:
        print(f"[API] 用户已存在：phone={req.phone}, email={req.email}")
        raise HTTPException(status_code=400, detail="User already exists")
    print(f"[API] 用户不存在，继续注册")
    
    user = User(
        id=str(uuid.uuid4()),
        phone=req.phone,
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=req.nickname
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    trial_end = datetime.utcnow() + timedelta(days=7)
    subscription = Subscription(
        id=str(uuid.uuid4()),
        user_id=user.id,
        plan=SubscriptionPlan.basic,
        status=SubscriptionStatus.trial,
        trial_start=datetime.utcnow(),
        trial_end=trial_end
    )
    db.add(subscription)
    db.commit()
    
    token = create_token(user.id)  # type: ignore
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": str(user.id),
        "phone": user.phone,
        "email": user.email,
        "nickname": user.nickname
    }}


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    if not req.phone and not req.email:
        raise HTTPException(status_code=400, detail="Phone or email required")
    
    if req.email:
        user = db.query(User).filter(User.email == req.email).first()
    elif req.phone:
        user = db.query(User).filter(User.phone == req.phone).first()
    else:
        raise HTTPException(status_code=400, detail="Invalid login credentials")
    
    if not user or user.password_hash != hash_password(req.password):  # type: ignore
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user.id)  # type: ignore
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": str(user.id),
        "phone": user.phone,
        "email": user.email,
        "nickname": user.nickname
    }}


@router.post("/send-code")
async def send_code(
    req: SendCodeRequest,
    db: Session = Depends(get_db),
    email_service: EmailService = Depends(get_email_service)
):
    print(f"[API]  收到发送验证码请求：email={req.email}, purpose={req.purpose}")
    
    if req.purpose not in ["register", "reset_password"]:
        raise HTTPException(status_code=400, detail="Invalid purpose")
    
    if req.purpose == "register":
        existing = db.query(User).filter(User.email == req.email).first()
        if existing:
            print(f"[API] 邮箱已注册：{req.email}")
            raise HTTPException(status_code=400, detail="Email already registered")
        print(f"[API] 邮箱未注册，继续")
    
    now = datetime.utcnow()
    print(f"[API] 检查频率限制：email={req.email}, purpose={req.purpose}, 限制=60 秒")
    recent_code = db.query(EmailVerificationCode).filter(
        EmailVerificationCode.email == req.email,
        EmailVerificationCode.purpose == req.purpose,
        EmailVerificationCode.created_at > now - timedelta(seconds=60)
    ).first()
    
    if recent_code:
        wait_time = 60 - int((now - recent_code.created_at).total_seconds())
        print(f"[API] 频率限制触发：需等待 {wait_time} 秒 (recent_code.created_at={recent_code.created_at})")
        raise HTTPException(status_code=429, detail=f"Please wait {wait_time} seconds before requesting another code")
    else:
        print(f"[API] 频率限制检查通过")
    
    code = generate_verification_code()
    expires_at = now + timedelta(minutes=5)
    print(f"[API]  生成验证码：{code}")
    
    verification = EmailVerificationCode(
        id=str(uuid.uuid4()),
        email=req.email,
        code=code,
        purpose=req.purpose,
        expires_at=expires_at
    )
    db.add(verification)
    db.commit()
    print(f"[API]  验证码已保存到数据库")
    
    success = await email_service.send_verification_code(req.email, code, req.purpose)
    
    if success:
        print(f"[API] 邮件发送成功")
        return {"message": "Verification code sent successfully", "expires_in": 300}
    else:
        print(f"[API] 邮件发送失败")
        db.delete(verification)
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to send verification code")


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    
    verification = db.query(EmailVerificationCode).filter(
        EmailVerificationCode.email == req.email,
        EmailVerificationCode.code == req.code,
        EmailVerificationCode.purpose == "reset_password",
        EmailVerificationCode.used == False,
        EmailVerificationCode.expires_at > now
    ).first()
    
    if not verification:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.password_hash = hash_password(req.new_password)  # type: ignore
    user.updated_at = now  # type: ignore
    
    verification.used = True  # type: ignore
    
    db.commit()
    
    return {"message": "Password reset successfully"}
