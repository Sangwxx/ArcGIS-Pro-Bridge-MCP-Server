from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Callable

from arcgis_runtime_utils import encode_resource_path


def build_project_layers_resource_uri(
    project_path: str | None = None, *, open_current_project: bool = False
) -> str:
    if open_current_project or not project_path:
        return "arcgis://project/current/layers"
    return f"arcgis://project/{encode_resource_path(project_path)}/layers"


def build_project_context_resource_uri(
    project_path: str | None = None, *, open_current_project: bool = False
) -> str:
    if open_current_project or not project_path:
        return "arcgis://project/current/context"
    return f"arcgis://project/{encode_resource_path(project_path)}/context"


def build_gdb_schema_resource_uri(gdb_path: str) -> str:
    return f"arcgis://gdb/{encode_resource_path(gdb_path)}/schema"


def result_to_dict(result: Any) -> dict[str, Any]:
    return asdict(result)


def coerce_result_data(result: Any) -> Any | None:
    if getattr(result, "data", None) is not None:
        return result.data

    stdout = getattr(result, "stdout", "").strip()
    if not stdout:
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def build_resource_payload(
    result: Any,
    *,
    resource_uri: str,
    resource_kind: str,
) -> dict[str, Any]:
    payload = {
        "resource_uri": resource_uri,
        "resource_kind": resource_kind,
        "status": result.status,
        "data": coerce_result_data(result),
        "execution": result_to_dict(result),
    }
    if getattr(result, "error", None):
        payload["message"] = result.error.get("message")
    return payload


