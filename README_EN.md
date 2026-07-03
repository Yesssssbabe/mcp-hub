# MCP Hub 🔧

> MCP Hub - Discover, install, and manage MCP tools with security scanning and multi-client configuration

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

---

## Table of Contents

- [What is MCP Hub?](#what-is-mcp-hub)
- [Features](#features)
- [Quick Start](#quick-start)
- [Command Reference](#command-reference)
- [Configuration Guide](#configuration-guide)
- [Security](#security)
- [Development](#development)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [License & Credits](#license--credits)

---

## What is MCP Hub?

### What is MCP?

**MCP (Model Context Protocol)** is an open protocol initiated by Anthropic to standardize the interaction between AI models and external tools, data sources, and services. Through MCP, AI assistants can safely access file systems, databases, API services, development tools, and more, greatly expanding their capabilities.

### Why MCP Hub?

As the MCP ecosystem rapidly grows, hundreds of MCP tools (also called MCP Servers) have emerged. However, developers face many challenges:

- **Discovery difficulty**: Scattered across GitHub, npm, PyPI, etc., with no unified index
- **Complex installation**: Each tool has different installation methods and configuration formats
- **Tedious configuration**: Manual editing of client config files (Claude, Cursor, Cline, etc.)
- **Security risks**: No quick way to assess permission risks and security levels
- **Version management**: Lack of version control and update mechanisms

**MCP Hub** solves all of these problems. It provides a one-stop MCP tool discovery, installation, configuration, and management experience, allowing developers to integrate any MCP tool into their workflow in seconds.

### Core Positioning

MCP Hub is positioned as the **"npm + Homebrew" of the MCP ecosystem** — a platform that combines package manager, registry, security scanner, and configuration tool:

| Analogy | MCP Hub Feature |
|---------|-----------------|
| npm Registry | MCP Hub Registry — indexes all MCP tools |
| `npm install` | `mcp-hub install` — one-click install any MCP tool |
| `package.json` | `mcp-hub config` — unified client configuration management |
| `npm audit` | `mcp-hub scan` — security scanning and risk assessment |
| Homebrew Cask | `mcp-hub search` — discover new tools |

---

## Features

- ✅ **MCP Tool Discovery & Search** — Smart search by name, tags, categories, keywords
- ✅ **One-Click Installation** — Supports npm, pip, Docker, git, binary, and auto-detection
- ✅ **Multi-Client Configuration** — Auto-adapts to Claude, Cursor, Cline, Copilot, VSCode, Windsurf
- ✅ **Security Scanning & Scoring** — Static code analysis + dynamic permission detection, 0-100 security score
- ✅ **Client Auto-Configuration** — Automatically configure installed tools to specified clients
- ✅ **Cross-Platform Support** — Native support for macOS, Windows, Linux
- ✅ **Environment Variable Support** — `MCP_HUB_CONFIG_DIR` for custom config directory
- ✅ **Rich CLI Output** — Beautiful tables and colored output using Rich
- ✅ **Dry-Run Mode** — Preview installation steps without making changes
- ✅ **Batch Scanning** — Scan all installed tools at once

---

## Quick Start

### Installation

```bash
# Install with pip
pip install mcp-hub

# Or use uv
uv tool install mcp-hub

# Verify installation
mcp-hub --version
```

### Initialize

```bash
# First time use — initialize config directory and default registry
mcp-hub init
```

After initialization, MCP Hub creates a config folder in your user directory:

- **macOS/Linux**: `~/.config/mcp-hub/`
- **Windows**: `%APPDATA%\mcp-hub\`

(Backward compatible with `~/.mcp-hub/` if it exists)

### Search for Tools

```bash
# Search for filesystem-related tools
mcp-hub search filesystem

# Search by tag
mcp-hub search --tag database

# Limit results and sort by downloads
mcp-hub search --limit 10 --sort downloads

# JSON output for scripting
mcp-hub search filesystem --json
```

### Install a Tool

```bash
# Install filesystem tool and auto-configure for Claude
mcp-hub install server-filesystem --client claude

# Install to multiple clients
mcp-hub install server-filesystem --client claude --client cursor

# Use Docker installation method
mcp-hub install server-filesystem --method docker

# Force reinstall
mcp-hub install server-filesystem --force

# Dry run — preview only
mcp-hub install server-filesystem --dry-run
```

### List Installed Tools

```bash
# List all installed tools
mcp-hub list --installed

# Filter by category
mcp-hub list --category filesystem

# JSON output
mcp-hub list --json
```

### Security Scan

```bash
# Scan a single tool
mcp-hub scan server-filesystem

# Detailed scan report
mcp-hub scan server-filesystem --detailed

# JSON output
mcp-hub scan server-filesystem --json

# Scan all installed tools
mcp-hub scan

# Filter by severity level
mcp-hub scan --severity HIGH
```

---

## Command Reference

### `mcp-hub init`

Initialize MCP Hub workspace and default configuration.

```bash
mcp-hub init [OPTIONS]

Options:
  --registry PATH    Custom registry path
  --config PATH      Custom config path
  --force            Force reinitialize, overwrite existing config
  --config-dir PATH  Custom configuration directory
```

**Examples:**

```bash
# Standard initialization
mcp-hub init

# Force reinitialize
mcp-hub init --force

# Use custom config directory
mcp-hub init --config-dir ~/.custom-mcp-hub
```

---

### `mcp-hub search <query>`

Search for tools in the MCP Hub registry.

```bash
mcp-hub search <query> [OPTIONS]

Arguments:
  query         Search query (supports fuzzy matching, defaults to empty string)

Options:
  --tag, --tags TEXT     Filter by tags (comma-separated)
  --category TEXT        Filter by category
  --limit INT            Maximum number of results (default: 20)
  --sort TEXT            Sort by: relevance, stars, name, recent, downloads
  --json                 Output results as JSON
  --registry PATH        Custom registry path
```

**Examples:**

```bash
# Search for filesystem tools
mcp-hub search filesystem

# Search database tools, sorted by downloads
mcp-hub search --tag database --sort downloads --limit 10

# JSON output for scripting
mcp-hub search filesystem --json | jq '.[].name'
```

---

### `mcp-hub install <tool>`

Install an MCP tool from the registry.

```bash
mcp-hub install <tool> [OPTIONS]

Arguments:
  tool          Tool name or identifier (supports @org/package format)

Options:
  --registry PATH        Custom registry path
  --base-dir PATH        Custom installation directory
  --dry-run              Show what would be installed without installing
  --method TEXT          Install method: auto, npm, pip, docker, git, binary (default: auto)
  --force                Force reinstall if already installed
  --client TEXT          Target client to configure (can be used multiple times)
```

**Examples:**

```bash
# Install and auto-configure for Claude
mcp-hub install server-filesystem --client claude

# Install to multiple clients with pip method
mcp-hub install server-sqlite --method pip --client claude --client cursor

# Force reinstall
mcp-hub install server-filesystem --force

# Dry run — preview only
mcp-hub install server-filesystem --dry-run
```

---

### `mcp-hub uninstall <tool>`

Uninstall a previously installed MCP tool.

```bash
mcp-hub uninstall <tool> [OPTIONS]

Arguments:
  tool          Tool name or identifier

Options:
  --base-dir PATH        Custom installation directory
  --yes, -y              Skip confirmation prompt
  --purge                Purge configuration and data after uninstall
```

**Examples:**

```bash
# Uninstall with confirmation
mcp-hub uninstall server-filesystem

# Uninstall without confirmation
mcp-hub uninstall server-filesystem --yes

# Purge completely (including config)
mcp-hub uninstall server-filesystem --purge
```

---

### `mcp-hub list`

List tools from the registry.

```bash
mcp-hub list [OPTIONS]

Options:
  --installed, -i        Show only installed tools
  --category TEXT      Filter by category
  --json               Output as JSON list
  --registry PATH      Custom registry path
```

**Examples:**

```bash
# List all installed tools
mcp-hub list --installed

# List filesystem category tools
mcp-hub list --category filesystem

# JSON output
mcp-hub list --json
```

---

### `mcp-hub config <action>`

Manage MCP client configurations.

```bash
mcp-hub config <action> [OPTIONS]

Arguments:
  action          Action: add, remove, list, show, generate, detect, auto, validate, import, export

Options:
  --client TEXT          Target client (claude, cursor, cline, copilot, vscode, windsurf)
  --tool TEXT            Tool name (for auto action)
  --config PATH          Custom config path
  --name TEXT            Server name (for add/remove)
  --command TEXT         Command path (for add)
  --args TEXT            Comma-separated arguments (for add)
  --env KEY=VALUE        Environment variable (can be used multiple times)
  --import PATH          Import configuration from file (import action)
  --export PATH          Export configuration to file (export action)
```

**Examples:**

```bash
# List all client configurations
mcp-hub config list

# Add server configuration
mcp-hub config add --client claude --name filesystem --command /usr/bin/npx --args "-y,@modelcontextprotocol/server-filesystem"

# Add with environment variables
mcp-hub config add --client claude --name postgres --command npx --env DATABASE_URL=postgres://localhost/db

# Remove server configuration
mcp-hub config remove --client claude --name filesystem

# Generate MCP JSON config
mcp-hub config generate --client claude

# Show current configuration
mcp-hub config show

# Validate configuration
mcp-hub config validate --client claude

# Export configuration
mcp-hub config export --client claude --export ./claude-mcp-backup.json

# Import configuration
mcp-hub config import --client claude --import ./claude-mcp-backup.json

# Auto-configure a tool
mcp-hub config auto --client claude --tool server-filesystem

# Detect client configurations
mcp-hub config detect
```

---

### `mcp-hub scan [tool]`

Scan MCP tool(s) for security issues.

```bash
mcp-hub scan [tool] [OPTIONS]

Arguments:
  tool          Tool name (omit to scan all installed tools)

Options:
  --registry PATH        Custom registry path
  --quick, -q            Quick scan mode (score only)
  --detailed, -d         Show detailed scan information
  --json, -j             Output scan results in JSON
  --severity TEXT        Filter by minimum security level (UNKNOWN, LOW, MEDIUM, HIGH, VERIFIED)
```

**Examples:**

```bash
# Scan a single tool
mcp-hub scan server-filesystem

# Detailed scan report
mcp-hub scan server-filesystem --detailed

# Scan all installed tools
mcp-hub scan

# Quick scan
mcp-hub scan server-filesystem --quick

# JSON output
mcp-hub scan server-filesystem --json

# Filter by severity
mcp-hub scan --severity HIGH
```

---

### Global Options

```bash
mcp-hub --version          # Show version and exit
mcp-hub --help             # Show help message
```

---

## Configuration Guide

### Client Config Paths

MCP Hub automatically detects and manages MCP configurations for the following clients:

| Client | Config File Path |
|--------|------------------|
| **Claude Desktop** | `~/.config/claude/claude_desktop_config.json` (macOS/Linux) <br> `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |
| **Cursor** | `~/.cursor/mcp.json` (macOS/Linux) <br> `%APPDATA%\Cursor\mcp.json` (Windows) |
| **Cline** | `~/.config/cline/mcp.json` (macOS/Linux) <br> `%APPDATA%\Cline\mcp.json` (Windows) |
| **GitHub Copilot** | VSCode settings `github.copilot.mcp` config |
| **VSCode** | `~/.vscode/mcp.json` (macOS/Linux) <br> `%APPDATA%\Code\User\mcp.json` (Windows) |
| **Windsurf** | `~/.config/windsurf/mcp.json` (macOS/Linux) <br> `%APPDATA%\Windsurf\mcp.json` (Windows) |

### Manual Configuration

If you need to manually edit configurations, MCP Hub uses the standard MCP configuration format:

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

### Export/Import Configuration

```bash
# Export current configuration to file
mcp-hub config export --client claude --export ./mcp-config-backup.json

# Import configuration from file (merge mode)
mcp-hub config import --client claude --import ./mcp-config-backup.json
```

### Environment Variables

MCP Hub supports the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_HUB_CONFIG_DIR` | Configuration directory path | `~/.config/mcp-hub/` (or `~/.mcp-hub/` if exists) |
| `MCP_HUB_TEST_MODE` | Test mode (set to `1` to enable) | None |

---

## Security

### Security Scoring System

MCP Hub provides a 0-100 security score for each tool based on the following dimensions:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| **Permission Scope** | 30% | Breadth of permissions (filesystem, network, code execution, etc.) |
| **Code Analysis** | 35% | Static code analysis results |
| **Dependency Security** | 20% | Known vulnerabilities in third-party dependencies |
| **Network Analysis** | 15% | Network access requirements and risk assessment |

### Security Levels

- **🟢 90-100**: Verified — Official maintenance, minimal permissions, no known vulnerabilities
- **🟡 70-89**: High — Well-maintained community tools, reasonable permissions
- **🟠 50-69**: Medium — Broad permissions or known dependency issues
- **🔴 0-49**: Low/Unknown — Code execution permissions, unrestricted network access, or serious vulnerabilities

### Permission Types

Each MCP tool's permissions are explicitly declared in the registry:

- `filesystem:read` — File read access
- `filesystem:write` — File write access
- `network` — Network access
- `code_execution` — Code execution
- `command:shell` — Shell command execution
- `database` — Database access

### Security Best Practices

1. **Scan before installing**: Always use `mcp-hub scan` to check the security score
2. **Principle of least privilege**: Only install tools you need, avoid overly permissive tools
3. **Isolate environments**: Use Docker or virtual environments for high-risk tools
4. **Regular review**: Use `mcp-hub list --installed` to check installed tools
5. **Monitor logs**: Watch tool runtime logs for anomalous behavior
6. **Restrict directories**: Filesystem tools should be limited to specific working directories

---

## Development

### Clone the Project

```bash
git clone https://github.com/your-org/mcp-hub.git
cd mcp-hub
```

### Install Development Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install development dependencies
pip install -e ".[dev]"

# Or use uv
uv pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=mcp_hub --cov-report=html

# Run specific test file
pytest tests/test_installer.py
```

### Code Style

This project uses the following tools to maintain code quality:

```bash
# Code formatting (black)
black src/mcp_hub tests

# Code linting (ruff)
ruff check src/mcp_hub tests

# Type checking (mypy)
mypy src/mcp_hub

# One-command lint
make lint

# Auto-fix fixable issues
make fix
```

### PR Workflow

1. **Fork** the repository and create a feature branch: `git checkout -b feature/your-feature`
2. **Write code** and ensure all tests and lint checks pass
3. **Update documentation** and CHANGELOG (if applicable)
4. **Submit PR** to `main` branch using the provided PR template
5. **Wait for CI** and maintainer review

---

## Architecture

```
mcp-hub/
├── src/mcp_hub/
│   ├── __init__.py        # Package entry
│   ├── cli.py             # Command-line interface (Typer)
│   ├── registry.py        # Tool registry (local + remote)
│   ├── installer.py       # Installation manager (npm/pip/docker/git/binary)
│   ├── config.py          # Configuration management (multi-client adapters)
│   ├── security.py        # Security scanning engine
│   ├── utils.py           # Utility functions and helpers
│   └── constants.py       # Constants and defaults
├── tests/
│   ├── test_cli.py        # CLI tests
│   ├── test_config.py     # Config tests
│   ├── test_installer.py # Installer tests
│   ├── test_registry.py   # Registry tests
│   ├── test_security.py   # Security tests
│   ├── test_utils.py      # Utility tests
│   └── conftest.py        # Shared fixtures
├── pyproject.toml         # Project configuration and dependencies
├── README.md              # This file (English)
└── README_CN.md           # Chinese version
```

### Core Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Parse command-line arguments, call functional modules, format output |
| `registry.py` | Maintain tool metadata index, support search, query, caching |
| `installer.py` | Unified interface for multiple installation methods, handle dependencies |
| `config.py` | Adapt configuration formats for different clients, read/write config files |
| `security.py` | Static code analysis, permission extraction, vulnerability scanning, scoring |
| `utils.py` | Shared utilities, logging, progress bars, platform detection |

---

## Contributing

We welcome all forms of contribution! Whether submitting new MCP tools, fixing bugs, improving documentation, or suggesting new features.

### How to Submit an MCP Tool

1. Submit a tool inclusion request in [GitHub Issues](https://github.com/your-org/mcp-hub/issues)
2. Or directly edit `registry/tools.json` and submit a PR
3. Tools must include the following information:
   - Name and unique identifier
   - Description and category
   - Installation method (npm/pip/docker/git)
   - Permission declarations
   - Maintainer information

### How to Contribute Code

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for details, including:
- Development environment setup
- Code standards (PEP 8, black, ruff, mypy)
- Testing requirements (coverage > 80%)
- PR templates and commit message conventions

### Code Standards

- Follow [PEP 8](https://peps.python.org/pep-0008/) style guide
- Use `black` for code formatting (line width 100 characters)
- Use `ruff` for code linting
- Use `mypy` for type checking (strict mode)
- All public functions must include docstrings

### Testing Requirements

- Unit test coverage ≥ 80%
- All new features must include corresponding test cases
- Integration tests verify end-to-end workflows
- Use `pytest` as the test framework

---

## License & Credits

### License

This project is open-sourced under the [MIT License](https://opensource.org/licenses/MIT).

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

### Credits

- [Anthropic](https://www.anthropic.com/) — Initiated the MCP protocol
- [Model Context Protocol](https://modelcontextprotocol.io/) — Official protocol specification
- All [contributors](https://github.com/your-org/mcp-hub/graphs/contributors) — Making the project better

---

<p align="center">
  <strong>⭐ If MCP Hub helps you, please give us a Star!</strong>
</p>

<p align="center">
  <a href="https://github.com/your-org/mcp-hub/issues">Report Issues</a> •
  <a href="https://github.com/your-org/mcp-hub/discussions">Discussions</a> •
  <a href="https://modelcontextprotocol.io/">MCP Official Docs</a>
</p>
