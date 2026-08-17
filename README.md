# rag-service

本地部署的 **RAG 检索服务**（检索即服务 / 方式 A）：只含 embedding 模型（无 LLM、无 API key），为任意 Agent（Hermes / DeepCode / Claude Code / 自研）提供知识库检索能力。回答由 Agent 自带 LLM 生成——"资料库 + 思考者"分离。

![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04-orange) ![Python](https://img.shields.io/badge/Python-3.12-blue) ![License](https://img.shields.io/badge/License-Non--Commercial-lightgrey)

## 特性

- **混合检索**：BGE 向量（Chroma）+ BM25 稀疏 + RRF 融合，中文检索命中率 88%
- **检索即服务（方式 A）**：HTTP API `/search`，只含 embedding，无 LLM 依赖
- **自动更新**：watchdog / polling 两种模式，文档变更自动增量入库
- **资源可控**：`resources.embedding_threads` + systemd `MemoryMax` 双层限制，内存峰值 < 500M
- **标准部署**：`install.sh` 一键装到 `/opt`，systemd 服务 + 专用低权限用户
- **Agent 接入**：SKILL（技能文件）与 MCP（工具协议）两种通用模式

## 架构

```
┌──────────┐   /search   ┌─────────────┐
│  Agent   │ ──────────► │ rag-service │
│ (LLM)    │ ◄────────── │ (embedding) │
└──────────┘   hits片段  └──────┬──────┘
                                │
                    Chroma(BGE) + BM25 + RRF
```

## 快速开始（开发）

```bash
git clone https://github.com/cxl-nkb/rag-service.git
cd rag-service
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 配置数据源后启动
python scripts/build_once.py      # 首次构建索引
python scripts/start.sh           # 启动服务（127.0.0.1:8931）

# 检索测试
curl -X POST http://127.0.0.1:8931/search \
  -H "Content-Type: application/json" \
  -d '{"query":"P8 元规则","top_k":3}'
```

## 标准部署（生产 /opt）

```bash
sudo ./deploy/install.sh          # 一键安装（systemd + 专用用户 + 资源限制）
sudo systemctl start rag-service
curl http://127.0.0.1:8931/health
# 增量更新：sudo ./deploy/update.sh
```

详见 [`docs`](docs) 与 [部署章节](#部署文档)。

## API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/search` | POST | 检索：`{"query": "...", "top_k": 3}` → `{"hits": [...]}` |
| `/ingest` | POST | 手动触发入库（全量/增量） |
| `/health` | GET | 健康检查（返回 chunks 数） |
| `/stats` | GET | 数据源/文档统计 |
| `/eval` | POST | 检索质量评测 |

## Agent 接入

- **SKILL 模式**：`skills/llm-wiki-search-HTTP/SKILL.md`（复制到 `~/.hermes/skills/...` 即用）
- **MCP 模式**：`mcp/rag_search_mcp.py`（注册到 DeepCode / Claude Code 的 mcpServers）

完整指南见 [`RAG-Service接入指南-SKILL与MCP.md`](docs/RAG-Service接入指南-SKILL与MCP.md)。

## 测试

```bash
pytest tests/                     # 41 核心 + 12 可靠性（需服务在线）
```

## 许可

**非商用许可（Non-Commercial）**：本软件仅供个人学习与内部使用，禁止商业用途。详见 [LICENSE](LICENSE)。
