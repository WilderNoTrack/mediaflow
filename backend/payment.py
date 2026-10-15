from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import os
from datetime import datetime

router = APIRouter(prefix="/api/payment", tags=["支付"])

# 支付宝沙箱配置（可选）
ALIPAY_APP_ID = os.getenv("ALIPAY_APP_ID", "")
ALIPAY_GATEWAY = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"


class CreateOrderRequest(BaseModel):
    """创建支付订单请求"""
    subject: str  # 订单标题
    total_amount: float  # 订单金额
    out_trade_no: str  # 商户订单号
    product_code: str = "FAST_INSTANT_TRADE_PAY"  # 产品码


class CreateOrderResponse(BaseModel):
    """创建支付订单响应"""
    success: bool
    alipay_url: Optional[str] = None
    order_id: Optional[str] = None
    message: str


@router.post("/create", response_model=CreateOrderResponse)
async def create_payment_order(request: CreateOrderRequest):
    """创建支付宝支付订单"""
    if not ALIPAY_APP_ID:
        # 返回模拟订单（开发模式）
        return CreateOrderResponse(
            success=True,
            alipay_url="https://openapi-sandbox.dl.alipaydev.com/demo",
            order_id=request.out_trade_no,
            message="沙箱环境未配置，返回模拟订单（生产环境需配置 ALIPAY_APP_ID）"
        )
    
    # 构建支付 URL（简化版）
    alipay_url = f"{ALIPAY_GATEWAY}?app_id={ALIPAY_APP_ID}&method=alipay.trade.page.pay"
    
    return CreateOrderResponse(
        success=True,
        alipay_url=alipay_url,
        order_id=request.out_trade_no,
        message="订单创建成功，请跳转到支付宝页面完成支付"
    )


@router.get("/callback")
async def payment_callback():
    """支付宝支付回调"""
    # TODO: 验证签名并更新订单状态
    return {"success": True, "message": "支付成功"}


@router.get("/query/{out_trade_no}")
async def query_order_status(out_trade_no: str):
    """查询订单状态"""
    # 模拟查询（实际需调用支付宝 API）
    return {
        "success": True,
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": out_trade_no
    }
