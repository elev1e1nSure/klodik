# Клодик — Правила проекта

## 1. Суть и концепция

**Клодик** — десктопный оверлей-агент (пиксельный персонаж), живущий прямо на рабочем столе Windows. Пользователь перетаскивает агента, задаёт задачи в текстовом поле, агент выполняет их через LLM с tool calling.

Окно: прозрачное, без рамок, поверх всех окон (`alwaysOnTop`), не в таскбаре (`skipTaskbar`), квадратное 320×320 px. Перетаскивание через `data-tauri-drag-region`.

Агент отвечает **строго по-русски**, кратко (1–2 предложения), в стиле живого собеседника в мессенджере. Умеет инициировать разговор сам.

---

## 2. Стек

| Слой | Технологии |
|------|-----------|
| Desktop shell | Tauri v2 (Rust) |
| UI | React 19 + TypeScript + Tailwind CSS v4 |
| Коммуникация | WebSocket (фронт ↔ sidecar) |
| Sidecar | Python 3.12+, FastAPI, Uvicorn |
| LLM | Groq, OpenAI, Gemini, Ollama (via litellm) |
| Память | SQLite (`sidecar/memory.db`) |
| Менеджер зависимостей JS | pnpm |
| Менеджер зависимостей Python | pip |

---

## 3. Архитектура

```
┌─────────────────────────────────────┐
│  Tauri Window (transparent overlay)   │
│  ┌─────────────────────────────┐    │
│  │  React App                   │    │
│  │  ├── Agent.tsx (спрайт, UI)  │    │
│  │  └── useWebSocket.ts (WS)    │    │
│  └─────────────────────────────┘    │
└──────────────┬────────────────────────┘
               │ WebSocket  ws://localhost:8765/ws
               ▼
┌─────────────────────────────────────┐
│  Python Sidecar (FastAPI + uvicorn) │
│  ├── /health                        │
│  ├── /ws  (WebSocket endpoint)      │
│  │   └── agent_loop()              │
│  │       ├── litellm completion     │
│  │       ├── Memory (SQLite)        │
│  │       └── execute_tool()         │
│  ├── connection.py (WebSocket mgr)  │
│  ├── log.py (colored logging)       │
│  └── TOOLS: terminal, read_file,   │
│      write_file, search, mkdir,      │
│      list_dir, move_file, move_mouse,│
│      click, open_app, open_url,      │
│      google, read_url, type_text,    │
│      press_key                       │
└─────────────────────────────────────┘
               │
               ▼ HTTPS  api.groq.com
        ┌──────────────┐
        │  Groq Cloud  │
        │  llama-3.3-70b│
        └──────────────┘
```

### Поток данных

1. Пользователь пишет в `textarea` → Enter/Send
2. `useWebSocket` отправляет JSON: `{"type":"task","content":"..."}`
3. Sidecar получает задачу → `agent_loop()`
4. Sidecar загружает последние 5 взаимодействий из `Memory`
5. Отправляет статус `thinking` → вызывает Groq API с `tools`
6. Если LLM вызывает tool → статус `working` → `execute_tool()` → результат обратно
7. Максимум 5 итераций (`MAX_TOOL_ITERATIONS`)
8. Финальный ответ → `{"type":"message"}` → сохраняется в `Memory` → статус `idle`

### Инициатива

Фоновая задача (`initiative_loop`) раз в 60 секунд проверяет бездействие. Если пользователь молчит >60 сек — агент сам пишет случайное приветствие.

---

## 4. Структура директорий

