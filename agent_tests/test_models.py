import json
import httpx
import pytest
from agentic.models import OpenAICompatibleModel


def test_hosted_adapter_request_and_output(monkeypatch):
    real_client = httpx.Client
    def handle(request):
        assert str(request.url) == "https://configured.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-credential"
        body = json.loads(request.content)
        assert body["model"] == "test-model" and body["temperature"] == 0
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][-1]["content"] == "Question"
        return httpx.Response(200, json={"choices":[{"message":{"content":'{"tool":"inspect_schema","args":{}}'}}]})
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handle)))
    model = OpenAICompatibleModel("https://configured.example/v1/", "test-model", "test-credential")
    assert json.loads(model([{"role":"user","content":"Question"}]))["tool"] == "inspect_schema"


@pytest.mark.parametrize("status", [401, 503])
def test_hosted_adapter_rejects_failed_http(monkeypatch, status):
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"error":"fixture"}))))
    with pytest.raises(httpx.HTTPStatusError):
        OpenAICompatibleModel("https://configured.example/v1", "model", "test-key")([])
