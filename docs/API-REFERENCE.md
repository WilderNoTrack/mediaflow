# MediaFlow API 接口文档

**版本**: v1.0.0
**后端框架**: FastAPI
**数据库**: SQLite / PostgreSQL
**认证方式**: Bearer Token (JWT)

---

## 📋 目录

1. [Auth 模块 (认证)](#1-auth-模块-认证)
2. [Users 模块 (用户管理)](#2-users-模块-用户管理)
3. [Lobsters 模块 (AI员工管理)](#3-lobsters-模块-ai员工管理)
4. [Chat 模块 (对话系统)](#4-chat-模块-对话系统)
5. [Contents 模块 (内容管理)](#5-contents-模块-内容管理)
6. [Publish 模块 (发布系统)](#6-publish-模块-发布系统)
7. [Config 模块 (配置管理)](#7-config-模块-配置管理)

---

## 1. Auth 模块 (认证)

**路径前缀**: `/api/auth`
**负责人**: Person A
**文件**: `backend/routers/auth.py`

### 1.1 用户注册

```
POST /api/auth/register
```

**请求参数**:
```json
{
  "phone": "13800138000",        // 可选，手机号
  "email": "user@example.com",   // 可选，邮箱
  "password": "password123",     // 必填，密码
  "nickname": "张老板",         // 可选，昵称
  "code": "123456"               // 必填（使用邮箱注册时），邮箱验证码
}
```

**响应成功** (201 Created):
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "phone": "13800138000",
    "email": "user@example.com",
    "nickname": "张老板"
  }
}
```

**响应失败** (400 Bad Request):
```json
{
  "detail": "Phone or email required"
}
```

**响应失败** (400 Bad Request):
```json
{
  "detail": "Verification code is required for email registration"
}
```

**响应失败** (400 Bad Request):
```json
{
  "detail": "User already exists"
}
```

**说明**:
- 注册成功后自动创建 7 天试用期订阅
- 自动创建默认 AI 员工"阿龙"
- 返回 JWT Token，30 天有效期

---

### 1.2 用户登录

```
POST /api/auth/login
```

**请求参数**:
```json
{
  "phone": "13800138000",        // 可选，手机号
  "email": "user@example.com",   // 可选，邮箱
  "password": "password123"      // 必填，密码
}
```

**响应成功** (200 OK):
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "phone": "13800138000",
    "email": "user@example.com",
    "nickname": "张老板"
  }
}
```

**响应失败** (401 Unauthorized):
```json
{
  "detail": "Invalid credentials"
}
```

---

### 1.3 发送验证码

```
POST /api/auth/send-code
```

**请求参数**:
```json
{
  "email": "user@example.com",   // 必填，邮箱地址
  "purpose": "register"          // 必填，用途：register（注册）或 reset_password（重置密码）
}
```

**响应成功** (200 OK):
```json
{
  "message": "Verification code sent successfully",
  "expires_in": 300              // 验证码有效期（秒）
}
```

**响应失败** (400 Bad Request):
```json
{
  "detail": "Email already registered"
}
```

**响应失败** (429 Too Many Requests):
```json
{
  "detail": "Please wait 1 seconds before requesting another code"
}
```

**响应失败** (500 Internal Server Error):
```json
{
  "detail": "Failed to send verification email"
}
```

**说明**:
- 验证码有效期 5 分钟
- 频率限制：同一邮箱 1 秒内只能发送一次
- 开发模式下验证码会打印到控制台

---

### 1.4 重置密码

```
POST /api/auth/reset-password
```

**请求参数**:
```json
{
  "email": "user@example.com",   // 必填，邮箱地址
  "code": "123456",              // 必填，验证码
  "new_password": "newpass123"    // 必填，新密码
}
```

**响应成功** (200 OK):
```json
{
  "message": "Password reset successfully"
}
```

**响应失败** (400 Bad Request):
```json
{
  "detail": "Invalid or expired verification code"
}
```

**响应失败** (404 Not Found):
```json
{
  "detail": "User not found"
}
```

---

## 2. Users 模块 (用户管理)

**路径前缀**: `/api/user`
**负责人**: Person A
**文件**: `backend/routers/users.py`

### 2.1 获取用户资料

```
GET /api/user/profile
```

**认证**: Bearer Token (必填)

**响应成功** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "phone": "13800138000",
  "email": "user@example.com",
  "nickname": "张老板",
  "created_at": "2026-03-19T10:00:00.000000",
  "subscription": {
    "plan": "basic",
    "status": "trial",
    "trial_end": "2026-03-26T10:00:00.000000",
    "expires_at": null
  },
  "lobster": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "阿龙",
    "domain": "general",
    "status": "running"
  },
  "xiaohongshu_account": {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "username": "user_xhs",
    "status": "active"
  }
}
```

**响应失败** (401 Unauthorized):
```json
{
  "detail": "Not authenticated"
}
```

---

## 3. Lobsters 模块 (AI员工管理)

**路径前缀**: `/api/lobsters`
**负责人**: Person A
**文件**: `backend/routers/lobsters.py`

### 3.1 创建/更新 AI 员工

```
POST /api/lobsters/create-or-update
```

**认证**: Bearer Token (必填)

**请求参数**:
```json
{
  "name": "阿龙",                // 可选，AI员工名称
  "domain": "hiphop",            // 可选，内容领域
  "status": "running"            // 可选，状态：running/paused/error
}
```

**响应成功** (200 OK):
```json
{
  "message": "Lobster created/updated successfully",
  "lobster": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "阿龙",
    "domain": "hiphop",
    "status": "running"
  }
}
```

---

### 3.2 获取 AI 员工详情

```
GET /api/lobsters/me
```

**认证**: Bearer Token (必填)

**响应成功** (200 OK):
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "阿龙",
  "domain": "hiphop",
  "status": "running",
  "created_at": "2026-03-19T10:00:00.000000",
  "preferences": {
    "content_source": {"domain": "hiphop"},
    "image_source": "mixed",
    "publish_frequency": "daily",
    "publish_time": ["18:00", "20:00"],
    "content_style": "轻松搞笑",
    "tags": ["热门", "新歌发布"]
  }
}
```

---

## 4. Chat 模块 (对话系统)

**路径前缀**: `/api/chat`
**负责人**: Person B
**文件**: `backend/routers/chat.py`

### 4.1 对话式配置

```
POST /api/chat/config
```

**认证**: Bearer Token (必填)

**请求参数**:
```json
{
  "message": "我想做嘻哈资讯账号，每天晚上发布"  // 必填，用户消息
}
```

**响应成功** (200 OK):
```json
{
  "message": "好的老板！嘻哈资讯很棒🎵 请问您想覆盖哪些内容？比如新歌发布、艺人动态、还是比赛资讯？",
  "extracted_config": {
    "domain": "hiphop",
    "publish_frequency": "daily",
    "publish_time": ["18:00", "20:00"]
  },
  "saved": true
}
```

**说明**:
- 使用 Kimi AI 提取用户配置偏好
- 自动保存对话历史
- 自动更新用户偏好
- AI 响应基于提取的配置生成

---

### 4.2 保存对话历史

```
POST /api/chat/history
```

**认证**: Bearer Token (必填)

**请求参数**:
```json
{
  "message": "用户发的消息",      // 必填
  "role": "user",               // 可选，角色：user 或 assistant
  "intent": "hiphop",           // 可选，识别的意图
  "extracted_config": {...}     // 可选，提取的配置
}
```

**响应成功** (200 OK):
```json
{
  "message": "Conversation saved",
  "id": "880e8400-e29b-41d4-a716-446655440003"
}
```

---

### 4.3 获取对话历史

```
GET /api/chat/history?limit=50
```

**认证**: Bearer Token (必填)

**查询参数**:
- `limit`: 可选，返回条数，默认 50

**响应成功** (200 OK):
```json
{
  "conversations": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "role": "user",
      "message": "我想做嘻哈资讯账号",
      "intent": "hiphop",
      "extracted_config": {
        "domain": "hiphop"
      },
      "created_at": "2026-03-19T10:00:00.000000"
    },
    {
      "id": "990e8400-e29b-41d4-a716-446655440004",
      "role": "assistant",
      "message": "好的老板！嘻哈资讯很棒🎵",
      "intent": "hiphop",
      "extracted_config": {
        "domain": "hiphop"
      },
      "created_at": "2026-03-19T10:00:01.000000"
    }
  ]
}
```

---

## 5. Contents 模块 (内容管理)

**路径前缀**: `/api/contents`
**负责人**: Person B
**文件**: `backend/routers/contents.py`

### 5.1 创建内容

```
POST /api/contents
```

**认证**: Bearer Token (必填)

**请求参数**:
```json
{
  "title": "嘻哈日报 - 今日新歌速递",     // 必填
  "content": "今天又有一大波新歌上线...",  // 必填
  "images": ["image1.jpg", "image2.jpg"],  // 可选，图片列表
  "tags": ["嘻哈", "新歌发布"],            // 可选，标签
  "scheduled_at": "2026-03-19T18:00:00"   // 可选，计划发布时间
}
```

**响应成功** (201 Created):
```json
{
  "message": "Content created successfully",
  "content": {
    "id": "aa0e8400-e29b-41d4-a716-446655440005",
    "title": "嘻哈日报 - 今日新歌速递",
    "content": "今天又有一大波新歌上线...",
    "status": "draft",
    "created_at": "2026-03-19T10:00:00.000000"
  }
}
```

---

### 5.2 获取内容列表

```
GET /api/contents?status=published&limit=50
```

**认证**: Bearer Token (必填)

**查询参数**:
- `status`: 可选，状态过滤：draft/pending/published/failed
- `limit`: 可选，返回条数，默认 50

**响应成功** (200 OK):
```json
{
  "contents": [
    {
      "id": "aa0e8400-e29b-41d4-a716-446655440005",
      "title": "嘻哈日报 - 今日新歌速递",
      "content": "今天又有一大波新歌上线...",
      "images": ["image1.jpg", "image2.jpg"],
      "tags": ["嘻哈", "新歌发布"],
      "status": "published",
      "published_at": "2026-03-19T18:00:00.000000",
      "created_at": "2026-03-19T10:00:00.000000"
    }
  ]
}
```

---

### 5.3 更新内容

```
PUT /api/contents/{content_id}
```

**认证**: Bearer Token (必填)

**路径参数**:
- `content_id`: 必填，内容 ID

**请求参数**:
```json
{
  "title": "更新后的标题",         // 可选
  "content": "更新后的内容",       // 可选
  "images": ["new_image.jpg"],     // 可选
  "tags": ["嘻哈", "热点"],        // 可选
  "status": "pending",             // 可选
  "scheduled_at": "2026-03-20T18:00:00"  // 可选
}
```

**响应成功** (200 OK):
```json
{
  "message": "Content updated successfully"
}
```

---

### 5.4 删除内容

```
DELETE /api/contents/{content_id}
```

**认证**: Bearer Token (必填)

**路径参数**:
- `content_id`: 必填，内容 ID

**响应成功** (200 OK):
```json
{
  "message": "Content deleted successfully"
}
```

---

## 6. Publish 模块 (发布系统)

**路径前缀**: `/api/publish`
**负责人**: Person B
**文件**: `backend/routers/publish.py`

### 6.1 发布到小红书

```
POST /api/publish
```

**认证**: Bearer Token (必填)

**请求参数**:
```json
{
  "title": "嘻哈日报 - 今日新歌速递",     // 必填
  "content": "今天又有一大波新歌上线...",  // 必填
  "images": ["image1.jpg", "image2.jpg"]   // 可选，图片列表
}
```

**响应成功** (200 OK):
```json
{
  "status": "success",
  "note_id": "1234567890abcdef",          // 小红书笔记 ID
  "content_id": "aa0e8400-e29b-41d4-a716-446655440005"
}
```

**响应失败** (400 Bad Request):
```json
{
  "detail": "No Xiaohongshu account bound"
}
```

**响应失败** (503 Service Unavailable):
```json
{
  "detail": "MCP service unavailable"
}
```

**说明**:
- 调用小红书 MCP API 发布
- 自动创建发布日志
- 需要用户先绑定小红书账号

---

### 6.2 获取发布日志

```
GET /api/publish/logs?limit=50
```

**认证**: Bearer Token (必填)

**查询参数**:
- `limit`: 可选，返回条数，默认 50

**响应成功** (200 OK):
```json
{
  "logs": [
    {
      "id": "bb0e8400-e29b-41d4-a716-446655440006",
      "content_id": "aa0e8400-e29b-41d4-a716-446655440005",
      "status": "success",
      "xiaohongshu_note_id": "1234567890abcdef",
      "error_message": null,
      "created_at": "2026-03-19T18:00:00.000000"
    }
  ]
}
```

---

## 7. Config 模块 (配置管理)

**路径前缀**: `/api/config`
**负责人**: Person A
**文件**: `backend/routers/config.py`

### 7.1 获取用户配置

```
GET /api/config
```

**认证**: Bearer Token (必填)

**响应成功** (200 OK):
```json
{
  "configs": {
    "domain": "hiphop",
    "content_style": "轻松搞笑",
    "publish_frequency": "daily",
    "publish_time": ["18:00", "20:00"],
    "image_source": "mixed",
    "tags": ["热门", "新歌发布"]
  }
}
```

---

### 7.2 保存用户配置

**格式 1: 保存单个配置**
```
POST /api/config
```

**请求参数**:
```json
{
  "config_key": "domain",    // 必填，配置键
  "config_value": "hiphop"   // 必填，配置值
}
```

**响应成功** (200 OK):
```json
{
  "message": "Config saved successfully",
  "config_key": "domain"
}
```

---

**格式 2: 批量保存配置**
```
POST /api/config
```

**请求参数**:
```json
{
  "domain": "hiphop",
  "content_style": "轻松搞笑",
  "publish_frequency": "daily",
  "publish_time": ["18:00", "20:00"],
  "image_source": "mixed",
  "tags": ["热门", "新歌发布"]
}
```

**响应成功** (200 OK):
```json
{
  "message": "Config saved successfully",
  "saved_keys": ["domain", "content_style", "publish_frequency", "publish_time", "image_source", "tags"]
}
```

---

## 8. 其他端点

### 8.1 健康检查

```
GET /health
```

**响应成功** (200 OK):
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### 8.2 绑定小红书账号

```
POST /api/xiaohongshu/bind
```

**认证**: Bearer Token (必填)

**请求参数**:
```json
{
  "username": "user_xhs",        // 必填，小红书用户名
  "cookies": "cookie_string_here"  // 必填，登录 cookies
}
```

**响应成功** (200 OK):
```json
{
  "message": "Xiaohongshu account bound successfully"
}
```

---

### 8.3 学习用户偏好

```
POST /api/user/preferences/learn
```

**认证**: Bearer Token (必填)

**响应成功** (200 OK):
```json
{
  "message": "Preferences learned successfully",
  "learned": true,
  "preferences": {
    "domain": "hiphop",
    "content_style": "轻松搞笑",
    "publish_frequency": "daily",
    "image_source": "mixed",
    "tags": ["热门", "新歌发布"]
  },
  "conversations_analyzed": 20
}
```

**说明**:
- 分析最近的对话历史
- 提取最常见的内容领域、风格、发布频率等
- 自动更新用户偏好

---

## 🔒 认证说明

### Token 获取

登录或注册成功后会返回 `access_token`，该 Token 有效期为 30 天。

### Token 使用

所有需要认证的接口都需要在请求头中携带 Token：

```
Authorization: Bearer {access_token}
```

示例：
```http
GET /api/user/profile
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

### Token 过期

Token 过期后会返回 401 错误，需要重新登录获取新 Token。

---

## 📝 错误码说明

| HTTP 状态码 | 说明 |
|-------------|------|
| 200 OK | 请求成功 |
| 201 Created | 资源创建成功 |
| 400 Bad Request | 请求参数错误 |
| 401 Unauthorized | 未认证或 Token 无效 |
| 403 Forbidden | 无权限访问 |
| 404 Not Found | 资源不存在 |
| 429 Too Many Requests | 请求频率超限 |
| 500 Internal Server Error | 服务器内部错误 |
| 503 Service Unavailable | 服务不可用（如 MCP 服务） |

---

## 📚 快速参考

### 常用端点

| 功能 | 方法 | 路径 |
|------|------|------|
| 注册 | POST | `/api/auth/register` |
| 登录 | POST | `/api/auth/login` |
| 发送验证码 | POST | `/api/auth/send-code` |
| 获取用户信息 | GET | `/api/user/profile` |
| 绑定小红书 | POST | `/api/xiaohongshu/bind` |
| 对话配置 | POST | `/api/chat/config` |
| 获取对话历史 | GET | `/api/chat/history` |
| 发布内容 | POST | `/api/publish` |
| 获取内容列表 | GET | `/api/contents` |

---

**文档结束**

**最后更新**: 2026-03-19
