from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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


def path_exists(path: str | None) -> bool:
    return bool(path) and Path(path).exists()


def build_arcgis_subprocess_env(
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    for key in list(env):
        if key in ENV_DROP_KEYS or any(key.startswith(prefix) for prefix in ENV_DROP_PREFIXES):
            env.pop(key, None)

    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["ARCGIS_MCP_SUBPROCESS"] = "1"
    return env


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
