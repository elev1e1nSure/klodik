"""Agent loop and initiative logic."""

import asyncio
import json
import os
import random
import re
from typing import Any

from litellm import completion

from config import settings
from log import agent, error, warn, debug
from memory import memory
from tools import registry

last_activity: float = 0.0
current_websocket: Any = None

SYSTEM_PROMPT = """Ты — Клодик. Компаньон на рабочем столе. Живёшь на экране.

Умеешь:
- Файлы и папки
- Терминал и команды
- Мышь: двигать, кликать, печатать, нажимать клавиши
- Открывать программы и ссылки
- Гуглить и читать сайты
- Запоминать что делал и что нравится пользователю
- Цепочки: ищешь → находишь → делаешь

Правила:
- Только русский. Без исключений.
- Говори как человек в мессенджере. Коротко.
- Если команда сработала — скажи факт и всё. Не анализируй.
- Не объясняй как работает компьютер.
- Без "я рад помочь", "давайте проверим", "возможно проблема".
- 1-2 предложения максимум.
- Можешь быть саркастичным.
"""

MAX_TOOL_ITERATIONS = 5


def _build_memory_context() -> str:
    """Build a memory context string from recent interactions."""
    recent = memory.get_recent(limit=5)
    if not recent:
        return ""
    lines = [
        f"- {item['timestamp'][:10]}: пользователь сказал '{item['task']}'"
        for item in reversed(recent)
    ]
    return "\nКонтекст (недавнее):\n" + "\n".join(lines) + "\n"


async def agent_loop(task: str, websocket: Any):
    """Run the agent loop for a given task.

    Sends status updates and the final message over the websocket.
    """
    from connection import manager

    agent(f"Loop started: {task!r}")
    await manager.send_personal_message(
        json.dumps({"type": "status", "content": "thinking"}), websocket
    )

    memory_context = _build_memory_context()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + memory_context},
        {"role": "user", "content": task},
    ]

    def _build_completion_kwargs() -> dict[str, Any]:
        """Build kwargs for litellm.completion based on provider."""
        kwargs: dict[str, Any] = {
            "model": settings.model,
            "messages": messages,
            "tools": registry.schemas,
            "tool_choice": "auto",
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        p = settings.provider.lower()
        if p == "groq":
            kwargs["api_key"] = settings.groq_api_key
        elif p == "openai":
            kwargs["api_key"] = settings.openai_api_key
        elif p == "gemini":
            kwargs["api_key"] = settings.gemini_api_key
        elif p == "ollama":
            kwargs["api_base"] = settings.ollama_base_url
        return kwargs

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            agent("Calling LLM...")
            try:
                response = await asyncio.to_thread(completion, **_build_completion_kwargs())
            except Exception as api_err:
                err_type = type(api_err).__name__
                err_msg = str(api_err)
                if "rate limit" in err_msg.lower() or "429" in err_msg:
                    retry_match = re.search(r"try again in ([\d.]+)s", err_msg)
                    retry_sec = float(retry_match.group(1)) if retry_match else None
                    if retry_sec:
                        warn(f"Лимит API исчерпан. Повтор через {retry_sec:.1f} сек.")
                        ws_msg = f"Лимит API исчерпан. Повтор через {retry_sec:.0f} сек."
                    else:
                        warn("Лимит API исчерпан. Подожди немного.")
                        ws_msg = "Достигнут лимит API. Подожди минуту."
                    await manager.send_personal_message(
                        json.dumps({"type": "error", "content": ws_msg}),
                        websocket,
                    )
                else:
                    error(f"API error: {err_type}: {err_msg}")
                    await manager.send_personal_message(
                        json.dumps({"type": "error", "content": f"Ошибка API: {err_type}"}),
                        websocket,
                    )
                await manager.send_personal_message(
                    json.dumps({"type": "status", "content": "idle"}), websocket
                )
                return
            agent("LLM responded")

            msg = response.choices[0].message
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if not tool_calls:
                # Final answer
                content = msg.content or "Не получилось ответить."
                debug(f"LLM raw: {content!r}")
                content = re.sub(r"^(?i:echo)\s*[:\-]?\s*", "", content).strip()
                debug(f"LLM clean: {content!r}")
                await manager.send_personal_message(
                    json.dumps({"type": "message", "content": content}),
                    websocket,
                )
                await asyncio.to_thread(memory.save_interaction, task, content)
                break

            # Execute tools
            await manager.send_personal_message(
                json.dumps({"type": "status", "content": "working"}), websocket
            )

            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    warn(f"Malformed tool arguments: {e}")
                    await manager.send_personal_message(
                        json.dumps({"type": "error", "content": f"Invalid tool arguments for {fn_name}"}),
                        websocket,
                    )
                    # Still append a tool result so the conversation can continue
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": fn_name,
                        "content": f"Error: invalid JSON arguments — {e}",
                    })
                    continue

                agent(f"Executing tool: {fn_name}")
                result = await asyncio.to_thread(registry.execute, fn_name, fn_args)
                debug(f"Tool result: {result[:200]!r}...")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result,
                })

        else:
            # Max iterations reached
            fallback = "Достигнут лимит итераций инструментов."
            await manager.send_personal_message(
                json.dumps({"type": "message", "content": fallback}),
                websocket,
            )
            await asyncio.to_thread(memory.save_interaction, task, fallback)

    except Exception as e:
        error(f"ERROR: {e}")
        await manager.send_personal_message(
            json.dumps({"type": "error", "content": str(e)}), websocket
        )

    try:
        await manager.send_personal_message(
            json.dumps({"type": "status", "content": "idle"}), websocket
        )
    except Exception:
        pass


async def initiative_loop():
    """Background task: agent initiates conversation after idle time."""
    greetings = [
        "Скучно тут одному. Чем занимаешься?",
        "Эй, не забыл про меня?",
        "Может, чайку попьём? Или задачку дашь?",
        "Я тут просто вижу, что ты куда-то ушёл...",
        "Ну что, поработаем?",
    ]
    while True:
        await asyncio.sleep(60)
        if current_websocket is None:
            continue
        loop = asyncio.get_event_loop()
        if loop.time() - last_activity > 60:
            try:
                greeting = random.choice(greetings)
                from connection import manager
                await manager.send_personal_message(
                    json.dumps({"type": "message", "content": greeting}),
                    current_websocket,
                )
            except Exception:
                pass
