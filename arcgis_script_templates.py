from __future__ import annotations

from textwrap import dedent


def build_project_layers_code(
    include_fields: bool = False,
    include_data_source_details: bool = False,
) -> str:
    code = """
    INCLUDE_FIELDS = __INCLUDE_FIELDS__
    INCLUDE_DATA_SOURCE_DETAILS = __INCLUDE_DATA_SOURCE_DETAILS__


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
        if not INCLUDE_DATA_SOURCE_DETAILS:
            return {
                "path": data_source,
                "status": "skipped",
                "message": "Data source details not probed in default lightweight mode.",
            }
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
                "error": str(exc.__class__.__name__) + ": " + str(exc),
            }


    def list_layer_fields(layer):
        if not INCLUDE_FIELDS:
            return []
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
            return [{"error": str(exc.__class__.__name__) + ": " + str(exc)}]


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
    return (
        dedent(code)
        .replace("__INCLUDE_FIELDS__", repr(include_fields))
        .replace("__INCLUDE_DATA_SOURCE_DETAILS__", repr(include_data_source_details))
        .strip()
    )


def build_gdb_schema_code(gdb_path: str) -> str:
    code = """
    def spatial_reference_to_dict(spatial_reference):
        if not spatial_reference:
            return None
        return {
            "name": getattr(spatial_reference, "name", None),
            "factory_code": getattr(spatial_reference, "factoryCode", None),
            "type": getattr(spatial_reference, "type", None),
            "linear_unit_name": getattr(spatial_reference, "linearUnitName", None),
        }


    def describe_fields(dataset_name):
        return [
            {
                "name": field.name,
                "alias": field.aliasName,
                "type": field.type,
                "length": field.length,
                "nullable": field.isNullable,
            }
            for field in arcpy.ListFields(dataset_name)
        ]


    def describe_feature_class(feature_class_name):
        description = arcpy.Describe(feature_class_name)
        return {
            "name": feature_class_name,
            "catalog_path": getattr(description, "catalogPath", None),
            "shape_type": getattr(description, "shapeType", None),
            "feature_type": getattr(description, "featureType", None),
            "spatial_reference": spatial_reference_to_dict(
                getattr(description, "spatialReference", None)
            ),
            "fields": describe_fields(feature_class_name),
        }


    arcpy.env.workspace = __GDB_PATH__
    feature_datasets = []
    for dataset_name in arcpy.ListDatasets("*", "Feature") or []:
        feature_datasets.append(
            {
                "name": dataset_name,
                "feature_classes": [
                    describe_feature_class(feature_class_name)
                    for feature_class_name in (
                        arcpy.ListFeatureClasses(feature_dataset=dataset_name) or []
                    )
                ],
            }
        )

    standalone_feature_classes = [
        describe_feature_class(feature_class_name)
        for feature_class_name in (arcpy.ListFeatureClasses(feature_dataset="") or [])
    ]

    tables = []
    for table_name in arcpy.ListTables() or []:
        description = arcpy.Describe(table_name)
        tables.append(
            {
                "name": table_name,
                "catalog_path": getattr(description, "catalogPath", None),
                "fields": describe_fields(table_name),
            }
        )

    set_result(
        {
            "workspace": arcpy.env.workspace,
            "feature_datasets": feature_datasets,
            "standalone_feature_classes": standalone_feature_classes,
            "tables": tables,
        }
    )
    """
    return dedent(code).replace("__GDB_PATH__", repr(gdb_path)).strip()


def build_project_context_code(include_source_details: bool = False) -> str:
    code = """
    INCLUDE_SOURCE_DETAILS = __INCLUDE_SOURCE_DETAILS__


    def spatial_reference_to_dict(spatial_reference):
        if not spatial_reference:
            return None
        return {
            "name": getattr(spatial_reference, "name", None),
            "factory_code": getattr(spatial_reference, "factoryCode", None),
            "type": getattr(spatial_reference, "type", None),
        }


    def safe_describe_data_source(data_source, is_broken=False):
        if not data_source:
            return {
                "path": None,
                "status": "missing",
                "is_broken": True,
            }

        if not INCLUDE_SOURCE_DETAILS:
            return {
                "path": data_source,
                "status": "broken" if is_broken else "skipped",
                "is_broken": is_broken,
                "message": "Data source details not probed in default lightweight mode.",
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
                "message": str(exc.__class__.__name__) + ": " + str(exc),
            }


    def summarize_map(current_map):
        broken_layers = []
        layers = []
        for layer in current_map.listLayers():
            data_source = getattr(layer, "dataSource", None)
            layer_is_broken = (
                getattr(layer, "isBroken", None)
                if hasattr(layer, "isBroken")
                else False
            )
            source_status = safe_describe_data_source(data_source, layer_is_broken)
            layer_info = {
                "name": getattr(layer, "name", None),
                "long_name": getattr(layer, "longName", None),
                "visible": getattr(layer, "visible", None),
                "is_feature_layer": getattr(layer, "isFeatureLayer", False),
                "is_group_layer": getattr(layer, "isGroupLayer", False),
                "is_broken": layer_is_broken
                if layer_is_broken is not None
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
                    "source_status": safe_describe_data_source(data_source, False),
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
    return dedent(code).replace("__INCLUDE_SOURCE_DETAILS__", repr(include_source_details)).strip()


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
    code = """
    result = arcpy.analysis.Buffer(
        in_features=__IN_FEATURES__,
        out_feature_class=__OUT_FEATURE_CLASS__,
        buffer_distance_or_field=__BUFFER_DISTANCE_OR_FIELD__,
        dissolve_option=__DISSOLVE_OPTION__,
        dissolve_field=__DISSOLVE_FIELD__,
        method=__METHOD__,
    )

    output_path = result.getOutput(0)
    description = arcpy.Describe(output_path)
    count_result = arcpy.management.GetCount(output_path)
    set_result(
        {
            "tool": "Buffer",
            "output_path": output_path,
            "row_count": int(count_result.getOutput(0)),
            "shape_type": getattr(description, "shapeType", None),
            "spatial_reference": {
                "name": getattr(getattr(description, "spatialReference", None), "name", None),
                "factory_code": getattr(
                    getattr(description, "spatialReference", None), "factoryCode", None
                ),
            },
        }
    )
    """
    return (
        dedent(code)
        .replace("__IN_FEATURES__", repr(in_features))
        .replace("__OUT_FEATURE_CLASS__", repr(out_feature_class))
        .replace("__BUFFER_DISTANCE_OR_FIELD__", repr(buffer_distance_or_field))
        .replace("__DISSOLVE_OPTION__", repr(dissolve_option))
        .replace("__DISSOLVE_FIELD__", repr(dissolve_field))
        .replace("__METHOD__", repr(method))
        .strip()
    )


def build_clip_features_code(
    in_features: str,
    clip_features: str,
    out_feature_class: str,
    cluster_tolerance: str | None,
) -> str:
    code = """
    result = arcpy.analysis.Clip(
        in_features=__IN_FEATURES__,
        clip_features=__CLIP_FEATURES__,
        out_feature_class=__OUT_FEATURE_CLASS__,
        cluster_tolerance=__CLUSTER_TOLERANCE__,
    )

    output_path = result.getOutput(0)
    description = arcpy.Describe(output_path)
    count_result = arcpy.management.GetCount(output_path)
    set_result(
        {
            "tool": "Clip",
            "output_path": output_path,
            "row_count": int(count_result.getOutput(0)),
            "shape_type": getattr(description, "shapeType", None),
            "spatial_reference": {
                "name": getattr(getattr(description, "spatialReference", None), "name", None),
                "factory_code": getattr(
                    getattr(description, "spatialReference", None), "factoryCode", None
                ),
            },
        }
    )
    """
    return (
        dedent(code)
        .replace("__IN_FEATURES__", repr(in_features))
        .replace("__CLIP_FEATURES__", repr(clip_features))
        .replace("__OUT_FEATURE_CLASS__", repr(out_feature_class))
        .replace("__CLUSTER_TOLERANCE__", repr(cluster_tolerance))
        .strip()
    )


def build_validate_project_data_code(
    project_gdb: str,
    land_values_gdb: str | None,
    required_layers_json: str,
    target_srs: str,
    study_area_fc: str | None,
) -> str:
    code = """
    import arcpy
    import json

    PROJECT_GDB = __PROJECT_GDB__
    LAND_VALUES_GDB = __LAND_VALUES_GDB__
    REQUIRED_LAYERS = json.loads(__REQUIRED_LAYERS_JSON__)
    TARGET_SRS = __TARGET_SRS__
    STUDY_AREA_FC = __STUDY_AREA_FC__

    checks = []
    warnings = []
    errors = []
    overall = "pass"

    target_sr = arcpy.SpatialReference(int(TARGET_SRS))

    for layer_name in REQUIRED_LAYERS:
        layer_path = None
        if PROJECT_GDB:
            candidate = f"{PROJECT_GDB}\\\\{layer_name}"
            if arcpy.Exists(candidate):
                layer_path = candidate
        if layer_path is None and LAND_VALUES_GDB:
            candidate = f"{LAND_VALUES_GDB}\\\\{layer_name}"
            if arcpy.Exists(candidate):
                layer_path = candidate

        if not layer_path or not arcpy.Exists(layer_path):
            checks.append({
                "layer": layer_name,
                "exists": False,
                "status": "fail",
            })
            errors.append(f"Missing layer: {layer_name}")
            overall = "fail"
            continue

        desc = arcpy.Describe(layer_path)
        sr = desc.spatialReference
        srs_match = (sr.factoryCode == int(TARGET_SRS)) if sr else False

        check = {
            "layer": layer_name,
            "exists": True,
            "srs_match": srs_match,
            "status": "pass" if srs_match else "warn",
        }

        if desc.datasetType == "FeatureClass":
            count = int(arcpy.management.GetCount(layer_path)[0])
            check["row_count"] = count
            check["shape_type"] = desc.shapeType
            if count == 0:
                check["status"] = "warn"
                warnings.append(f"Empty feature class: {layer_name}")
                if overall == "pass":
                    overall = "warn"
        elif desc.datasetType == "RasterDataset":
            check["cell_size"] = f"{desc.meanCellWidth:.1f}m"
            if not srs_match:
                fc = sr.factoryCode if sr else "unknown"
                msg = f"CRS mismatch for {layer_name}"
                msg += f": expected EPSG:{TARGET_SRS}, got EPSG:{fc}"
                warnings.append(msg)

        if not srs_match:
            if overall == "pass":
                overall = "warn"

        checks.append(check)

    if STUDY_AREA_FC and arcpy.Exists(STUDY_AREA_FC):
        dem_path = f"{PROJECT_GDB}\\\\dem" if PROJECT_GDB else None
        if dem_path and arcpy.Exists(dem_path):
            dem_desc = arcpy.Describe(dem_path)
            sa_desc = arcpy.Describe(STUDY_AREA_FC)
            dem_ext = dem_desc.extent
            sa_ext = sa_desc.extent
            covers = (
                dem_ext.XMin <= sa_ext.XMin and dem_ext.XMax >= sa_ext.XMax and
                dem_ext.YMin <= sa_ext.YMin and dem_ext.YMax >= sa_ext.YMax
            )
            checks.append({
                "layer": "dem_coverage",
                "covers_study_area": covers,
                "status": "pass" if covers else "warn",
            })
            if not covers:
                warnings.append("DEM does not fully cover the study area")
                if overall == "pass":
                    overall = "warn"

    if LAND_VALUES_GDB and arcpy.Exists(LAND_VALUES_GDB):
        lv_path = f"{LAND_VALUES_GDB}\\\\unimproved_land_values"
        if arcpy.Exists(lv_path):
            fields = [f.name for f in arcpy.ListFields(lv_path)]
            has_val_ha = "Val_ha" in fields
            checks.append({
                "layer": "unimproved_land_values",
                "exists": True,
                "has_Val_ha_field": has_val_ha,
                "status": "pass" if has_val_ha else "warn",
            })
            if not has_val_ha:
                warnings.append("land_values.gdb/unimproved_land_values missing Val_ha field")
                if overall == "pass":
                    overall = "warn"
        else:
            checks.append({"layer": "unimproved_land_values", "exists": False, "status": "warn"})
            warnings.append("land_values.gdb/unimimproved_land_values not found")
            if overall == "pass":
                overall = "warn"

    sa_status = arcpy.CheckExtension("Spatial")
    checks.append({
        "layer": "spatial_analyst_license",
        "status": "pass" if sa_status == "Available" else "fail",
        "license_status": sa_status,
    })
    if sa_status != "Available":
        errors.append("Spatial Analyst extension not available")
        overall = "fail"

    set_result({
        "overall": overall,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    })
    """
    return (
        dedent(code)
        .replace("__PROJECT_GDB__", repr(project_gdb))
        .replace("__LAND_VALUES_GDB__", repr(land_values_gdb))
        .replace("__REQUIRED_LAYERS_JSON__", repr(required_layers_json))
        .replace("__TARGET_SRS__", repr(target_srs))
        .replace("__STUDY_AREA_FC__", repr(study_area_fc))
        .strip()
    )


def build_prepare_analysis_inputs_code(
    project_gdb: str,
    land_values_gdb: str | None,
    study_area_fc: str,
    cell_size: int,
    snap_raster_name: str,
    dem_name: str,
    distance_sources_json: str,
    output_gdb: str,
) -> str:
    code = """
    import arcpy
    import json
    import os
    from arcpy.sa import *

    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True
    arcpy.env.cellSize = __CELL_SIZE__
    arcpy.env.snapRaster = os.path.join(__PROJECT_GDB__, __SNAP_RASTER_NAME__)
    arcpy.env.outputCoordinateSystem = arcpy.SpatialReference(28356)

    PROJECT_GDB = __PROJECT_GDB__
    LAND_VALUES_GDB = __LAND_VALUES_GDB__
    STUDY_AREA_FC = __STUDY_AREA_FC__
    OUTPUT_GDB = __OUTPUT_GDB__
    DISTANCE_SOURCES = json.loads(__DISTANCE_SOURCES_JSON__)

    outputs = {}

    if not arcpy.Exists(OUTPUT_GDB):
        arcpy.management.CreateFileGDB(os.path.dirname(OUTPUT_GDB), os.path.basename(OUTPUT_GDB))

    vector_layers = [
        "protected_areas", "rem_veg", "water_courses",
        "roads_tracks", "coastline", "pop_dwell", "land_use",
    ]
    for name in vector_layers:
        in_path = os.path.join(PROJECT_GDB, name)
        out_path = os.path.join(OUTPUT_GDB, f"{name}_clip")
        if arcpy.Exists(in_path):
            arcpy.analysis.Clip(in_path, STUDY_AREA_FC, out_path)
            outputs[f"{name}_clip"] = out_path

    if LAND_VALUES_GDB:
        lv_in = os.path.join(LAND_VALUES_GDB, "unimproved_land_values")
        lv_out = os.path.join(OUTPUT_GDB, "land_values_clip")
        if arcpy.Exists(lv_in):
            arcpy.analysis.Clip(lv_in, STUDY_AREA_FC, lv_out)
            outputs["land_values_clip"] = lv_out

    dem_in = os.path.join(PROJECT_GDB, __DEM_NAME__)
    dem_out = os.path.join(OUTPUT_GDB, "dem_30m")
    if arcpy.Exists(dem_in):
        arcpy.management.Resample(dem_in, dem_out, __CELL_SIZE__, "BILINEAR")
        outputs["dem_30m"] = dem_out

        slope_out = os.path.join(OUTPUT_GDB, "slope_degrees")
        arcpy.gp.Slope_sa(dem_out, slope_out, "DEGREE")
        outputs["slope_degrees"] = slope_out

    for out_name, src_name in DISTANCE_SOURCES.items():
        src_path = os.path.join(OUTPUT_GDB, f"{src_name}_clip")
        if not arcpy.Exists(src_path):
            src_path = os.path.join(PROJECT_GDB, src_name)
        if arcpy.Exists(src_path):
            dist_out = os.path.join(OUTPUT_GDB, f"dist_{out_name}")
            arcpy.sa.EucDistance(
                src_path, dist_out,
                cell_size=__CELL_SIZE__,
                maximum_distance=10000,
            )
            outputs[f"dist_{out_name}"] = dist_out

    land_use_clip = os.path.join(OUTPUT_GDB, "land_use_clip")
    if arcpy.Exists(land_use_clip):
        fields = [f.name for f in arcpy.ListFields(land_use_clip)]
        if "secondary" in fields:
            select_field = "secondary"
        elif "primary" in fields:
            select_field = "primary"
        else:
            select_field = None
        if select_field:
            res_fc = os.path.join(OUTPUT_GDB, "residential_areas")
            arcpy.analysis.Select(land_use_clip, res_fc, f"{select_field} = 'Residential'")
            outputs["residential_areas"] = res_fc

            dist_urban = os.path.join(OUTPUT_GDB, "dist_urban")
            arcpy.sa.EucDistance(
                res_fc, dist_urban,
                cell_size=__CELL_SIZE__,
                maximum_distance=10000,
            )
            outputs["dist_urban"] = dist_urban

    for name, path in outputs.items():
        if arcpy.Exists(path):
            desc = arcpy.Describe(path)
            if desc.datasetType == "FeatureClass":
                count = int(arcpy.management.GetCount(path)[0])
            else:
                count = "raster"
            outputs[name] = {"path": path, "count": count}

    set_result({
        "outputs": outputs,
        "cell_size": __CELL_SIZE__,
        "output_gdb": OUTPUT_GDB,
    })
    """
    return (
        dedent(code)
        .replace("__PROJECT_GDB__", repr(project_gdb))
        .replace("__LAND_VALUES_GDB__", repr(land_values_gdb))
        .replace("__STUDY_AREA_FC__", repr(study_area_fc))
        .replace("__CELL_SIZE__", repr(cell_size))
        .replace("__SNAP_RASTER_NAME__", repr(snap_raster_name))
        .replace("__DEM_NAME__", repr(dem_name))
        .replace("__DISTANCE_SOURCES_JSON__", repr(distance_sources_json))
        .replace("__OUTPUT_GDB__", repr(output_gdb))
        .strip()
    )


def build_reclassify_criteria_code(
    reclass_table_json: str,
    output_gdb: str,
    nodata_value: int,
) -> str:
    code = """
    import arcpy
    import json
    import os
    from arcpy.sa import *

    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True

    RECLASS_TABLE = json.loads(__RECLASS_TABLE_JSON__)
    OUTPUT_GDB = __OUTPUT_GDB__
    NODATA_VALUE = __NODATA_VALUE__

    results = []

    for entry in RECLASS_TABLE:
        input_raster = entry["input_raster"]
        output_name = entry["output_name"]
        remap = entry["remap"]
        field = entry.get("field", "VALUE")

        if not arcpy.Exists(input_raster):
            results.append({
                "output_name": output_name,
                "status": "error",
                "message": f"Input raster not found: {input_raster}",
            })
            continue

        try:
            remap_obj = arcpy.sa.RemapRange(remap)
            out_raster = arcpy.sa.Reclassify(input_raster, field, remap_obj, NODATA_VALUE)
            out_path = os.path.join(OUTPUT_GDB, output_name)
            out_raster.save(out_path)

            arcpy.management.BuildRasterAttributeTable(out_path)
            class_counts = {}
            nodata_cells = 0
            with arcpy.da.SearchCursor(out_path, ["VALUE", "COUNT"]) as cursor:
                for row in cursor:
                    if row[0] is None:
                        nodata_cells += row[1]
                    else:
                        class_counts[int(row[0])] = int(row[1])

            results.append({
                "output_name": output_name,
                "output_path": out_path,
                "status": "success",
                "class_counts": class_counts,
                "nodata_cells": nodata_cells,
            })
        except Exception as exc:
            results.append({
                "output_name": output_name,
                "status": "error",
                "message": str(exc),
            })

    set_result({"results": results})
    """
    return (
        dedent(code)
        .replace("__RECLASS_TABLE_JSON__", repr(reclass_table_json))
        .replace("__OUTPUT_GDB__", repr(output_gdb))
        .replace("__NODATA_VALUE__", repr(nodata_value))
        .strip()
    )


def build_weighted_suitability_code(
    model_name: str,
    criteria_json: str,
    output_raster: str,
    normalize: bool,
    eval_min: float,
    eval_max: float,
) -> str:
    code = """
    import arcpy
    import json
    import os
    from arcpy.sa import *

    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True

    MODEL_NAME = __MODEL_NAME__
    CRITERIA = json.loads(__CRITERIA_JSON__)
    OUTPUT_RASTER = __OUTPUT_RASTER__
    NORMALIZE = __NORMALIZE__
    EVAL_MIN = __EVAL_MIN__
    EVAL_MAX = __EVAL_MAX__

    weights_sum = sum(c["weight"] for c in CRITERIA)
    if abs(weights_sum - 1.0) > 0.01:
        set_result({
            "status": "error",
            "message": f"Weights sum to {weights_sum:.4f}, must be within ±0.01 of 1.0",
        })
        raise ValueError(f"Weights sum to {weights_sum:.4f}")

    ws_entries = [(c["raster_path"], "VALUE", c["weight"]) for c in CRITERIA]
    ws_table = arcpy.sa.WSTable(ws_entries)
    result = arcpy.sa.WeightedSum(ws_table)

    raw_min = float(arcpy.Raster(result).minimum)
    raw_max = float(arcpy.Raster(result).maximum)

    if NORMALIZE and (raw_min < EVAL_MIN or raw_max > EVAL_MAX):
        normalized = (result - raw_min) / (raw_max - raw_min) * (EVAL_MAX - EVAL_MIN) + EVAL_MIN
        normalized.save(OUTPUT_RASTER)
        output = arcpy.Raster(OUTPUT_RASTER)
        was_normalized = True
    else:
        result.save(OUTPUT_RASTER)
        output = arcpy.Raster(OUTPUT_RASTER)
        was_normalized = False

    props = arcpy.GetRasterProperties_management(output, "MINIMUM;MAXIMUM;MEAN;STD")
    stats = {
        "min": float(props.getOutput(0)),
        "max": float(props.getOutput(1)),
        "mean": float(props.getOutput(2)),
        "std": float(props.getOutput(3)),
    }

    histogram = {}
    for cls in range(1, 6):
        class_raster = arcpy.sa.Con(int(output) == cls, 1, 0)
        count = int(arcpy.GetRasterProperties_management(class_raster, "SUM").getOutput(0))
        histogram[cls] = count

    weights_used = {f"criterion_{i}": c["weight"] for i, c in enumerate(CRITERIA)}

    set_result({
        "model_name": MODEL_NAME,
        "output_path": OUTPUT_RASTER,
        "statistics": stats,
        "class_histogram": histogram,
        "weights_used": weights_used,
        "was_normalized": was_normalized,
        "raw_range": {"min": raw_min, "max": raw_max},
    })
    """
    return (
        dedent(code)
        .replace("__MODEL_NAME__", repr(model_name))
        .replace("__CRITERIA_JSON__", repr(criteria_json))
        .replace("__OUTPUT_RASTER__", repr(output_raster))
        .replace("__NORMALIZE__", repr(normalize))
        .replace("__EVAL_MIN__", repr(eval_min))
        .replace("__EVAL_MAX__", repr(eval_max))
        .strip()
    )


def build_conflict_analysis_code(
    conservation_raster: str,
    urban_raster: str,
    threshold: float,
    output_gdb: str,
    land_use_raster: str | None,
    cell_size_area_ha: float | None,
) -> str:
    code = """
    import arcpy
    import os
    from arcpy.sa import *

    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True

    CONSERVATION_RASTER = __CONSERVATION_RASTER__
    URBAN_RASTER = __URBAN_RASTER__
    THRESHOLD = __THRESHOLD__
    OUTPUT_GDB = __OUTPUT_GDB__
    LAND_USE_RASTER = __LAND_USE_RASTER__
    CELL_AREA_HA = __CELL_SIZE_AREA_HA__

    cons = arcpy.Raster(CONSERVATION_RASTER)
    urban = arcpy.Raster(URBAN_RASTER)

    conflict = arcpy.sa.Con((cons >= THRESHOLD) & (urban >= THRESHOLD), 1, 0)
    conflict_path = os.path.join(OUTPUT_GDB, "conflict_map")
    conflict.save(conflict_path)

    allocation = arcpy.sa.Con(cons > urban, 1, arcpy.sa.Con(urban > cons, 2, 3))
    if LAND_USE_RASTER and arcpy.Exists(LAND_USE_RASTER):
        tie_areas = arcpy.sa.Con(allocation == 3, 1, 0)
        cons_landuse = arcpy.sa.Con(arcpy.Raster(LAND_USE_RASTER) <= 2, 1, 0)
        urban_landuse = arcpy.sa.Con(arcpy.Raster(LAND_USE_RASTER) >= 4, 2, 0)
        allocation = arcpy.sa.Con(
            allocation == 3,
            arcpy.sa.Con(cons_landuse == 1, 1, arcpy.sa.Con(urban_landuse == 2, 2, 3)),
            allocation
        )
    allocation_path = os.path.join(OUTPUT_GDB, "allocation_map")
    allocation.save(allocation_path)

    if CELL_AREA_HA:
        cell_area_ha = CELL_AREA_HA
    else:
        desc = arcpy.Describe(CONSERVATION_RASTER)
        cell_area_ha = (desc.meanCellWidth * desc.meanCellHeight) / 10000.0

    def count_cells(raster_path, value):
        r = arcpy.sa.Con(arcpy.Raster(raster_path) == value, 1, 0)
        return int(arcpy.GetRasterProperties_management(r, "SUM").getOutput(0))

    conflict_cells = count_cells(conflict_path, 1)
    no_conflict_cells = count_cells(conflict_path, 0)
    total_cells = conflict_cells + no_conflict_cells

    cons_cells = count_cells(allocation_path, 1)
    urban_cells = count_cells(allocation_path, 2)
    other_cells = count_cells(allocation_path, 3)

    set_result({
        "conflict_map": conflict_path,
        "allocation_map": allocation_path,
        "threshold": THRESHOLD,
        "cell_area_ha": round(cell_area_ha, 4),
        "conflict_area": {
            "conflict_cells": conflict_cells,
            "conflict_ha": round(conflict_cells * cell_area_ha, 1),
            "no_conflict_ha": round(no_conflict_cells * cell_area_ha, 1),
            "conflict_pct": round(conflict_cells / total_cells * 100, 1) if total_cells > 0 else 0,
        },
        "allocation_area": {
            "conservation_cells": cons_cells,
            "conservation_ha": round(cons_cells * cell_area_ha, 1),
            "urban_residential_cells": urban_cells,
            "urban_residential_ha": round(urban_cells * cell_area_ha, 1),
            "other_cells": other_cells,
            "other_ha": round(other_cells * cell_area_ha, 1),
        },
    })
    """
    return (
        dedent(code)
        .replace("__CONSERVATION_RASTER__", repr(conservation_raster))
        .replace("__URBAN_RASTER__", repr(urban_raster))
        .replace("__THRESHOLD__", repr(threshold))
        .replace("__OUTPUT_GDB__", repr(output_gdb))
        .replace("__LAND_USE_RASTER__", repr(land_use_raster))
        .replace("__CELL_SIZE_AREA_HA__", repr(cell_size_area_ha))
        .strip()
    )


def build_raster_area_summary_code(
    raster_path: str,
    cell_area_ha: float | None,
    output_csv: str | None,
) -> str:
    code = """
    import arcpy
    import csv
    import os

    RASTER_PATH = __RASTER_PATH__
    CELL_AREA_HA = __CELL_AREA_HA__
    OUTPUT_CSV = __OUTPUT_CSV__

    desc = arcpy.Describe(RASTER_PATH)
    if CELL_AREA_HA:
        cell_area_ha = CELL_AREA_HA
    else:
        cell_area_ha = (desc.meanCellWidth * desc.meanCellHeight) / 10000.0

    raster = arcpy.Raster(RASTER_PATH)
    if raster.isInteger:
        arcpy.management.BuildRasterAttributeTable(RASTER_PATH)
        counts = {}
        with arcpy.da.SearchCursor(RASTER_PATH, ["VALUE", "COUNT"]) as cursor:
            for row in cursor:
                if row[0] is not None:
                    counts[int(row[0])] = int(row[1])
    else:
        counts = {}
        rounded = arcpy.sa.Int(raster + 0.5)
        scratch = arcpy.env.scratchGDB or os.path.dirname(RASTER_PATH)
        temp_path = os.path.join(scratch, "temp_rounded")
        rounded.save(temp_path)
        arcpy.management.BuildRasterAttributeTable(temp_path)
        with arcpy.da.SearchCursor(temp_path, ["VALUE", "COUNT"]) as cursor:
            for row in cursor:
                if row[0] is not None:
                    counts[int(row[0])] = int(row[1])

    total_cells = sum(counts.values())
    total_area_ha = total_cells * cell_area_ha

    classes = []
    for cls in sorted(counts.keys()):
        cells = counts[cls]
        area_ha = cells * cell_area_ha
        pct = (cells / total_cells * 100) if total_cells > 0 else 0
        classes.append({
            "class": cls,
            "cell_count": cells,
            "area_ha": round(area_ha, 1),
            "percentage": round(pct, 1),
        })

    if OUTPUT_CSV:
        with open(OUTPUT_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["class", "cell_count", "area_ha", "percentage"])
            for c in classes:
                writer.writerow([c["class"], c["cell_count"], c["area_ha"], c["percentage"]])

    props = arcpy.GetRasterProperties_management(RASTER_PATH, "MINIMUM;MAXIMUM;MEAN;STD")
    set_result({
        "raster": RASTER_PATH,
        "cell_size_m": round(desc.meanCellWidth, 1),
        "cell_area_ha": round(cell_area_ha, 4),
        "total_area_ha": round(total_area_ha, 1),
        "statistics": {
            "min": float(props.getOutput(0)),
            "max": float(props.getOutput(1)),
            "mean": float(props.getOutput(2)),
            "std": float(props.getOutput(3)),
        },
        "classes": classes,
        "csv_path": OUTPUT_CSV,
    })
    """
    return (
        dedent(code)
        .replace("__RASTER_PATH__", repr(raster_path))
        .replace("__CELL_AREA_HA__", repr(cell_area_ha))
        .replace("__OUTPUT_CSV__", repr(output_csv))
        .strip()
    )


def build_sensitivity_check_code(
    conservation_rasters_json: str,
    urban_rasters_json: str,
    conservation_weights_json: str,
    urban_weights_json: str,
    baseline_allocation: str,
    perturbation_pct: float,
    thresholds_json: str,
    output_gdb: str,
    output_csv: str | None,
) -> str:
    code = """
    import arcpy
    import csv
    import json
    import os
    from arcpy.sa import *

    arcpy.CheckOutExtension("Spatial")
    arcpy.env.overwriteOutput = True

    CONS_RASTERS = json.loads(__CONSERVATION_RASTERS_JSON__)
    URBAN_RASTERS = json.loads(__URBAN_RASTERS_JSON__)
    CONS_WEIGHTS = json.loads(__CONSERVATION_WEIGHTS_JSON__)
    URBAN_WEIGHTS = json.loads(__URBAN_WEIGHTS_JSON__)
    BASELINE_ALLOC = __BASELINE_ALLOCATION__
    PERT_PCT = __PERTURBATION_PCT__
    THRESHOLDS = json.loads(__THRESHOLDS_JSON__)
    OUTPUT_GDB = __OUTPUT_GDB__
    OUTPUT_CSV = __OUTPUT_CSV__

    def perturb_weights(weights, idx, direction):
        factor = 1.0 + (PERT_PCT / 100.0) if direction == "+" else 1.0 - (PERT_PCT / 100.0)
        perturbed = list(weights)
        perturbed[idx] *= factor
        s = sum(perturbed)
        return [w / s for w in perturbed]

    def compute_wlc(raster_paths, weights):
        result = arcpy.Raster(raster_paths[0]) * weights[0]
        for i in range(1, len(raster_paths)):
            result = result + arcpy.Raster(raster_paths[i]) * weights[i]
        return result

    def normalize_raster(r):
        mn = float(arcpy.GetRasterProperties_management(r, "MINIMUM").getOutput(0))
        mx = float(arcpy.GetRasterProperties_management(r, "MAXIMUM").getOutput(0))
        if mx == mn:
            return r
        return ((r - mn) / (mx - mn)) * 4 + 1

    def compute_allocation(cons, urban):
        return arcpy.sa.Con(cons > urban, 1, arcpy.sa.Con(urban > cons, 2, 3))

    def count_changed(alloc_new, alloc_baseline):
        diff = arcpy.sa.Con(alloc_new != alloc_baseline, 1, 0)
        return int(arcpy.GetRasterProperties_management(diff, "SUM").getOutput(0))

    def count_cells(raster_path, value):
        r = arcpy.sa.Con(arcpy.Raster(raster_path) == value, 1, 0)
        return int(arcpy.GetRasterProperties_management(r, "SUM").getOutput(0))

    baseline_alloc_raster = arcpy.Raster(BASELINE_ALLOC)
    total_cells = 0
    for val in [1, 2, 3]:
        total_cells += count_cells(BASELINE_ALLOC, val)

    cell_area_ha = (
        arcpy.Describe(CONS_RASTERS[0]).meanCellWidth
        * arcpy.Describe(CONS_RASTERS[0]).meanCellHeight
    ) / 10000.0

    cons_base_wlc = compute_wlc(CONS_RASTERS, CONS_WEIGHTS)
    cons_base_norm = normalize_raster(cons_base_wlc)
    urban_base_wlc = compute_wlc(URBAN_RASTERS, URBAN_WEIGHTS)
    urban_base_norm = normalize_raster(urban_base_wlc)

    scenarios = []
    scenario_id = 0

    cons_names = [f"C{i+1}" for i in range(len(CONS_WEIGHTS))]
    urban_names = [f"U{i+1}" for i in range(len(URBAN_WEIGHTS))]

    for criteria_name, weights_base, raster_paths, landuse_label in [
        (cons_names, CONS_WEIGHTS, CONS_RASTERS, "Conservation"),
        (urban_names, URBAN_WEIGHTS, URBAN_RASTERS, "Urban"),
    ]:
        for idx in range(len(weights_base)):
            for direction in ["+", "-"]:
                scenario_id += 1
                perturbed_w = perturb_weights(weights_base, idx, direction)
                actual_pct = ((perturbed_w[idx] / weights_base[idx]) - 1.0) * 100.0

                if landuse_label == "Conservation":
                    cons_wlc_temp = compute_wlc(raster_paths, perturbed_w)
                    cons_norm_temp = normalize_raster(cons_wlc_temp)
                    urban_norm_temp = urban_base_norm
                else:
                    urban_wlc_temp = compute_wlc(raster_paths, perturbed_w)
                    urban_norm_temp = normalize_raster(urban_wlc_temp)
                    cons_norm_temp = cons_base_norm

                alloc_temp = compute_allocation(cons_norm_temp, urban_norm_temp)
                alloc_temp_path = os.path.join(OUTPUT_GDB, f"temp_alloc_{scenario_id}")
                alloc_temp.save(alloc_temp_path)
                alloc_counts = {}
                for val in [1, 2, 3]:
                    alloc_counts[val] = count_cells(alloc_temp_path, val)

                changed = count_changed(alloc_temp, baseline_alloc_raster)
                pct_changed = (changed / total_cells * 100) if total_cells > 0 else 0

                conflict_temp = arcpy.sa.Con(
                    (cons_norm_temp >= 4.0) & (urban_norm_temp >= 4.0),
                    1, 0,
                )
                conflict_path = os.path.join(OUTPUT_GDB, f"temp_conflict_{scenario_id}")
                conflict_temp.save(conflict_path)
                conflict_cnt = count_cells(conflict_path, 1)
                conflict_ha = conflict_cnt * cell_area_ha

                cons_props = arcpy.GetRasterProperties_management(cons_norm_temp, "MEAN;STD")
                urban_props = arcpy.GetRasterProperties_management(urban_norm_temp, "MEAN;STD")

                scenarios.append({
                    "scenario_id": f"S{scenario_id:03d}",
                    "scenario_type": "weight_perturbation",
                    "perturbed_criterion": f"{landuse_label}_{criteria_name[idx]}",
                    "direction": direction,
                    "perturbation_pct": f"{actual_pct:+.1f}",
                    "threshold": 4.0,
                    "alloc_conservation_cells": alloc_counts[1],
                    "alloc_urban_cells": alloc_counts[2],
                    "alloc_other_cells": alloc_counts[3],
                    "cells_changed": changed,
                    "pct_cells_changed": f"{pct_changed:.2f}",
                    "conflict_cells": conflict_cnt,
                    "conflict_area_ha": f"{conflict_ha:.1f}",
                    "cons_mean": f"{float(cons_props.getOutput(0)):.4f}",
                    "cons_std": f"{float(cons_props.getOutput(1)):.4f}",
                    "urban_mean": f"{float(urban_props.getOutput(0)):.4f}",
                    "urban_std": f"{float(urban_props.getOutput(1)):.4f}",
                })

    for threshold in THRESHOLDS:
        scenario_id += 1
        conflict_temp = arcpy.sa.Con(
            (cons_base_norm >= threshold) & (urban_base_norm >= threshold),
            1, 0,
        )
        conflict_path = os.path.join(OUTPUT_GDB, f"temp_conflict_thresh_{scenario_id}")
        conflict_temp.save(conflict_path)
        conflict_cnt = count_cells(conflict_path, 1)
        conflict_ha = conflict_cnt * cell_area_ha

        cons_props = arcpy.GetRasterProperties_management(cons_base_norm, "MEAN;STD")
        urban_props = arcpy.GetRasterProperties_management(urban_base_norm, "MEAN;STD")

        scenarios.append({
            "scenario_id": f"S{scenario_id:03d}",
            "scenario_type": "threshold_variation",
            "perturbed_criterion": "CONFLICT_THRESHOLD",
            "direction": "N/A",
            "perturbation_pct": "N/A",
            "threshold": threshold,
            "alloc_conservation_cells": 0,
            "alloc_urban_cells": 0,
            "alloc_other_cells": 0,
            "cells_changed": 0,
            "pct_cells_changed": "0.00",
            "conflict_cells": conflict_cnt,
            "conflict_area_ha": f"{conflict_ha:.1f}",
            "cons_mean": f"{float(cons_props.getOutput(0)):.4f}",
            "cons_std": f"{float(cons_props.getOutput(1)):.4f}",
            "urban_mean": f"{float(urban_props.getOutput(0)):.4f}",
            "urban_std": f"{float(urban_props.getOutput(1)):.4f}",
        })

    header = [
        "scenario_id", "scenario_type", "perturbed_criterion", "direction",
        "perturbation_pct", "threshold",
        "alloc_conservation_cells", "alloc_urban_cells", "alloc_other_cells",
        "cells_changed", "pct_cells_changed",
        "conflict_cells", "conflict_area_ha",
        "cons_mean", "cons_std", "urban_mean", "urban_std",
    ]

    csv_path = OUTPUT_CSV or os.path.join(os.path.dirname(OUTPUT_GDB), "sensitivity_analysis.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(scenarios)

    weight_scenarios = [s for s in scenarios if s["scenario_type"] == "weight_perturbation"]
    most_sensitive = max(weight_scenarios, key=lambda s: float(s["pct_cells_changed"]))
    least_sensitive = min(weight_scenarios, key=lambda s: float(s["pct_cells_changed"]))

    set_result({
        "total_scenarios": len(scenarios),
        "weight_perturbation_scenarios": len(weight_scenarios),
        "threshold_scenarios": len(scenarios) - len(weight_scenarios),
        "most_sensitive": most_sensitive["perturbed_criterion"],
        "most_sensitive_pct": most_sensitive["pct_cells_changed"],
        "least_sensitive": least_sensitive["perturbed_criterion"],
        "least_sensitive_pct": least_sensitive["pct_cells_changed"],
        "csv_path": csv_path,
        "scenarios": scenarios,
    })
    """
    return (
        dedent(code)
        .replace("__CONSERVATION_RASTERS_JSON__", repr(conservation_rasters_json))
        .replace("__URBAN_RASTERS_JSON__", repr(urban_rasters_json))
        .replace("__CONSERVATION_WEIGHTS_JSON__", repr(conservation_weights_json))
        .replace("__URBAN_WEIGHTS_JSON__", repr(urban_weights_json))
        .replace("__BASELINE_ALLOCATION__", repr(baseline_allocation))
        .replace("__PERTURBATION_PCT__", repr(perturbation_pct))
        .replace("__THRESHOLDS_JSON__", repr(thresholds_json))
        .replace("__OUTPUT_GDB__", repr(output_gdb))
        .replace("__OUTPUT_CSV__", repr(output_csv))
        .strip()
    )


def build_export_suitability_map_code(
    project_path: str,
    raster_path: str,
    map_name: str,
    title: str,
    subtitle: str | None,
    classification_json: str,
    output_format: str,
    output_path: str,
    dpi: int,
) -> str:
    code = """
    import arcpy
    import json
    import os

    arcpy.env.overwriteOutput = True

    PROJECT_PATH = __PROJECT_PATH__
    RASTER_PATH = __RASTER_PATH__
    MAP_NAME = __MAP_NAME__
    TITLE = __TITLE__
    SUBTITLE = __SUBTITLE__
    CLASSIFICATION = json.loads(__CLASSIFICATION_JSON__)
    OUTPUT_FORMAT = __OUTPUT_FORMAT__
    OUTPUT_PATH = __OUTPUT_PATH__
    DPI = __DPI__

    aprx = arcpy.mp.ArcGISProject(PROJECT_PATH)

    m = None
    for existing_map in aprx.listMaps():
        if existing_map.name == MAP_NAME:
            m = existing_map
            break
    if m is None:
        m = aprx.createMap(MAP_NAME, "MAP")

    m.addDataFromPath(RASTER_PATH)
    lyr = m.listLayers()[0]

    sym = lyr.symbology
    if hasattr(sym, "updateColorizer"):
        sym.updateColorizer("UniqueValuesColorizer")
        sym.renderer.classificationField = "Value"
        if CLASSIFICATION:
            color_list = []
            for c in CLASSIFICATION:
                color_list.append({
                    "label": str(c["value"]),
                    "values": [[c["value"]]],
                    "color": {
                        "type": "CIMRGBColor",
                        "values": [{"r": c["rgb"][0], "g": c["rgb"][1], "b": c["rgb"][2]}],
                    },
                })
            sym.renderer.groups = color_list
    lyr.symbology = sym

    layouts = aprx.listLayouts()
    if layouts:
        layout = layouts[0]
    else:
        layout = aprx.createLayout(297, 210, "MILLIMETERS", "Suitability_Layout")

    map_frames = layout.listElements("MAPFRAME_ELEMENT")
    if map_frames:
        mf = map_frames[0]
        mf.map = m
    else:
        mf = layout.createMapFrame(m, 15, 20, 270, 180, "MILLIMETERS")

    title_elements = layout.listElements("TEXT_ELEMENT")
    title_el = None
    for el in title_elements:
        if "title" in el.name.lower():
            title_el = el
            break
    if title_el:
        title_el.text = TITLE
    else:
        title_el = layout.createTextElement(148.5, 205, TITLE, 14, "POINT")

    if SUBTITLE:
        subtitle_el = None
        for el in title_elements:
            if "subtitle" in el.name.lower():
                subtitle_el = el
                break
        if subtitle_el:
            subtitle_el.text = SUBTITLE

    if OUTPUT_FORMAT.upper() == "PDF":
        layout.exportToPDF(OUTPUT_PATH, resolution=DPI, image_quality="BEST")
    else:
        layout.exportToPNG(OUTPUT_PATH, resolution=DPI)

    file_size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)

    set_result({
        "output_path": OUTPUT_PATH,
        "format": OUTPUT_FORMAT,
        "dpi": DPI,
        "file_size_mb": round(file_size_mb, 2),
    })
    """
    return (
        dedent(code)
        .replace("__PROJECT_PATH__", repr(project_path))
        .replace("__RASTER_PATH__", repr(raster_path))
        .replace("__MAP_NAME__", repr(map_name))
        .replace("__TITLE__", repr(title))
        .replace("__SUBTITLE__", repr(subtitle))
        .replace("__CLASSIFICATION_JSON__", repr(classification_json))
        .replace("__OUTPUT_FORMAT__", repr(output_format))
        .replace("__OUTPUT_PATH__", repr(output_path))
        .replace("__DPI__", repr(dpi))
        .strip()
    )
