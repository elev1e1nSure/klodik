import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import WebSocket, WebSocketDisconnect
from httpx import ASGITransport, AsyncClient

from main import app, execute_tool, manager, websocket_endpoint, agent_loop


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
        from main import lifespan, app
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
        await manager.send_personal_message("hello", ws)


class TestWebSocket:
    @pytest.mark.asyncio
    async def test_websocket_invalid_json(self):
        ws = AsyncMock(spec=WebSocket)
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
        ws.receive_text = AsyncMock(side_effect=[
            json.dumps({"type": "task", "content": "hello"}),
            WebSocketDisconnect(),
        ])
        mock_agent_loop = AsyncMock()
        monkeypatch.setattr("main.agent_loop", mock_agent_loop)
        await websocket_endpoint(ws)
        mock_agent_loop.assert_called_once_with("hello", ws)


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_agent_loop_sends_thinking_message_idle(self, monkeypatch):
        from main import completion

        class FakeMessage:
            content = "hi"
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        monkeypatch.setattr("main.completion", lambda **_: FakeResponse())

        ws = AsyncMock(spec=WebSocket)
        await agent_loop("do something", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        statuses = [c["content"] for c in calls if c["type"] == "status"]
        assert statuses[0] == "thinking"
        assert statuses[-1] == "idle"
        messages = [c["content"] for c in calls if c["type"] == "message"]
        assert messages[0] == "hi"

    @pytest.mark.asyncio
    async def test_agent_loop_with_tool_call(self, monkeypatch):
        from main import completion

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

        monkeypatch.setattr("main.completion", fake_completion)

        ws = AsyncMock(spec=WebSocket)
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
        from main import completion

        def bad_completion(**_):
            raise RuntimeError("ollama down")

        monkeypatch.setattr("main.completion", bad_completion)

        ws = AsyncMock(spec=WebSocket)
        await agent_loop("fail me", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        types = [c["type"] for c in calls]
        assert "error" in types
        assert "idle" in [c["content"] for c in calls if c["type"] == "status"]

    @pytest.mark.asyncio
    async def test_agent_loop_max_iterations(self, monkeypatch):
        from main import completion

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

        monkeypatch.setattr("main.completion", lambda **_: FakeResponse())

        ws = AsyncMock(spec=WebSocket)
        await agent_loop("loop forever", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        messages = [c["content"] for c in calls if c["type"] == "message"]
        assert "Reached max tool iterations." in messages
        assert "idle" in [c["content"] for c in calls if c["type"] == "status"]


class TestExecuteTool:
    def test_terminal_echo(self):
        result = execute_tool("terminal", {"command": "echo hello_test"})
        assert "hello_test" in result

    def test_read_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("file_content_123")
            path = f.name
        try:
            result = execute_tool("read_file", {"path": path})
            assert result == "file_content_123"
        finally:
            os.unlink(path)

    def test_write_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "test.txt")
            result = execute_tool("write_file", {"path": path, "content": "written"})
            assert "written" in result
            with open(path, "r") as f:
                assert f.read() == "written"

    def test_search_by_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "alpha.txt"), "w").close()
            open(os.path.join(tmpdir, "beta.py"), "w").close()
            result = execute_tool("search", {"query": "alpha", "path": tmpdir})
            assert "alpha.txt" in result
            assert "beta.py" not in result

    def test_search_by_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "note.txt"), "w") as f:
                f.write("magic_keyword_here")
            result = execute_tool("search", {"query": "magic_keyword", "path": tmpdir, "by_content": True})
            assert "note.txt" in result

    def test_unknown_tool(self):
        result = execute_tool("nonexistent", {})
        assert "Unknown tool" in result

    def test_terminal_error_exit_code(self):
        result = execute_tool("terminal", {"command": "exit 42"})
        assert "Exit code 42" in result

    def test_run_script(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('script_output')")
            path = f.name
        try:
            result = execute_tool("run_script", {"path": path})
            assert "script_output" in result
        finally:
            os.unlink(path)

    def test_run_script_error_exit_code(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("import sys; sys.exit(1)")
            path = f.name
        try:
            result = execute_tool("run_script", {"path": path})
            assert "Exit code 1" in result
        finally:
            os.unlink(path)

    def test_search_by_content_with_unreadable_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "binary.bin"), "wb") as f:
                f.write(b"\xff\xfe")
            with open(os.path.join(tmpdir, "text.txt"), "w") as f:
                f.write("magic_keyword")
            result = execute_tool("search", {"query": "magic_keyword", "path": tmpdir, "by_content": True})
            assert "text.txt" in result

    def test_mkdir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "new_folder")
            result = execute_tool("mkdir", {"path": path})
            assert "Directory created" in result
            assert os.path.isdir(path)

    def test_list_dir_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_tool("list_dir", {"path": tmpdir})
            assert result == "(empty)"

    def test_list_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.txt"), "w").close()
            open(os.path.join(tmpdir, "b.txt"), "w").close()
            result = execute_tool("list_dir", {"path": tmpdir})
            assert "a.txt" in result
            assert "b.txt" in result

    def test_move_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "old.txt")
            dest = os.path.join(tmpdir, "new.txt")
            with open(source, "w") as f:
                f.write("data")
            result = execute_tool("move_file", {"source": source, "destination": dest})
            assert "Moved" in result
            assert os.path.exists(dest)
            assert not os.path.exists(source)

    def test_move_mouse_no_pyautogui(self):
        result = execute_tool("move_mouse", {"x": 100, "y": 200})
        assert "pyautogui not installed" in result

    def test_click_no_pyautogui(self):
        result = execute_tool("click", {"x": 100, "y": 200})
        assert "pyautogui not installed" in result

    def test_move_mouse_with_pyautogui(self, monkeypatch):
        mock_pyautogui = MagicMock()
        monkeypatch.setattr("main.pyautogui", mock_pyautogui)
        result = execute_tool("move_mouse", {"x": 100, "y": 200})
        assert "Mouse moved to (100, 200)" in result
        mock_pyautogui.moveTo.assert_called_once_with(100, 200, duration=0.5)

    def test_click_with_pyautogui(self, monkeypatch):
        mock_pyautogui = MagicMock()
        monkeypatch.setattr("main.pyautogui", mock_pyautogui)
        result = execute_tool("click", {"x": 100, "y": 200})
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

            result = execute_tool("search", {"query": "content", "path": tmpdir, "by_content": True})
            assert result == "No matches found"

    def test_execute_tool_exception(self):
        result = execute_tool("read_file", {"path": "/nonexistent/path/xyz.txt"})
        assert "Error:" in result


