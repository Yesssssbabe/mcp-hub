import os
import re
import json
import time
import sys
import ast

import importlib.util
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set, Union
from filelock import FileLock
from dataclasses import dataclass, field, asdict
from enum import IntEnum

from mcp_hub.constants import (
    SecurityError, SECURITY_LEVELS, DEFAULT_DATA_DIR
)
from mcp_hub.registry import Registry, MCPTool

logger = logging.getLogger(__name__)

# Optional parser libraries — prefer standard/specialized parsers over regex
# packaging: lazy-loaded on first use to avoid import overhead
_Requirement = None

def _get_requirement_class():
    """Lazy-load and cache packaging.requirements.Requirement."""
    global _Requirement
    if _Requirement is None:
        try:
            from packaging.requirements import Requirement
            _Requirement = Requirement
        except ImportError:  # pragma: no cover
            _Requirement = False
    return _Requirement


class SecurityLevel(IntEnum):
    """Security maturity levels for MCP tools."""
    UNKNOWN = 0
    LOW = 1      # 基本安全检查通过
    MEDIUM = 2   # 静态分析通过，无高危漏洞
    HIGH = 3     # 代码审计通过，权限合理
    VERIFIED = 4 # 官方验证，签名完整
    CRITICAL = 5 # 显式高危，触发 Tier 1 封顶


@dataclass
class SecurityReport:
    """Security analysis report for an MCP tool."""
    tool_name: str
    overall_score: int  # 0-100
    security_level: SecurityLevel
    
    # Analysis results
    permissions_analysis: Dict[str, Any] = field(default_factory=dict)
    code_analysis: Dict[str, Any] = field(default_factory=dict)
    dependency_analysis: Dict[str, Any] = field(default_factory=dict)
    network_analysis: Dict[str, Any] = field(default_factory=dict)
    
    # Findings
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Metadata
    status: str = "scanned"
    scanned_at: str = field(default_factory=lambda: datetime.now().isoformat())
    scan_duration: float = 0.0
    scanner_version: str = "0.1.0"
    
    def to_dict(self, exclude_none: bool = False) -> Dict:
        d = {
            "tool_name": self.tool_name,
            "overall_score": self.overall_score,
            "security_level": self.security_level.name,
            "status": self.status,
            "permissions_analysis": self.permissions_analysis,
            "code_analysis": self.code_analysis,
            "dependency_analysis": self.dependency_analysis,
            "network_analysis": self.network_analysis,
            "warnings": self.warnings,
            "errors": self.errors,
            "recommendations": self.recommendations,
            "scanned_at": self.scanned_at,
            "scan_duration": self.scan_duration,
            "scanner_version": self.scanner_version,
        }
        if exclude_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d

    def to_json(self, exclude_none: bool = True) -> str:
        return json.dumps(self.to_dict(exclude_none=exclude_none), ensure_ascii=False, indent=2)


