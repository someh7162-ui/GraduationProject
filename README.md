# 新疆工程学院 Campus AI 校园智能信息服务系统

面向新疆工程学院的校园智能信息服务系统：统一学院专业身份、可解释推荐、带来源的校园问答、学业档案、班级排名与奖学金资格初评。

完整改造清单、权限说明、安全设计、实验结果与演示步骤见 [系统优化总报告与验收指南](docs/系统优化总报告与验收指南.md)。

## 启动

```powershell
uv sync --extra dev
uv run python scripts/init_local_env.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 http://127.0.0.1:5173。默认使用 SQLite；已有 .env 中的 MySQL/DATABASE_URL 配置继续生效。JWT_SECRET 必须至少 32 字符，初始化脚本会生成本地随机密钥且不输出其内容。不要提交 .env。

公开注册仅支持学生，学院与专业从后端目录选择。首次登录选择 3–8 个兴趣，完成后进入推荐首页。

## 管理员与班级授权

首次先注册账号，由本地部署人员执行：

```powershell
uv run python scripts/set_academic_admin.py 用户名
```

重新登录后通过“账号与数据管理”登记班级、创建工作人员、分配学生班级及辅导员负责范围。学院管理员仅访问本院，辅导员仅访问负责班级，学生仅操作个人档案。政策发布由系统管理员负责。

## 功能与资料导入

- 推荐：行为权重、衰减、负反馈、真实 Top 10 兴趣匹配率与评分解释。
- 校园问答：TF-IDF/关键词融合、本地摘录、索引缓存、拒答与来源复查；不调用外部模型。
- 学业：成绩导入、人工确认、版本化政策、资格初评、OCR 辅助班级排名。
- 教务助手：可选 DeepSeek；无 Key 时保留本地规则流程，模型提议仍需验证。

```powershell
uv run python scripts/import_campus_data.py data/xju_enriched.ndjson
```

支持 JSON、NDJSON、CSV、文字型 PDF。相同 source_id 支持仅更新来源/权限字段。官网类型不等于已核验，last_verified_at 需来自实际人工核验。详细规则见 [第四阶段说明](docs/第四阶段_RAG权限缓存与来源验证.md)。

MySQL 配置、模型配置及明确的 CORS_ORIGINS 示例见 .env.example。旧表在启动时自动补齐新增字段；升级前请按部署流程备份实际数据。缓存为单进程内缓存。

## 验证

```powershell
uv run python -m pytest -q -p no:cacheprovider
uv run python scripts/evaluate_recommendations.py data/recommendation_eval_sample.json --output docs/recommendation_eval_sample_results.json
cd frontend
npm run build
```

本轮本地结果：42 项测试通过，前端构建通过。GitHub Actions 配置会运行相同检查。推荐评估样例为合成数据，仅用于验证流程；真实效果与论文结论需要独立标注数据。算法细节见 [第三阶段说明](docs/第三阶段_推荐算法优化与验证.md)。

历史文档和 Repaire1Demo 参考资料保留作过程记录；当前状态以总报告及代码为准。
