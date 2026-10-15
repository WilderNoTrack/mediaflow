"""
小红书 MCP 客户端模块
用于与本地运行的 xiaohongshu-mcp 服务通信
"""

import requests
from typing import Optional, Dict, Any, List
import os
import logging
import uuid

logger = logging.getLogger(__name__)

# MCP 服务默认地址
MCP_BASE_URL = os.getenv("XIAOHONGSHU_MCP_URL", "http://localhost:18060")


class XiaohongshuMCPClient:
    """小红书 MCP 客户端"""
    
    def __init__(self, base_url: str = MCP_BASE_URL):
        self.base_url = base_url
        self.api_v1 = f"{base_url}/api/v1"
        self.mcp_endpoint = f"{base_url}/mcp"
    
    def health_check(self) -> bool:
        """检查 MCP 服务是否运行"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"MCP health check failed: {e}")
            return False
    
    def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具 (JSON-RPC 协议)
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具返回结果
        """
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            response = requests.post(
                self.mcp_endpoint,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if "error" in result:
                    logger.error(f"MCP tool error: {result['error']}")
                    return {"success": False, "error": result["error"]}
                # MCP 返回结果在 result.result 中
                return result.get("result", {"success": True})
            else:
                error_msg = response.text
                logger.error(f"MCP call failed: {error_msg}")
                return {"success": False, "error": error_msg}
        except Exception as e:
            logger.error(f"MCP request failed: {e}")
            return {"success": False, "error": str(e)}
    
    def search_users(self, keyword: str, limit: int = 10) -> Dict[str, Any]:
        """
        搜索小红书用户
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            {"success": True, "users": [...]}
        """
        return self._call_mcp_tool("search_users", {
            "keyword": keyword,
            "limit": limit
        })
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户资料
        
        Args:
            user_id: 小红书用户ID
            
        Returns:
            {"success": True, "profile": {...}}
        """
        return self._call_mcp_tool("get_user_profile", {
            "user_id": user_id
        })
    
    def get_current_user_profile(self) -> Dict[str, Any]:
        """
        获取当前登录用户资料
        
        Returns:
            {"success": True, "profile": {...}}
        """
        return self._call_mcp_tool("get_user_profile", {})
    
    def search_user_notes(self, keyword: str, limit: int = 10) -> Dict[str, Any]:
        """
        搜索笔记
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            {"success": True, "notes": [...]}
        """
        return self._call_mcp_tool("search_feeds", {
            "keyword": keyword,
            "limit": limit
        })
    
    def get_user_notes(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        """
        获取用户发布的笔记列表
        
        Args:
            user_id: 小红书用户ID
            limit: 返回结果数量限制
            
        Returns:
            {"success": True, "notes": [...]}
        """
        return self._call_mcp_tool("get_user_notes", {
            "user_id": user_id,
            "limit": limit
        })
    
    def publish_note(
        self, 
        title: str, 
        content: str, 
        images: List[str], 
        tags: List[str]
    ) -> Dict[str, Any]:
        """
        发布图文笔记到小红书
        
        Args:
            title: 笔记标题（最多 20 字）
            content: 笔记正文内容
            images: 图片路径列表（本地文件路径）
            tags: 话题标签列表
            
        Returns:
            {"success": True, "note_id": "...", "url": "..."}
        """
        payload = {
            "title": title,
            "content": content,
            "images": images,
            "tags": tags
        }
        
        try:
            response = requests.post(
                f"{self.api_v1}/publish",
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                error_msg = response.text
                logger.error(f"Publish failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
        except Exception as e:
            logger.error(f"Publish request failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# 全局客户端实例
mcp_client = XiaohongshuMCPClient()
