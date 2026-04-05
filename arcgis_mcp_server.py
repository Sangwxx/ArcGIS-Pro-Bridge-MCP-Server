from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Any

from mcp.server.fastmcp import FastMCP

from arcgis_script_templates import (
    build_arcpy_runtime_check_code,
    build_buffer_features_code,
    build_clip_features_code,
    build_gdb_schema_code,
    build_project_context_code,
    build_project_layers_code,
)

try:
    import winreg
except ImportError:  # pragma: no cover - 仅在非 Windows 环境触发
    winreg = None


SERVER_NAME = "ArcGIS Pro Bridge MCP Server"
DEFAULT_TIMEOUT_SECONDS = 300
ARCGIS_REGISTRY_PATHS = (
    r"SOFTWARE\ESRI\ArcGISPro",
    r"SOFTWARE\WOW6432Node\ESRI\ArcGISPro",
)
ARCGIS_PYTHON_RELATIVE_PATHS = (
    Path("bin/Python/envs/arcgispro-py3/python.exe"),
    Path("bin/Python/scripts/propy.bat"),
)
RUNNER_FILENAME = "arcgis_runner.py"
PAYLOAD_FILENAME = "payload.json"
RESULT_FILENAME = "result.json"

mcp = FastMCP(
    name=SERVER_NAME,
    instructions=(
        "用于桥接 AI Agent 与本地 ArcGIS Pro。"
        "ArcPy 逻辑统一通过 ArcGIS Pro 自带 Python 子进程执行。"
    ),
    json_response=True,
)


class ArcGISDiscoveryError(RuntimeError):
    """未能发现 ArcGIS Pro 环境时抛出的异常。"""


@dataclass(slots=True)
class ArcGISPythonInfo:
    install_dir: str
    python_executable: str
    source: str


@dataclass(slots=True)
class ArcPyExecutionResult:
    status: str
    exit_code: int
    python_executable: str
    stdout: str
    stderr: str
    data: Any | None = None
    error: dict[str, Any] | None = None
    hint: str | None = None
    workspace: str | None = None
    project_path: str | None = None


def _normalize_path(value: str | os.PathLike[str]) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _encode_resource_path(path: str | os.PathLike[str]) -> str:
    normalized = _normalize_path(path)
    encoded = base64.urlsafe_b64encode(normalized.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_resource_path(path_ref: str) -> str:
    padding = "=" * (-len(path_ref) % 4)
    decoded = base64.urlsafe_b64decode(f"{path_ref}{padding}").decode("utf-8")
    return _normalize_path(decoded)


def build_project_layers_resource_uri(
    project_path: str | None = None, *, open_current_project: bool = False
) -> str:
    if open_current_project or not project_path:
        return "arcgis://project/current/layers"
    return f"arcgis://project/{_encode_resource_path(project_path)}/layers"


def build_project_context_resource_uri(
    project_path: str | None = None, *, open_current_project: bool = False
) -> str:
    if open_current_project or not project_path:
        return "arcgis://project/current/context"
    return f"arcgis://project/{_encode_resource_path(project_path)}/context"


def build_gdb_schema_resource_uri(gdb_path: str) -> str:
    return f"arcgis://gdb/{_encode_resource_path(gdb_path)}/schema"


def _guess_install_dir_from_python(python_path: str | os.PathLike[str]) -> str:
    normalized_path = Path(_normalize_path(python_path))
    parts = normalized_path.parts
    marker = ("bin", "Python", "envs", "arcgispro-py3")
    if len(parts) >= len(marker) + 1 and tuple(parts[-5:-1]) == marker:
        return _normalize_path(normalized_path.parents[4])
    return _normalize_path(normalized_path.parent)


def _iter_env_python_candidates() -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    explicit_python = os.environ.get("ARCGIS_PRO_PYTHON")
    if explicit_python:
        python_path = Path(explicit_python).expanduser()
        normalized_python_path = _normalize_path(python_path)
        candidates.append(
            (
                "env:ARCGIS_PRO_PYTHON",
                normalized_python_path,
                _guess_install_dir_from_python(normalized_python_path),
            )
        )

    install_dir = os.environ.get("ARCGIS_PRO_INSTALL_DIR")
    if install_dir:
        install_path = Path(install_dir).expanduser()
        normalized_install_path = _normalize_path(install_path)
        for relative_path in ARCGIS_PYTHON_RELATIVE_PATHS:
            candidates.append(
                (
                    "env:ARCGIS_PRO_INSTALL_DIR",
                    _normalize_path(install_path / relative_path),
                    normalized_install_path,
                )
            )

    return candidates


def _iter_registry_install_dirs() -> list[tuple[str, str]]:
    if winreg is None:
        return []

    discovered: list[tuple[str, str]] = []
    registry_views = [0]
    key_read = getattr(winreg, "KEY_READ", 0)
    for extra_flag_name in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
        extra_flag = getattr(winreg, extra_flag_name, 0)
        if extra_flag:
            registry_views.append(extra_flag)

    for registry_path in ARCGIS_REGISTRY_PATHS:
        for view_flag in registry_views:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, registry_path, 0, key_read | view_flag
                ) as key:
                    install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
            except OSError:
                continue
            discovered.append((f"registry:{registry_path}", _normalize_path(install_dir)))

    return discovered