```
klodik/
├── src/                          # Frontend (React + TS)
│   ├── components/
│   │   ├── Agent.tsx             # Главный компонент: спрайт, input, bubble
│   │   ├── Agent.test.tsx        # Тесты Agent
│   │   └── ErrorBoundary.tsx     # Обработка ошибок React
│   ├── hooks/
│   │   ├── useWebSocket.ts       # Хук для WS-соединения
│   │   └── useWebSocket.test.ts  # Тесты WS
│   ├── test/
│   │   └── setup.ts              # setup для vitest
│   ├── App.tsx                   # Корневой компонент
│   ├── main.tsx                  # Точка входа React
│   └── index.css                 # Tailwind + кастомные keyframes
├── src-tauri/                    # Tauri (Rust)
│   ├── Cargo.toml
│   ├── tauri.conf.json           # Конфиг окна: transparent, undecorated, alwaysOnTop, 320×320
│   ├── capabilities/
│   │   └── default.json          # Permissions
│   └── src/
│       └── main.rs               # Rust entrypoint
├── sidecar/                      # Python sidecar
│   ├── requirements.txt          # Python-зависимости
│   ├── .env                      # API-ключи и настройки (не коммитить)
│   ├── config.py                 # Pydantic Settings (GROQ_API_KEY, MODEL, ...)
│   ├── main.py                   # Entry point (uvicorn)
│   ├── server.py                 # FastAPI app + WebSocket endpoint
│   ├── connection.py             # ConnectionManager (разрыв цикла server↔agent)
│   ├── agent.py                  # Agent loop + initiative_loop
│   ├── memory.py                 # SQLite Memory
│   ├── log.py                    # Структурированный цветной логгер
│   ├── tools/
│   │   ├── __init__.py           # Auto-discovery
│   │   ├── base.py               # Tool decorators
│   │   ├── registry.py           # ToolRegistry
│   │   ├── file_tools.py         # read/write/search/mkdir/list/move
│   │   ├── system_tools.py       # terminal/open_app/open_url/run_script
│   │   ├── web_tools.py          # google/read_url
│   │   └── input_tools.py        # mouse/keyboard (pyautogui)
│   └── tests/
│       ├── conftest.py           # Dummy GROQ_API_KEY для pytest
│       └── test_main.py          # Тесты sidecar
├── scripts/
│   ├── dev.cjs                   # Единый скрипт запуска sidecar + tauri
│   └── launch.py                 # Красивый лаунчер с выбором провайдера и модели
├── public/
│   ├── claude.png                # Статичный спрайт
│   └── claude_animated.lottie   # Анимированный спрайт
├── AGENTS.md                     # Этот файл
├── README.md                     # Описание проекта (EN)
├── README.ru.md                  # Описание проекта (RU)
├── package.json                  # JS-зависимости
├── vitest.config.ts              # Конфиг фронтенд-тестов
└── vite.config.ts                # Vite config
```

---

## 5. Конвенции

### Нейминг
- **Английский** в коде (переменные, функции, файлы, коммиты)
- React компоненты: `PascalCase.tsx`
- Хуки: `camelCase.ts`, префикс `use`
- Тесты: рядом с исходником, суффикс `.test.ts` / `.test.tsx`
- Python: `snake_case.py`, классы `PascalCase`

### Code style
- TypeScript: строгие типы, без `any`
- React: функциональные компоненты, хуки
- CSS: Tailwind utility-first, кастомные анимации через `@keyframes`
- Python: type hints, docstrings

### Коммиты
- Формат: `type(scope): message` (Conventional Commits)
- Примеры:
  - `feat(sidecar): add google search tool`
  - `fix(agent): fix websocket disconnect handling`

---

## 6. Тестирование

### Python sidecar
Запуск: `cd sidecar && python -m pytest tests/`

### Frontend
Запуск: `pnpm test`

---

## 7. Sidecar правила

- `execute_tool` — **всегда** возвращает `str`, даже при ошибке
- `agent_loop` — **никогда** не блокирует event loop (все sync вызовы через `asyncio.to_thread`)
- `search` tool — кроссплатформенный (`os.walk` + `fnmatch`)
- `write_file` — создаёт промежуточные директории через `os.makedirs`
- `tool_calls` в `messages.append` — добавлять **только если они есть**
- `Memory.save_interaction()` — вызывать после финального ответа

---

## 8. Frontend правила

