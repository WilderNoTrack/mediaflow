from fastapi import APIRouter
from .auth import router as auth_router
from .users import router as users_router
from .contents import router as contents_router
from .publish import router as publish_router
from .config import router as config_router
from .upload import router as upload_router
from .xiaohongshu_accounts import router as xiaohongshu_accounts_router
from .agent import router as agent_router
from .accounts_workspace import router as workspace_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(contents_router)
api_router.include_router(publish_router)
api_router.include_router(config_router)
api_router.include_router(upload_router)
api_router.include_router(xiaohongshu_accounts_router)
api_router.include_router(agent_router)
api_router.include_router(workspace_router)

__all__ = ["api_router"]
