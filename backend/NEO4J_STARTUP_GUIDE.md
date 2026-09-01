# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Neo4j Startup Guide

To run the local ContextGraph, you must start the portable Neo4j instance. Because it requires Java 21, you must point the `JAVA_HOME` environment variable to the portable JDK directory before running the startup script.

### Startup Command (PowerShell)

Open a PowerShell terminal, navigate to the `neo4j-community-5.24.0` directory, and run:

```powershell
# 1. Navigate to the Neo4j installation directory
cd C:\Users\AmiyaRanjanSarangi\Downloads\AMC_Context_Engineering_Graph\amc_code\neo4j_local\neo4j-community-5.24.0

# 2. Set JAVA_HOME and start the console
$env:JAVA_HOME="C:\Users\AmiyaRanjanSarangi\Downloads\AMC_Context_Engineering_Graph\amc_code\neo4j_local\jdk_dir\jdk-21.0.11+10"; bin\neo4j.bat console
```

### Important Notes:
- Keep this PowerShell window open to keep the database running.
- To shut down the database gracefully, press `Ctrl + C` in the terminal.
- The credentials for this database (if not default) are stored in the `.env` file located at `C:\Users\AmiyaRanjanSarangi\Downloads\AMC_Context_Engineering_Graph\amc_code\amc-context-engineering-poc\streamlit_app\.env`.
