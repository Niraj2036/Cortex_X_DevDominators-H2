import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class MongoDBManager:
    client: AsyncIOMotorClient | None = None

db_manager = MongoDBManager()

async def init_db() -> None:
    """Initialize the MongoDB connection pool."""
    settings = get_settings()
    if not settings.mongo_uri:
        logger.warning("MONGO_URI not set. MongoDB Atlas integration disabled.")
        return

    logger.info("Connecting to MongoDB Atlas...")
    try:
        db_manager.client = AsyncIOMotorClient(settings.mongo_uri)
        # Test connection
        await db_manager.client.admin.command('ping')
        
        # Explicitly create the collection to allow immediate Vector Search Index creation
        db = db_manager.client[settings.mongo_db_name]
        try:
            await db.create_collection("cases")
            logger.info("Created 'cases' collection explicitly.")
        except Exception as coll_err:
            if "already exists" in str(coll_err).lower() or "CollectionExists" in str(coll_err) or "NamespaceExists" in str(coll_err):
                logger.info("'cases' collection already exists - ready for Vector Search Index.")
            else:
                logger.warning(f"Note on collection creation: {coll_err}")
                
        try:
            await db.create_collection("sessions")
            logger.info("Created 'sessions' collection explicitly.")
        except Exception as coll_err:
            if "already exists" in str(coll_err).lower() or "CollectionExists" in str(coll_err) or "NamespaceExists" in str(coll_err):
                pass
            else:
                logger.warning(f"Note on sessions collection creation: {coll_err}")
                
        try:
            await db.create_collection("diagnoses")
            logger.info("Created 'diagnoses' collection explicitly.")
        except Exception as coll_err:
            if "already exists" in str(coll_err).lower() or "CollectionExists" in str(coll_err) or "NamespaceExists" in str(coll_err):
                pass
            else:
                logger.warning(f"Note on diagnoses collection creation: {coll_err}")

        logger.info("Successfully connected to MongoDB Atlas.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB Atlas: {e}")
        db_manager.client = None

def close_db() -> None:
    """Close the MongoDB connection pool."""
    if db_manager.client:
        db_manager.client.close()
        logger.info("MongoDB Atlas connection closed.")

def get_db():
    """Dependency to get the database instance."""
    settings = get_settings()
    if db_manager.client:
        return db_manager.client[settings.mongo_db_name]
    return None
