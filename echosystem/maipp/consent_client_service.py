# echosystem/maipp/consent_client_service.py
import logging
import httpx # Using httpx for async requests
from typing import Dict, Any, Optional

from .config import settings

logger = logging.getLogger(__name__)

# Conceptual structure for the response from the Consent Verification API
# Based on UDIM's phase1_udim_api_specifications.md for /internal/consent/v1/verify
class ConsentVerificationResponse:
    def __init__(self,
                 is_valid: bool,
                 reason: Optional[str] = None,
                 granted_scope: Optional[Dict[str, Any]] = None, # Keep as Dict for flexibility
                 error_message: Optional[str] = None
                ):
        self.is_valid = is_valid
        self.reason = reason # Reason for invalidity if applicable
        self.granted_scope_details = granted_scope # Details of the scope that was confirmed
        self.error_message = error_message # For logging technical errors

    def __repr__(self):
        return (f"ConsentVerificationResponse(is_valid={self.is_valid}, reason='{self.reason}', "
                f"granted_scope_details={self.granted_scope_details}, error_message='{self.error_message}')")


async def verify_consent_for_action(
    user_id: str,
    consent_token_id: Optional[str], # Consent token might not always be present if checking general capability
    required_scope: str, # e.g., "action:analyze_text_sentiment,resource_package_id:xyz"
    http_client: httpx.AsyncClient, # Pass httpx client for testability & connection pooling
    package_id_for_logging: str = "N/A" # For contextual logging
    # data_hash: Optional[str] = None # If needed by consent service in future
) -> ConsentVerificationResponse:
    """
    Calls the internal Consent Verification API to check if a specific action is permitted.
    """
    log_prefix = f"[{package_id_for_logging}][UserID:{user_id}]"

    if not settings.CONSENT_API_URL:
        logger.error(f"{log_prefix} CONSENT_API_URL is not configured. Cannot verify consent. Defaulting to DENY.")
        return ConsentVerificationResponse(is_valid=False, reason="Consent service not configured by MAIPP")

    if not consent_token_id: # If, for some reason, a consent token isn't available for a check that requires it
        logger.warning(f"{log_prefix} No consentTokenID provided for scope '{required_scope}'. Defaulting to DENY.")
        return ConsentVerificationResponse(is_valid=False, reason="Missing consentTokenID for verification")

    api_url = f"{settings.CONSENT_API_URL.rstrip('/')}/verify" # Ensure no double slashes if CONSENT_API_URL has trailing slash
    params = {
        "userID": user_id,
        "consentTokenID": consent_token_id,
        "requiredScope": required_scope,
        # if data_hash: params["dataHash"] = data_hash
    }

    try:
        logger.debug(f"{log_prefix} Verifying consent: URL='{api_url}', Scope='{required_scope}', TokenID='{consent_token_id}'")
        response = await http_client.get(api_url, params=params, timeout=5.0) # 5 sec timeout

        response.raise_for_status() # Raise an exception for 4xx/5xx errors from consent service

        data = response.json()
        is_valid = data.get("isValid", False)
        reason_for_invalidity = data.get("reason_for_invalidity") # Expected if isValid is false
        granted_scope_details = data.get("scopeGranted")   # Details of the scope that was actually validated

        if is_valid:
            logger.info(f"{log_prefix} Consent GRANTED for scope '{required_scope}'. Details: {granted_scope_details}")
        else:
            logger.warning(f"{log_prefix} Consent DENIED for scope '{required_scope}'. Reason: {reason_for_invalidity}")

        return ConsentVerificationResponse(is_valid=is_valid, reason=reason_for_invalidity, granted_scope=granted_scope_details)

    except httpx.HTTPStatusError as e:
        # Error response from the consent service itself (e.g., 400, 403, 404, 500)
        error_text = e.response.text
        logger.error(f"{log_prefix} Consent API HTTP Error for scope '{required_scope}': {e.response.status_code} - {error_text[:200]}", exc_info=True)
        return ConsentVerificationResponse(is_valid=False, reason=f"Consent API HTTP error: {e.response.status_code}", error_message=error_text)
    except httpx.RequestError as e:
        # Network error, timeout, etc. while trying to reach consent service
        logger.error(f"{log_prefix} Consent API Request Error for scope '{required_scope}': {str(e)}", exc_info=True)
        return ConsentVerificationResponse(is_valid=False, reason=f"Consent API request error (e.g. connection failed, timeout)", error_message=str(e))
    except json.JSONDecodeError as e:
        logger.error(f"{log_prefix} Failed to decode JSON response from Consent API for scope '{required_scope}': {str(e)}", exc_info=True)
        return ConsentVerificationResponse(is_valid=False, reason="Consent API response not valid JSON", error_message=str(e))
    except Exception as e:
        logger.error(f"{log_prefix} Unexpected error verifying consent for scope '{required_scope}': {e}", exc_info=True)
        return ConsentVerificationResponse(is_valid=False, reason="Unexpected error during consent verification", error_message=str(e))
```
