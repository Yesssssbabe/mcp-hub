# MCP Hub 🔧

> MCP 生态的 "npm + Homebrew" — 发现、安装、管理 MCP 工具的一站式平台

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

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

**MCP Hub** 正是为解决这些问题而生。它提供了一站式的 MCP 工具发现、安装、配置和管理体验，让开发者可以在几秒钟内将任意 MCP 工具集成到自己的工作流中。

### 核心价值和定位

MCP Hub 的定位是 **MCP 生态的 "npm + Homebrew"** — 一个集包管理器、注册表、安全扫描和配置工具于一体的平台：

| 类比 | 功能对应 |
|------|----------|
| npm Registry | MCP Hub Registry — 收录和索引所有 MCP 工具 |
| `npm install` | `mcp-hub install` — 一键安装任意 MCP 工具 |
| `package.json` | `mcp-hub config` — 统一管理客户端配置 |
| `npm audit` | `mcp-hub scan` — 安全扫描与风险评估 |
| Homebrew Cask | `mcp-hub search` — 发现新工具 |

---

## 功能特性

- ✅ **MCP 工具发现与搜索** — 支持按名称、标签、类别、关键词智能搜索
- ✅ **一键安装** — 支持 npm、pip、Docker、git、binary 等多种安装方式
- ✅ **多客户端配置** — 自动适配 Claude、Cursor、Cline、Copilot、VSCode、Windsurf 等客户端
- ✅ **安全扫描与评分** — 静态代码分析 + 动态权限检测，提供 0-100 安全评分
- ✅ **工具版本管理** — 支持安装、更新、回滚、锁定版本
- ✅ **本地测试环境** — 内置 MCP 工具测试沙箱，无需连接真实客户端即可验证功能
- ✅ **跨平台支持** — 原生支持 macOS、Windows、Linux 三大平台
- ✅ **插件扩展系统** — 支持自定义安装器和配置适配器（v0.3.0+）
- ✅ **批量操作** — 支持批量安装、更新、扫描，提升效率
- ✅ **离线缓存** — 本地缓存注册表数据和工具包，支持离线环境使用

---

## 快速开始

### 安装

```bash
# 使用 pip 安装（推荐）
pip install mcp-hub

# 或使用 uv
uv tool install mcp-hub

# 验证安装
mcp-hub --version
```

### 初始化配置

```bash
# 首次使用，初始化配置目录和默认注册表
mcp-hub init
```

初始化后，MCP Hub 会在你的用户目录下创建配置文件夹：

- **macOS/Linux**: `~/.config/mcp-hub/`
- **Windows**: `%APPDATA%\mcp-hub\`

### 搜索工具

```bash
# 搜索文件系统相关工具
mcp-hub search filesystem

# 按标签搜索
mcp-hub search --tag database

# 限制结果数量
mcp-hub search --limit 10 --sort downloads
```

### 安装工具

```bash
# 安装文件系统工具，并自动配置到 Claude Desktop
mcp-hub install @modelcontextprotocol/server-filesystem --client claude

# 使用 Docker 方式安装
mcp-hub install @modelcontextprotocol/server-filesystem --method docker

# 强制重新安装
mcp-hub install @modelcontextprotocol/server-filesystem --force
```

### 查看已安装工具

```bash
# 列出所有已安装工具
mcp-hub list --installed

# 按类别筛选
mcp-hub list --category filesystem
```

### 安全扫描

```bash
# 扫描工具安全评分
mcp-hub scan @modelcontextprotocol/server-filesystem

# 获取详细扫描报告
mcp-hub scan @modelcontextprotocol/server-filesystem --detailed
```

---

## 详细命令参考

### `mcp-hub init`

初始化 MCP Hub 工作目录和默认配置。

```bash
mcp-hub init [OPTIONS]

Options:
  --force       强制重新初始化，覆盖现有配置
  --client      指定默认客户端（claude|cursor|cline|copilot|vscode|windsurf）
  --config-dir  自定义配置目录路径
```

**示例：**

```bash
# 标准初始化
mcp-hub init

# 设置默认客户端为 Cursor
mcp-hub init --client cursor

# 使用自定义配置目录
mcp-hub init --config-dir /path/to/custom/config
```

---

### `mcp-hub search <query>`

在 MCP Hub 注册表中搜索工具。

```bash
mcp-hub search <query> [OPTIONS]

Arguments:
  query         搜索关键词（支持模糊匹配）

