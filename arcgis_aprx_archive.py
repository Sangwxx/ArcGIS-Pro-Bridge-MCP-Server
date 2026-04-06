from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def can_read_project_archive(project_path: str | None, *, open_current_project: bool) -> bool:
    if open_current_project or not project_path:
        return False
    path = Path(project_path)
    return path.suffix.lower() == ".aprx" and path.exists()


class AprxArchiveReader:
    def __init__(self, project_path: str) -> None:
        self.project_path = Path(project_path).expanduser().resolve(strict=False)
        self.project_dir = self.project_path.parent
        self._zip = zipfile.ZipFile(self.project_path)
        self._json_cache: dict[str, dict[str, Any]] = {}
        self.index = self._read_json("Index.json")
        self.project = self._read_json("GISProject.json")
        self.nodes = self.index.get("Nodes", [])
        self.nodes_by_id = {node["NodeId"]: node for node in self.nodes}
        self.map_nodes = [node for node in self.nodes if node.get("NodeType") == "Map"]
        self.layout_nodes = [node for node in self.nodes if node.get("NodeType") == "Layout"]
        self._map_name_by_uri: dict[str, str] = {}

    def close(self) -> None:
        self._zip.close()

    def _read_json(self, member_name: str) -> dict[str, Any]:
        if member_name not in self._json_cache:
            raw = self._zip.read(member_name).decode("utf-8")
            self._json_cache[member_name] = json.loads(raw)
        return self._json_cache[member_name]

    def _resolve_cim_path(self, cim_path: str | None) -> str | None:
        if not cim_path:
            return None
        if cim_path.startswith("CIMPATH="):
            return cim_path.removeprefix("CIMPATH=")
        return cim_path

    def _parse_spatial_reference(
        self, spatial_reference: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if not spatial_reference:
            return None
        factory_code = spatial_reference.get("latestWkid") or spatial_reference.get("wkid")
        return {
            "name": spatial_reference.get("name"),
            "factory_code": factory_code,
            "type": spatial_reference.get("type"),
            "wkid": spatial_reference.get("wkid"),
            "latest_wkid": spatial_reference.get("latestWkid"),
            "vcs_wkid": spatial_reference.get("vcsWkid"),
        }

    def _extract_connection(self, layer_json: dict[str, Any]) -> dict[str, Any] | None:
        feature_table = layer_json.get("featureTable")
        if isinstance(feature_table, dict) and feature_table.get("dataConnection"):
            return feature_table["dataConnection"]
        return layer_json.get("dataConnection")

    def _resolve_workspace_path(self, workspace_connection_string: str | None) -> str | None:
        if not workspace_connection_string:
            return None
        parts = workspace_connection_string.split(";")
        database_value = None
        for part in parts:
            key, _, value = part.partition("=")
            if key.strip().upper() == "DATABASE":
                database_value = value.strip()
                break
        if not database_value:
            return None
        return str((self.project_dir / database_value).resolve(strict=False))

    def _summarize_standard_connection(self, connection: dict[str, Any]) -> dict[str, Any]:
        workspace_path = self._resolve_workspace_path(connection.get("workspaceConnectionString"))
        dataset = connection.get("dataset")
        resolved_dataset_path = None
        if workspace_path and dataset:
            resolved_dataset_path = str((Path(workspace_path) / dataset).resolve(strict=False))
        return {
            "type": connection.get("type"),
            "workspace_factory": connection.get("workspaceFactory"),
            "workspace_connection_string": connection.get("workspaceConnectionString"),
            "workspace_path": workspace_path,
            "dataset": dataset,
            "dataset_type": connection.get("datasetType"),
            "resolved_dataset_path": resolved_dataset_path,
            "status": "not_validated",
            "message": "基于 aprx 元数据解析，未访问实际数据源。",
        }

    def _summarize_connection(self, connection: dict[str, Any] | None) -> dict[str, Any] | None:
        if not connection:
            return None
        connection_type = connection.get("type")
        if connection_type == "CIMStandardDataConnection":
            return self._summarize_standard_connection(connection)
        if connection_type == "CIMRelQueryTableDataConnection":
            return {
                "type": connection_type,
                "name": connection.get("name"),
                "join_type": connection.get("joinType"),
                "status": "not_validated",
                "message": "基于 aprx 元数据解析，未访问实际数据源。",
                "source_table": self._summarize_connection(connection.get("sourceTable")),
                "destination_table": self._summarize_connection(connection.get("destinationTable")),
            }
        return {
            "type": connection_type,
            "status": "not_validated",
            "message": "基于 aprx 元数据解析，未访问实际数据源。",
        }

    def _extract_fields(
        self, layer_json: dict[str, Any], *, include_fields: bool
    ) -> list[dict[str, Any]]:
        if not include_fields:
            return []
        feature_table = layer_json.get("featureTable")
        if not isinstance(feature_table, dict):
            return []
        fields = []
        for field in feature_table.get("fieldDescriptions", []):
            field_name = field.get("fieldName")
            simple_name = field_name.split(".")[-1] if isinstance(field_name, str) else field_name
            fields.append(
                {
                    "name": simple_name,
                    "full_name": field_name,
                    "alias": field.get("alias"),
                    "visible": field.get("visible"),
                    "read_only": field.get("readOnly"),
                }
            )
        return fields

    def _layer_flags(self, layer_type: str | None) -> dict[str, bool]:
        layer_type = layer_type or ""
        return {
            "is_feature_layer": layer_type == "CIMFeatureLayer",
            "is_raster_layer": layer_type == "CIMRasterLayer",
            "is_group_layer": layer_type == "CIMGroupLayer",
        }

    def _load_layer(
        self, cim_path: str, *, include_fields: bool, include_data_source_details: bool
    ) -> dict[str, Any]:
        member_name = self._resolve_cim_path(cim_path)
        if member_name is None:
            return {
                "name": None,
                "long_name": None,
                "visible": None,
                "is_broken": None,
                "is_feature_layer": False,
                "is_raster_layer": False,
                "is_group_layer": False,
                "definition_query": None,
                "data_source": None,
                "source_status": None,
                "fields": [],
            }

        layer_json = self._read_json(member_name)
        flags = self._layer_flags(layer_json.get("type"))
        source_summary = self._summarize_connection(self._extract_connection(layer_json))
        layer_info = {
            "name": layer_json.get("name"),
            "long_name": layer_json.get("name"),
            "visible": layer_json.get("visibility"),
            "is_broken": None,
            "is_feature_layer": flags["is_feature_layer"],
            "is_raster_layer": flags["is_raster_layer"],
            "is_group_layer": flags["is_group_layer"],
            "definition_query": None,
            "data_source": None,
            "source_status": (
                source_summary
                if include_data_source_details
                else {
                    "status": "not_validated",
                    "message": "默认轻量模式下未探测数据源详情。",
                }
            ),
            "fields": self._extract_fields(layer_json, include_fields=include_fields),
            "layer_type": layer_json.get("type"),
        }
        if source_summary and isinstance(source_summary, dict):
            layer_info["data_source"] = source_summary.get(
                "resolved_dataset_path"
            ) or source_summary.get("workspace_path")
        return layer_info

    def _summarize_map(
        self, node: dict[str, Any], *, include_fields: bool, include_data_source_details: bool
    ) -> dict[str, Any]:
        map_json = self._read_json(node["FileName"])
        layers = [
            self._load_layer(
                layer_path,
                include_fields=include_fields,
                include_data_source_details=include_data_source_details,
            )
            for layer_path in map_json.get("layers", [])
        ]
        self._map_name_by_uri[map_json.get("uRI", "")] = map_json.get("name")
        return {
            "name": map_json.get("name"),
            "description": map_json.get("description"),
            "map_type": map_json.get("mapType"),
            "spatial_reference": self._parse_spatial_reference(map_json.get("spatialReference")),
            "layer_count": len(layers),
            "table_count": 0,
            "broken_layer_count": 0,
            "layers": layers,
            "tables": [],
            "broken_layers": [],
        }

    def _summarize_map_frame(self, element: dict[str, Any]) -> dict[str, Any]:
        view = element.get("view", {})
        camera = view.get("camera", {})
        map_uri = element.get("uRI") or view.get("viewableObjectPath")
        return {
            "name": element.get("name"),
            "map_name": self._map_name_by_uri.get(map_uri),
            "camera_scale": camera.get("scale"),
            "camera_heading": camera.get("heading"),
            "element_position_x": None,
            "element_position_y": None,
            "element_width": None,
            "element_height": None,
        }

    def _summarize_layout(self, node: dict[str, Any]) -> dict[str, Any]:
        layout_json = self._read_json(node["FileName"])
        elements = layout_json.get("elements", [])
        map_frames = [
            self._summarize_map_frame(element)
            for element in elements
            if element.get("type") == "CIMMapFrame"
        ]
        page = layout_json.get("page", {})
        return {
            "name": layout_json.get("name"),
            "page_width": page.get("width"),
            "page_height": page.get("height"),
            "page_units": page.get("units", {}).get("uwkid"),
            "map_frame_count": len(map_frames),
            "map_frames": map_frames,
        }

    def read_project_layers(
        self, *, include_fields: bool, include_data_source_details: bool
    ) -> dict[str, Any]:
        maps = [
            self._summarize_map(
                node,
                include_fields=include_fields,
                include_data_source_details=include_data_source_details,
            )
            for node in self.map_nodes
        ]
        return {
            "project": {
                "file_path": str(self.project_path),
                "home_folder": self.project.get("defaultFolder"),
                "default_geodatabase": self.project.get("defaultGeoDatabase"),
            },
            "maps": maps,
            "read_mode": "aprx_archive",
        }

    def read_project_context(self, *, include_source_details: bool) -> dict[str, Any]:
        maps = [
            self._summarize_map(
                node,
                include_fields=False,
                include_data_source_details=include_source_details,
            )
            for node in self.map_nodes
        ]
        layouts = [self._summarize_layout(node) for node in self.layout_nodes]
        default_map_candidate = None
        for layout in layouts:
            for map_frame in layout["map_frames"]:
                if map_frame["map_name"]:
                    default_map_candidate = {
                        "name": map_frame["map_name"],
                        "source": "first_layout_map_frame",
                    }
                    break
            if default_map_candidate:
                break
        if not default_map_candidate and maps:
            default_map_candidate = {
                "name": maps[0]["name"],
                "source": "first_project_map",
            }

        return {
            "project": {
                "file_path": str(self.project_path),
                "home_folder": self.project.get("defaultFolder"),
                "default_geodatabase": self.project.get("defaultGeoDatabase"),
                "default_toolbox": self.project.get("defaultToolbox"),
                "map_count": len(maps),
                "layout_count": len(layouts),
                "broken_layer_count": 0,
                "source_validation_mode": (
                    "archive_metadata_only"
                    if not include_source_details
                    else "archive_metadata_with_connection_summary"
                ),
            },
            "default_map_candidate": default_map_candidate,
            "maps": maps,
            "layouts": layouts,
            "broken_data_sources": [],
            "read_mode": "aprx_archive",
        }


def read_project_layers_from_archive(
    project_path: str,
    *,
    include_fields: bool = False,
    include_data_source_details: bool = False,
) -> dict[str, Any]:
    reader = AprxArchiveReader(project_path)
    try:
        return reader.read_project_layers(
            include_fields=include_fields,
            include_data_source_details=include_data_source_details,
        )
    finally:
        reader.close()


def read_project_context_from_archive(
    project_path: str,
    *,
    include_source_details: bool = False,
) -> dict[str, Any]:
    reader = AprxArchiveReader(project_path)
    try:
        return reader.read_project_context(include_source_details=include_source_details)
    finally:
        reader.close()
