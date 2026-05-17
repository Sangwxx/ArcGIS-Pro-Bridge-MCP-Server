# Security Notes

## Security Boundary
The `execute_arcpy_code` tool provided by this project is essentially a local Python / ArcPy code execution capability.

This means:
- AI Agents can execute Python code under the current user's permissions.
- If scripts access local files, databases, networks, or ArcGIS data sources, the risk is the same as running scripts directly on the machine.

## Usage Recommendations
- Only run on a local machine you trust.
- Do not expose directly to the public internet.
- Do not execute write operations against production databases or official data without review.
- Always backup important geospatial data before letting AI execute geoprocessing.

## Vulnerability Reporting
If you discover a security issue, please do not disclose exploitation details in a public issue.
Contact the maintainers privately first, and coordinate public disclosure after a fix is confirmed.
