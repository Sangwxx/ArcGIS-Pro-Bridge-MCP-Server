from __future__ import annotations

import json
import os
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import arcgis_mcp_server as server
from arcgis_runtime_utils import build_arcgis_subprocess_env, remove_tree

TEST_TEMP_ROOT = Path.cwd() / ".tmp-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["ARCGIS_MCP_TEMP_DIR"] = str(TEST_TEMP_ROOT)


def make_test_dir(prefix: str) -> Path:
    path = TEST_TEMP_ROOT / f"{prefix}{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def create_sample_aprx(path: Path) -> None:
    files = {
        "GISProject.json": {
            "type": "CIMGISProject",
            "defaultGeoDatabase": r".\Demo.gdb",
            "defaultToolbox": r".\toolbox.atbx",
            "defaultFolder": r"D:\GIS\Workspace",
        },
        "Index.json": {
            "DocumentType": "Index",
            "NumberOfNodes": 3,
            "Nodes": [
                {
                    "NodeId": 1,
                    "NodeType": "Map",
                    "FileName": "maps/main.json",
                    "ChildNodeIds": "2",
                },
                {
                    "NodeId": 2,
                    "NodeType": "Layer",
                    "FileName": "layers/roads.json",
                    "ChildNodeIds": "",
                },
                {
                    "NodeId": 3,
                    "NodeType": "Layout",
                    "FileName": "layouts/layout.json",
                    "ChildNodeIds": "",
                },
            ],
        },
        "maps/main.json": {
            "type": "CIMMap",
            "name": "主地图",
            "uRI": "CIMPATH=maps/main.json",
            "mapType": "Map",
            "spatialReference": {"wkid": 4490, "latestWkid": 4490},
            "layers": ["CIMPATH=layers/roads.json"],
        },
        "layers/roads.json": {
            "type": "CIMFeatureLayer",
            "name": "道路",
            "visibility": True,
            "featureTable": {
                "dataConnection": {
                    "type": "CIMStandardDataConnection",
                    "workspaceConnectionString": r"DATABASE=.\Demo.gdb",
                    "workspaceFactory": "FileGDB",
                    "dataset": "道路",
                    "datasetType": "esriDTFeatureClass",
                },
                "fieldDescriptions": [
                    {
                        "fieldName": "道路.NAME",
                        "alias": "名称",
                        "visible": True,
                        "readOnly": False,
                    }
                ],
            },
        },
        "layouts/layout.json": {
            "type": "CIMLayout",
            "name": "布局1",
            "page": {"width": 297, "height": 210, "units": {"uwkid": 1025}},
            "elements": [
                {
                    "type": "CIMMapFrame",
                    "name": "地图框",
                    "uRI": "CIMPATH=maps/main.json",
                    "view": {
                        "viewableObjectPath": "CIMPATH=maps/main.json",
                        "camera": {"scale": 50000, "heading": 0},
                    },
                }
            ],
        },
    }
    with zipfile.ZipFile(path, "w") as zf:
        for name, payload in files.items():
            zf.writestr(name, json.dumps(payload, ensure_ascii=False))


class DiscoverArcGISPythonTests(unittest.TestCase):
    def tearDown(self) -> None:
        server.clear_discovery_cache()

    def test_prefers_explicit_python_environment_variable(self) -> None:
        temp_dir = make_test_dir("discover-")
        self.addCleanup(remove_tree, temp_dir)
        fake_python = temp_dir / "python.exe"
        fake_python.write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"ARCGIS_PRO_PYTHON": str(fake_python)}, clear=True):
            info = server.discover_arcgis_pro_python()

        self.assertEqual(info.python_executable, str(fake_python.resolve()))
        self.assertEqual(info.source, "env:ARCGIS_PRO_PYTHON")

    def test_uses_install_dir_environment_variable(self) -> None:
        install_dir = make_test_dir("discover-")
        self.addCleanup(remove_tree, install_dir)
        python_dir = install_dir / "bin" / "Python" / "envs" / "arcgispro-py3"
        python_dir.mkdir(parents=True)
        fake_python = python_dir / "python.exe"
        fake_python.write_text("", encoding="utf-8")

        with patch.dict(os.environ, {"ARCGIS_PRO_INSTALL_DIR": str(install_dir)}, clear=True):
            info = server.discover_arcgis_pro_python()

        self.assertEqual(info.python_executable, str(fake_python.resolve()))
        self.assertEqual(info.install_dir, str(install_dir.resolve()))
        self.assertEqual(info.source, "env:ARCGIS_PRO_INSTALL_DIR")


