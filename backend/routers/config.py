import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User, ContentConfig
from dependencies import get_current_user

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    configs = db.query(ContentConfig).filter(ContentConfig.user_id == user.id).all()
    result = {}
    for config in configs:
        result[config.config_key] = config.config_value
    return {"configs": result}


@router.post("")
def save_config(
    request: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    config_key = request.get("config_key")
    config_value = request.get("config_value")
    
    if config_key and config_value is not None:
        config = db.query(ContentConfig).filter(
            ContentConfig.user_id == user.id,
            ContentConfig.config_key == config_key
        ).first()
        
        if config:
            config.config_value = config_value
        else:
            config = ContentConfig(
                id=str(uuid.uuid4()),
                user_id=user.id,
                config_key=config_key,
                config_value=config_value
            )
            db.add(config)
        
        db.commit()
        return {"message": "Config saved successfully", "config_key": config_key}
    else:
        config_data = {k: v for k, v in request.items() if k not in ["config_key", "config_value"]}
        
        saved_keys = []
        for key, value in config_data.items():
            config = db.query(ContentConfig).filter(
                ContentConfig.user_id == user.id,
                ContentConfig.config_key == key
            ).first()
            
            if config:
                config.config_value = value
            else:
                config = ContentConfig(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    config_key=key,
                    config_value=value
                )
                db.add(config)
            saved_keys.append(key)
        
        db.commit()
        return {"message": "Config saved successfully", "saved_keys": saved_keys}