Options:
  --tag TEXT      按标签筛选（可多次使用）
  --category      按类别筛选
  --limit INT     结果数量限制（默认 20）
  --sort TEXT     排序方式：relevance|downloads|stars|updated|name
  --json          以 JSON 格式输出
  --installed     仅搜索已安装工具
```

**示例：**

```bash
# 搜索文件系统工具
mcp-hub search filesystem

# 搜索数据库工具，按下载量排序
mcp-hub search --tag database --sort downloads --limit 10

# 搜索已安装的 Git 相关工具
mcp-hub search git --installed

# JSON 输出（供脚本使用）
mcp-hub search filesystem --json | jq '.[].name'
```

---

### `mcp-hub install <tool>`

安装 MCP 工具并可选配置到指定客户端。

```bash
mcp-hub install <tool> [OPTIONS]

Arguments:
  tool          工具名称或标识符（如 @modelcontextprotocol/server-filesystem）

Options:
  --method TEXT    安装方式：npm|pip|docker|git|binary|auto（默认 auto）
  --client TEXT    目标客户端（可多次使用，支持 claude|cursor|cline|copilot|vscode|windsurf）
  --force          强制重新安装（覆盖现有版本）
  --version TEXT   指定版本号
  --no-config      不自动配置到客户端
  --dry-run        模拟安装，不执行实际操作
```

**示例：**

```bash
# 自动安装到 Claude
mcp-hub install @modelcontextprotocol/server-filesystem --client claude

# 使用 pip 安装到多个客户端
mcp-hub install mcp-server-sqlite --method pip --client claude --client cursor

# 安装特定版本
mcp-hub install @modelcontextprotocol/server-filesystem --version 1.2.0

# 仅安装不配置
mcp-hub install @modelcontextprotocol/server-filesystem --no-config

# 模拟安装（预览操作）
mcp-hub install @modelcontextprotocol/server-filesystem --dry-run
```

---

### `mcp-hub remove <tool>`

卸载已安装的 MCP 工具。

```bash
mcp-hub remove <tool> [OPTIONS]

Arguments:
  tool          工具名称或标识符

Options:
  --purge           彻底删除，包括配置和数据文件
  --keep-config     保留客户端配置文件
  --yes             跳过确认提示
```

**示例：**

```bash
# 卸载工具
mcp-hub remove @modelcontextprotocol/server-filesystem

# 彻底删除（含配置）
mcp-hub remove @modelcontextprotocol/server-filesystem --purge

# 静默卸载
mcp-hub remove @modelcontextprotocol/server-filesystem --yes
```

---

### `mcp-hub list`

列出注册表中的工具或已安装的工具。

```bash
mcp-hub list [OPTIONS]

Options:
  --installed       仅列出已安装工具
  --category TEXT   按类别筛选
  --tag TEXT        按标签筛选
  --json            以 JSON 格式输出
  --outdated        仅列出有更新可用的工具
```

**示例：**

```bash
# 列出所有已安装工具
mcp-hub list --installed

# 列出文件系统类别工具
mcp-hub list --category filesystem

# 列出可更新的工具
mcp-hub list --outdated
```

---

### `mcp-hub config`

管理客户端配置。

```bash
mcp-hub config [OPTIONS]

Options:
  --client TEXT     指定客户端（claude|cursor|cline|copilot|vscode|windsurf）
  --list            列出所有客户端配置
  --show            显示当前配置详情
  --edit            打开配置文件编辑器
  --export PATH     导出配置到文件
  --import PATH     从文件导入配置
  --validate        验证配置格式
```

**示例：**

```bash
# 列出所有客户端配置
mcp-hub config --list

# 查看 Claude 配置详情
mcp-hub config --client claude --show

# 导出配置备份
mcp-hub config --export ./mcp-backup.json

# 导入配置
mcp-hub config --import ./mcp-backup.json

# 验证配置格式
mcp-hub config --validate
```

---

### `mcp-hub scan <tool>`

对 MCP 工具进行安全扫描。

```bash
mcp-hub scan <tool> [OPTIONS]

Arguments:
  tool          工具名称或标识符（留空扫描所有已安装）

Options:
  --detailed        显示详细扫描报告
  --json            以 JSON 格式输出
  --severity TEXT   最低严重级别：info|low|medium|high|critical
```

**示例：**

```bash
# 扫描单个工具
mcp-hub scan @modelcontextprotocol/server-filesystem

# 详细扫描报告
mcp-hub scan @modelcontextprotocol/server-filesystem --detailed

