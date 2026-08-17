# RAG-Service 接入指南：SKILL 与 MCP 两种通用模式（v3 完整版）

> 2026-08-17。目标：文档完整说明 **"请求 → harness → 调用 SKILL/MCP → RAG 检索 → 插入 prompt → LLM 回答"** 整体流程，给出每一步的实现代码。任何 harness（Hermes / DeepCode / Claude Code / Cursor / 自研）照此适配。
> rag-service 是检索服务（只含 embedding 模型），回答由 Agent 自带 LLM 生成——"资料库 + 思考者"分离（方式 A）。

---

## 0. 整体流程（先看懂全貌）

```
① 用户提问
   │
   ▼
② harness（Hermes / DeepCode）的 LLM 主模型
   │  判断："这个话题可能记录过" → 决定调用检索能力
   │  （触发依据：SKILL 的 description 或 MCP 工具描述）
   ▼
③ 调用检索（两种方式任选）
   ├─ SKILL：agent 读 SKILL.md 正文 → 执行里面的命令（curl /search）
   └─ MCP：agent 通过协议调 knowledge_search 工具（server 内部 curl /search）
   ▼
④ rag-service 检索
   │  query → embedding 向量化 → 混合检索（向量+BM25+RRF）→ 返回 top-k 片段（含来源）
   ▼
⑤ agent 拿到 hits → 插入自己的 prompt（片段作为上下文）
   ▼
⑥ agent 的 LLM 基于片段 + 用户问题重新推算 → 生成回答
   ▼
⑦ 回答展示给用户（引用来源）
```

**职责边界（每步谁负责）：**

| 步 | 谁 | 做什么 |
|---|---|---|
| ① ② | harness + LLM | 判断是否检索、决定调用 |
| ③ ④ | SKILL/MCP → rag-service | 执行检索，返回片段 |
| ⑤ ⑥ | harness + LLM | 插入 prompt、生成回答 |
| ⑦ | harness | 展示 |

**关键：rag-service 只做 ④；③ 是 SKILL/MCP 的桥接；⑤⑥ 是 agent 自己的 LLM 的活。**

---

## 1. 两种模式总览

| 维度 | SKILL（技能文件） | MCP（工具协议） |
|---|---|---|
| 本质 | markdown 说明书，agent 按描述执行命令 | 标准协议工具（JSON-RPC），工具化调用 |
| 依赖 | 无（curl/python） | mcp 1.x 库 + server 进程 |
| 触发 | SKILL description | 工具描述（docstring） |
| 适用 | Hermes / Claude Code 等 | DeepCode / Cursor / Claude Code 等 |
| 复杂度 | 低 | 中 |

**选择建议**：支持 skill → SKILL；支持 MCP → MCP；都支持可同时配。

---

## 模式一：SKILL（技能文件驱动）

### 2.1 是什么

SKILL = 一个 markdown 技能包：`description`（何时用）+ 正文（怎么用，含可执行命令）。Agent 判断话题匹配 description 时，执行正文命令。

### 2.2 目录结构

```
<skills-dir>/<skill-name>/SKILL.md
```
Hermes：`~/.hermes/skills/<category>/<skill-name>/SKILL.md`

### 2.3 description 设计三要素（触发率核心）

1. **正向触发词**："我记得/我的 wiki 里有没有/之前讨论过"
2. **主题域**：PARA/常绿笔记/P8 规则/系统概念（列举越具体越准）
3. **负向边界**：天气/新闻/通用编程不调用（省 token）

### 2.4 完整 SKILL.md 模板（可直接复制使用）

