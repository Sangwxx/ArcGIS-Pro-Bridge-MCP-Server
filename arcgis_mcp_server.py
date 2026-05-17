from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Any

from mcp.server.fastmcp import FastMCP

from arcgis_aprx_archive import (
    can_read_project_archive,
    read_project_context_from_archive,
    read_project_layers_from_archive,
)
from arcgis_mcp_resources import (
    build_gdb_schema_resource_uri,
    build_project_context_resource_uri,
    build_project_layers_resource_uri,
    build_resource_payload,
    coerce_result_data,
    register_resources,
    result_to_dict,
)
from arcgis_mcp_services import (
    build_doctor_report,
    read_gdb_schema,
    read_project_context,
    read_project_layers,
    run_arcpy_runtime_check,
)
from arcgis_runtime_utils import (
    build_arcgis_subprocess_env,
    build_execution_hint,
    build_tool_payload,
    collect_runtime_context,
    create_temp_workspace,
    decode_resource_path,
    guess_install_dir_from_python,
    normalize_path,
    path_exists,
    remove_tree,
    resolve_temp_root,
    timestamp_utc_iso,
    validate_path,
)
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
except ImportError:  # pragma: no cover - only triggered on non-Windows
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
        "Bridges AI agents with local ArcGIS Pro. "
        "ArcPy logic executes via ArcGIS Pro's bundled Python subprocess."
    ),
    json_response=True,
)


def _validate_gis_path(path: str | None, label: str) -> str | None:
    """Validate a GIS path against ARCGIS_MCP_ALLOWED_PATHS if set."""
    if path is None:
        return None
    try:
        return str(validate_path(path))
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from exc


class ArcGISDiscoveryError(RuntimeError):
    """Raised when ArcGIS Pro environment cannot be discovered."""


class ArcGISProNotRunningError(RuntimeError):
    """Raised when open_current_project=True but ArcGIS Pro is not running."""


def is_running_inside_pro() -> bool:
    """Detect whether this process is running inside ArcGIS Pro's Python window.

    ArcGIS Pro sets the ARCGIS_PRO_RUNNING environment variable and provides
    arcpy.mp.ArcGISProject("CURRENT") only when running in-process.
    """
    if os.environ.get("ARCGIS_PRO_RUNNING") == "1":
        return True
    try:
        import arcpy  # type: ignore

        test_project = arcpy.mp.ArcGISProject("CURRENT")
        return getattr(test_project, "filePath", None) is not None
    except Exception:
        return False


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


def _iter_env_python_candidates() -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    explicit_python = os.environ.get("ARCGIS_PRO_PYTHON")
    if explicit_python:
        python_path = Path(explicit_python).expanduser()
        normalized_python_path = normalize_path(python_path)
        candidates.append(
            (
                "env:ARCGIS_PRO_PYTHON",
                normalized_python_path,
                guess_install_dir_from_python(normalized_python_path),
            )
        )

    install_dir = os.environ.get("ARCGIS_PRO_INSTALL_DIR")
    if install_dir:
        install_path = Path(install_dir).expanduser()
        normalized_install_path = normalize_path(install_path)
        for relative_path in ARCGIS_PYTHON_RELATIVE_PATHS:
            candidates.append(
                (
                    "env:ARCGIS_PRO_INSTALL_DIR",
                    normalize_path(install_path / relative_path),
                    normalized_install_path,
                )
            )

    return candidates


def _iter_registry_install_dirs() -> list[tuple[str, str]]:
    if winreg is None:
        return []

    discovered: list[tuple[str, str]] = []
    key_read = getattr(winreg, "KEY_READ", 0)
    registry_views = [key_read]
    for extra_flag_name in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
        extra_flag = getattr(winreg, extra_flag_name, 0)
        if extra_flag:
            registry_views.append(key_read | extra_flag)

    for registry_path in ARCGIS_REGISTRY_PATHS:
        for view_flag in registry_views:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, registry_path, 0, key_read | view_flag
                ) as key:
                    install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
            except OSError:
                continue
            discovered.append((f"registry:{registry_path}", normalize_path(install_dir)))

    return discovered