def _build_python_candidates() -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for source, python_path, install_dir in _iter_env_python_candidates():
        normalized = _normalize_path(python_path)
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append((source, normalized, install_dir))

    for source, install_dir in _iter_registry_install_dirs():
        install_path = Path(install_dir)
        for relative_path in ARCGIS_PYTHON_RELATIVE_PATHS:
            python_path = _normalize_path(install_path / relative_path)
            if python_path in seen:
                continue
            seen.add(python_path)
            candidates.append((source, python_path, _normalize_path(install_path)))

    filesystem_fallback = Path(r"C:\Program Files\ArcGIS\Pro")
    for relative_path in ARCGIS_PYTHON_RELATIVE_PATHS:
        python_path = _normalize_path(filesystem_fallback / relative_path)
        if python_path in seen:
            continue
        seen.add(python_path)
        candidates.append(("filesystem:default", python_path, _normalize_path(filesystem_fallback)))

    return candidates


def clear_discovery_cache() -> None:
    """测试或重载场景下清理发现缓存。"""
    discover_arcgis_pro_python.cache_clear()


@lru_cache(maxsize=1)
def discover_arcgis_pro_python() -> ArcGISPythonInfo:
    """自动发现 ArcGIS Pro 自带 Python 解释器。"""
    for source, python_path, install_dir in _build_python_candidates():
        if Path(python_path).exists():
            return ArcGISPythonInfo(
                install_dir=_normalize_path(install_dir),
                python_executable=python_path,
                source=source,
            )

    raise ArcGISDiscoveryError(
        "未找到 ArcGIS Pro Python 解释器。请确认已安装 ArcGIS Pro，"
        "或通过 ARCGIS_PRO_PYTHON / ARCGIS_PRO_INSTALL_DIR 提供路径。"
    )


def _build_runner_script() -> str:
    """生成在 ArcGIS Python 环境中执行的包装脚本。"""
    return dedent(
        """
        from __future__ import annotations

        import contextlib
        import io
        import json
        import os
        import sys
        import traceback
        from pathlib import Path

        payload_path = Path(sys.argv[1])
        result_path = Path(sys.argv[2])

        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        code = payload["code"]
        workspace = payload.get("workspace")
        project_path = payload.get("project_path")
        open_current_project = payload.get("open_current_project", False)
        require_arcpy = payload.get("require_arcpy", True)

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        namespace = {
            "__name__": "__main__",
            "__file__": str(payload_path.with_name("user_code.py")),
        }
        namespace["__arcgis_mcp_result__"] = None

        def set_result(value):
            namespace["__arcgis_mcp_result__"] = value

        namespace["set_result"] = set_result
        error = None
        status = "success"

        try:
            arcpy = None
            if require_arcpy:
                import arcpy  # type: ignore

                namespace["arcpy"] = arcpy
                if workspace:
                    arcpy.env.workspace = workspace

                def open_project(path=None):
                    target = path or project_path or "CURRENT"
                    return arcpy.mp.ArcGISProject(target)

                namespace["open_project"] = open_project

                if project_path:
                    namespace["arcgis_project"] = arcpy.mp.ArcGISProject(project_path)
                elif open_current_project:
                    namespace["arcgis_project"] = arcpy.mp.ArcGISProject("CURRENT")

            os.environ["ARCGIS_MCP_WORKSPACE"] = workspace or ""
            os.environ["ARCGIS_MCP_PROJECT_PATH"] = project_path or ""

            with (
                contextlib.redirect_stdout(stdout_buffer),
                contextlib.redirect_stderr(stderr_buffer),
            ):
                exec(compile(code, namespace["__file__"], "exec"), namespace, namespace)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }

        result = {
            "status": status,
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "data": namespace.get("__arcgis_mcp_result__"),
            "error": error,
            "workspace": workspace,
            "project_path": project_path,
        }
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        sys.exit(0 if status == "success" else 1)
        """
    ).strip()


