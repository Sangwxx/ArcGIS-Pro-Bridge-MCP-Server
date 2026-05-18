# Changelog

## 0.3.0 - 2026-05-18

### Added — Raster Analysis Tools (8 new MCP tools)
- `validate_project_data` — Pre-flight check for all required layers, CRS, coverage, and Spatial Analyst license
- `prepare_analysis_inputs` — One-shot data prep: clip vectors, resample DEM, derive slope, Euclidean distance rasters
- `reclassify_criteria` — Batch reclassify multiple rasters to 1-5 suitability scale with RemapRange
- `weighted_suitability` — Weighted Linear Combination using `arcpy.sa.WeightedSum` with weight validation and normalization
- `conflict_analysis` — Binary conflict map + allocation map with area statistics
- `raster_area_summary` — Area statistics by suitability class with optional CSV export
- `sensitivity_check` — One-at-a-time weight perturbation (±10%) + threshold variation analysis
- `export_suitability_map` — Publication-quality layout creation with PDF/PNG export

### Changed
- All raster tools use `arcpy.sa.WeightedSum` (not `WeightedOverlay`) for float weight support
- Snap raster alignment to `forest_prop` for consistent 30m cell output
- Default timeout for raster tools set to 600s; `prepare_analysis_inputs` uses 900s

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
