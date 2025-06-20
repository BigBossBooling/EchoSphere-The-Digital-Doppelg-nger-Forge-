# echosystem/maipp/feature_store_service.py
import logging
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection # For MongoDB
from pymongo.errors import ConnectionFailure, OperationFailure, BulkWriteError
import uuid # To ensure featureSetID is handled as UUID if needed before string conversion

from .config import settings # Assuming settings.MONGO_DB_URL and settings.MONGO_MAIPP_DATABASE_NAME
from .models import RawAnalysisFeatureSet # Import the Pydantic model

logger = logging.getLogger(__name__)

RAW_FEATURES_COLLECTION_NAME = "raw_analysis_features"

# Database and collection can be passed as arguments, or initialized and passed if this becomes a class.
# For functional approach, passing 'db' instance is cleaner.

async def get_raw_features_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    """Helper to get the collection."""
    return db[RAW_FEATURES_COLLECTION_NAME]

async def save_raw_analysis_feature_set( # Renamed to avoid conflict with model name
    db: AsyncIOMotorDatabase,
    feature_set_data: RawAnalysisFeatureSet
) -> Optional[str]: # Returns the string representation of featureSetID (which is _id) or None
    """Saves a RawAnalysisFeatureSet document to MongoDB."""
    if not db:
        logger.error(f"[{feature_set_data.featureSetID}] MongoDB database instance not available. Cannot save features.")
        return None

    collection = await get_raw_features_collection(db)

    try:
        # Pydantic model_dump(mode='json') handles UUID to str and datetime to ISO str conversion
        # as per model's json_encoders.
        # The alias `_id` for `featureSetID` in the Pydantic model should map featureSetID to _id.
        feature_set_dict = feature_set_data.model_dump(mode='json', by_alias=True)

        # Motor expects _id to be set if we're controlling it, otherwise it generates an ObjectId.
        # If featureSetID (which is aliased to _id) is already a UUID string from model_dump,
        # MongoDB will store it as a string for _id if that's desired.
        # If native ObjectId is preferred for _id and featureSetID is just another field,
        # then don't alias featureSetID to _id in Pydantic model.
        # Current Pydantic model aliases featureSetID to _id.

        logger.debug(f"Saving RawAnalysisFeatureSet to MongoDB: {feature_set_dict.get('_id')}")

        result = await collection.insert_one(feature_set_dict)

        # result.inserted_id will be the value of _id field (which is featureSetData.featureSetID as string)
        inserted_id_str = str(result.inserted_id)
        logger.info(f"Successfully saved RawAnalysisFeatureSet with _id: {inserted_id_str} (featureSetID: {feature_set_data.featureSetID})")
        return inserted_id_str # This is the _id value from MongoDB

    except OperationFailure as e:
        logger.error(f"MongoDB OperationFailure while saving RawAnalysisFeatureSet (ID: {feature_set_data.featureSetID}): {e.details}", exc_info=True)
    except ConnectionFailure as e: # Should ideally be handled by Motor's reconnection logic to some extent
        logger.error(f"MongoDB ConnectionFailure while saving RawAnalysisFeatureSet (ID: {feature_set_data.featureSetID}): {e}", exc_info=True)
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error saving RawAnalysisFeatureSet (ID: {feature_set_data.featureSetID}): {e}", exc_info=True)
    return None

async def save_batch_raw_analysis_features(
    db: AsyncIOMotorDatabase,
    feature_sets_data: List[RawAnalysisFeatureSet]
) -> Optional[List[str]]: # Returns list of string _ids or None if batch fails
    """Saves a batch of RawAnalysisFeatureSet documents to MongoDB."""
    if not db:
        logger.error("MongoDB database instance not available. Cannot save batch features.")
        return None
    if not feature_sets_data:
        logger.info("No feature sets provided in batch to save.")
        return []

    collection = await get_raw_features_collection(db)
    try:
        documents_to_insert = [fs.model_dump(mode='json', by_alias=True) for fs in feature_sets_data]
        logger.debug(f"Attempting to save batch of {len(documents_to_insert)} RawAnalysisFeatureSet documents to MongoDB...")

        # ordered=False allows valid inserts in the batch to proceed even if some documents fail validation (e.g. duplicate _id if not careful)
        result = await collection.insert_many(documents_to_insert, ordered=False)

        inserted_ids_str = [str(id_val) for id_val in result.inserted_ids]
        logger.info(f"Successfully saved batch of {len(inserted_ids_str)} RawAnalysisFeatureSet documents.")
        # Note: If ordered=False, some inserts might fail silently if not checking write errors in result.
        # For more robustness, check result.inserted_count vs len(documents_to_insert)
        # and potentially inspect write errors if available in the driver's result object for insert_many.
        return inserted_ids_str

    except BulkWriteError as bwe:
        logger.error(f"MongoDB BulkWriteError during batch save of RawAnalysisFeatures: {bwe.details}", exc_info=True)
        # bwe.details['nInserted'] gives count of successfully inserted documents
        # Can return partially successful list of IDs if needed:
        # successful_ids = [str(doc['_id']) for doc in documents_to_insert if ???] # Hard to map back without more logic
    except OperationFailure as e:
        logger.error(f"MongoDB OperationFailure during batch save: {e.details}", exc_info=True)
    except ConnectionFailure as e:
        logger.error(f"MongoDB ConnectionFailure during batch save: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error during batch save of RawAnalysisFeatures: {e}", exc_info=True)
    return None
```