class RuntimeIsolationTests(unittest.TestCase):
    def test_build_arcgis_subprocess_env_strips_parent_python_and_trae_variables(self) -> None:
        local_appdata_root = TEST_TEMP_ROOT / "localappdata-env"
        self.addCleanup(remove_tree, local_appdata_root)
        payload = build_arcgis_subprocess_env(
            {
                "PATH": r"C:\Windows\System32",
                "PYTHONPATH": "demo",
                "VIRTUAL_ENV": "venv",
                "UV_PROJECT_ENVIRONMENT": ".venv",
                "TRAE_SANDBOX": "1",
            },
            local_appdata_root=local_appdata_root,
        )

        self.assertEqual(payload["PATH"], r"C:\Windows\System32")
        self.assertNotIn("PYTHONPATH", payload)
        self.assertNotIn("VIRTUAL_ENV", payload)
        self.assertNotIn("UV_PROJECT_ENVIRONMENT", payload)
        self.assertNotIn("TRAE_SANDBOX", payload)
        self.assertEqual(payload["PYTHONUTF8"], "1")
        self.assertEqual(payload["ARCGIS_MCP_SUBPROCESS"], "1")
        self.assertEqual(payload["LOCALAPPDATA"], str(local_appdata_root.resolve()))
        self.assertTrue((local_appdata_root / "ESRI" / "ArcGISPro" / "Toolboxes").exists())

    def test_run_in_arcgis_env_uses_isolated_subprocess_settings(self) -> None:
        completed = type(
            "CompletedProcess",
            (),
            {"returncode": 0, "stdout": "", "stderr": ""},
        )()

        temp_dir = make_test_dir("runtime-")
        self.addCleanup(remove_tree, temp_dir)

        with patch("arcgis_mcp_server.create_temp_workspace", return_value=temp_dir):
            with patch("arcgis_mcp_server.subprocess.run", return_value=completed) as mocked_run:
                result_path = temp_dir / server.RESULT_FILENAME
                result_path.write_text(
                    json.dumps(
                        {
                            "status": "success",
                            "stdout": "",
                            "stderr": "",
                            "data": {"ok": True},
                            "error": None,
                            "workspace": None,
                            "project_path": None,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                result = server.run_in_arcgis_env(
                    "set_result({'ok': True})",
                    python_executable=sys.executable,
                    require_arcpy=False,
                    timeout_seconds=20,
                )

        self.assertEqual(result.status, "success")
        mocked_run.assert_called_once()
        kwargs = mocked_run.call_args.kwargs
        self.assertEqual(kwargs["stdin"], server.subprocess.DEVNULL)
        self.assertEqual(kwargs["env"]["ARCGIS_MCP_SUBPROCESS"], "1")
        self.assertEqual(kwargs["cwd"], str(temp_dir))
        self.assertEqual(
            kwargs["env"]["LOCALAPPDATA"],
            str((temp_dir / "localappdata").resolve()),
        )
        self.assertEqual(kwargs["creationflags"], getattr(server.subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(temp_dir.parent, TEST_TEMP_ROOT)


class RunInArcGISEnvTests(unittest.TestCase):
    def test_captures_stdout_without_arcpy_for_self_test(self) -> None:
        result = server.run_in_arcgis_env(
            "print('hello from subprocess')",
            python_executable=sys.executable,
            require_arcpy=False,
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello from subprocess", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_returns_structured_error_when_user_code_fails(self) -> None:
        result = server.run_in_arcgis_env(
            "raise RuntimeError('boom')",
            python_executable=sys.executable,
            require_arcpy=False,
        )

        self.assertEqual(result.status, "error")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error["type"], "RuntimeError")
        self.assertIn("boom", result.error["message"])

    def test_supports_structured_result_channel(self) -> None:
        result = server.run_in_arcgis_env(
            "set_result({'layers': 3, 'project': 'demo'}); print('ok')",
            python_executable=sys.executable,
            require_arcpy=False,
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, {"layers": 3, "project": "demo"})


class ResourceHelpersTests(unittest.TestCase):
    def test_project_resource_uri_roundtrip(self) -> None:
        project_path = r"D:\GIS\Projects\City.aprx"
        resource_uri = server.build_project_layers_resource_uri(project_path)
        project_ref = resource_uri.split("/")[3]

        self.assertEqual(
            server.decode_resource_path(project_ref),
            str(Path(project_path).resolve()),
        )

    def test_project_context_resource_uri_roundtrip(self) -> None:
        project_path = r"D:\GIS\Projects\Atlas.aprx"
        resource_uri = server.build_project_context_resource_uri(project_path)
        project_ref = resource_uri.split("/")[3]

        self.assertEqual(
            server.decode_resource_path(project_ref),
            str(Path(project_path).resolve()),
        )

    def test_current_project_resource_uri(self) -> None:
        self.assertEqual(
            server.build_project_layers_resource_uri(open_current_project=True),
            "arcgis://project/current/layers",
        )

    def test_gdb_schema_resource_returns_json_payload(self) -> None:
        result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"workspace": r"D:\GIS\Data\demo.gdb", "tables": []},
        )
        encoded = server.build_gdb_schema_resource_uri(r"D:\GIS\Data\demo.gdb").split("/")[3]

        with patch("arcgis_mcp_server._read_gdb_schema", return_value=result):
            payload = json.loads(server.gdb_schema_resource(encoded))

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["resource_kind"], "gdb_schema")
        self.assertEqual(
            payload["data"]["workspace"],
            str(Path(r"D:\GIS\Data\demo.gdb").resolve()),
        )

    def test_project_context_resource_returns_json_payload(self) -> None:
        result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={
                "project": {"file_path": r"D:\GIS\Projects\demo.aprx"},
                "default_map_candidate": {"name": "BaseMap"},
                "layouts": [],
                "maps": [],
                "broken_data_sources": [],
            },
        )
        encoded = server.build_project_context_resource_uri(r"D:\GIS\Projects\demo.aprx").split(
            "/"
        )[3]

        with patch("arcgis_mcp_server._read_project_context", return_value=result):
            payload = json.loads(server.project_context_resource(encoded))

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["resource_kind"], "project_context")
        self.assertEqual(payload["data"]["project"]["file_path"], r"D:\GIS\Projects\demo.aprx")

    def test_inspect_project_context_uses_aprx_archive_fast_path(self) -> None:
        temp_dir = make_test_dir("aprx-")
        self.addCleanup(remove_tree, temp_dir)
        aprx_path = temp_dir / "demo.aprx"
        create_sample_aprx(aprx_path)

        payload = server.inspect_project_context(
            project_path=str(aprx_path),
            timeout_seconds=10,
            include_source_details=False,
        )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["read_mode"], "aprx_archive")
        self.assertEqual(payload["data"]["project"]["map_count"], 1)
        self.assertEqual(payload["data"]["default_map_candidate"]["name"], "主地图")

    def test_list_gis_layers_uses_aprx_archive_fast_path(self) -> None:
        temp_dir = make_test_dir("aprx-")
        self.addCleanup(remove_tree, temp_dir)
        aprx_path = temp_dir / "demo.aprx"
        create_sample_aprx(aprx_path)

        payload = server.list_gis_layers(
            project_path=str(aprx_path),
            timeout_seconds=10,
            include_fields=True,
            include_data_source_details=True,
        )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["read_mode"], "aprx_archive")
        layer = payload["data"]["maps"][0]["layers"][0]
        self.assertEqual(layer["name"], "道路")
        self.assertEqual(layer["fields"][0]["alias"], "名称")
        self.assertEqual(layer["source_status"]["workspace_factory"], "FileGDB")


