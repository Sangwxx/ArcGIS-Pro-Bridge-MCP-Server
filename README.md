# ArcGIS Pro Bridge MCP Server

ArcGIS Pro Bridge MCP Server 是一个让 AI 客户端连接本机 ArcGIS Pro 的 MCP Server。

它的目标很简单：
- 让 Trae、Cursor、Claude Desktop 这类支持 MCP 的客户端，能够读取 ArcGIS Pro 工程信息
- 让 AI 能在 ArcGIS Pro 自带的 Python 环境里执行 ArcPy
- 尽量减少 GISer 手动配置 Python 环境的麻烦

如果你平时主要用 ArcGIS Pro，但对 Python、终端、环境变量、MCP 这些概念并不熟，也没关系。这个 README 会尽量用“按步骤照着做”的方式来写。

## 这个项目适合做什么

你可以用它来做这些事情：

- 读取当前 ArcGIS Pro 工程中的地图和图层
- 检查哪些图层的数据源已经断开
- 读取 `.aprx` 工程中的布局和地图框
- 读取 `.gdb` 的要素类、字段和空间参考
- 让 AI 生成 ArcPy 脚本
- 让 AI 调用 ArcPy 执行 Buffer、Clip、Merge 等地理处理

## 这个项目不适合做什么

当前版本不适合直接拿来做这些事情：

- 对公网开放的远程 GIS 服务
- 无人值守地直接修改生产数据
- 替代 ArcGIS Pro 图形界面
- 自动保证地理处理结果一定符合业务逻辑

更准确地说，它是一个“本机上的 ArcGIS Pro AI 桥接工具”，不是一个完整 GIS 平台。

## 你需要准备什么

使用前请先确认：

- 你使用的是 Windows
- 你已经安装 ArcGIS Pro
- ArcGIS Pro 可以正常启动
- 你愿意在本机运行 AI 生成的 ArcPy 代码
- 你的电脑中有 Python 3.11 或更高版本
- 建议安装 `uv`

## 它的工作原理

你不需要完全理解这部分，但知道大概会有帮助。

这个项目分成两层：

1. MCP Server 本体
它运行在普通 Python 环境里，负责和 AI 客户端通信。

2. ArcGIS Pro Python 执行层
所有需要 `arcpy` 的代码，不在普通 Python 里执行，而是切换到 ArcGIS Pro 自带的 `arcgispro-py3` 解释器里执行。

这也是为什么你不需要手动把 `arcpy` 安装到当前虚拟环境里。

## 10 分钟快速开始

### 第一步：获取项目

如果你是从 GitHub 获取项目，先克隆仓库并进入项目目录。

如果你已经拿到了项目文件夹，直接进入项目目录即可。

### 第二步：安装依赖

在项目目录中运行 `uv sync`。

这一步会安装 MCP Server 本身需要的依赖。

注意：
- `arcpy` 不会在这里安装
- `arcpy` 来自 ArcGIS Pro 自带环境
- 本项目会在运行时自动寻找它

### 第三步：检查 ArcGIS Pro 是否能被发现

运行一个最简单的环境检测命令，调用 `detect_arcgis_environment`。

如果输出中出现类似这样的信息：

- `status: ready`
- `python_executable: ...ArcGIS...python.exe`

说明当前电脑上的 ArcGIS Pro 环境已经能被正确发现。

### 第四步：启动 MCP Server

启动方式很简单，运行 `uv run arcgis_mcp_server.py` 或 `uv run arcgis-mcp-server` 即可。

只要这个进程保持运行，你的 AI 客户端就可以连接它。

## 如何接入 Cursor

不同版本的 Cursor 界面可能略有变化，但核心思路相同：添加一个本地 `stdio` MCP Server。

### 操作步骤

1. 打开 Cursor
2. 找到 MCP 或工具配置入口
3. 新增一个本地 MCP Server
4. 使用下面这组配置
5. 保存配置
6. 重启 Cursor，或者刷新 MCP Server 列表

### 配置示例

可参考：
- [examples/cursor-mcp-config.json](examples/cursor-mcp-config.json)

### 接好以后先怎么试

你可以先对 Cursor 里的 AI 说：

```text
请先调用 detect_arcgis_environment，告诉我 ArcGIS Pro 是否已经被正确发现。
```

如果它能返回 ArcGIS Pro Python 路径，说明接入成功。

## 如何接入 Trae

Trae 的接入方式通常和 Cursor 类似，也是增加一个本地 `stdio` MCP Server。

### 建议步骤

1. 打开 Trae
2. 找到 MCP、工具、开发者工具或外部工具配置入口
3. 新增一个自定义 MCP Server
4. 使用下面的配置
5. 保存后重启 Trae，或者刷新工具列表

### 配置示例

```json
{
  "mcpServers": {
    "arcgis-pro-bridge": {
      "command": "uv",
      "args": [
        "run",
        "arcgis_mcp_server.py"
      ],
      "cwd": "D:\\ArcgisproMCP"
    }
  }
}
```

如果你的 Trae 版本支持直接导入配置，也可以直接参考：
- [examples/cursor-mcp-config.json](examples/cursor-mcp-config.json)

## 如何接入 Claude Desktop

Claude Desktop 一般也是通过 MCP 配置文件接入。

### 操作步骤

1. 打开 Claude Desktop 的 MCP 配置文件
2. 在 `mcpServers` 中加入本项目配置
3. 保存文件
4. 完全退出 Claude Desktop
5. 重新打开 Claude Desktop

### 配置示例

可参考：
- [examples/claude-desktop-mcp-config.json](examples/claude-desktop-mcp-config.json)

## 第一次使用时，推荐这样验证

不要一上来就让 AI 做复杂分析。

建议按下面顺序来：

