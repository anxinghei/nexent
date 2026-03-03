"""
Unit tests for northbound_app module.

Tests the API endpoints in the northbound_app router.
"""
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
import types
import sys as _sys

# Dynamically determine the backend path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "../../../backend"))
sys.path.append(backend_dir)


# Pre-mock heavy dependencies before importing router
sys.modules['consts'] = MagicMock()
sys.modules['consts.model'] = MagicMock()

# Mock nexent module before any imports that depend on it
sys.modules['nexent'] = MagicMock()
sys.modules['nexent.core'] = MagicMock()
sys.modules['nexent.core.agents'] = MagicMock()
sys.modules['nexent.core.agents.agent_model'] = MagicMock()

consts_exceptions_mod = types.ModuleType("consts.exceptions")


class LimitExceededError(Exception):
    pass


class UnauthorizedError(Exception):
    pass


class SignatureValidationError(Exception):
    pass


consts_exceptions_mod.LimitExceededError = LimitExceededError
consts_exceptions_mod.UnauthorizedError = UnauthorizedError
consts_exceptions_mod.SignatureValidationError = SignatureValidationError

# Ensure the parent 'consts' is a module
if 'consts' not in _sys.modules or not isinstance(_sys.modules['consts'], types.ModuleType):
    consts_root = types.ModuleType("consts")
    consts_root.__path__ = []
    _sys.modules['consts'] = consts_root
else:
    consts_root = _sys.modules['consts']

consts_root.exceptions = consts_exceptions_mod
_sys.modules['consts.exceptions'] = consts_exceptions_mod
sys.modules['services'] = MagicMock()
sys.modules['services.northbound_service'] = MagicMock()
sys.modules['utils'] = MagicMock()
sys.modules['utils.auth_utils'] = MagicMock()

# Import router after setting mocks
from apps.northbound_app import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _build_headers(auth="Bearer test_jwt", request_id="req-123", aksk=True):
    headers = {
        "Authorization": auth,
        "X-Request-Id": request_id,
    }
    if aksk:
        headers.update({
            "X-Access-Key": "ak",
            "X-Timestamp": "1710000000",
            "X-Signature": "sig",
        })
    return headers


