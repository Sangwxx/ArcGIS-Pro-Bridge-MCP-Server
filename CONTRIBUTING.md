# 贡献指南

感谢你为 ArcGIS Pro Bridge MCP Server 做贡献。

## 开发环境
- 操作系统：Windows
- Python：建议 `3.11+`
- 包管理：`uv`
- ArcPy 相关能力需要本机安装 ArcGIS Pro

## 开发流程
1. Fork 或克隆仓库。
2. 创建功能分支。
3. 安装依赖：

```powershell
uv sync
```

4. 提交前运行本地检查：

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -p "test_*.py"
```

## 提交建议
- 保持变更聚焦，避免混入无关修改。
- 优先补充单元测试。
- 如果修改了 Tool / Resource 的返回结构，请同步更新 README 和示例。

## Pull Request 建议
- 说明变更背景、实现方式和验证结果。
- 如果涉及 ArcGIS Pro 行为差异，请注明测试环境与版本。
