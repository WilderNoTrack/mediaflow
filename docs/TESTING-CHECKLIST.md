# MediaFlow 后端测试清单

**目的**: 确保模块化重构后所有功能正常
**测试工具**: Postman / curl / pytest
**测试环境**: 本地开发环境

---

## 📋 目录

1. [测试准备](#1-测试准备)
2. [模块测试清单](#2-模块测试清单)
3. [集成测试](#3-集成测试)
4. [性能测试](#4-性能测试)
5. [安全测试](#5-安全测试)
6. [测试报告模板](#6-测试报告模板)

---

## 1. 测试准备

### 1.1 环境配置

**确保以下环境已就绪**:

- [ ] Python 3.10+ 已安装
- [ ] 虚拟环境已创建：`python -m venv venv`
- [ ] 依赖已安装：`pip install -r requirements.txt`
- [ ] 数据库已初始化：`python -c "from database import init_db; init_db()"`
- [ ] 环境变量已配置：`.env` 文件存在
- [ ] 后端服务已启动：`python -m uvicorn main:app --reload`

### 1.2 测试账号准备

**创建测试账号**:

```bash
# 使用 Postman 或 curl 注册测试账号
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123456",
    "nickname": "测试用户"
  }'
```

**保存返回的 Token**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {...}
}
```

### 1.3 测试工具

**Postman 配置**:
1. 创建新的 Collection：`MediaFlow Backend Tests`
2. 配置 Base URL：`http://localhost:8000`
3. 添加环境变量：`{{token}}` 存储 access_token
4. 配置 Authorization：Bearer {{token}}

---

## 2. 模块测试清单

### 2.1 Auth 模块测试

#### 测试组 1: 用户注册

**TC-AUTH-001: 正常注册（手机号）**
```bash
# 准备
POST /api/auth/register
Headers: {"Content-Type": "application/json"}
Body: {
  "phone": "13800138000",
  "password": "Test123456",
  "nickname": "测试用户A"
}

# 预期结果
Status: 201 Created
Response: {
  "access_token": "string",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "phone": "13800138000",
    "nickname": "测试用户A"
  }
}

# 验证点
- [ ] 状态码为 201
- [ ] 返回 access_token
- [ ] 返回用户信息
- [ ] 数据库中创建了用户记录
- [ ] 数据库中创建了订阅记录（trial 状态）
- [ ] 数据库中创建了 AI 员工记录
```

**TC-AUTH-002: 正常注册（邮箱 + 验证码）**
```bash
# 步骤 1: 发送验证码
POST /api/auth/send-code
Body: {
  "email": "test@example.com",
  "purpose": "register"
}

# 验证
- [ ] 状态码为 200
- [ ] 返回 expires_in: 300

# 步骤 2: 使用验证码注册
POST /api/auth/register
Body: {
  "email": "test@example.com",
  "password": "Test123456",
  "code": "123456"  # 从控制台或邮件获取
}

# 验证
- [ ] 状态码为 201
- [ ] 用户创建成功
```

**TC-AUTH-003: 注册失败 - 缺少必填字段**
```bash
POST /api/auth/register
Body: {
  "password": "Test123456"
}

# 预期结果
Status: 400 Bad Request
Response: {"detail": "Phone or email required"}

# 验证点
- [ ] 状态码为 400
- [ ] 返回正确错误信息
```

**TC-AUTH-004: 注册失败 - 邮箱缺少验证码**
```bash
POST /api/auth/register
Body: {
  "email": "test@example.com",
  "password": "Test123456"
}

# 预期结果
Status: 400 Bad Request
Response: {"detail": "Verification code is required for email registration"}

# 验证点
- [ ] 状态码为 400
- [ ] 返回正确错误信息
```

**TC-AUTH-005: 注册失败 - 用户已存在**
```bash
# 先注册一个用户
POST /api/auth/register
Body: {"phone": "13800138000", "password": "Test123456"}

# 再次注册相同手机号
POST /api/auth/register
Body: {"phone": "13800138000", "password": "Test123456"}

# 预期结果
Status: 400 Bad Request
Response: {"detail": "User already exists"}

# 验证点
- [ ] 状态码为 400
- [ ] 不会创建重复用户
```

---

#### 测试组 2: 用户登录

**TC-AUTH-006: 正常登录（手机号）**
```bash
POST /api/auth/login
Body: {
  "phone": "13800138000",
  "password": "Test123456"
}

# 预期结果
Status: 200 OK
Response: {
  "access_token": "string",
  "token_type": "bearer",
  "user": {...}
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回 access_token
- [ ] Token 有效期为 30 天
```

**TC-AUTH-007: 正常登录（邮箱）**
```bash
POST /api/auth/login
Body: {
  "email": "test@example.com",
  "password": "Test123456"
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回 access_token
```

**TC-AUTH-008: 登录失败 - 用户不存在**
```bash
POST /api/auth/login
Body: {
  "phone": "19999999999",
  "password": "Test123456"
}

# 预期结果
Status: 401 Unauthorized
Response: {"detail": "Invalid credentials"}

# 验证点
- [ ] 状态码为 401
```

**TC-AUTH-009: 登录失败 - 密码错误**
```bash
POST /api/auth/login
Body: {
  "phone": "13800138000",
  "password": "WrongPassword"
}

# 预期结果
Status: 401 Unauthorized
Response: {"detail": "Invalid credentials"}

# 验证点
- [ ] 状态码为 401
```

---

#### 测试组 3: 发送验证码

**TC-AUTH-010: 正常发送验证码**
```bash
POST /api/auth/send-code
Body: {
  "email": "new@example.com",
  "purpose": "register"
}

# 预期结果
Status: 200 OK
Response: {
  "message": "Verification code sent successfully",
  "expires_in": 300
}

# 验证点
- [ ] 状态码为 200
- [ ] 验证码有效期为 300 秒
- [ ] 数据库中保存了验证码记录
```

**TC-AUTH-011: 发送验证码失败 - 邮箱已注册**
```bash
# 假设 new@example.com 已经注册
POST /api/auth/send-code
Body: {
  "email": "new@example.com",
  "purpose": "register"
}

# 预期结果
Status: 400 Bad Request
Response: {"detail": "Email already registered"}

# 验证点
- [ ] 状态码为 400
```

**TC-AUTH-012: 发送验证码失败 - 频率限制**
```bash
# 第一次发送
POST /api/auth/send-code
Body: {"email": "test@example.com", "purpose": "register"}

# 立即再次发送
POST /api/auth/send-code
Body: {"email": "test@example.com", "purpose": "register"}

# 预期结果
Status: 429 Too Many Requests
Response: {"detail": "Please wait 1 seconds before requesting another code"}

# 验证点
- [ ] 状态码为 429
- [ ] 等待 1 秒后可以再次发送
```

---

#### 测试组 4: 重置密码

**TC-AUTH-013: 正常重置密码**
```bash
# 步骤 1: 发送验证码
POST /api/auth/send-code
Body: {
  "email": "test@example.com",
  "purpose": "reset_password"
}

# 步骤 2: 重置密码
POST /api/auth/reset-password
Body: {
  "email": "test@example.com",
  "code": "123456",
  "new_password": "NewPassword123"
}

# 预期结果
Status: 200 OK
Response: {"message": "Password reset successfully"}

# 验证点
- [ ] 状态码为 200
- [ ] 新密码可以正常登录
```

**TC-AUTH-014: 重置密码失败 - 验证码无效**
```bash
POST /api/auth/reset-password
Body: {
  "email": "test@example.com",
  "code": "000000",  # 错误的验证码
  "new_password": "NewPassword123"
}

# 预期结果
Status: 400 Bad Request
Response: {"detail": "Invalid or expired verification code"}

# 验证点
- [ ] 状态码为 400
```

---

### 2.2 Users 模块测试

#### 测试组 5: 获取用户资料

**TC-USERS-001: 正常获取用户资料**
```GET /api/user/profile
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 预期结果
Status: 200 OK
Response: {
  "id": "uuid",
  "email": "test@example.com",
  "nickname": "测试用户",
  "subscription": {...},
  "lobster": {...},
  "xiaohongshu_account": null
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回完整的用户信息
- [ ] 返回订阅信息
- [ ] 返回 AI 员工信息
```

**TC-USERS-002: 获取用户资料失败 - 未认证**
```GET /api/user/profile
# 不带 Authorization header

# 预期结果
Status: 401 Unauthorized
Response: {"detail": "Not authenticated"}

# 验证点
- [ ] 状态码为 401
```

---

#### 测试组 6: 学习用户偏好

**TC-USERS-003: 正常学习偏好**
```POST /api/user/preferences/learn
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 预期结果
Status: 200 OK
Response: {
  "message": "Preferences learned successfully",
  "learned": true,
  "preferences": {
    "domain": "hiphop",
    "content_style": "轻松搞笑",
    ...
  }
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回学习到的偏好
- [ ] 数据库中更新了偏好记录
```

---

### 2.3 Lobsters 模块测试

#### 测试组 7: 创建/更新 AI 员工

**TC-LOBSTERS-001: 创建 AI 员工**
```POST /api/lobsters/create-or-update
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "name": "阿龙",
  "domain": "hiphop",
  "status": "running"
}

# 预期结果
Status: 200 OK
Response: {
  "message": "Lobster created/updated successfully",
  "lobster": {...}
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回 AI 员工信息
```

**TC-LOBSTERS-002: 更新 AI 员工**
```POST /api/lobsters/create-or-update
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "domain": "food"
}

# 验证点
- [ ] 状态码为 200
- [ ] 域名从 hiphop 更新为 food
```

---

#### 测试组 8: 获取 AI 员工详情

**TC-LOBSTERS-003: 正常获取 AI 员工**
```GET /api/lobsters/me
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回完整的 AI 员工信息
- [ ] 返回偏好设置
```

---

### 2.4 Chat 模块测试

#### 测试组 9: 对话式配置

**TC-CHAT-001: 正常对话**
```POST /api/chat/config
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "message": "我想做嘻哈资讯账号，每天晚上发布"
}

# 预期结果
Status: 200 OK
Response: {
  "message": "好的老板！嘻哈资讯很棒🎵...",
  "extracted_config": {
    "domain": "hiphop",
    "publish_frequency": "daily",
    "publish_time": ["18:00", "20:00"]
  },
  "saved": true
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回 AI 响应
- [ ] 提取配置正确
- [ ] 保存对话历史
- [ ] 更新用户偏好
```

---

#### 测试组 10: 对话历史

**TC-CHAT-002: 保存对话历史**
```POST /api/chat/history
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "message": "用户发的消息",
  "role": "user"
}

# 验证点
- [ ] 状态码为 200
- [ ] 数据库中保存了对话记录
```

**TC-CHAT-003: 获取对话历史**
```GET /api/chat/history?limit=10
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回最近的 10 条对话
- [ ] 对话按时间倒序排列
```

---

### 2.5 Contents 模块测试

#### 测试组 11: 创建内容

**TC-CONTENTS-001: 正常创建内容**
```POST /api/contents
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "title": "测试标题",
  "content": "测试内容",
  "images": ["image1.jpg"],
  "tags": ["标签1", "标签2"]
}

# 预期结果
Status: 201 Created
Response: {
  "message": "Content created successfully",
  "content": {...}
}

# 验证点
- [ ] 状态码为 201
- [ ] 返回内容信息
- [ ] 数据库中保存了内容记录
```

---

#### 测试组 12: 获取内容列表

**TC-CONTENTS-002: 获取所有内容**
```GET /api/contents
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回内容列表
```

**TC-CONTENTS-003: 按状态过滤内容**
```GET /api/contents?status=published
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 验证点
- [ ] 状态码为 200
- [ ] 只返回已发布的内容
```

---

#### 测试组 13: 更新内容

**TC-CONTENTS-004: 正常更新内容**
```PUT /api/contents/{content_id}
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "title": "更新后的标题",
  "status": "pending"
}

# 验证点
- [ ] 状态码为 200
- [ ] 内容已更新
```

---

#### 测试组 14: 删除内容

**TC-CONTENTS-005: 正常删除内容**
```DELETE /api/contents/{content_id}
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 验证点
- [ ] 状态码为 200
- [ ] 数据库中内容已删除
```

---

### 2.6 Publish 模块测试

#### 测试组 15: 发布到小红书

**TC-PUBLISH-001: 正常发布**
```POST /api/publish
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "title": "测试笔记",
  "content": "测试内容",
  "images": ["image1.jpg"]
}

# 前提条件：用户已绑定小红书账号

# 预期结果
Status: 200 OK
Response: {
  "status": "success",
  "note_id": "1234567890",
  "content_id": "uuid"
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回小红书笔记 ID
- [ ] 创建发布日志
```

**TC-PUBLISH-002: 发布失败 - 未绑定小红书账号**
```POST /api/publish
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {...}

# 预期结果
Status: 400 Bad Request
Response: {"detail": "No Xiaohongshu account bound"}

# 验证点
- [ ] 状态码为 400
```

---

#### 测试组 16: 获取发布日志

**TC-PUBLISH-003: 正常获取发布日志**
```GET /api/publish/logs
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回发布日志列表
```

---

### 2.7 Config 模块测试

#### 测试组 17: 保存配置

**TC-CONFIG-001: 保存单个配置**
```POST /api/config
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "config_key": "domain",
  "config_value": "hiphop"
}

# 验证点
- [ ] 状态码为 200
- [ ] 数据库中保存了配置
```

**TC-CONFIG-002: 批量保存配置**
```POST /api/config
Headers: {
  "Authorization": "Bearer {{token}}"
}
Body: {
  "domain": "hiphop",
  "content_style": "轻松搞笑",
  "publish_frequency": "daily"
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回 saved_keys
```

---

#### 测试组 18: 获取配置

**TC-CONFIG-003: 正常获取配置**
```GET /api/config
Headers: {
  "Authorization": "Bearer {{token}}"
}

# 预期结果
Status: 200 OK
Response: {
  "configs": {
    "domain": "hiphop",
    "content_style": "轻松搞笑",
    ...
  }
}

# 验证点
- [ ] 状态码为 200
- [ ] 返回所有配置
```

---

## 3. 集成测试

### 集成测试组 1: 完整用户流程

**TC-INT-001: 注册 → 登录 → 获取资料**
```bash
# 1. 注册
POST /api/auth/register
→ 保存 access_token

# 2. 使用 Token 获取资料
GET /api/user/profile
→ 验证返回正确用户信息
```

### 集成测试组 2: 完整内容流程

**TC-INT-002: 创建内容 → 发布 → 查看日志**
```bash
# 1. 创建内容
POST /api/contents
→ 保存 content_id

# 2. 发布内容
POST /api/publish
→ 保存 note_id

# 3. 查看发布日志
GET /api/publish/logs
→ 验证返回发布的日志
```

### 集成测试组 3: 完整对话流程

**TC-INT-003: 对话 → 提取配置 → 更新偏好**
```bash
# 1. 发送对话消息
POST /api/chat/config
→ 保存 extracted_config

# 2. 获取 AI 员工详情
GET /api/lobsters/me
→ 验证 preferences 已更新
```

---

## 4. 性能测试

### TC-PERF-001: 并发请求处理

**测试方法**:
```python
import asyncio
import httpx

async def test_concurrent_requests():
    client = httpx.AsyncClient()
    
    async def make_request():
        return await client.get("http://localhost:8000/health")
    
    # 同时发送 100 个请求
    response = await asyncio.gather(*[make_request() for _ in range(100)])
    
    print(f"Success: {sum(1 for r in response if r.status_code == 200)}")

asyncio.run(test_concurrent_requests())
```

**验证点**:
- [ ] 所有请求都成功
- [ ] 响应时间 < 1 秒

---

### TC-PERF-002: 数据库查询性能

**测试方法**:
```bash
# 创建 1000 条内容记录
for i in {1..1000}; do
  curl -X POST http://localhost:8000/api/contents \
    -H "Authorization: Bearer {{token}}" \
    -d '{"title": "测试'$i'", "content": "内容"}'
done

# 查询所有内容
time curl http://localhost:8000/api/contents?limit=1000
```

**验证点**:
- [ ] 查询时间 < 2 秒
- [ ] 返回 1000 条记录

---

## 5. 安全测试

### TC-SEC-001: Token 过期验证

```bash
# 使用过期Token访问API
GET /api/user/profile
Headers: {
  "Authorization": "Bearer expired_token"
}

# 预期结果
Status: 401 Unauthorized
Response: {"detail": "Invalid token"}

# 验证点
- [ ] 状态码为 401
- [ ] 无法访问受保护的资源
```

---

### TC-SEC-002: SQL 注入防护

```bash
# 尝试 SQL 注入
POST /api/auth/login
Body: {
  "email": "'; DROP TABLE users; --",
  "password": "any"
}

# 验证点
- [ ] 不会导致数据库错误
- [ ] 登录失败
```

---

### TC-SEC-003: XSS 防护

```bash
# 尝试 XSS
POST /api/contents
Body: {
  "title": "<script>alert('XSS')</script>",
  "content": "内容"
}

# 验证点
- [ ] 内容正确保存
- [ ] 查询时不会执行脚本
```

---

## 6. 测试报告模板

### 测试执行报告

```markdown
# MediaFlow 后端测试报告

**测试日期**: YYYY-MM-DD
**测试人员**: [姓名]
**测试环境**: 开发/测试/生产

---

## 测试概述

| 模块 | 总用例 | 通过 | 失败 | 通过率 |
|------|--------|:----:|:----:|:------:|
| Auth | 14 | 14 | 0 | 100% |
| Users | 3 | 3 | 0 | 100% |
| Lobsters | 3 | 3 | 0 | 100% |
| Chat | 3 | 3 | 0 | 100% |
| Contents | 5 | 5 | 0 | 100% |
| Publish | 3 | 3 | 0 | 100% |
| Config | 3 | 3 | 0 | 100% |
| **总计** | **34** | **34** | **0** | **100%** |

---

## 失败用例

| 用例ID | 模块 | 失败原因 | 严重程度 | 状态 |
|--------|------|----------|----------|------|
| - | - | - | - | - |

---

## 性能测试结果

| 测试项 | 目标值 | 实际值 | 状态 |
|--------|--------|--------|------|
| 并发请求（100个） | < 1s | 0.8s | ✅ |
| 数据库查询（1000条） | < 2s | 1.5s | ✅ |

---

## 安全测试结果

| 测试项 | 状态 | 备注 |
|--------|------|------|
| Token 过期验证 | ✅ | 正确拒绝过期Token |
| SQL 注入防护 | ✅ | 成功防护 |
| XSS 防护 | ✅ | 成功防护 |

---

## 结论

**测试结论**: 通过 / 失败

**建议**:
- [ ] 通过，可以上线
- [ ] 部分失败，需要修复 [列出问题]
- [ ] 严重失败，不可上线

---

**测试人员签名**: _____________
**测试日期**: _____________
```

---

## 🎯 快速测试脚本

### 自动化测试脚本示例

```python
# test_backend.py
import httpx
import pytest

BASE_URL = "http://localhost:8000"
TOKEN = None

def test_register():
    """测试注册"""
    global TOKEN
    response = httpx.post(f"{BASE_URL}/api/auth/register", json={
        "email": "test@example.com",
        "password": "Test123456"
    })
    assert response.status_code == 201
    TOKEN = response.json()["access_token"]

def test_login():
    """测试登录"""
    response = httpx.post(f"{BASE_URL}/api/auth/login", json={
        "email": "test@example.com",
        "password": "Test123456"
    })
    assert response.status_code == 200

def test_get_profile():
    """测试获取用户资料"""
    global TOKEN
    response = httpx.get(
        f"{BASE_URL}/api/user/profile",
        headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200

if __name__ == "__main__":
    test_register()
    test_login()
    test_get_profile()
    print("所有测试通过！✅")
```

---

**文档结束**

**最后更新**: 2026-03-19
