"""Tests for mcp_hub.security module."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_hub.registry import MCPTool, Registry
from mcp_hub.security import SecurityScanner, SecurityReport, SecurityLevel


def make_tool(**kwargs):
    defaults = {
        "name": "test-tool",
        "display_name": "Test Tool",
        "description": "desc",
        "install_type": "npm",
        "install_command": "npx test-tool",
        "author": "a",
        "repository": "https://github.com/a/b",
    }
    defaults.update(kwargs)
    return MCPTool(**defaults)


class TestSecurityReport:
    """Test SecurityReport dataclass."""

    def test_create_default(self):
        report = SecurityReport(tool_name="test", overall_score=50, security_level=SecurityLevel.MEDIUM)
        assert report.tool_name == "test"
        assert report.overall_score == 50
        assert report.security_level == SecurityLevel.MEDIUM
        assert report.warnings == []
        assert report.errors == []
        assert report.recommendations == []

    def test_to_dict(self):
        report = SecurityReport(tool_name="test", overall_score=80, security_level=SecurityLevel.HIGH)
        d = report.to_dict()
        assert d["tool_name"] == "test"
        assert d["overall_score"] == 80
        assert d["security_level"] == "HIGH"
        assert "permissions_analysis" in d

    def test_to_dict_with_lists(self):
        report = SecurityReport(
            tool_name="test",
            overall_score=80,
            security_level=SecurityLevel.HIGH,
            warnings=["w1"],
            recommendations=["r1"],
        )
        d = report.to_dict()
        assert d["warnings"] == ["w1"]
        assert d["recommendations"] == ["r1"]


class TestSecurityScannerInit:
    """Test SecurityScanner initialization."""

    def test_init(self):
        scanner = SecurityScanner()
        assert scanner.registry is not None

    def test_init_with_registry(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        scanner = SecurityScanner(registry=registry)
        assert scanner.registry is registry


class TestSecurityScannerScan:
    """Test SecurityScanner.scan method."""

    def test_scan_tool_not_found(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        report = scanner.scan("nonexistent")
        assert report.overall_score == 0
        assert "not found" in report.errors[0].lower()

    def test_scan_safe_tool(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="safe", permissions=["filesystem:read"]))
        scanner = SecurityScanner(registry=registry)
        report = scanner.scan("safe", detailed=False)
        assert report.overall_score > 50
        assert report.security_level in [SecurityLevel.MEDIUM, SecurityLevel.HIGH, SecurityLevel.VERIFIED]

    def test_scan_dangerous_permissions(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="dangerous", permissions=["filesystem:execute", "network:all"]))
        scanner = SecurityScanner(registry=registry)
        report = scanner.scan("dangerous", detailed=False)
        assert report.overall_score <= 100

    def test_scan_with_installed_source(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        install_dir = tmp_path / "installed" / "src-tool"
        install_dir.mkdir(parents=True)
        # NOTE: The following text is intentionally crafted to simulate malicious code patterns
        # for static AST analysis only. It MUST NOT be executed via exec() or eval().
        (install_dir / "main.py").write_text("import os\nos.system('ls')\n")
        registry.add(make_tool(
            name="src-tool",
            is_installed=True,
            install_path=str(install_dir),
            permissions=["filesystem:read"],
        ))
        scanner = SecurityScanner(registry=registry)
        report = scanner.scan("src-tool", detailed=True)
        assert report.code_analysis["files_scanned"] > 0

    def test_scan_quick(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="quick", permissions=[]))
        scanner = SecurityScanner(registry=registry)
        score = scanner.quick_scan("quick")
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_scan_compare_tools(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="a", permissions=["filesystem:read"]))
        registry.add(make_tool(name="b", permissions=["filesystem:execute"]))
        scanner = SecurityScanner(registry=registry)
        reports = scanner.compare_tools(["a", "b"])
        assert len(reports) == 2
        assert "a" in reports and "b" in reports

    def test_scan_compare_tools_with_error(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="ok", permissions=[]))
        scanner = SecurityScanner(registry=registry)
        reports = scanner.compare_tools(["ok", "missing"])
        assert "missing" in reports
        assert reports["missing"].errors


class TestSecurityScannerCheckPrerequisites:
    """Test check_prerequisites."""

    def test_check_prerequisites(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        preqs = scanner.check_prerequisites()
        assert isinstance(preqs, dict)
        assert "npm_audit" in preqs
        assert "python_ast" in preqs

    def test_check_prerequisites_caching(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        p1 = scanner.check_prerequisites()
        p2 = scanner.check_prerequisites()
        assert p1 == p2


class TestSecurityScannerRecommendations:
    """Test generate_recommendations."""

    def test_recommendations_critical(self):
        report = SecurityReport(
            tool_name="test",
            overall_score=20,
            security_level=SecurityLevel.LOW,
            permissions_analysis={"total_risk_score": 30, "high_risk_permissions": ["p1"]},
            code_analysis={"total_risk_score": 30, "pattern_counts": {"command_execution": 3}},
            dependency_analysis={"total_risk": 15, "risky_dependencies": [{"name": "bad"}], "outdated_dependencies": [{"name": "old"}]},
            network_analysis={"has_network_access": True, "risk_level": "high", "endpoints": ["http://a.com"]},
        )
        scanner = SecurityScanner()
        recs = scanner.generate_recommendations(report)
        assert len(recs) > 0
        assert any("CRITICAL" in r for r in recs)

    def test_recommendations_good(self):
        report = SecurityReport(
            tool_name="test",
            overall_score=95,
            security_level=SecurityLevel.VERIFIED,
            permissions_analysis={"total_risk_score": 0, "high_risk_permissions": []},
            code_analysis={"total_risk_score": 0, "pattern_counts": {}},
            dependency_analysis={"total_risk": 0, "risky_dependencies": [], "outdated_dependencies": []},
            network_analysis={"has_network_access": False},
        )
        scanner = SecurityScanner()
        recs = scanner.generate_recommendations(report)
        assert len(recs) > 0
        assert any("LOW" in r for r in recs)

    def test_recommendations_empty(self):
        report = SecurityReport(
            tool_name="test",
            overall_score=50,
            security_level=SecurityLevel.MEDIUM,
            permissions_analysis={"total_risk_score": 0, "high_risk_permissions": []},
            code_analysis={"total_risk_score": 0, "pattern_counts": {}},
            dependency_analysis={"total_risk": 0, "risky_dependencies": [], "outdated_dependencies": []},
            network_analysis={"has_network_access": False},
        )
        scanner = SecurityScanner()
        recs = scanner.generate_recommendations(report)
        assert len(recs) > 0


class TestSecurityScannerInternal:
    """Test internal methods."""

    def test_analyze_permissions(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="perm", permissions=["filesystem:write", "network:fetch"]))
        scanner = SecurityScanner(registry=registry)
        tool = registry.get("perm")
        result = scanner._analyze_permissions(tool)
        assert "total_risk_score" in result
        assert result["declared_count"] == 2

    def test_analyze_permissions_empty(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="no-perm", permissions=[]))
        scanner = SecurityScanner(registry=registry)
        result = scanner._analyze_permissions(registry.get("no-perm"))
        assert result["total_risk_score"] == 0

    def test_analyze_network_access(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="net", permissions=["network:all"]))
        scanner = SecurityScanner(registry=registry)
        result = scanner._analyze_network_access(registry.get("net"))
        assert result["has_network_access"] is True

    def test_analyze_network_access_no_network(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="no-net", permissions=["filesystem:read"]))
        scanner = SecurityScanner(registry=registry)
        result = scanner._analyze_network_access(registry.get("no-net"))
        assert result["has_network_access"] is False

    def test_scan_source_code_not_installed(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="not-installed"))
        scanner = SecurityScanner(registry=registry)
        result = scanner._scan_source_code(registry.get("not-installed"), None, detailed=False)
        assert result["status"] == "not_installed"

    def test_check_dependencies_not_installed(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="no-deps"))
        scanner = SecurityScanner(registry=registry)
        result = scanner._check_dependencies(registry.get("no-deps"), None)
        assert result["status"] == "not_installed"

    def test_calculate_score(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        score = scanner._calculate_score(10, 20, 5, 5)
        assert 0 <= score <= 100

    def test_determine_security_level(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        assert scanner._determine_security_level(95, 0, 0) == SecurityLevel.VERIFIED
        assert scanner._determine_security_level(80, 5, 5) == SecurityLevel.HIGH
        assert scanner._determine_security_level(50, 20, 10) == SecurityLevel.MEDIUM
        assert scanner._determine_security_level(20, 30, 20) == SecurityLevel.LOW

    def test_create_error_report(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        report = scanner._create_error_report("test", "error msg")
        assert report.tool_name == "test"
        assert "error msg" in report.errors[0]

    def test_parse_dependency_file_package_json(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        pkg = tmp_path / "package.json"
        pkg.write_text('{"dependencies": {"lodash": "^4.0.0"}}')
        deps = scanner._parse_dependency_file(pkg, "npm")
        assert any(d["name"] == "lodash" for d in deps)

    def test_parse_dependency_file_requirements(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        req = tmp_path / "requirements.txt"
        req.write_text("requests>=2.0\nnumpy==1.0\n")
        deps = scanner._parse_dependency_file(req, "pip")
        assert len(deps) == 2

    def test_parse_dependency_file_unknown(self, tmp_path):
        scanner = SecurityScanner(Registry(registry_path=str(tmp_path / "reg.json")))
        f = tmp_path / "unknown.txt"
        f.write_text("x")
        deps = scanner._parse_dependency_file(f, "unknown")
        assert deps == []


class TestScanSourceCodeBoundaries:
    """Test _scan_source_code boundary conditions."""

    def test_scan_source_code_max_files(self, tmp_path):
        scanner = SecurityScanner()
        install_dir = tmp_path / "src"
        install_dir.mkdir()
        for i in range(510):
            (install_dir / f"file{i}.py").write_text("x = 1\n")
        tool = make_tool(name="max-files", is_installed=True, install_path=str(install_dir))
        result = scanner._scan_source_code(tool, str(install_dir), detailed=False)
        assert result["files_scanned"] <= scanner.MAX_FILES_PER_SCAN
        assert result["files_skipped"] > 0

    def test_scan_source_code_skips_binary(self, tmp_path):
        scanner = SecurityScanner()
        install_dir = tmp_path / "src"
        install_dir.mkdir()
        binary_file = install_dir / "binary.so"
        binary_file.write_bytes(b"\x00\x01\x02\x03")
        py_file = install_dir / "valid.py"
        py_file.write_text("x = 1\n")
        tool = make_tool(name="binary-skip", is_installed=True, install_path=str(install_dir))
        result = scanner._scan_source_code(tool, str(install_dir), detailed=False)
        assert result["files_scanned"] == 1
        assert result["status"] == "completed"

    def test_scan_source_code_skip_dirs(self, tmp_path):
        scanner = SecurityScanner()
        install_dir = tmp_path / "src"
        install_dir.mkdir()
        node_modules = install_dir / "node_modules"
        node_modules.mkdir()
        (node_modules / "bad.js").write_text("os.system('rm -rf /')\n")
        (install_dir / "valid.py").write_text("x = 1\n")
        tool = make_tool(name="skip-dirs", is_installed=True, install_path=str(install_dir))
        result = scanner._scan_source_code(tool, str(install_dir), detailed=False)
        assert result["files_scanned"] == 1
        assert result["pattern_counts"]["command_execution"] == 0

    def test_scan_source_code_detailed_snippets(self, tmp_path):
        scanner = SecurityScanner()
        install_dir = tmp_path / "src"
        install_dir.mkdir()
        (install_dir / "script.py").write_text("import os\nos.system('ls')\n")
        tool = make_tool(name="detailed", is_installed=True, install_path=str(install_dir))
        result = scanner._scan_source_code(tool, str(install_dir), detailed=True)
        assert result["status"] == "completed"
        matches = result["pattern_matches"]["command_execution"]
        assert len(matches) > 0
        assert "os.system" in matches[0]["snippet"]


class TestCheckRequiredPermissions:
    """Test _check_required_permissions."""

    def test_missing_filesystem_permission(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="missing-fs"))
        scanner = SecurityScanner(registry=registry)
        tool = registry.get("missing-fs")
        object.__setattr__(tool, "config", {"file_path": "/tmp/test"})
        missing = scanner._check_required_permissions(tool)
        assert "filesystem" in missing

    def test_missing_network_permission(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="missing-net"))
        scanner = SecurityScanner(registry=registry)
        tool = registry.get("missing-net")
        object.__setattr__(tool, "config", {"url": "http://example.com"})
        missing = scanner._check_required_permissions(tool)
        assert "network" in missing

    def test_missing_command_permission(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="missing-cmd"))
        scanner = SecurityScanner(registry=registry)
        tool = registry.get("missing-cmd")
        object.__setattr__(tool, "config", {"command": "ls -la"})
        missing = scanner._check_required_permissions(tool)
        assert "command_execution" in missing


class TestAnalyzePermissionsExtended:
    """Extended permission analysis tests."""

    def test_analyze_permissions_medium_risk(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="medium", permissions=["filesystem:read", "network:connect"]))
        scanner = SecurityScanner(registry=registry)
        result = scanner._analyze_permissions(registry.get("medium"))
        assert result["total_risk_score"] > 0
        assert result["declared_count"] == 2

    def test_analyze_network_access_http_endpoint(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="http"))
        scanner = SecurityScanner(registry=registry)
        tool = registry.get("http")
        object.__setattr__(tool, "config", {"endpoints": ["http://example.com/api"]})
        result = scanner._analyze_network_access(tool)
        assert result["has_network_access"] is True
        assert any("http://example.com" in e for e in result["endpoints"])
        assert result["risk_score"] > 0

    def test_analyze_network_access_wildcard(self, tmp_path):
        registry = Registry(registry_path=str(tmp_path / "reg.json"))
        registry.add(make_tool(name="wildcard"))
        scanner = SecurityScanner(registry=registry)
        tool = registry.get("wildcard")
        object.__setattr__(tool, "config", {"endpoints": ["https://*.example.com"]})
        result = scanner._analyze_network_access(tool)
        assert result["risk_score"] > 0
        assert "*" in result["endpoints"][0]
