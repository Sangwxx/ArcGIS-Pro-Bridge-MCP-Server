from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable


def run_arcpy_runtime_check(
    *,
    run_in_arcgis_env: Callable[..., Any],
    build_arcpy_runtime_check_code: Callable[[], str],
    timeout_seconds: int = 60,
) -> Any:
    return run_in_arcgis_env(
        build_arcpy_runtime_check_code(),
        timeout_seconds=timeout_seconds,
        require_arcpy=True,
    )


def read_project_layers(
    *,
    run_in_arcgis_env: Callable[..., Any],
    build_project_layers_code: Callable[..., str],
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int,
    include_fields: bool,
    include_data_source_details: bool,
) -> Any:
    return run_in_arcgis_env(
        build_project_layers_code(
            include_fields=include_fields,
            include_data_source_details=include_data_source_details,
        ),
        project_path=project_path,
        open_current_project=open_current_project,
        timeout_seconds=timeout_seconds,
        require_arcpy=True,
    )


def read_gdb_schema(
    *,
    run_in_arcgis_env: Callable[..., Any],
    build_gdb_schema_code: Callable[[str], str],
    gdb_path: str,
) -> Any:
    return run_in_arcgis_env(
        build_gdb_schema_code(gdb_path),
        workspace=gdb_path,
        require_arcpy=True,
    )


def read_project_context(
    *,
    run_in_arcgis_env: Callable[..., Any],
    build_project_context_code: Callable[..., str],
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int,
    include_source_details: bool,
) -> Any:
    return run_in_arcgis_env(
        build_project_context_code(include_source_details=include_source_details),
        project_path=project_path,
        open_current_project=open_current_project,
        timeout_seconds=timeout_seconds,
        require_arcpy=True,
    )


def build_doctor_report(
    *,
    server_name: str,
    timestamp_utc_iso: Callable[[], str],
    discover_arcgis_pro_python: Callable[[], Any],
    arcgis_discovery_error: type[Exception],
    run_runtime_check: Callable[..., Any],
    path_exists: Callable[[str | None], bool],
    result_to_dict: Callable[[Any], dict[str, Any]],
    coerce_result_data: Callable[[Any], Any | None],
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        {
            "name": "mcp_tool_reachable",
            "status": "pass",
            "message": "doctor tool has been called, client has entered MCP Tool call chain.",
        }
    ]
    recommendations: list[str] = []
    overall_status = "ready"

    try:
        python_info = discover_arcgis_pro_python()
        checks.append(
            {
                "name": "arcgis_python_discovery",
                "status": "pass",
                "message": "ArcGIS Pro Python found.",
                "details": asdict(python_info),
            }
        )
    except arcgis_discovery_error as exc:
        overall_status = "unavailable"
        python_info = None
        checks.append(
            {
                "name": "arcgis_python_discovery",
                "status": "fail",
                "message": str(exc),
            }
        )
        recommendations.extend(
            [
                "Confirm ArcGIS Pro is installed and can start.",
                "If needed, manually set ARCGIS_PRO_PYTHON or ARCGIS_PRO_INSTALL_DIR.",
                "If testing in Trae or Cursor, confirm the client is "
                "actually calling the MCP Tool, not shell.",
            ]
        )

    runtime_payload: dict[str, Any] | None = None
    if python_info is not None:
        runtime_result = run_runtime_check(timeout_seconds=timeout_seconds)
        runtime_payload = coerce_result_data(runtime_result)
        if runtime_result.status == "success":
            checks.append(
                {
                    "name": "arcpy_runtime_check",
                    "status": "pass",
                    "message": "ArcPy runtime check passed.",
                    "details": runtime_payload,
                }
            )
            if not path_exists(runtime_result.python_executable):
                overall_status = "warning"
                checks.append(
                    {
                        "name": "python_path_exists",
                        "status": "warn",
                        "message": (
                            "Discovered Python path is not accessible in "
                            "the current filesystem, confirm if the install "
                            "directory has changed."
                        ),
                        "details": {"python_executable": runtime_result.python_executable},
                    }
                )
        else:
            overall_status = "warning"
            checks.append(
                {
                    "name": "arcpy_runtime_check",
                    "status": "fail",
                    "message": runtime_result.error.get("message")
                    if runtime_result.error
                    else "ArcPy runtime check failed.",
                    "details": result_to_dict(runtime_result),
                }
            )
            recommendations.extend(
                [
                    "First confirm license status and login status in ArcGIS Pro.",
                    "If this is the first time connecting to an AI "
                    "client, start by testing detect_arcgis_environment "
                    "or ping.",
                ]
            )

    if overall_status == "ready":
        recommendations.extend(
            [
                "Next step: call ping or health_check to confirm the client is actually using MCP.",
                "Then call inspect_gdb, inspect_project_context, or dedicated geoprocessing tools.",
            ]
        )

    return {
        "status": overall_status,
        "server": server_name,
        "timestamp_utc": timestamp_utc_iso(),
        "arcgis_python": asdict(python_info) if python_info is not None else None,
        "runtime": runtime_payload,
        "checks": checks,
        "recommendations": recommendations,
    }
