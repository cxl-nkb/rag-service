# rag-service Agent 集成指南（方式 A：检索即服务）

> 产品定位：rag-service 是**检索服务**，不是问答服务。它只包含 embedding 模型，不含生成模型、不含 LLM API key。
> 生成（回答）由接入方的 Agent 自带 LLM 完成——rag-service 是"资料库"，Agent 是"思考者"。

---

## 1. 集成原理（为什么这样设计）

```
用户 ──→ harness（Reasonix / Claude Code / Hermes）
            │
            ▼
        LLM 主模型（agent 的大脑）
            │  ① 判断：话题可能记录过 → 决定查知识库
            ▼
        调用 rag-service POST /search（HTTP，作为工具）
            │  ② 只传 query
            ▼
   [rag-service：embedding 向量化 → 混合检索 → 返回片段]
            │  ③ 返回 top-k 片段（来源 + 内容 + 分数）
            ▼
        LLM 主模型
            │  ④ 片段插入 prompt，重新推算
            ▼
        最终回答 ──→ 用户
```

**职责边界：**
- rag-service 负责 **第 ②③ 步**（检索）
- Agent 的 LLM 负责 **第 ①④ 步**（判断 + 生成）
- rag-service 不感知"谁在调用"，任何 LLM 都可复用

## 2. 接入步骤

### 2.1 启动服务

```bash
# 前台（开发）
./rag-service/scripts/start.sh

# 或 systemd（生产）
sudo systemctl start rag-service
```

### 2.2 Agent 注册为工具（Tool use）

以 Reasonix/Claude Code/Hermes 为例，注册一个工具描述：

```yaml
# 工具定义（tool schema）
name: knowledge_search
description: >
  查询本地 llm-wiki 知识库（方法论/系统概念/P8 决策规则等）。
  当用户问题可能涉及个人知识库、过往记录、笔记方法论时调用；
  无关话题（天气/编程教程）不调用。
parameters:
  query: string   # 要检索的问题
  top_k: integer  # 返回条数，默认 3
```

### 2.3 调用并注入

```python
# Agent 内部（伪代码）：检索 → 注入 prompt → 生成
hits = call_rag_service("POST /search", {"query": user_question, "top_k": 3})

# 命中 → 注入上下文
if hits:
    context = "\n\n".join(
        f"[来源: {h['file']} → {h['section']}]\n{h['text']}" for h in hits)
    prompt = f"{context}\n\n【问题】{user_question}\n基于以上资料回答，无关则忽略。"
else:
    # 未命中 → 正常对话，不编造知识库内容
    prompt = user_question
answer = llm_generate(prompt)   # agent 自己的模型
```

## 3. API 契约（/search）

```bash
curl -X POST http://127.0.0.1:8931/search \
  -H "Content-Type: application/json" \
  -d '{"query":"P8 入库条件是什么","top_k":3}'
```

响应：

```json
{
  "hits": [
    {"text": "【P8 / 元规则】...", "file": "P8 - 内容归置决策",
     "section": "元规则", "score": 0.26}
  ],
  "filtered": false,
  "query": "P8 入库条件是什么"
}
```

**关键语义（Agent 必须理解）：**
- `hits` 是**候选**，不是结论——相关性由 Agent 的 LLM 判断（分数阈值无法替代语义判断）
- `filtered=true` 表示主题过滤拦截（查询明显不在知识库主题域）
- `hits=[]` 表示无匹配 → Agent 应正常回答，**不编造知识库内容**
- `score` 为 RRF 融合分，越高越相关（参考：0.25+ 强相关）

## 4. 可靠性约定（Agent 侧）

| 场景 | Agent 行为 |
|---|---|
| 命中且相关 | 引用来源回答，注明"来自我的知识库" |
| 命中但无关 | 忽略检索结果，正常回答 |
| 无命中 | 正常回答，不编造 |
| /search 报错 | 忽略，正常对话（检索失败不阻塞主流程） |

## 5. /ask 是什么（已降级，可选）

`POST /ask` 是"一体化完整模式"——检索 + **内置** LLM 汇总（需配置 `ARK_API_KEY`）。它绕过 Agent 自己的模型，**不是产品主路径**。仅作为一体化演示或独立知识库问答用。主架构请用 `/search` + Agent 自带 LLM。
