# 校园信息智能推荐系统

## 启动

后端（FastAPI）：

```powershell
uv sync
# 首次使用 MySQL：复制 .env.example 为 .env，填写 MYSQL_PASSWORD
uv run python scripts/init_mysql.py
uv run uvicorn app.main:app --reload
```

前端（Vue 3 + Vite）：

```powershell
cd frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5173。首次访问必须注册，登录后按提示选择至少 3 个兴趣模块。

## 数据库

默认未配置 MySQL 时使用项目目录的 SQLite 进行离线开发；配置 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DB` 后使用本地 MySQL 8。数据库表由 SQLAlchemy 自动创建。

## DeepSeek

DeepSeek 仅由后端代理调用：

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
$env:DEEPSEEK_MODEL="deepseek-chat"
uv run uvicorn app.main:app --reload
```

未配置 Key 时，RAG 接口返回本地检索结果，不会暴露密钥或阻塞系统使用。

## 导入校园资料（含 PDF）

支持 JSON、NDJSON、CSV 和 PDF；PDF 会按页切分写入 `contents`，自动生成
`content_hash`、来源字段并按 `source_id`/来源链接/内容哈希去重，可重复执行：

```powershell
uv run python scripts/import_campus_data.py "data/新疆工程学院公开校内信息汇总.pdf"
```

RAG 使用 TF-IDF 字符 n-gram 检索最多 5 条资料，`RAG_MIN_SCORE`（默认 `0.02`）
用于拒答低相关问题，返回结果包含来源链接、部门和相似度。

Windows 上若安装了 Poppler，将优先使用 `pdftotext` 读取本 PDF 的中文字体映射；
未安装时回退到 `pypdf`。如需把 PDF 中的每条新闻（而非每页）拆成独立记录，
先运行 `data/parse_pdf.py`，再用 `scripts/build_campus_dataset.py` 合并详情页数据后导入。

## 主要流程

1. 注册用户名、密码、角色、学院、年级。
2. 登录后进入兴趣引导页，选择 3～8 个模块。
3. 推荐服务按角色、学院、年级、兴趣和内容标签过滤排序。
4. 大一优先获得入学/校园生活信息，大四优先获得就业/实习信息。
5. 校园问答检索相关资料，可选用 DeepSeek 生成有来源的回答。