def _build_python_candidates() -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for source, python_path, install_dir in _iter_env_python_candidates():
        normalized = normalize_path(python_path)
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append((source, normalized, install_dir))

    for source, install_dir in _iter_registry_install_dirs():
        install_path = Path(install_dir)
        for relative_path in ARCGIS_PYTHON_RELATIVE_PATHS:
            python_path = normalize_path(install_path / relative_path)
            if python_path in seen:
                continue
            seen.add(python_path)
            candidates.append((source, python_path, normalize_path(install_path)))

    filesystem_fallback = Path(r"C:\Program Files\ArcGIS\Pro")
    for relative_path in ARCGIS_PYTHON_RELATIVE_PATHS:
        python_path = normalize_path(filesystem_fallback / relative_path)
        if python_path in seen:
            continue
        seen.add(python_path)
        candidates.append(("filesystem:default", python_path, normalize_path(filesystem_fallback)))

    return candidates


def clear_discovery_cache() -> None:
    discover_arcgis_pro_python.cache_clear()


@lru_cache(maxsize=1)
def discover_arcgis_pro_python() -> ArcGISPythonInfo:
    """Auto-discover ArcGIS Pro's bundled Python interpreter."""
    for source, python_path, install_dir in _build_python_candidates():
        if Path(python_path).exists():
            return ArcGISPythonInfo(
                install_dir=normalize_path(install_dir),
                python_executable=python_path,
                source=source,
            )

    raise ArcGISDiscoveryError(
        "ArcGIS Pro Python interpreter not found. Confirm ArcGIS Pro is installed, "
        "or provide path via ARCGIS_PRO_PYTHON / ARCGIS_PRO_INSTALL_DIR."
    )


def _build_runner_script() -> str:
    """Generate wrapper script executed in ArcGIS Python environment."""
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

        class ArcGISProNotRunningError(RuntimeError):
            pass

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
                    if open_current_project and not path and not project_path:
                        raise ArcGISProNotRunningError(
                            'ArcGISProject("CURRENT") only works inside '
                            "ArcGIS Pro's Python window. "
                            "Close ArcGIS Pro and provide an explicit .aprx "
                            "path via project_path, or run this code directly "
                            "in ArcGIS Pro's Python window."
                        )
                    target = path or project_path
                    return arcpy.mp.ArcGISProject(target)

                namespace["open_project"] = open_project

                if project_path:
                    namespace["arcgis_project"] = arcpy.mp.ArcGISProject(project_path)
                elif open_current_project:
                    raise ArcGISProNotRunningError(
                        "open_current_project=True only works inside ArcGIS Pro's Python window. "
                        "Provide a project_path parameter with an explicit .aprx file path instead."
                    )

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
    """Execute code in ArcGIS Pro Python environment and return structured results."""
    resolved_python = python_executable
    if resolved_python is None:
        resolved_python = discover_arcgis_pro_python().python_executable

    temp_root = resolve_temp_root()
    temp_path = create_temp_workspace("arcgis-mcp-", temp_root)
    try:
        payload_path = temp_path / PAYLOAD_FILENAME
        result_path = temp_path / RESULT_FILENAME
        runner_path = temp_path / RUNNER_FILENAME
        local_appdata_path = temp_path / "localappdata"

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
                stdin=subprocess.DEVNULL,
                cwd=str(temp_path),
                env=build_arcgis_subprocess_env(local_appdata_root=local_appdata_path),
                timeout=timeout_seconds,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            return ArcPyExecutionResult(
                status="error",
                exit_code=-1,
                python_executable=normalize_path(resolved_python),
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                data=None,
                error={
                    "type": "TimeoutExpired",
                    "message": (
                        "ArcGIS Python subprocess execution timed out "
                        f"after {timeout_seconds} seconds."
                    ),
                },
                hint=(
                    "Narrow the processing scope, optimize the script, "
                    "or increase timeout_seconds and retry."
                ),
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
                    "message": "ArcGIS Python subprocess did not produce a result file.",
                },
                "workspace": workspace,
                "project_path": project_path,
            }
    finally:
        remove_tree(temp_path)

    hint = build_execution_hint(result_payload.get("stderr", ""), result_payload.get("error"))
    return ArcPyExecutionResult(
        status=result_payload.get("status", "error"),
        exit_code=completed.returncode,
        python_executable=normalize_path(resolved_python),
        stdout=result_payload.get("stdout", ""),
        stderr=result_payload.get("stderr", completed.stderr),
        data=result_payload.get("data"),
        error=result_payload.get("error"),
        hint=hint,
        workspace=workspace,
        project_path=project_path,
    )


