import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from citeguard import embeddings


class _Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    fail = False

    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).requests.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
        if type(self).fail:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        vectors = []
        for text in body["input"]:
            if "cat" in text:
                vectors.append({"embedding": [1.0, 0.0, 0.0]})
            elif "dog" in text:
                vectors.append({"embedding": [0.8, 0.2, 0.0]})
            else:
                vectors.append({"embedding": [0.0, 1.0, 0.0]})
        payload = {"data": vectors, "model": body.get("model")}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence test output
        pass


@pytest.fixture()
def fake_server():
    _Handler.requests = []
    _Handler.fail = False
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", _Handler
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_unconfigured_raises_with_human_message(monkeypatch):
    monkeypatch.delenv("CITEGUARD_EMBED_ENDPOINT", raising=False)
    assert embeddings.load_config() is None
    assert embeddings.is_configured() is False
    with pytest.raises(embeddings.EmbeddingError) as err:
        embeddings.embed_texts(["x"])
    assert "未配置向量服务" in str(err.value)


def test_embed_and_auth_header(fake_server, monkeypatch):
    url, handler = fake_server
    monkeypatch.setenv("CITEGUARD_EMBED_ENDPOINT", url)
    monkeypatch.setenv("CITEGUARD_EMBED_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("CITEGUARD_EMBED_API_KEY", "sk-test")
    vectors = embeddings.embed_texts(["cat", "dog"])
    assert vectors == [[1.0, 0.0, 0.0], [0.8, 0.2, 0.0]]
    sent = handler.requests[-1]
    assert sent["path"] == "/v1/embeddings"
    assert sent["auth"] == "Bearer sk-test"
    assert sent["body"]["model"] == "BAAI/bge-m3"


def test_endpoint_with_embeddings_suffix_is_not_doubled(fake_server):
    url, handler = fake_server
    cfg = embeddings.EmbeddingConfig(endpoint=url + "/embeddings")
    embeddings.embed_texts(["cat"], config=cfg)
    assert handler.requests[-1]["path"] == "/v1/embeddings"


def test_rerank_orders_similar_first(fake_server):
    url, _ = fake_server
    cfg = embeddings.EmbeddingConfig(endpoint=url)
    ranked = embeddings.rerank("a cat photo", ["a dog", "a city"], config=cfg)
    assert [i for i, _ in ranked] == [0, 1]
    assert ranked[0][1] > 0.9
    assert ranked[1][1] == pytest.approx(0.0)


def test_http_error_is_reported(fake_server, monkeypatch):
    url, handler = fake_server
    handler.fail = True
    monkeypatch.setenv("CITEGUARD_EMBED_ENDPOINT", url)
    with pytest.raises(embeddings.EmbeddingError) as err:
        embeddings.embed_texts(["cat"])
    assert "HTTP 500" in str(err.value)


def test_cosine_edge_cases():
    assert embeddings.cosine([1, 0], [1, 0]) == 1.0
    assert embeddings.cosine([], [1]) == 0.0
    assert embeddings.cosine([0, 0], [1, 1]) == 0.0