### 1. 先确认 ArcGIS 环境
先让 AI 调用 `detect_arcgis_environment`，确认当前 ArcGIS Pro 的 Python 路径是否已经被发现。

### 2. 再读取当前工程图层
再让 AI 读取当前 ArcGIS Pro 工程中的地图、图层和断开的数据源。

### 3. 再读取指定 GDB
然后读取指定 GDB 的要素类、字段和空间参考。

### 4. 再读取指定工程概览
接着读取指定 `.aprx` 工程的地图、布局、地图框和默认地图候选。

### 5. 最后再让 AI 执行 ArcPy
最后再让 AI 先生成 ArcPy，再由你确认后执行。

## 常见使用方法

### 用法 1：让 AI 看懂当前工程
让 AI 读取当前 ArcGIS Pro 工程中的地图、图层和字段，并判断哪些图层适合做缓冲分析。

### 用法 2：让 AI 检查布局
让 AI 读取指定工程的布局和地图框，并说明每个地图框绑定的是哪个地图。

### 用法 3：让 AI 先写代码再执行
让 AI 基于当前工程图层先生成 ArcPy 代码，再由你确认后执行。

### 用法 4：直接执行 ArcPy Buffer
让 AI 直接执行 ArcPy Buffer，并返回是否成功、`stdout` 和 `stderr`。

更多现成示例见：
- [examples/prompt-examples.md](examples/prompt-examples.md)

## Tool 说明

### `detect_arcgis_environment`

作用：
- 检查 ArcGIS Pro 是否能被正确发现
- 返回 ArcGIS Pro Python 路径

适合什么时候用：
- 第一次安装后
- 换电脑后
- AI 提示找不到 `arcpy` 时

### `execute_arcpy_code`

作用：
- 在 ArcGIS Pro Python 环境中执行 ArcPy 代码

常见参数：
- `code`
- `workspace`
- `project_path`
- `open_current_project`
- `timeout_seconds`

常见返回值：
- `status`
- `stdout`
- `stderr`
- `data`
- `error`
- `hint`

### `list_gis_layers`

作用：
- 读取地图、图层、字段和空间参考

适合什么时候用：
- 在写 ArcPy 之前先读取上下文
- 确认 AI 将要处理的图层到底是哪一个

### `inspect_project_context`

作用：
- 读取 `.aprx` 工程概览

返回内容通常包括：
- 工程基本信息
- 地图摘要
- 布局
- 地图框
- 默认地图候选
- 失效数据源

### `inspect_gdb`

作用：
- 读取 `.gdb` 结构

返回内容通常包括：
- Feature Dataset
- 独立要素类
- 表
- 字段
- 空间参考

### `build_gis_resource_uri`

作用：
- 根据资源类型和本地路径生成可复用的 Resource URI

支持：
- `project_layers`
- `project_context`
- `gdb_schema`

## Resource 是什么

如果你不想深入理解 MCP，可以简单把它理解为：

- Tool：执行动作
- Resource：读取上下文

这个项目当前提供的固定 Resource 有：

- `arcgis://server/status`
- `arcgis://resources/catalog`
- `arcgis://project/current/layers`
- `arcgis://project/current/context`

模板 Resource 有：

- `arcgis://project/{project_ref}/layers`
- `arcgis://project/{project_ref}/context`
- `arcgis://gdb/{gdb_ref}/schema`

如果你不想自己处理路径编码，直接调用 `build_gis_resource_uri` 就可以。

## ArcPy 示例

示例文件：
- [examples/arcpy-buffer-example.py](examples/arcpy-buffer-example.py)

## 常见问题

### 1. 找不到 ArcGIS Pro 或找不到 arcpy

请先检查：

- ArcGIS Pro 是否已经安装
- ArcGIS Pro 是否可以正常启动
- 是否运行过 `detect_arcgis_environment`

如果仍然失败，可以手动设置：

- `ARCGIS_PRO_PYTHON`
- `ARCGIS_PRO_INSTALL_DIR`

### 2. 读取不到当前工程

如果 `ArcGISProject("CURRENT")` 无法附着，这通常是 ArcGIS Pro 当前运行上下文的限制，不一定是程序错误。

此时建议直接传入 `.aprx` 路径，而不是依赖 `CURRENT`。

### 3. 图层数据源断开

常见原因：

- 数据路径变了
- 网络盘没有挂载
- GDB 被移动
- SDE 连接不可用

建议先调用：
- `list_gis_layers`
- `inspect_project_context`

让 AI 先把断开的数据源找出来。

### 4. ArcPy 执行时报锁定错误

常见原因：

- 图层正在编辑
- 数据正在被 ArcGIS Pro 占用
- 外部程序正在读写数据

建议先关闭编辑状态，再重试。

### 5. 处理很慢或超时

你可以尝试：

- 缩小处理范围
- 减少一次处理的数据量
- 提高 `timeout_seconds`

## 安全提醒

这个项目的 `execute_arcpy_code` 本质上是“在本机执行代码”。

所以请务必注意：

- 只在你信任的电脑上使用
- 不要直接暴露到公网
- 不要让 AI 未经确认就修改正式数据
- 对重要数据先备份，再执行写操作

更稳妥的工作方式是：

1. 先读取上下文
2. 再让 AI 生成 ArcPy 代码
3. 你先确认代码
4. 最后再执行

详细说明见：
- [SECURITY.md](SECURITY.md)

## 示例目录

示例文件见：
- [examples/README.md](examples/README.md)

## 本地校验

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -p "test_*.py"
```

## 开源信息

- 许可证：[LICENSE](LICENSE)
- 更新记录：[CHANGELOG.md](CHANGELOG.md)
- 贡献说明：[CONTRIBUTING.md](CONTRIBUTING.md)