def _run_arcpy_runtime_check(
    *,
    timeout_seconds: int = 60,
) -> ArcPyExecutionResult:
    return run_arcpy_runtime_check(
        run_in_arcgis_env=run_in_arcgis_env,
        build_arcpy_runtime_check_code=build_arcpy_runtime_check_code,
        timeout_seconds=timeout_seconds,
    )


def _read_project_layers(
    *,
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    include_fields: bool = False,
    include_data_source_details: bool = False,
) -> ArcPyExecutionResult:
    if can_read_project_archive(project_path, open_current_project=open_current_project):
        return ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=normalize_path(sys.executable),
            stdout="",
            stderr="",
            data=read_project_layers_from_archive(
                project_path,
                include_fields=include_fields,
                include_data_source_details=include_data_source_details,
            ),
            workspace=None,
            project_path=project_path,
        )

    return read_project_layers(
        run_in_arcgis_env=run_in_arcgis_env,
        build_project_layers_code=build_project_layers_code,
        project_path=project_path,
        open_current_project=open_current_project,
        timeout_seconds=timeout_seconds,
        include_fields=include_fields,
        include_data_source_details=include_data_source_details,
    )


def _read_gdb_schema(gdb_path: str) -> ArcPyExecutionResult:
    return read_gdb_schema(
        run_in_arcgis_env=run_in_arcgis_env,
        build_gdb_schema_code=build_gdb_schema_code,
        gdb_path=gdb_path,
    )


def _read_project_context(
    *,
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    include_source_details: bool = False,
) -> ArcPyExecutionResult:
    if can_read_project_archive(project_path, open_current_project=open_current_project):
        return ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=normalize_path(sys.executable),
            stdout="",
            stderr="",
            data=read_project_context_from_archive(
                project_path,
                include_source_details=include_source_details,
            ),
            workspace=None,
            project_path=project_path,
        )

    return read_project_context(
        run_in_arcgis_env=run_in_arcgis_env,
        build_project_context_code=build_project_context_code,
        project_path=project_path,
        open_current_project=open_current_project,
        timeout_seconds=timeout_seconds,
        include_source_details=include_source_details,
    )


def _build_doctor_report(timeout_seconds: int = 60) -> dict[str, Any]:
    return build_doctor_report(
        server_name=SERVER_NAME,
        timestamp_utc_iso=timestamp_utc_iso,
        discover_arcgis_pro_python=discover_arcgis_pro_python,
        arcgis_discovery_error=ArcGISDiscoveryError,
        run_runtime_check=_run_arcpy_runtime_check,
        path_exists=path_exists,
        result_to_dict=result_to_dict,
        coerce_result_data=coerce_result_data,
        timeout_seconds=timeout_seconds,
    )