```markdown
---
name: llm-wiki-search
description: >-
  Search the local rag-service knowledge base (Chroma + BGE + BM25 hybrid retrieval) via HTTP API and
  inject matched knowledge into the current conversation. Use when the user references past discussions,
  personal knowledge, or previously stored notes — e.g. "我记得之前讨论过…", "我的 wiki 里有没有…", "上次是怎么决定的",
  or topics likely covered by the knowledge base (knowledge management, PARA/Evergreen/JIT methodology,
  P8 rules, system concepts). Do NOT call for clearly unrelated topics (weather, news, coding tasks).
  rag-service 是检索服务（只含 embedding 模型），生成回答由 Agent 自己的 LLM 完成。
---

# 本地知识库检索（HTTP 方式 A：检索即服务）

对话中先从 rag-service 检索，命中则把片段注入 prompt 再回答；未命中正常对话。

## 如何调用（执行命令）

curl -s -X POST http://127.0.0.1:8931/search \
  -H "Content-Type: application/json" \
  -d '{"query":"你的问题","top_k":3}'

## 输出格式与解析

响应：{"hits":[{"text":"片段内容","file":"来源文件","section":"章节","score":0.26}], "filtered":false}

- hits 非空 → 把每个 hit 的 text 作为上下文插入 prompt，回答注明来源
- filtered=true 或 hits 为空 → 知识库无相关内容，正常回答，不编造

## 注入 prompt 的格式（回答前拼装）

[来源: <file> → <section>]
<text>

【问题】<用户问题>
请基于以上资料回答；资料无关则忽略。

## 注意事项

- 检索只是召回层，相关性由你（LLM）判断，分数不能替代语义判断
- /search 报错或超时 → 忽略，正常对话（检索不阻塞主流程）
- 引用时注明来源（file/section），让用户感到知识跨会话可追溯
```

> 这个模板就是 `rag-service/skills/llm-wiki-search-HTTP/SKILL.md` 的完整内容——**正文即执行 + 解析 + 注入约定**，agent 拿到就能照做。

### 2.5 执行查询的三种写法（正文选一种）

**① curl 直调（推荐，零依赖）**——见 2.4 模板。
**② 封装脚本**（查询逻辑复杂、要后处理时）：

```python
#!/usr/bin/env python3
# /opt/rag-service/mcp/rag_query_cli.py — 查询 CLI（skill 正文引用它）
import sys, json, urllib.request

def search(query, top_k=3):
    req = urllib.request.Request("http://127.0.0.1:8931/search",
        data=json.dumps({"query": query, "top_k": top_k}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

if __name__ == "__main__":
    hits = search(sys.argv[1], int(sys.argv[3]) if len(sys.argv) > 3 else 3)
    for i, h in enumerate(hits.get("hits", []), 1):
        print(f"{i}. [{h['file']}→{h['section']}] {h['text'][:200]}")
```

SKILL 正文：`python3 /opt/rag-service/mcp/rag_query_cli.py "用户问题" --top 3`
**③ 走 MCP 工具**（harness 已配 MCP 时）：正文写"使用 knowledge_search 工具（query=..., top_k=3）"。

### 2.6 结果如何插入 prompt 给 LLM（agent 侧实现）

Agent 拿到 hits 后的拼装逻辑（伪代码，各 harness 语言对应）：

```python
hits = call_skill_search(user_question)     # ① 执行 SKILL 正文命令，得到 hits

if hits and is_relevant(hits, user_question):   # ② 判断相关性（LLM 自己看来源/内容）
    context = "\n\n".join(
        f"[来源: {h['file']} → {h['section']}]\n{h['text']}" for h in hits)
    prompt = f"{context}\n\n【问题】{user_question}\n基于以上资料回答并注明来源"
else:
    prompt = user_question                   # ③ 无匹配/无关 → 原问题，不注入

answer = llm_generate(prompt)                # ④ 调 agent 自己的模型生成
```

**这就是"检索结果插入 prompt 给 LLM"的完整实现**：片段拼进 user 消息作为上下文，LLM 基于它生成。

### 2.7 Hermes 具体配置示例（完整流程）

```bash
# ① 放置 SKILL（完整模板见 2.4）
cp /root/ubuntu-manage/chat/rag-service/skills/llm-wiki-search-HTTP/SKILL.md \
   /root/.hermes/skills/research/llm-wiki-search/SKILL.md

# ② 确认 rag-service 在跑
curl http://127.0.0.1:8931/health    # {"status":"ok","chunks":583}

# ③ 新对话验证
# 问："查一下我的 wiki：P8 内容归置的元规则是什么"
# 期望链路：Hermes 判断话题匹配 → 执行 curl /search → 拿到 hits → 注入 prompt → 回答引用来源
```

