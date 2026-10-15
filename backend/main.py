import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from routers import api_router
from payment import router as payment_router

# Load environment variables from .env file
load_dotenv()
print(f"[ENV] OK .env file loaded")
print(f"[ENV] SMTP_HOST: {os.getenv('SMTP_HOST')}")
print(f"[ENV] SMTP_USER: {os.getenv('SMTP_USER')}")
print(f"[ENV] SMTP_PASSWORD: {'***' + os.getenv('SMTP_PASSWORD', '')[-4:] if os.getenv('SMTP_PASSWORD') else 'None'}")

app = FastAPI(title="MediaFlow API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发环境）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(payment_router)
app.include_router(api_router)

app.mount("/uploads", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "uploads")), name="uploads")


@app.on_event("startup")
def startup():
    init_db()
    # 启动 Agent 自动运营调度器
    if os.getenv("AUTO_AGENT_ENABLED", "true").lower() == "true":
        from scheduler import start_scheduler
        start_scheduler()


@app.on_event("shutdown")
def shutdown():
    from scheduler import stop_scheduler
    stop_scheduler()


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
