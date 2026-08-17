# rag-service GitHub 交付方案：deb 打包 + apt/PPA

> 2026-08-15。目标：任何人 `git clone` 后，通过 deb 包或 apt 仓库安装，`systemctl start rag-service` 即用。
> 许可：非商用（详见第 7 节）。环境：Ubuntu 24.04 (noble)。

---

## 1. 总体目标与用户视角

```
方式 A（apt 直达，最顺）:
  sudo add-apt-repository ppa:<you>/rag-service
  sudo apt update && sudo apt install rag-service
  systemctl start rag-service

方式 B（deb 手动安装）:
  wget https://github.com/<you>/rag-service/releases/download/v2.0.0/rag-service_2.0.0_amd64.deb
  sudo dpkg -i rag-service_2.0.0_amd64.deb && sudo apt -f install
  systemctl start rag-service

方式 C（源码构建）:
  git clone ... && ./scripts/build-deb.sh   # 本机构建 deb
```

安装后自动完成：Python 依赖、BGE 模型下载、systemd 单元注册并 enable、数据目录初始化。

## 2. deb 包构成（安装后的系统布局）

| 路径 | 内容 |
|---|---|
| `/usr/lib/rag-service/venv/` | 完整虚拟环境（dh-virtualenv 打包，含全部 pip 依赖） |
| `/usr/bin/rag-service` | 启动入口（指向 venv 的 uvicorn） |
| `/etc/rag-service/config.yaml` | 配置文件（安装时从示例生成，用户可改） |
| `/var/lib/rag-service/data/` | Chroma 索引、chunks、manifest（运行时数据） |
| `/lib/systemd/system/rag-service.service` | systemd 单元（dpkg 自动注册） |
| `/var/log/rag-service/` | 运行日志 |

**关键设计：代码只读（/usr）、配置可改（/etc）、数据可变（/var）——符合 Debian 目录规范。**

## 3. 打包流程（关键：Python 依赖自包含）

**难点：** chromadb / fastembed / rank_bm25 等在 Debian 官方源里没有或版本旧。解决方案：**dh-virtualenv**——把整个 venv 打进 deb，一次装好所有 pip 依赖，不依赖系统 Python 包。

```
1. 准备工具链
   sudo apt install devscripts debhelper dh-virtualenv dh-python

2. 项目结构（Debian 打包约定）
   rag-service/
   ├── debian/
   │   ├── control        # 包元信息（描述/依赖/许可）
   │   ├── rules          # dh-virtualenv 构建规则
   │   ├── changelog
   │   ├── postinst       # 安装后：注册 systemd、下模型、建索引
   │   └── compat
   ├── setup.py / pyproject.toml
   └── src/rag_service/

3. 构建
   dpkg-buildpackage -us -uc      # 生成 rag-service_2.0.0_amd64.deb

4. 关键规则（debian/rules）
   %:
       dh $@ --with python-virtualenv
   override_dh_virtualenv:
       dh_virtualenv --python=/usr/bin/python3
```

## 4. systemd 集成（deb 自动完成）

`debian/postinst`（安装后脚本）：

```bash
#!/bin/sh
set -e
# 1. 生成默认配置（用户可覆盖）
[ -f /etc/rag-service/config.yaml ] || cp /usr/lib/rag-service/config.example.yaml /etc/rag-service/config.yaml
# 2. 首次构建索引（模型下载 + 数据入库；可跳过，由服务首启懒加载）
# 3. 注册并启动服务
systemctl daemon-reload
systemctl enable rag-service
systemctl restart rag-service || true
```

`debian/prerm`（卸载前）：`systemctl stop rag-service`。
`debian/postrm`（卸载后）：purge 时删 /etc、/var/lib 数据（可选，加 --purge 判断）。

## 5. apt/PPA 发布（两种方式）

### 方式 A：Launchpad PPA（最省心，推荐）

1. 注册 Launchpad 账号 → 创建 PPA（`ppa:<you>/rag-service`）
2. 用 `dput` 上传源码包（源包含 debian/ 目录）
3. Launchpad 自动构建 amd64/arm64，用户 `add-apt-repository` 即用
4. **限制**：非商用许可需在 PPA 描述中明确；源码需公开或走私有 PPA（Launchpad 支持私有 PPA）

### 方式 B：自建 apt 仓库（GitHub Releases + 脚本）

用已有的 `apt-ftparchive`（本机已装）生成 Packages 索引，托管到 GitHub Releases 页面：

```bash
# build-deb.sh 里：构建 deb → 生成 Packages.gz → 打包 repo 上传
apt-ftparchive packages . > Packages
gzip -k Packages
# 用户侧：
echo "deb [signed-by=key] https://github.com/<you>/rag-service/releases/download/repo ./" > /etc/apt/sources.list.d/rag-service.list
```

（需 GPG 签名 key，用户导入公钥；比 Launchpad 灵活但维护多。）

## 6. 关键工程改造（打包前必须做）

1. **app/ → src/rag_service/**：包化，去掉 sys.path hack（`from config import ...` → `from rag_service.config import ...`）
2. **配置/数据分离**：
   - 代码读 `/etc/rag-service/config.yaml`（可被环境变量覆盖 `RAG_CONFIG`）
   - 数据写 `/var/lib/rag-service/data/`（可配）
3. **模型下载独立模块**：`model_download.py`——检测缓存（`~/.cache/rag-service/`），无则从 hf-mirror 下载（复用已验证的禁 xet 逻辑）；失败降级提示
4. **入口脚本**：`rag-service` 命令包装 uvicorn（解析 /etc 配置）
5. **.gitignore**：`data/ venv/ __pycache__ *.egg-info .pytest_cache`
6. **版本化**：`__version__` + changelog，git tag 对应版本

## 7. 非商用许可

非商用许可不能直接用标准 MIT/Apache——需自定义或用 CC BY-NC：

- **推荐：自定义 LICENSE 文本**（基于 MIT 修改 + 非商用条款），明确：
  - 允许：下载、学习、修改、个人/内部使用
  - 禁止：商业用途、闭源再分发（视条款）、未经许可商用集成
- 打包时：`debian/copyright` 声明许可；README 醒目提示非商用
- **提醒**：非商用许可能限制传播（企业用户会谨慎），如需推广可后续放宽

## 8. 当前环境限制与建议

| 限制 | 说明 | 应对 |
|---|---|---|
| `/etc` 只读 | 本 WSL 环境无法实装 systemd 单元 | 打包与验证在可写区完成，交付物供真实环境安装 |
| 打包工具缺 3 个 | debuild/dh_make/dh-virtualenv | `apt install`（模拟验证已通过） |
| PPA 需账号 | Launchpad 需注册 | 先用 GitHub Releases 自建 repo（方式 B）起步 |

## 9. 阶段划分

- **阶段 1（打包 MVP）**：src 包化改造 → dh-virtualenv 打 deb → 本机构建出 `.deb` → 验证 dpkg 安装 + systemctl（在可写环境）→ GitHub Releases 发布 deb
- **阶段 2（apt 仓库）**：apt-ftparchive 生成 repo → GPG 签名 → 用户 add-apt-repository 可装
- **阶段 3（可选进阶）**：Launchpad PPA（自动多架构构建）、CI（GitHub Actions 自动打 deb 发布）

## 10. 与 V3 增强的关系

V3 增强（鉴权/分库/评测接口）应在打包结构稳定后进行——避免反复改 deb 布局。建议：**先完成阶段 1 打包 MVP，再并行开发 V3 功能**（功能进源码，打包流程不变）。
