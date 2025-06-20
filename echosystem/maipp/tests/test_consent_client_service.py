import pytest
import httpx
from unittest.mock import MagicMock, patch # For settings

# Adjust import path
try:
    from maipp import consent_client_service
    from maipp.config import Settings
    from maipp.consent_client_service import ConsentVerificationResponse
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from maipp import consent_client_service
    from maipp.config import Settings
    from maipp.consent_client_service import ConsentVerificationResponse


@pytest.fixture
def mock_settings_for_consent(monkeypatch):
    settings_obj = Settings(CONSENT_API_URL="http://test-consent-service.internal/api/v1")
    monkeypatch.setattr(consent_client_service, "settings", settings_obj)
    return settings_obj

@pytest.fixture
def mock_httpx_client():
    # This fixture provides a mock httpx.AsyncClient
    # Tests will then mock specific responses on this client (e.g., client.get.return_value)
    return MagicMock(spec=httpx.AsyncClient)

@pytest.mark.asyncio
async def test_verify_consent_success(mock_settings_for_consent, mock_httpx_client):
    user_id = "user123"
    consent_token_id = "token789"
    required_scope = "action:read,resource:profile"
    package_id_log = "pkg_consent_test"

    # Mock the response from httpx.AsyncClient.get()
    mock_api_response = MagicMock(spec=httpx.Response)
    mock_api_response.status_code = 200
    mock_api_response.json.return_value = {
        "isValid": True,
        "scopeGranted": {"action": "read", "resource": "profile"},
        "reason_for_invalidity": None
    }
    # Configure the client's get method to return this mock response
    mock_httpx_client.get = AsyncMock(return_value=mock_api_response)

    result = await consent_client_service.verify_consent_for_action(
        user_id, consent_token_id, required_scope, mock_httpx_client, package_id_log
    )

    assert result.is_valid is True
    assert result.reason is None
    assert result.granted_scope_details == {"action": "read", "resource": "profile"}
    mock_httpx_client.get.assert_called_once()
    call_args = mock_httpx_client.get.call_args
    assert call_args[0][0] == f"{mock_settings_for_consent.CONSENT_API_URL}/verify"
    assert call_args[1]["params"]["userID"] == user_id


@pytest.mark.asyncio
async def test_verify_consent_denied(mock_settings_for_consent, mock_httpx_client):
    user_id = "user123"
    consent_token_id = "token789"
    required_scope = "action:write,resource:profile"
    package_id_log = "pkg_consent_denied"

    mock_api_response = MagicMock(spec=httpx.Response)
    mock_api_response.status_code = 200 # API call itself is successful
    mock_api_response.json.return_value = {
        "isValid": False,
        "reason_for_invalidity": "Scope not granted by user",
        "scopeGranted": None
    }
    mock_httpx_client.get = AsyncMock(return_value=mock_api_response)

    result = await consent_client_service.verify_consent_for_action(
        user_id, consent_token_id, required_scope, mock_httpx_client, package_id_log
    )

    assert result.is_valid is False
    assert result.reason == "Scope not granted by user"

@pytest.mark.asyncio
async def test_verify_consent_api_http_error(mock_settings_for_consent, mock_httpx_client):
    user_id = "user123"
    consent_token_id = "token789"
    required_scope = "action:read,resource:profile"

    # Simulate an HTTPStatusError (e.g., 500 from consent service)
    mock_httpx_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
        message="Internal Server Error",
        request=MagicMock(spec=httpx.Request),
        response=MagicMock(status_code=500, text="Consent service unavailable")
    ))

    result = await consent_client_service.verify_consent_for_action(
        user_id, consent_token_id, required_scope, mock_httpx_client
    )
    assert result.is_valid is False
    assert result.reason == "Consent API HTTP error: 500"
    assert "Consent service unavailable" in result.error_message


@pytest.mark.asyncio
async def test_verify_consent_api_request_error(mock_settings_for_consent, mock_httpx_client):
    # Simulate a network error (e.g., httpx.ConnectTimeout)
    mock_httpx_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("Connection timed out"))

    result = await consent_client_service.verify_consent_for_action(
        "user123", "token789", "scope", mock_httpx_client
    )
    assert result.is_valid is False
    assert "Consent API request error" in result.reason
    assert "Connection timed out" in result.error_message


@pytest.mark.asyncio
async def test_verify_consent_no_api_url_configured(monkeypatch, mock_httpx_client):
    # Temporarily set CONSENT_API_URL to None for this test
    settings_no_url = Settings(CONSENT_API_URL=None)
    monkeypatch.setattr(consent_client_service, "settings", settings_no_url)

    result = await consent_client_service.verify_consent_for_action(
        "user123", "token789", "scope", mock_httpx_client
    )
    assert result.is_valid is False
    assert result.reason == "Consent service not configured"
    mock_httpx_client.get.assert_not_called() # Ensure API was not called

@pytest.mark.asyncio
async def test_verify_consent_no_token_id(mock_settings_for_consent, mock_httpx_client):
    result = await consent_client_service.verify_consent_for_action(
        "user123", None, "scope", mock_httpx_client # Passing None for consent_token_id
    )
    assert result.is_valid is False
    assert result.reason == "Missing consentTokenID for verification"
    mock_httpx_client.get.assert_not_called()
