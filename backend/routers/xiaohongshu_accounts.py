from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import uuid

from database import get_db
from models import User, XiaohongshuAccountBinding
from dependencies import get_current_user
from services.multi_account_client import multi_account_client

router = APIRouter(prefix="/api/xiaohongshu/accounts", tags=["xiaohongshu_accounts"])


class AccountCreate(BaseModel):
    name: str


class AccountResponse(BaseModel):
    id: str
    user_id: str
    mcp_account_id: str
    is_default: bool
    created_at: str

    class Config:
        from_attributes = True


class AccountListResponse(BaseModel):
    accounts: List[AccountResponse]


class QRCodeResponse(BaseModel):
    success: bool
    qrcode_data: Optional[str] = None
    qrcode_url: Optional[str] = None
    error: Optional[str] = None


class StatusResponse(BaseModel):
    success: bool
    logged_in: bool
    account: Optional[str] = None
    error: Optional[str] = None


@router.post("/")
def create_account(
    account_data: AccountCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new Xiaohongshu account binding
    """
    # Call MultiAccountClient.create_account() to create account in manager
    create_result = multi_account_client.create_account(account_data.name)
    
    if not create_result.get("success"):
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create account in manager: {create_result.get('error', 'Unknown error')}"
        )
    
    # Extract the MCP account ID from the created account
    mcp_account = create_result.get("account")
    if not mcp_account or not isinstance(mcp_account, dict):
        raise HTTPException(
            status_code=500, 
            detail="Invalid response from account manager"
        )
    
    mcp_account_id = mcp_account.get("id")
    if not mcp_account_id:
        raise HTTPException(
            status_code=500, 
            detail="Account manager did not return account ID"
        )
    
    # Create XiaohongshuAccountBinding record in database
    try:
        # Check if this MCP account ID is already bound to any user (shouldn't happen but be safe)
        existing_binding = db.query(XiaohongshuAccountBinding).filter(
            XiaohongshuAccountBinding.mcp_account_id == mcp_account_id
        ).first()
        
        if existing_binding:
            # If it exists, we should delete the old account from manager and create a new one
            # But for now, just raise an error
            multi_account_client.delete_account(mcp_account_id)
            raise HTTPException(
                status_code=500, 
                detail="MCP account ID already bound to another user"
            )
        
        # Create new binding
        new_binding = XiaohongshuAccountBinding(
            user_id=user.id,
            mcp_account_id=mcp_account_id,
            is_default=False  # Will be set to default later if needed
        )
        db.add(new_binding)
        db.commit()
        db.refresh(new_binding)
        
        # Return AccountResponse with binding details
        return AccountResponse(
            id=new_binding.id,
            user_id=new_binding.user_id,
            mcp_account_id=new_binding.mcp_account_id,
            is_default=new_binding.is_default,
            created_at=new_binding.created_at.isoformat()
        )
        
    except Exception as e:
        # If database operation fails, try to cleanup the account in manager
        try:
            multi_account_client.delete_account(mcp_account_id)
        except:
            pass  # Ignore cleanup errors
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/")
def list_accounts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all Xiaohongshu accounts for the current user
    """
    # Query XiaohongshuAccountBinding by user_id
    user_bindings = db.query(XiaohongshuAccountBinding).filter(
        XiaohongshuAccountBinding.user_id == user.id
    ).all()
    
    if not user_bindings:
        return AccountListResponse(accounts=[])
    
    # Get MCP account IDs for this user
    mcp_account_ids = [binding.mcp_account_id for binding in user_bindings]
    
    # Call MultiAccountClient.list_accounts() to get account details from manager
    list_result = multi_account_client.list_accounts()
    
    if not list_result.get("success"):
        # If manager is down, return basic binding info without manager details
        accounts = []
        for binding in user_bindings:
            accounts.append(AccountResponse(
                id=binding.id,
                user_id=binding.user_id,
                mcp_account_id=binding.mcp_account_id,
                is_default=binding.is_default,
                created_at=binding.created_at.isoformat()
            ))
        return AccountListResponse(accounts=accounts)
    
    # Create a map of MCP account ID to account details
    manager_accounts = {}
    accounts_list = list_result.get("accounts", [])
    if isinstance(accounts_list, list):
        for account in accounts_list:
            if isinstance(account, dict) and account.get("id"):
                manager_accounts[account["id"]] = account
    
    # Combine data and return AccountListResponse
    accounts = []
    for binding in user_bindings:
        account_response = AccountResponse(
            id=binding.id,
            user_id=binding.user_id,
            mcp_account_id=binding.mcp_account_id,
            is_default=binding.is_default,
            created_at=binding.created_at.isoformat()
        )
        accounts.append(account_response)
    
    return AccountListResponse(accounts=accounts)


@router.get("/{id}")
def get_account_details(
    id: str = Path(..., description="Account ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific Xiaohongshu account binding
    """
    # Verify binding belongs to user
    account_binding = db.query(XiaohongshuAccountBinding).filter(
        XiaohongshuAccountBinding.id == id,
        XiaohongshuAccountBinding.user_id == user.id
    ).first()
    
    if not account_binding:
        raise HTTPException(status_code=404, detail="Account binding not found or not owned by user")
    
    # Get details from MultiAccountClient.get_account()
    get_result = multi_account_client.get_account(account_binding.mcp_account_id)
    
    if not get_result.get("success"):
        # Even if manager fails, return basic binding info
        return AccountResponse(
            id=account_binding.id,
            user_id=account_binding.user_id,
            mcp_account_id=account_binding.mcp_account_id,
            is_default=account_binding.is_default,
            created_at=account_binding.created_at.isoformat()
        )
    
    # Return AccountResponse (we don't have additional details from manager in the response model)
    return AccountResponse(
        id=account_binding.id,
        user_id=account_binding.user_id,
        mcp_account_id=account_binding.mcp_account_id,
        is_default=account_binding.is_default,
        created_at=account_binding.created_at.isoformat()
    )


@router.delete("/{id}")
def delete_account(
    id: str = Path(..., description="Account ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a Xiaohongshu account binding
    """
    # Verify binding belongs to user
    account_binding = db.query(XiaohongshuAccountBinding).filter(
        XiaohongshuAccountBinding.id == id,
        XiaohongshuAccountBinding.user_id == user.id
    ).first()
    
    if not account_binding:
        raise HTTPException(status_code=404, detail="Account binding not found or not owned by user")
    
    mcp_account_id = account_binding.mcp_account_id
    
    try:
        # Delete binding from database first
        db.delete(account_binding)
        db.commit()
        
        # Call MultiAccountClient.delete_account() to cleanup in manager
        delete_result = multi_account_client.delete_account(mcp_account_id)
        
        if not delete_result.get("success"):
            # Log the error but don't fail the deletion since DB record is already gone
            # In a real app, we might want to implement some cleanup retry mechanism
            pass
        
        return {"message": "Account deleted successfully"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")


@router.put("/{id}/default")
def set_as_default(
    id: str = Path(..., description="Account ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Set the specified account as the default account for the user
    """
    # Verify binding belongs to user
    target_binding = db.query(XiaohongshuAccountBinding).filter(
        XiaohongshuAccountBinding.id == id,
        XiaohongshuAccountBinding.user_id == user.id
    ).first()
    
    if not target_binding:
        raise HTTPException(status_code=404, detail="Account binding not found or not owned by user")
    
    try:
        # Set is_default=False for all user's bindings
        db.query(XiaohongshuAccountBinding).filter(
            XiaohongshuAccountBinding.user_id == user.id
        ).update({XiaohongshuAccountBinding.is_default: False})
        
        # Set is_default=True for selected binding
        target_binding.is_default = True
        db.add(target_binding)
        db.commit()
        db.refresh(target_binding)
        
        return {"message": "Account set as default successfully"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to set default account: {str(e)}")


@router.post("/{id}/qrcode")
def get_qr_code(
    id: str = Path(..., description="Account ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get QR code for account login
    """
    # Verify XiaohongshuAccountBinding belongs to user
    account_binding = db.query(XiaohongshuAccountBinding).filter(
        XiaohongshuAccountBinding.id == id,
        XiaohongshuAccountBinding.user_id == user.id
    ).first()
    
    if not account_binding:
        raise HTTPException(status_code=404, detail="Account binding not found or not owned by user")
    
    # Call MultiAccountClient.get_qrcode(mcp_account_id)
    result = multi_account_client.get_qrcode(account_binding.mcp_account_id)
    
    if not result.get("success"):
        return QRCodeResponse(
            success=False,
            error=result.get("error", "Failed to get QR code from manager")
        )
    
    # Return QRCodeResponse with qrcode_data and qrcode_url
    return QRCodeResponse(
        success=True,
        qrcode_data=result.get("qr_code"),
        qrcode_url=result.get("qr_code_url")
    )


@router.get("/{id}/status")
def check_login_status(
    id: str = Path(..., description="Account ID"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check the login status of a Xiaohongshu account
    """
    # Verify XiaohongshuAccountBinding belongs to user
    account_binding = db.query(XiaohongshuAccountBinding).filter(
        XiaohongshuAccountBinding.id == id,
        XiaohongshuAccountBinding.user_id == user.id
    ).first()
    
    if not account_binding:
        raise HTTPException(status_code=404, detail="Account binding not found or not owned by user")
    
    # Call MultiAccountClient.check_login_status(mcp_account_id)
    result = multi_account_client.check_login_status(account_binding.mcp_account_id)
    
    if not result.get("success"):
        return StatusResponse(
            success=False,
            logged_in=False,
            error=result.get("error", "Failed to check login status from manager")
        )
    
    # Return StatusResponse with logged_in status and account info
    return StatusResponse(
        success=True,
        logged_in=result.get("is_logged_in", False),
        account=result.get("account") if result.get("is_logged_in") else None
    )