Hermes 特性：`~/.hermes/skills/<category>/<name>/`；skill 触发由 LLM 读 description 自主判断，无需额外配置。

### 2.8 注意事项（SKILL 模式）

| 项 | 说明 |
|---|---|
| description 质量 | 触发唯一依据，写触发词+主题域+边界 |
| 命令可复制 | 正文命令必须可直接执行（完整路径/参数） |
| 输出自解释 | 写明输出格式、命中/未命中区分 |
| 只读幂等 | 检索只读，可安全重试 |
| 安全 | 不要写密钥进 SKILL.md（检索免鉴权） |

---

## 模式二：MCP（模型上下文协议）

### 3.1 是什么

MCP 让 agent 通过**标准协议（JSON-RPC）**调用工具。harness 是 MCP 客户端，连接 MCP server，server 暴露 `knowledge_search` 工具（内部实现 RAG 检索）。比"读文档敲命令"更规范、可复用。

### 3.2 完整 MCP server 代码（含查询逻辑，无密钥）

```python
#!/usr/bin/env python3
# /opt/rag-service/mcp/rag_search_mcp.py — rag-service MCP server
# 依赖：mcp 1.x（pip install "mcp>=1.0,<2"）；密钥不在此文件（在 harness 的 env 配置）
import json
import os
import urllib.request

from mcp.server.fastmcp import FastMCP

# rag-service 检索端点（标准部署 8931）
RAG_BASE = os.environ.get("RAG_BASE", "http://127.0.0.1:8931")

mcp = FastMCP("rag-service")


def _search(query: str, top_k: int) -> dict:
    """内部查询逻辑：HTTP 调 rag-service /search，返回原始 JSON"""
    req = urllib.request.Request(
        RAG_BASE + "/search",
        data=json.dumps({"query": query, "top_k": top_k}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


@mcp.tool()
def knowledge_search(query: str, top_k: int = 3) -> str:
    """查询本地 llm-wiki 知识库（方法论/P8 规则/系统概念）。

    当用户问题可能涉及个人知识库、过往记录、笔记方法论时调用；
    命中返回知识片段（含来源），供回答引用；无命中返回"未匹配"。
    """
    # ① 调 rag-service 检索
    try:
        result = _search(query, top_k)
    except Exception as e:      # ② 失败兜底：返回可读文本，不崩协议
        return f"[检索失败] {e}"

    hits = result.get("hits") or []
    if not hits:                # ③ 无命中：明确告知，让 agent 不编造
        return "[未匹配] 知识库无相关内容"

    # ④ 格式化：把片段 + 来源拼成文本返回给 agent
    lines = [f"命中 {len(hits)} 条（来自本地知识库）："]
    for i, h in enumerate(hits, 1):
        text = h["text"].replace("\n", " ")[:300]
        lines.append(f"{i}. [来源:{h['file']}→{h['section']}] {text}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()                   # ⑤ 启动：默认 stdio 模式，等待客户端连接
```

**内部查询逻辑说明（对应整体流程 ③④⑤）：**

| 代码位置 | 实现 |
|---|---|
| `_search()` | ③④：HTTP POST /search，query 传 rag-service，拿原始 hits |
| `knowledge_search()` ① | ④：调用检索 |
| ② 错误处理 | 检索失败返回"[检索失败]"，agent 可忽略继续对话 |
| ③ 无命中 | 返回"[未匹配]"，防止 agent 编造 |
| ④ 格式化 | 把 hits 拼成"来源+内容"文本（这就是**插入 prompt 的原料**） |
| ⑤ `mcp.run()` | stdio 模式启动，客户端按协议调用 |

**agent 拿到返回值后**：把返回文本作为上下文插入自己的 prompt → LLM 生成回答（同 2.6 的拼装逻辑）。

### 3.3 调用方式（三种格式）

**① stdio 模式（本地，默认）**——client 启动 server 进程，stdin/stdout 走 JSON-RPC：

```json
// client → server：初始化
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
// server → client
{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{}},...}}
// client → server：调用工具
{"jsonrpc":"2.0","id":2,"method":"tools/call",
 "params":{"name":"knowledge_search","arguments":{"query":"P8 规则","top_k":3}}}
// server → client：返回结果
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"命中 2 条（来自本地知识库）：1. [来源:P8...→元规则] ..."}]}}
```