_resource_handlers = register_resources(
    mcp,
    server_name=SERVER_NAME,
    decode_resource_path=decode_resource_path,
    discover_arcgis_pro_python=discover_arcgis_pro_python,
    arcgis_discovery_error=ArcGISDiscoveryError,
    read_project_layers=lambda **kwargs: _read_project_layers(**kwargs),
    read_project_context=lambda **kwargs: _read_project_context(**kwargs),
    read_gdb_schema=lambda gdb_path: _read_gdb_schema(gdb_path),
)
server_status = _resource_handlers["server_status"]
gis_resource_catalog = _resource_handlers["gis_resource_catalog"]
current_project_layers_resource = _resource_handlers["current_project_layers_resource"]
project_layers_resource = _resource_handlers["project_layers_resource"]
current_project_context_resource = _resource_handlers["current_project_context_resource"]
project_context_resource = _resource_handlers["project_context_resource"]
gdb_schema_resource = _resource_handlers["gdb_schema_resource"]


@mcp.tool()
def detect_arcgis_environment() -> dict[str, Any]:
    """Detect ArcGIS Pro installation and Python interpreter path."""
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
    """Return a minimal verifiable result to confirm the client is actually calling the MCP Tool."""
    return {
        "status": "ok",
        "server": SERVER_NAME,
        "timestamp_utc": timestamp_utc_iso(),
        "message": (
            "If you see this result, the request has successfully entered the MCP Tool call chain."
        ),
    }


