# Hermes 与 DeepCode 接入 rag-service 指南（方式 A：检索即服务）

> 2026-08-17。目标：让 Hermes 和 DeepCode 两个 agent 在对话中自动检索本地知识库（rag-service），命中注入回答。
> 原理：rag-service 是检索服务（只含 embedding 模型），agent 的 LLM 负责判断与生成——"资料库 + 思考者"分离。

---

## 1. 接入原理回顾

```
用户提问 → Agent LLM 判断"可能记录过" → 调 rag-service /search（HTTP）
        → 拿到知识片段 → 注入 prompt → Agent LLM 生成回答
```

- rag-service 只做检索（/search），不含 LLM、不含 API key
- 两个 agent 接入方式不同（各用其原生扩展机制）：
  - **Hermes**：skill（SKILL.md 描述驱动触发）
  - **DeepCode**：MCP server（settings.json 注册工具）

---

## 2. Hermes 接入（skill 方式）

### 2.1 原理

Hermes 通过 `~/.hermes/skills/<category>/<skill-name>/SKILL.md` 发现 skill。SKILL.md 的 `description` 描述触发场景，Hermes 在对话中判断"这个话题可能记录过"时，按 skill 内说明调用检索。

### 2.2 步骤

**① 放置新版 skill 文件**

新版 skill（HTTP 方式 A）在：`rag-service/skills/llm-wiki-search-HTTP/SKILL.md`

复制到 Hermes skills 目录（替换旧 CLI 版）：

```bash
cp /root/ubuntu-manage/chat/rag-service/skills/llm-wiki-search-HTTP/SKILL.md \
   /root/.hermes/skills/research/llm-wiki-search/SKILL.md
```

> 注意：旧版是 CLI 调 `llm-wiki-search.py`（直连开发索引），新版改为 `curl /search`（走生产 rag-service）。**生产环境必须用 HTTP 版**（V1 CLI 直连 rag-wiki-db 与生产索引冲突）。

**② 确认 rag-service 在运行**

```bash
curl http://127.0.0.1:8931/health   # {"status":"ok","chunks":583}
```

**③ 验证（新对话测试）**

问 Hermes："查一下我的知识库：P8 内容归置的元规则是什么"——如果回答引用了来源（"按你 wiki 里的 P8 规则…"），说明 skill 触发链路通了。

### 2.3 触发优化（可选）

SKILL.md 的 `description` 已含触发词（"我记得/我的 wiki 里有没有/之前讨论过"等）。想让 Hermes 更主动，可在 system prompt 或角色配置中补充："涉及个人知识库/过往记录时，先调用 llm-wiki-search"。

---

## 3. DeepCode 接入（MCP 方式）

### 3.1 原理

DeepCode 支持 MCP（`~/.deepcode/settings.json` 的 `mcpServers` 配置）。我们提供一个 MCP server，暴露 `knowledge_search` 工具，内部调 rag-service /search。

### 3.2 准备 MCP server

MCP server 文件已写好：`rag-service/mcp/rag_search_mcp.py`（依赖 mcp 1.x 库）。

```bash
# ① 部署 MCP server 到生产（/opt/rag-service/mcp/）
sudo mkdir -p /opt/rag-service/mcp
sudo cp /root/ubuntu-manage/chat/rag-service/mcp/rag_search_mcp.py /opt/rag-service/mcp/

# ② 安装 mcp 库到 venv（供 MCP server 运行）
/root/ubuntu-manage/chat/venv-rag/bin/pip install "mcp>=1.0,<2"
```

### 3.3 注册到 DeepCode

编辑 `~/.deepcode/settings.json`，在 `mcpServers` 加一项：

```json
{
  "env": {
    "MODEL": "deepseek-v4-flash",
    "BASE_URL": "https://ark.cn-beijing.volces.com/api/coding/v3",
    "API_KEY": "<你的key>"
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

### 3.4 重启 DeepCode 并验证

1. 重启 DeepCode（新对话生效）
2. 测试：问 DeepCode 一个知识库话题（如"P8 的内容归置规则是什么"）——DeepCode 应调用 `knowledge_search` 工具，返回来源片段后基于它回答
3. 失败排查：
   - `rag-search` 工具未出现 → 检查 settings.json JSON 语法、MCP server 路径、`pip show mcp` 版本（需 1.x）
   - 工具调用报错 → 确认 rag-service 在跑（`curl /health`）

### 3.5 DeepCode 补充（AGENTS.md，可选加固）

DeepCode 读取 `AGENTS.md` 作为项目指令。可在项目根 `AGENTS.md` 加：

```markdown
## 知识库检索

本项目接入了本地 rag-service（http://127.0.0.1:8931）。当用户问题涉及个人知识库、
过往记录、笔记方法论（PARA/常绿笔记/P8 规则等）时，使用 `knowledge_search` 工具
检索后再回答，并注明来源。检索无命中时正常回答，不编造。
```

---

## 4. 两种接入方式对比

| 项 | Hermes | DeepCode |
|---|---|---|
| 机制 | skill（SKILL.md 描述驱动） | MCP server（工具注册） |
| 触发 | 对话中按 description 判断 | 对话中按工具描述调用 |
| 文件 | `~/.hermes/skills/research/llm-wiki-search/SKILL.md` | `~/.deepcode/settings.json` + MCP server |
| 依赖 | curl（系统自带） | mcp 1.x 库（venv） |
| 验证 | 问知识库话题，看是否引用来源 | 问知识库话题，看工具调用 |

## 5. 通用可靠性约定（两个 agent 都要遵守）

1. **hits 是候选不是结论**——相关性由 agent LLM 判断（分数不能替代语义判断）
2. **无匹配不编造**——`filtered=true` 或 `hits=[]` 时正常回答，不虚构知识库内容
3. **来源可追溯**——引用时注明 file/section
4. **检索失败不阻塞**——/search 报错时忽略，继续正常对话

## 6. 相关文件清单

| 文件 | 作用 |
|---|---|
| `rag-service/skills/llm-wiki-search-HTTP/SKILL.md` | Hermes 新版 skill（HTTP 方式 A） |
| `rag-service/mcp/rag_search_mcp.py` | DeepCode MCP server（knowledge_search 工具） |
| `/etc/rag-service/config.yaml` | rag-service 配置（数据源/资源） |
| `Agent集成指南.md` | 通用接入说明（方式 A） |
