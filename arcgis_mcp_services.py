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
            "message": "doctor 工具已被实际调用，说明客户端已经进入 MCP Tool 调用链路。",
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
                "message": "已找到 ArcGIS Pro Python。",
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
                "请确认 ArcGIS Pro 已安装且能够正常启动。",
                "如有需要，可手动设置 ARCGIS_PRO_PYTHON 或 ARCGIS_PRO_INSTALL_DIR。",
                "如果是在 Trae 或 Cursor 中测试，请确认客户端真正调用了 MCP Tool，而不是 shell。",
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
                    "message": "ArcPy 运行时检查通过。",
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
                            "发现到的 Python 路径在当前文件系统中不可访问，请确认安装目录是否变更。"
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
                    else "ArcPy 运行时检查失败。",
                    "details": result_to_dict(runtime_result),
                }
            )
            recommendations.extend(
                [
                    "请先在 ArcGIS Pro 中确认许可状态和登录状态。",
                    "如果是首次接入 AI 客户端，建议先只测试 detect_arcgis_environment 或 ping。",
                ]
            )

    if overall_status == "ready":
        recommendations.extend(
            [
                "下一步建议先调用 ping 或 health_check，确认客户端确实在走 MCP Tool。",
                "然后再调用 inspect_gdb、inspect_project_context 或专用地理处理 Tool。",
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
