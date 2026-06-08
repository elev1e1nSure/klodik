# Changelog

## [0.1.0] - 2026-06-08

### Security
- Убран хардкод `GROQ_API_KEY` из исходников. Ключ теперь загружается из `.env` через `pydantic-settings` с валидацией.
- Добавлен `.env.example` и инструкция по настройке.

### Multi-Provider LLM Support
- **litellm** — единый интерфейс для Groq, OpenAI, Gemini, Ollama.
- `sidecar/config.py` — динамическая валидация ключа в зависимости от `PROVIDER`.
- `scripts/launch.py` — красивый интерактивный лаунчер (Rich) с выбором провайдера и модели.
- Поддержка **Ollama** — автоопределение локальных моделей через `localhost:11434/api/tags`.

### Architecture
- **Sidecar разбит на модули**: `config`, `memory`, `agent`, `server`, `tools/*`.
- Внедрён `ToolRegistry` с декоратором `@tool` вместо монолитного `if-elif`.
- Инструменты разделены по категориям: `file_tools`, `system_tools`, `web_tools`, `input_tools`.

### Cross-platform
- `open_app` / `open_url` / `run_script` теперь поддерживают Windows, macOS и Linux.
- `run_script` использует `sys.executable` вместо хардкода `python`.

### Reliability
- **Frontend**: auto-reconnect WebSocket с exponential backoff (max 5 попыток).
- **Frontend**: обработка `error`-сообщений из sidecar, отображение в пузыре.
- **Agent**: защита от malformed JSON в `tool_call.arguments` — отправляется `error` и цикл продолжается.
- **Agent**: max iterations теперь сохраняет fallback в `Memory`.
- **ConnectionManager**: `disconnect` не падает при отсутствующем websocket; `send_personal_message` проверяет состояние соединения.
- **File tools**: валидация путей, ограничение размера файла (5MB), ограничение глубины поиска (10), защита от системных директорий.

### Frontend
- Исправлен рендер `thinking` vs `working`: thinking — статичный спрайт с анимацией, working — Lottie.
- Добавлен `aria-live="polite"` для accessibility.
- Добавлен `title` на кнопку отправки с понятными подсказками.

### Rust
- Удалён scaffold-команд `greet` из `lib.rs`.
- Удалено запрещённое поле `shadow` из `tauri.conf.json` (Tauri v2).

### Tests
- Sidecar: 34 теста (все проходят).
- Frontend: 18 тестов (все проходят).

### Docs
- Актуализированы `AGENTS.md`, `README.md`, `README.ru.md`.
- Добавлен раздел Troubleshooting.
- Добавлен `CHANGELOG.md`.
