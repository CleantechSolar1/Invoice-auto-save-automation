"""Microsoft Graph authentication handler using MSAL."""

import logging
from typing import Optional
import msal

logger = logging.getLogger("invoice_automation.auth")


class AuthenticationError(Exception):
    """Raised when Microsoft Graph authentication fails."""
    pass


class GraphAuthProvider:
    """Manages Microsoft Entra ID (Azure AD) client credentials authentication for Microsoft Graph."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, scope: str = "https://graph.microsoft.com/.default"):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = [scope]
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"
        self._app: Optional[msal.ConfidentialClientApplication] = None

    def _get_app(self) -> msal.ConfidentialClientApplication:
        """Lazily initialize and return MSAL ConfidentialClientApplication."""
        if self._app is None:
            if not self.tenant_id or not self.client_id or not self.client_secret:
                raise AuthenticationError(
                    "Azure AD credentials missing: TENANT_ID, CLIENT_ID, and CLIENT_SECRET must be configured."
                )
            self._app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=self.authority,
            )
        return self._app

    def get_access_token(self) -> str:
        """Retrieve a valid Microsoft Graph access token.

        First attempts to acquire token silently from memory cache.
        If expired or not found, acquires a new token via client credentials flow.
        """
        app = self._get_app()

        # Check internal MSAL cache
        result = app.acquire_token_silent(scopes=self.scope, account=None)

        if not result:
            logger.debug("No valid cached token found. Requesting new token from Azure Entra ID...")
            result = app.acquire_token_for_client(scopes=self.scope)

        if "access_token" in result:
            return result["access_token"]

        error = result.get("error", "unknown_error")
        error_description = result.get("error_description", "No description provided")
        logger.error(
            "Authentication failed with Azure AD. Error: %s, Description: %s",
            error,
            error_description,
        )
        raise AuthenticationError(f"Failed to acquire Microsoft Graph token: {error} - {error_description}")
