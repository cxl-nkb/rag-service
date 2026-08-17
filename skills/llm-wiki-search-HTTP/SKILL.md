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

## 如何调用（HTTP，不再用 CLI）

```bash
curl -s -X POST http://127.0.0.1:8931/search \
  -H "Content-Type: application/json" \
  -d '{"query":"你的问题","top_k":3}'
```

响应：`{"hits":[{"text":...,"file":...,"section":...,"score":...}], "filtered":bool}`

## 结果判断（检索是召回层，相关性由 Agent LLM 判断）

1. 看 `hits` 的 `file`/`section` 是否与话题相关
2. 相关 → 把 `text` 注入 prompt，回答并注明来源（"按你 wiki 里的 P8 规则…"）
3. 无关或 `hits` 为空 / `filtered=true` → 正常回答，**不编造知识库内容**
4. `/search` 报错 → 忽略，正常对话（检索失败不阻塞主流程）

## 提示

- 服务未启动时先 `systemctl start rag-service`（或开发环境 `scripts/start.sh`）
- 回答引用知识库时标注来源（file/section），让用户感到知识跨会话可追溯
