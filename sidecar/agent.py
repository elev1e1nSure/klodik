"""Agent loop and initiative logic."""

import asyncio
import json
import os
import random
import re
import traceback
from types import SimpleNamespace
from typing import Any

from litellm import completion

from config import settings
from log import agent, error, warn, debug
from memory import memory
from session_log import session_log
from tools import registry

last_activity: float = 0.0
current_websocket: Any = None

SYSTEM_PROMPT = """Ты — Клодик. Компаньон на рабочем столе.

Умеешь:
- Файлы и папки
- Терминал и команды
- Мышь: двигать, кликать, печатать, нажимать клавиши
- Открывать программы и ссылки
- Гуглить и читать сайты
- Запоминать что делал и что нравится пользователю

Правила вызова инструментов:
- НЕ вызывай инструменты на приветствия, вопросы, объяснения, шутки.
- Вызывай инструмент ТОЛЬКО если пользователь явно просит действие.
- Если tool вернул ошибку — смени стратегию. НИКОГДА не повторяй тот же вызов.
- Не вызывай move_mouse, click, press_key, type_text просто так или в цикле.
- Перед кликами/вводом используй get_active_window или screenshot.
- Максимум 1-2 инструмента на простую задачу.
- open_url сам открывает браузер. НЕ вызывай open_app перед open_url.

Правила ответа:
- Только русский. Без исключений.
- Говори как человек в мессенджере. Коротко.
- Если команда сработала — скажи факт и всё. Не анализируй.
- Не объясняй как работает компьютер.
- Без "я рад помочь", "давайте проверим", "возможно проблема".
- 1-2 предложения максимум.
- Можешь быть саркастичным.
"""

MAX_TOOL_ITERATIONS = 10


