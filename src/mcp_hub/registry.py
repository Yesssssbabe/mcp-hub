"""MCP Tool Registry module for managing MCP tool metadata and discovery."""

import os
import json
from datetime import datetime
from typing import List, Optional, Dict

from pydantic import BaseModel, Field

DEFAULT_REGISTRY_PATH = "~/.mcp-hub/registry.json"


class MCPTool(BaseModel):
    """Represents an MCP tool in the registry."""

    name: str = Field(..., description="Unique tool name")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Short description")
    long_description: str = Field("", description="Detailed description")
    version: str = Field("0.1.0", description="Current version")
    author: str = Field(..., description="Author or organization")
    repository: str = Field(..., description="GitHub repository URL")
    homepage: Optional[str] = Field(None, description="Project homepage")
    license: str = Field("MIT", description="License type")

    # Installation info
    install_type: str = Field(..., description="npm, pip, docker, git, binary")
    install_command: str = Field(..., description="Command to install")
    install_args: Optional[Dict] = Field(None, description="Additional install args")

    # Categorization
    tags: List[str] = Field(default_factory=list, description="Tags/categories")
    categories: List[str] = Field(default_factory=list, description="Primary categories")
    language: Optional[str] = Field(None, description="Primary language")

    # Metrics
    stars: int = Field(0, description="GitHub stars")
    forks: int = Field(0, description="GitHub forks")
    downloads: int = Field(0, description="Total downloads")

    # Security
    security_score: Optional[int] = Field(None, description="0-4 security score")
    permissions: List[str] = Field(default_factory=list, description="Required permissions")

    # Metadata
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    is_official: bool = Field(False, description="Official/verified tool")
    is_installed: bool = Field(False, description="Whether installed locally")
    install_path: Optional[str] = Field(None, description="Local install path")

    # MCP specific
    mcp_server_name: Optional[str] = Field(None, description="MCP server name for config")
    mcp_config_template: Optional[Dict] = Field(None, description="MCP config JSON template")
    env_vars: List[str] = Field(default_factory=list, description="Required env vars")

    class Config:
        validate_assignment = True