# 扫描所有已安装工具
mcp-hub scan

# 仅显示高危问题
mcp-hub scan --severity high
```

---

### `mcp-hub test <tool>`

在本地测试环境中验证 MCP 工具功能。

```bash
mcp-hub test <tool> [OPTIONS]

Arguments:
  tool          工具名称或标识符

Options:
  --interactive     进入交互式测试模式
  --timeout INT     测试超时时间（秒，默认 30）
  --env TEXT        指定环境变量（key=value，可多次使用）
```

**示例：**

```bash
# 基本功能测试
mcp-hub test @modelcontextprotocol/server-filesystem

# 交互式测试
mcp-hub test @modelcontextprotocol/server-filesystem --interactive

# 带环境变量测试
mcp-hub test mcp-server-db --env DATABASE_URL=sqlite:///test.db
```

---

### `mcp-hub info <tool>`

查看 MCP 工具的详细信息。

```bash
mcp-hub info <tool> [OPTIONS]

Arguments:
  tool          工具名称或标识符

Options:
  --readme          显示完整 README
  --versions        显示可用版本列表
  --dependencies    显示依赖关系
```

**示例：**

```bash
# 查看工具基本信息
mcp-hub info @modelcontextprotocol/server-filesystem

# 查看所有版本
mcp-hub info @modelcontextprotocol/server-filesystem --versions
```

---

### `mcp-hub update [tool]`

更新已安装的 MCP 工具。

```bash
mcp-hub update [tool] [OPTIONS]

Arguments:
  tool          工具名称（留空更新所有）

Options:
  --all             更新所有已安装工具
  --force           强制更新（即使版本相同）
  --dry-run         预览更新，不执行
  --client TEXT     同时更新客户端配置
```

**示例：**

```bash
# 更新指定工具
mcp-hub update @modelcontextprotocol/server-filesystem

# 更新所有工具
mcp-hub update --all

# 预览更新
mcp-hub update --all --dry-run
```

---

## 配置指南

### 各客户端配置路径

MCP Hub 会自动检测并管理以下客户端的 MCP 配置：

| 客户端 | 配置文件路径 |
|--------|-------------|
| **Claude Desktop** | `~/.config/claude/claude_desktop_config.json` (macOS/Linux) <br> `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |
| **Cursor** | `~/.cursor/mcp.json` (macOS/Linux) <br> `%USERPROFILE%\.cursor\mcp.json` (Windows) |
| **Cline** | `~/.config/cline/mcp.json` (macOS/Linux) <br> `%APPDATA%\Cline\mcp.json` (Windows) |
| **GitHub Copilot** | VSCode 设置中的 `github.copilot.mcp` 配置 |
| **VSCode** | `.vscode/mcp.json` 或用户设置 |
| **Windsurf** | `~/.config/windsurf/mcp.json` (macOS/Linux) <br> `%APPDATA%\Windsurf\mcp.json` (Windows) |

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

### 导出/导入配置

```bash
# 导出当前所有配置到文件
mcp-hub config --export ./mcp-config-backup.json

# 从文件导入配置（合并模式）
mcp-hub config --import ./mcp-config-backup.json

# 导出特定客户端配置
mcp-hub config --client claude --export ./claude-mcp.json
```

### 环境变量配置

MCP Hub 支持以下环境变量：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MCP_HUB_CONFIG_DIR` | 配置目录路径 | `~/.config/mcp-hub/` |
| `MCP_HUB_REGISTRY_URL` | 自定义注册表 URL | 内置注册表 |
| `MCP_HUB_CACHE_DIR` | 缓存目录路径 | `~/.cache/mcp-hub/` |
| `MCP_HUB_LOG_LEVEL` | 日志级别 | `INFO` |
| `MCP_HUB_DEFAULT_CLIENT` | 默认客户端 | 无 |
| `MCP_HUB_NO_COLOR` | 禁用彩色输出 | `false` |
| `MCP_HUB_VERIFY_SSL` | 验证 SSL 证书 | `true` |

---

## 安全说明

### 安全评分系统

MCP Hub 为每个工具提供 0-100 分的安全评分，基于以下维度：

| 维度 | 权重 | 说明 |
|------|------|------|
| **代码来源** | 25% | 官方维护 vs 社区贡献 vs 未知来源 |
| **权限范围** | 30% | 文件系统、网络、代码执行等权限的广度 |
| **依赖安全** | 20% | 第三方依赖的已知漏洞扫描 |
| **代码审查** | 15% | 静态代码分析结果 |
| **社区信任** | 10% | 下载量、Star 数、维护活跃度 |

### 安全等级

- **🟢 90-100**: 极安全 — 官方维护、权限最小化、无已知漏洞
- **🟡 70-89**: 较安全 — 社区维护良好、权限合理
- **🟠 50-69**: 需谨慎 — 权限较广或依赖存在已知问题
- **🔴 0-49**: 高风险 — 代码执行权限、网络访问、或存在严重漏洞

### 权限分析说明

每个 MCP 工具的权限在注册表中被明确标注：

```bash
# 查看工具权限详情
mcp-hub info @modelcontextprotocol/server-filesystem --permissions
```

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
4. **定期审查**：使用 `mcp-hub list --outdated` 检查工具更新
5. **监控日志**：关注工具的运行日志，发现异常行为
6. **限制目录**：文件系统工具应限制到特定工作目录

更多安全信息，请参阅 [SECURITY.md](docs/SECURITY.md)。

---

## 开发指南

### 克隆项目

```bash
git clone https://github.com/your-org/mcp-hub.git
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

