"""FreeLLMAPI configuration; credentials stay in the server process."""

import os
from ipaddress import ip_address
from urllib.parse import urlsplit


def is_loopback_url(base_url: str) -> bool:
    """Only literal loopback IPs and the exact localhost name are local."""
    try:
        host = urlsplit(base_url).hostname
        if host == "localhost":
            return True
        return bool(host and ip_address(host).is_loopback)
    except ValueError:
        return False


def resolve_settings(app_config: dict) -> tuple[str, str, str]:
    key = (
        os.getenv("FREELLM_API_KEY") or app_config.get("freellm_api_key", "")
    ).strip()
    base_url = (
        os.getenv("FREELLM_BASE_URL") or app_config.get("freellm_base_url", "")
    ).strip()
    model = (
        os.getenv("FREELLM_MODEL") or app_config.get("freellm_model_name", "")
    ).strip()
    if base_url:
        message = (
            "FreeLLMAPI base URL must use HTTPS, or HTTP on localhost/loopback, "
            "without embedded credentials, query, or fragment"
        )
        try:
            parsed = urlsplit(base_url)
            port = parsed.port
        except ValueError:
            raise ValueError(message) from None
        if (
            parsed.scheme not in {"http", "https"}
            or (parsed.scheme == "http" and not is_loopback_url(base_url))
            or not parsed.hostname
            or (port is not None and port == 0)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(message)
    return key, base_url, model


def configuration_status(app_config: dict) -> dict[str, bool]:
    """Return presence only, never a key or a secret-bearing URL."""
    key, base_url, model = resolve_settings(app_config)
    return {"key": bool(key), "base_url": bool(base_url), "model": bool(model)}
