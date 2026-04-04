# ArcGIS Pro Bridge MCP Server

ArcGIS Pro Bridge MCP Server 是一个给 ArcGIS Pro 用的本地 MCP Server。

它的作用可以直接理解成：

- 让 Trae、Cursor、Claude Desktop 这类支持 MCP 的 AI 客户端，能够读取你本机的 ArcGIS Pro 工程信息
- 让 AI 能在 ArcGIS Pro 自带的 Python 环境中执行 ArcPy
- 尽量减少 GISer 手动折腾 Python 环境的成本

这个项目不是 ArcGIS Pro 插件，也不是双击就能打开的桌面软件。它更像一个“后台桥接服务”，由 AI 客户端按 MCP 方式调用。

## 它适合做什么

当前版本适合这些场景：

- 读取当前 ArcGIS Pro 工程中的地图和图层
- 检查哪些图层的数据源已经断开
- 读取 `.aprx` 工程中的布局、地图框和默认地图候选
- 读取 `.gdb` 的要素类、字段和空间参考
- 让 AI 生成 ArcPy 脚本
- 让 AI 执行 Buffer、Clip、Merge 等 ArcPy 地理处理

## 它不适合做什么

当前版本不适合直接用于这些场景：

- 对公网开放的远程 GIS 服务
- 无人值守地直接修改生产数据
- 替代 ArcGIS Pro 图形界面
- 当作通用文件管理工具浏览任意本地目录

它的定位是“本机上的 ArcGIS Pro AI 桥接工具”，不是通用桌面助手。

## 使用前需要准备什么

请先确认：

- 你使用的是 Windows
- 你的电脑已经安装 ArcGIS Pro
- ArcGIS Pro 可以正常启动
- 你的电脑中有 Python 3.11 或更高版本
- 建议安装 `uv`

## 最容易误解的地方

这是最重要的一节。

### 1. MCP 配置里的 JSON 不是命令行命令

README 或 `examples/` 目录里提供的 JSON 配置，不是复制到 PowerShell 或 CMD 里直接运行的。

这些 JSON 的正确用途是：

- 粘贴到 Trae 的 MCP 配置界面
- 或写入 Cursor / Claude Desktop 的 MCP 配置文件

如果你把 JSON 直接复制到命令行里运行，是不会按预期工作的。

### 2. `uv run arcgis_mcp_server.py` 不是给你长期手动测试 stdout 用的

这条命令的作用是启动一个 `stdio` 型 MCP Server。

它启动后会一直等待客户端请求，这是正常现象，不是卡死。

正常使用时，一般应由 Trae、Cursor、Claude Desktop 自动拉起它，而不是你手动先开一个终端，再自己写测试脚本去读 stdout。

### 3. 这个项目主要是 ArcGIS MCP，不是文件系统 MCP

它擅长的问题是：

- ArcGIS 环境是否发现成功
- `.aprx` 工程里有什么
- `.gdb` 里有什么
- ArcPy 能不能执行

它不适合用来回答：

- 当前项目目录里有什么文件
- 帮我列出任意本地目录结构

这类需求更适合 shell 或单独的文件系统 MCP。

## 正确使用流程

建议按下面顺序使用：

1. 获取项目并进入项目目录
2. 运行 `uv sync`
3. 把 MCP 配置 JSON 填到 Trae / Cursor / Claude Desktop 的 MCP 配置里
4. 重启客户端，或刷新 MCP Server 列表
5. 在聊天中直接让 AI 调用 MCP Tool

## 不推荐的错误流程

这些做法很容易导致“看起来卡住”：

- 把 MCP 配置 JSON 当成命令行命令去运行
- 手动启动 `uv run arcgis_mcp_server.py` 后，再自己写 Python 脚本去测试 stdout
- 明明要测试 ArcGIS MCP，却问“当前目录下有哪些文件”
- 没有明确要求 AI 使用 MCP，结果它自己转去走 shell

## 快速开始

