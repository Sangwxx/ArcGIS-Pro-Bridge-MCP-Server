import arcpy

roads = r"C:\GIS\Data\roads.shp"
output_fc = r"C:\GIS\Data\roads_buffer_50m.shp"

arcpy.analysis.Buffer(
    in_features=roads,
    out_feature_class=output_fc,
    buffer_distance_or_field="50 Meters",
)

print(f"Buffer 完成：{output_fc}")