**② HTTP/SSE（服务化，多客户端）**——server 改 `mcp.run(transport="streamable-http")`，客户端 POST：

```bash
curl -X POST http://127.0.0.1:8932/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"knowledge_search","arguments":{"query":"P8 规则","top_k":3}}}'
```

**③ 纯 REST（最简，不经 MCP）**——任何 harness 直接调 rag-service：

```bash
curl -X POST http://127.0.0.1:8931/search \
  -H "Content-Type: application/json" \
  -d '{"query":"P8 规则","top_k":3}'
```

### 3.4 DeepCode 具体配置示例（完整）

```json
// ~/.deepcode/settings.json（密钥用 <你的key> 占位，不在此文档展示真实值）
{
  "env": {
    "MODEL": "deepseek-v4-flash",
    "BASE_URL": "https://ark.cn-beijing.volces.com/api/coding/v3",
    "API_KEY": "<你的API_KEY>"
  },
  "mcpServers": {
    "rag-service": {
      "command": "/root/ubuntu-manage/chat/venv-rag/bin/python",
      "args": ["/opt/rag-service/mcp/rag_search_mcp.py"],
      "timeout": 60000
    }
  }
}
```

部署步骤：
```bash
# ① 部署 server 文件 + 装依赖
sudo mkdir -p /opt/rag-service/mcp
sudo cp /root/ubuntu-manage/chat/rag-service/mcp/rag_search_mcp.py /opt/rag-service/mcp/
/root/ubuntu-manage/chat/venv-rag/bin/pip install "mcp>=1.0,<2"

# ② 改 settings.json（如上）③ 重启 DeepCode
# ④ 验证：问知识库话题，DeepCode 应调用 knowledge_search 并基于结果回答
```

### 3.5 注意事项（MCP 模式）

| 项 | 说明 |
|---|---|
| mcp 版本 | 必须 1.x（2.x 无 FastMCP） |
| server 常驻 | stdio 由 client 拉起；HTTP 需自己守护（systemd） |
| 工具描述 | docstring 是 agent 触发依据（同 SKILL description 三要素） |
| 超时 | 首调加载模型可能慢，client timeout ≥60s |
| 密钥 | **server 不含密钥**（key 在 harness env 配置，如 DeepCode settings.json） |

---

## 4. 通用可靠性约定（两模式共享）

1. **hits 是候选不是结论**：相关性由 Agent LLM 判断
2. **无匹配不编造**：空/`filtered=true` → 正常回答，不虚构
3. **来源可追溯**：引用注明 file/section
4. **检索失败不阻塞**：报错忽略，继续对话
5. **只读幂等**：检索无副作用

---

## 5. 故障排查

| 现象 | 排查 |
|---|---|
| skill 未触发 | description 触发词/主题域；harness 技能目录 |
| skill 报错 | 手动执行正文命令；curl /health |
| MCP 工具未出现 | settings.json 语法；mcp 1.x；server/venv 路径 |
| MCP 超时 | client timeout ≥60s（首调加载模型） |
| 检索不准 | top_k、POST /eval 评测、数据源配置 |

---

## 6. 适配任意 harness 速查

| 方式 | 我需要做 |
|---|---|
| **SKILL** | 复制 2.4 模板 → 改 description → 放 harness skills 目录 |
| **MCP stdio** | 用 3.2 server → 装 mcp 1.x → harness MCP 配置填 command/args |
| **MCP HTTP** | server 改 streamable-http → 配置 url → 服务常驻 |
| **纯 REST** | 任何能发 HTTP 的 harness，直接 curl /search（3.3③） |

---

## 7. 文件清单

| 文件 | 用途 |
|---|---|
| `rag-service/skills/llm-wiki-search-HTTP/SKILL.md` | SKILL 完整模板（= 2.4 内容） |
| `rag-service/mcp/rag_search_mcp.py` | MCP server 完整代码（= 3.2 内容） |
| `rag-service/Agent集成指南.md` | 方式 A 原理 |
| `/etc/rag-service/config.yaml` | rag-service 配置 |