### 第一步：安装依赖

进入项目目录后，运行 `uv sync`。

注意：

- `arcpy` 不会通过 `uv` 安装
- `arcpy` 来自 ArcGIS Pro 自带环境
- 本项目会在运行时自动寻找它

### 第二步：把 MCP 配置加到客户端

具体可复制配置请看：

- [examples/cursor-mcp-config.json](examples/cursor-mcp-config.json)
- [examples/claude-desktop-mcp-config.json](examples/claude-desktop-mcp-config.json)
- [examples/README.md](examples/README.md)

### 第三步：重启客户端

无论是 Trae、Cursor 还是 Claude Desktop，配置完成后都建议完全重启一次。

### 第四步：先做最简单的测试

第一次不要直接让 AI 做复杂分析。

建议先让它只调用：

- `detect_arcgis_environment`

确认 ArcGIS Pro 已被正确发现后，再继续读取工程和 GDB。

## 如何接入 Trae

Trae 里最关键的是要理解：

- 你填的是 MCP 配置
- 不是终端命令

### 正确做法

1. 打开 Trae 的 MCP 配置页面
2. 新增一个本地 MCP Server
3. 把示例 JSON 粘贴到 MCP 配置区域
4. 保存配置
5. 重启 Trae，或者刷新 MCP 列表

可参考：

- [examples/cursor-mcp-config.json](examples/cursor-mcp-config.json)

如果你的 Trae 已经显示服务名称，并且旁边是绿色勾，通常说明：

- 配置格式基本正确
- Trae 能识别这个 MCP Server

但这还不代表当前这次对话一定已经真正调用了 MCP Tool。

## 如何接入 Cursor

Cursor 的思路和 Trae 类似，也是把 MCP 配置写入它的 MCP 配置位置，而不是复制到终端。

建议做法：

1. 打开 Cursor 的 MCP 配置入口
2. 新增一个本地 `stdio` MCP Server
3. 填入示例 JSON
4. 保存并重启 Cursor，或刷新工具列表

可参考：

- [examples/cursor-mcp-config.json](examples/cursor-mcp-config.json)

## 如何接入 Claude Desktop

Claude Desktop 一般也是通过 MCP 配置文件接入。

建议做法：

1. 找到 Claude Desktop 的 MCP 配置文件
2. 把示例 JSON 加到 `mcpServers`
3. 保存文件
4. 完全退出 Claude Desktop
5. 重新打开 Claude Desktop

可参考：

- [examples/claude-desktop-mcp-config.json](examples/claude-desktop-mcp-config.json)

## 第一次使用时建议怎么问

第一次测试，建议问题尽量简单、尽量像 ArcGIS 问题，而不是“帮我测试 server”。

推荐顺序：

1. 先检测 ArcGIS 环境
2. 再读取当前工程图层
3. 再读取指定 GDB
4. 再读取指定 `.aprx` 工程概览
5. 最后再让 AI 生成或执行 ArcPy

更多可直接复制的中文提示词见：

- [examples/prompt-examples.md](examples/prompt-examples.md)

## 如何判断 AI 是否真的调用了 MCP

这也是非常关键的一节。

### 如果 AI 真正调用了 MCP

通常会出现这些特征：

- 直接返回 `detect_arcgis_environment`、`inspect_gdb`、`inspect_project_context` 等结果
- 结果内容明显是 ArcGIS 结构化信息
- 不会自己去写测试脚本
- 不会要求你手动长期开着一个 server 窗口读 stdout

### 如果 AI 没有真正调用 MCP

通常会出现这些特征：

- 它开始自己写 `test_mcp_server.py`、`inspect_gdb.py` 之类的脚本
- 它在终端里手动运行 `uv run arcgis_mcp_server.py`
- 它尝试自己解析 stdout
- 过程看起来“卡住很久”

如果出现这些现象，通常不是 ArcGIS 真的慢，而是它没有按 MCP 协议去使用这个服务。

## 推荐给 Trae 的测试提示词

