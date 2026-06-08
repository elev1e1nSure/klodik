import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import WebSocket, WebSocketDisconnect
from httpx import ASGITransport, AsyncClient

from server import app, manager, websocket_endpoint
from agent import agent_loop
from tools.registry import registry


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_runs(self):
        from server import lifespan, app
        async with lifespan(app):
            pass


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_send_personal_message_swallows_error(self):
        ws = AsyncMock(spec=WebSocket)
        ws.send_text = AsyncMock(side_effect=RuntimeError("closed"))
        ws.client_state = 1  # CONNECTED
        await manager.send_personal_message("hello", ws)

    @pytest.mark.asyncio
    async def test_disconnect_missing_ws(self):
        ws = AsyncMock(spec=WebSocket)
        manager.disconnect(ws)  # should not raise


class TestWebSocket:
    @pytest.mark.asyncio
    async def test_websocket_invalid_json(self):
        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        ws.receive_text = AsyncMock(side_effect=["not json", WebSocketDisconnect()])
        await websocket_endpoint(ws)
        ws.send_text.assert_called_once()
        call_arg = ws.send_text.call_args[0][0]
        data = json.loads(call_arg)
        assert data["type"] == "error"
        assert "Invalid JSON" in data["content"]

    @pytest.mark.asyncio
    async def test_websocket_task_triggers_agent_loop(self, monkeypatch):
        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        ws.receive_text = AsyncMock(side_effect=[
            json.dumps({"type": "task", "content": "hello"}),
            WebSocketDisconnect(),
        ])
        mock_agent_loop = AsyncMock()
        monkeypatch.setattr("server.agent_loop", mock_agent_loop)
        await websocket_endpoint(ws)
        mock_agent_loop.assert_called_once_with("hello", ws)


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_agent_loop_sends_thinking_message_idle(self, monkeypatch):
        class FakeMessage:
            content = "hi"
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        monkeypatch.setattr("agent.completion", lambda **_: FakeResponse())

        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        await agent_loop("do something", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        statuses = [c["content"] for c in calls if c["type"] == "status"]
        assert statuses[0] == "thinking"
        assert statuses[-1] == "idle"
        messages = [c["content"] for c in calls if c["type"] == "message"]
        assert messages[0] == "hi"

    @pytest.mark.asyncio
    async def test_agent_loop_with_tool_call(self, monkeypatch):
        call_count = 0
        def fake_completion(**_):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                class FakeToolCall:
                    class function:
                        name = "terminal"
                        arguments = json.dumps({"command": "echo tool_test"})
                    id = "call_1"
                class FakeMessage:
                    content = None
                    tool_calls = [FakeToolCall()]
                class FakeChoice:
                    message = FakeMessage()
                return type("R", (), {"choices": [FakeChoice()]})()
            else:
                class FakeMessage2:
                    content = "done"
                    tool_calls = None
                class FakeChoice2:
                    message = FakeMessage2()
                return type("R", (), {"choices": [FakeChoice2()]})()

        monkeypatch.setattr("agent.completion", fake_completion)

        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        await agent_loop("run tool", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        statuses = [c["content"] for c in calls if c["type"] == "status"]
        assert "thinking" in statuses
        assert "working" in statuses
        assert "idle" in statuses
        messages = [c["content"] for c in calls if c["type"] == "message"]
        assert messages[0] == "done"

    @pytest.mark.asyncio
    async def test_agent_loop_exception(self, monkeypatch):
        def bad_completion(**_):
            raise RuntimeError("ollama down")

        monkeypatch.setattr("agent.completion", bad_completion)

        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        await agent_loop("fail me", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        types = [c["type"] for c in calls]
        assert "error" in types
        assert "idle" in [c["content"] for c in calls if c["type"] == "status"]

    @pytest.mark.asyncio
    async def test_agent_loop_max_iterations(self, monkeypatch):
        class FakeToolCall:
            class function:
                name = "terminal"
                arguments = json.dumps({"command": "echo loop"})
            id = "call_loop"

        class FakeMessage:
            content = None
            tool_calls = [FakeToolCall()]

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        monkeypatch.setattr("agent.completion", lambda **_: FakeResponse())

        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        await agent_loop("loop forever", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        messages = [c["content"] for c in calls if c["type"] == "message"]
        assert "Достигнут лимит итераций инструментов." in messages
        assert "idle" in [c["content"] for c in calls if c["type"] == "status"]

    @pytest.mark.asyncio
    async def test_agent_loop_malformed_tool_args(self, monkeypatch):
        class FakeToolCall:
            class function:
                name = "terminal"
                arguments = "not-json{{"
            id = "call_bad"

        class FakeMessage:
            content = None
            tool_calls = [FakeToolCall()]

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        monkeypatch.setattr("agent.completion", lambda **_: FakeResponse())

        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        await agent_loop("bad args", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        errors = [c for c in calls if c["type"] == "error"]
        assert len(errors) >= 1
        assert "Invalid tool arguments" in errors[0]["content"]


class TestExecuteTool:
    def test_terminal_echo(self):
        result = registry.execute("terminal", {"command": "echo hello_test"})
        assert "hello_test" in result

    def test_read_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("file_content_123")
            path = f.name
        try:
            result = registry.execute("read_file", {"path": path})
            assert result == "file_content_123"
        finally:
            os.unlink(path)

    def test_write_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "test.txt")
            result = registry.execute("write_file", {"path": path, "content": "written"})
            assert "written" in result
            with open(path, "r") as f:
                assert f.read() == "written"

    def test_search_by_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "alpha.txt"), "w").close()
            open(os.path.join(tmpdir, "beta.py"), "w").close()
            result = registry.execute("search", {"query": "alpha", "path": tmpdir})
            assert "alpha.txt" in result
            assert "beta.py" not in result

    def test_search_by_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "note.txt"), "w") as f:
                f.write("magic_keyword_here")
            result = registry.execute("search", {"query": "magic_keyword", "path": tmpdir, "by_content": True})
            assert "note.txt" in result

    def test_unknown_tool(self):
        result = registry.execute("nonexistent", {})
        assert "Unknown tool" in result

    def test_terminal_error_exit_code(self):
        result = registry.execute("terminal", {"command": "exit 42"})
        assert "Exit code 42" in result

    def test_run_script(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('script_output')")
            path = f.name
        try:
            result = registry.execute("run_script", {"path": path})
            assert "script_output" in result
        finally:
            os.unlink(path)

    def test_run_script_error_exit_code(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("import sys; sys.exit(1)")
            path = f.name
        try:
            result = registry.execute("run_script", {"path": path})
            assert "Exit code 1" in result
        finally:
            os.unlink(path)

    def test_search_by_content_with_unreadable_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "binary.bin"), "wb") as f:
                f.write(b"\xff\xfe")
            with open(os.path.join(tmpdir, "text.txt"), "w") as f:
                f.write("magic_keyword")
            result = registry.execute("search", {"query": "magic_keyword", "path": tmpdir, "by_content": True})
            assert "text.txt" in result

    def test_mkdir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "new_folder")
            result = registry.execute("mkdir", {"path": path})
            assert "Directory created" in result
            assert os.path.isdir(path)

    def test_list_dir_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = registry.execute("list_dir", {"path": tmpdir})
            assert result == "(empty)"

    def test_list_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.txt"), "w").close()
            open(os.path.join(tmpdir, "b.txt"), "w").close()
            result = registry.execute("list_dir", {"path": tmpdir})
            assert "a.txt" in result
            assert "b.txt" in result

    def test_move_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "old.txt")
            dest = os.path.join(tmpdir, "new.txt")
            with open(source, "w") as f:
                f.write("data")
            result = registry.execute("move_file", {"source": source, "destination": dest})
            assert "Moved" in result
            assert os.path.exists(dest)
            assert not os.path.exists(source)

    def test_move_mouse_no_pyautogui(self, monkeypatch):
        monkeypatch.setattr("tools.input_tools.pyautogui", None)
        result = registry.execute("move_mouse", {"x": 100, "y": 200})
        assert "pyautogui not installed" in result

    def test_click_no_pyautogui(self, monkeypatch):
        monkeypatch.setattr("tools.input_tools.pyautogui", None)
        result = registry.execute("click", {"x": 100, "y": 200})
        assert "pyautogui not installed" in result

    def test_move_mouse_with_pyautogui(self, monkeypatch):
        mock_pyautogui = MagicMock()
        monkeypatch.setattr("tools.input_tools.pyautogui", mock_pyautogui)
        result = registry.execute("move_mouse", {"x": 100, "y": 200})
        assert "Mouse moved to (100, 200)" in result
        mock_pyautogui.moveTo.assert_called_once_with(100, 200, duration=0.5)

    def test_click_with_pyautogui(self, monkeypatch):
        mock_pyautogui = MagicMock()
        monkeypatch.setattr("tools.input_tools.pyautogui", mock_pyautogui)
        result = registry.execute("click", {"x": 100, "y": 200})
        assert "Clicked at (100, 200)" in result
        mock_pyautogui.click.assert_called_once_with(100, 200)

    def test_search_open_exception(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "file.txt")
            with open(path, "w") as f:
                f.write("content")

            def bad_open(*args, **kwargs):
                raise PermissionError("denied")
            monkeypatch.setattr("builtins.open", bad_open)

            result = registry.execute("search", {"query": "content", "path": tmpdir, "by_content": True})
            assert result == "No matches found"

    def test_execute_tool_exception(self):
        result = registry.execute("read_file", {"path": "/nonexistent/path/xyz.txt"})
        assert "Error:" in result

    def test_read_file_not_found(self):
        result = registry.execute("read_file", {"path": "/this/does/not/exist.txt"})
        assert "File not found" in result

    def test_move_file_missing_source(self):
        result = registry.execute("move_file", {"source": "/missing", "destination": "/dest"})
        assert "Source does not exist" in result

    def test_write_file_empty_path(self):
        result = registry.execute("write_file", {"path": "", "content": "x"})
        assert "Path cannot be empty" in result