def register_resources(
    mcp: Any,
    *,
    server_name: str,
    decode_resource_path: Callable[[str], str],
    discover_arcgis_pro_python: Callable[[], Any],
    arcgis_discovery_error: type[Exception],
    read_project_layers: Callable[..., Any],
    read_project_context: Callable[..., Any],
    read_gdb_schema: Callable[[str], Any],
) -> dict[str, Callable[..., str]]:
    @mcp.resource("arcgis://server/status")
    def server_status() -> str:
        """返回当前服务与 ArcGIS 环境发现状态。"""
        try:
            python_info = discover_arcgis_pro_python()
            payload = {
                "server": server_name,
                "status": "ready",
                "arcgis_python": asdict(python_info),
            }
        except arcgis_discovery_error as exc:
            payload = {
                "server": server_name,
                "status": "degraded",
                "message": str(exc),
            }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.resource(
        "arcgis://resources/catalog",
        title="ArcGIS 资源目录",
        description="列出当前服务提供的固定资源与模板资源。",
        mime_type="application/json",
    )
    def gis_resource_catalog() -> str:
        payload = {
            "resources": [
                {
                    "uri": "arcgis://server/status",
                    "kind": "server_status",
                    "description": "ArcGIS Pro 环境发现状态。",
                },
                {
                    "uri": "arcgis://project/current/layers",
                    "kind": "project_layers",
                    "description": "当前打开的 ArcGIS Pro 工程图层上下文。",
                },
                {
                    "uri": "arcgis://project/current/context",
                    "kind": "project_context",
                    "description": "当前 ArcGIS Pro 工程的布局、地图框和连接状态概览。",
                },
                {
                    "uri_template": "arcgis://project/{project_ref}/layers",
                    "kind": "project_layers",
                    "description": "指定 .aprx 工程的图层上下文。",
                    "path_encoding": "base64-url",
                },
                {
                    "uri_template": "arcgis://project/{project_ref}/context",
                    "kind": "project_context",
                    "description": "指定 .aprx 工程的布局、地图框和连接状态概览。",
                    "path_encoding": "base64-url",
                },
                {
                    "uri_template": "arcgis://gdb/{gdb_ref}/schema",
                    "kind": "gdb_schema",
                    "description": "指定文件地理数据库的要素类、字段与空间参考信息。",
                    "path_encoding": "base64-url",
                },
            ],
            "helpers": {
                "project_current": build_project_layers_resource_uri(open_current_project=True),
                "project_current_context": build_project_context_resource_uri(
                    open_current_project=True
                ),
                "example_project": build_project_layers_resource_uri(
                    r"C:\GIS\Projects\Example.aprx"
                ),
                "example_project_context": build_project_context_resource_uri(
                    r"C:\GIS\Projects\Example.aprx"
                ),
                "example_gdb": build_gdb_schema_resource_uri(r"C:\GIS\Data\Example.gdb"),
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.resource(
        "arcgis://project/current/layers",
        title="当前工程图层上下文",
        description="读取当前 ArcGIS Pro 工程中的地图、图层、字段与空间参考。",
        mime_type="application/json",
    )
    def current_project_layers_resource() -> str:
        result = read_project_layers(open_current_project=True)
        payload = build_resource_payload(
            result,
            resource_uri=build_project_layers_resource_uri(open_current_project=True),
            resource_kind="project_layers",
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.resource(
        "arcgis://project/{project_ref}/layers",
        title="指定工程图层上下文",
        description="读取指定 .aprx 工程中的地图、图层、字段与空间参考。",
        mime_type="application/json",
    )
    def project_layers_resource(project_ref: str) -> str:
        try:
            project_path = decode_resource_path(project_ref)
        except Exception as exc:  # noqa: BLE001
            payload = {
                "resource_uri": f"arcgis://project/{project_ref}/layers",
                "resource_kind": "project_layers",
                "status": "error",
                "message": f"无法解析 project_ref：{exc}",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        result = read_project_layers(project_path=project_path)
        payload = build_resource_payload(
            result,
            resource_uri=build_project_layers_resource_uri(project_path),
            resource_kind="project_layers",
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.resource(
        "arcgis://project/current/context",
        title="当前工程概览",
        description="读取当前 ArcGIS Pro 工程的布局、地图框、默认地图候选与数据源状态。",
        mime_type="application/json",
    )
    def current_project_context_resource() -> str:
        result = read_project_context(open_current_project=True)
        payload = build_resource_payload(
            result,
            resource_uri=build_project_context_resource_uri(open_current_project=True),
            resource_kind="project_context",
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.resource(
        "arcgis://project/{project_ref}/context",
        title="指定工程概览",
        description="读取指定 .aprx 工程的布局、地图框、默认地图候选与数据源状态。",
        mime_type="application/json",
    )
    def project_context_resource(project_ref: str) -> str:
        try:
            project_path = decode_resource_path(project_ref)
        except Exception as exc:  # noqa: BLE001
            payload = {
                "resource_uri": f"arcgis://project/{project_ref}/context",
                "resource_kind": "project_context",
                "status": "error",
                "message": f"无法解析 project_ref：{exc}",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        result = read_project_context(project_path=project_path)
        payload = build_resource_payload(
            result,
            resource_uri=build_project_context_resource_uri(project_path),
            resource_kind="project_context",
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @mcp.resource(
        "arcgis://gdb/{gdb_ref}/schema",
        title="GDB 模式上下文",
        description="读取指定文件地理数据库的要素类、字段和空间参考。",
        mime_type="application/json",
    )
    def gdb_schema_resource(gdb_ref: str) -> str:
        try:
            gdb_path = decode_resource_path(gdb_ref)
        except Exception as exc:  # noqa: BLE001
            payload = {
                "resource_uri": f"arcgis://gdb/{gdb_ref}/schema",
                "resource_kind": "gdb_schema",
                "status": "error",
                "message": f"无法解析 gdb_ref：{exc}",
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)

        result = read_gdb_schema(gdb_path)
        payload = build_resource_payload(
            result,
            resource_uri=build_gdb_schema_resource_uri(gdb_path),
            resource_kind="gdb_schema",
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    return {
        "server_status": server_status,
        "gis_resource_catalog": gis_resource_catalog,
        "current_project_layers_resource": current_project_layers_resource,
        "project_layers_resource": project_layers_resource,
        "current_project_context_resource": current_project_context_resource,
        "project_context_resource": project_context_resource,
        "gdb_schema_resource": gdb_schema_resource,
    }