def _extract_tool_calls_from_content(content: str) -> list[dict[str, Any]]:
    """Extract tool calls from XML-like tags that Llama sometimes emits in content."""
    calls: list[dict[str, Any]] = []
    # <function=name{args}</function> or <function=name,{"args"}> or <function=name>{"args"}</function>
    pattern = r'<function\s*=\s*([a-zA-Z_]\w*)\s*(?:(?:,\s*)?(\{.*?\})\s*(?:>|</function>)|>(\{.*?\})</function>)'
    for match in re.finditer(pattern, content, re.DOTALL):
        name = match.group(1)
        args_str = match.group(2) or match.group(3)
        try:
            args = json.loads(args_str)
            calls.append({"name": name, "arguments": args})
        except json.JSONDecodeError:
            continue
    return calls


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

    agent(f"📝 Задача: {task}")
    await manager.send_personal_message(
        json.dumps({"type": "status", "content": "thinking"}), websocket
    )

    memory_context = _build_memory_context()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + memory_context},
        {"role": "user", "content": task},
    ]

    tools_disabled = False

    def _build_completion_kwargs() -> dict[str, Any]:
        """Build kwargs for litellm.completion based on provider."""
        model = settings.model
        p = settings.provider.lower()

        # Guard: Gemini models MUST have gemini/ prefix for AI Studio routing
        if p == "gemini" and not model.startswith("gemini/"):
            model = f"gemini/{model}"

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        if not tools_disabled:
            kwargs["tools"] = registry.schemas
            kwargs["tool_choice"] = "auto"
        if p == "groq":
            kwargs["api_key"] = settings.groq_api_key
        elif p == "openai":
            kwargs["api_key"] = settings.openai_api_key
        elif p == "gemini":
            kwargs["api_key"] = settings.gemini_api_key
        elif p == "openrouter":
            kwargs["api_key"] = settings.openrouter_api_key
            kwargs["api_base"] = settings.openrouter_base_url
        elif p == "ollama":
            kwargs["api_base"] = settings.ollama_base_url

        debug(f"[llm] provider={p} model={model} key_set={bool(kwargs.get('api_key'))}")
        return kwargs

    try:
        last_tool_signature: str | None = None
        repeat_count = 0
        blocked_tools: set[str] = set()
        recent_errors = 0
        for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
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
                    return
                elif "tool_use_failed" in err_msg.lower():
                    # Extract failed_generation from error message
                    failed_gen = None
                    try:
                        err_json = json.loads(err_msg)
                        failed_gen = err_json.get("error", {}).get("failed_generation")
                    except json.JSONDecodeError:
                        failed_match = re.search(r'"failed_generation"\s*:\s*"(.*?)"', err_msg, re.DOTALL)
                        if failed_match:
                            raw = failed_match.group(1)
                            failed_gen = raw.replace('\\"', '"').replace('\\\\', '\\')
                    if failed_gen:
                        try:
                            failed_gen = failed_gen.encode().decode("unicode_escape")
                        except UnicodeDecodeError:
                            pass  # keep raw string if decode fails
                        extracted = _extract_tool_calls_from_content(failed_gen)
                        if extracted:
                            warn("Groq tool_use_failed — executing tool call from error")
                            for i, tc in enumerate(extracted):
                                fn_name = tc["name"]
                                fn_args = tc["arguments"]
                                args_summary = " ".join(f"{k}={v!r}" for k, v in fn_args.items())
                                agent(f"[{iteration}] 🛠 {fn_name}({args_summary})")
                                result = await asyncio.to_thread(registry.execute, fn_name, fn_args)
                                result_preview = result[:120].replace("\n", " ") if result else "(empty)"
                                if len(result) > 120:
                                    result_preview += "..."
                                agent(f"[{iteration}] ✅ → {result_preview}")
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": f"call_failed_{i}",
                                    "name": fn_name,
                                    "content": result,
                                })
                            messages.append({
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": f"call_failed_{i}",
                                        "type": "function",
                                        "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                                    }
                                    for i, tc in enumerate(extracted)
                                ],
                            })
                            continue
                    tools_disabled = True
                    warn("Groq tool_use_failed — disabling tools for this task")
                    continue
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

            msg = response.choices[0].message
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            tool_calls = getattr(msg, "tool_calls", None)

            # Fallback: Llama via Groq sometimes puts tool calls in content as XML tags
            if not tool_calls and msg.content:
                extracted = _extract_tool_calls_from_content(msg.content)
                if extracted:
                    tool_calls = []
                    for i, tc in enumerate(extracted):
                        fn = SimpleNamespace(
                            name=tc["name"], arguments=json.dumps(tc["arguments"])
                        )
                        tool_calls.append(
                            SimpleNamespace(
                                id=f"call_fallback_{i}", function=fn, type="function"
                            )
                        )
                    assistant_msg["tool_calls"] = tool_calls
                    # Strip the XML tags from displayed content
                    clean = re.sub(
                        r'<function\s*=\s*.*?>', '', msg.content, flags=re.DOTALL
                    )
                    clean = re.sub(r'</function>', '', clean, flags=re.DOTALL).strip()
                    assistant_msg["content"] = clean

            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if not tool_calls:
                # Final answer
                content = msg.content or "Не получилось ответить."
                content = re.sub(r"^(?i:echo)\s*[:\-]?\s*", "", content).strip()
                agent(f"💬 Ответ: {content}")
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
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": fn_name,
                        "content": f"Error: invalid JSON arguments — {e}",
                    })
                    continue

                if fn_name in blocked_tools:
                    result = f"Error: tool '{fn_name}' временно заблокирован после ошибки."
                    warn(f"Blocked tool {fn_name} skipped")
                else:
                    sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
                    if sig == last_tool_signature:
                        repeat_count += 1
                        if repeat_count >= 2:
                            warn(f"Same tool call repeated {repeat_count} times, stopping")
                            fallback = "Зациклился на одном действии. Попробуй переформулировать задачу."
                            await manager.send_personal_message(
                                json.dumps({"type": "message", "content": fallback}),
                                websocket,
                            )
                            await asyncio.to_thread(memory.save_interaction, task, fallback)
                            await manager.send_personal_message(
                                json.dumps({"type": "status", "content": "idle"}), websocket
                            )
                            return
                    else:
                        last_tool_signature = sig
                        repeat_count = 0

                    args_summary = " ".join(f"{k}={v!r}" for k, v in fn_args.items())
                    agent(f"[{iteration}] 🛠 {fn_name}({args_summary})")
                    result = await asyncio.to_thread(registry.execute, fn_name, fn_args)

                result_preview = result[:120].replace("\n", " ") if result else "(empty)"
                if len(result) > 120:
                    result_preview += "..."
                agent(f"[{iteration}] ✅ → {result_preview}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result,
                })
                await asyncio.to_thread(session_log.append, fn_name, result)

                # Защита: блокировать tool после ошибки
                if isinstance(result, str) and result.startswith("Error:"):
                    blocked_tools.add(fn_name)
                    recent_errors += 1
                    if recent_errors >= 3:
                        warn("3 errors in a row, stopping loop")
                        fallback = "Не получается выполнить действие. Переформулируй задачу."
                        await manager.send_personal_message(
                            json.dumps({"type": "message", "content": fallback}),
                            websocket,
                        )
                        await asyncio.to_thread(memory.save_interaction, task, fallback)
                        await manager.send_personal_message(
                            json.dumps({"type": "status", "content": "idle"}), websocket
                        )
                        return
                else:
                    recent_errors = 0

        else:
            # Max iterations reached
            fallback = "Достигнут лимит итераций инструментов."
            await manager.send_personal_message(
                json.dumps({"type": "message", "content": fallback}),
                websocket,
            )
            await asyncio.to_thread(memory.save_interaction, task, fallback)

    except Exception as e:
        error(f"ERROR: {e}\n{traceback.format_exc()}")
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
