# Prompt Examples

The following prompts can be sent directly to an AI client that supports MCP.

If this is your first time using this workflow, start by reading information, then gradually have the AI execute ArcPy.

## 1. Check the Environment First

Please check whether the ArcGIS Pro environment has been correctly discovered, and tell me which Python path is currently in use.

## 2. Read Layers in the Current Project

Please read the maps and layers in the current ArcGIS Pro project, and tell me:
- What maps exist
- What layers are in each map
- Which layers have broken data sources

## 3. Read a Specific GDB Schema

Please inspect the structure of this GDB: `C:\GIS\Data\CityData.gdb`

Tell me:
- What feature classes exist
- What fields are in each feature class
- What spatial reference is used

## 4. Read a Specific Project Overview

Please read this `.aprx` project: `C:\GIS\Projects\City.aprx`

Tell me:
- What maps exist
- What layouts exist
- What map frames are in each layout
- What the default map candidate is
- Whether there are any broken data sources

## 5. Generate ArcPy First, Then Execute

Based on the `roads` layer in the current project, generate ArcPy Buffer code with a 50-meter buffer distance, output to the default GDB.

Do not execute yet -- show me the code for confirmation first.

## 6. Execute Buffer Directly

Please execute an ArcPy Buffer:
- Input layer: `C:\GIS\Data\roads.shp`
- Output layer: `C:\GIS\Data\roads_buffer_50m.shp`
- Distance: `50 Meters`

After execution, tell me:
- Whether it succeeded
- What stdout contains
- What stderr contains

## 7. Check Map Frames in Layouts

Please read the layouts and map frames in this project: `C:\GIS\Projects\Report.aprx`

Tell me which map each map frame is bound to.
