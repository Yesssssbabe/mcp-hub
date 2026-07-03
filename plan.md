# UAT Fix Plan — fix_install_client & comprehensive fixes

## 阶段 1: 基础设施修复 (constants.py, registry.py, config.py)
- [fix_path_consistency] 统一配置目录为 `~/.config/mcp-hub/`，回退 `~/.mcp-hub/`
- [fix_env_var] 读取 `MCP_HUB_CONFIG_DIR` 环境变量
- [fix_registry_builtin] 在 Registry 添加 `load_builtin_registry()` 方法

## 阶段 2: CLI 核心修复 (cli.py)
- [fix_init_registry] init() 创建 registry.json 并加载内置工具
- [fix_init_config] init() 创建默认 config.json
- [fix_init_force] 添加 --force 选项到 init
- [fix_init_configdir] 添加 --config-dir 选项到 init
- [fix_install_toolname] 支持 npm scope 包名 (@org/package)
- [fix_install_param] 修复参数传递
- [fix_install_client] 添加 --client 选项到 install
- [fix_install_dryrun] 添加 --dry-run 选项到 install
- [fix_install_force] 添加 --force 选项到 install
- [fix_install_method] 添加 --method 选项到 install
- [fix_scan_attr] 修复 report.level -> report.security_level
- [fix_scan_return] 修复 quick_scan() 返回类型
- [fix_scan_detailed] 添加 --detailed 选项到 scan
- [fix_scan_json] 添加 --json 选项到 scan
- [fix_scan_severity] 添加 --severity 选项到 scan
- [fix_scan_noarg] 支持无参数扫描所有已安装工具
- [fix_except_handler] 修复 except Exception 捕获 typer.Exit
- [fix_base_dir] 修复 --base-dir 路径验证逻辑
- [fix_version_global] 添加 --version 全局选项
- [fix_search_limit] 添加 --limit 选项到 search
- [fix_search_sort] 添加 --sort 选项到 search
- [fix_search_json] 添加 --json 选项到 search
- [fix_search_tag] 修复 --tag 别名
- [fix_list_category] 添加 --category 选项到 list
- [fix_list_json] 添加 --json 选项到 list
- [fix_list_installed] 修复 list --installed
- [fix_config_show] 添加 --show 选项到 config
- [fix_config_export] 添加 --export 选项到 config
- [fix_config_import] 添加 --import 选项到 config
- [fix_config_validate] 添加 --validate 选项到 config
- [fix_config_env] 添加 --env 选项到 config add
- [fix_uninstall_purge] 添加 --purge 选项到 uninstall
- [fix_uninstall_yes] 添加 --yes 选项到 uninstall
- [fix_empty_hint] 空注册表时添加引导提示
- [fix_log_prefix] 移除 config generate 的 [INFO] CLI: 前缀
- [fix_error_msg] 统一错误信息格式

## 阶段 3: 数据模型修复 (security.py, config.py)
- [fix_security_report] 修复 SecurityReport 字段名一致性
- [fix_config_data] 修复 config add/list/remove 数据模型一致性
- [fix_config_path] 修复 config add 命令 PATH 查找

## 阶段 4: 验证
- py_compile 所有文件
- 运行测试检查