class Registry:
    """Manages the MCP tool registry."""

    def __init__(self, registry_path: Optional[str] = None):
        self.registry_path = registry_path or os.path.expanduser(DEFAULT_REGISTRY_PATH)
        self.tools: Dict[str, MCPTool] = {}
        self._load()

    def _load(self) -> None:
        """Load registry from disk."""
        if os.path.exists(self.registry_path):
            with open(self.registry_path, encoding="utf-8") as f:
                data = json.load(f)
                for tool_data in data.get("tools", []):
                    tool = MCPTool(**tool_data)
                    self.tools[tool.name] = tool

    def _save(self) -> None:
        """Save registry to disk."""
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        data = {"tools": [tool.model_dump() for tool in self.tools.values()]}
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def search(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        limit: int = 10,
        sort_by: str = "stars",
    ) -> List[MCPTool]:
        """Search tools by query string, tags, or category.

        Supports sorting by: stars, name, recent, downloads.
        """
        results = list(self.tools.values())
        query_lower = query.lower()

        # Filter by query string (matches name, display_name, description, tags)
        if query_lower:
            results = [
                tool
                for tool in results
                if query_lower in tool.name.lower()
                or query_lower in tool.display_name.lower()
                or query_lower in tool.description.lower()
                or any(query_lower in tag.lower() for tag in tool.tags)
                or any(query_lower in cat.lower() for cat in tool.categories)
            ]

        # Filter by tags (all provided tags must be present)
        if tags:
            tags_lower = [t.lower() for t in tags]
            results = [
                tool
                for tool in results
                if all(t in [tag.lower() for tag in tool.tags] for t in tags_lower)
            ]

        # Filter by category (case-insensitive)
        if category:
            cat_lower = category.lower()
            results = [
                tool
                for tool in results
                if any(cat_lower == cat.lower() for cat in tool.categories)
            ]

        # Sort results
        sort_key = sort_by.lower()
        if sort_key == "stars":
            results.sort(key=lambda t: t.stars, reverse=True)
        elif sort_key == "name":
            results.sort(key=lambda t: t.name.lower())
        elif sort_key == "recent":
            results.sort(
                key=lambda t: datetime.fromisoformat(t.updated_at), reverse=True
            )
        elif sort_key == "downloads":
            results.sort(key=lambda t: t.downloads, reverse=True)
        else:
            results.sort(key=lambda t: t.stars, reverse=True)

        return results[:limit]

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a tool by name (alias for get)."""
        return self.get(name)

    def mark_installed(self, name: str, install_path: str, method: str) -> None:
        """Mark a tool as installed."""
        tool = self.tools.get(name)
        if tool:
            tool.is_installed = True
            tool.install_path = install_path
            tool.updated_at = datetime.now().isoformat()
            self._save()

    def mark_uninstalled(self, name: str) -> None:
        """Mark a tool as not installed."""
        tool = self.tools.get(name)
        if tool:
            tool.is_installed = False
            tool.install_path = None
            tool.updated_at = datetime.now().isoformat()
            self._save()

    def list_installed(self) -> List[str]:
        """List names of all installed tools."""
        return [tool.name for tool in self.tools.values() if tool.is_installed]

    def get_install_path(self, name: str) -> Optional[str]:
        """Get installation path for a tool."""
        tool = self.tools.get(name)
        return tool.install_path if tool else None

    def get_install_method(self, name: str) -> Optional[str]:
        """Get install method for a tool."""
        tool = self.tools.get(name)
        return tool.install_type if tool else None

    def is_installed(self, name: str) -> bool:
        """Check if a tool is installed."""
        tool = self.tools.get(name)
        return tool.is_installed if tool else False

    def add(self, tool: MCPTool) -> None:
        """Add a new tool to registry."""
        if tool.name in self.tools:
            raise ValueError(f"Tool '{tool.name}' already exists in registry.")
        tool.updated_at = datetime.now().isoformat()
        self.tools[tool.name] = tool
        self._save()

    def remove(self, name: str) -> None:
        """Remove a tool from registry."""
        if name not in self.tools:
            raise KeyError(f"Tool '{name}' not found in registry.")
        del self.tools[name]
        self._save()

    def list_categories(self) -> List[str]:
        """List all unique categories."""
        categories = set()
        for tool in self.tools.values():
            categories.update(tool.categories)
        return sorted(categories)

    def list_tags(self) -> List[str]:
        """List all unique tags."""
        tags = set()
        for tool in self.tools.values():
            tags.update(tool.tags)
        return sorted(tags)

    def get_installed(self) -> List[MCPTool]:
        """Get all installed tools."""
        return [tool for tool in self.tools.values() if tool.is_installed]

    def update_metrics(
        self, name: str, stars: Optional[int] = None, downloads: Optional[int] = None
    ) -> None:
        """Update tool metrics."""
        tool = self.tools.get(name)
        if not tool:
            raise KeyError(f"Tool '{name}' not found in registry.")
        if stars is not None:
            tool.stars = stars
        if downloads is not None:
            tool.downloads = downloads
        tool.updated_at = datetime.now().isoformat()
        self._save()

    def update_security_score(self, name: str, score: int) -> None:
        """Update security score."""
        if not (0 <= score <= 4):
            raise ValueError("Security score must be between 0 and 4.")
        tool = self.tools.get(name)
        if not tool:
            raise KeyError(f"Tool '{name}' not found in registry.")
        tool.security_score = score
        tool.updated_at = datetime.now().isoformat()
        self._save()

    def update(self, tool: MCPTool) -> None:
        """Update an existing tool in the registry."""
        if tool.name not in self.tools:
            raise KeyError(f"Tool '{tool.name}' not found in registry.")
        tool.updated_at = datetime.now().isoformat()
        self.tools[tool.name] = tool
        self._save()

    def __len__(self) -> int:
        return len(self.tools)

    def __contains__(self, name: str) -> bool:
        return name in self.tools


def _builtin_tools() -> List[MCPTool]:
    """Return the raw built-in MCP tool definitions."""
    return [
        # ─── Browser / Web ──────────────────────────────
        MCPTool(
            name="server-puppeteer",
            display_name="MCP Puppeteer",
            description="Web scraping and browser automation via Puppeteer.",
            long_description="An MCP server implementation that provides browser automation capabilities using Puppeteer. It enables agents to navigate websites, take screenshots, execute JavaScript, and interact with web pages programmatically.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-puppeteer",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-puppeteer",
            tags=["browser", "web", "automation", "scraping", "puppeteer"],
            categories=["Browser", "Web"],
            language="TypeScript",
            stars=3200,
            forks=450,
            downloads=185000,
            security_score=3,
            permissions=["filesystem", "network"],
            is_official=True,
            mcp_server_name="puppeteer",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
            },
        ),
        MCPTool(
            name="browser-use",
            display_name="Browser Use MCP",
            description="AI-driven browser automation and task execution.",
            long_description="A browser automation MCP server that enables AI agents to perform complex web tasks. Supports navigation, form filling, clicking, scrolling, and multi-step workflows.",
            version="1.0.0",
            author="Browser-Use Team",
            repository="https://github.com/browser-use/browser-use",
            homepage="https://browser-use.com/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @browser-use/mcp-server",
            tags=["browser", "automation", "ai", "web"],
            categories=["Browser", "Web"],
            language="TypeScript",
            stars=8400,
            forks=1200,
            downloads=92000,
            security_score=3,
            permissions=["network", "filesystem"],
            mcp_server_name="browser-use",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@browser-use/mcp-server"]
            },
        ),
        MCPTool(
            name="firecrawl",
            display_name="Firecrawl MCP",
            description="Web scraping and data extraction with Firecrawl.",
            long_description="A powerful MCP server for web scraping, crawling, and structured data extraction. Converts any website into clean, structured data for AI consumption.",
            version="1.0.0",
            author="Firecrawl Team",
            repository="https://github.com/mendableai/firecrawl-mcp-server",
            homepage="https://firecrawl.dev/",
            license="MIT",
            install_type="npm",
            install_command="npx -y firecrawl-mcp",
            tags=["browser", "scraping", "crawling", "data"],
            categories=["Browser", "Web"],
            language="TypeScript",
            stars=2100,
            forks=300,
            downloads=45000,
            security_score=3,
            permissions=["network"],
            env_vars=["FIRECRAWL_API_KEY"],
            mcp_server_name="firecrawl",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "firecrawl-mcp"]
            },
        ),
        # ─── Database ─────────────────────────────────────
        MCPTool(
            name="server-postgres",
            display_name="MCP PostgreSQL",
            description="PostgreSQL database integration for MCP.",
            long_description="Official MCP server for PostgreSQL databases. Enables querying, schema inspection, and data manipulation through standardized tool interfaces.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-postgres",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-postgres",
            tags=["database", "postgres", "sql", "data"],
            categories=["Database"],
            language="TypeScript",
            stars=2800,
            forks=380,
            downloads=160000,
            security_score=3,
            permissions=["database"],
            is_official=True,
            mcp_server_name="postgres",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-postgres"],
                "env": {"DATABASE_URL": "${DATABASE_URL}"}
            },
            env_vars=["DATABASE_URL"],
        ),
        MCPTool(
            name="server-sqlite",
            display_name="MCP SQLite",
            description="SQLite database integration for MCP.",
            long_description="Official MCP server for SQLite databases. Provides read and write access to SQLite databases with schema inspection and query execution.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-sqlite",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-sqlite",
            tags=["database", "sqlite", "sql", "data"],
            categories=["Database"],
            language="TypeScript",
            stars=2500,
            forks=320,
            downloads=140000,
            security_score=3,
            permissions=["database"],
            is_official=True,
            mcp_server_name="sqlite",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sqlite"]
            },
        ),
        MCPTool(
            name="server-mongodb",
            display_name="MCP MongoDB",
            description="MongoDB database integration for MCP.",
            long_description="Official MCP server for MongoDB. Enables querying, document manipulation, and collection management through the MCP protocol.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-mongodb",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-mongodb",
            tags=["database", "mongodb", "nosql", "data"],
            categories=["Database"],
            language="TypeScript",
            stars=1800,
            forks=240,
            downloads=85000,
            security_score=3,
            permissions=["database"],
            is_official=True,
            mcp_server_name="mongodb",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-mongodb"],
                "env": {"MONGODB_URL": "${MONGODB_URL}"}
            },
            env_vars=["MONGODB_URL"],
        ),
        # ─── File System ──────────────────────────────────
        MCPTool(
            name="server-filesystem",
            display_name="MCP Filesystem",
            description="Secure file system access for MCP.",
            long_description="Official MCP server providing secure, sandboxed file system access. Allows reading, writing, and directory listing within allowed paths only.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-filesystem",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-filesystem",
            tags=["filesystem", "files", "storage"],
            categories=["File System"],
            language="TypeScript",
            stars=4100,
            forks=580,
            downloads=220000,
            security_score=2,
            permissions=["filesystem"],
            is_official=True,
            mcp_server_name="filesystem",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"]
            },
        ),
        MCPTool(
            name="server-github",
            display_name="MCP GitHub",
            description="GitHub API integration for MCP.",
            long_description="Official MCP server for GitHub. Provides access to repositories, issues, pull requests, and other GitHub resources through standardized tools.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-github",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-github",
            tags=["github", "git", "api", "vcs"],
            categories=["File System", "Development"],
            language="TypeScript",
            stars=5600,
            forks=720,
            downloads=195000,
            security_score=3,
            permissions=["network"],
            is_official=True,
            mcp_server_name="github",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
            },
            env_vars=["GITHUB_TOKEN"],
        ),
        # ─── Search ───────────────────────────────────────
        MCPTool(
            name="server-brave-search",
            display_name="MCP Brave Search",
            description="Brave Search API integration for MCP.",
            long_description="Official MCP server for Brave Search. Enables web search and local search capabilities through the Brave Search API.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-brave-search",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-brave-search",
            tags=["search", "web", "api", "brave"],
            categories=["Search"],
            language="TypeScript",
            stars=1900,
            forks=260,
            downloads=110000,
            security_score=3,
            permissions=["network"],
            is_official=True,
            mcp_server_name="brave-search",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
            },
            env_vars=["BRAVE_API_KEY"],
        ),
        MCPTool(
            name="server-tavily",
            display_name="MCP Tavily",
            description="Tavily AI search API for MCP.",
            long_description="MCP server for Tavily's AI-powered search API. Provides intelligent web search with structured results and source attribution.",
            version="1.0.0",
            author="Tavily",
            repository="https://github.com/tavily-ai/tavily-mcp",
            homepage="https://tavily.com/",
            license="MIT",
            install_type="npm",
            install_command="npx -y tavily-mcp",
            tags=["search", "ai", "web", "api"],
            categories=["Search"],
            language="TypeScript",
            stars=1500,
            forks=200,
            downloads=78000,
            security_score=3,
            permissions=["network"],
            mcp_server_name="tavily",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "tavily-mcp"],
                "env": {"TAVILY_API_KEY": "${TAVILY_API_KEY}"}
            },
            env_vars=["TAVILY_API_KEY"],
        ),
        # ─── AI / LLM ───────────────────────────────────────
        MCPTool(
            name="server-ollama",
            display_name="MCP Ollama",
            description="Local LLM integration via Ollama for MCP.",
            long_description="Official MCP server for Ollama. Enables running local LLMs and embeddings through Ollama's API with full MCP tool support.",
            version="1.0.0",
            author="Ollama Team",
            repository="https://github.com/ollama/mcp-server-ollama",
            homepage="https://ollama.com/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @ollama/mcp-server-ollama",
            tags=["llm", "ai", "local", "ollama"],
            categories=["AI/LLM"],
            language="TypeScript",
            stars=4200,
            forks=550,
            downloads=130000,
            security_score=3,
            permissions=["network"],
            mcp_server_name="ollama",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@ollama/mcp-server-ollama"]
            },
        ),
        MCPTool(
            name="server-chroma",
            display_name="MCP Chroma",
            description="Vector database integration with Chroma for MCP.",
            long_description="MCP server for Chroma vector database. Provides embeddings storage, similarity search, and vector retrieval capabilities for RAG applications.",
            version="1.0.0",
            author="Chroma Team",
            repository="https://github.com/chroma-core/chroma-mcp-server",
            homepage="https://trychroma.com/",
            license="MIT",
            install_type="pip",
            install_command="pip install chroma-mcp-server",
            tags=["vector", "database", "ai", "embeddings", "rag"],
            categories=["AI/LLM", "Database"],
            language="Python",
            stars=3200,
            forks=400,
            downloads=95000,
            security_score=3,
            permissions=["filesystem"],
            mcp_server_name="chroma",
            mcp_config_template={
                "command": "python",
                "args": ["-m", "chroma_mcp_server"]
            },
        ),
        # ─── Development Tools ──────────────────────────────
        MCPTool(
            name="server-git",
            display_name="MCP Git",
            description="Git operations and repository management for MCP.",
            long_description="Official MCP server for Git. Provides tools for repository operations, commit history, branching, and diff analysis.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-git",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-git",
            tags=["git", "vcs", "development", "scm"],
            categories=["Development Tools"],
            language="TypeScript",
            stars=3400,
            forks=460,
            downloads=145000,
            security_score=3,
            permissions=["filesystem"],
            is_official=True,
            mcp_server_name="git",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-git"]
            },
        ),
        MCPTool(
            name="server-memory",
            display_name="MCP Memory",
            description="Persistent memory and knowledge graph for MCP.",
            long_description="Official MCP server providing a knowledge graph-based memory system. Stores entities, relations, and observations for long-term memory across conversations.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-memory",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-memory",
            tags=["memory", "knowledge-graph", "persistence", "ai"],
            categories=["Development Tools", "AI/LLM"],
            language="TypeScript",
            stars=3800,
            forks=500,
            downloads=165000,
            security_score=2,
            permissions=["filesystem"],
            is_official=True,
            mcp_server_name="memory",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"]
            },
        ),
        # ─── Productivity ───────────────────────────────────
        MCPTool(
            name="server-slack",
            display_name="MCP Slack",
            description="Slack workspace integration for MCP.",
            long_description="Official MCP server for Slack. Enables sending messages, reading channels, and managing workspace interactions through MCP tools.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-slack",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-slack",
            tags=["slack", "chat", "messaging", "productivity"],
            categories=["Productivity"],
            language="TypeScript",
            stars=2200,
            forks=310,
            downloads=125000,
            security_score=3,
            permissions=["network"],
            is_official=True,
            mcp_server_name="slack",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-slack"],
                "env": {
                    "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
                    "SLACK_TEAM_ID": "${SLACK_TEAM_ID}"
                }
            },
            env_vars=["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        ),
        MCPTool(
            name="server-notion",
            display_name="MCP Notion",
            description="Notion workspace integration for MCP.",
            long_description="MCP server for Notion. Provides read and write access to pages, databases, and blocks within your Notion workspace.",
            version="1.0.0",
            author="Notion Community",
            repository="https://github.com/makenotion/notion-mcp-server",
            homepage="https://notion.so/",
            license="MIT",
            install_type="npm",
            install_command="npx -y notion-mcp-server",
            tags=["notion", "productivity", "notes", "wiki"],
            categories=["Productivity"],
            language="TypeScript",
            stars=1800,
            forks=250,
            downloads=72000,
            security_score=3,
            permissions=["network"],
            mcp_server_name="notion",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "notion-mcp-server"],
                "env": {"NOTION_API_KEY": "${NOTION_API_KEY}"}
            },
            env_vars=["NOTION_API_KEY"],
        ),
        # ─── Cloud Platform ───────────────────────────────
        MCPTool(
            name="server-aws",
            display_name="MCP AWS",
            description="AWS cloud resource management for MCP.",
            long_description="MCP server for AWS. Provides tools for managing AWS resources including EC2, S3, Lambda, and CloudFormation through standardized interfaces.",
            version="1.0.0",
            author="AWS Community",
            repository="https://github.com/awslabs/mcp-server-aws",
            homepage="https://aws.amazon.com/",
            license="Apache-2.0",
            install_type="npm",
            install_command="npx -y aws-mcp-server",
            tags=["aws", "cloud", "infrastructure", "devops"],
            categories=["Cloud Platform"],
            language="TypeScript",
            stars=2100,
            forks=340,
            downloads=88000,
            security_score=2,
            permissions=["network"],
            mcp_server_name="aws",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "aws-mcp-server"],
                "env": {
                    "AWS_ACCESS_KEY_ID": "${AWS_ACCESS_KEY_ID}",
                    "AWS_SECRET_ACCESS_KEY": "${AWS_SECRET_ACCESS_KEY}",
                    "AWS_REGION": "${AWS_REGION}"
                }
            },
            env_vars=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"],
        ),
        MCPTool(
            name="server-gcp",
            display_name="MCP GCP",
            description="Google Cloud Platform integration for MCP.",
            long_description="MCP server for Google Cloud Platform. Enables management of GCP resources including Compute Engine, Cloud Storage, and BigQuery.",
            version="1.0.0",
            author="Google Cloud Community",
            repository="https://github.com/GoogleCloudPlatform/mcp-server-gcp",
            homepage="https://cloud.google.com/",
            license="Apache-2.0",
            install_type="npm",
            install_command="npx -y gcp-mcp-server",
            tags=["gcp", "google", "cloud", "infrastructure"],
            categories=["Cloud Platform"],
            language="TypeScript",
            stars=1600,
            forks=240,
            downloads=65000,
            security_score=2,
            permissions=["network"],
            mcp_server_name="gcp",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "gcp-mcp-server"],
                "env": {"GOOGLE_APPLICATION_CREDENTIALS": "${GOOGLE_APPLICATION_CREDENTIALS}"}
            },
            env_vars=["GOOGLE_APPLICATION_CREDENTIALS"],
        ),
        # ─── Security ───────────────────────────────────────
        MCPTool(
            name="strix",
            display_name="Strix Security Scanner",
            description="Security vulnerability scanning for MCP.",
            long_description="A security-focused MCP server that performs vulnerability scanning, dependency analysis, and security posture assessment on codebases and dependencies.",
            version="1.0.0",
            author="Strix Security",
            repository="https://github.com/strix-security/strix-mcp",
            homepage="https://strix.security/",
            license="MIT",
            install_type="npm",
            install_command="npx -y strix-mcp",
            tags=["security", "vulnerability", "scanning", "audit"],
            categories=["Security"],
            language="TypeScript",
            stars=850,
            forks=120,
            downloads=28000,
            security_score=3,
            permissions=["filesystem", "network"],
            mcp_server_name="strix",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "strix-mcp"]
            },
        ),
        MCPTool(
            name="vulnclaw",
            display_name="VulnClaw",
            description="Vulnerability detection and remediation for MCP.",
            long_description="An MCP security tool that detects known vulnerabilities in dependencies and suggests remediation steps using CVE databases and security advisories.",
            version="1.0.0",
            author="VulnClaw Team",
            repository="https://github.com/vulnclaw/vulnclaw-mcp",
            homepage="https://vulnclaw.io/",
            license="MIT",
            install_type="pip",
            install_command="pip install vulnclaw-mcp",
            tags=["security", "vulnerability", "cve", "dependencies"],
            categories=["Security"],
            language="Python",
            stars=620,
            forks=90,
            downloads=18000,
            security_score=3,
            permissions=["filesystem", "network"],
            mcp_server_name="vulnclaw",
            mcp_config_template={
                "command": "python",
                "args": ["-m", "vulnclaw_mcp"]
            },
        ),
        # ─── Other / Utility ────────────────────────────────
        MCPTool(
            name="server-fetch",
            display_name="MCP Fetch",
            description="HTTP client and web fetching for MCP.",
            long_description="Official MCP server for HTTP fetching. Provides robust web request capabilities with support for headers, authentication, and various HTTP methods.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-fetch",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-fetch",
            tags=["fetch", "http", "api", "network"],
            categories=["Utility"],
            language="TypeScript",
            stars=2900,
            forks=400,
            downloads=155000,
            security_score=3,
            permissions=["network"],
            is_official=True,
            mcp_server_name="fetch",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-fetch"]
            },
        ),
        MCPTool(
            name="server-sequential-thinking",
            display_name="MCP Sequential Thinking",
            description="Structured reasoning and thought chains for MCP.",
            long_description="Official MCP server that provides structured sequential thinking capabilities. Helps break down complex problems into step-by-step reasoning chains.",
            version="1.0.0",
            author="Anthropic",
            repository="https://github.com/modelcontextprotocol/server-sequential-thinking",
            homepage="https://modelcontextprotocol.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y @modelcontextprotocol/server-sequential-thinking",
            tags=["thinking", "reasoning", "ai", "chain-of-thought"],
            categories=["AI/LLM", "Utility"],
            language="TypeScript",
            stars=2600,
            forks=350,
            downloads=135000,
            security_score=4,
            permissions=[],
            is_official=True,
            mcp_server_name="sequential-thinking",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
            },
        ),
        # ─── Bonus tools ────────────────────────────────────
        MCPTool(
            name="server-sentry",
            display_name="MCP Sentry",
            description="Error tracking and monitoring via Sentry for MCP.",
            long_description="MCP server for Sentry error tracking. Enables querying issues, events, and performance data from Sentry projects.",
            version="1.0.0",
            author="Sentry",
            repository="https://github.com/getsentry/sentry-mcp",
            homepage="https://sentry.io/",
            license="MIT",
            install_type="npm",
            install_command="npx -y sentry-mcp",
            tags=["monitoring", "errors", "sentry", "devops"],
            categories=["Development Tools", "Cloud Platform"],
            language="TypeScript",
            stars=1100,
            forks=170,
            downloads=52000,
            security_score=3,
            permissions=["network"],
            mcp_server_name="sentry",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "sentry-mcp"],
                "env": {"SENTRY_AUTH_TOKEN": "${SENTRY_AUTH_TOKEN}"}
            },
            env_vars=["SENTRY_AUTH_TOKEN"],
        ),
        MCPTool(
            name="server-obsidian",
            display_name="MCP Obsidian",
            description="Obsidian vault integration for MCP.",
            long_description="MCP server for Obsidian. Provides read and write access to notes, links, and graph data within your Obsidian vault.",
            version="1.0.0",
            author="Obsidian Community",
            repository="https://github.com/coinbase/obsidian-mcp",
            homepage="https://obsidian.md/",
            license="MIT",
            install_type="npm",
            install_command="npx -y obsidian-mcp",
            tags=["obsidian", "notes", "knowledge", "productivity"],
            categories=["Productivity"],
            language="TypeScript",
            stars=1400,
            forks=200,
            downloads=48000,
            security_score=2,
            permissions=["filesystem"],
            mcp_server_name="obsidian",
            mcp_config_template={
                "command": "npx",
                "args": ["-y", "obsidian-mcp"]
            },
        ),
    ]


def load_builtin_registry() -> List[MCPTool]:
    """Load the built-in registry with popular MCP tools."""
    return _builtin_tools()
