# Changelog

## [v2.1.0] - 2026-08-17

### 新增
- 资源限制可配置（`resources` 段）：`embedding_threads`（onnxruntime 线程）、`memory_max`（systemd MemoryMax Drop-in）、`embedding_batch`
- 部署脚本生成资源限制 Drop-in（`/etc/systemd/system/rag-service.service.d/resource.conf`）
- `deploy/update.sh`：生产增量更新（同步代码 + Drop-in，不动配置/数据）
- MCP server（`mcp/rag_search_mcp.py`）：DeepCode 等 harness 通过 MCP 工具调用检索
- SKILL 模板（`skills/llm-wiki-search-HTTP/SKILL.md`）：HTTP 方式 A 接入模板

### 修复
- `install.sh`/`update.sh` 在 pipefail + grep 无匹配时提前退出导致 Drop-in 未生成（`|| true` + if-fallback）

### 性能
- 生产内存峰值从 7.4G（接近 OOM）降至 < 500M（限制后实测 peak 472M）

## [v2.0.0] - 2026-08-15

### 新增
- 检索即服务（方式 A）定位：只含 embedding，无 LLM / API key 依赖
- 标准部署：`install.sh` 安装到 `/opt`，systemd 服务 + 专用低权限用户 `rag-service`
- 数据源分离：`datasources` 多源配置 + exclude 规则
- 自动更新：watchdog（防抖 3s）/ polling（5s）两种模式
- `/eval` 检索质量评测端点

### 修复
- 空语料 BM25 除零
- 局部增量 Path/str key 不匹配
- 全量重建死锁（Lock → RLock）

## [v1.0.0] - 2026-08-10

### 新增
- 中文 RAG 向量库全流程：Chroma + BGE（bge-small-zh-v1.5）+ BM25 混合检索（RRF 融合）
- 主题过滤（TOPIC_KEYWORDS）、懒加载、线程安全单例模型
- 文档解析：Markdown / docx / txt
