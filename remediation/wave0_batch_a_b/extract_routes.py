#!/usr/bin/env python3
"""
G01-T02: Export current OpenAPI schema and all mounted routes
Acceptance: Route inventory includes methods, auth and response contracts
"""
import json
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import create_app


def extract_routes():
    """Extract all routes from FastAPI app"""
    app = create_app()
    
    routes_data = {
        "manifest_version": "1.0",
        "task": "G01-T02",
        "purpose": "Export OpenAPI schema and all mounted routes",
        "routes": [],
        "route_count": 0,
        "openapi_schema": None
    }
    
    # Extract OpenAPI schema
    try:
        routes_data["openapi_schema"] = app.openapi()
    except Exception as e:
        routes_data["openapi_schema_error"] = str(e)
    
    # Extract route details
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            route_info = {
                "path": route.path,
                "methods": list(route.methods) if route.methods else [],
                "name": route.name if hasattr(route, "name") else None,
                "endpoint": str(route.endpoint) if hasattr(route, "endpoint") else None,
            }
            
            # Check for auth dependencies in endpoint
            if hasattr(route, "dependant"):
                dependencies = []
                for dep in getattr(route.dependant, "dependencies", []):
                    dep_str = str(dep.call) if hasattr(dep, "call") else str(dep)
                    dependencies.append(dep_str)
                    if "CurrentUser" in dep_str or "get_current_user" in dep_str:
                        route_info["requires_auth"] = True
                route_info["dependencies"] = dependencies
            
            routes_data["routes"].append(route_info)
    
    routes_data["route_count"] = len(routes_data["routes"])
    
    # Save to file
    output_path = Path(__file__).parent / "routes_inventory.json"
    with open(output_path, "w") as f:
        json.dump(routes_data, f, indent=2)
    
    print(f"✓ Route inventory saved to {output_path}")
    print(f"✓ Total routes: {routes_data['route_count']}")
    
    # Create summary
    summary_path = Path(__file__).parent / "routes_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("G01-T02: Route Inventory Summary\n")
        f.write("=" * 80 + "\n\n")
        
        # Group by prefix
        by_prefix = {}
        for route in routes_data["routes"]:
            path = route["path"]
            if path.startswith("/api/"):
                prefix = path.split("/")[2] if len(path.split("/")) > 2 else "root"
            else:
                prefix = "frontend"
            
            if prefix not in by_prefix:
                by_prefix[prefix] = []
            by_prefix[prefix].append(route)
        
        for prefix, routes in sorted(by_prefix.items()):
            f.write(f"\n{prefix.upper()} ({len(routes)} routes)\n")
            f.write("-" * 80 + "\n")
            for route in routes:
                methods = ",".join(route.get("methods", []))
                auth_marker = "🔒" if route.get("requires_auth") else "🔓"
                f.write(f"  {auth_marker} {methods:10} {route['path']}\n")
    
    print(f"✓ Summary saved to {summary_path}")
    print("\nG01-T02 COMPLETE: Route inventory exported")
    return routes_data


if __name__ == "__main__":
    extract_routes()