@mcp.tool()
def health_check(timeout_seconds: int = 30) -> dict[str, Any]:
    """Return a lightweight health check to determine if MCP and
    ArcGIS environment are available.
    """
    payload: dict[str, Any] = {
        "status": "ready",
        "server": SERVER_NAME,
        "timestamp_utc": timestamp_utc_iso(),
        "mcp": {
            "status": "ok",
            "message": "health_check has been called, client is currently using MCP Tool.",
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
            "Confirm ArcGIS Pro is installed and can start; if testing "
            "in Trae or Cursor, explicitly ask the client to call the "
            "MCP Tool directly instead of writing test scripts or "
            "manually starting the server."
        )
        return payload

    runtime_result = _run_arcpy_runtime_check(timeout_seconds=timeout_seconds)
    payload["runtime"] = result_to_dict(runtime_result)
    payload["runtime_data"] = coerce_result_data(runtime_result)

    if runtime_result.status != "success":
        payload["status"] = "warning"
        payload["message"] = (
            runtime_result.error.get("message")
            if runtime_result.error
            else "ArcPy runtime check did not pass."
        )
        payload["next_step"] = (
            "Next step: call doctor for full diagnostics, "
            "focus on license status, ArcPy runtime, and whether the client is actually using MCP."
        )
        return payload

    payload["message"] = "MCP reachable, ArcGIS Pro Python discovered, ArcPy runtime check passed."
    payload["next_step"] = (
        "Continue with inspect_gdb, inspect_project_context, buffer_features, or clip_features."
    )
    return payload


@mcp.tool()
def doctor(timeout_seconds: int = 60) -> dict[str, Any]:
    """Return a comprehensive environment diagnostic report for GIS users."""
    return _build_doctor_report(timeout_seconds=timeout_seconds)


@mcp.tool()
def debug_runtime_context() -> dict[str, Any]:
    """Return the current MCP process runtime context for debugging
    Trae or sandbox environment differences.
    """
    return {
        "status": "ready",
        "server": SERVER_NAME,
        "timestamp_utc": timestamp_utc_iso(),
        "context": collect_runtime_context(),
    }


@mcp.tool()
def execute_arcpy_code(
    code: str,
    workspace: str | None = None,
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute ArcPy code in ArcGIS Pro Python environment and return
    stdout, stderr, and exception info.
    """
    try:
        workspace = _validate_gis_path(workspace, "workspace")
        project_path = _validate_gis_path(project_path, "project_path")
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
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
    return result_to_dict(result)


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
    """Execute Buffer analysis, return output feature summary and execution info."""
    try:
        in_features = _validate_gis_path(in_features, "in_features")
        out_feature_class = _validate_gis_path(out_feature_class, "out_feature_class")
        workspace = _validate_gis_path(workspace, "workspace")
    except ValueError as exc:
        return {"tool": "buffer_features", "status": "error", "message": str(exc)}
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

    return build_tool_payload(
        result,
        tool_name="buffer_features",
        result_to_dict=result_to_dict,
        coerce_result_data=coerce_result_data,
        message="Buffer execution completed." if result.status == "success" else None,
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
    """Execute Clip analysis, return output feature summary and execution info."""
    try:
        in_features = _validate_gis_path(in_features, "in_features")
        clip_features_path = _validate_gis_path(clip_features_path, "clip_features_path")
        out_feature_class = _validate_gis_path(out_feature_class, "out_feature_class")
        workspace = _validate_gis_path(workspace, "workspace")
    except ValueError as exc:
        return {"tool": "clip_features", "status": "error", "message": str(exc)}
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

    return build_tool_payload(
        result,
        tool_name="clip_features",
        result_to_dict=result_to_dict,
        coerce_result_data=coerce_result_data,
        message="Clip execution completed." if result.status == "success" else None,
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
    """Generate a readable ArcGIS Resource URI based on resource type and local path."""
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
                "message": "gdb_schema resource requires a gdb path.",
            }
        return {
            "status": "ready",
            "resource_kind": resource_kind,
            "resource_uri": build_gdb_schema_resource_uri(path),
        }

    return {
        "status": "error",
        "message": (
            "Unsupported resource_kind, valid values are project_layers, "
            "project_context, or gdb_schema."
        ),
    }


@mcp.tool()
def list_gis_layers(
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    include_fields: bool = False,
    include_data_source_details: bool = False,
) -> dict[str, Any]:
    """List maps, layers, fields, and spatial references in the project
    and return corresponding Resource URI.
    """
    try:
        project_path = _validate_gis_path(project_path, "project_path")
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    result = _read_project_layers(
        project_path=project_path,
        open_current_project=open_current_project,
        timeout_seconds=timeout_seconds,
        include_fields=include_fields,
        include_data_source_details=include_data_source_details,
    )
    return build_resource_payload(
        result,
        resource_uri=build_project_layers_resource_uri(
            project_path,
            open_current_project=open_current_project,
        ),
        resource_kind="project_layers",
    )


@mcp.tool()
def inspect_project_context(
    project_path: str | None = None,
    open_current_project: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    include_source_details: bool = False,
) -> dict[str, Any]:
    """Read project overview including layouts, map frames, default map
    candidates, and data source status.
    """
    try:
        project_path = _validate_gis_path(project_path, "project_path")
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    result = _read_project_context(
        project_path=project_path,
        open_current_project=open_current_project,
        timeout_seconds=timeout_seconds,
        include_source_details=include_source_details,
    )
    return build_resource_payload(
        result,
        resource_uri=build_project_context_resource_uri(
            project_path,
            open_current_project=open_current_project,
        ),
        resource_kind="project_context",
    )


@mcp.tool()
def inspect_gdb(gdb_path: str) -> dict[str, Any]:
    """Inspect GDB feature classes, fields, and spatial references and
    return corresponding Resource URI.
    """
    try:
        gdb_path = _validate_gis_path(gdb_path, "gdb_path")
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    result = _read_gdb_schema(gdb_path)
    return build_resource_payload(
        result,
        resource_uri=build_gdb_schema_resource_uri(gdb_path),
        resource_kind="gdb_schema",
    )


@mcp.tool()
def generate_sync_plan(
    source_description: str, project_context: str | None = None
) -> dict[str, Any]:
    """Placeholder interface for data sync logic, to be extended later
    with diff analysis and script generation.
    """
    return {
        "status": "todo",
        "message": "Data sync capability is not yet implemented, tool interface is reserved.",
        "source_description": source_description,
        "project_context": project_context,
    }


def main() -> None:
    """Server startup entry point."""
    if sys.platform != "win32":
        print("Warning: ArcGIS Pro MCP Server is designed for Windows.", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
