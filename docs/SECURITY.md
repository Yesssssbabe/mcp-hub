# MCP Hub 安全文档

> 本文档描述 MCP Hub 的安全扫描原理、评分算法和安全漏洞报告流程。

---

## 目录

- [安全扫描原理](#安全扫描原理)
- [评分算法说明](#评分算法说明)
- [如何报告安全漏洞](#如何报告安全漏洞)
- [安全更新策略](#安全更新策略)
- [安全最佳实践](#安全最佳实践)
- [安全扫描配置](#安全扫描配置)

---

## 安全扫描原理

MCP Hub 的安全扫描采用**多层防御**策略，从静态代码分析到动态行为检测，全方位评估 MCP 工具的安全风险。

### 安全扫描架构

```
┌─────────────────────────────────────────────┐
│              安全扫描引擎                    │
│                                             │
│  ┌─────────────┐    ┌─────────────┐       │
│  │ 静态分析器   │    │ 依赖扫描器   │       │
│  │  (Static)   │    │(Dependency) │       │
│  └──────┬──────┘    └──────┬──────┘       │
│         │                  │               │
│         ▼                  ▼               │
│  ┌─────────────────────────────────┐      │
│  │         权限分析器               │      │
│  │      (Permission)               │      │
│  └──────────────┬──────────────────┘      │
│                 │                          │
│                 ▼                          │
│  ┌─────────────────────────────────┐      │
│  │         评分引擎                 │      │
│  │      (Scoring Engine)          │      │
│  └──────────────┬──────────────────┘      │
│                 │                          │
│                 ▼                          │
│  ┌─────────────────────────────────┐      │
│  │         安全报告                 │      │
│  │      (Security Report)          │      │
│  └─────────────────────────────────┘      │
└─────────────────────────────────────────────┘
```

### 1. 静态代码分析（Static Analysis）

对工具源代码进行自动化的 AST（抽象语法树）分析，检测潜在的安全问题。

#### 检测维度

| 检测项 | 说明 | 严重级别 |
|--------|------|---------|
| **代码执行** | 检测 `eval()`, `exec()`, `subprocess.call()` 等危险函数 | 🔴 Critical |
| **文件操作** | 检测未限制路径的文件读写操作 | 🟠 High |
| **网络请求** | 检测未经验证的外部网络调用 | 🟡 Medium |
| **数据序列化** | 检测 `pickle.loads()`, `yaml.load()` 等不安全反序列化 | 🔴 Critical |
| **敏感信息** | 检测硬编码的 API 密钥、密码、Token | 🟠 High |
| **路径遍历** | 检测 `../` 等路径遍历漏洞 | 🟡 Medium |
| **SQL 注入** | 检测字符串拼接的 SQL 查询 | 🟠 High |
| **命令注入** | 检测用户输入拼接的 Shell 命令 | 🔴 Critical |

#### 示例检测

```python
# 会被标记为 Critical 的代码模式
import os; os.system(user_input)      # 命令注入
eval(expression)                        # 代码执行
pickle.loads(data)                      # 不安全的反序列化
subprocess.call(cmd, shell=True)        # Shell 命令执行

# 会被标记为 High 的代码模式
open(file_path, "w")  # 未限制路径的文件写入
requests.get(url)     # 未经验证的网络请求
```

### 2. 依赖漏洞扫描（Dependency Scanning）

分析工具的依赖树，比对已知漏洞数据库。

#### 漏洞数据源

| 数据源 | 覆盖范围 | 更新频率 |
|--------|---------|---------|
| **OSV (Open Source Vulnerabilities)** | npm, PyPI, Go, Rust | 实时 |
| **Snyk Vulnerability DB** | npm, PyPI, Docker | 每日 |
| **GitHub Security Advisories** | GitHub 生态 | 实时 |
| **NVD (National Vulnerability Database)** | 通用 CVE | 每日 |

#### 扫描流程

```
工具包/代码
    │
    ▼
┌─────────────┐
│  Extract    │─── 提取依赖清单（package.json, requirements.txt, etc.）
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Parse      │─── 解析依赖名称和版本
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Query DB   │─── 查询漏洞数据库
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  CVSS Score │─── 计算 CVSS 评分
└──────┬──────┘
       │
       ▼
    Vulnerability Report
```

### 3. 权限分析（Permission Analysis）

分析工具声明和实际使用的权限，检测权限过度授权。

#### 权限分类

| 权限类别 | 说明 | 风险等级 |
|----------|------|---------|
| `filesystem:read` | 读取文件 | 🟢 Low |
| `filesystem:write` | 写入文件 | 🟡 Medium |
| `filesystem:execute` | 执行文件 | 🟠 High |
| `network:local` | 本地网络访问 | 🟡 Medium |
| `network:internet` | 互联网访问 | 🟠 High |
| `code_execution` | 执行任意代码 | 🔴 Critical |
| `shell` | 执行 Shell 命令 | 🔴 Critical |
| `database:write` | 数据库写入 | 🟠 High |
| `environment` | 读取环境变量 | 🟡 Medium |

#### 权限评分规则

- 每个 Critical 权限：-20 分
- 每个 High 权限：-10 分
- 每个 Medium 权限：-5 分
- 每个 Low 权限：-2 分
- 权限声明与代码实际行为不一致：额外 -15 分

### 4. 行为分析（Behavioral Analysis）—— v0.2.0+

在隔离环境中运行工具，监控其实际行为：

- 文件系统访问模式
- 网络连接目标
- 子进程创建
- 环境变量读取
- 系统调用序列

---

## 评分算法说明

### 综合评分公式

安全评分是一个 0-100 的整数，计算公式如下：

```
Score = Base(100)
        - StaticPenalty     (静态分析扣分)
        - DependencyPenalty   (依赖漏洞扣分)
        - PermissionPenalty   (权限扣分)
        - TrustPenalty        (信任度扣分)
        + Bonus               (加分项)
```

### 各维度权重

| 维度 | 权重 | 说明 |
|------|------|------|
| **静态分析** | 30% | 代码中的危险模式 |
| **依赖安全** | 25% | 已知漏洞和依赖风险 |
| **权限范围** | 25% | 工具权限的广度 |
| **信任度** | 20% | 来源可信度和社区验证 |

### 详细评分规则

#### 1. 静态分析扣分（StaticPenalty）

| 发现级别 | 扣分 | 上限 |
|----------|------|------|
| Critical | -15/个 | -45 |
| High | -8/个 | -24 |
| Medium | -4/个 | -12 |
| Low | -2/个 | -6 |

#### 2. 依赖漏洞扣分（DependencyPenalty）

| CVSS 评分 | 扣分 | 说明 |
|-----------|------|------|
| 9.0-10.0 | -20/个 | 严重漏洞 |
| 7.0-8.9 | -12/个 | 高危漏洞 |
| 4.0-6.9 | -6/个 | 中危漏洞 |
| 0.1-3.9 | -2/个 | 低危漏洞 |
| 依赖无版本锁定 | -5 | 使用浮动版本 |
| 依赖已废弃 | -3/个 | 使用废弃包 |

#### 3. 权限扣分（PermissionPenalty）

| 权限类型 | 扣分 |
|----------|------|
| `code_execution` | -20 |
| `shell` | -20 |
| `filesystem:execute` | -15 |
| `network:internet` | -12 |
| `database:write` | -10 |
| `filesystem:write` | -8 |
| `network:local` | -5 |
| `environment` | -3 |
| `filesystem:read` | -2 |
| `database:read` | -2 |

#### 4. 信任度扣分（TrustPenalty）

| 因素 | 扣分/加分 | 说明 |
|------|----------|------|
| 非官方维护 | -10 | 非原始作者维护 |
| 无维护（>1年未更新） | -15 | 项目已废弃 |
| 下载量 < 100 | -5 | 未经验证的包 |
| 无测试套件 | -5 | 缺乏质量保证 |
| 官方维护 | +5 | 原始作者维护 |
| 社区验证（>1000 Stars） | +5 | 广泛社区使用 |
| 安全审计报告 | +10 | 通过第三方审计 |

#### 5. 加分项（Bonus）

| 因素 | 加分 | 说明 |
|------|------|------|
| 使用 Docker 隔离 | +5 | 提供容器化运行 |
| 最小权限设计 | +5 | 仅声明必要权限 |
| 输入验证 | +5 | 全面的输入校验 |
| 沙箱运行 | +10 | 内置沙箱机制 |

### 评分示例

```
工具：@modelcontextprotocol/server-filesystem

基础分：100

静态分析：
  - 无危险模式发现
  扣分：0

依赖扫描：
  - 依赖安全，无已知漏洞
  扣分：0

权限分析：
  - filesystem:read  (-2)
  - filesystem:write  (-8)
  扣分：-10

信任度：
  - 官方维护  (+5)
  - 社区验证  (+5)
  加分：+10

总分：100 - 0 - 0 - 10 + 10 = 100 ✅
```

```
工具：community-tool-with-risks

基础分：100

静态分析：
  - 发现 eval() 调用 (Critical)  (-15)
  - 发现 subprocess.call() (High)  (-8)
  扣分：-23

依赖扫描：
  - 存在 1 个高危漏洞 (CVSS 7.5)  (-12)
  - 使用浮动版本  (-5)
  扣分：-17

权限分析：
  - shell  (-20)
  - network:internet  (-12)
  - filesystem:write  (-8)
  扣分：-40

信任度：
  - 非官方维护  (-10)
  - 无测试套件  (-5)
  扣分：-15

总分：100 - 23 - 17 - 40 - 15 = 5 🔴 (高风险)
```

### 评分等级

| 分数 | 等级 | 图标 | 说明 |
|------|------|------|------|
| 90-100 | 极安全 | 🟢 | 可以放心使用 |
| 70-89 | 较安全 | 🟡 | 注意使用场景 |
| 50-69 | 需谨慎 | 🟠 | 建议审查代码 |
| 0-49 | 高风险 | 🔴 | 强烈不建议使用 |

---

## 如何报告安全漏洞

### 报告流程

我们非常重视安全问题。如果你发现了安全漏洞，请按照以下流程报告：

```
发现漏洞
    │
    ▼
┌─────────────────┐
│ 不要公开披露！  │─── 不要在 GitHub Issues 公开报告
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 发送邮件至      │─── security@mcp-hub.dev
│ security@       │    (或 GitHub Security Advisory)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 包含信息：      │
│ • 漏洞描述      │
│ • 复现步骤      │
│ • 影响范围      │
│ • 建议修复方案  │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 等待确认        │─── 48 小时内回复确认
│ (48小时内)      │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ 修复和披露      │─── 修复后协调公开披露
└─────────────────┘
```

### 报告模板

```
主题：Security Vulnerability Report - [简要描述]

漏洞类型：[远程代码执行 / 权限提升 / 信息泄露 / 其他]

影响版本：[受影响的版本范围]

严重性：[Critical / High / Medium / Low]

描述：
[详细描述漏洞原理和影响]

复现步骤：
1. [步骤 1]
2. [步骤 2]
3. [步骤 3]

概念验证：
[如果有 PoC 代码，请附上]

建议修复：
[如有修复建议，请说明]

 reporter 信息：
- 名称/昵称：[你的名字]
- 联系方式：[邮箱或其他联系方式]
- 是否允许公开署名：[是 / 否]
```

### 安全漏洞响应时间

| 严重级别 | 初始响应 | 修复目标 | 公开披露 |
|----------|---------|---------|---------|
| Critical | 24 小时 | 7 天 | 修复后 30 天 |
| High | 48 小时 | 14 天 | 修复后 30 天 |
| Medium | 72 小时 | 30 天 | 修复后 30 天 |
| Low | 7 天 | 60 天 | 修复后 30 天 |

### 安全公告

所有安全修复将通过以下渠道发布：

- GitHub Security Advisories
- 项目 Releases 页面（标记为 security fix）
- 邮件列表通知（如订阅）

---

## 安全更新策略

### 漏洞数据库更新

MCP Hub 的安全扫描依赖外部漏洞数据库，更新策略如下：

| 数据库 | 更新频率 | 本地缓存 |
|--------|---------|---------|
| OSV | 实时查询 + 每日同步 | 24 小时 |
| Snyk | 每日同步 | 24 小时 |
| GitHub Advisories | 实时查询 | 12 小时 |
| NVD | 每日同步 | 24 小时 |

### 安全规则更新

安全扫描规则（静态分析规则）通过以下方式更新：

1. **内置规则**：随版本发布更新
2. **远程规则**：支持从远程 URL 加载最新规则（需配置 `MCP_HUB_SECURITY_RULES_URL`）
3. **自定义规则**：用户可通过配置文件添加自定义规则

### 安全扫描缓存策略

```
首次扫描工具
    │
    ▼
执行完整扫描
    │
    ▼
缓存结果（24 小时）
    │
    ▼
再次扫描同一工具
    │
    ▼
检查缓存是否有效
    │
    ├─ 有效 → 返回缓存结果（< 100ms）
    │
    └─ 过期 → 重新扫描（更新漏洞数据库后）
```

### 强制重新扫描

```bash
# 忽略缓存，强制重新扫描
mcp-hub scan <tool> --force

# 更新漏洞数据库后重新扫描所有工具
mcp-hub scan --all --refresh-db
```

---

## 安全最佳实践

### 对于工具使用者

1. **安装前扫描**
   ```bash
   mcp-hub scan <tool> --detailed
   ```

2. **限制工具权限**
   - 使用 `--read-only` 选项限制文件系统工具
   - 使用 `--no-network` 禁止网络访问
   - 指定允许访问的目录

3. **隔离运行**
   ```bash
   # 使用 Docker 方式安装，增加隔离性
   mcp-hub install <tool> --method docker
   ```

4. **定期审查**
   ```bash
   # 扫描所有已安装工具
   mcp-hub scan --all
   
   # 检查可更新工具（可能包含安全修复）
   mcp-hub list --outdated
   ```

5. **监控日志**
   ```bash
   # 查看工具运行日志
   mcp-hub logs <tool>
   ```

### 对于工具开发者

1. **最小权限原则**
   - 只声明必要的权限
   - 使用 `filesystem:read` 而不是 `filesystem:write` 如果不需要写入
   - 避免 `code_execution` 和 `shell` 权限

2. **输入验证**
   - 对所有用户输入进行验证和清理
   - 使用白名单而非黑名单
   - 限制文件路径到指定目录

3. **安全编码**
   - 避免使用 `eval()`, `exec()`
   - 使用参数化查询而非字符串拼接 SQL
   - 验证所有外部 URL

4. **依赖管理**
   - 锁定依赖版本（package-lock.json, requirements.txt）
   - 定期更新依赖
   - 使用 `npm audit` / `pip-audit` 检查依赖漏洞

5. **提供安全信息**
   - 在 README 中明确说明权限需求
   - 提供安全最佳实践文档
   - 响应安全报告

---

## 安全扫描配置

### 配置文件

安全扫描可以通过配置文件自定义：

```toml
# ~/.config/mcp-hub/security.toml
[scan]
# 默认扫描级别：basic | standard | deep
level = "standard"

# 是否自动扫描新安装的工具
auto_scan = true

# 最低安全评分阈值（低于此评分拒绝安装）
min_score = 50

# 是否阻止 Critical 级别问题
deny_critical = true

# 自定义漏洞数据库 URL
vuln_db_url = "https://custom-vuln-db.example.com/api"

[scan.rules]
# 启用/禁用特定规则
enable_all = true
disable = ["rule-id-1", "rule-id-2"]

# 自定义规则
[[scan.rules.custom]]
id = "custom-rule-1"
name = "Custom Security Check"
pattern = "dangerous_function\s*\("
severity = "high"
message = "检测到危险函数调用"
```

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MCP_HUB_SECURITY_LEVEL` | 默认扫描级别 | `standard` |
| `MCP_HUB_SECURITY_MIN_SCORE` | 最低安全评分 | `50` |
| `MCP_HUB_SECURITY_AUTO_SCAN` | 自动扫描 | `true` |
| `MCP_HUB_SECURITY_DENY_CRITICAL` | 阻止 Critical | `true` |
| `MCP_HUB_SECURITY_RULES_URL` | 自定义规则 URL | `None` |
| `MCP_HUB_VULN_DB_CACHE_HOURS` | 漏洞数据库缓存 | `24` |

### 命令行选项

```bash
# 指定扫描级别
mcp-hub scan <tool> --level basic
mcp-hub scan <tool> --level standard
mcp-hub scan <tool> --level deep

# 跳过特定检查
mcp-hub scan <tool> --skip-dependency
mcp-hub scan <tool> --skip-static

# 忽略缓存
mcp-hub scan <tool> --force

# 安装时跳过安全扫描（不推荐）
mcp-hub install <tool> --no-scan
```

---

## 安全审计日志

MCP Hub 记录所有安全相关的操作：

```bash
# 查看安全日志
mcp-hub logs --security

# 查看特定工具的安全历史
mcp-hub logs <tool> --security
```

日志内容包含：

- 扫描时间戳
- 工具标识符
- 扫描结果摘要
- 发现的漏洞列表
- 评分变化
- 用户操作（安装/更新/移除）

---

*本文档最后更新于 2025 年。安全策略和扫描规则会随版本更新，请保持 MCP Hub 为最新版本。*
