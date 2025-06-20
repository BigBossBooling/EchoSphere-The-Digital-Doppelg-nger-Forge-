import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timezone
from typing import List

# Adjust import path
try:
    from maipp import feature_store_service
    from maipp.models import RawAnalysisFeatureSet # Assuming this is where Pydantic model is
    from maipp.config import Settings # For settings, if service uses it directly (it doesn't for DB object)
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp import feature_store_service
    from maipp.models import RawAnalysisFeatureSet
    from maipp.config import Settings


# Mocking pymongo.errors as they might not be available if pymongo/motor is not fully present in test runner
# or if we want to precisely control error types raised by mocks.
class MockOperationFailure(Exception): # Base class for DB errors
    def __init__(self, message, code=None, details=None):
        super().__init__(message)
        self.code = code
        self.details = details if details is not None else {"message": message}

class MockConnectionFailure(MockOperationFailure): # Inherits from MockOperationFailure
    pass

class MockBulkWriteError(MockOperationFailure):
    def __init__(self, message, details=None):
        super().__init__(message, details=details)
        # BulkWriteError often has 'details' like {'nInserted': 0, 'writeErrors': [...]}
        self.details = details if details is not None else {"nInserted": 0, "writeErrors": []}


@pytest.fixture
def mock_motor_db_collection():
    # This fixture provides a mock for an AsyncIOMotorCollection
    collection_mock = AsyncMock()
    collection_mock.insert_one = AsyncMock()
    collection_mock.insert_many = AsyncMock()
    return collection_mock

@pytest.fixture
def mock_motor_db(mock_motor_db_collection):
    # This fixture provides a mock for an AsyncIOMotorDatabase
    db_mock = AsyncMock()
    # Make db_mock['collection_name'] return our collection_mock
    db_mock.__getitem__.return_value = mock_motor_db_collection
    return db_mock

@pytest.fixture
def sample_feature_set_data() -> RawAnalysisFeatureSet:
    # Make sure userID and sourceUserDataPackageID are valid UUIDs for the model
    return RawAnalysisFeatureSet(
        userID=uuid.uuid4(),
        sourceUserDataPackageID=uuid.uuid4(),
        modality="text",
        modelNameOrType="TestModel_FeatureStore_v1",
        extractedFeatures={"key_feature": "test_value", "score": 0.99},
        status="success",
        timestamp=datetime.now(timezone.utc) # Ensure timezone aware for Pydantic model if needed
    )

@pytest.fixture
def sample_feature_set_data_list(sample_feature_set_data) -> List[RawAnalysisFeatureSet]:
    # Create another distinct feature set for batch tests
    another_fs = RawAnalysisFeatureSet(
        userID=uuid.uuid4(),
        sourceUserDataPackageID=uuid.uuid4(),
        modality="audio",
        modelNameOrType="TestAudioModel_v1",
        extractedFeatures={"emotion": "neutral", "confidence": 0.7},
        status="success"
    )
    return [sample_feature_set_data, another_fs]


@pytest.mark.asyncio
async def test_get_raw_features_collection(mock_motor_db, mock_motor_db_collection):
    # Test the helper function if it's used elsewhere or becomes more complex
    collection = await feature_store_service.get_raw_features_collection(mock_motor_db)
    mock_motor_db.__getitem__.assert_called_once_with(feature_store_service.RAW_FEATURES_COLLECTION_NAME)
    assert collection == mock_motor_db_collection


@pytest.mark.asyncio
async def test_save_raw_analysis_feature_set_success(mock_motor_db, mock_motor_db_collection, sample_feature_set_data):
    # Configure mock for insert_one result
    mock_insert_result = MagicMock()
    # Pydantic model uses alias `_id` for `featureSetID`. model_dump(by_alias=True) will produce `_id`.
    # Motor/PyMongo will store this string UUID as `_id` if provided.
    expected_mongo_id = str(sample_feature_set_data.featureSetID)
    mock_insert_result.inserted_id = expected_mongo_id
    mock_motor_db_collection.insert_one.return_value = mock_insert_result

    inserted_id = await feature_store_service.save_raw_analysis_feature_set(mock_motor_db, sample_feature_set_data)

    assert inserted_id == expected_mongo_id
    mock_motor_db_collection.insert_one.assert_called_once()
    # Check the document that was passed to insert_one
    called_with_doc = mock_motor_db_collection.insert_one.call_args[0][0]
    assert called_with_doc["_id"] == expected_mongo_id # Pydantic model_dump(by_alias=True) uses _id
    assert called_with_doc["userID"] == str(sample_feature_set_data.userID)
    assert called_with_doc["modelNameOrType"] == "TestModel_FeatureStore_v1"

