import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from agent import agent_loop
from tools.registry import registry


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, message):
        self.choices = [FakeChoice(message)]


class TestAgentLoopAntiLoop:
    """Tests for deduplication, blocked_tools, and error-count heuristics."""

    @pytest.mark.asyncio
    async def test_agent_loop_blocks_tool_after_error(self, monkeypatch):
        """After a tool returns Error, it should be skipped on next iteration."""
        call_count = 0

        def fake_completion(**_):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                class FakeToolCall:
                    class function:
                        name = "terminal"
                        arguments = json.dumps({"command": "exit 1"})
                    id = "call_1"
                return FakeResponse(FakeMessage(tool_calls=[FakeToolCall()]))
            else:
                return FakeResponse(FakeMessage(content="done"))

        monkeypatch.setattr("agent.completion", fake_completion)

        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        await agent_loop("test", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        messages = [c["content"] for c in calls if c["type"] == "message"]
        assert messages[0] == "done"

    @pytest.mark.asyncio
    async def test_agent_loop_stops_after_three_errors(self, monkeypatch):
        """Three consecutive tool errors should abort the loop."""
        class FakeToolCall:
            class function:
                name = "move_mouse"
                arguments = json.dumps({"x": 0, "y": 0})
            id = "call_err"

        monkeypatch.setattr("agent.completion", lambda **_: FakeResponse(FakeMessage(tool_calls=[FakeToolCall()])))
        # Force the tool to always return an error
        monkeypatch.setattr(
            registry, "execute",
            lambda _name, _args: "Error: fake error",
        )

        ws = AsyncMock(spec=WebSocket)
        ws.client_state = 1
        await agent_loop("fail loop", ws)

        calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        messages = [c["content"] for c in calls if c["type"] == "message"]
        assert any("Не получается выполнить действие" in m for m in messages)


class TestVisionTools:
    def test_screenshot_no_pyautogui(self, monkeypatch):
        monkeypatch.setattr("tools.vision_tools.pyautogui", None)
        result = registry.execute("screenshot", {})
        assert "pyautogui not installed" in result

    def test_screenshot_with_pyautogui(self, monkeypatch, tmp_path):
        mock_img = MagicMock()
        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.return_value = mock_img
        monkeypatch.setattr("tools.vision_tools.pyautogui", mock_pyautogui)

        path = str(tmp_path / "scr.png")
        result = registry.execute("screenshot", {"path": path})
        assert "Screenshot saved" in result
        mock_pyautogui.screenshot.assert_called_once()
        mock_img.save.assert_called_once()

    def test_get_active_window_no_pyautogui(self, monkeypatch):
        monkeypatch.setattr("tools.vision_tools.pyautogui", None)
        result = registry.execute("get_active_window", {})
        assert "pyautogui not installed" in result

    def test_get_active_window_with_pyautogui(self, monkeypatch):
        mock_win = MagicMock()
        mock_win.title = "Test Window"
        mock_win.left = 10
        mock_win.top = 20
        mock_win.width = 300
        mock_win.height = 400
        mock_pyautogui = MagicMock()
        mock_pyautogui.getActiveWindow.return_value = mock_win
        monkeypatch.setattr("tools.vision_tools.pyautogui", mock_pyautogui)

        result = registry.execute("get_active_window", {})
        assert "Test Window" in result
        assert "300x400" in result

    def test_click_element_with_pyautogui(self, monkeypatch, tmp_path):
        mock_img = MagicMock()
        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.return_value = mock_img
        monkeypatch.setattr("tools.vision_tools.pyautogui", mock_pyautogui)

        result = registry.execute("click_element", {"description": "Save button"})
        assert "Save button" in result
        mock_pyautogui.screenshot.assert_called_once()


class TestClipboardTools:
    def test_read_clipboard_with_pyperclip(self, monkeypatch):
        mock_pyperclip = MagicMock()
        mock_pyperclip.paste.return_value = "hello clipboard"
        monkeypatch.setattr("tools.clipboard_tools.pyperclip", mock_pyperclip)

        result = registry.execute("read_clipboard", {})
        assert "hello clipboard" in result

    def test_write_clipboard_with_pyperclip(self, monkeypatch):
        mock_pyperclip = MagicMock()
        monkeypatch.setattr("tools.clipboard_tools.pyperclip", mock_pyperclip)

        result = registry.execute("write_clipboard", {"text": "copied text"})
        assert "Copied to clipboard" in result
        mock_pyperclip.copy.assert_called_once_with("copied text")


class TestWindowTools:
    def test_list_windows_no_pygetwindow(self, monkeypatch):
        monkeypatch.setattr("tools.window_tools.gw", None)
        result = registry.execute("list_windows", {})
        assert "pygetwindow not installed" in result

    def test_list_windows_with_pygetwindow(self, monkeypatch):
        mock_win1 = MagicMock()
        mock_win1.title = "VS Code"
        mock_win1.visible = True
        mock_win1.left = 0
        mock_win1.top = 0
        mock_win1.width = 1920
        mock_win1.height = 1080

        mock_win2 = MagicMock()
        mock_win2.title = ""
        mock_win2.visible = True
        mock_win2.left = 0
        mock_win2.top = 0
        mock_win2.width = 100
        mock_win2.height = 100

        mock_gw = MagicMock()
        mock_gw.getAllWindows.return_value = [mock_win1, mock_win2]
        monkeypatch.setattr("tools.window_tools.gw", mock_gw)

        result = registry.execute("list_windows", {})
        assert "VS Code" in result
        assert "1920x1080" in result

    def test_focus_window(self, monkeypatch):
        mock_win = MagicMock()
        mock_win.title = "Notepad"
        mock_gw = MagicMock()
        mock_gw.getWindowsWithTitle.return_value = [mock_win]
        monkeypatch.setattr("tools.window_tools.gw", mock_gw)

        result = registry.execute("focus_window", {"title": "Notepad"})
        assert "Focused window" in result
        mock_win.activate.assert_called_once()

    def test_minimize_window(self, monkeypatch):
        mock_win = MagicMock()
        mock_win.title = "Calculator"
        mock_gw = MagicMock()
        mock_gw.getWindowsWithTitle.return_value = [mock_win]
        monkeypatch.setattr("tools.window_tools.gw", mock_gw)

        result = registry.execute("minimize_window", {"title": "Calculator"})
        assert "Minimized" in result
        mock_win.minimize.assert_called_once()

    def test_move_window(self, monkeypatch):
        mock_win = MagicMock()
        mock_win.title = "Explorer"
        mock_gw = MagicMock()
        mock_gw.getWindowsWithTitle.return_value = [mock_win]
        monkeypatch.setattr("tools.window_tools.gw", mock_gw)

        result = registry.execute("move_window", {"title": "Explorer", "x": 100, "y": 200, "width": 800, "height": 600})
        assert "Moved/resized" in result
        mock_win.moveTo.assert_called_once_with(100, 200)
        mock_win.resizeTo.assert_called_once_with(800, 600)


class TestSessionLog:
    def test_append_and_read(self, monkeypatch, tmp_path):
        import session_log as sl_mod

        # Redirect log dir to tmp_path
        monkeypatch.setattr(sl_mod, "_LOG_DIR", tmp_path)
        monkeypatch.setattr(sl_mod, "_current_session_path", None)

        session_log = sl_mod.SessionLog()
        session_log.append("terminal", "output here")
        session_log.append("click", "clicked at 100,200")

        files = session_log.list_sessions()
        assert len(files) == 1

        content = session_log.read_session(files[0])
        assert "terminal" in content
        assert "output here" in content
        assert "click" in content
