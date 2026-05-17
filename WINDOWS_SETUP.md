# Windows Setup Guide

## Prerequisites

1. **ArcGIS Pro installed** on Windows
2. **OpenCode installed** on Windows (or use WSL2 with Windows ArcGIS)
3. **Git** for cloning the repository

## Quick Setup

### 1. Clone or Copy the Repository

```cmd
# If using Git:
git clone https://github.com/mrcanofcatfood/ArcGIS-Pro-Bridge-MCP-Server.git
cd ArcGIS-Pro-Bridge-MCP-Server
git checkout opencode-integration

# Or simply copy the arcgis-opencode-mcp folder to your Windows machine
```

### 2. Install Dependencies

Open **Python Command Prompt** from Start Menu (Start > ArcGIS > Python Command Prompt):

```cmd
cd C:\path\to\arcgis-opencode-mcp
uv sync
```

Or using pip:

```cmd
cd C:\path\to\arcgis-opencode-mcp
pip install -e .
```

### 3. Update opencode.json

Edit `opencode.json` with your correct paths:

```json
{
  "mcp": {
    "arcgis-pro": {
      "command": [
        "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe",
        "C:\\path\\to\\arcgis-opencode-mcp\\arcgis_mcp_server.py"
      ]
    }
  }
}
```

### 4. Copy to OpenCode Config

Copy `opencode.json` to your OpenCode config directory:

```cmd
copy opencode.json "%APPDATA%\opencode\opencode.json"
```

Or edit the global config at:
```
C:\Users\<YourName>\AppData\Roaming\opencode\opencode.json
```

### 5. Verify Setup

Start OpenCode and check MCP status:

```cmd
opencode
/mcp
```

You should see `arcgis-pro` listed as Connected.

### 6. Test

Try asking OpenCode:
> Run a health check and tell me if ArcGIS Pro is accessible.

## Troubleshooting

### "Python not found" or arcpy import errors

Make sure you're using ArcGIS Pro's Python environment:
```cmd
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" -c "import arcpy; print(arcpy.GetInstallInfo()['ProductName'])"
```

### MCP server shows error

Check that the paths in `opencode.json` are correct (use double backslashes `\\` in paths).

### Permission denied

Run Command Prompt as Administrator, or check file permissions.

## Testing Script

Run `tests/setup_test.bat` to verify your setup step by step.