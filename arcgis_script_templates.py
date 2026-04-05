from __future__ import annotations

from textwrap import dedent


def build_project_layers_code() -> str:
    return dedent(
        """
        def spatial_reference_to_dict(spatial_reference):
            if not spatial_reference:
                return None
            return {
                "name": getattr(spatial_reference, "name", None),
                "factory_code": getattr(spatial_reference, "factoryCode", None),
                "type": getattr(spatial_reference, "type", None),
                "linear_unit_name": getattr(spatial_reference, "linearUnitName", None),
            }


        def extent_to_dict(extent):
            if not extent:
                return None
            return {
                "xmin": getattr(extent, "XMin", None),
                "ymin": getattr(extent, "YMin", None),
                "xmax": getattr(extent, "XMax", None),
                "ymax": getattr(extent, "YMax", None),
            }


        def describe_data_source(data_source):
            if not data_source:
                return None
            try:
                description = arcpy.Describe(data_source)
                return {
                    "catalog_path": getattr(description, "catalogPath", None),
                    "dataset_type": getattr(description, "datasetType", None),
                    "shape_type": getattr(description, "shapeType", None),
                    "workspace_path": getattr(description, "path", None),
                    "spatial_reference": spatial_reference_to_dict(
                        getattr(description, "spatialReference", None)
                    ),
                    "extent": extent_to_dict(getattr(description, "extent", None)),
                }
            except Exception as exc:
                return {
                    "path": data_source,
                    "error": f"{exc.__class__.__name__}: {exc}",
                }


        def list_layer_fields(layer):
            if not getattr(layer, "isFeatureLayer", False):
                return []

            data_source = getattr(layer, "dataSource", None)
            if not data_source:
                return []

            try:
                return [
                    {
                        "name": field.name,
                        "alias": field.aliasName,
                        "type": field.type,
                        "length": field.length,
                        "nullable": field.isNullable,
                    }
                    for field in arcpy.ListFields(data_source)
                ]
            except Exception as exc:
                return [{"error": f"{exc.__class__.__name__}: {exc}"}]


        def layer_to_dict(layer):
            layer_info = {
                "name": getattr(layer, "name", None),
                "long_name": getattr(layer, "longName", None),
                "visible": getattr(layer, "visible", None),
                "is_broken": getattr(layer, "isBroken", None),
                "is_feature_layer": getattr(layer, "isFeatureLayer", False),
                "is_raster_layer": getattr(layer, "isRasterLayer", False),
                "is_group_layer": getattr(layer, "isGroupLayer", False),
                "definition_query": getattr(layer, "definitionQuery", None),
                "data_source": getattr(layer, "dataSource", None),
            }
            layer_info["dataset"] = describe_data_source(layer_info["data_source"])
            layer_info["fields"] = list_layer_fields(layer)

            if layer_info["is_group_layer"]:
                layer_info["children"] = [layer_to_dict(child) for child in layer.listLayers()]

            return layer_info


        project = arcgis_project if "arcgis_project" in globals() else open_project()
        payload = {
            "project": {
                "file_path": getattr(project, "filePath", None),
                "home_folder": getattr(project, "homeFolder", None),
                "default_geodatabase": getattr(project, "defaultGeodatabase", None),
            },
            "maps": [],
        }

        for current_map in project.listMaps():
            payload["maps"].append(
                {
                    "name": current_map.name,
                    "description": getattr(current_map, "description", None),
                    "map_type": getattr(current_map, "mapType", None),
                    "spatial_reference": spatial_reference_to_dict(
                        getattr(current_map, "spatialReference", None)
                    ),
                    "layers": [layer_to_dict(layer) for layer in current_map.listLayers()],
                }
            )

        set_result(payload)
        """
    ).strip()