class DiagnosticToolTests(unittest.TestCase):
    def test_ping_returns_ok(self) -> None:
        payload = server.ping()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["server"], server.SERVER_NAME)
        self.assertIn("MCP Tool", payload["message"])

    def test_health_check_reports_unavailable_when_discovery_fails(self) -> None:
        with patch(
            "arcgis_mcp_server.discover_arcgis_pro_python",
            side_effect=server.ArcGISDiscoveryError("ArcGIS Pro 未安装"),
        ):
            payload = server.health_check()

        self.assertEqual(payload["status"], "unavailable")
        self.assertIsNone(payload["arcgis_python"])
        self.assertIn("ArcGIS Pro 未安装", payload["message"])

    def test_health_check_reports_ready_when_runtime_passes(self) -> None:
        python_info = server.ArcGISPythonInfo(
            install_dir=r"D:\Program Files\ArcGIS\Pro",
            python_executable=(
                r"D:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
            ),
            source="registry:SOFTWARE\\ESRI\\ArcGISPro",
        )
        runtime_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=python_info.python_executable,
            stdout="",
            stderr="",
            data={"product_name": "ArcGISPro", "version": "3.4"},
        )

        with patch("arcgis_mcp_server.discover_arcgis_pro_python", return_value=python_info):
            with patch("arcgis_mcp_server._run_arcpy_runtime_check", return_value=runtime_result):
                payload = server.health_check(timeout_seconds=12)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["arcgis_python"]["install_dir"], python_info.install_dir)
        self.assertEqual(payload["runtime"]["status"], "success")
        self.assertEqual(payload["runtime_data"]["product_name"], "ArcGISPro")

    def test_doctor_returns_detailed_report(self) -> None:
        python_info = server.ArcGISPythonInfo(
            install_dir=r"D:\Program Files\ArcGIS\Pro",
            python_executable=sys.executable,
            source="env:ARCGIS_PRO_PYTHON",
        )
        runtime_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"product_name": "ArcGISPro", "version": "3.4"},
        )

        with patch("arcgis_mcp_server.discover_arcgis_pro_python", return_value=python_info):
            with patch("arcgis_mcp_server._run_arcpy_runtime_check", return_value=runtime_result):
                payload = server.doctor(timeout_seconds=20)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["server"], server.SERVER_NAME)
        self.assertEqual(payload["runtime"]["product_name"], "ArcGISPro")
        self.assertTrue(any(check["name"] == "mcp_tool_reachable" for check in payload["checks"]))

    def test_debug_runtime_context_returns_context(self) -> None:
        payload = server.debug_runtime_context()

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["server"], server.SERVER_NAME)
        self.assertIn("context", payload)
        self.assertIn("cwd", payload["context"])


