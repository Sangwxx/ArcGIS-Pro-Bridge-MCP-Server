# Changelog

## 0.2.0 - 2026-05-18

### Added
- OpenCode integration: `opencode.json` config, `AGENTS.md` agent instructions
- Path validation with `ARCGIS_MCP_ALLOWED_PATHS` for production sandboxing
- English translation for all Chinese documentation
- Windows setup guide (`WINDOWS_SETUP.md`) and test project generator
- Structured logging support (`arcgis_mcp_logging.py`)
- Test suite with mock `.aprx` archives and subprocess mocking

### Changed
- Improved `.aprx` archive reader performance for project inspection
- Hardened ArcGIS subprocess isolation (scrubs `PYTHONPATH`, `VIRTUAL_ENV`, Trae/UV vars)
- Enhanced error hints with actionable messages for common failures

### Security
- Added `opencode.json` to `.gitignore` to prevent leaking local paths
- Documented `execute_arcpy_code` permission gate in security notes

## 0.1.0 - 2026-04-04

- Initialize ArcGIS Pro Bridge MCP Server core capabilities.
- Support auto-discovery of ArcGIS Pro installation path and Python interpreter.
- Support executing ArcPy code via subprocess and collecting structured results.
- Provide MCP Tools / Resources for project layers, GDB schema, and `.aprx` project overview.
- Add examples, CI, contributing guide, and security notes required for GitHub release.
