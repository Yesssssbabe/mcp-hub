# MCP Hub 贡献指南

> 感谢你对 MCP Hub 的贡献！本文档将帮助你快速搭建开发环境并参与项目。

---

## 目录

- [开发环境搭建](#开发环境搭建)
- [代码规范](#代码规范)
- [测试要求](#测试要求)
- [PR 模板](#pr-模板)
- [提交消息规范](#提交消息规范)
- [如何添加新 MCP 工具到注册表](#如何添加新-mcp-工具到注册表)
- [常见问题](#常见问题)

---

## 开发环境搭建

### 前置要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.9+ | 运行时环境 |
| Git | 2.30+ | 版本控制 |
| Make | 任意 | 构建工具（可选） |
| Node.js | 18+ | 测试 npm 适配器（可选） |
| Docker | 20+ | 测试 Docker 适配器（可选） |

### 1. 克隆仓库

```bash
git clone https://github.com/Yesssssbabe/mcp-hub.git
cd mcp-hub
```

### 2. 创建虚拟环境

我们推荐使用 `uv` 或 `venv` 管理虚拟环境：

```bash
# 方式一：使用 uv（推荐，速度更快）
uv venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 方式二：使用 venv
python -m venv .venv
source .venv/bin/activate
```

### 3. 安装开发依赖

```bash
# 安装可编辑模式 + 所有开发依赖
pip install -e ".[dev]"

# 或使用 uv
uv pip install -e ".[dev]"
```

这会安装所有运行时依赖和开发工具：pytest、black、ruff、mypy、coverage 等。

### 4. 验证环境

```bash
# 验证 mcp-hub 可以运行
mcp-hub --version

# 运行测试（确保环境正常）
pytest tests/ -v --tb=short
```

### 5. 安装 Git 预提交钩子（推荐）

```bash
# 使用 pre-commit 框架
pre-commit install

# 手动测试钩子
pre-commit run --all-files
```

---

## 代码规范

### 基础规范

本项目遵循 [PEP 8](https://peps.python.org/pep-0008/) 风格指南，并在此基础上使用以下工具确保一致性：

### Black（代码格式化）

- 行宽：**88 字符**（Black 默认）
- 字符串引号：优先使用双引号
- 尾随逗号：启用

```bash
# 格式化整个项目
black src/mcp_hub tests

# 检查但不修改
black --check src/mcp_hub tests
```

### Ruff（代码检查）

Ruff 替代了 flake8、pydocstyle、isort 等多个工具，检查规则包括：

- **E** — pycodestyle 错误
- **F** — Pyflakes 错误
- **I** — isort 导入排序
- **N** — pep8-naming 命名规范
- **W** — pycodestyle 警告
- **UP** — pyupgrade 升级建议
- **B** — flake8-bugbear 潜在 Bug
- **C4** — flake8-comprehensions 推导式优化
- **SIM** — flake8-simplify 简化建议

```bash
# 检查代码
ruff check src/mcp_hub tests

# 自动修复可修复的问题
ruff check --fix src/mcp_hub tests

# 检查导入排序
ruff check --select I src/mcp_hub tests
```

### MyPy（类型检查）

使用严格模式检查类型注解：

```bash
# 类型检查
mypy src/mcp_hub

# 严格模式（推荐）
mypy --strict src/mcp_hub
```

类型注解要求：
- 所有公共函数必须有参数和返回值类型注解
- 使用 `from __future__ import annotations` 启用延迟类型评估
- 复杂类型使用 `typing` 模块（Python < 3.10）或内置类型（Python 3.10+）
- 使用 `Optional[X]` 或 `X | None` 表示可选参数

### 命名规范

| 类型 | 命名方式 | 示例 |
|------|---------|------|
| 模块 | 小写 + 下划线 | `registry.py`, `security_scanner.py` |
| 包 | 小写 + 下划线 | `mcp_hub`, `install_adapters` |
| 类 | 大驼峰 | `RegistryService`, `SecurityReport` |
| 函数 | 小写 + 下划线 | `search_tools`, `calculate_score` |
| 常量 | 全大写 + 下划线 | `DEFAULT_TIMEOUT`, `MAX_RESULTS` |
| 变量 | 小写 + 下划线 | `tool_name`, `install_result` |
| 私有 | 前缀下划线 | `_internal_cache`, `_validate_input` |
| 抽象 | 前缀 `Abstract` 或后缀 `Protocol` | `AbstractAdapter`, `InstallProtocol` |

### 文档字符串规范

所有公共模块、类、方法必须包含 Google 风格的文档字符串：

```python
def install_tool(
    tool: ToolInfo,
    method: str = "auto",
    clients: list[str] | None = None,
) -> InstallResult:
    """安装 MCP 工具到指定客户端。

    Args:
        tool: 要安装的工具信息。
        method: 安装方式，可选值为 "auto", "npm", "pip", "docker", "git", "binary"。
            默认为 "auto"，由系统自动选择最佳方式。
        clients: 要配置的目标客户端列表。如果为 None，则配置到默认客户端。

    Returns:
        InstallResult 对象，包含安装状态和详细信息。

    Raises:
        ToolNotFoundError: 当工具在注册表中未找到时。
        InstallationError: 当安装过程失败时。
        UnsupportedMethodError: 当指定的安装方式不受支持时。

    Examples:
        >>> result = install_tool(tool_info, method="npm", clients=["claude"])
        >>> result.success
        True
    """
    ...
```

### 导入排序规范

使用 `isort` 风格（通过 Ruff 实现）：

```python
# 标准库
import os
import sys
from pathlib import Path
from typing import Any

# 第三方库
import pytest
import requests
from rich.console import Console
from typer import Argument, Option

# 本地模块
from mcp_hub.config import ConfigService
from mcp_hub.models import ToolInfo
from mcp_hub.utils import format_output
```

---

## 测试要求

### 测试框架

使用 **pytest** 作为测试框架，配合以下插件：

| 插件 | 用途 |
|------|------|
| pytest | 核心测试框架 |
| pytest-cov | 覆盖率统计 |
| pytest-asyncio | 异步测试支持 |
| pytest-mock | Mock 支持 |
| pytest-benchmark | 性能基准测试 |
| pytest-xdist | 并行测试执行 |

### 覆盖率要求

- **整体覆盖率 ≥ 80%**
- **核心模块覆盖率 ≥ 90%**（`registry.py`, `installer.py`, `config.py`, `security.py`）
- **新增代码覆盖率 ≥ 85%**

```bash
# 运行所有测试
pytest

# 带覆盖率报告
pytest --cov=mcp_hub --cov-report=term-missing

# HTML 覆盖率报告
pytest --cov=mcp_hub --cov-report=html
open htmlcov/index.html

# 并行测试（加速）
pytest -n auto

# 特定测试文件
pytest tests/test_installer.py -v

# 特定测试用例
pytest tests/test_installer.py::test_npm_install -v
```

### 测试目录结构

```
tests/
├── conftest.py              # 共享 fixture 和配置
├── unit/                    # 单元测试
│   ├── test_cli.py
│   ├── test_registry.py
│   ├── test_installer.py
│   ├── test_config.py
│   ├── test_security.py
│   └── test_utils.py
├── integration/             # 集成测试
│   ├── test_install_flow.py
│   ├── test_config_flow.py
│   └── test_end_to_end.py
├── fixtures/                # 测试数据和 Mock
│   ├── mock_tools.json
│   ├── mock_configs/
│   └── sample_packages/
└── benchmark/               # 性能测试
    └── test_performance.py
```

### 测试编写规范

1. **测试函数命名**：`test_<被测函数>_<场景>_<期望结果>`

```python
def test_install_tool_npm_success():
    """测试 npm 安装成功场景"""
    ...

def test_install_tool_not_found_raises_error():
    """测试工具未找到时抛出异常"""
    ...

def test_search_with_empty_query_returns_all():
    """测试空查询返回所有工具"""
    ...
```

2. **使用 fixture 共享资源**：

```python
@pytest.fixture
def mock_registry():
    """提供 mock 注册表"""
    return MockRegistry(tools=[
        ToolInfo(id="test-tool", name="Test Tool"),
    ])

@pytest.fixture
def temp_config_dir(tmp_path):
    """提供临时配置目录"""
    return tmp_path / "config"

def test_search(mock_registry, temp_config_dir):
    service = RegistryService(cache_dir=temp_config_dir)
    ...
```

3. **使用 parametrize 测试多组参数**：

```python
@pytest.mark.parametrize("method,expected_adapter", [
    ("npm", NpmAdapter),
    ("pip", PipAdapter),
    ("docker", DockerAdapter),
])
def test_installer_selects_correct_adapter(method, expected_adapter):
    installer = InstallerService()
    adapter = installer._get_adapter(method)
    assert isinstance(adapter, expected_adapter)
```

4. **Mock 外部依赖**：

```python
def test_install_calls_npm(mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    installer = NpmAdapter()
    installer.install(mock_tool)
    mock_subprocess.assert_called_once()
```

### 测试检查清单

提交 PR 前，请确保：

- [ ] 所有测试通过：`pytest` ✅
- [ ] 覆盖率达标：`pytest --cov` 显示 ≥ 80%
- [ ] 新功能有对应测试
- [ ] Bug 修复有回归测试
- [ ] 测试文档字符串清晰描述测试目的
- [ ] 没有使用 `sleep` 或 `time.sleep` 进行等待（使用 `pytest` 的异步等待机制）

---

## PR 模板

提交 PR 时请使用以下模板：

```markdown
## 描述

简要描述这个 PR 做了哪些更改。

Fixes # (issue 编号)

## 更改类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 破坏性变更
- [ ] 文档更新
- [ ] 性能优化
- [ ] 代码重构

## 测试

- [ ] 新增测试用例
- [ ] 所有现有测试通过
- [ ] 覆盖率 ≥ 80%

## 检查清单

- [ ] 代码遵循项目代码规范（black, ruff, mypy）
- [ ] 文档已更新（如适用）
- [ ] CHANGELOG 已更新（如适用）
- [ ] PR 标题清晰描述更改内容

## 截图/日志（如适用）

提供相关截图或日志输出。
```

### PR 审查流程

1. **自动化检查**：CI 必须全部通过（测试、lint、类型检查）
2. **代码审查**：至少 1 名维护者审查批准
3. **文档审查**：如涉及用户可见变更，需文档审查
4. **合并**：由维护者合并到 `main` 分支

---

## 提交消息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### 类型（Type）

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(installer): 支持 pip 安装方式` |
| `fix` | Bug 修复 | `fix(config): 修复 Claude 配置路径检测` |
| `docs` | 文档更新 | `docs(readme): 更新安装说明` |
| `style` | 代码格式（不影响功能） | `style(cli): 格式化输出` |
| `refactor` | 代码重构 | `refactor(registry): 优化搜索算法` |
| `perf` | 性能优化 | `perf(cache): 减少注册表同步时间` |
| `test` | 测试相关 | `test(security): 添加安全扫描测试` |
| `chore` | 构建/工具 | `chore(deps): 更新依赖版本` |
| `ci` | CI/CD 配置 | `ci(github): 添加自动发布流程` |
| `revert` | 回滚 | `revert: 回滚 feat 安装器更改` |

### 作用域（Scope）

可选，表示修改的模块：

- `cli` — 命令行接口
- `registry` — 注册表服务
- `installer` — 安装服务
- `config` — 配置服务
- `security` — 安全扫描
- `tester` — 测试环境
- `docs` — 文档
- `deps` — 依赖

### 示例

```bash
# 新功能
feat(installer): 添加 Docker 安装方式支持

# 修复 Bug
fix(config): 修复 Windows 上配置路径解析错误

Closes #123

# 破坏性变更
feat(security): 安全扫描默认启用

BREAKING CHANGE: 安装工具时现在默认执行安全扫描，
可通过 --no-scan 选项禁用。

# 文档
docs(contributing): 添加测试编写指南
```

---

## 如何添加新 MCP 工具到注册表

### 方式一：通过 Issue 提交（推荐）

1. 创建新 Issue，选择 "Tool Submission" 模板
2. 填写工具信息：
   - 工具名称和标识符
   - 描述和分类
   - 安装方式（npm/pip/docker/git）
   - GitHub 仓库地址
   - 维护者信息
   - 权限声明

### 方式二：直接编辑注册表（PR 方式）

如果你熟悉项目结构，可以直接提交 PR 修改 `registry/tools.json`：

1. **Fork 仓库** 并创建分支：`git checkout -b registry/add-<tool-name>`

2. **编辑 `registry/tools.json`**，添加工具条目：

```json
{
  "tools": [
    {
      "id": "server-filesystem",
      "name": "Filesystem Server",
      "description": "提供安全的文件系统访问能力",
      "publisher": "modelcontextprotocol",
      "version": "1.0.0",
      "category": "filesystem",
      "tags": ["filesystem", "files", "io"],
      "installation": {
        "npm": {
          "package": "@modelcontextprotocol/server-filesystem",
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem"]
        },
        "docker": {
          "image": "mcp/filesystem",
          "command": "docker",
          "args": ["run", "-i", "--rm", "mcp/filesystem"]
        }
      },
      "permissions": [
        "filesystem:read",
        "filesystem:write"
      ],
      "homepage": "https://github.com/modelcontextprotocol/servers",
      "license": "MIT",
      "maintainers": ["@anthropic"]
    }
  ]
}
```

3. **验证格式**：

```bash
python scripts/validate_registry.py
```

4. **提交 PR**：使用标题 `registry: add <tool-name>`

### 工具条目字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 唯一标识符，使用 kebab-case |
| `name` | ✅ | 显示名称 |
| `description` | ✅ | 简短描述（< 200 字符） |
| `publisher` | ✅ | 发布者/组织 |
| `version` | ✅ | 当前版本 |
| `category` | ✅ | 分类（见下方） |
| `tags` | ✅ | 标签数组（3-10 个） |
| `installation` | ✅ | 安装方式配置 |
| `permissions` | ✅ | 权限声明列表 |
| `homepage` | ❌ | 项目主页 |
| `repository` | ❌ | GitHub 仓库地址 |
| `license` | ❌ | 许可证 |
| `maintainers` | ❌ | 维护者列表 |
| `security_score` | ❌ | 安全评分（由系统计算） |

### 分类列表

- `filesystem` — 文件系统
- `database` — 数据库
- `web` — 网络/Web API
- `development` — 开发工具
- `communication` — 通信/消息
- `productivity` — 生产力工具
- `search` — 搜索/索引
- `ai` — AI/ML 服务
- `monitoring` — 监控/日志
- `cloud` — 云服务
- `other` — 其他

### 权限声明

- `filesystem:read` — 读取文件
- `filesystem:write` — 写入文件
- `filesystem:execute` — 执行文件
- `network` — 网络访问
- `network:internet` — 互联网访问
- `network:local` — 本地网络访问
- `code_execution` — 代码执行
- `shell` — Shell 命令执行
- `database:read` — 数据库读取
- `database:write` — 数据库写入
- `memory` — 访问进程内存
- `environment` — 读取环境变量

---

## 常见问题

### Q: 如何运行单个测试文件？

```bash
pytest tests/unit/test_installer.py -v
```

### Q: 如何调试测试失败？

```bash
# 使用 --pdb 在失败时进入调试器
pytest tests/test_installer.py --pdb

# 使用 -s 显示 print 输出
pytest tests/test_installer.py -s
```

### Q: 我的代码通过了测试，但 lint 失败了？

```bash
# 一键修复所有可自动修复的问题
make fix

# 或手动运行
ruff check --fix src/mcp_hub tests
black src/mcp_hub tests
```

### Q: 如何添加新的客户端支持？

1. 在 `src/mcp_hub/config_adapters/` 创建新的适配器文件
2. 继承 `ClientConfigAdapter` 接口
3. 在 `ConfigService` 中注册
4. 添加测试和文档
5. 提交 PR

详见 [ARCHITECTURE.md](ARCHITECTURE.md) 的扩展点设计部分。

### Q: 贡献者的代码会被谁审查？

所有 PR 由项目维护者审查。核心维护者包括：

- @maintainer-1 — 核心架构和 CLI
- @maintainer-2 — 安装器和适配器
- @maintainer-3 — 安全扫描和注册表

---

*如有其他问题，请在 [GitHub Discussions](https://github.com/Yesssssbabe/mcp-hub/discussions) 中提问。*