class ProjectContextToolTests(unittest.TestCase):
    def test_inspect_project_context_uses_lightweight_mode_by_default(self) -> None:
        execution_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"project": {"file_path": r"D:\GIS\Projects\demo.aprx"}},
        )

        with patch(
            "arcgis_mcp_server._read_project_context", return_value=execution_result
        ) as mocked_read:
            payload = server.inspect_project_context(project_path=r"D:\GIS\Projects\demo.aprx")

        mocked_read.assert_called_once_with(
            project_path=r"D:\GIS\Projects\demo.aprx",
            open_current_project=False,
            timeout_seconds=server.DEFAULT_TIMEOUT_SECONDS,
            include_source_details=False,
        )
        self.assertEqual(payload["status"], "success")

    def test_inspect_project_context_supports_explicit_detail_and_timeout(self) -> None:
        execution_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"project": {"file_path": r"D:\GIS\Projects\demo.aprx"}},
        )

        with patch(
            "arcgis_mcp_server._read_project_context", return_value=execution_result
        ) as mocked_read:
            server.inspect_project_context(
                project_path=r"D:\GIS\Projects\demo.aprx",
                timeout_seconds=180,
                include_source_details=True,
            )

        mocked_read.assert_called_once_with(
            project_path=r"D:\GIS\Projects\demo.aprx",
            open_current_project=False,
            timeout_seconds=180,
            include_source_details=True,
        )


