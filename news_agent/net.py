import logging
import time
import httpx

LOG = logging.getLogger(__name__)


def get(client: httpx.Client, url: str, attempts=3, **kwargs) -> httpx.Response:
    """Retry safe reads; preserve TLS validation. Never log response bodies/secrets."""
    for attempt in range(attempts):
        try:
            response = client.get(url, **kwargs)
            if not response.is_redirect:
                response.raise_for_status()
            if len(response.content) > 5_000_000:
                raise ValueError('Response exceeds 5 MB')
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (429, 500, 502, 503, 504):
                raise
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError('unreachable')
