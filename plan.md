# v0.2.0 Group 1: OSV NPM Query — 执行计划

## 目标
将安全扫描从"本地启发式评分"升级为"本地规则 + 在线OSV漏洞情报 + 策略判定"组合模型。

## 新增文件
1. `src/mcp_hub/vulnerability_models.py` — VulnerabilityEntry pydantic模型 + ScanResult
2. `src/mcp_hub/osv_client.py` — OSV API客户端（批量查询、单包查询、速率限制、重试、错误处理）
3. `src/mcp_hub/scan_cache.py` — 扫描缓存（TTL、手动失效、依赖变更检测）
4. `src/mcp_hub/dependency_mapper.py` — 依赖解析→OSV查询格式转换（npm/pip/cargo/go）
5. `src/mcp_hub/offline_vuln_db.py` — 本地SQLite漏洞数据库（离线降级）

## 修改文件
1. `src/mcp_hub/security.py` — 集成OSV扫描到SecurityScanner.scan()流程
2. `tests/test_security.py` — 新增OSV集成测试

## 执行顺序（Stage-Gate）

### Stage 1: 数据模型（独立）
- `vulnerability_models.py`: VulnerabilityEntry, ScanResult, SeverityLevel
- 使用 pydantic v2

### Stage 2: OSV API客户端（独立）
- `osv_client.py`: OSVClient类
  - 批量查询 /v1/querybatch
  - 单包查询 /v1/query
  - 速率限制（token bucket）
  - 重试机制（指数退避）
  - 错误处理（timeout, 404, 500, 429）
  - 网络不可用时抛出OSError，由调用方降级

### Stage 3: 依赖映射器（依赖Stage 1）
- `dependency_mapper.py`: 将package.json/requirements.txt等解析结果转为OSV查询格式
- 支持 npm, pip, cargo, go

### Stage 4: 扫描缓存（独立）
- `scan_cache.py`: TTL缓存 + 手动失效 + 依赖文件mtime检测

### Stage 5: 离线漏洞数据库（独立）
- `offline_vuln_db.py`: SQLite本地缓存，schema设计，查询接口

### Stage 6: 集成到security.py（依赖Stage 1-5）
- SecurityScanner新增OSV集成
- _check_dependencies调用OSV查询
- 网络不可用时降级为本地扫描
- 新增vulnerabilities字段到SecurityReport

### Stage 7: 测试
- mock API测试
- 离线降级测试
- 缓存失效测试
- 速率限制测试

## 代码风格
- black (line-width 100)
- ruff
- mypy strict mode
- pydantic v2
