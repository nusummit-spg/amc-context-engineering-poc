"""
PostgreSQL Migration Runner.

PURPOSE:
- Execute SQL migrations in order
- Track migration state in database
- Provide rollback capabilities
- Idempotent execution (safe to run multiple times)

USAGE:
    python migration_runner.py up
    python migration_runner.py down
    python migration_runner.py status
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

MIGRATIONS_DIR = Path(__file__).parent


class MigrationRunner:
    """Execute PostgreSQL migrations."""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=1,
            max_size=5
        )
        logger.info("PostgreSQL connection pool initialized")
    
    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")
    
    async def create_migrations_table(self):
        """Create table to track applied migrations."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id SERIAL PRIMARY KEY,
                    version VARCHAR(255) UNIQUE NOT NULL,
                    description VARCHAR(500),
                    installed_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    execution_time_ms FLOAT
                )
            """)
        logger.info("Migrations tracking table created")
    
    async def get_applied_migrations(self) -> List[str]:
        """Get list of already-applied migrations."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT version FROM schema_migrations
                ORDER BY version
            """)
        return [row['version'] for row in rows]
    
    def get_migration_files(self) -> List[tuple]:
        """
        Get all migration files in order.
        
        Returns: List of (filename, version, description)
        """
        migration_files = []
        
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            filename = sql_file.name
            # Parse filename: NNN_description.sql
            parts = filename.replace(".sql", "").split("_", 1)
            
            if len(parts) != 2:
                logger.warning(f"Invalid migration filename: {filename}")
                continue
            
            version = parts[0]
            description = parts[1].replace("_", " ")
            
            migration_files.append((filename, version, description))
        
        return migration_files
    
    async def apply_migration(self, filename: str, version: str, description: str) -> bool:
        """
        Apply a single migration.
        
        Returns: True if successful
        """
        migration_file = MIGRATIONS_DIR / filename
        
        if not migration_file.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False
        
        try:
            # Read migration SQL
            sql_content = migration_file.read_text()
            
            logger.info(f"Applying migration {version}: {description}")
            
            # Execute migration
            start_time = datetime.utcnow()
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Split by -- separator if multiple statements
                    statements = [s.strip() for s in sql_content.split(';') if s.strip()]
                    
                    for statement in statements:
                        if statement and not statement.startswith('--'):
                            await conn.execute(statement)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Record migration in tracking table
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO schema_migrations (version, description, execution_time_ms)
                    VALUES ($1, $2, $3)
                """, version, description, execution_time)
            
            logger.info(f"✓ Migration {version} applied in {execution_time:.2f}ms")
            return True
        
        except Exception as e:
            logger.error(f"✗ Migration {version} failed: {e}", exc_info=True)
            return False
    
    async def up(self, verbose: bool = False):
        """Apply all pending migrations."""
        await self.create_migrations_table()
        
        applied = await self.get_applied_migrations()
        all_migrations = self.get_migration_files()
        
        pending = [m for m in all_migrations if m[1] not in applied]
        
        if not pending:
            logger.info("No pending migrations")
            return
        
        logger.info(f"Found {len(pending)} pending migrations")
        
        successful = 0
        failed = 0
        
        for filename, version, description in pending:
            if await self.apply_migration(filename, version, description):
                successful += 1
            else:
                failed += 1
                logger.error(f"Aborting migration sequence due to failure")
                break
        
        logger.info(f"Migration summary: {successful} successful, {failed} failed")
    
    async def status(self):
        """Show migration status."""
        try:
            await self.create_migrations_table()
            
            applied = await self.get_applied_migrations()
            all_migrations = self.get_migration_files()
            
            logger.info(f"\n{'VERSION':<10} {'STATUS':<15} {'DESCRIPTION'}")
            logger.info("-" * 60)
            
            for filename, version, description in all_migrations:
                status = "✓ Applied" if version in applied else "⏳ Pending"
                logger.info(f"{version:<10} {status:<15} {description}")
            
            logger.info(f"\nTotal: {len(all_migrations)} | Applied: {len(applied)} | Pending: {len(all_migrations) - len(applied)}")
        
        except Exception as e:
            logger.error(f"Error checking migration status: {e}")
    
    async def down(self, steps: int = 1):
        """
        Rollback migrations (limited support).
        
        NOTE: Full rollback requires down() SQL in each migration.
        Currently, this is a placeholder for future implementation.
        """
        logger.warning("Rollback functionality not yet implemented")
        logger.info("To rollback manually, restore from backup and re-run migrations")


async def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python migration_runner.py <command>")
        print("Commands: up, down, status")
        sys.exit(1)
    
    command = sys.argv[1]
    
    # Get connection string from environment or use default
    connection_string = (
        "postgresql://postgres:postgres@localhost:5432/amc_feedback"
    )
    
    runner = MigrationRunner(connection_string)
    await runner.initialize()
    
    try:
        if command == "up":
            await runner.up()
        elif command == "status":
            await runner.status()
        elif command == "down":
            steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            await runner.down(steps)
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