@pytest.mark.asyncio
async def test_save_raw_analysis_feature_set_db_not_passed(sample_feature_set_data):
    # Test the guard clause if db is None
    result = await feature_store_service.save_raw_analysis_feature_set(None, sample_feature_set_data)
    assert result is None

@pytest.mark.asyncio
async def test_save_raw_analysis_feature_set_operation_failure(mock_motor_db, mock_motor_db_collection, sample_feature_set_data):
    # Patch pymongo.errors within the scope of feature_store_service if they are imported there.
    # For now, using our custom MockOperationFailure.
    with patch.object(feature_store_service, "OperationFailure", MockOperationFailure):
        mock_motor_db_collection.insert_one.side_effect = MockOperationFailure("Simulated DB write error", code=121)
        result = await feature_store_service.save_raw_analysis_feature_set(mock_motor_db, sample_feature_set_data)
        assert result is None

# --- Tests for save_batch_raw_analysis_features ---
@pytest.mark.asyncio
async def test_save_batch_raw_analysis_features_success(mock_motor_db, mock_motor_db_collection, sample_feature_set_data_list):
    mock_batch_result = MagicMock()
    # model_dump(mode='json', by_alias=True) used in service, so _id will be stringified featureSetID
    expected_ids_str = [str(fs.featureSetID) for fs in sample_feature_set_data_list]
    mock_batch_result.inserted_ids = expected_ids_str # insert_many returns list of _ids
    mock_motor_db_collection.insert_many.return_value = mock_batch_result

    inserted_ids_result = await feature_store_service.save_batch_raw_analysis_features(mock_motor_db, sample_feature_set_data_list)

    assert inserted_ids_result == expected_ids_str
    mock_motor_db_collection.insert_many.assert_called_once()
    called_with_docs_list = mock_motor_db_collection.insert_many.call_args[0][0]
    assert len(called_with_docs_list) == len(sample_feature_set_data_list)
    assert called_with_docs_list[0]["_id"] == str(sample_feature_set_data_list[0].featureSetID)
    assert called_with_docs_list[1]["_id"] == str(sample_feature_set_data_list[1].featureSetID)

@pytest.mark.asyncio
async def test_save_batch_raw_analysis_features_empty_list(mock_motor_db, mock_motor_db_collection):
    result = await feature_store_service.save_batch_raw_analysis_features(mock_motor_db, [])
    assert result == []
    mock_motor_db_collection.insert_many.assert_not_called()

@pytest.mark.asyncio
async def test_save_batch_raw_analysis_features_db_not_passed(sample_feature_set_data_list):
    result = await feature_store_service.save_batch_raw_analysis_features(None, sample_feature_set_data_list)
    assert result is None

@pytest.mark.asyncio
async def test_save_batch_raw_analysis_features_bulk_write_error(mock_motor_db, mock_motor_db_collection, sample_feature_set_data_list):
    # Patch pymongo.errors within the scope of feature_store_service if they are imported there.
    with patch.object(feature_store_service, "BulkWriteError", MockBulkWriteError):
        mock_motor_db_collection.insert_many.side_effect = MockBulkWriteError(
            "Simulated bulk write error",
            details={"nInserted": 0, "writeErrors": [{"index": 0, "code": 11000, "errmsg": "dup key"}]}
        )
        result = await feature_store_service.save_batch_raw_analysis_features(mock_motor_db, sample_feature_set_data_list)
        assert result is None # Current service logic returns None on BulkWriteError
```