def build_gdb_schema_code(gdb_path: str) -> str:
    return dedent(
        f"""
        def spatial_reference_to_dict(spatial_reference):
            if not spatial_reference:
                return None
            return {{
                "name": getattr(spatial_reference, "name", None),
                "factory_code": getattr(spatial_reference, "factoryCode", None),
                "type": getattr(spatial_reference, "type", None),
                "linear_unit_name": getattr(spatial_reference, "linearUnitName", None),
            }}


        def describe_fields(dataset_name):
            return [
                {{
                    "name": field.name,
                    "alias": field.aliasName,
                    "type": field.type,
                    "length": field.length,
                    "nullable": field.isNullable,
                }}
                for field in arcpy.ListFields(dataset_name)
            ]


        def describe_feature_class(feature_class_name):
            description = arcpy.Describe(feature_class_name)
            return {{
                "name": feature_class_name,
                "catalog_path": getattr(description, "catalogPath", None),
                "shape_type": getattr(description, "shapeType", None),
                "feature_type": getattr(description, "featureType", None),
                "spatial_reference": spatial_reference_to_dict(
                    getattr(description, "spatialReference", None)
                ),
                "fields": describe_fields(feature_class_name),
            }}


        arcpy.env.workspace = {gdb_path!r}
        feature_datasets = []
        for dataset_name in arcpy.ListDatasets("*", "Feature") or []:
            feature_datasets.append(
                {{
                    "name": dataset_name,
                    "feature_classes": [
                        describe_feature_class(feature_class_name)
                        for feature_class_name in (
                            arcpy.ListFeatureClasses(feature_dataset=dataset_name) or []
                        )
                    ],
                }}
            )

        standalone_feature_classes = [
            describe_feature_class(feature_class_name)
            for feature_class_name in (arcpy.ListFeatureClasses(feature_dataset="") or [])
        ]

        tables = []
        for table_name in arcpy.ListTables() or []:
            description = arcpy.Describe(table_name)
            tables.append(
                {{
                    "name": table_name,
                    "catalog_path": getattr(description, "catalogPath", None),
                    "fields": describe_fields(table_name),
                }}
            )

        set_result(
            {{
                "workspace": arcpy.env.workspace,
                "feature_datasets": feature_datasets,
                "standalone_feature_classes": standalone_feature_classes,
                "tables": tables,
            }}
        )
        """
    ).strip()


def build_project_context_code() -> str:
    return dedent(
        """
        def spatial_reference_to_dict(spatial_reference):
            if not spatial_reference:
                return None
            return {
                "name": getattr(spatial_reference, "name", None),
                "factory_code": getattr(spatial_reference, "factoryCode", None),
                "type": getattr(spatial_reference, "type", None),
            }


        def safe_describe_data_source(data_source):
            if not data_source:
                return {
                    "path": None,
                    "status": "missing",
                    "is_broken": True,
                }

            try:
                description = arcpy.Describe(data_source)
                return {
                    "path": data_source,
                    "status": "ok",
                    "is_broken": False,
                    "dataset_type": getattr(description, "datasetType", None),
                    "workspace_path": getattr(description, "path", None),
                    "catalog_path": getattr(description, "catalogPath", None),
                }
            except Exception as exc:
                return {
                    "path": data_source,
                    "status": "broken",
                    "is_broken": True,
                    "message": f"{exc.__class__.__name__}: {exc}",
                }


        def summarize_map(current_map):
            broken_layers = []
            layers = []
            for layer in current_map.listLayers():
                data_source = getattr(layer, "dataSource", None)
                source_status = safe_describe_data_source(data_source)
                layer_info = {
                    "name": getattr(layer, "name", None),
                    "long_name": getattr(layer, "longName", None),
                    "visible": getattr(layer, "visible", None),
                    "is_feature_layer": getattr(layer, "isFeatureLayer", False),
                    "is_group_layer": getattr(layer, "isGroupLayer", False),
                    "is_broken": getattr(layer, "isBroken", None)
                    if hasattr(layer, "isBroken")
                    else source_status["is_broken"],
                    "data_source": data_source,
                    "source_status": source_status,
                }
                layers.append(layer_info)
                if layer_info["is_broken"]:
                    broken_layers.append(
                        {
                            "map_name": current_map.name,
                            "layer_name": layer_info["name"],
                            "long_name": layer_info["long_name"],
                            "data_source": data_source,
                            "source_status": source_status,
                        }
                    )

            tables = []
            for table in current_map.listTables():
                data_source = getattr(table, "dataSource", None)
                tables.append(
                    {
                        "name": getattr(table, "name", None),
                        "data_source": data_source,
                        "source_status": safe_describe_data_source(data_source),
                    }
                )

            return {
                "name": current_map.name,
                "description": getattr(current_map, "description", None),
                "map_type": getattr(current_map, "mapType", None),
                "spatial_reference": spatial_reference_to_dict(
                    getattr(current_map, "spatialReference", None)
                ),
                "layer_count": len(layers),
                "table_count": len(tables),
                "broken_layer_count": len(broken_layers),
                "layers": layers,
                "tables": tables,
                "broken_layers": broken_layers,
            }


        def summarize_map_frame(element):
            camera_scale = None
            camera_heading = None
            linked_map_name = None
            try:
                if getattr(element, "map", None):
                    linked_map_name = element.map.name
            except Exception:
                linked_map_name = None

            try:
                if getattr(element, "camera", None):
                    camera_scale = getattr(element.camera, "scale", None)
                    camera_heading = getattr(element.camera, "heading", None)
            except Exception:
                camera_scale = None
                camera_heading = None

            return {
                "name": getattr(element, "name", None),
                "map_name": linked_map_name,
                "camera_scale": camera_scale,
                "camera_heading": camera_heading,
                "element_position_x": getattr(element, "elementPositionX", None),
                "element_position_y": getattr(element, "elementPositionY", None),
                "element_width": getattr(element, "elementWidth", None),
                "element_height": getattr(element, "elementHeight", None),
            }


        def summarize_layout(layout):
            try:
                elements = layout.listElements("MAPFRAME_ELEMENT")
            except Exception:
                elements = []
            map_frames = [summarize_map_frame(element) for element in elements]
            return {
                "name": getattr(layout, "name", None),
                "page_width": getattr(layout, "pageWidth", None),
                "page_height": getattr(layout, "pageHeight", None),
                "page_units": getattr(layout, "pageUnits", None),
                "map_frame_count": len(map_frames),
                "map_frames": map_frames,
            }


        def infer_default_map_name(project, layouts, maps):
            try:
                active_map = getattr(project, "activeMap", None)
            except Exception:
                active_map = None

            if active_map:
                return {
                    "name": getattr(active_map, "name", None),
                    "source": "active_map",
                }

            for layout in layouts:
                for map_frame in layout["map_frames"]:
                    if map_frame["map_name"]:
                        return {
                            "name": map_frame["map_name"],
                            "source": "first_layout_map_frame",
                        }

            if maps:
                return {
                    "name": maps[0]["name"],
                    "source": "first_project_map",
                }
            return None


        project = arcgis_project if "arcgis_project" in globals() else open_project()
        maps = [summarize_map(current_map) for current_map in project.listMaps()]
        layouts = [summarize_layout(layout) for layout in project.listLayouts()]
        broken_layers = []
        for current_map in maps:
            broken_layers.extend(current_map["broken_layers"])

        set_result(
            {
                "project": {
                    "file_path": getattr(project, "filePath", None),
                    "home_folder": getattr(project, "homeFolder", None),
                    "default_geodatabase": getattr(project, "defaultGeodatabase", None),
                    "default_toolbox": getattr(project, "defaultToolbox", None),
                    "map_count": len(maps),
                    "layout_count": len(layouts),
                    "broken_layer_count": len(broken_layers),
                },
                "default_map_candidate": infer_default_map_name(project, layouts, maps),
                "maps": maps,
                "layouts": layouts,
                "broken_data_sources": broken_layers,
            }
        )
        """
    ).strip()