def _build_execution_hint(stderr: str, error: dict[str, Any] | None) -> str | None:
    combined = "\n".join(
        filter(None, [stderr, (error or {}).get("message", ""), (error or {}).get("traceback", "")])
    )
    lowered = combined.lower()
    if "schema lock" in lowered or "cannot acquire a lock" in lowered:
        return "检测到 ArcGIS 数据锁定问题，请关闭占用该数据的图层、编辑会话或外部程序后重试。"
    if "license" in lowered and "not available" in lowered:
        return "检测到 ArcGIS 许可不可用，请确认 ArcGIS Pro 已完成登录并具有对应工具许可。"
    if "module not found" in lowered and "arcpy" in lowered:
        return (
            "当前解释器无法导入 arcpy，请确认发现到的是 ArcGIS Pro 自带 Python，而不是普通 Python。"
        )
    return None


def run_in_arcgis_env(
    code: str,
    *,
    workspace: str | None = None,
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    python_executable: str | None = None,
    require_arcpy: bool = True,
) -> ArcPyExecutionResult:
    """在 ArcGIS Pro Python 环境中执行代码，并回收结构化结果。"""
    resolved_python = python_executable
    if resolved_python is None:
        resolved_python = discover_arcgis_pro_python().python_executable

    with tempfile.TemporaryDirectory(prefix="arcgis-mcp-") as temp_dir:
        temp_path = Path(temp_dir)
        payload_path = temp_path / PAYLOAD_FILENAME
        result_path = temp_path / RESULT_FILENAME
        runner_path = temp_path / RUNNER_FILENAME

        payload = {
            "code": code,
            "workspace": workspace,
            "project_path": project_path,
            "open_current_project": open_current_project,
            "require_arcpy": require_arcpy,
        }
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        runner_path.write_text(_build_runner_script(), encoding="utf-8")

        try:
            completed = subprocess.run(  # noqa: S603
                [resolved_python, str(runner_path), str(payload_path), str(result_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ArcPyExecutionResult(
                status="error",
                exit_code=-1,
                python_executable=_normalize_path(resolved_python),
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                data=None,
                error={
                    "type": "TimeoutExpired",
                    "message": f"ArcGIS Python 子进程执行超时，超过 {timeout_seconds} 秒。",
                },
                hint="请缩小处理范围、优化脚本，或适当提高 timeout_seconds 后重试。",
                workspace=workspace,
                project_path=project_path,
            )

        if result_path.exists():
            result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            result_payload = {
                "status": "error",
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "data": None,
                "error": {
                    "type": "RunnerExecutionError",
                    "message": "ArcGIS Python 子进程未生成结果文件。",
                },
                "workspace": workspace,
                "project_path": project_path,
            }

    hint = _build_execution_hint(result_payload.get("stderr", ""), result_payload.get("error"))
    return ArcPyExecutionResult(
        status=result_payload.get("status", "error"),
        exit_code=completed.returncode,
        python_executable=_normalize_path(resolved_python),
        stdout=result_payload.get("stdout", ""),
        stderr=result_payload.get("stderr", completed.stderr),
        data=result_payload.get("data"),
        error=result_payload.get("error"),
        hint=hint,
        workspace=workspace,
        project_path=project_path,
    )


def _result_to_dict(result: ArcPyExecutionResult) -> dict[str, Any]:
    return asdict(result)


def _coerce_result_data(result: ArcPyExecutionResult) -> Any | None:
    if result.data is not None:
        return result.data

    stdout = result.stdout.strip()
    if not stdout:
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _build_resource_payload(
    result: ArcPyExecutionResult,
    *,
    resource_uri: str,
    resource_kind: str,
) -> dict[str, Any]:
    payload = {
        "resource_uri": resource_uri,
        "resource_kind": resource_kind,
        "status": result.status,
        "data": _coerce_result_data(result),
        "execution": _result_to_dict(result),
    }
    if result.error:
        payload["message"] = result.error.get("message")
    return payload


def _build_tool_payload(
    result: ArcPyExecutionResult,
    *,
    tool_name: str,
    message: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "tool": tool_name,
        "status": result.status,
        "data": _coerce_result_data(result),
        "execution": _result_to_dict(result),
    }
    if inputs is not None:
        payload["inputs"] = inputs
    if message:
        payload["message"] = message
    elif result.error:
        payload["message"] = result.error.get("message")
    return payload


def _timestamp_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_arcpy_runtime_check(
    *,
    timeout_seconds: int = 60,
) -> ArcPyExecutionResult:
    return run_in_arcgis_env(
        build_arcpy_runtime_check_code(),
        timeout_seconds=timeout_seconds,
        require_arcpy=True,
    )


def _check_exists(path: str | None) -> bool:
    return bool(path) and Path(path).exists()


def _read_project_layers(
    *, project_path: str | None = None, open_current_project: bool = False
) -> ArcPyExecutionResult:
    return run_in_arcgis_env(
        build_project_layers_code(),
        project_path=project_path,
        open_current_project=open_current_project,
        require_arcpy=True,
    )


def _read_gdb_schema(gdb_path: str) -> ArcPyExecutionResult:
    return run_in_arcgis_env(
        build_gdb_schema_code(gdb_path),
        workspace=gdb_path,
        require_arcpy=True,
    )


def _read_project_context(
    *, project_path: str | None = None, open_current_project: bool = False
) -> ArcPyExecutionResult:
    return run_in_arcgis_env(
        build_project_context_code(),
        project_path=project_path,
        open_current_project=open_current_project,
        require_arcpy=True,
    )


def _build_doctor_report(timeout_seconds: int = 60) -> dict[str, Any]:
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
    except ArcGISDiscoveryError as exc:
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
        runtime_result = _run_arcpy_runtime_check(timeout_seconds=timeout_seconds)
        runtime_payload = _coerce_result_data(runtime_result)
        if runtime_result.status == "success":
            checks.append(
                {
                    "name": "arcpy_runtime_check",
                    "status": "pass",
                    "message": "ArcPy 运行时检查通过。",
                    "details": runtime_payload,
                }
            )
            if not _check_exists(runtime_result.python_executable):
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
                    "details": _result_to_dict(runtime_result),
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
        "server": SERVER_NAME,
        "timestamp_utc": _timestamp_utc_iso(),
        "arcgis_python": asdict(python_info) if python_info is not None else None,
        "runtime": runtime_payload,
        "checks": checks,
        "recommendations": recommendations,
    }


@mcp.resource("arcgis://server/status")
def server_status() -> str:
    """返回当前服务器与 ArcGIS 发现状态。"""
    try:
        python_info = discover_arcgis_pro_python()
        payload = {
            "server": SERVER_NAME,
            "status": "ready",
            "arcgis_python": asdict(python_info),
        }
    except ArcGISDiscoveryError as exc:
        payload = {
            "server": SERVER_NAME,
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
            "example_project": build_project_layers_resource_uri(r"C:\GIS\Projects\Example.aprx"),
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
    result = _read_project_layers(open_current_project=True)
    payload = _build_resource_payload(
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
        project_path = _decode_resource_path(project_ref)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "resource_uri": f"arcgis://project/{project_ref}/layers",
            "resource_kind": "project_layers",
            "status": "error",
            "message": f"无法解析 project_ref：{exc}",
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    result = _read_project_layers(project_path=project_path)
    payload = _build_resource_payload(
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
    result = _read_project_context(open_current_project=True)
    payload = _build_resource_payload(
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
        project_path = _decode_resource_path(project_ref)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "resource_uri": f"arcgis://project/{project_ref}/context",
            "resource_kind": "project_context",
            "status": "error",
            "message": f"无法解析 project_ref：{exc}",
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    result = _read_project_context(project_path=project_path)
    payload = _build_resource_payload(
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
        gdb_path = _decode_resource_path(gdb_ref)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "resource_uri": f"arcgis://gdb/{gdb_ref}/schema",
            "resource_kind": "gdb_schema",
            "status": "error",
            "message": f"无法解析 gdb_ref：{exc}",
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    result = _read_gdb_schema(gdb_path)
    payload = _build_resource_payload(
        result,
        resource_uri=build_gdb_schema_resource_uri(gdb_path),
        resource_kind="gdb_schema",
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def detect_arcgis_environment() -> dict[str, Any]:
    """检测 ArcGIS Pro 安装与 Python 解释器路径。"""
    try:
        return {
            "status": "ready",
            "arcgis": asdict(discover_arcgis_pro_python()),
            "resource_catalog_uri": "arcgis://resources/catalog",
        }
    except ArcGISDiscoveryError as exc:
        return {
            "status": "unavailable",
            "message": str(exc),
        }


@mcp.tool()
def ping() -> dict[str, Any]:
    """返回一个最小可验证结果，用于确认客户端已真正调用 MCP Tool。"""
    return {
        "status": "ok",
        "server": SERVER_NAME,
        "timestamp_utc": _timestamp_utc_iso(),
        "message": "如果你看到这条结果，说明这次请求已经真正进入 MCP Tool 调用链路。",
    }


@mcp.tool()
def health_check(timeout_seconds: int = 30) -> dict[str, Any]:
    """返回轻量级健康检查，帮助快速判断 MCP 与 ArcGIS 环境是否可用。"""
    payload: dict[str, Any] = {
        "status": "ready",
        "server": SERVER_NAME,
        "timestamp_utc": _timestamp_utc_iso(),
        "mcp": {
            "status": "ok",
            "message": "health_check 已被实际调用，客户端当前正在使用 MCP Tool。",
        },
    }

    try:
        python_info = discover_arcgis_pro_python()
        payload["arcgis_python"] = asdict(python_info)
    except ArcGISDiscoveryError as exc:
        payload["status"] = "unavailable"
        payload["arcgis_python"] = None
        payload["message"] = str(exc)
        payload["next_step"] = (
            "请先确认 ArcGIS Pro 已安装且可正常启动；如果是在 Trae 或 Cursor 中测试，"
            "请明确要求客户端直接调用 MCP Tool，而不是写测试脚本或手动启动 server。"
        )
        return payload

    runtime_result = _run_arcpy_runtime_check(timeout_seconds=timeout_seconds)
    payload["runtime"] = _result_to_dict(runtime_result)
    payload["runtime_data"] = _coerce_result_data(runtime_result)

    if runtime_result.status != "success":
        payload["status"] = "warning"
        payload["message"] = (
            runtime_result.error.get("message")
            if runtime_result.error
            else "ArcPy 运行时检查未通过。"
        )
        payload["next_step"] = (
            "建议下一步调用 doctor 获取完整诊断，"
            "重点检查许可状态、ArcPy 运行时和客户端是否真的走了 MCP。"
        )
        return payload

    payload["message"] = "MCP 可达，ArcGIS Pro Python 已发现，ArcPy 运行时检查通过。"
    payload["next_step"] = (
        "可以继续调用 inspect_gdb、inspect_project_context、buffer_features 或 clip_features。"
    )
    return payload


@mcp.tool()
def doctor(timeout_seconds: int = 60) -> dict[str, Any]:
    """返回面向 GISer 的完整环境诊断报告。"""
    return _build_doctor_report(timeout_seconds=timeout_seconds)


@mcp.tool()
def execute_arcpy_code(
    code: str,
    workspace: str | None = None,
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """在 ArcGIS Pro Python 环境中执行 ArcPy 代码并返回 stdout、stderr 与异常信息。"""
    try:
        result = run_in_arcgis_env(
            code,
            workspace=workspace,
            project_path=project_path,
            open_current_project=open_current_project,
            timeout_seconds=timeout_seconds,
            require_arcpy=True,
        )
    except ArcGISDiscoveryError as exc:
        return {
            "status": "unavailable",
            "message": str(exc),
        }
    return _result_to_dict(result)


@mcp.tool()
def buffer_features(
    in_features: str,
    out_feature_class: str,
    buffer_distance_or_field: str,
    dissolve_option: str = "NONE",
    dissolve_field: str | None = None,
    method: str = "PLANAR",
    workspace: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """执行常用 Buffer 分析，返回输出要素摘要和执行信息。"""
    try:
        result = run_in_arcgis_env(
            build_buffer_features_code(
                in_features=in_features,
                out_feature_class=out_feature_class,
                buffer_distance_or_field=buffer_distance_or_field,
                dissolve_option=dissolve_option,
                dissolve_field=dissolve_field,
                method=method,
            ),
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            require_arcpy=True,
        )
    except ArcGISDiscoveryError as exc:
        return {
            "tool": "buffer_features",
            "status": "unavailable",
            "message": str(exc),
        }

    return _build_tool_payload(
        result,
        tool_name="buffer_features",
        message="Buffer 执行完成。" if result.status == "success" else None,
        inputs={
            "in_features": in_features,
            "out_feature_class": out_feature_class,
            "buffer_distance_or_field": buffer_distance_or_field,
            "dissolve_option": dissolve_option,
            "dissolve_field": dissolve_field,
            "method": method,
            "workspace": workspace,
            "timeout_seconds": timeout_seconds,
        },
    )


@mcp.tool()
def clip_features(
    in_features: str,
    clip_features_path: str,
    out_feature_class: str,
    cluster_tolerance: str | None = None,
    workspace: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """执行常用 Clip 分析，返回输出要素摘要和执行信息。"""
    try:
        result = run_in_arcgis_env(
            build_clip_features_code(
                in_features=in_features,
                clip_features=clip_features_path,
                out_feature_class=out_feature_class,
                cluster_tolerance=cluster_tolerance,
            ),
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            require_arcpy=True,
        )
    except ArcGISDiscoveryError as exc:
        return {
            "tool": "clip_features",
            "status": "unavailable",
            "message": str(exc),
        }

    return _build_tool_payload(
        result,
        tool_name="clip_features",
        message="Clip 执行完成。" if result.status == "success" else None,
        inputs={
            "in_features": in_features,
            "clip_features": clip_features_path,
            "out_feature_class": out_feature_class,
            "cluster_tolerance": cluster_tolerance,
            "workspace": workspace,
            "timeout_seconds": timeout_seconds,
        },
    )


@mcp.tool()
def build_gis_resource_uri(
    resource_kind: str,
    path: str | None = None,
    open_current_project: bool = False,
) -> dict[str, Any]:
    """根据资源类型与本地路径生成可读取的 ArcGIS Resource URI。"""
    if resource_kind == "project_layers":
        return {
            "status": "ready",
            "resource_kind": resource_kind,
            "resource_uri": build_project_layers_resource_uri(
                path,
                open_current_project=open_current_project,
            ),
        }

    if resource_kind == "project_context":
        return {
            "status": "ready",
            "resource_kind": resource_kind,
            "resource_uri": build_project_context_resource_uri(
                path,
                open_current_project=open_current_project,
            ),
        }

    if resource_kind == "gdb_schema":
        if not path:
            return {
                "status": "error",
                "message": "gdb_schema 资源必须提供 gdb 路径。",
            }
        return {
            "status": "ready",
            "resource_kind": resource_kind,
            "resource_uri": build_gdb_schema_resource_uri(path),
        }

    return {
        "status": "error",
        "message": (
            "不支持的 resource_kind，可选值为 project_layers、project_context 或 gdb_schema。"
        ),
    }


@mcp.tool()
def list_gis_layers(
    project_path: str | None = None, open_current_project: bool = False
) -> dict[str, Any]:
    """列出工程中的地图、图层、字段与空间参考，并返回对应 Resource URI。"""
    result = _read_project_layers(
        project_path=project_path,
        open_current_project=open_current_project,
    )
    return _build_resource_payload(
        result,
        resource_uri=build_project_layers_resource_uri(
            project_path,
            open_current_project=open_current_project,
        ),
        resource_kind="project_layers",
    )


@mcp.tool()
def inspect_project_context(
    project_path: str | None = None, open_current_project: bool = False
) -> dict[str, Any]:
    """读取工程概览，包括布局、地图框、默认地图候选与数据源状态。"""
    result = _read_project_context(
        project_path=project_path,
        open_current_project=open_current_project,
    )
    return _build_resource_payload(
        result,
        resource_uri=build_project_context_resource_uri(
            project_path,
            open_current_project=open_current_project,
        ),
        resource_kind="project_context",
    )


@mcp.tool()
def inspect_gdb(gdb_path: str) -> dict[str, Any]:
    """检查 GDB 的要素类、字段与空间参考，并返回对应 Resource URI。"""
    result = _read_gdb_schema(gdb_path)
    return _build_resource_payload(
        result,
        resource_uri=build_gdb_schema_resource_uri(gdb_path),
        resource_kind="gdb_schema",
    )


@mcp.tool()
def generate_sync_plan(
    source_description: str, project_context: str | None = None
) -> dict[str, Any]:
    """数据同步逻辑的占位接口，后续可扩展为差异分析与脚本生成能力。"""
    return {
        "status": "todo",
        "message": "数据同步能力尚未实现，当前版本已预留工具接口。",
        "source_description": source_description,
        "project_context": project_context,
    }


def main() -> None:
    """服务启动入口。"""
    if sys.platform != "win32":
        print("警告：ArcGIS Pro MCP Server 设计目标平台为 Windows。", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
