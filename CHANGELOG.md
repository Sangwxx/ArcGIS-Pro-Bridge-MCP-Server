# Changelog

## 未发布

- 修复 MCP 配置示例中的硬编码路径，替换为 `<项目目录>` 占位符。
- 新增 `start-mcp-server.bat` 启动脚本，解决 Windows GUI 应用（Claude Desktop）找不到 `uv` 的 PATH 隔离问题。
- Claude Desktop 配置改用 `cmd /c` + 批处理脚本方式，避免 `uv` 不可见导致连接失败。
- README 补充 Claude Desktop 连接失败排查指南。

## 0.1.0 - 2026-04-04
- 初始化 ArcGIS Pro Bridge MCP Server 核心能力。
- 支持自动发现 ArcGIS Pro 安装路径与 Python 解释器。
- 支持通过子进程执行 ArcPy 代码并回收结构化结果。
- 提供工程图层、GDB 模式、`.aprx` 工程概览等 MCP Tool / Resource。
- 补充 GitHub 发布所需的示例、CI、贡献说明与安全说明。
