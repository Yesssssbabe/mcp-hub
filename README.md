# MCP Hub 🔧

> MCP 生态的 "npm + Homebrew" — 发现、安装、管理 MCP 工具的一站式平台

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

> [English README](README_EN.md) | 中文文档

---

## 目录

- [项目简介](#项目简介)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [详细命令参考](#详细命令参考)
- [配置指南](#配置指南)
- [安全说明](#安全说明)
- [开发指南](#开发指南)
- [架构概览](#架构概览)
- [贡献指南](#贡献指南)
- [路线图](#路线图)
- [许可证和致谢](#许可证和致谢)

---

## 项目简介

### 什么是 MCP？

**MCP（Model Context Protocol）** 是由 Anthropic 发起的开放协议，旨在标准化 AI 模型与外部工具、数据源之间的交互方式。通过 MCP，AI 助手可以安全地访问文件系统、数据库、API 服务、开发工具等，大幅扩展其能力边界。

### 为什么需要 MCP Hub？

随着 MCP 生态的快速发展，社区已经涌现出数百个 MCP 工具（也称为 MCP Server）。然而，开发者面临诸多挑战：

- **发现困难**：散落在 GitHub、npm、PyPI 等各处，没有统一索引
- **安装复杂**：每个工具的安装方式不同，配置格式各异
- **配置繁琐**：需要手动编辑 Claude、Cursor、Cline 等客户端的配置文件
- **安全隐患**：无法快速评估工具的权限风险和安全等级
- **版本管理**：缺乏版本控制和更新机制

**MCP Hub** 正是为逐步解决这些问题而生。它提供了一站式的 MCP 工具发现、安装、配置和安全扫描体验，让开发者可以更快地将注册表中的常见 MCP 工具集成到自己的工作流中。

### 核心价值和定位

MCP Hub 的定位是 **MCP 生态的 "npm + Homebrew"** — 一个集包管理器、注册表、安全扫描和配置工具于一体的平台：

| 类比 | 功能对应 |
|------|----------|
| npm Registry | MCP Hub Registry — 收录和索引所有 MCP 工具 |
| `npm install` | `mcp-hub install` — 安装注册表中的 MCP 工具 |
| `package.json` | `mcp-hub config` — 统一管理客户端配置 |
| `npm audit` | `mcp-hub scan` — 安全扫描与风险评估 |
| Homebrew Cask | `mcp-hub search` — 发现新工具 |

---

## 功能特性

- ✅ **MCP 工具发现与搜索** — 支持按名称、标签、类别、关键词智能搜索
- ✅ **一键安装** — 支持 npm、pip、Docker、git、binary 等多种安装方式
- ✅ **多客户端配置** — 自动适配 Claude、Cursor、Cline、Copilot、VSCode、Windsurf 等客户端
- ✅ **安全扫描与评分** — 静态代码分析、权限/网络风险分析、依赖文件解析，提供 0-100 安全评分
- ✅ **安装生命周期管理** — 支持安装、强制重装、卸载、验证；Installer 层提供已安装工具的原子更新和失败回滚
- ✅ **跨平台支持** — 原生支持 macOS、Windows、Linux 三大平台
- ✅ **批量扫描** — `mcp-hub scan` 可扫描所有已安装工具
- ✅ **本地缓存** — 支持本地注册表、扫描缓存和离线漏洞库组件
- 🚧 **v0.2.0 安全增强进行中** — OSV 漏洞查询、离线降级、扫描缓存等组件已加入；安全策略、安装前门禁和审计日志仍在路线图中

---

## 快速开始

### 安装

```bash
# 使用 pip 安装（推荐）
pip install mcp-hub

# 或使用 uv
uv tool install mcp-hub
```

### 初始化配置

```bash
# 首次使用，初始化配置目录和默认注册表
mcp-hub init
```

初始化后，MCP Hub 会在你的用户目录下创建配置文件夹：

- **macOS/Linux**: `~/.config/mcp-hub/`（若已存在 `~/.mcp-hub/` 则兼容保留）
- **Windows**: `%APPDATA%\mcp-hub\`

### 搜索工具

```bash
# 搜索文件系统相关工具
mcp-hub search filesystem

# 按标签搜索
mcp-hub search --tags database

# 限制结果数量
mcp-hub search --limit 10
```

### 安装工具

```bash
# 安装文件系统工具
mcp-hub install server-filesystem

# 使用自定义安装目录
mcp-hub install server-filesystem --base-dir /tmp/mcp-tools
```

> **注意**：当前版本已支持 npm 作用域包名（如 `@org/package`）。

### 查看已安装工具

```bash
# 列出所有已安装工具
mcp-hub list --installed
```

### 安全扫描

```bash
# 扫描工具安全评分
mcp-hub scan server-filesystem

# 快速扫描
mcp-hub scan server-filesystem --quick
```

---

## 详细命令参考

### `mcp-hub init`

初始化 MCP Hub 工作目录和默认配置。

```bash
mcp-hub init [OPTIONS]

Options:
  --registry PATH   自定义注册表路径
  --config PATH     自定义配置文件路径
  --config-dir PATH 自定义配置目录
  --force           强制重新初始化，覆盖现有配置
```

**示例：**

```bash
# 标准初始化
mcp-hub init

# 使用自定义注册表路径
mcp-hub init --registry ~/.config/mcp-hub/custom-registry.json

# 使用自定义配置文件路径
mcp-hub init --config ~/.config/mcp-hub/custom-config.json

# 强制重新初始化
mcp-hub init --force
```

---

### `mcp-hub search <query>`

在 MCP Hub 注册表中搜索工具。

```bash
mcp-hub search <query> [OPTIONS]

Arguments:
  query         搜索关键词（支持模糊匹配，默认为空字符串）

Options:
  --tag TEXT      按标签筛选（可多次使用，逗号分隔）
  --category TEXT 按类别筛选
  --limit INT          结果数量限制（默认 20）
  --sort TEXT          排序方式：relevance、stars、name、recent、downloads
  --json               以 JSON 格式输出
  --registry PATH      指定注册表路径
```

**示例：**

```bash
# 搜索文件系统工具
mcp-hub search filesystem

# 搜索数据库工具，按下载量排序
mcp-hub search --tag database --sort downloads --limit 10

# JSON 输出（供脚本使用）
mcp-hub search filesystem --json | jq '.[].name'
```

---

### `mcp-hub install <tool>`

安装 MCP 工具。

```bash
mcp-hub install <tool> [OPTIONS]

Arguments:
  tool          工具名称（仅支持字母、数字、下划线、连字符）

Options:
  --method TEXT       安装方式：auto、npm、pip、docker、git、binary（默认 auto）
  --client TEXT       目标客户端（可多次使用，支持 claude|cursor|cline|copilot|vscode|windsurf）
  --force             强制重新安装（覆盖现有版本）
  --dry-run           模拟安装，不执行实际操作
```

**示例：**

```bash
# 自动安装并配置到 Claude
mcp-hub install server-filesystem --client claude

# 安装到多个客户端
mcp-hub install server-filesystem --client claude --client cursor

# 使用 pip 安装
mcp-hub install server-sqlite --method pip

# 强制重新安装
mcp-hub install server-filesystem --force

# 模拟安装（预览操作）
mcp-hub install server-filesystem --dry-run
```

---

### `mcp-hub uninstall <tool>`

卸载已安装的 MCP 工具。

```bash
mcp-hub uninstall <tool> [OPTIONS]

Arguments:
  tool          工具名称

Options:
  --base-dir PATH     自定义安装目录
  --yes, -y           跳过确认提示
  --purge             彻底删除，包括配置和数据文件
```

**示例：**

```bash
# 卸载工具（带确认）
mcp-hub uninstall server-filesystem

# 静默卸载
mcp-hub uninstall server-filesystem --yes

# 彻底删除（含配置）
mcp-hub uninstall server-filesystem --purge
```

---

### `mcp-hub list`

列出注册表中的工具或已安装的工具。

```bash
mcp-hub list [OPTIONS]

Options:
  --installed         仅列出已安装工具
  --category TEXT     按类别筛选
  --json              以 JSON 格式输出
  --registry PATH     指定注册表路径
```

**示例：**

```bash
# 列出所有已安装工具
mcp-hub list --installed

# 列出文件系统类别工具
mcp-hub list --category filesystem

# JSON 输出
mcp-hub list --json
```

---

### `mcp-hub config <action>`

管理客户端配置。

```bash
mcp-hub config <action> [OPTIONS]

Arguments:
  action          操作类型：add, remove, list, show, generate, detect, auto, validate, import, export

Options:
  --client TEXT      指定客户端（claude|cursor|cline|copilot|vscode|windsurf）
  --tool TEXT        指定工具名称（用于 auto 操作）
  --config PATH      指定配置文件路径
  --name TEXT        服务器名称（用于 add/remove）
  --command TEXT     命令路径（用于 add）
  --args TEXT        命令参数，逗号分隔（用于 add）
  --env KEY=VALUE    环境变量（可多次使用，格式 KEY=VALUE）
  --import PATH      从文件导入配置（import 操作）
  --export PATH      导出配置到文件路径（export 操作）
```

**示例：**

```bash
# 列出所有客户端配置
mcp-hub config list

# 添加服务器配置
mcp-hub config add --client claude --name filesystem --command npx --args "-y,@modelcontextprotocol/server-filesystem"

# 添加带环境变量的配置
mcp-hub config add --client claude --name postgres --command npx --env DATABASE_URL=postgres://localhost/db

# 移除服务器配置
mcp-hub config remove --client claude --name filesystem

# 生成 MCP JSON 配置
mcp-hub config generate --client claude

# 显示当前配置
mcp-hub config show

# 验证配置格式
mcp-hub config validate --client claude

# 导出配置备份
mcp-hub config export --client claude --export ~/.config/mcp-hub/exports/claude-backup.json

# 导入配置
mcp-hub config import --client claude --import ~/.config/mcp-hub/exports/claude-backup.json

# 自动配置工具到客户端
mcp-hub config auto --client claude --tool server-filesystem

# 检测客户端配置
mcp-hub config detect
```

---

### `mcp-hub scan <tool>`

对 MCP 工具进行安全扫描。

```bash
mcp-hub scan [tool] [OPTIONS]

Arguments:
  tool          工具名称（留空扫描所有已安装工具）

Options:
  --registry PATH    指定注册表路径
  --quick, -q        快速扫描模式（仅输出分数）
  --detailed, -d     显示详细扫描报告
  --json, -j         以 JSON 格式输出
  --severity TEXT    最低严重级别：UNKNOWN、LOW、MEDIUM、HIGH、VERIFIED
```

**示例：**

```bash
# 扫描单个工具
mcp-hub scan server-filesystem

# 详细扫描报告
mcp-hub scan server-filesystem --detailed

# 扫描所有已安装工具
mcp-hub scan

# 快速扫描
mcp-hub scan server-filesystem --quick

# JSON 输出
mcp-hub scan server-filesystem --json

# 仅显示高危问题
mcp-hub scan --severity HIGH
```

---

## 配置指南

### 各客户端配置路径

MCP Hub 会自动检测并管理以下客户端的 MCP 配置：

| 客户端 | 配置文件路径 |
|--------|-------------|
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) <br> `~/.config/claude/claude_desktop_config.json` (Linux) <br> `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |
| **Cursor** | `~/.cursor/mcp.json` (macOS) <br> `~/.config/Cursor/mcp.json` (Linux) <br> `%APPDATA%\Cursor\mcp.json` (Windows) |
| **Cline** | `~/.cline/mcp.json` (macOS) <br> `~/.config/Cline/mcp.json` (Linux) <br> `%APPDATA%\Cline\mcp.json` (Windows) |
| **GitHub Copilot** | `~/.github/copilot/mcp.json` (macOS) <br> `~/.config/GitHub Copilot/mcp.json` (Linux) <br> `%APPDATA%\GitHub Copilot\mcp.json` (Windows) |
| **VSCode** | `~/.vscode/mcp.json` (macOS) <br> `~/.config/Code/User/mcp.json` (Linux) <br> `%APPDATA%\Code\User\mcp.json` (Windows) |
| **Windsurf** | `~/.windsurf/mcp.json` (macOS) <br> `~/.config/Windsurf/mcp.json` (Linux) <br> `%APPDATA%\Windsurf\mcp.json` (Windows) |

### 手动配置

如果你需要手动编辑配置，MCP Hub 使用标准的 MCP 配置格式：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
      "env": {
        "NODE_ENV": "production"
      }
    },
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "/path/to/db.sqlite"]
    }
  }
}
```

### 环境变量配置

MCP Hub 支持以下环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MCP_HUB_CONFIG_DIR` | 配置目录路径 | `~/.config/mcp-hub/`（若 `~/.mcp-hub/` 存在则回退） |
| `MCP_HUB_TEST_MODE` | 测试模式（值为 `1` 时启用） | 无 |

> **注意**：`MCP_HUB_REGISTRY_URL`、`MCP_HUB_CACHE_DIR`、`MCP_HUB_LOG_LEVEL`、`MCP_HUB_DEFAULT_CLIENT`、`MCP_HUB_NO_COLOR` 和 `MCP_HUB_VERIFY_SSL` 环境变量将在后续版本支持。

---

## 安全说明

### 安全评分系统

MCP Hub 为每个工具提供 0-100 分的安全评分，基于以下维度：

| 维度 | 权重 | 说明 |
|------|------|------|
| **权限范围** | 30% | 文件系统、网络、代码执行等权限的广度 |
| **代码静态分析** | 35% | 源码风险模式扫描结果 |
| **依赖风险** | 20% | 依赖文件解析、可疑依赖和版本风险；OSV 漏洞情报组件在 v0.2.0 中逐步接入 |
| **网络访问** | 15% | 网络权限、端点配置和访问范围风险 |

### 安全等级

- **🟢 90-100**: 风险很低 — 权限较小、静态扫描和依赖检查未发现明显风险
- **🟡 70-89**: 风险较低 — 存在少量提示项或未安装导致的可验证性限制
- **🟠 50-69**: 需谨慎 — 权限较广、依赖或网络访问存在明显风险信号
- **🔴 0-49**: 高风险 — 代码执行、写权限、网络访问或依赖风险较高

### 权限分析说明

每个 MCP 工具的权限在注册表中被明确标注：

权限类型包括：

- `filesystem:read` — 文件读取
- `filesystem:write` — 文件写入
- `network` — 网络访问
- `code_execution` — 代码执行
- `shell` — Shell 命令执行
- `database` — 数据库访问

### 安全最佳实践

1. **安装前扫描**：始终使用 `mcp-hub scan` 检查安全评分
2. **最小权限原则**：只安装所需工具，避免使用权限过广的工具
3. **隔离环境**：使用 Docker 或虚拟环境运行高风险工具
4. **定期审查**：使用 `mcp-hub list --installed` 检查已安装工具
5. **监控日志**：关注工具的运行日志，发现异常行为
6. **限制目录**：文件系统工具应限制到特定工作目录

---

## 开发指南

### 克隆项目

```bash
git clone https://github.com/Yesssssbabe/mcp-hub.git
cd mcp-hub
```

### 安装开发依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装开发依赖
pip install -e ".[dev]"

# 或使用 uv
uv pip install -e ".[dev]"
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行带覆盖率报告
pytest --cov=mcp_hub --cov-report=html

# 运行特定测试文件
pytest tests/test_installer.py
```

### 代码风格

本项目使用以下工具保持代码质量：

```bash
# 代码格式化（black）
black src/mcp_hub tests

# 代码检查（ruff）
ruff check src/mcp_hub tests

# 类型检查（mypy）
mypy src/mcp_hub

# 一键运行所有检查
make lint

# 自动修复可修复的问题
make fix
```

### 提交 PR 流程

1. **Fork 仓库** 并创建功能分支：`git checkout -b feature/your-feature`
2. **编写代码** 并确保通过所有测试和 lint 检查
3. **更新文档** 和 CHANGELOG（如适用）
4. **提交 PR** 到 `main` 分支，使用提供的 PR 模板
5. **等待 CI 通过** 和维护者审查

---

## 架构概览

```
mcp-hub/
├── src/mcp_hub/
│   ├── __init__.py        # 包入口
│   ├── cli.py             # 命令行接口（Typer）
│   ├── registry.py        # 工具注册表（本地 + 内置）
│   ├── installer.py       # 安装管理器（npm/pip/docker/git/binary）
│   ├── config.py          # 配置管理（多客户端适配）
│   ├── security.py        # 安全扫描引擎
│   ├── osv_client.py      # OSV 漏洞情报客户端
│   ├── scan_cache.py      # 扫描结果缓存和失效管理
│   ├── offline_vuln_db.py # 离线漏洞库
│   ├── vulnerability_models.py # 漏洞扫描数据模型
│   ├── utils.py           # 工具函数和辅助方法
│   └── constants.py       # 常量和默认值
├── tests/
│   ├── test_cli.py        # CLI 测试
│   ├── test_config.py     # 配置测试
│   ├── test_installer.py  # 安装器测试
│   ├── test_registry.py   # 注册表测试
│   ├── test_security.py   # 安全测试
│   ├── test_osv_client.py # OSV 客户端测试
│   ├── test_osv_integration.py # OSV 集成测试
│   ├── test_scan_cache.py # 扫描缓存测试
│   ├── test_utils.py      # 工具测试
│   └── conftest.py        # pytest 配置和共享 fixture
├── pyproject.toml         # 项目配置和依赖
├── README.md              # 中文文档
├── README_EN.md          # 英文文档
└── plan.md               # UAT 修复计划
```

### 核心模块职责

| 模块 | 职责 |
|------|------|
| `cli.py` | 解析命令行参数，调用各功能模块，格式化输出 |
| `registry.py` | 维护工具元数据索引，支持搜索、查询、内置工具加载 |
| `installer.py` | 封装多种安装方式的统一接口，处理依赖和环境 |
| `config.py` | 适配不同客户端的配置格式，读写配置文件 |
| `security.py` | 静态代码分析、权限/网络风险分析、依赖解析、评分计算 |
| `osv_client.py` / `dependency_vuln_mapper.py` | OSV 查询、依赖到漏洞情报的映射、离线降级 |
| `scan_cache.py` / `offline_vuln_db.py` | 扫描缓存、缓存失效、离线漏洞数据存取 |
| `utils.py` | 共享工具函数、日志、进度条、平台检测 |

---

## 贡献指南

我们欢迎各种形式的贡献！无论是提交新的 MCP 工具、修复 Bug、改进文档还是提出新功能建议。

### 如何提交 MCP 工具

1. 在 [GitHub Issues](https://github.com/Yesssssbabe/mcp-hub/issues) 中提交工具收录请求
2. 或直接编辑 `registry/tools.json` 提交 PR
3. 工具需包含以下信息：
   - 名称和唯一标识符
   - 描述和分类
   - 安装方式（npm/pip/docker/git）
   - 权限声明
   - 维护者信息

### 如何贡献代码

详见 [CONTRIBUTING.md](docs/CONTRIBUTING.md)，包含：
- 开发环境搭建
- 代码规范（PEP 8, black, ruff, mypy）
- 测试要求（覆盖率 > 80%）
- PR 模板和提交消息规范

### 代码规范

- 遵循 [PEP 8](https://peps.python.org/pep-0008/) 风格指南
- 使用 `black` 进行代码格式化（行宽 88 字符）
- 使用 `ruff` 进行代码检查
- 使用 `mypy` 进行类型检查（严格模式）
- 所有公共函数必须包含 docstring

### 测试要求

- 单元测试覆盖率 ≥ 80%
- 所有新功能必须包含对应的测试用例
- 集成测试验证端到端流程
- 使用 `pytest` 作为测试框架

---

## 路线图

### v0.1.0 — 基础功能 ✅
- [x] 核心命令行接口（含 `--version` 全局选项）
- [x] 工具注册表和搜索（支持 `--tag`、`--category`、`--limit`、`--sort`、`--json`）
- [x] 多安装方式支持（npm/pip/docker/git/binary/auto）
- [x] 多客户端配置管理（Claude/Cursor/Cline/Copilot/VSCode/Windsurf）
- [x] 安装后自动配置到客户端（`--client`）
- [x] 基础安全扫描（支持 `--quick`、`--detailed`、`--json`、`--severity`）
- [x] 无参数扫描所有已安装工具
- [x] 强制重新安装（`--force`）
- [x] 模拟安装（`--dry-run`）
- [x] 配置导出/导入（`--export`、`--import`）
- [x] 配置验证（`--validate`）
- [x] 环境变量支持（`MCP_HUB_CONFIG_DIR`）
- [x] 路径一致性修复（`~/.config/mcp-hub/`）
- [x] npm scope 包名支持（`@org/package`）
- [x] 工具名验证和路径遍历防护
- [x] Rich 表格和彩色输出

### v0.2.0 — 安全扫描增强 🚧

v0.2.0 的目标是在 v0.1.0 已有的静态代码扫描、权限分析、依赖文件解析和安全评分基础上，补齐“可执行的安全决策链路”：安装前能给出更可靠的风险判断，安装后能留下可审计记录，团队可以用配置文件统一约束最低安全要求。

当前 v0.2.0 分支已经加入 OSV 客户端、依赖到漏洞情报映射、离线漏洞库和扫描缓存组件；安全策略配置、安装前门禁、审计日志和完整 CLI 报告增强仍在开发计划中。

#### 开发目标

- [ ] 将安全扫描从“本地启发式评分”升级为“本地规则 + 在线漏洞情报 + 策略判定”的组合模型
- [ ] 在安装、更新、配置变更等关键操作中记录安全审计事件
- [ ] 支持项目级/用户级安全策略配置，允许设置最低分数、阻断高危权限、跳过规则白名单
- [ ] 为未来 v0.3.0 自定义安全规则插件预留稳定的数据结构和接口边界

#### 计划范围

| 模块 | 计划内容 | 输出 |
|------|----------|------|
| `security.py` + v0.2 安全模块 | 增加 OSV 客户端、依赖漏洞归一化、离线漏洞库、扫描缓存失效策略 | 更完整的漏洞扫描基础组件 |
| `installer.py` | 在安装前执行可选安全门禁，阻断低于策略阈值的工具 | 安装前风险提示和阻断结果 |
| `config.py` | 读取安全策略配置，支持默认策略和用户覆盖 | `security_policy` 配置模型 |
| `cli.py` | 扩展 `scan` 输出，新增策略校验结果和审计日志入口 | 更清晰的 CLI 报告 |
| `docs/SECURITY.md` | 同步更新扫描原理、策略示例和漏洞数据源说明 | v0.2.0 安全文档 |
| `tests/` | 覆盖 OSV 查询、离线降级、策略阻断、审计日志和 CLI 输出 | 回归测试和边界测试 |

#### 里程碑拆分

1. **M1：漏洞情报集成**
   - [x] 支持 OSV API 查询 npm、PyPI、Go、Rust 等生态的已知漏洞（组件层）
   - [x] 为网络不可用、API 限流、漏洞库异常提供离线降级路径（组件层）
   - [x] 将漏洞条目统一为 `{id, package, version, severity, cvss, fixed_versions, source}` 结构

2. **M2：安全策略配置**
   - [ ] 支持 `~/.config/mcp-hub/security.toml` 或 hub config 内嵌策略
   - [ ] 支持最低安全分数、阻断权限、允许列表、忽略漏洞 ID
   - [ ] 在 `scan` 和 `install` 中展示策略判定：`allowed` / `warn` / `blocked`

3. **M3：安装前安全门禁**
   - [ ] `mcp-hub install <tool>` 默认执行轻量扫描和策略评估
   - [ ] 对高危权限、严重漏洞、未知来源工具给出明确确认提示
   - [ ] 保留受控逃生口，例如 `--no-scan` 或 `--allow-risk`，并写入审计日志

4. **M4：审计日志**
   - [ ] 记录安装、卸载、更新、配置变更、策略绕过和扫描结果
   - [ ] 日志默认写入 MCP Hub 数据目录，权限保持 `0600`
   - [ ] 日志内容默认脱敏，不记录 API Key、Token、数据库连接串等敏感值

5. **M5：报告和文档**
   - [ ] 增强 `mcp-hub scan --json` 输出，便于 CI/CD 和脚本消费
   - [ ] 在 README 和 `docs/SECURITY.md` 增加策略配置示例
   - [ ] 给出常见风险的处理建议：升级依赖、限制权限、使用隔离安装目录

#### 验收标准

- [ ] 全量测试通过，覆盖率保持在 80% 以上
- [ ] 新增安全策略和漏洞扫描逻辑具备单元测试、离线测试和错误路径测试
- [ ] `mcp-hub scan --json` 输出保持向后兼容，新增字段不破坏现有消费者
- [ ] 网络不可用时扫描不会失败退出，而是降级为本地扫描并给出清晰警告
- [ ] 审计日志不包含明文敏感环境变量或凭证

#### 暂不纳入 v0.2.0

- [ ] 完整动态行为沙箱和系统调用跟踪（延后到 v0.3.0+ 评估）
- [ ] 企业级集中策略管理和合规报表（归入 v0.4.0）
- [ ] 第三方插件市场和自定义扫描规则插件（归入 v0.3.0）

### v0.3.0 — 插件系统 📋
- [ ] 自定义安装器插件
- [ ] 客户端配置适配器插件
- [ ] 自定义安全扫描规则
- [ ] 社区插件市场

### v0.4.0 — 企业版功能 📋
- [ ] 私有注册表支持
- [ ] 团队配置同步
- [ ] 集中式安全策略
- [ ] 审计日志和合规报告
- [ ] SSO 集成

### v1.0.0 — 稳定版 🎯
- [ ] 完整 API 稳定性保证
- [ ] 全面文档和教程
- [ ] 性能优化和缓存策略
- [ ] 社区治理模型

---

## 许可证和致谢

### 许可证

本项目采用 [MIT 许可证](https://opensource.org/licenses/MIT) 开源。

```
MIT License

Copyright (c) 2025 MCP Hub Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 致谢

- [Anthropic](https://www.anthropic.com/) — 发起 MCP 协议
- [Model Context Protocol](https://modelcontextprotocol.io/) — 官方协议规范
- 所有 [贡献者](https://github.com/Yesssssbabe/mcp-hub/graphs/contributors) — 让项目变得更好

---

<p align="center">
  <strong>⭐ 如果 MCP Hub 对你有帮助，请给我们点个 Star！</strong>
</p>

<p align="center">
  <a href="https://github.com/Yesssssbabe/mcp-hub/issues">报告问题</a> •
  <a href="https://github.com/Yesssssbabe/mcp-hub/discussions">讨论区</a> •
  <a href="https://modelcontextprotocol.io/">MCP 官方文档</a>
</p>
