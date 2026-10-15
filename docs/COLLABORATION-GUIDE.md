# MediaFlow 协作开发指南

**项目**: MediaFlow 后端模块化重构
**协作方式**: VS Code Live Share + Git
**参与者**: 2 人（Person A + Person B）

---

## 📋 目录

1. [环境准备](#1-环境准备)
2. [VS Code Live Share 协作](#2-vs-code-live-share-协作)
3. [Git 工作流](#3-git-工作流)
4. [模块开发流程](#4-模块开发流程)
5. [代码审查流程](#5-代码审查流程)
6. [常见问题](#6-常见问题)

---

## 1. 环境准备

### 1.1 系统要求

- **操作系统**: Windows / macOS / Linux
- **VS Code**: 最新版本（1.80+）
- **Python**: 3.10+
- **Git**: 最新版本

### 1.2 安装 Live Share 插件

**步骤**:
1. 打开 VS Code
2. 点击左侧 **Extensions** (Ctrl+Shift+X)
3. 搜索 **"Live Share"**
4. 选择官方插件（发布者：Microsoft）
5. 点击 **Install**

**截图说明**:
```
┌─────────────────────────────────────────┐
│ EXTENSIONS                              │
│                                         │
│ 🔍 Search Extensions                    │
│                                         │
│ ⭐ Live Share         [Microsoft]       │
│    Visual Studio Live Share              │
│    [Install]                             │
└─────────────────────────────────────────┘
```

### 1.3 登录账号

**双方都需要做**:

1. 按 `Ctrl+Shift+P` 打开命令面板
2. 输入 **"Live Share: Sign In"**
3. 选择账号类型：
   - **GitHub Account**（推荐）
   - **Microsoft Account**

**为什么需要登录？**
- Live Share 使用云端中继服务器
- 需要 GitHub/Microsoft 账号进行身份验证
- 免费使用，无需付费

---

## 2. VS Code Live Share 协作

### 2.1 发起协作会话（一方发起）

**发起人（你）操作**:

1. 打开 MediaFlow 项目根目录
2. 按 `Ctrl+Shift+P`
3. 输入 **"Live Share: Start Collaboration Session"**
4. VS Code 会生成一个**协作链接**，并自动复制到剪贴板
5. 发送链接给朋友（微信/QQ/邮件等）

**示例链接**:
```
https://insiders.liveshare.vsengsaas.visualstudio.com/join?session_id=abc123...
```

**你看到的界面**:
```
┌─────────────────────────────────────────┐
│ Live Share - Collaboration Session       │
│                                         │
│ ✅ Session started                     │
│                                         │
🔗 https://insiders.liveshare...         │
│                                         │
│ Share this link with your collaborator │
│                                         │
│ [Copy Link]  [End Session]            │
└─────────────────────────────────────────┘
```

### 2.2 加入协作会话（另一方加入）

**加入人（朋友）操作**:

1. 打开 VS Code（**不一定要打开项目**）
2. 接收并复制协作链接
3. 按 `Ctrl+Shift+P`
4. 输入 **"Live Share: Join Collaboration Session"**
5. 粘贴链接，按 Enter
6. 等待几秒，连接成功！

**连接成功后，你会看到**:
- 发起人的项目自动打开
- 右下角显示连接状态：**"Connected to [发起人名字]"**
- 双方可以看到对方的光标和操作

### 2.3 实时协作功能

#### ✅ 功能 1: 实时代码同步

- 双方编辑**同一个文件**时，会看到**彩色光标**显示对方的位置
- 修改会**实时同步**，毫秒级延迟
- 支持**多文件同时编辑**

**光标颜色**:
- 发起人：🟡 黄色
- 加入人：🔵 蓝色

#### ✅ 功能 2: 共享终端

**发起人操作**:
1. 按 `Ctrl+Shift+P`
2. 输入 **"Live Share: Share Terminal"**
3. 选择一个终端分享

**效果**:
- 双方都能看到终端输出
- 双方都能在终端输入命令
- 适合一起调试、运行测试

#### ✅ 功能 3: 语音通话（可选）

1. 连接成功后，右下角会显示**麦克风图标**
2. 点击麦克风图标即可开启语音通话
3. 无需额外软件，直接在 VS Code 内通话

#### ✅ 功能 4: 共享服务器

**适用场景**:
- 前端开发服务器（`npm run dev`）
- 后端 API 服务器（`uvicorn main:app --reload`）

**操作**:
1. 在共享终端中启动服务器
2. 双方都能访问 `http://localhost:5173`
3. 一方修改代码，双方浏览器自动刷新

### 2.4 结束协作会话

**发起人操作**:
1. 右下角点击 **Live Share 状态图标**
2. 选择 **"End Session"**
3. 确认结束

**加入人会自动断开连接**。

---

## 3. Git 工作流

### 3.1 分支策略

```
main                              # 生产分支（稳定代码）
  ├── dev                         # 开发分支（日常开发）
       ├── refactor/auth-router    # Person A 分支
       ├── refactor/chat-router     # Person B 分支
       └── refactor/publish-router # Person B 分支
```

### 3.2 初始化分支（第一天）

**双方操作**:

```bash
# 1. 确保在 main 分支
git checkout main
git pull origin main

# 2. 创建开发分支
git checkout -b refactor/backend-modular

# 3. 推送到远程
git push -u origin refactor/backend-modular
```

**双方创建个人子分支**:

**你（Person A）**:
```bash
git checkout -b refactor/auth-router
git push -u origin refactor/auth-router
```

**朋友（Person B）**:
```bash
git checkout -b refactor/chat-router
git push -u origin refactor/chat-router
```

### 3.3 日常开发流程

#### 你的流程（Person A）

```bash
# 1. 拉取最新代码
git checkout refactor/auth-router
git pull origin refactor/auth-router

# 2. 创建功能分支（可选）
git checkout -b feature/auth-register

# 3. 开发...（使用 Live Share 实时协作）

# 4. 提交代码
git add .
git commit -m "feat(auth): implement register endpoint"

# 5. 推送到远程
git push -u origin feature/auth-register

# 6. 合并到主分支（可选）
git checkout refactor/auth-router
git merge feature/auth-register
git push origin refactor/auth-router
```

#### 朋友的流程（Person B）

```bash
# 1. 拉取最新代码
git checkout refactor/chat-router
git pull origin refactor/chat-router

# 2. 创建功能分支（可选）
git checkout -b feature/chat-config

# 3. 开发...（使用 Live Share 实时协作）

# 4. 提交代码
git add .
git commit -m "feat(chat): implement config endpoint"

# 5. 推送到远程
git push -u origin feature/chat-config

# 6. 合并到主分支（可选）
git checkout refactor/chat-router
git merge feature/chat-config
git push origin refactor/chat-router
```

### 3.4 处理代码冲突

**场景**：你们修改了同一个文件（如 `main.py`）

```bash
# 1. 拉取远程代码
git pull origin refactor/auth-router

# 2. 如果有冲突，Git 会提示
Auto-merging backend/main.py
CONFLICT (content): Merge conflict in backend/main.py
Automatic merge failed; fix conflicts and then commit the result.

# 3. 手动解决冲突（在 VS Code 中解决更方便）
#    - 打开冲突文件
#    - 找到冲突标记 <<<<<<< HEAD
#    - 选择保留谁的代码或合并
#    - 删除冲突标记

# 4. 标记冲突已解决
git add backend/main.py

# 5. 提交合并
git commit -m "resolve: merge conflict in main.py"

# 6. 推送
git push origin refactor/auth-router
```

### 3.5 代码审查（Code Review）

**流程**:

1. **Person A 完成** `auth.py` 模块
2. **创建 Pull Request (PR)**
3. **Person B 审查** PR 代码
4. **在 Live Share 中**一起讨论问题
5. **Person A 修改**问题
6. **Person B 批准** PR
7. **合并到主分支**

**如何创建 PR**:
- 使用 GitHub 网页界面
- 或使用 GitHub CLI：`gh pr create`

---

## 4. 模块开发流程

### 4.1 模块开发清单

**每开发一个模块，都要完成以下步骤**:

- [ ] 1. 创建模块文件（如 `backend/routers/auth.py`）
- [ ] 2. 定义 Pydantic 模型（请求/响应）
- [ ] 3. 实现端点逻辑
- [ ] 4. 从 `main.py` 迁移代码
- [ ] 5. 添加错误处理
- [ ] 6. 本地测试（使用 Postman/curl）
- [ ] 7. 提交代码（Git）
- [ ] 8. 代码审查（对方 review）
- [ ] 9. 修复问题（如有）
- [ ] 10. 合并到主分支

### 4.2 你的开发流程（Person A）

#### Day 1: 开发 `auth.py`

```
1. 创建文件
   └── backend/routers/auth.py

2. 实现以下端点：
   ├─ POST /api/auth/register
   ├─ POST /api/auth/login
   ├─ POST /api/auth/send-code
   └─ POST /api/auth/reset-password

3. 测试每个端点：
   └─ 使用 Postman 或 curl

4. 提交代码：
   git add backend/routers/auth.py
   git commit -m "feat(auth): implement auth router"
   git push origin refactor/auth-router

5. 朋友审查代码
```

#### Day 2: 开发 `users.py`

```
1. 创建文件
   └── backend/routers/users.py

2. 实现以下端点：
   ├─ GET /api/user/profile
   └─ POST /api/user/preferences/learn

3. 测试每个端点

4. 提交代码
   git add backend/routers/users.py
   git commit -m "feat(users): implement users router"
   git push origin refactor/auth-router

5. 朋友审查代码
```

#### Day 3: 开发 `lobsters.py`

```
1. 创建文件
   └── backend/routers/lobsters.py

2. 实现以下端点：
   ├─ POST /api/lobsters/create-or-update
   └─ GET /api/lobsters/me

3. 测试每个端点

4. 提交代码
   git add backend/routers/lobsters.py
   git commit -m "feat(lobsters): implement lobsters router"
   git push origin refactor/auth-router

5. 朋友审查代码
```

### 4.3 朋友的开发流程（Person B）

#### Day 1: 开发 `chat.py`

```
1. 创建文件
   └── backend/routers/chat.py

2. 实现以下端点：
   ├─ POST /api/chat/config
   ├─ POST /api/chat/history
   └─ GET /api/chat/history

3. 测试每个端点：
   └─ 使用 Postman 或 curl

4. 提交代码：
   git add backend/routers/chat.py
   git commit -m "feat(chat): implement chat router"
   git push origin refactor/chat-router

5. 你审查代码
```

#### Day 2: 开发 `contents.py`

```
1. 创建文件
   └── backend/routers/contents.py

2. 实现以下端点：
   ├─ POST /api/contents
   ├─ GET /api/contents
   ├─ PUT /api/contents/{id}
   └─ DELETE /api/contents/{id}

3. 测试每个端点

4. 提交代码
   git add backend/routers/contents.py
   git commit -m "feat(contents): implement contents router"
   git push origin refactor/chat-router

5. 你审查代码
```

#### Day 3: 开发 `publish.py`

```
1. 创建文件
   └── backend/routers/publish.py

2. 实现以下端点：
   ├─ POST /api/publish
   └─ GET /api/publish/logs

3. 测试每个端点：
   └─ 注意：需要小红书 MCP 服务运行

4. 提交代码
   git add backend/routers/publish.py
   git commit -m "feat(publish): implement publish router"
   git push origin refactor/chat-router

5. 你审查代码
```

---

## 5. 代码审查流程

### 5.1 审查清单

**审查时，检查以下项目**:

- [ ] **代码规范**
  - 遵循 PEP 8 规范
  - 使用有意义的变量名
  - 函数名使用小写下划线

- [ ] **错误处理**
  - 所有端点都有错误处理
  - 返回适当的 HTTP 状态码
  - 错误消息清晰明了

- [ ] **安全性**
  - 敏感信息不泄露到日志
  - 密码不直接存储
  - 用户权限验证

- [ ] **性能**
  - 数据库查询优化
  - 避免N+1查询
  - 使用适当的数据结构

- [ ] **文档**
  - 函数有 docstring
  - 复杂逻辑有注释
  - API 参数有说明

### 5.2 使用 Live Share 进行审查

**流程**:

1. **发起审查**（你审查朋友的代码）
   - 在 Live Share 中打开朋友的代码文件
   - 使用注释功能（右键 → "添加注释"）
   - 标记有问题的地方

2. **实时讨论**
   - 一起逐行审查代码
   - 提出修改建议
   - 讨论实现方案

3. **跟踪修改**
   - 朋友修改代码时，你能实时看到
   - 修改完成后，再次审查

4. **批准**
   - 所有问题解决后，在 PR 中批准

### 5.3 审查沟通技巧

**好的审查方式**:
- ✅ "这里有个小问题，建议改成..."
- ✅ "我注意到这个查询可能有点慢，可以考虑..."
- ✅ "这个函数没有错误处理，如果...会怎么样？"

**避免的审查方式**:
- ❌ "这代码写得不好"
- ❌ "为什么要这样写？"
- ❌ "这逻辑有问题"

---

## 6. 常见问题

### Q1: Live Share 连接不上？

**解决方法**:
1. 检查网络连接
2. 确认双方都登录了 GitHub/Microsoft 账号
3. 尝试重新生成链接
4. 如果在中国大陆，可能需要 VPN（Live Share 服务器在海外）

### Q2: 看不到对方的光标？

**解决方法**:
1. 确认双方都打开**同一个文件**
2. 检查右下角连接状态
3. 尝试重新连接

### Q3: Git 提交时提示"上游分支未设置"？

**解决方法**:
```bash
# 设置上游分支
git push -u origin refactor/auth-router
```

### Q4: 如何知道朋友在做什么？

**解决方法**:
- 右下角看连接状态
- 看对方的光标位置
- 在 Live Share 中聊天（右下角聊天图标）

### Q5: 如何避免代码冲突？

**最佳实践**:
1. **频繁同步**：每隔 30 分钟 pull 一次
2. **分模块开发**'：不要同时修改同一个文件
3. **提前沟通**：开始前说清楚要修改哪些文件
4. **使用功能分支**：每个功能一个分支，减少冲突

### Q6: Live Share 支持多人协作吗？

**答案**: 支持！最多支持 **10 人**同时协作。

**操作**:
1. 发起人分享链接
2. 多个人可以同时加入
3. 所有人都能实时看到彼此的编辑

---

## 📚 快速参考

### Live Share 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Shift+P` | 命令面板 |
| `Ctrl+Shift+A` | 开始协作会话 |
| `Ctrl+Alt+J` | 加入协作会话 |
| `Ctrl+Alt+T` | 共享终端 |

### Git 常用命令

```bash
# 分支操作
git checkout -b feature-xxx    # 创建并切换分支
git branch                     # 查看分支
git merge feature-xxx          # 合并分支

# 提交操作
git add .                      # 添加所有更改
git commit -m "message"        # 提交
git push                       # 推送
git pull                       # 拉取

# 查看状态
git status                     # 查看状态
git log                        # 查看提交历史
git diff                       # 查看更改

# 解决冲突
git add conflict-file.py        # 标记冲突已解决
```

---

## 🎯 下一步

1. **今天**：设置 VS Code Live Share，测试连接
2. **明天**：创建 Git 分支，开始开发第一个模块
3. **未来 3-5 天**：完成所有模块，通过代码审查

---

**文档结束**

**最后更新**: 2026-03-19
