"""
Multi-Account Client Service
用于与本地运行的多账号管理器服务通信 (localhost:8080)
"""

import requests
from typing import Optional, Dict, Any, List
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from requests import Session
from requests.exceptions import RequestException, ConnectionError, Timeout, HTTPError
import os
import logging

logger = logging.getLogger(__name__)

# 多账号管理器服务默认地址
MULTI_ACCOUNT_MANAGER_URL = os.getenv("MULTI_ACCOUNT_MANAGER_URL", "http://localhost:8080")


class MultiAccountClient:
    """多账号管理器客户端"""
    
    def __init__(self, base_url: str = MULTI_ACCOUNT_MANAGER_URL, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_v1 = f"{self.base_url}/api/v1"
        self.timeout = timeout
        
        # 创建带有重试机制的会话
        self.session = Session()
        retries = Retry(
            total=3,
            backoff_factor=0.1,
            status_forcelist=[502, 503, 504],
            allowed_methods={'GET', 'POST', 'DELETE'},
        )
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
    
    def health_check(self) -> bool:
        """检查多账号管理器服务是否运行"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200 and response.json().get("status") == "ok"
        except Exception as e:
            logger.error(f"Multi-account manager health check failed: {e}")
            return False
    
    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        统一的HTTP请求方法，包含错误处理和重试逻辑
        
        Args:
            method: HTTP方法 ('GET', 'POST', 'DELETE')
            url: 完整的URL
            **kwargs: 传递给requests的其他参数
            
        Returns:
            成功时返回响应JSON数据，失败时返回错误信息字典
        """
        try:
            # 设置超时
            kwargs.setdefault('timeout', self.timeout)
            
            response = self.session.request(method, url, **kwargs)
            
            # 检查HTTP状态码 (2xx 都是成功)
            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except ValueError:
                    # 如果不是JSON响应，返回文本内容
                    return {"success": True, "data": response.text}
            elif response.status_code == 404:
                return {"success": False, "error": "Resource not found", "status_code": 404}
            elif response.status_code == 400:
                return {"success": False, "error": "Bad request", "status_code": 400}
            elif response.status_code >= 500:
                return {"success": False, "error": f"Server error: {response.status_code}", "status_code": response.status_code}
            else:
                return {"success": False, "error": f"Unexpected status code: {response.status_code}", "status_code": response.status_code}
                
        except ConnectionError as e:
            logger.error(f"Connection error calling {url}: {e}")
            return {"success": False, "error": "Failed to connect to multi-account manager"}
        except Timeout as e:
            logger.error(f"Timeout calling {url}: {e}")
            return {"success": False, "error": "Request timed out"}
        except HTTPError as e:
            logger.error(f"HTTP error calling {url}: {e}")
            return {"success": False, "error": f"HTTP error: {e}"}
        except RequestException as e:
            logger.error(f"Request failed calling {url}: {e}")
            return {"success": False, "error": f"Request failed: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error calling {url}: {e}")
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    def create_account(self, name: str) -> Dict[str, Any]:
        """
        创建新账户
        
        Args:
            name: 账户名称
            
        Returns:
            {"success": True, "account": {...}} 或 {"success": False, "error": "..."}
        """
        url = f"{self.api_v1}/accounts"
        payload = {"name": name}
        return self._make_request("POST", url, json=payload)
    
    def get_account(self, account_id: str) -> Dict[str, Any]:
        """
        获取指定账户信息
        
        Args:
            account_id: 账户ID
            
        Returns:
            {"success": True, "account": {...}} 或 {"success": False, "error": "..."}
        """
        url = f"{self.api_v1}/accounts/{account_id}"
        return self._make_request("GET", url)
    
    def list_accounts(self) -> Dict[str, Any]:
        """
        列出所有账户
        
        Returns:
            {"success": True, "accounts": [...]} 或 {"success": False, "error": "..."}
        """
        url = f"{self.api_v1}/accounts"
        return self._make_request("GET", url)
    
    def delete_account(self, account_id: str) -> Dict[str, Any]:
        """
        删除指定账户
        
        Args:
            account_id: 账户ID
            
        Returns:
            {"success": True} 或 {"success": False, "error": "..."}
        """
        url = f"{self.api_v1}/accounts/{account_id}"
        return self._make_request("DELETE", url)
    
    def get_qrcode(self, account_id: str) -> Dict[str, Any]:
        """
        获取账户登录二维码
        
        Args:
            account_id: 账户ID
            
        Returns:
            {"success": True, "qr_code": "...", "qr_code_url": "..."} 或 {"success": False, "error": "..."}
        """
        url = f"{self.api_v1}/accounts/{account_id}/qr"
        return self._make_request("POST", url)
    
    def check_login_status(self, account_id: str) -> Dict[str, Any]:
        """
        检查账户登录状态
        
        Args:
            account_id: 账户ID
            
        Returns:
            {"success": True, "status": "...", "is_logged_in": bool} 或 {"success": False, "error": "..."}
        """
        url = f"{self.api_v1}/accounts/{account_id}/status"
        return self._make_request("GET", url)
    
    def call_mcp_tool(self, account_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用MCP工具
        
        Args:
            account_id: 账户ID
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具返回结果
        """
        url = f"{self.api_v1}/accounts/{account_id}/mcp/message"
        payload = {
            "tool_name": tool_name,
            "arguments": arguments
        }
        return self._make_request("POST", url, json=payload)


# 全局客户端实例
multi_account_client = MultiAccountClient()