def build_arcpy_runtime_check_code() -> str:
    return dedent(
        """
        install_info = arcpy.GetInstallInfo()
        set_result(
            {
                "product_name": install_info.get("ProductName"),
                "version": install_info.get("Version"),
                "build_number": install_info.get("BuildNumber"),
                "install_dir": install_info.get("InstallDir"),
                "product_info": arcpy.ProductInfo(),
                "scratch_gdb": getattr(arcpy.env, "scratchGDB", None),
                "scratch_folder": getattr(arcpy.env, "scratchFolder", None),
            }
        )
        """
    ).strip()


def build_buffer_features_code(
    in_features: str,
    out_feature_class: str,
    buffer_distance_or_field: str,
    dissolve_option: str,
    dissolve_field: str | None,
    method: str,
) -> str:
    return dedent(
        f"""
        result = arcpy.analysis.Buffer(
            in_features={in_features!r},
            out_feature_class={out_feature_class!r},
            buffer_distance_or_field={buffer_distance_or_field!r},
            dissolve_option={dissolve_option!r},
            dissolve_field={dissolve_field!r},
            method={method!r},
        )

        output_path = result.getOutput(0)
        description = arcpy.Describe(output_path)
        count_result = arcpy.management.GetCount(output_path)
        set_result(
            {{
                "tool": "Buffer",
                "output_path": output_path,
                "row_count": int(count_result.getOutput(0)),
                "shape_type": getattr(description, "shapeType", None),
                "spatial_reference": {{
                    "name": getattr(getattr(description, "spatialReference", None), "name", None),
                    "factory_code": getattr(
                        getattr(description, "spatialReference", None), "factoryCode", None
                    ),
                }},
            }}
        )
        """
    ).strip()


def build_clip_features_code(
    in_features: str,
    clip_features: str,
    out_feature_class: str,
    cluster_tolerance: str | None,
) -> str:
    return dedent(
        f"""
        result = arcpy.analysis.Clip(
            in_features={in_features!r},
            clip_features={clip_features!r},
            out_feature_class={out_feature_class!r},
            cluster_tolerance={cluster_tolerance!r},
        )

        output_path = result.getOutput(0)
        description = arcpy.Describe(output_path)
        count_result = arcpy.management.GetCount(output_path)
        set_result(
            {{
                "tool": "Clip",
                "output_path": output_path,
                "row_count": int(count_result.getOutput(0)),
                "shape_type": getattr(description, "shapeType", None),
                "spatial_reference": {{
                    "name": getattr(getattr(description, "spatialReference", None), "name", None),
                    "factory_code": getattr(
                        getattr(description, "spatialReference", None), "factoryCode", None
                    ),
                }},
            }}
        )
        """
    ).strip()
