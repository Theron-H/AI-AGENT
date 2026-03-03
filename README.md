# AI Data Assistant

一个最小可运行的 AI 智能体助手，支持：

- 数据库存储（SQLite）
- 数据分析（聚合、趋势、Top N）
- AI 问答入口（自然语言转分析）

## 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 启动

```bash
uvicorn app.main:app --reload
```

默认服务地址：`http://127.0.0.1:8000`

## 3. API 快速测试

### 3.1 写入样例数据

```bash
curl -X POST "http://127.0.0.1:8000/events/batch" \
  -H "Content-Type: application/json" \
  -d '[
    {"source":"shop","category":"book","value":120.5,"occurred_at":"2026-03-01T10:00:00"},
    {"source":"shop","category":"book","value":98.0,"occurred_at":"2026-03-02T10:00:00"},
    {"source":"shop","category":"food","value":45.0,"occurred_at":"2026-03-02T12:00:00"},
    {"source":"shop","category":"food","value":72.0,"occurred_at":"2026-03-03T12:00:00"}
  ]'
```

### 3.2 聚合分析

```bash
curl "http://127.0.0.1:8000/analytics/aggregate?group_by=category&metric=value&agg=sum"
```

### 3.3 AI 问答

```bash
curl -X POST "http://127.0.0.1:8000/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我看一下每个类别的总金额","session_id":"demo"}'
```

### 3.4 导出分析报表

```bash
curl -o report.csv "http://127.0.0.1:8000/analytics/export?group_by=category&metric=value&agg=sum&format=csv"
```

### 3.5 图表生成（ECharts 配置）

```bash
curl "http://127.0.0.1:8000/analytics/chart?type=bar&agg=sum&metric=value"
```

### 3.6 图表图片（PNG/SVG）

```bash
curl -o chart.png "http://127.0.0.1:8000/analytics/chart/image?type=bar&format=png"
```

### 3.7 只读 SQL（AI 调用也支持）

```bash
curl -X POST "http://127.0.0.1:8000/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"sql: SELECT category, SUM(value) AS total FROM event_records GROUP BY category","session_id":"demo"}'
```

### 3.8 自然语言 -> SQL -> 执行（需 OPENAI_API_KEY）

```bash
curl -X POST "http://127.0.0.1:8000/agent/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"每个类别的总金额是多少？","session_id":"demo"}'
```

### 3.9 数据导入（CSV/Excel）

```bash
curl -X POST "http://127.0.0.1:8000/events/import?tenant_id=demo" \
  -F "file=@./data.csv"
```

### 3.10 数据清洗（异常值）

```bash
curl -X POST "http://127.0.0.1:8000/events/clean?tenant_id=demo&remove_outliers=true"
```

### 3.11 统计摘要 / 异常检测 / 时间窗口

```bash
curl "http://127.0.0.1:8000/analytics/summary?tenant_id=demo&window_days=30"
curl "http://127.0.0.1:8000/analytics/outliers?tenant_id=demo&window_days=30"
```

### 3.12 报表任务

```bash
curl -X POST "http://127.0.0.1:8000/reports/jobs" \
  -H "Content-Type: application/json" \
  -d '{"name":"daily_report","schedule":"daily","format":"csv","tenant_id":"demo"}'

curl -X POST "http://127.0.0.1:8000/reports/run"
```

### 3.13 采集模拟器

```bash
curl -X POST "http://127.0.0.1:8000/events/simulate?tenant_id=demo&days=7&per_day=20"
```

## 4. 环境变量

复制 `.env.example` 到 `.env`，按需配置：

- `DB_URL`: 数据库连接字符串，生产建议 `postgresql+psycopg://user:pass@host:5432/db`
- `OPENAI_API_KEY`: 可选。如果配置，会优先使用 OpenAI 做意图理解；未配置时用内置规则解析。
- `JWT_SECRET`: JWT 签名密钥
- `GM_USERNAME` / `GM_PASSWORD`: 固定 GM 账号（不可删除）
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` / `ALERT_EMAIL_TO`: 备份邮件告警

> 说明：多轮记忆基于 `session_id` 保存到数据库的 `chat_messages` 表。

## 6. 生产部署（Docker + Postgres）

```bash
docker compose up --build
```

默认服务：
- API: `http://localhost:8000`
- Postgres: `localhost:5432`

备份服务每小时执行一次 `pg_dump`，生成带 SHA256 的文件，并通过邮件告警。

## 7. 认证与权限

1) 登录获取 JWT：

```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"gm","password":"gm_password","tenant_id":"default"}'
```

2) GM 创建用户（需 `Authorization: Bearer <token>`）：

```bash
curl -X POST "http://127.0.0.1:8000/auth/users" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"analyst","password":"pwd","roles":["analyst"],"tenant_id":"default"}'
```

3) GM 创建租户 / 禁用租户：

```bash
curl -X POST "http://127.0.0.1:8000/tenants" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"tenant_a"}'

curl -X PATCH "http://127.0.0.1:8000/tenants/tenant_a" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

4) GM 重置密码：

```bash
curl -X POST "http://127.0.0.1:8000/auth/reset-password?username=analyst&new_password=newpwd" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 8. 监控

Prometheus 指标端点：

```
GET /metrics
```

## 9. 数据字典 / 模板 / 报表历史

```bash
curl -X POST "http://127.0.0.1:8000/dictionary?field_name=amount&field_type=float&description=demo" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl "http://127.0.0.1:8000/dictionary" -H "Authorization: Bearer YOUR_TOKEN"

curl -X POST "http://127.0.0.1:8000/analysis/templates?name=basic" \
  -H "Authorization: Bearer YOUR_TOKEN"

curl "http://127.0.0.1:8000/reports/history" -H "Authorization: Bearer YOUR_TOKEN"
```

## 9. 代码规范与安全检查（建议每次提交前执行）

```bash
pip install -r requirements-dev.txt
pre-commit install
pre-commit run --all-files
```

已内置：
- `ruff` 代码规范与自动修复
- `ruff-format` 统一格式
- `bandit` 安全扫描
- `mypy` 类型检查（按需扩展）

## 5. 项目结构

```
app/
  main.py        # FastAPI 入口
  db.py          # 数据库连接与会话
  models.py      # ORM 模型
  schemas.py     # 请求/响应模型
  analysis.py    # 分析逻辑
  agent.py       # AI 智能体（工具编排）
```
