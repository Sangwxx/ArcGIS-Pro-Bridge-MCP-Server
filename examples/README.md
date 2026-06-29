# 示例目录

这个目录里的文件，主要是给第一次使用项目的人准备的。

如果你已经把项目跑起来，但不知道下一步怎么接入客户端、怎么提问、怎么测试，可以先看这里。

## 文件说明

- `claude-desktop-mcp-config.json`
  - 适合 Claude Desktop 的 MCP 配置示例
  - **推荐使用 `cmd /c start-mcp-server.bat` 方式**，可避免 Windows 上 GUI 应用找不到 `uv` 的 PATH 问题

- `cursor-mcp-config.json`
  - 适合 Cursor / Trae 风格的 MCP 配置示例
  - 使用 `uv run` 方式

- `start-mcp-server.bat`（项目根目录）
  - Windows 批处理启动脚本
  - 自动在常见位置查找 `uv`，解决 GUI 应用 PATH 隔离问题
  - Claude Desktop 推荐通过此脚本启动

- `arcpy-buffer-example.py`
  - 一个最简单的 ArcPy Buffer 示例
  - 适合拿来确认 `execute_arcpy_code` 是否工作正常

- `prompt-examples.md`
  - 给 AI 客户端使用的中文提示词示例
  - 适合不熟悉这类工作方式的 GISer 直接复制使用

## 配置前必读

所有配置 JSON 中的 `<项目目录>` 都需要替换为你克隆项目的实际路径，例如：

- `D:\\GIS\\ArcGIS-Pro-Bridge-MCP-Server`
- `C:\\Users\\张三\\Projects\\ArcGIS-Pro-Bridge-MCP-Server`

不要直接复制 JSON 就用，否则服务无法启动。

## Claude Desktop 用户特别注意

Claude Desktop 是 Windows 原生 GUI 应用，它的 PATH 环境变量与终端不同。如果你在终端里能跑 `uv`，但 Claude Desktop 报连接失败，大概率是 PATH 问题。

**推荐方式**：使用 `claude-desktop-mcp-config.json` 中的 `cmd /c` + 批处理脚本方式，脚本会自动查找 `uv`。

**备选方式**：将 `uv` 所在目录（通常是 `%USERPROFILE%\\.local\\bin`）添加到 Windows **系统 PATH** 环境变量，然后可以像 Cursor 一样直接用 `uv run` 方式配置。
