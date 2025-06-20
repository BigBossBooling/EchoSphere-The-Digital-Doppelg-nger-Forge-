# echosystem/ptfi/db_clients.py
import logging
import asyncpg
from typing import Optional, Any # Added Any for Neo4j driver placeholder
from neo4j import AsyncGraphDatabase, AsyncDriver # Import Neo4j async driver components

from .config import settings

logger = logging.getLogger(__name__)

# Global variable to hold the PostgreSQL connection pool for PTFI
pg_pool_ptfi: Optional[asyncpg.pool.Pool] = None
# Global variable for Neo4j driver
neo4j_driver_ptfi: Optional[AsyncDriver] = None # Use AsyncDriver for type hint

async def init_postgres_pool():
    """Initializes the PostgreSQL connection pool for PTFI's own data needs."""
    global pg_pool_ptfi
    if pg_pool_ptfi:
        logger.info("PTFI PostgreSQL pool already initialized.")
        return

    if not settings.POSTGRES_DSN_PTFI:
        logger.warning("POSTGRES_DSN_PTFI is not configured. PTFI PostgreSQL pool will not be initialized.")
        pg_pool_ptfi = None
        return

    try:
        dsn_parts = settings.POSTGRES_DSN_PTFI.split('@')
        loggable_dsn = dsn_parts[-1] if len(dsn_parts) > 1 else settings.POSTGRES_DSN_PTFI
        logger.info(f"Initializing PostgreSQL connection pool for PTFI to: {loggable_dsn}")

        pg_pool_ptfi = await asyncpg.create_pool(
            dsn=settings.POSTGRES_DSN_PTFI,
            min_size=getattr(settings, 'POSTGRES_POOL_MIN_SIZE_PTFI', 2), # Use getattr for optional settings
            max_size=getattr(settings, 'POSTGRES_POOL_MAX_SIZE_PTFI', 10),
            timeout=30,
            command_timeout=10
        )
        async with pg_pool_ptfi.acquire() as connection:
            await connection.execute("SELECT 1")
        logger.info("PostgreSQL connection pool for PTFI initialized successfully and tested.")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL pool for PTFI: {e}", exc_info=True)
        pg_pool_ptfi = None
        # raise # Consider re-raising to halt startup if DB is critical

async def close_postgres_pool():
    """Closes the PostgreSQL connection pool."""
    global pg_pool_ptfi
    if pg_pool_ptfi:
        try:
            logger.info("Closing PostgreSQL connection pool for PTFI.")
            await pg_pool_ptfi.close()
            logger.info("PostgreSQL connection pool for PTFI closed.")
        except Exception as e:
            logger.error(f"Failed to close PostgreSQL pool for PTFI: {e}", exc_info=True)
        finally:
            pg_pool_ptfi = None

async def get_postgres_pool() -> asyncpg.pool.Pool:
    """Returns the initialized PostgreSQL pool. Raises RuntimeError if not initialized."""
    if pg_pool_ptfi is None:
        logger.error("PTFI PostgreSQL pool has not been initialized.")
        raise RuntimeError("PTFI PostgreSQL database pool is not available.")
    return pg_pool_ptfi

async def init_neo4j_driver(): # Renamed for consistency if this becomes the sole init function
    """Initializes the Neo4j asynchronous driver."""
    global neo4j_driver_ptfi # Use the specific global for PTFI if it's distinct
    if neo4j_driver_ptfi:
        logger.info("PTFI Neo4j driver already initialized.")
        return

    if not (settings.NEO4J_URI and settings.NEO4J_USER and settings.NEO4J_PASSWORD):
        logger.warning("Neo4j URI, user, or password not configured. PTFI Neo4j driver will not be initialized.")
        neo4j_driver_ptfi = None
        return

    try:
        # Mask password in log for URI if it's embedded, though separate user/pass is better
        loggable_uri = settings.NEO4J_URI
        if "@" in settings.NEO4J_URI:
            protocol_host = settings.NEO4J_URI.split('@')[0]
            host_details = settings.NEO4J_URI.split('@')[-1]
            loggable_uri = f"{protocol_host.split('//')[0]}//****:****@{host_details}"

        logger.info(f"Initializing Neo4j driver for PTFI. URI: {loggable_uri}")
        neo4j_driver_ptfi = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        await neo4j_driver_ptfi.verify_connectivity()
        logger.info("Neo4j driver for PTFI initialized and connectivity verified.")
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j driver for PTFI or verify connectivity: {e}", exc_info=True)
        if neo4j_driver_ptfi: # Attempt to close if partially initialized
            await neo4j_driver_ptfi.close()
        neo4j_driver_ptfi = None
        # raise # Consider re-raising if Neo4j is critical for startup

async def close_neo4j_driver(): # Renamed for consistency
    """Closes the Neo4j driver."""
    global neo4j_driver_ptfi
    if neo4j_driver_ptfi:
        try:
            logger.info("Closing Neo4j driver for PTFI.")
            await neo4j_driver_ptfi.close()
            logger.info("Neo4j driver for PTFI closed.")
        except Exception as e:
            logger.error(f"Failed to close Neo4j driver for PTFI: {e}", exc_info=True)
        finally:
            neo4j_driver_ptfi = None

async def get_neo4j_driver() -> AsyncDriver: # Renamed for consistency and type hint
    """Returns the initialized Neo4j driver. Raises RuntimeError if not initialized."""
    if neo4j_driver_ptfi is None:
        logger.error("PTFI Neo4j driver has not been initialized.")
        raise RuntimeError("PTFI Neo4j database driver is not available.")
    return neo4j_driver_ptfi

# Optional: Context manager for sessions if desired, or use directly:
# async def get_neo4j_session() -> AsyncIterator[AsyncSession]:
# driver = await get_neo4j_driver()
# async with driver.session() as session:
# yield session
```
