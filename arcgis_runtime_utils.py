from __future__ import annotations

import base64
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

ENV_DROP_KEYS = {
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "__PYVENV_LAUNCHER__",
}
ENV_DROP_PREFIXES = (
    "TRAE_",
    "UV_",
)
ENV_INSPECT_KEYS = (
    "ARCGIS_PRO_PYTHON",
    "ARCGIS_PRO_INSTALL_DIR",
    "TERM",
    "TERM_PROGRAM",
    "COMSPEC",
    "VIRTUAL_ENV",
    "PYTHONHOME",
    "PYTHONPATH",
)
ENV_INSPECT_PREFIXES = (
    "TRAE_",
    "UV_",
)


def build_tool_payload(
    result: Any,
    *,
    tool_name: str,
    result_to_dict: Any,
    coerce_result_data: Any,
    message: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "tool": tool_name,
        "status": result.status,
        "data": coerce_result_data(result),
        "execution": result_to_dict(result),
    }
    if inputs is not None:
        payload["inputs"] = inputs
    if message:
        payload["message"] = message
    elif result.error:
        payload["message"] = result.error.get("message")
    return payload


def timestamp_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(value: str | os.PathLike[str]) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def guess_install_dir_from_python(python_path: str | os.PathLike[str]) -> str:
    normalized_path = Path(normalize_path(python_path))
    marker = ("bin", "Python", "envs", "arcgispro-py3")
    if (
        len(normalized_path.parts) >= len(marker) + 1
        and tuple(normalized_path.parts[-5:-1]) == marker
    ):
        return normalize_path(normalized_path.parents[4])
    return normalize_path(normalized_path.parent)


def encode_resource_path(path: str | os.PathLike[str]) -> str:
    normalized = normalize_path(path)
    encoded = base64.urlsafe_b64encode(normalized.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def decode_resource_path(path_ref: str) -> str:
    padding = "=" * (-len(path_ref) % 4)
    decoded = base64.urlsafe_b64decode(f"{path_ref}{padding}").decode("utf-8")
    return normalize_path(decoded)


def path_exists(path: str | None) -> bool:
    return bool(path) and Path(path).exists()


def build_arcgis_subprocess_env(
    base_env: Mapping[str, str] | None = None,
    *,
    local_appdata_root: str | os.PathLike[str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    for key in list(env):
        if key in ENV_DROP_KEYS or any(key.startswith(prefix) for prefix in ENV_DROP_PREFIXES):
            env.pop(key, None)

    if local_appdata_root is not None:
        local_appdata_path = Path(local_appdata_root).expanduser().resolve(strict=False)
        (local_appdata_path / "ESRI" / "ArcGISPro" / "Toolboxes").mkdir(parents=True, exist_ok=True)
        env["LOCALAPPDATA"] = str(local_appdata_path)

    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["ARCGIS_MCP_SUBPROCESS"] = "1"
    return env


def resolve_temp_root(base_env: Mapping[str, str] | None = None) -> str | None:
    env = dict(base_env or os.environ)
    raw_value = env.get("ARCGIS_MCP_TEMP_DIR")
    if not raw_value:
        return None

    temp_root = Path(raw_value).expanduser().resolve(strict=False)
    temp_root.mkdir(parents=True, exist_ok=True)
    return str(temp_root)


def create_temp_workspace(prefix: str, root: str | None = None) -> Path:
    base_dir = (
        Path(root).expanduser().resolve(strict=False)
        if root
        else Path(tempfile.gettempdir()).resolve(strict=False)
    )
    base_dir.mkdir(parents=True, exist_ok=True)
    workspace = base_dir / f"{prefix}{uuid4().hex[:8]}"
    workspace.mkdir(parents=True, exist_ok=False)
    return workspace


def remove_tree(path: str | os.PathLike[str]) -> None:
    shutil.rmtree(path, ignore_errors=True)


def build_execution_hint(stderr: str, error: dict[str, Any] | None) -> str | None:
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


def collect_runtime_context(base_env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = dict(base_env or os.environ)
    interesting_env = {
        key: value
        for key, value in env.items()
        if key in ENV_INSPECT_KEYS or any(key.startswith(prefix) for prefix in ENV_INSPECT_PREFIXES)
    }
    path_entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    sandbox_indicators = sorted(
        key for key in env if key.startswith("TRAE_") or "sandbox" in key.lower()
    )

    return {
        "pid": os.getpid(),
        "cwd": str(Path.cwd()),
        "python_executable": sys.executable,
        "argv": sys.argv,
        "is_windows": sys.platform == "win32",
        "interesting_env": interesting_env,
        "path_preview": path_entries[:8],
        "sandbox_indicators": sandbox_indicators,
        "trae_like_environment": bool(sandbox_indicators),
    }