- `Agent.tsx` — единственный визуальный компонент
- `ErrorBoundary.tsx` — обработка ошибок React
- `data-tauri-drag-region` — на корневом div для drag окна
- `data-tauri-no-drag` — на input/form
- WebSocket URL: `ws://localhost:8765/ws`
- Импорты React — через `from "react"`
- Ответный пузырь: появляется над input, плавно исчезает через N секунд
- Placeholder и сообщения ошибок — на русском

---

## 9. Tauri / Rust правила

- `tauri.conf.json` — валидировать после изменений
- Окно: `transparent`, `decorations: false`, `skipTaskbar: true`, `alwaysOnTop: true`
- Поле `shadow` запрещено в Tauri v2 — не использовать
- **Удаление border/shadow на Windows** — делается через Win32 API в `setup` хуке `lib.rs`:
  - `SetWindowLongPtrW(GWL_STYLE)` — убирает `WS_BORDER/WS_DLGFRAME/WS_THICKFRAME`, оставляет `WS_POPUP`
  - `SetWindowLongPtrW(GWL_EXSTYLE)` — добавляет `WS_EX_TOOLWINDOW`
  - `DwmSetWindowAttribute(DWMWA_NCRENDERING_POLICY = DWMNCRP_DISABLED)` — отключает DWM rendering
  - `DwmSetWindowAttribute(DWMWA_BORDER_COLOR = DWMWA_COLOR_NONE)` — убирает accent border
  - `DwmSetWindowAttribute(DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_DONOTROUND)` — убирает закругление
  - `SetWindowPos(SWP_FRAMECHANGED)` — форсирует пересчёт рамки
- **НЕЛЬЗЯ** возвращать `shadow` или любой другой border в конфиг или код

---

## 10. Зависимости и окружение

### Установка
```powershell
# JS
pnpm install

# Python
python -m venv sidecar\.venv
sidecar\.venv\Scripts\pip install -r sidecar\requirements.txt

# Создать .env (скопировать из .env.example)
copy .env.example sidecar\.env
```

### Запуск dev
```powershell
# Красивый лаунчер с выбором провайдера и модели
python scripts/launch.py

# Или через pnpm
pnpm launch

# Классический единый скрипт
pnpm dev:all
```

### Кроссплатформенность
- `open_app` / `open_url` адаптируются под Windows (`start`), macOS (`open`), Linux (`xdg-open`)
- `run_script` использует `sys.executable` вместо хардкода `python`
- `pyautogui` требует доступ к экрану на macOS (System Preferences → Security)

---

## 11. Что коммитить / не коммитить

### Коммитить
- Исходный код (`src/`, `src-tauri/`, `sidecar/`)
- Тесты, конфиги, `AGENTS.md`, `README.md`
- `public/claude.svg`, `public/claude_animated.lottie`

### НЕ коммитить
- `node_modules/`, `.venv/`, `target/`, `dist/`, `build/`
- `.env`, логи, IDE-файлы (кроме shared `.vscode/`)
- `sidecar/memory.db`

---

## 12. Работа с AI-моделью

Sidecar использует **litellm** — единый интерфейс для множества провайдеров.

| Провайдер | Формат модели | Ключ |
|-----------|--------------|------|
| Groq | `groq/llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| OpenAI | `gpt-4o` | `OPENAI_API_KEY` |
| Gemini | `gemini/gemini-1.5-pro` | `GEMINI_API_KEY` |
| Ollama | `ollama/llama3` | не нужен |

- **Tool calling**: OpenAI-compatible формат (`tools` / `tool_calls`) — поддерживается Groq, OpenAI, Gemini; для Ollama ограничена
- **Temperature**: 0.7
- **Max tokens**: 512 (краткие ответы)
- **Промпт**: строго русский, живой стиль, 1–2 предложения, без корпоративщины
- **MAX_TOOL_ITERATIONS = 5**
- **Fallback**: если tool calling не сработал — просто текстовый ответ

---

*Последнее обновление: 2026-06-08 (рефакторинг)*
