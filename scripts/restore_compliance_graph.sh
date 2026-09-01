#!/bin/bash
# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# ===========================================================================
# AMC Compliance System - Neo4j Graph Restore Script
# ===========================================================================

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore_compliance_graph.sh /path/to/backup.dump"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "Restoring Neo4j database from $BACKUP_FILE..."
if command -v neo4j-admin &> /dev/null; then
    neo4j stop 2>/dev/null || true
    neo4j-admin load --database=neo4j --from="$BACKUP_FILE" --force
    neo4j start
    echo "✅ Restore completed successfully."
else
    echo "neo4j-admin CLI not found; please verify Neo4j service installation."
fi
