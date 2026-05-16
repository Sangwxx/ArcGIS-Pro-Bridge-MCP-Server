# Future Development

## Option 2: C# Add-In + .NET MCP (Real-time Project Access)

This document describes a future enhancement for real-time, in-process access to ArcGIS Pro through a C# Add-In and .NET 8 MCP server.

**Status:** Not implemented - future work

---

## Why This Matters

The current Python MCP server (this repo) accesses ArcGIS Pro projects via `.aprx` file paths. This means:

| Approach | Pros | Cons |
|----------|------|------|
| Current (file-based) | Works without Pro running, simple | No real-time state, Pro must be closed for writes |
| Option 2 (Add-In) | Real-time `MapView.Active`, live state | Requires Pro running with Add-In, C# development |

---

## Architecture Overview

```
OpenCode / Claude / MCP Client
    |
    v
.NET 8 MCP Server (Named Pipe Client)
    |
    v
Named Pipe IPC
    |
    v
ArcGIS Pro Add-In (C#) (Named Pipe Server)
    |
    v
ArcGIS Pro SDK (in-process)
    |
    v
ArcGIS Pro (active map, layers, selections)
```

---

## Prerequisites

- Visual Studio 2022 **17.14 or later** (for MCP Agent Mode support)
- ArcGIS Pro SDK for .NET
- ArcGIS Pro installed
- .NET 8 SDK

---

## Implementation Reference

This approach is demonstrated by [nicogis/MCP-Server-ArcGIS-Pro-AddIn](https://github.com/nicogis/MCP-Server-ArcGIS-Pro-AddIn).

Key features from that implementation:
- Named Pipe IPC for in-process communication
- `MapView.Active` access for real-time map state
- Tools: `pro.getActiveMapName`, `pro.listLayers`, `pro.countFeatures`, `pro.zoomToLayer`

---

## Planned Tools (Option 2)

| Tool | Description |
|------|-------------|
| `pro.getActiveMapName` | Get name of active map |
| `pro.listLayers` | List all layers in active map |
| `pro.countFeatures` | Count features in a layer |
| `pro.zoomToLayer` | Zoom to specified layer |
| `pro.selectByAttribute` | Select features by SQL query |
| `pro.getCurrentExtent` | Get current map extent |
| `pro.exportLayer` | Export layer to file |

---

## When to Consider Option 2

Choose Option 2 (C# Add-In) when you need:
- Real-time access to currently open ArcGIS Pro project
- Live layer selections and map state
- Zoom/pan operations from AI
- Integration with Pro's active editing session

Stick with current Python MCP when:
- You need to work without ArcGIS Pro running
- You prefer Python development
- You want simpler setup

---

## Implementation Steps

1. Create ArcGIS Pro Add-In project using ArcGIS Pro SDK template
2. Implement Named Pipe server in Add-In's `Module.cs`
3. Create .NET 8 MCP server console app
4. Implement Named Pipe client in MCP server
5. Define MCP tools that map to IPC operations
6. Test with Visual Studio Copilot Agent Mode
7. Document setup

---

## Time Estimate

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Set up VS2022 + ArcGIS Pro SDK | 1-2 hours |
| 2 | Create Add-In with Named Pipe server | 2-3 hours |
| 3 | Create .NET MCP server | 2 hours |
| 4 | Wire tools and test | 2-3 hours |
| 5 | Documentation | 1 hour |

**Total: 8-11 hours**

---

## Open Questions

1. Should Option 2 replace Option 1 or coexist?
2. Shared tool namespacing (`pro.*` vs `arcgis.*`)?
3. Configuration via environment or config file?
4. Support for multiple concurrent ArcGIS Pro sessions?