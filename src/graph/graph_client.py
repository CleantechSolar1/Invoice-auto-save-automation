"""Base Microsoft Graph API client with automatic retry, throttling, and pagination."""

import logging
import random
import time
from typing import Any, Dict, Generator, List, Optional
import requests
from requests.exceptions import RequestException

from src.auth.graph_auth import GraphAuthProvider

logger = logging.getLogger("invoice_automation.graph")

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class GraphAPIError(Exception):
    """Exception for Microsoft Graph API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GraphResourceNotFoundError(GraphAPIError):
    """Raised when a requested resource is not found (HTTP 404)."""
    pass


class GraphClient:
    """Core HTTP client for interacting with Microsoft Graph API."""

    def __init__(
        self,
        auth_provider: GraphAuthProvider,
        base_url: str = "https://graph.microsoft.com/v1.0",
        timeout: int = 30,
        max_retries: int = 4,
    ):
        self.auth_provider = auth_provider
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()

    def _get_headers(self, additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Construct request headers including fresh Bearer authorization."""
        token = self.auth_provider.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if additional_headers:
            headers.update(additional_headers)
        return headers

    def request(
        self,
        method: str,
        endpoint_or_url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> requests.Response:
        """Execute HTTP request against Microsoft Graph with exponential backoff on transient errors."""
        if endpoint_or_url.startswith("http://") or endpoint_or_url.startswith("https://"):
            url = endpoint_or_url
        else:
            clean_endpoint = endpoint_or_url.lstrip("/")
            url = f"{self.base_url}/{clean_endpoint}"

        retries = 0
        backoff_delay = 1.0

        while True:
            request_headers = self._get_headers(headers)
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    data=data,
                    headers=request_headers,
                    timeout=self.timeout,
                    stream=stream,
                )

                if response.status_code < 400:
                    return response

                # Handle 404 cleanly
                if response.status_code == 404:
                    raise GraphResourceNotFoundError(
                        f"Resource not found at {url} (HTTP 404)",
                        status_code=404,
                        response_body=response.text,
                    )

                # Check if transient error eligible for retry
                if response.status_code in TRANSIENT_STATUS_CODES and retries < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        wait_seconds = float(retry_after)
                    else:
                        wait_seconds = backoff_delay + random.uniform(0.1, 0.5)

                    logger.warning(
                        "Graph API returned %s for %s %s. Retrying in %.2f seconds (attempt %d/%d)...",
                        response.status_code,
                        method,
                        url,
                        wait_seconds,
                        retries + 1,
                        self.max_retries,
                    )
                    time.sleep(wait_seconds)
                    backoff_delay *= 2
                    retries += 1
                    continue

                # Non-transient or max retries exceeded
                logger.error(
                    "Graph API request failed: %s %s -> HTTP %s: %s",
                    method,
                    url,
                    response.status_code,
                    response.text,
                )
                raise GraphAPIError(
                    f"Graph API {method} {url} returned HTTP {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text,
                )

            except (requests.ConnectionError, requests.Timeout) as exc:
                if retries < self.max_retries:
                    wait_seconds = backoff_delay + random.uniform(0.1, 0.5)
                    logger.warning(
                        "Network error during Graph API call (%s). Retrying in %.2f seconds (attempt %d/%d)...",
                        str(exc),
                        wait_seconds,
                        retries + 1,
                        self.max_retries,
                    )
                    time.sleep(wait_seconds)
                    backoff_delay *= 2
                    retries += 1
                    continue
                raise GraphAPIError(f"Network error after {self.max_retries} retries: {str(exc)}")

    def get(self, endpoint_or_url: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        return self.request("GET", endpoint_or_url, params=params, **kwargs)

    def post(self, endpoint_or_url: str, json_data: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
        return self.request("POST", endpoint_or_url, json_data=json_data, **kwargs)

    def put(self, endpoint_or_url: str, data: Optional[bytes] = None, **kwargs) -> requests.Response:
        return self.request("PUT", endpoint_or_url, data=data, **kwargs)

    def paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Iterate through Microsoft Graph paginated responses using @odata.nextLink."""
        next_url: Optional[str] = endpoint
        query_params = params

        while next_url:
            resp = self.get(next_url, params=query_params)
            data = resp.json()

            items = data.get("value", [])
            for item in items:
                yield item

            next_url = data.get("@odata.nextLink")
            # Query params are embedded in @odata.nextLink, so clear them for subsequent calls
            query_params = None
