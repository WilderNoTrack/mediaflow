# 🚀 媒力 MediaFlow 部署文档

## 快速开始

### 开发环境（SQLite）

```bash
# 1. 启动后端
cd lobster-cloud/backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# 2. 启动前端
cd mediaflow-figma
npm install
npm run dev
```

访问：
- 前端：http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档：http://localhost:8000/docs

---

## 生产环境部署（Docker）

### 前置要求

- Docker 20+
- Docker Compose 2.0+
- 域名（可选）

### 步骤 1: 配置环境变量

```bash
cd lobster-cloud
cp backend/.env.example .env

# 编辑 .env 文件
vim .env
```

**必须配置**:
```bash
DB_PASSWORD=你的数据库密码
JWT_SECRET_KEY=你的 JWT 密钥（至少 32 字符）
KIMI_API_KEY=你的 Kimi API Key（可选）
```

### 步骤 2: 启动服务

```bash
docker-compose up -d
```

### 步骤 3: 验证部署

```bash
# 查看日志
docker-compose logs -f

# 检查服务状态
docker-compose ps

# 测试 API
curl http://localhost/api/user/profile
```

访问：
- 前端：http://localhost
- 后端 API: http://localhost:8000

---

## 数据库迁移（SQLite → PostgreSQL）

### 1. 导出 SQLite 数据

```bash
cd lobster-cloud/backend
python3 << 'EOF'
import sqlite3
import json

conn = sqlite3.connect('mediaflow.db')
cursor = conn.cursor()

# 导出所有表
tables = ['users', 'subscriptions', 'xiaohongshu_accounts', 
          'lobsters', 'user_preferences', 'conversation_history',
          'contents', 'publish_logs', 'content_configs']

for table in tables:
    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()
    with open(f'{table}.json', 'w') as f:
        json.dump(rows, f)
        
conn.close()
print("数据导出完成")
EOF
```

### 2. 导入 PostgreSQL

```bash
# 启动 PostgreSQL
docker-compose up -d postgres

# 导入数据（需要编写导入脚本）
python3 migrate_to_postgres.py
```

---

## AI 模型集成（Kimi）

### 1. 获取 API Key

访问 https://platform.moonshot.cn/ 注册并获取 API Key

### 2. 配置环境变量

```bash
echo "KIMI_API_KEY=sk-xxx" >> .env
```

### 3. 修改后端代码

在 `main.py` 中的 `extract_config_from_message` 函数替换为 Kimi API 调用：

```python
import httpx

async def extract_config_with_ai(message: str) -> dict:
    response = await httpx.post(
        "https://api.moonshot.cn/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('KIMI_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "model": "moonshot-v1-8k",
            "messages": [
                {"role": "system", "content": "你是一个配置提取助手，从用户消息中提取小红书账号配置..."},
                {"role": "user", "content": message}
            ]
        }
    )
    return response.json()
```

---

## 支付集成（支付宝沙箱）

### 1. 注册支付宝开放平台

访问 https://open.alipay.com/ 创建应用

### 2. 配置沙箱环境

```bash
echo "ALIPAY_APP_ID=你的应用 ID" >> .env
echo "ALIPAY_PRIVATE_KEY=你的私钥" >> .env
echo "ALIPAY_PUBLIC_KEY=支付宝公钥" >> .env
```

### 3. 测试支付

访问沙箱环境：https://openapi-sandbox.dl.alipaydev.com/

---

## 监控与日志

### 查看日志

```bash
# 所有服务
docker-compose logs -f

# 单个服务
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
```

### 健康检查

```bash
# 后端健康
curl http://localhost:8000/health

# 数据库连接
docker-compose exec postgres pg_isready -U mediaflow
```

---

## 常见问题

### Q: 后端无法连接数据库
A: 确保 PostgreSQL 已启动且环境变量正确

### Q: 前端无法访问后端 API
A: 检查 CORS 配置或配置反向代理

### Q: MCP 发布失败
A: 确保 MCP Server 运行在 http://localhost:18060

---

## 备份与恢复

### 备份数据库

```bash
docker-compose exec postgres pg_dump -U mediaflow mediaflow > backup.sql
```

### 恢复数据库

```bash
docker-compose exec -T postgres psql -U mediaflow mediaflow < backup.sql
```

---

**部署完成！** 🎉