class SecurityScanner:
    """Scans MCP tools for security issues and generates comprehensive reports."""
    
    # ─── Risk patterns for static analysis ───────────────────────────────────
    
    RISK_PATTERNS = {
        "filesystem_access": [
            r"\bopen\s*\([^)]*,\s*['\"](w|w\+|a|a\+|x|x\+)['\"]",
            r"\bos\.remove\s*\(",
            r"\bshutil\.(rmtree|move|copy|copytree|copyfile)\b",
            r"\bpathlib\..*\.unlink\s*\(",
            r"\bos\.rmdir\s*\(",
            r"\bos\.mkdir\s*\(",
            r"\bos\.makedirs\s*\(",
            r"\bpathlib\..*\.write_text\s*\(",
            r"\bpathlib\..*\.write_bytes\s*\(",
            r"\bos\.rename\s*\(",
            r"\bos\.replace\s*\(",
            r"\btempfile\.mktemp\s*\(",
            r"\btarfile\.(extractall|extract)\b",
            r"\bzipfile\.(extractall|extract)\b",
        ],
        "network_access": [
            r"\brequests\.(get|post|put|delete|patch|head|options)\b",
            r"\burllib\.request\.(urlopen|urlretrieve|Request)\b",
            r"\bhttp\.client\.(HTTPConnection|HTTPSConnection)\b",
            r"\bsocket\.(socket|create_connection|connect)\b",
            r"\bhttpx\.(get|post|put|delete|patch)\b",
            r"\baiohttp\.(ClientSession|get|post)\b",
            r"\burllib3\.(PoolManager|RequestMethods)\b",
            r"\bwebsocket\.(connect|create_connection)\b",
            r"\bhttplib\.(HTTPConnection|HTTPSConnection)\b",
        ],
        "command_execution": [
            r"\bos\.system\s*\(",
            r"\bos\.(popen|popen2|popen3|popen4)\b",
            r"\bos\.spawn(l|le|lp|v|ve|vp|vpe)\b",
            r"\bos\.exec(l|le|lp|v|ve|vp|vpe)\b",
            r"\bos\.startfile\b",
            r"\bsubprocess\.(call|run|Popen|check_output|check_call)\b",
            r"\beval\s*\(",
            r"\bexec\s*\(",
            r"\bcompile\s*\(",
            r"\bnew\s+Function\s*\(",
            r"\bvm\.(runInContext|runInNewContext|runInThisContext)\b",
            r"\bpickle\.(loads|load)\b",
            r"\bmarshal\.(loads|load)\b",
            r"\byaml\.(load|unsafe_load)\b",
            r"\bgetattr\s*\([^)]*['\"](system|eval|exec|popen|compile)['\"]",
            r"\bsetattr\s*\(",
        ],
        "sensitive_data": [
            r"\bpassword\s*=\s*['\"]",
            r"\btoken\s*=\s*['\"]",
            r"\bapi[_-]?key\s*=\s*['\"]",
            r"\bsecret\s*=\s*['\"]",
            r"\bprivate[_-]?key\s*=\s*['\"]",
            r"\bpasswd\s*=\s*['\"]",
            r"\bauth\s*=\s*['\"]",
            r"\bcredential\s*=\s*['\"]",
            r"\bbearer\s+['\"]",
            r"\bbasic\s+auth\s*=\s*['\"]",
            r"\baws_access_key\s*=\s*['\"]",
            r"\baws_secret_key\s*=\s*['\"]",
            r"\bdatabase_url\s*=\s*['\"]",
            r"\bconnection_string\s*=\s*['\"]",
            r"\bload_dotenv\b",
        ],
        "data_exfiltration": [
            r"\brequests\.(post|put|patch)\s*\(.*\b(json|data|files)\s*=",
            r"\burllib\.request\.urlopen\s*\(.*\bdata\s*=",
            r"\bxmlhttprequest\b",
        ],
        "foreign_function": [
            r"\bctypes\.(CDLL|cdll|windll|pythonapi|PyDLL)\b",
            r"\bcffi\.FFI\b",
            r"\bffi\.dlopen\b",
        ],
        "dynamic_import": [
            r"\bimportlib\.import_module\b",
            r"\bimportlib\.util\.spec_from_file_location\b",
            r"\bimportlib\.util\.module_from_spec\b",
            r"\b__import__\b",
        ],
        "obfuscated_execution": [
            r"\b(eval|exec|compile)\s*\(\s*base64\.(b64decode|decode)",
        ],
        "environment_manipulation": [
            r"\bsys\.path\.(insert|append)\b",
            r"\bos\.environ\s*\[",
            r"\bos\.environ\.(get|setdefault|pop)\b",
        ],
    }
    
    # High-risk permission categories
    HIGH_RISK_PERMISSIONS = {
        "filesystem": {
            "write": "文件写入权限可能导致数据损坏或恶意文件创建",
            "delete": "文件删除权限可能导致数据丢失",
            "execute": "文件执行权限可运行任意代码",
        },
        "network": {
            "outbound": "出站网络连接可能泄露数据或下载恶意内容",
            "inbound": "入站网络连接可能暴露攻击面",
            "raw": "原始网络访问可绕过安全控制",
        },
        "command": {
            "shell": "Shell 命令执行是最高风险操作",
            "process": "进程创建可运行任意程序",
        },
        "system": {
            "root": "Root/管理员权限可完全控制系统",
            "registry": "注册表访问可修改系统配置",
            "kernel": "内核访问可绕过所有安全机制",
        },
    }
    
    # Permission risk severity weights (higher = more dangerous)
    RISK_SEVERITY_WEIGHTS = {
        "command:shell": 50,      # 致命 — 任意代码执行
        "system:root": 45,        # 致命 — 完全控制系统
        "system:kernel": 40,      # 致命 — 内核级访问
        "filesystem:execute": 30,  # 高危 — 可执行任意文件
        "network:outbound": 20,  # 高危 — 出站网络
        "network:raw": 20,       # 高危 — 原始网络
        "command:process": 18,   # 中高危 — 进程创建
        "filesystem:delete": 15, # 中高危 — 文件删除
        "network:inbound": 12,   # 中高危 — 入站网络
        "system:registry": 12,   # 中高危 — 注册表
        "filesystem:write": 12,  # 中高危 — 文件写入
    }
    
    # Score weights
    WEIGHT_PERMISSIONS = 0.30
    WEIGHT_CODE = 0.35
    WEIGHT_DEPENDENCIES = 0.20
    WEIGHT_NETWORK = 0.15
    
    # Risk scoring thresholds
    RISK_THRESHOLD_LOW = 5      # 低于此值为低风险
    RISK_THRESHOLD_MEDIUM = 15  # 低于此值为中风险
    RISK_THRESHOLD_HIGH = 30    # 低于此值为高风险，否则极高
    
    # Supported dependency files
    DEPENDENCY_FILES = {
        "package.json": "npm",
        "requirements.txt": "pip",
        "Cargo.toml": "cargo",
        "go.mod": "go",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "pyproject.toml": "poetry",
        "Pipfile": "pipenv",
        "Gemfile": "bundler",
        "composer.json": "composer",
    }
    
    # Known risky dependency patterns (name: {severity, description})
    RISKY_DEPENDENCIES = {
        "eval-like": {
            "pattern": r"^(eval|exec|unsafe-eval|vm2|sandbox)$",
            "severity": "high",
            "description": "动态代码执行库存在注入风险",
        },
        "serialization": {
            "pattern": r"^(pickle|pyyaml|js-yaml|serialize-javascript)$",
            "severity": "high",
            "description": "不安全的序列化库可能导致反序列化漏洞",
        },
        "network-raw": {
            "pattern": r"^(net|raw-socket|scapy|libpcap)$",
            "severity": "medium",
            "description": "底层网络访问库",
        },
        "crypto-weak": {
            "pattern": r"^(md5|sha1|des|rc4|ssl2|ssl3|tls1\.0)$",
            "severity": "medium",
            "description": "弱加密算法或旧协议",
        },
        "obfuscation": {
            "pattern": r"^(javascript-obfuscator|pyarmor|bytenode)$",
            "severity": "medium",
            "description": "代码混淆可能隐藏恶意行为",
        },
    }
    
    # Maximum files to scan per tool to avoid performance issues
    MAX_FILES_PER_SCAN = 500

    # Security limits for ReDoS/performance protection
    MAX_LINE_LENGTH = 10000           # 10KB per line
    MAX_SCAN_DURATION_SECONDS = 30.0  # 30 seconds total scan time limit
    MAX_DEP_FILE_SIZE = 10 * 1024 * 1024  # 10MB dependency file size limit
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB file size limit
    MAX_ENUMERATED_PATHS = 2000       # limit rglob enumeration
    MAX_LINES_PER_FILE = 50000        # limit lines processed per file
    RE_TIMEOUT = 5.0                  # 5 seconds regex match timeout (Python 3.11+)

    # Concurrent scan limit (file-based cross-process lock)
    _scan_lock_file: Optional[str] = None
    
    # Code file extensions to scan
    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
        ".go", ".rs", ".java", ".kt", ".scala",
        ".c", ".cpp", ".cc", ".h", ".hpp",
        ".rb", ".php", ".sh", ".bash", ".zsh",
        ".ps1", ".pl", ".lua", ".r", ".swift",
    }
    
    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry if registry is not None else Registry()
        self._prerequisites_cache: Optional[Dict[str, bool]] = None
        self._pattern_cache: Dict[Tuple[str, int], re.Pattern] = {}
    
    # ──────────────────────────────────────────────────────────────
    #  Regex Safety Utilities
    # ──────────────────────────────────────────────────────────────

    def _compile_pattern(self, pattern: str, flags: int = 0) -> re.Pattern:
        """Compile and cache regex pattern with optional Python 3.11+ timeout."""
        key = (pattern, flags)
        if key not in self._pattern_cache:
            if sys.version_info >= (3, 11):
                self._pattern_cache[key] = re.compile(pattern, flags, timeout=self.RE_TIMEOUT)
            else:
                self._pattern_cache[key] = re.compile(pattern, flags)
        return self._pattern_cache[key]

    def _safe_search(self, compiled: re.Pattern, text: str) -> Optional[re.Match]:
        """Search with timeout protection, logging on regex timeout."""
        _timeout_err = getattr(re, "TimeoutError", None)
        try:
            if sys.version_info >= (3, 11):
                return compiled.search(text, timeout=self.RE_TIMEOUT)
            return compiled.search(text)
        except Exception as e:
            if _timeout_err is not None and isinstance(e, _timeout_err):
                logger.warning(f"Regex timeout for pattern: {compiled.pattern[:50]}...")
                return None
            raise

    def _get_python_excluded_lines(self, source: str) -> Set[int]:
        """Return line numbers that belong to __main__ blocks or multiline strings.

        Used to reduce false positives from regex-based Python scanning.
        """
        excluded: Set[int] = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return excluded

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                start = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", start)
                # Exclude all lines of multiline string literals
                if start and end and end > start:
                    for ln in range(start, end + 1):
                        excluded.add(ln)
            elif isinstance(node, ast.If):
                # Detect `if __name__ == "__main__":` guard blocks
                cond = node.test
                if (
                    isinstance(cond, ast.Compare)
                    and isinstance(cond.left, ast.Name)
                    and cond.left.id == "__name__"
                    and len(cond.ops) == 1
                    and isinstance(cond.ops[0], ast.Eq)
                    and len(cond.comparators) == 1
                    and isinstance(cond.comparators[0], ast.Constant)
                    and cond.comparators[0].value == "__main__"
                ):
                    start = getattr(node, "lineno", None)
                    end = getattr(node, "end_lineno", start)
                    if start:
                        for ln in range(start, (end or start) + 1):
                            excluded.add(ln)
        return excluded

    def _get_python_string_spans(self, source: str) -> Dict[int, List[Tuple[int, int]]]:
        """Return per-line column spans of single-line string literals.

        Regex matches that fall inside these spans are ignored.
        """
        spans: Dict[int, List[Tuple[int, int]]] = {}
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return spans

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                start = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", start)
                if start and start == end:
                    col_start = getattr(node, "col_offset", None)
                    col_end = getattr(node, "end_col_offset", None)
                    if col_start is not None and col_end is not None:
                        spans.setdefault(start, []).append((col_start, col_end))
        return spans
    
    # ──────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────
    
    def scan(self, tool_name: str, detailed: bool = False) -> SecurityReport:
        """Perform a full security scan on an MCP tool.
        
        Steps:
        1. Get tool info from registry
        2. Check permissions (what can the tool do?)
        3. If installed, scan source code for risk patterns
        4. Check dependencies for known vulnerabilities
        5. Analyze network access requirements
        6. Calculate overall security score
        7. Generate report with warnings and recommendations
        
        Args:
            tool_name: Name of the MCP tool to scan
            detailed: If True, include full code snippets in report
            
        Returns:
            SecurityReport with complete analysis results
        """
        start_time = time.time()
        
        # Step 1: Get tool info
        tool = self._get_tool(tool_name)
        if tool is None:
            return self._create_error_report(tool_name, f"Tool '{tool_name}' not found in registry")
        
        install_path = self._get_install_path(tool)

        # Short-circuit only when directory exists but is empty
        if install_path and os.path.isdir(install_path):
            try:
                entries = os.listdir(install_path)
            except OSError:
                entries = []
            if not entries:
                return SecurityReport(
                    tool_name=tool_name,
                    overall_score=0,
                    security_level=SecurityLevel.UNKNOWN,
                    status="not_installed",
                    permissions_analysis={},
                    code_analysis={},
                    dependency_analysis={},
                    network_analysis={},
                    warnings=[f"Tool '{tool_name}' installation directory is empty."],
                    recommendations=["Reinstall the tool before scanning."],
                )

        # Step 2: Analyze permissions
        permissions_analysis = self._analyze_permissions(tool)
        permissions_risk = permissions_analysis.get("total_risk_score", 0)
        
        # Step 3: Scan source code
        code_analysis = self._scan_source_code(tool, install_path, detailed=detailed)
        code_risk = code_analysis.get("total_risk_score", 0)
        code_scanned = code_analysis.get("status") == "completed"
        
        # Step 4: Check dependencies
        dependency_analysis = self._check_dependencies(tool, install_path)
        dependency_risk = dependency_analysis.get("total_risk", 0)
        dependencies_scanned = dependency_analysis.get("status") == "completed"
        
        # Step 5: Analyze network access
        network_analysis = self._analyze_network_access(tool)
        network_risk = network_analysis.get("risk_score", 0)
        
        # Step 6: Calculate overall score
        overall_score = self._calculate_score(
            permissions_risk, code_risk, dependency_risk, network_risk,
            code_scanned=code_scanned, dependencies_scanned=dependencies_scanned
        )
        
        # Determine security level (pass critical flags for Tier 1 cap)
        has_critical_code = code_analysis.get("has_critical_code", False)
        has_critical_dependency = dependency_analysis.get("has_critical_dependency", False)
        security_level = self._determine_security_level(
            overall_score, code_risk, dependency_risk, permissions_risk,
            has_critical_code=has_critical_code,
            has_critical_dependency=has_critical_dependency,
        )
        
        # Step 7: Create report
        scan_duration = time.time() - start_time
        
        report = SecurityReport(
            tool_name=tool_name,
            overall_score=overall_score,
            security_level=security_level,
            permissions_analysis=permissions_analysis,
            code_analysis=code_analysis,
            dependency_analysis=dependency_analysis,
            network_analysis=network_analysis,
            warnings=[],
            errors=[],
            recommendations=[],
            scan_duration=round(scan_duration, 3),
        )
        
        # Generate warnings, errors, and recommendations
        self._collect_findings(report, permissions_analysis, code_analysis, 
                               dependency_analysis, network_analysis)
        report.recommendations = self.generate_recommendations(report)
        
        logger.info(f"Security scan completed for '{tool_name}': score={overall_score}, "
                   f"level={security_level.name}, duration={scan_duration:.3f}s")
        
        return report
    
    # LRU cache for scan results (max 50 entries)
    _scan_cache: Dict[str, SecurityReport] = {}
    _scan_cache_max_size: int = 50

    def quick_scan(self, tool_name: str) -> SecurityReport:
        """Quick security scan without detailed analysis.

        This is a lightweight scan that skips source-code AST parsing
        and detailed dependency analysis. Suitable for batch operations.

        Args:
            tool_name: Name of the MCP tool to scan

        Returns:
            SecurityReport with analysis results
        """
        # Check cache first
        if tool_name in self._scan_cache:
            return self._scan_cache[tool_name]

        report = self.scan(tool_name, detailed=False)
        # Cache the result
        if len(self._scan_cache) >= self._scan_cache_max_size:
            # Simple eviction: clear half the cache
            keys = list(self._scan_cache.keys())
            for k in keys[:len(keys)//2]:
                del self._scan_cache[k]
        self._scan_cache[tool_name] = report
        return report

    def invalidate_cache(self, tool_name: str) -> None:
        """Invalidate cached scan result for a tool."""
        self._scan_cache.pop(tool_name, None)

    def quick_scan_score(self, tool_name: str) -> int:
        """Quick security score (0-100) without detailed analysis.

        Returns:
            Integer score from 0 (high risk) to 100 (low risk),
            or -1 if the tool is not installed.
        """
        report = self.scan(tool_name, detailed=False)
        if report.status == "not_installed":
            return -1
        return report.overall_score
    
    def compare_tools(self, tool_names: List[str]) -> Dict[str, SecurityReport]:
        """Compare security reports for multiple tools.
        
        Scans each tool and returns a mapping of tool name to report.
        Results are sorted by score descending (most secure first).
        
        Args:
            tool_names: List of MCP tool names to compare
            
        Returns:
            Dictionary mapping tool_name -> SecurityReport
        """
        reports = {}
        for name in tool_names:
            try:
                reports[name] = self.scan(name, detailed=False)
            except Exception as e:
                logger.error(f"Failed to scan '{name}': {e}")
                reports[name] = self._create_error_report(name, str(e))
        
        # Sort by score descending
        return dict(sorted(reports.items(), key=lambda x: x[1].overall_score, reverse=True))
    
    def check_prerequisites(self) -> Dict[str, bool]:
        """Check if security scanning prerequisites are available.
        
        Returns a dictionary mapping tool name to availability.
        Checks for:
        - npm audit (Node.js dependency auditing)
        - pip-audit (Python dependency auditing)
        - safety (Python safety checker)
        - cargo audit (Rust dependency auditing)
        - go mod (Go module vulnerability checking)
        """
        if self._prerequisites_cache is not None:
            return self._prerequisites_cache.copy()
        
        def _command_exists(cmd: str) -> bool:
            """Check if a command exists in PATH."""
            for path in os.environ.get("PATH", "").split(os.pathsep):
                if os.path.isfile(os.path.join(path, cmd)):
                    return True
                # Windows extensions
                for ext in (".exe", ".cmd", ".bat"):
                    if os.path.isfile(os.path.join(path, cmd + ext)):
                        return True
            return False
        
        def _module_exists(module: str) -> bool:
            """Check if a Python module is importable without executing it."""
            return importlib.util.find_spec(module) is not None
        
        prerequisites = {
            "npm_audit": _command_exists("npm"),
            "pip_audit": _command_exists("pip-audit"),
            "safety": _command_exists("safety"),
            "cargo_audit": _command_exists("cargo-audit"),
            "go_vuln": _command_exists("govulncheck"),
            "python_ast": _module_exists("ast"),
            "python_bandit": _module_exists("bandit"),
        }
        
        self._prerequisites_cache = prerequisites
        return prerequisites.copy()
    
    def generate_recommendations(self, report: SecurityReport) -> List[str]:
        """Generate security recommendations based on findings.
        
        Analyzes the report findings and produces actionable
        recommendations for improving security posture.
        
        Args:
            report: Completed SecurityReport to analyze
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Score-based recommendations
        if report.overall_score < 30:
            recommendations.append(
                "[CRITICAL] 该工具存在严重安全风险，建议立即审查或暂停使用。"
                "请先检查所有高风险的代码模式和权限声明。"
            )
        elif report.overall_score < 60:
            recommendations.append(
                "[HIGH] 该工具存在显著安全风险，建议在限制环境中运行，"
                "并审查所有权限和代码模式。"
            )
        elif report.overall_score < 80:
            recommendations.append(
                "[MEDIUM] 该工具安全评分中等，建议定期审查并考虑减少不必要的权限。"
            )
        elif report.overall_score >= 90:
            recommendations.append(
                "[LOW] 该工具安全评分良好，建议继续保持安全实践。"
            )
        
        # Permission-based recommendations
        perm_risk = report.permissions_analysis.get("total_risk_score", 0)
        if perm_risk >= 20:
            recommendations.append(
                "[PERMISSIONS] 工具声明了过多高风险权限。"
                "建议遵循最小权限原则，仅声明必需的权限。"
            )
        
        high_risk_perms = report.permissions_analysis.get("high_risk_permissions", [])
        if high_risk_perms:
            for perm in high_risk_perms:
                recommendations.append(
                    f"[PERMISSIONS] 高风险权限 '{perm}' 可能导致安全问题。"
                    f"建议评估该权限是否必需，并考虑使用更安全的替代方案。"
                )
        
        missing_perms = report.permissions_analysis.get("missing_permissions", [])
        if missing_perms:
            recommendations.append(
                f"[PERMISSIONS] 工具使用了但未声明的权限: {', '.join(missing_perms)}。"
                "建议在工具清单中显式声明这些权限，以提高透明度。"
            )
        
        # Code-based recommendations
        code_risk = report.code_analysis.get("total_risk_score", 0)
        if code_risk >= 20:
            recommendations.append(
                "[CODE] 代码中存在大量高风险模式。"
                "建议进行完整代码审计，特别关注文件系统、命令执行和网络访问代码。"
            )
        
        pattern_counts = report.code_analysis.get("pattern_counts", {})
        for pattern_type, count in pattern_counts.items():
            if count > 0:
                if pattern_type == "command_execution":
                    recommendations.append(
                        f"[CODE] 发现 {count} 处命令执行相关代码。"
                        "建议使用参数列表而非字符串拼接，并对输入进行严格验证。"
                    )
                elif pattern_type == "filesystem_access":
                    recommendations.append(
                        f"[CODE] 发现 {count} 处文件系统操作。"
                        "建议限制可访问的路径范围，并验证所有路径参数。"
                    )
                elif pattern_type == "network_access":
                    recommendations.append(
                        f"[CODE] 发现 {count} 处网络访问代码。"
                        "建议使用允许列表限制可访问的目标地址，并验证 SSL 证书。"
                    )
                elif pattern_type == "sensitive_data":
                    recommendations.append(
                        f"[CODE] 发现 {count} 处敏感数据处理。"
                        "建议使用环境变量或密钥管理服务存储凭证，避免硬编码。"
                    )
                elif pattern_type == "data_exfiltration":
                    recommendations.append(
                        f"[CODE] 发现 {count} 处可能的数据外泄模式。"
                        "建议审查数据传输目的，确保符合数据隐私要求。"
                    )
        
        # Dependency recommendations
        dep_risk = report.dependency_analysis.get("total_risk", 0)
        if dep_risk >= 10:
            recommendations.append(
                "[DEPENDENCIES] 依赖项存在已知风险。"
                "建议运行依赖审计工具（npm audit / pip-audit）并升级有漏洞的包。"
            )
        
        risky_deps = report.dependency_analysis.get("risky_dependencies", [])
        if risky_deps:
            dep_names = [d["name"] for d in risky_deps]
            recommendations.append(
                f"[DEPENDENCIES] 发现风险依赖项: {', '.join(dep_names)}。"
                "建议评估这些依赖的必要性，并寻找更安全的替代方案。"
            )
        
        outdated = report.dependency_analysis.get("outdated_dependencies", [])
        if outdated:
            recommendations.append(
                f"[DEPENDENCIES] 发现 {len(outdated)} 个过时的依赖项。"
                "建议定期更新依赖以获得最新的安全补丁。"
            )
        
        # Network recommendations
        network = report.network_analysis
        if network.get("has_network_access", False):
            if network.get("risk_level") == "HIGH":
                recommendations.append(
                    "[NETWORK] 工具具有不受限制的网络访问权限。"
                    "建议实施网络访问控制，使用代理或防火墙限制出站连接。"
                )
            elif network.get("endpoints", []):
                endpoints = network["endpoints"]
                recommendations.append(
                    f"[NETWORK] 工具访问的端点: {', '.join(endpoints[:5])}"
                    f"{' 等' if len(endpoints) > 5 else ''}。"
                    "建议验证这些端点的合法性，并监控网络流量。"
                )
        
        # General recommendations
        if not recommendations:
            recommendations.append(
                "[INFO] 未发现显著安全问题。建议定期进行安全审查，保持依赖更新。"
            )
        
        return recommendations
    
    # ──────────────────────────────────────────────────────────────
    #  Core Analysis Methods
    # ──────────────────────────────────────────────────────────────
    
    def _analyze_permissions(self, tool: MCPTool) -> Dict[str, Any]:
        """Analyze tool permissions and their risk levels.
        
        Evaluates each declared permission against known risk categories
        and calculates an overall risk score.
        
        Args:
            tool: MCPTool instance to analyze
            
        Returns:
            Dictionary with:
            - permissions: {permission_name: {level, description, risk_score}}
            - total_risk_score: int (0-100)
            - high_risk_permissions: list of high-risk permission names
            - missing_permissions: list of used but undeclared permissions
        """
        result = {
            "permissions": {},
            "total_risk_score": 0,
            "high_risk_permissions": [],
            "missing_permissions": [],
        }
        
        # Get declared permissions from tool
        declared = getattr(tool, "permissions", None) or getattr(tool, "required_permissions", [])
        if not declared:
            declared = []
        
        # Also check mcp.json or tool configuration
        config = getattr(tool, "config", {}) or {}
        if isinstance(config, dict):
            config_perms = config.get("permissions", []) or config.get("required_permissions", [])
            if config_perms and not declared:
                declared = config_perms
        
        total_risk = 0
        high_risk = []
        permissions_detail = {}
        
        for perm in declared:
            perm_str = str(perm).lower()
            risk_score = 0
            level = "low"
            description = "低风险权限"
            
            # Check against high-risk categories
            for category, risks in self.HIGH_RISK_PERMISSIONS.items():
                for risk_type, risk_desc in risks.items():
                    if risk_type in perm_str or any(kw in perm_str for kw in risk_type.split()):
                        full_key = f"{category}:{risk_type}"
                        risk_score = self.RISK_SEVERITY_WEIGHTS.get(full_key, 15)
                        level = "high"
                        description = risk_desc
                        break
                if level == "high":
                    break
            
            # Check for medium-risk patterns
            if level == "low":
                medium_patterns = [
                    ("read", "文件读取权限", 5),
                    ("list", "目录列表权限", 5),
                    ("connect", "网络连接权限", 8),
                    ("query", "数据查询权限", 5),
                    ("fetch", "数据获取权限", 8),
                    ("download", "文件下载权限", 10),
                ]
                for pattern, desc, score in medium_patterns:
                    if pattern in perm_str:
                        risk_score += score
                        level = "medium" if score >= 8 else "low"
                        description = desc
                        break
            
            if level == "low" and risk_score == 0:
                risk_score = self.RISK_THRESHOLD_LOW
            
            permissions_detail[perm] = {
                "level": level,
                "description": description,
                "risk_score": risk_score,
            }
            
            total_risk += risk_score
            if level == "high":
                high_risk.append(perm)
        
        # Check for missing permissions (used but not declared)
        missing = self._check_required_permissions(tool)
        
        # Cap total risk at 100
        total_risk = min(total_risk, 100)
        
        result["permissions"] = permissions_detail
        result["total_risk_score"] = total_risk
        result["high_risk_permissions"] = high_risk
        result["missing_permissions"] = missing
        result["declared_count"] = len(declared)
        result["missing_count"] = len(missing)
        
        # Classify overall permission risk using RISK_THRESHOLD_* constants
        if total_risk >= self.RISK_THRESHOLD_HIGH:
            result["risk_level"] = "CRITICAL"
        elif total_risk >= self.RISK_THRESHOLD_MEDIUM:
            result["risk_level"] = "HIGH"
        elif total_risk >= self.RISK_THRESHOLD_LOW:
            result["risk_level"] = "MEDIUM"
        else:
            result["risk_level"] = "LOW"
        
        return result
    
    def _scan_source_code(self, tool: MCPTool, install_path: Optional[str], 
                          detailed: bool = False) -> Dict[str, Any]:
        """Scan source code for risk patterns.
        
        Traverses the installation directory, scans code files against
        RISK_PATTERNS, and collects matches with file/line context.
        
        Args:
            tool: MCPTool instance
            install_path: Path to installed tool directory, or None
            detailed: If True, include full code snippets
            
        Returns:
            Dictionary with:
            - pattern_counts: {pattern_type: match_count}
            - pattern_matches: {pattern_type: [{file, line, snippet}]}
            - total_risk_score: int
            - files_scanned: int
            - files_skipped: int
        """
        result = {
            "pattern_counts": {k: 0 for k in self.RISK_PATTERNS},
            "pattern_matches": {k: [] for k in self.RISK_PATTERNS},
            "total_risk_score": 0,
            "files_scanned": 0,
            "files_skipped": 0,
            "total_lines": 0,
        }
        
        if not install_path or not os.path.isdir(install_path):
            result["status"] = "not_installed"
            return result
        
        install_path = Path(install_path)
        
        # Compile patterns (with caching and optional timeout)
        compiled_patterns = {}
        for pattern_type, patterns in self.RISK_PATTERNS.items():
            compiled_patterns[pattern_type] = [self._compile_pattern(p, re.IGNORECASE) for p in patterns]
        
        # Risk weights per pattern type
        risk_weights = {
            "command_execution": 5,
            "foreign_function": 10,
            "dynamic_import": 5,
            "obfuscated_execution": 8,
            "data_exfiltration": 4,
            "sensitive_data": 3,
            "filesystem_access": 2,
            "network_access": 2,
            "environment_manipulation": 3,
        }
        
        files_scanned = 0
        total_lines = 0
        total_paths_enumerated = 0
        
        # Scan files
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".tox", ".pytest_cache"}
        blocked_roots = {"/dev", "/proc", "/sys"}
        
        start_time = time.time()
        
        # Cross-process scan lock
        lock_path = Path(DEFAULT_DATA_DIR) / ".scan.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(lock_path))
        with lock:
            for path in install_path.rglob("*"):
                total_paths_enumerated += 1
                
                # Limit total enumerated paths to prevent rglob DoS
                if total_paths_enumerated > self.MAX_ENUMERATED_PATHS:
                    logger.warning("Security scan reached max enumerated paths, aborting.")
                    break
                
                # Total scan time limit
                if time.time() - start_time > self.MAX_SCAN_DURATION_SECONDS:
                    logger.warning("Security scan timeout reached, aborting scan.")
                    break
                
                # Max files per scan limit
                if files_scanned >= self.MAX_FILES_PER_SCAN:
                    break
                
                # Reject symlinks before any other file check
                try:
                    if path.is_symlink():
                        continue
                except (OSError, IOError):
                    continue
                
                if not path.is_file():
                    continue
                
                # Skip known directories
                if any(part in skip_dirs for part in path.parts):
                    continue
                
                # Reject paths pointing to pseudo-filesystems
                try:
                    real_path = path.resolve()
                    real_path_str = str(real_path)
                    if any(real_path_str.startswith(br) for br in blocked_roots):
                        continue
                except (OSError, IOError):
                    continue
                
                # Check extension
                if path.suffix not in self.CODE_EXTENSIONS:
                    # Allow only small text files without extension
                    if path.suffix == "":
                        try:
                            if path.stat().st_size > 1024 * 1024:
                                continue
                        except (OSError, IOError):
                            continue
                    else:
                        continue
                
                # Unified file size limit for all scanned files (10MB)
                try:
                    if path.stat().st_size > self.MAX_FILE_SIZE:
                        continue
                except (OSError, IOError):
                    continue
                
                # Skip binary files (check for null bytes in first 1KB)
                try:
                    with open(path, "rb") as f:
                        sample = f.read(1024)
                        if b"\x00" in sample:
                            continue
                except (IOError, OSError):
                    continue
                
                files_scanned += 1
                
                # Scan file content
                file_line_count = 0
                is_python = path.suffix == ".py"
                excluded_lines: Set[int] = set()
                string_spans: Dict[int, List[Tuple[int, int]]] = {}
                try:
                    if is_python:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            source = f.read(self.MAX_FILE_SIZE + 1)
                        if len(source) > self.MAX_FILE_SIZE:
                            continue
                        # Skip AST string-span detection for files > 1MB to reduce memory
                        if len(source) > 1024 * 1024:
                            excluded_lines = self._get_python_excluded_lines(source)
                            string_spans = {}
                        else:
                            excluded_lines = self._get_python_excluded_lines(source)
                            string_spans = self._get_python_string_spans(source)
                        line_iter = enumerate(source.splitlines(keepends=True), 1)
                    else:
                        f = open(path, "r", encoding="utf-8", errors="ignore")
                        line_iter = enumerate(f, 1)
                    
                    for line_num, line in line_iter:
                        # Limit lines per file
                        if file_line_count >= self.MAX_LINES_PER_FILE:
                            break
                        
                        # Limit line length
                        if len(line) > self.MAX_LINE_LENGTH:
                            line = line[:self.MAX_LINE_LENGTH]
                        
                        file_line_count += 1
                        total_lines += 1
                        
                        # Skip lines inside __main__ blocks or multiline strings in Python
                        if line_num in excluded_lines:
                            continue
                        
                        line_stripped = line.strip()
                        # Skip comments and docstrings (basic heuristic)
                        if line_stripped.startswith("#") or line_stripped.startswith("//") or \
                           line_stripped.startswith("*") or line_stripped.startswith("/*") or \
                           line_stripped.startswith("<!--") or line_stripped.startswith("--"):
                            continue
                        
                        for pattern_type, compiled_list in compiled_patterns.items():
                            for compiled in compiled_list:
                                match = self._safe_search(compiled, line)
                                if not match:
                                    continue
                                # Ignore matches that fall inside Python string literals
                                if is_python:
                                    in_string = False
                                    for start_col, end_col in string_spans.get(line_num, []):
                                        if match.start() < end_col and match.end() > start_col:
                                            in_string = True
                                            break
                                    if in_string:
                                        continue
                                result["pattern_counts"][pattern_type] += 1
                                
                                snippet = line.strip()[:200]  # Limit snippet length
                                match_info = {
                                    "file": str(path.relative_to(install_path)),
                                    "line": line_num,
                                    "snippet": snippet if detailed else "(redacted in quick scan)",
                                }
                                result["pattern_matches"][pattern_type].append(match_info)
                                break  # Only count one match per pattern type per line
                except (IOError, OSError, UnicodeDecodeError):
                    continue
                finally:
                    if not is_python and "f" in locals():
                        try:
                            f.close()
                        except Exception:
                            pass
        
        # Calculate skipped files based on enumerated paths
        files_skipped = total_paths_enumerated - files_scanned

        # Calculate total risk score
        total_risk = 0
        for pattern_type, count in result["pattern_counts"].items():
            weight = risk_weights.get(pattern_type, 1)
            total_risk += count * weight

        # Mark if critical code patterns (command_execution) were detected
        result["has_critical_code"] = result["pattern_counts"].get("command_execution", 0) > 0

        # Cap at 100
        result["total_risk_score"] = min(total_risk, 100)
        result["files_scanned"] = files_scanned
        result["files_skipped"] = files_skipped
        result["total_lines"] = total_lines
        result["status"] = "completed"

        return result
    
    def _check_dependencies(self, tool: MCPTool, install_path: Optional[str]) -> Dict[str, Any]:
        """Check dependencies for known vulnerabilities and risks.
        
        Scans dependency files (package.json, requirements.txt, etc.)
        and identifies risky or outdated dependencies.
        
        Args:
            tool: MCPTool instance
            install_path: Path to installed tool directory, or None
            
        Returns:
            Dictionary with:
            - dependencies: list of {name, version, type, risk}
            - total_risk: int
            - risky_dependencies: list of risky ones
            - outdated_dependencies: list of outdated ones
            - dependency_files_found: list of found file names
        """
        result = {
            "dependencies": [],
            "total_risk": 0,
            "risky_dependencies": [],
            "outdated_dependencies": [],
            "dependency_files_found": [],
        }
        
        if not install_path or not os.path.isdir(install_path):
            result["status"] = "not_installed"
            return result
        
        install_path = Path(install_path)
        all_deps = []
        total_risk = 0
        risky = []
        outdated = []
        dep_files_found = []
        
        # Check for each dependency file type
        for dep_file_name, dep_type in self.DEPENDENCY_FILES.items():
            dep_file_path = install_path / dep_file_name
            if dep_file_path.exists():
                # Security: path traversal and symlink validation
                try:
                    resolved = dep_file_path.resolve()
                    install_resolved = install_path.resolve()
                    if not str(resolved).startswith(str(install_resolved)):
                        logger.warning(f"Path traversal detected: {dep_file_path}")
                        continue
                    if resolved.is_symlink():
                        logger.warning(f"Skipping symlink dependency file: {dep_file_path}")
                        continue
                    if not resolved.is_file():
                        logger.warning(f"Skipping non-file dependency path: {dep_file_path}")
                        continue
                except (OSError, ValueError) as e:
                    logger.warning(f"Path validation error for {dep_file_path}: {e}")
                    continue
                dep_files_found.append(dep_file_name)
                try:
                    deps = self._parse_dependency_file(dep_file_path, dep_type)
                    all_deps.extend(deps)
                except Exception as e:
                    logger.warning(f"Failed to parse {dep_file_path}: {e}")
        
        # Also check lock files for more accurate versions
        lock_files = ["package-lock.json", "Pipfile.lock", "Cargo.lock", "go.sum", "poetry.lock"]
        for lock_file in lock_files:
            lock_path = install_path / lock_file
            if lock_path.exists():
                dep_files_found.append(lock_file)
        
        # Analyze each dependency
        for dep in all_deps:
            dep_risk = 0
            risk_reasons = []
            
            # Check against risky dependency patterns
            for risk_name, risk_info in self.RISKY_DEPENDENCIES.items():
                pattern = self._compile_pattern(risk_info["pattern"], re.IGNORECASE)
                if pattern.match(dep["name"]):
                    severity = risk_info["severity"]
                    if severity == "high":
                        dep_risk += 15
                    elif severity == "medium":
                        dep_risk += 8
                    risk_reasons.append(risk_info["description"])
            
            # Check for suspicious version patterns (dev/snapshot versions)
            version = dep.get("version", "")
            if version:
                if any(tag in version.lower() for tag in ["dev", "alpha", "beta", "rc", "snapshot", "nightly"]):
                    dep_risk += 3
                    risk_reasons.append(f"预发布版本: {version}")
            
            dep["risk_score"] = dep_risk
            dep["risk_reasons"] = risk_reasons
            
            if dep_risk > 0:
                risky.append(dep)
                total_risk += dep_risk
            
            # Check if version is pinned (good practice)
            if version and not re.match(r"^[\d~^><=]+.*$", str(version)):
                outdated.append(dep)
        
        # Check for direct dependency count (too many = higher risk)
        if len(all_deps) > 50:
            total_risk += 5
            result["note"] = "依赖数量过多，增加攻击面"
        
        # Mark if eval-like critical dependencies were detected
        result["has_critical_dependency"] = any(
            d.get("name", "").lower() in ("eval", "exec", "unsafe-eval", "vm2", "sandbox")
            for d in risky
        )

        result["dependencies"] = all_deps
        result["total_risk"] = min(total_risk, 100)
        result["risky_dependencies"] = risky
        result["outdated_dependencies"] = outdated
        result["dependency_files_found"] = dep_files_found
        result["dependency_count"] = len(all_deps)
        result["status"] = "completed"

        return result
    
    def _analyze_network_access(self, tool: MCPTool) -> Dict[str, Any]:
        """Analyze network access requirements and risk.
        
        Determines whether the tool requires network access and
        assesses the risk level based on declared endpoints and permissions.
        
        Args:
            tool: MCPTool instance
            
        Returns:
            Dictionary with:
            - has_network_access: bool
            - endpoints: list of endpoint strings
            - risk_level: str (LOW/MEDIUM/HIGH/CRITICAL)
            - risk_score: int
            - declared_in_permissions: bool
        """
        result = {
            "has_network_access": False,
            "endpoints": [],
            "risk_level": "LOW",
            "risk_score": 0,
            "declared_in_permissions": False,
        }
        
        # Check permissions for network access
        permissions = getattr(tool, "permissions", []) or getattr(tool, "required_permissions", [])
        config = getattr(tool, "config", {}) or {}
        
        perm_str = " ".join(str(p) for p in permissions).lower()
        config_str = json.dumps(config).lower() if config else ""
        
        network_keywords = ["network", "http", "url", "fetch", "request", "connect", 
                           "outbound", "internet", "api", "webhook", "websocket"]
        has_network_perm = any(kw in perm_str or kw in config_str for kw in network_keywords)
        
        # Extract endpoints from config
        endpoints = []
        if isinstance(config, dict):
            # Check common config keys for endpoints
            for key in ["endpoints", "urls", "hosts", "api_endpoints", "servers"]:
                if key in config:
                    val = config[key]
                    if isinstance(val, list):
                        endpoints.extend(str(v) for v in val if v)
                    elif isinstance(val, str):
                        endpoints.append(val)
                    elif isinstance(val, dict):
                        endpoints.extend(str(v) for v in val.values() if v)
            
            # Check for base_url or similar
            for key in ["base_url", "api_url", "host", "server_url"]:
                if key in config and config[key]:
                    endpoints.append(str(config[key]))
        
        # Also check tool metadata
        metadata = getattr(tool, "metadata", {}) or {}
        if isinstance(metadata, dict):
            for key in ["endpoints", "urls", "hosts"]:
                if key in metadata:
                    val = metadata[key]
                    if isinstance(val, list):
                        endpoints.extend(str(v) for v in val if v)
                    elif isinstance(val, str):
                        endpoints.append(val)
        
        endpoints = list(dict.fromkeys(endpoints))  # Remove duplicates while preserving order
        
        # Calculate risk
        risk_score = 0
        risk_level = "LOW"
        
        if has_network_perm or endpoints:
            result["has_network_access"] = True
            result["declared_in_permissions"] = has_network_perm
            
            # Base risk for any network access
            risk_score += 5
            
            # Risk for each endpoint (more endpoints = more risk)
            risk_score += min(len(endpoints) * 2, 20)
            
            # Check for known risky domains
            risky_domains = ["0.0.0.0"]
            for endpoint in endpoints:
                endpoint_lower = endpoint.lower()
                if any(rd in endpoint_lower for rd in risky_domains):
                    risk_score += 8
                # Check for HTTP vs HTTPS (localhost is considered safe)
                if endpoint_lower.startswith("http://") and not endpoint_lower.startswith("http://localhost"):
                    risk_score += 5
                # Check for wildcards
                if "*" in endpoint and not endpoint.startswith("*."):
                    risk_score += 10
                if "{}" in endpoint and re.search(r"\{\s*\}", endpoint):
                    risk_score += 5
        
        # If tool has network code patterns but no declared permissions
        if not has_network_perm and not endpoints:
            # We can't determine from static config alone - assume no network if not declared
            pass
        
        if risk_score >= 20:
            risk_level = "HIGH"
        elif risk_score >= 10:
            risk_level = "MEDIUM"
        
        result["endpoints"] = endpoints
        result["risk_level"] = risk_level
        result["risk_score"] = min(risk_score, 100)
        
        return result
    
    def _calculate_score(self, permissions_risk: int, code_risk: int,
                         dependency_risk: int, network_risk: int,
                         code_scanned: bool = True,
                         dependencies_scanned: bool = True) -> int:
        """Calculate overall security score (0-100, higher is better).

        Uses non-linear scoring with per-dimension hard caps and
        max-risk penalty to prevent a single high-risk dimension
        from being diluted by low-risk dimensions.

        Args:
            permissions_risk: Risk score from permission analysis (0-100)
            code_risk: Risk score from code analysis (0-100)
            dependency_risk: Risk score from dependency analysis (0-100)
            network_risk: Risk score from network analysis (0-100)
            code_scanned: Whether source code was successfully scanned
            dependencies_scanned: Whether dependencies were successfully scanned

        Returns:
            Integer score from 0 to 100
        """
        # Each dimension: 100 - risk = score for that dimension
        perm_score = max(0, 100 - permissions_risk)
        code_score = max(0, 100 - code_risk)
        dep_score = max(0, 100 - dependency_risk)
        net_score = max(0, 100 - network_risk)

        # Base weighted average
        base = (
            perm_score * self.WEIGHT_PERMISSIONS +
            code_score * self.WEIGHT_CODE +
            dep_score * self.WEIGHT_DEPENDENCIES +
            net_score * self.WEIGHT_NETWORK
        )

        # Per-dimension hard caps (prevent dilution)
        def _dim_cap(risk: int) -> int:
            if risk >= 60:
                return 40
            elif risk >= 40:
                return 60
            elif risk >= 20:
                return 80
            return 100

        hard_cap = min(
            _dim_cap(permissions_risk),
            _dim_cap(code_risk),
            _dim_cap(dependency_risk),
            _dim_cap(network_risk),
        )
        base = min(base, hard_cap)

        # Non-linear penalty based on max single-dimension risk.
        # Continuous at max_risk=40 (penalty=0) and grows quadratically
        # to +32 at max_risk=60 (replacing the old +30 discontinuity).
        max_risk = max(permissions_risk, code_risk, dependency_risk, network_risk)
        if max_risk <= 40:
            penalty = 0.0
        else:
            penalty = ((max_risk - 40) ** 2) / 12.5
        overall = max(0.0, base - penalty)

        # Explicit penalty for uninstalled tools (cannot verify code/dependencies)
        if not code_scanned or not dependencies_scanned:
            overall = min(overall, 70)

        return int(round(overall))
    
    def _check_required_permissions(self, tool: MCPTool) -> List[str]:
        """Check if tool declares all required permissions.
        
        Identifies permissions that the tool likely uses based on
        its configuration and metadata but hasn't explicitly declared.
        
        Args:
            tool: MCPTool instance
            
        Returns:
            List of potentially missing permission strings
        """
        missing = []
        
        # Get declared permissions
        declared = set()
        perms = getattr(tool, "permissions", []) or getattr(tool, "required_permissions", [])
        for p in perms:
            declared.add(str(p).lower())
        
        config = getattr(tool, "config", {}) or {}
        config_str = json.dumps(config).lower() if config else ""
        
        # Check for filesystem access patterns in config
        fs_patterns = ["file_path", "directory", "workspace", "path", "folder", "fs."]
        if any(p in config_str for p in fs_patterns):
            if not any("file" in d or "fs" in d or "path" in d for d in declared):
                missing.append("filesystem")
        
        # Check for network access patterns
        net_patterns = ["url", "endpoint", "api", "http", "fetch", "host"]
        if any(p in config_str for p in net_patterns):
            if not any("network" in d or "http" in d or "url" in d for d in declared):
                missing.append("network")
        
        # Check for command execution patterns
        cmd_patterns = ["command", "shell", "script", "exec", "run"]
        if any(p in config_str for p in cmd_patterns):
            if not any("command" in d or "shell" in d or "exec" in d for d in declared):
                missing.append("command_execution")
        
        return missing
    
    # ──────────────────────────────────────────────────────────────
    #  Helper Methods
    # ──────────────────────────────────────────────────────────────
    
    def _get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """Get tool from registry."""
        try:
            return self.registry.get(tool_name)
        except Exception:
            return None
    
    def _get_install_path(self, tool: MCPTool) -> Optional[str]:
        """Get installation path for a tool."""
        # Try multiple attributes
        for attr in ["install_path", "path", "location", "directory", "base_path"]:
            path = getattr(tool, attr, None)
            if path and os.path.isdir(str(path)):
                return str(path)
        
        # Try DEFAULT_DATA_DIR
        data_dir = Path(DEFAULT_DATA_DIR) if DEFAULT_DATA_DIR else Path.home() / ".mcp-hub"
        candidate = data_dir / "installed" / getattr(tool, "name", "")
        if candidate.exists():
            return str(candidate)
        
        return None
    
    def _parse_dependency_file(self, file_path: Path, dep_type: str) -> List[Dict[str, str]]:
        """Parse a dependency file and return list of dependencies.

        Args:
            file_path: Path to the dependency file
            dep_type: Type of dependency file (npm, pip, cargo, etc.)

        Returns:
            List of {name, version, type} dictionaries
        """
        # Lazy-load tomllib/tomli inside this method
        try:
            import tomllib
        except ImportError:  # pragma: no cover
            try:
                import tomli as tomllib
            except ImportError:  # pragma: no cover
                tomllib = None

        # Security: size limit and file type validation
        MAX_DEP_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
        try:
            if not file_path.is_file():
                logger.warning(f"Not a regular file: {file_path}")
                return []
            stat = file_path.stat()
            if stat.st_size > MAX_DEP_FILE_SIZE:
                logger.warning(
                    f"Dependency file too large ({stat.st_size} bytes), skipping: {file_path}"
                )
                return []
        except (OSError, ValueError) as e:
            logger.warning(f"Cannot validate dependency file: {e}")
            return []
        
        deps = []
        
        if dep_type == "npm":
            # Parse package.json
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Check dependencies and devDependencies
                for key in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
                    if key in data and isinstance(data[key], dict):
                        for name, version in data[key].items():
                            deps.append({
                                "name": name,
                                "version": str(version).replace("^", "").replace("~", ""),
                                "type": "npm",
                                "source": key,
                            })
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error parsing package.json: {e}")
        
        elif dep_type == "pip":
            # Parse requirements.txt
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("-"):
                            continue
                        
                        # Use packaging.requirements.Requirement for robust parsing
                        Requirement = _get_requirement_class()
                        if Requirement:
                            try:
                                req = Requirement(line)
                                version = str(req.specifier) if req.specifier else "unspecified"
                                deps.append({
                                    "name": req.name,
                                    "version": version,
                                    "type": "pip",
                                    "source": "requirements.txt",
                                })
                            except Exception as e:
                                logger.debug(f"Could not parse requirement line: {line}: {e}")
                                # Fallback: extract name only
                                clean = line.split(";")[0].split("#")[0].strip()
                                name = re.split(r'[[\]=<>~!]', clean)[0].strip()
                                if name and re.match(r'^[a-zA-Z0-9]', name):
                                    deps.append({
                                        "name": name,
                                        "version": "unspecified",
                                        "type": "pip",
                                        "source": "requirements.txt",
                                    })
                        else:
                            # Improved regex fallback: strip markers and comments first
                            clean = line.split(";")[0].split("#")[0].strip()
                            # Match name[extras] with optional version specifiers
                            match = re.match(
                                r'^([a-zA-Z0-9][a-zA-Z0-9_\-\.]*)'
                                r'(?:\[[^\]]+\])?'
                                r'\s*([=<>~!]*)'
                                r'\s*(.*)$',
                                clean
                            )
                            if match:
                                version = match.group(3).strip() or "unspecified"
                                deps.append({
                                    "name": match.group(1),
                                    "version": version,
                                    "type": "pip",
                                    "source": "requirements.txt",
                                })
                            else:
                                name = re.split(r'[[\]=<>~!]', clean)[0].strip()
                                if name and re.match(r'^[a-zA-Z0-9]', name):
                                    deps.append({
                                        "name": name,
                                        "version": "unspecified",
                                        "type": "pip",
                                        "source": "requirements.txt",
                                    })
            except IOError as e:
                logger.warning(f"Error parsing requirements.txt: {e}")
        
        elif dep_type == "cargo":
            # Parse Cargo.toml using tomllib/tomli if available
            try:
                if tomllib is not None:
                    with open(file_path, "rb") as f:
                        data = tomllib.load(f)
                    cargo_deps = data.get("dependencies", {})
                    if isinstance(cargo_deps, dict):
                        for name, spec in cargo_deps.items():
                            if isinstance(spec, str):
                                version = spec
                            elif isinstance(spec, dict):
                                version = spec.get("version", "complex")
                            else:
                                version = "complex"
                            deps.append({
                                "name": name,
                                "version": version,
                                "type": "cargo",
                                "source": "Cargo.toml",
                            })
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    # Safer regex: find [dependencies] section and parse each line
                    dep_section = re.search(r"\[dependencies\](.*?)(?=\[|$)", content, re.DOTALL)
                    if dep_section:
                        for line in dep_section.group(1).strip().split("\n"):
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            # Match name = "version" or name = { ... }
                            match = re.match(
                                r'^([a-zA-Z0-9][a-zA-Z0-9_\-\.]*)'
                                r'\s*=\s*'
                                r'(?:"([^"]+)"|(\{.*\}))',
                                line
                            )
                            if match:
                                name = match.group(1)
                                version = match.group(2) if match.group(2) else "complex"
                                deps.append({
                                    "name": name,
                                    "version": version,
                                    "type": "cargo",
                                    "source": "Cargo.toml",
                                })
            except (IOError, Exception) as e:
                logger.warning(f"Error parsing Cargo.toml: {e}")
        
        elif dep_type == "go":
            # Parse go.mod with line-by-line state machine
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    in_require_block = False
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("//"):
                            continue
                        if line.startswith("require ("):
                            in_require_block = True
                            continue
                        if in_require_block and line == ")":
                            in_require_block = False
                            continue
                        if in_require_block or line.startswith("require "):
                            req_line = line
                            if req_line.startswith("require "):
                                req_line = req_line[len("require "):].strip()
                            # Remove trailing parentheses if present
                            req_line = req_line.strip("()")
                            parts = req_line.split()
                            if len(parts) >= 2:
                                deps.append({
                                    "name": parts[0],
                                    "version": parts[1],
                                    "type": "go",
                                    "source": "go.mod",
                                })
            except IOError as e:
                logger.warning(f"Error parsing go.mod: {e}")
        
        elif dep_type == "maven":
            # Parse pom.xml using xml.etree.ElementTree
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(file_path)
                root = tree.getroot()
                # Find all dependencies regardless of namespace
                for dep in root.iter():
                    tag = dep.tag.split("}")[-1] if "}" in dep.tag else dep.tag
                    if tag == "dependency":
                        group = None
                        artifact = None
                        version = None
                        for child in dep:
                            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                            if child_tag == "groupId":
                                group = child.text
                            elif child_tag == "artifactId":
                                artifact = child.text
                            elif child_tag == "version":
                                version = child.text
                        if group and artifact:
                            deps.append({
                                "name": f"{group}:{artifact}",
                                "version": version or "unspecified",
                                "type": "maven",
                                "source": "pom.xml",
                            })
            except (IOError, Exception) as e:
                logger.warning(f"Error parsing pom.xml: {e}")
        
        elif dep_type == "gradle":
            # Parse build.gradle (simplified, regex-based)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Match implementation/compile/api dependencies
                dep_matches = re.findall(
                    r"(?:implementation|compile|api)\s+['\"]([^'\"]+)['\"]",
                    content
                )
                for dep_str in dep_matches:
                    parts = dep_str.split(":")
                    if len(parts) >= 2:
                        deps.append({
                            "name": ":".join(parts[:-1]),
                            "version": parts[-1],
                            "type": "gradle",
                            "source": "build.gradle",
                        })
                    else:
                        deps.append({
                            "name": dep_str,
                            "version": "unspecified",
                            "type": "gradle",
                            "source": "build.gradle",
                        })
            except IOError as e:
                logger.warning(f"Error parsing build.gradle: {e}")
        
        elif dep_type == "poetry":
            # Parse pyproject.toml using tomllib/tomli if available
            try:
                if tomllib is not None:
                    with open(file_path, "rb") as f:
                        data = tomllib.load(f)
                    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                    if isinstance(poetry_deps, dict):
                        for name, spec in poetry_deps.items():
                            if name == "python":
                                continue
                            if isinstance(spec, str):
                                version = spec
                            elif isinstance(spec, dict):
                                version = spec.get("version", "complex")
                            else:
                                version = "complex"
                            deps.append({
                                "name": name,
                                "version": version,
                                "type": "poetry",
                                "source": "pyproject.toml",
                            })
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    # Safer regex for [tool.poetry.dependencies] section
                    dep_section = re.search(
                        r'\[tool\.poetry\.dependencies\](.*?)(?=\[|$)',
                        content,
                        re.DOTALL
                    )
                    if dep_section:
                        for line in dep_section.group(1).strip().split("\n"):
                            line = line.strip()
                            if not line or line.startswith("#") or line.startswith("python"):
                                continue
                            match = re.match(
                                r'^([a-zA-Z0-9][a-zA-Z0-9_\-\.]*)\s*=\s*"([^"]+)"',
                                line
                            )
                            if match:
                                deps.append({
                                    "name": match.group(1),
                                    "version": match.group(2),
                                    "type": "poetry",
                                    "source": "pyproject.toml",
                                })
            except (IOError, Exception) as e:
                logger.warning(f"Error parsing pyproject.toml: {e}")
        
        elif dep_type == "pipenv":
            # Parse Pipfile using tomllib/tomli if available
            try:
                if tomllib is not None:
                    with open(file_path, "rb") as f:
                        data = tomllib.load(f)
                    for section_name in ["packages", "dev-packages"]:
                        section_data = data.get(section_name, {})
                        if not isinstance(section_data, dict):
                            continue
                        for name, spec in section_data.items():
                            if isinstance(spec, str):
                                version = spec
                            elif isinstance(spec, dict):
                                version = spec.get("version", "complex")
                            else:
                                version = "complex"
                            deps.append({
                                "name": name,
                                "version": version,
                                "type": "pipenv",
                                "source": "Pipfile",
                            })
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    for section_name in ["packages", "dev-packages"]:
                        section = re.search(
                            rf'\[{section_name}\](.*?)(?=\[|$)',
                            content,
                            re.DOTALL
                        )
                        if section:
                            for line in section.group(1).strip().split("\n"):
                                line = line.strip()
                                if not line or line.startswith("#"):
                                    continue
                                match = re.match(
                                    r'^([a-zA-Z0-9][a-zA-Z0-9_\-\.]*)\s*=\s*"([^"]+)"',
                                    line
                                )
                                if match:
                                    deps.append({
                                        "name": match.group(1),
                                        "version": match.group(2),
                                        "type": "pipenv",
                                        "source": "Pipfile",
                                    })
            except (IOError, Exception) as e:
                logger.warning(f"Error parsing Pipfile: {e}")
        
        elif dep_type == "bundler":
            # Parse Gemfile
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        
                        match = re.match(
                            r'^gem\s+["\']([a-zA-Z0-9][a-zA-Z0-9_\-\.]*)["\']'
                            r'(?:,\s*["\']([^"\']+)["\'])?',
                            line
                        )
                        if match:
                            deps.append({
                                "name": match.group(1),
                                "version": match.group(2) or "unspecified",
                                "type": "bundler",
                                "source": "Gemfile",
                            })
            except IOError as e:
                logger.warning(f"Error parsing Gemfile: {e}")
        
        elif dep_type == "composer":
            # Parse composer.json
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for key in ["require", "require-dev"]:
                    if key in data and isinstance(data[key], dict):
                        for name, version in data[key].items():
                            if name == "php":
                                continue
                            deps.append({
                                "name": name,
                                "version": str(version).replace("^", "").replace("~", ""),
                                "type": "composer",
                                "source": key,
                            })
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error parsing composer.json: {e}")
        
        return deps
    
    def _determine_security_level(
        self,
        overall_score: int,
        code_risk: int,
        dependency_risk: int,
        permissions_risk: int = 0,
        has_critical_code: bool = False,
        has_critical_dependency: bool = False,
    ) -> SecurityLevel:
        """Determine security level with four-tier cap logic.

        Tier 1: Explicit high-risk patterns (command_execution, eval-like deps)
                → hard cap at MEDIUM.
        Tier 2: Extreme single-dimension risk (permissions>=50, code>=50,
                dependency>=40) → cap at MEDIUM/LOW.
        Tier 3: Moderate-high single-dimension risk → cap at HIGH/MEDIUM.
        Tier 4: Score-based分级 (including CRITICAL for very low scores).

        Args:
            overall_score: Overall security score (0-100)
            code_risk: Code risk score (0-100)
            dependency_risk: Dependency risk score (0-100)
            permissions_risk: Permissions risk score (0-100)
            has_critical_code: True if command_execution patterns detected
            has_critical_dependency: True if eval-like dependencies detected

        Returns:
            SecurityLevel enum value
        """
        # Tier 1: Explicit high-risk patterns
        if has_critical_code or has_critical_dependency:
            return SecurityLevel.MEDIUM

        # Tier 2: Extreme single-dimension risk
        if permissions_risk >= 50 or code_risk >= 50 or dependency_risk >= 40:
            if overall_score >= 70:
                return SecurityLevel.MEDIUM
            return SecurityLevel.LOW

        # Tier 3: Moderate-high single-dimension risk
        if permissions_risk >= 30 or code_risk >= 30 or dependency_risk >= 25:
            if overall_score >= 80:
                return SecurityLevel.HIGH
            elif overall_score >= 50:
                return SecurityLevel.MEDIUM
            return SecurityLevel.LOW

        # Tier 4: Score-based分级
        if overall_score >= 90:
            return SecurityLevel.VERIFIED
        elif overall_score >= 75:
            return SecurityLevel.HIGH
        elif overall_score >= 50:
            return SecurityLevel.MEDIUM
        elif overall_score >= 20:
            return SecurityLevel.LOW
        elif overall_score >= 0:
            return SecurityLevel.UNKNOWN

        return SecurityLevel.CRITICAL
    
    def _collect_findings(self, report: SecurityReport, 
                          permissions_analysis: Dict[str, Any],
                          code_analysis: Dict[str, Any],
                          dependency_analysis: Dict[str, Any],
                          network_analysis: Dict[str, Any]) -> None:
        """Collect warnings and errors from analysis results.
        
        Populates the report's warnings and errors lists based on
        findings from all analysis dimensions.
        
        Args:
            report: SecurityReport to populate
            permissions_analysis: Results from permission analysis
            code_analysis: Results from code analysis
            dependency_analysis: Results from dependency analysis
            network_analysis: Results from network analysis
        """
        warnings = []
        errors = []
        
        # Permission warnings
        high_risk_perms = permissions_analysis.get("high_risk_permissions", [])
        if high_risk_perms:
            warnings.append(f"发现 {len(high_risk_perms)} 个高风险权限: {', '.join(high_risk_perms)}")
        
        missing_perms = permissions_analysis.get("missing_permissions", [])
        if missing_perms:
            warnings.append(f"工具可能使用了但未声明的权限: {', '.join(missing_perms)}")
        
        # Code warnings
        pattern_counts = code_analysis.get("pattern_counts", {})
        for pattern_type, count in pattern_counts.items():
            if count > 0:
                severity = "error" if pattern_type in ["command_execution", "data_exfiltration"] else "warning"
                msg = f"代码中发现 {count} 处 '{pattern_type}' 相关模式"
                if severity == "error":
                    errors.append(msg)
                else:
                    warnings.append(msg)
        
        # Dependency warnings
        risky_deps = dependency_analysis.get("risky_dependencies", [])
        if risky_deps:
            dep_names = [d["name"] for d in risky_deps]
            warnings.append(f"发现 {len(risky_deps)} 个风险依赖项: {', '.join(dep_names)}")
        
        # Dependency errors
        if dependency_analysis.get("total_risk", 0) >= 20:
            errors.append("依赖项存在严重安全风险，建议立即升级或替换")
        
        # Network warnings
        if network_analysis.get("has_network_access", False):
            risk_level = network_analysis.get("risk_level", "LOW")
            if risk_level == "HIGH":
                errors.append("工具具有不受限制的高风险网络访问权限")
            elif risk_level == "medium":
                warnings.append("工具具有中等风险的网络访问配置")
            
            endpoints = network_analysis.get("endpoints", [])
            if endpoints:
                for endpoint in endpoints:
                    if endpoint.startswith("http://") and not endpoint.startswith("http://localhost"):
                        warnings.append(f"端点使用未加密 HTTP: {endpoint}")
        
        # Network without declared permission
        if network_analysis.get("has_network_access", False) and \
           not network_analysis.get("declared_in_permissions", False):
            warnings.append("工具可能具有网络访问能力但未在权限中声明")
        
        report.warnings = warnings
        report.errors = errors
    
    def _create_error_report(self, tool_name: str, error_message: str) -> SecurityReport:
        """Create a minimal error report when scanning fails.

        Args:
            tool_name: Name of the tool that failed
            error_message: Error description

        Returns:
            SecurityReport with error status
        """
        return SecurityReport(
            tool_name=tool_name,
            overall_score=0,
            security_level=SecurityLevel.UNKNOWN,
            status="error",
            errors=[error_message],
            recommendations=[
                f"无法完成扫描: {error_message}",
                "请检查工具是否已正确安装并在注册表中注册",
            ],
        )
