# EchoSphere Models

This directory is intended to store various types of models used within the EchoSphere project:

1.  **Data Models:** Definitions or schemas for data structures that are persisted in databases or exchanged between services (e.g., Pydantic models, SQLAlchemy models).
2.  **AI Models:**
    *   Configuration files for pre-trained AI models.
    *   Scripts for training or fine-tuning custom AI models.
    *   Serialized custom-trained model files (though large model files might be stored externally, e.g., in a dedicated model registry or cloud storage, with pointers here).
3.  **Machine Learning Models:** Broader ML models that might not strictly be "AI" (e.g., statistical models).

The goal is to centralize model definitions and related resources for clarity and easier management.
Specific subdirectories might be created for `ai_models`, `data_schemas`, etc., as the project grows.