class ProjectLayersToolTests(unittest.TestCase):
    def test_list_gis_layers_uses_lightweight_mode_by_default(self) -> None:
        execution_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"maps": []},
        )

        with patch(
            "arcgis_mcp_server._read_project_layers", return_value=execution_result
        ) as mocked_read:
            payload = server.list_gis_layers(project_path=r"D:\GIS\Projects\demo.aprx")

        mocked_read.assert_called_once_with(
            project_path=r"D:\GIS\Projects\demo.aprx",
            open_current_project=False,
            timeout_seconds=server.DEFAULT_TIMEOUT_SECONDS,
            include_fields=False,
            include_data_source_details=False,
        )
        self.assertEqual(payload["status"], "success")

    def test_list_gis_layers_supports_explicit_detail_flags(self) -> None:
        execution_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"maps": []},
        )

        with patch(
            "arcgis_mcp_server._read_project_layers", return_value=execution_result
        ) as mocked_read:
            server.list_gis_layers(
                project_path=r"D:\GIS\Projects\demo.aprx",
                timeout_seconds=180,
                include_fields=True,
                include_data_source_details=True,
            )

        mocked_read.assert_called_once_with(
            project_path=r"D:\GIS\Projects\demo.aprx",
            open_current_project=False,
            timeout_seconds=180,
            include_fields=True,
            include_data_source_details=True,
        )


class GeoprocessingToolTests(unittest.TestCase):
    def test_buffer_features_wraps_execution_result(self) -> None:
        execution_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"tool": "Buffer", "output_path": r"D:\GIS\Data\roads_buffer", "row_count": 42},
        )

        with patch(
            "arcgis_mcp_server.run_in_arcgis_env",
            return_value=execution_result,
        ) as mocked_run:
            payload = server.buffer_features(
                in_features=r"D:\GIS\Data\roads",
                out_feature_class=r"D:\GIS\Data\roads_buffer",
                buffer_distance_or_field="50 Meters",
                workspace=r"D:\GIS\Data\demo.gdb",
                timeout_seconds=90,
            )

        mocked_run.assert_called_once()
        self.assertEqual(payload["tool"], "buffer_features")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["output_path"], r"D:\GIS\Data\roads_buffer")
        self.assertEqual(payload["inputs"]["buffer_distance_or_field"], "50 Meters")

    def test_clip_features_wraps_execution_result(self) -> None:
        execution_result = server.ArcPyExecutionResult(
            status="success",
            exit_code=0,
            python_executable=sys.executable,
            stdout="",
            stderr="",
            data={"tool": "Clip", "output_path": r"D:\GIS\Data\roads_clip", "row_count": 18},
        )

        with patch(
            "arcgis_mcp_server.run_in_arcgis_env",
            return_value=execution_result,
        ) as mocked_run:
            payload = server.clip_features(
                in_features=r"D:\GIS\Data\roads",
                clip_features_path=r"D:\GIS\Data\county_boundary",
                out_feature_class=r"D:\GIS\Data\roads_clip",
                workspace=r"D:\GIS\Data\demo.gdb",
                timeout_seconds=120,
            )

        mocked_run.assert_called_once()
        self.assertEqual(payload["tool"], "clip_features")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["row_count"], 18)
        self.assertEqual(payload["inputs"]["clip_features"], r"D:\GIS\Data\county_boundary")

    def test_buffer_features_returns_unavailable_when_discovery_fails(self) -> None:
        with patch(
            "arcgis_mcp_server.run_in_arcgis_env",
            side_effect=server.ArcGISDiscoveryError("未找到 ArcGIS Pro Python"),
        ):
            payload = server.buffer_features(
                in_features="in_fc",
                out_feature_class="out_fc",
                buffer_distance_or_field="10 Meters",
            )

        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["tool"], "buffer_features")


if __name__ == "__main__":
    unittest.main()
