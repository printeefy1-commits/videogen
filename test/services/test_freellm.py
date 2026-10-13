import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx
import pytest
from openai import OpenAI

from app.services import freellm, llm


def test_freellm_uses_real_sdk_with_configured_gateway_and_environment(monkeypatch):
    monkeypatch.setenv("FREELLM_API_KEY", "test-env-key")
    monkeypatch.setenv("FREELLM_BASE_URL", "https://gateway.example.test/v1")
    monkeypatch.setenv("FREELLM_MODEL", "free-test-model")
    requests = []

    def respond(request):
        requests.append(request)
        assert str(request.url) == "https://gateway.example.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-env-key"
        assert json.loads(request.content)["model"] == "free-test-model"
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "free-test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "A real SDK response.",
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    with patch.object(
        llm, "OpenAI", side_effect=lambda **kwargs: OpenAI(http_client=client, **kwargs)
    ):
        result = llm._generate_response(
            "Write a script",
            app_config={
                "llm_provider": "freellm",
                "freellm_api_key": "saved-key",
                "freellm_base_url": "https://saved.example.test/v1",
                "freellm_model_name": "saved-model",
            },
        )
    assert result == "A real SDK response."
    assert len(requests) == 1
    assert client.is_closed


def test_missing_configuration_does_not_call_a_paid_fallback(monkeypatch):
    for name in ("FREELLM_API_KEY", "FREELLM_BASE_URL", "FREELLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with patch.object(llm, "OpenAI") as client:
        result = llm._generate_response("test", app_config={"llm_provider": "freellm"})
    assert result.startswith("Error:")
    client.assert_not_called()


def test_provider_error_redacts_the_key(monkeypatch):
    for name in ("FREELLM_API_KEY", "FREELLM_BASE_URL", "FREELLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    test_key = "synthetic-key-for-redaction-test"
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                json={
                    "error": {
                        "message": f"Invalid key: {test_key}",
                        "type": "authentication_error",
                    }
                },
            )
        )
    )
    with patch.object(
        llm, "OpenAI", side_effect=lambda **kwargs: OpenAI(http_client=client, **kwargs)
    ):
        result = llm._generate_response(
            "test",
            app_config={
                "llm_provider": "freellm",
                "freellm_api_key": test_key,
                "freellm_base_url": "https://gateway.example.test/v1",
                "freellm_model_name": "free-model",
            },
        )
    assert result.startswith("Error:")
    assert test_key not in result
    assert "[redacted]" in result


@pytest.mark.parametrize(
    "url",
    [
        "http://gateway.example.test/v1",
        "http://localhost.example.test/v1",
        "http://192.168.1.20:8080/v1",
        "http://0.0.0.0:8080/v1",
        "http://127.0.0.1:invalid/v1",
        "http://127.0.0.1:0/v1",
        "https://user:password@gateway.example.test/v1",
        "https://gateway.example.test/v1?key=secret",
        "https://gateway.example.test/v1#fragment",
    ],
)
def test_secret_bearing_or_insecure_urls_are_rejected(url, monkeypatch):
    monkeypatch.delenv("FREELLM_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="HTTPS"):
        freellm.resolve_settings({"freellm_base_url": url})


@pytest.mark.parametrize(
    "url",
    ["http://localhost:8080/v1", "http://127.0.0.1:11434/v1", "http://[::1]:1234/v1"],
)
def test_local_http_addresses_are_supported(url, monkeypatch):
    monkeypatch.delenv("FREELLM_BASE_URL", raising=False)
    assert freellm.resolve_settings({"freellm_base_url": url})[1] == url


def test_real_local_http_connection_does_not_use_external_proxy(monkeypatch):
    for name in ("FREELLM_API_KEY", "FREELLM_BASE_URL", "FREELLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    # A broken proxy ensures this test fails if local credentials leave the
    # direct loopback route. No real provider or user key is involved.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            content = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, self.headers.get("Authorization"), content))
            body = json.dumps(
                {
                    "id": "local-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "local-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "OK"},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = llm._generate_response(
            "Reply with exactly: OK",
            app_config={
                "llm_provider": "freellm",
                "freellm_api_key": "synthetic-local-key",
                "freellm_base_url": f"http://127.0.0.1:{server.server_port}/v1",
                "freellm_model_name": "local-model",
            },
        )
        assert result == "OK"
        assert len(received) == 1
        assert received[0][0] == "/v1/chat/completions"
        assert received[0][1] == "Bearer synthetic-local-key"
        assert received[0][2]["model"] == "local-model"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