如果你怀疑 Trae 没真正走 MCP，可以直接复制这段话给它：

“不要使用 shell，不要写任何测试脚本，不要手动启动任何 server。只允许使用已经配置好的 MCP 工具。请直接调用 `detect_arcgis_environment`，并把返回结果完整告诉我。如果你没有实际调用 MCP 工具，请明确说明。” 

这段提示词的作用，是强制它别绕去 shell 路线。

## 常见使用场景

你可以这样使用它：

- 先让 AI 读取当前 ArcGIS Pro 工程中的地图、图层和字段
- 让 AI 检查哪些图层断开了数据源
- 让 AI 读取某个 `.aprx` 工程的布局和地图框
- 让 AI 读取某个 `.gdb` 的结构
- 让 AI 先生成 ArcPy，再由你确认后执行

## 当前可用 Tool

当前主要 Tool 包括：

- `detect_arcgis_environment`
- `execute_arcpy_code`
- `build_gis_resource_uri`
- `list_gis_layers`
- `inspect_project_context`
- `inspect_gdb`
- `generate_sync_plan`

## 当前可用 Resource

当前主要 Resource 包括：

- `arcgis://server/status`
- `arcgis://resources/catalog`
- `arcgis://project/current/layers`
- `arcgis://project/current/context`
- `arcgis://project/{project_ref}/layers`
- `arcgis://project/{project_ref}/context`
- `arcgis://gdb/{gdb_ref}/schema`

## 常见问题

### 1. 找不到 ArcGIS Pro 或找不到 arcpy

请先检查：

- ArcGIS Pro 是否已经安装
- ArcGIS Pro 是否可以正常启动
- 是否先调用过 `detect_arcgis_environment`

如果仍然失败，可以手动设置环境变量：

- `ARCGIS_PRO_PYTHON`
- `ARCGIS_PRO_INSTALL_DIR`

### 2. 读取不到当前工程

如果 `ArcGISProject("CURRENT")` 无法附着，这通常是 ArcGIS Pro 当前运行上下文的限制，不一定是程序错误。

这时建议直接传入 `.aprx` 路径，而不是依赖 `CURRENT`。

### 3. 图层数据源断开

常见原因包括：

- 数据路径改变
- 网络盘没有挂载
- GDB 被移动
- SDE 连接不可用

建议先调用：

- `list_gis_layers`
- `inspect_project_context`

先把断开的数据源找出来。

### 4. ArcPy 执行时报锁定错误

常见原因包括：

- 图层正在编辑
- 数据正在被 ArcGIS Pro 占用
- 外部程序正在读写数据

建议先关闭编辑状态，再重试。

### 5. 处理很慢或超时

可以尝试：

- 缩小处理范围
- 减少一次处理的数据量
- 提高 `timeout_seconds`

## 安全提醒

`execute_arcpy_code` 本质上是“在本机执行代码”。

所以请务必注意：

- 只在你信任的电脑上使用
- 不要直接暴露到公网
- 不要让 AI 未经确认就修改正式数据
- 对重要数据先备份，再执行写操作

更详细说明见：

- [SECURITY.md](SECURITY.md)

## 示例目录

如果你需要直接复制配置或查看完整示例，请看：

- [examples/README.md](examples/README.md)
- [examples/cursor-mcp-config.json](examples/cursor-mcp-config.json)
- [examples/claude-desktop-mcp-config.json](examples/claude-desktop-mcp-config.json)
- [examples/arcpy-buffer-example.py](examples/arcpy-buffer-example.py)
- [examples/prompt-examples.md](examples/prompt-examples.md)

## 本地校验

项目当前使用这些检查命令：

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run python -m unittest discover -s tests -p "test_*.py"`

## 开源信息

- 许可证：[LICENSE](LICENSE)
- 更新记录：[CHANGELOG.md](CHANGELOG.md)
- 贡献说明：[CONTRIBUTING.md](CONTRIBUTING.md)