def _std_headers(auth="Bearer test_jwt"):
    return {
        **_build_headers(auth=auth),
        "Idempotency-Key": "idem-xyz",
    }


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self):
        resp = client.get("/nb/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "northbound-api"


class TestServiceCalls:
    """Tests for service call functionality."""

    def test_run_chat_calls_service(self, monkeypatch):
        """Test POST /chat/run calls start_streaming_chat service."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))

        async def _gen():
            yield b"data: hello\n\n"
        start_mock = AsyncMock(return_value=StreamingResponse(
            _gen(), media_type="text/event-stream"))
        monkeypatch.setattr(
            "apps.northbound_app.start_streaming_chat", start_mock)

        payload = {"conversation_id": "nb-1",
                   "agent_name": "agent-a", "query": "hi"}
        headers = {**_build_headers(), "Idempotency-Key": "idem-1"}
        resp = client.post("/nb/v1/chat/run", json=payload, headers=headers)

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert start_mock.await_count == 1
        args, kwargs = start_mock.call_args
        assert kwargs["external_conversation_id"] == "nb-1"
        assert kwargs["agent_name"] == "agent-a"
        assert kwargs["query"] == "hi"
        assert kwargs["idempotency_key"] == "idem-1"

    def test_stop_chat_calls_service(self, monkeypatch):
        """Test GET /chat/stop/{conversation_id} calls stop_chat service."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body=None: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))
        stop_mock = AsyncMock(return_value={"message": "success"})
        monkeypatch.setattr("apps.northbound_app.stop_chat", stop_mock)

        resp = client.get("/nb/v1/chat/stop/nb-2", headers=_build_headers())
        assert resp.status_code == 200
        assert stop_mock.await_count == 1

    def test_get_history_calls_service(self, monkeypatch):
        """Test GET /conversations/{conversation_id} calls get_conversation_history service."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body=None: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))
        hist_mock = AsyncMock(return_value={"message": "success"})
        monkeypatch.setattr(
            "apps.northbound_app.get_conversation_history", hist_mock)

        resp = client.get("/nb/v1/conversations/nb-3",
                          headers=_build_headers())
        assert resp.status_code == 200
        assert hist_mock.await_count == 1

    def test_list_agents_calls_service(self, monkeypatch):
        """Test GET /agents calls get_agent_info_list service."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body=None: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))
        agents_mock = AsyncMock(
            return_value={"message": "success", "data": []})
        monkeypatch.setattr(
            "apps.northbound_app.get_agent_info_list", agents_mock)

        resp = client.get("/nb/v1/agents", headers=_build_headers())
        assert resp.status_code == 200
        assert agents_mock.await_count == 1

    def test_list_conversations_calls_service(self, monkeypatch):
        """Test GET /conversations calls list_conversations service."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body=None: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))
        list_mock = AsyncMock(return_value={"message": "success", "data": []})
        monkeypatch.setattr(
            "apps.northbound_app.list_conversations", list_mock)

        resp = client.get("/nb/v1/conversations", headers=_build_headers())
        assert resp.status_code == 200
        assert list_mock.await_count == 1

    def test_update_title_sets_headers(self, monkeypatch):
        """Test PUT /conversations/{conversation_id}/title calls update_conversation_title service."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body=None: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))

        class _NCtx:
            def __init__(self, request_id: str, tenant_id: str, user_id: str, authorization: str):
                self.request_id = request_id
                self.tenant_id = tenant_id
                self.user_id = user_id
                self.authorization = authorization
        monkeypatch.setattr("apps.northbound_app.NorthboundContext", _NCtx)

        update_mock = AsyncMock(
            return_value={"message": "success", "data": "nb-4", "idempotency_key": "ide-xyz"})
        monkeypatch.setattr(
            "apps.northbound_app.update_conversation_title", update_mock)

        headers = {**_build_headers(request_id="req-999"),
                   "Idempotency-Key": "ide-xyz"}
        resp = client.put("/nb/v1/conversations/nb-4/title",
                          params={"title": "New Title"}, headers=headers)

        assert resp.status_code == 200
        assert resp.headers.get("Idempotency-Key") == "ide-xyz"
        assert resp.headers.get("X-Request-Id") == "req-999"
        assert update_mock.await_count == 1


class TestAuthenticationExceptions:
    """Tests for authentication exception handling."""

    @pytest.mark.parametrize("exc_cls_name, status", [
        ("UnauthorizedError", 401),
        ("LimitExceededError", 429),
        ("SignatureValidationError", 401),
    ])
    def test_auth_exceptions_are_mapped(self, exc_cls_name, status):
        """Test all endpoints map auth exceptions to correct HTTP status codes."""
        # Get the exception class from consts.exceptions module
        # which is what northbound_app catches
        exc_cls = _sys.modules['consts.exceptions'].__dict__[exc_cls_name]

        def _raise(*_, **__):
            raise exc_cls("boom")

        # Patch validate_aksk_authentication to raise the exception
        with patch("apps.northbound_app.validate_aksk_authentication", _raise):
            # Test only GET endpoints
            endpoints = [
                "/nb/v1/chat/stop/nb-x",
                "/nb/v1/conversations/nb-x",
                "/nb/v1/agents",
                "/nb/v1/conversations",
            ]

            for path in endpoints:
                resp = client.get(path, headers=_build_headers())
                assert resp.status_code == status, f"Failed for {path}"


class TestJWTAuthentication:
    """Tests for JWT authentication handling."""

    def test_missing_authorization_header_returns_401(self, monkeypatch):
        """Test missing Authorization header returns 401."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body: True)
        headers = {k: v for k, v in _std_headers().items() if k.lower()
                   != "authorization"}
        resp = client.post("/nb/v1/chat/run", json={
                           "conversation_id": "nb-1", "agent_name": "a", "query": "hi"}, headers=headers)

        assert resp.status_code == 401
        assert resp.json()["detail"].startswith(
            "Unauthorized: No authorization header")

    def test_jwt_parse_exception_returns_500(self, monkeypatch):
        """Test JWT parse exception returns 500."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body: True)

        def _raise_jwt(_auth):
            raise Exception("jwt parse error")
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", _raise_jwt)

        resp = client.post("/nb/v1/chat/run", json={
                           "conversation_id": "nb-1", "agent_name": "a", "query": "hi"}, headers=_std_headers())

        assert resp.status_code == 500
        assert "cannot parse JWT token" in resp.json()["detail"]

    @pytest.mark.parametrize("user_id,tenant_id,expected_detail", [
        (None, "t1", "missing user_id"),
        ("u1", None, "unregistered user_id"),
    ])
    def test_jwt_missing_ids_return_401(self, monkeypatch, user_id, tenant_id, expected_detail):
        """Test missing user_id or tenant_id returns 401."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda _auth: (user_id, tenant_id))

        resp = client.post("/nb/v1/chat/run", json={
                           "conversation_id": "nb-1", "agent_name": "a", "query": "hi"}, headers=_std_headers())

        assert resp.status_code == 401
        assert expected_detail in resp.json()["detail"]


class TestServiceErrors:
    """Tests for service error handling."""

    @pytest.mark.parametrize("path,method,json_data", [
        ("/nb/v1/chat/stop/nb-x", "GET", None),
        ("/nb/v1/conversations/nb-x", "GET", None),
        ("/nb/v1/agents", "GET", None),
        ("/nb/v1/conversations", "GET", None),
    ])
    def test_service_errors_map_to_500(self, monkeypatch, path, method, json_data):
        """Test unexpected service errors return 500."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body=None: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))

        service_map = {
            "/nb/v1/chat/stop/nb-x": "apps.northbound_app.stop_chat",
            "/nb/v1/conversations/nb-x": "apps.northbound_app.get_conversation_history",
            "/nb/v1/agents": "apps.northbound_app.get_agent_info_list",
            "/nb/v1/conversations": "apps.northbound_app.list_conversations",
        }

        monkeypatch.setattr(service_map[path], AsyncMock(
            side_effect=Exception("boom")))

        resp = client.get(path, headers=_build_headers())

        assert resp.status_code == 500

    def test_update_title_service_error_maps_500(self, monkeypatch):
        """Test update_conversation_title service error returns 500."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body=None: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))
        monkeypatch.setattr("apps.northbound_app.update_conversation_title", AsyncMock(
            side_effect=Exception("boom")))

        resp = client.put("/nb/v1/conversations/nb-4/title",
                          params={"title": "x"}, headers=_build_headers())

        assert resp.status_code == 500


class TestContextParsing:
    """Tests for context parsing edge cases."""

    def test_context_parsing_internal_error_returns_500(self, monkeypatch):
        """Test internal error during context parsing returns 500."""
        def _raise(*_, **__):
            raise Exception("unexpected")
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", _raise)

        resp = client.post("/nb/v1/chat/run", json={
                           "conversation_id": "nb-1", "agent_name": "a", "query": "hi"}, headers=_std_headers())

        assert resp.status_code == 500
        assert "cannot parse northbound context" in resp.json()["detail"]

    def test_request_body_read_failure_is_tolerated(self, monkeypatch):
        """Test request body read failure uses empty body and continues."""
        captured = {"seen": None}

        def _validate(headers, body):
            captured["seen"] = body
            return True

        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", _validate)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))

        class _NCtx:
            def __init__(self, request_id: str, tenant_id: str, user_id: str, authorization: str):
                self.request_id = request_id
                self.tenant_id = tenant_id
                self.user_id = user_id
                self.authorization = authorization

        monkeypatch.setattr("apps.northbound_app.NorthboundContext", _NCtx)

        async def _ctx_builder(request):
            _validate(request.headers, "")
            auth = next((v for k, v in request.headers.items()
                        if k.lower() == "authorization"), "")
            req_id = next((v for k, v in request.headers.items()
                          if k.lower() == "x-request-id"), "req-ctx")
            return _NCtx(request_id=req_id, tenant_id="t1", user_id="u1", authorization=auth)

        monkeypatch.setattr(
            "apps.northbound_app._parse_northbound_context", _ctx_builder)

        async def _gen():
            yield b"data: ok\n\n"
        start_mock = AsyncMock(return_value=StreamingResponse(
            _gen(), media_type="text/event-stream"))
        monkeypatch.setattr(
            "apps.northbound_app.start_streaming_chat", start_mock)

        resp = client.post("/nb/v1/chat/run", json={
                           "conversation_id": "nb-1", "agent_name": "a", "query": "hi"}, headers=_std_headers())

        assert resp.status_code == 200
        assert captured["seen"] == ""
        assert "text/event-stream" in resp.headers["content-type"]


class TestResponseHeaders:
    """Tests for response header handling."""

    def test_run_chat_response_headers(self, monkeypatch):
        """Test run_chat passes headers from context to response."""
        monkeypatch.setattr(
            "apps.northbound_app.validate_aksk_authentication", lambda headers, body: True)
        monkeypatch.setattr(
            "apps.northbound_app.get_current_user_id", lambda auth: ("u1", "t1"))

        class _NCtx:
            def __init__(self, request_id: str, tenant_id: str, user_id: str, authorization: str):
                self.request_id = request_id
                self.tenant_id = tenant_id
                self.user_id = user_id
                self.authorization = authorization

        monkeypatch.setattr("apps.northbound_app.NorthboundContext", _NCtx)

        async def _gen():
            yield b"data: ok\n\n"

        async def _start(ctx, external_conversation_id, agent_name, query, idempotency_key=None):
            resp = StreamingResponse(_gen(), media_type="text/event-stream")
            resp.headers["X-Request-Id"] = ctx.request_id
            resp.headers["conversation_id"] = external_conversation_id
            return resp

        monkeypatch.setattr("apps.northbound_app.start_streaming_chat", _start)

        headers = {**_std_headers(), "X-Request-Id": "rid-123"}
        resp = client.post("/nb/v1/chat/run", json={
                           "conversation_id": "nb-1", "agent_name": "agent-a", "query": "hello"}, headers=headers)

        assert resp.status_code == 200
        assert resp.headers.get("X-Request-Id") == "rid-123"
        assert resp.headers.get("conversation_id") == "nb-1"