# 运行性能测试
pytest tests/ --benchmark-only
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
│   ├── cli.py             # 命令行接口（Click/Typer）
│   ├── registry.py        # 工具注册表（本地 + 远程）
│   ├── installer.py       # 安装管理器（npm/pip/docker/git/binary）
│   ├── config.py          # 配置管理（多客户端适配）
│   ├── security.py        # 安全扫描引擎
│   ├── tester.py          # 本地测试环境
│   ├── models.py          # 数据模型（Pydantic）
│   ├── utils.py           # 工具函数和辅助方法
│   └── constants.py       # 常量和默认值
├── tests/
│   ├── unit/              # 单元测试
│   ├── integration/       # 集成测试
│   ├── fixtures/          # 测试数据和 mock
│   └── conftest.py        # pytest 配置和共享 fixture
├── registry/
│   ├── tools.json         # 内置工具注册表
│   └── categories.json    # 分类定义
├── docs/
│   ├── ARCHITECTURE.md    # 架构设计文档
│   ├── CONTRIBUTING.md    # 贡献指南
│   └── SECURITY.md        # 安全文档
├── scripts/
│   ├── build.py           # 构建脚本
│   └── release.py         # 发布脚本
├── pyproject.toml         # 项目配置和依赖
├── Makefile               # 常用命令快捷方式
└── README.md              # 本文件
```

### 核心模块职责

| 模块 | 职责 |
|------|------|
| `cli.py` | 解析命令行参数，调用各功能模块，格式化输出 |
| `registry.py` | 维护工具元数据索引，支持搜索、查询、缓存 |
| `installer.py` | 封装多种安装方式的统一接口，处理依赖和环境 |
| `config.py` | 适配不同客户端的配置格式，读写配置文件 |
| `security.py` | 静态代码分析、权限提取、漏洞扫描、评分计算 |
| `tester.py` | 启动 MCP 工具进程，验证工具协议兼容性 |

---

## 贡献指南

我们欢迎各种形式的贡献！无论是提交新的 MCP 工具、修复 Bug、改进文档还是提出新功能建议。

### 如何提交 MCP 工具

1. 在 [GitHub Issues](https://github.com/your-org/mcp-hub/issues) 中提交工具收录请求
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
- [x] 核心命令行接口
- [x] 工具注册表和搜索
- [x] 多安装方式支持（npm/pip/docker/git/binary）
- [x] 多客户端配置管理（Claude/Cursor/Cline）
- [x] 基础安全扫描
- [x] 本地测试环境

### v0.2.0 — 安全扫描增强 🚧
- [ ] 动态行为分析沙箱
- [ ] 依赖漏洞数据库集成（Snyk, OSV）
- [ ] 权限变更审计日志
- [ ] 安全策略配置文件

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
- 所有 [贡献者](https://github.com/your-org/mcp-hub/graphs/contributors) — 让项目变得更好

---

<p align="center">
  <strong>⭐ 如果 MCP Hub 对你有帮助，请给我们点个 Star！</strong>
</p>

<p align="center">
  <a href="https://github.com/your-org/mcp-hub/issues">报告问题</a> •
  <a href="https://github.com/your-org/mcp-hub/discussions">讨论区</a> •
  <a href="https://modelcontextprotocol.io/">MCP 官方文档</a>
</p>
