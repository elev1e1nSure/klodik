# Claude Agent — Правила проекта

## 1. Суть и концепция

**Claude Agent** — десктопный оверлей-агент (пиксельный персонаж), который живёт прямо на рабочем столе Windows. Пользователь перетаскивает агента по экрану, задаёт задачи в текстовом поле над головой, агент выполняет их через локальную LLM (Ollama + LiteLLM) с tool calling.

Окно приложения: прозрачное, без рамок, поверх всех окон (`alwaysOnTop`), не отображается в таскбаре (`skipTaskbar`). Размер ~320×240 пикселей. Перетаскивание — через `data-tauri-drag-region`.

## 2. Стек

| Слой | Технологии |
|------|-----------|
| Desktop shell | Tauri v2 (Rust) |
| UI | React 19 + TypeScript + Tailwind CSS v4 |
| Коммуникация | WebSocket (фронт ↔ sidecar) |
| Sidecar | Python 3.12+, FastAPI, Uvicorn |
| LLM | LiteLLM → Ollama (локальная модель, по умолчанию `llama3.2`) |
| Менеджер зависимостей JS | pnpm |
| Менеджер зависимостей Python | uv |

## 3. Архитектура

```
┌─────────────────────────────────────┐
│  Tauri Window (transparent overlay) │
│  ┌─────────────────────────────┐  │
│  │  React App                   │  │
│  │  ├── Agent.tsx (спрайт, UI) │  │
│  │  └── useWebSocket.ts (WS)    │  │
│  └─────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │ WebSocket  ws://localhost:8765/ws
               ▼
┌─────────────────────────────────────┐
│  Python Sidecar (FastAPI + uvicorn)│
│  ├── /health                        │
│  ├── /ws  (WebSocket endpoint)      │
│  │   └── agent_loop()               │
│  │       ├── litellm.completion()    │
│  │       └── execute_tool()         │
│  └── TOOLS: terminal, read_file,   │
│      write_file, search, run_script │
└─────────────────────────────────────┘
               │
               ▼ HTTP  localhost:11434
        ┌──────────────┐
        │  Ollama      │
        │  (локально)  │
        └──────────────┘
```

### Поток данных при задаче

1. Пользователь пишет задачу в `textarea` → нажимает Send (или Enter)
2. `useWebSocket` отправляет JSON: `{"type":"task","content":"..."}`
3. Sidecar получает задачу → `agent_loop()`
4. `agent_loop` отправляет статус `thinking` → вызывает `litellm.completion()`
5. Если LLM хочет вызвать tool → статус `working` → `execute_tool()` → результат обратно в LLM
6. Максимум 5 итераций tool calling (`MAX_TOOL_ITERATIONS`)
7. Финальный ответ LLM отправляется как `{"type":"message"}` → статус `idle`

## 4. Структура директорий

```
claude-agent/
├── src/                          # Frontend (React + TS)
│   ├── components/
│   │   └── Agent.tsx             # Главный компонент: спрайт, textarea, статус
│   ├── hooks/
│   │   └── useWebSocket.ts       # Хук для WS-соединения
│   ├── test/
│   │   └── setup.ts              # setup для vitest
│   ├── App.tsx                   # Корневой компонент
│   ├── main.tsx                  # Точка входа React
│   └── index.css                 # Tailwind + кастомные keyframes
├── src-tauri/                    # Tauri (Rust)
│   ├── Cargo.toml
│   ├── tauri.conf.json           # Конфиг окна: transparent, undecorated, alwaysOnTop
│   ├── capabilities/
│   │   └── default.json          # Permissions: window drag, position, etc.
│   └── src/
│       └── main.rs               # Rust entrypoint (генерированный Tauri)
├── sidecar/                      # Python sidecar
│   ├── requirements.txt          # Python-зависимости
│   ├── main.py                   # FastAPI app + agent loop
│   └── tests/
│       └── test_main.py          # Тесты sidecar (pytest)
├── public/
│   └── claude.svg                # Пиксельный спрайт агента
├── PLAN.md                       # План разработки (фазы)
├── AGENTS.md                     # Этот файл
├── package.json                  # JS-зависимости
├── vitest.config.ts              # Конфиг фронтенд-тестов
└── vite.config.ts               # Vite config (host: 127.0.0.1)
```

## 5. Конвенции

### Нейминг
- **Всегда английский** в коде (переменные, функции, файлы, коммиты)
- React компоненты: `PascalCase.tsx`
- Хуки: `camelCase.ts`, префикс `use`
- Тесты: рядом с исходником, суффикс `.test.ts` / `.test.tsx`
- Python: `snake_case.py`, классы `PascalCase`

### Code style
- TypeScript: строгие типы, без `any` (если можно избежать)
- React: функциональные компоненты, хуки
- CSS: Tailwind utility-first, кастомные анимации через `@keyframes` в `index.css`
- Python: type hints (`dict[str, Any]`, `list[...]`), docstrings для функций
- Никаких hardcoded secrets / API keys

### Коммиты
- Формат: `type(scope): message` (Conventional Commits)
- Примеры:
  - `feat(sidecar): add search tool with os.walk`
  - `fix(agent): remove invalid shadow field from tauri config`
  - `test(ws): add useWebSocket hook tests`
- **Каждый коммит должен проходить тесты** (sidecar + frontend)

## 6. Тестирование (обязательно)

### Python sidecar (`sidecar/tests/`)
Запуск: `cd sidecar && uv run pytest tests/`

**Что тестировать:**
- `health` endpoint
- WebSocket lifecycle (connect, disconnect, invalid JSON)
- `agent_loop` — статусы `thinking` → `idle` при задаче
- Каждый `execute_tool`:
  - `terminal` (echo + error exit code)
  - `read_file` (чтение temp-файла)
  - `write_file` (запись + проверка содержимого)
  - `search` (by name + by content)
  - `unknown tool` (fallback)

### Frontend (`src/**/*.test.ts{x}`)
Запуск: `pnpm test`

**Что тестировать:**
- `useWebSocket`: подключение, получение статусов, получение сообщений, `sendTask`
- `Agent`: рендер, ввод текста, клик Send, Enter-отправка, блокировка пустого ввода, рендер спрайта
- Новые компоненты — минимум smoke test

**Правило: нет тестов → нет коммита.**

## 7. Sidecar правила

- `main.py` — единственный файл приложения. Если растёт >500 строк — рефакторить на модули (`tools.py`, `agent.py`)
- `execute_tool` — **всегда** возвращает `str`, даже при ошибке (`f"Error: {e}"`)
- `agent_loop` — **никогда** не блокирует event loop (все вызовы `completion()` — через sync в async, или `asyncio.to_thread` если нужно)
- `search` tool — кроссплатформенный (`os.walk` + `fnmatch`, никаких `grep`/`find` на Windows)
- `write_file` — создаёт промежуточные директории через `os.makedirs`
- `tool_calls` в `messages.append` — добавлять **только если они есть** (не `None`)

## 8. Frontend правила

- `Agent.tsx` — единственный визуальный компонент. Остальное — хуки и утилиты.
- `data-tauri-drag-region` — на корневом div для drag окна
- `data-tauri-no-drag` — на форму (textarea, button), чтобы не перетаскивать при вводе текста
- Анимации — CSS keyframes, **не** Tailwind utilities (`animate-bounce`, `animate-pulse` — запрещены для спрайта)
- Классы анимаций: `animate-agent-idle`, `animate-agent-thinking`, `animate-agent-working`, `animate-agent-success`, `animate-agent-error`
- WebSocket URL: `ws://localhost:8765/ws` (не `127.0.0.1` — для consistency)
- Все импорты React — через `from "react"` (не `React.*`)

## 9. Tauri / Rust правила

- `tauri.conf.json` — валидировать после любого изменения (схема может отвергать поля)
- Запрещённые поля (не поддерживаются v2): `shadow`
- `capabilities/default.json` — добавлять permissions при необходимости (window API)
- Cargo.toml: feature `window-effects` для прозрачных окон

## 10. Зависимости и окружение

### Установка
```powershell
# JS
pnpm install

# Python
uv venv sidecar\.venv
uv pip install -r sidecar\requirements.txt --python sidecar\.venv\Scripts\python.exe
```

### Запуск dev
```powershell
# Terminal 1: sidecar
sidecar\.venv\Scripts\python.exe sidecar\main.py

# Terminal 2: frontend
pnpm tauri dev
```

### Предусловия
- Ollama установлен и запущен на `localhost:11434`
- Модель `llama3.2` (или та, что в `MODEL = "ollama/..."`) скачана: `ollama pull llama3.2`

## 11. Что коммитить / не коммитить

### Коммитить
- Исходный код (`src/`, `src-tauri/`, `sidecar/`)
- Тесты (`*.test.ts`, `sidecar/tests/`)
- Конфиги (`vite.config.ts`, `vitest.config.ts`, `postcss.config.mjs`, `tsconfig.json`)
- `PLAN.md`, `AGENTS.md`, `requirements.txt`, `package.json`
- `public/claude.svg` (спрайт)

### НЕ коммитить
- `node_modules/`, `.venv/`, `target/` (Rust build)
- `dist/`, `build/`
- `.env` с секретами (хотя секретов и нет — всё локально)
- Логи, `.log`
- IDE-специфичные файлы (`.idea/`, `.vscode/` — если не shared config)

## 12. Работа с AI-моделью

- Модель: `ollama/llama3.2` (или другая, доступная в Ollama)
- LiteLLM выступает адаптером: единый API для любой модели
- `api_base` указывает на `http://localhost:11434`
- Tool calling — через OpenAI-compatible формат (`tools` / `tool_calls`)
- Если модель не поддерживает tool calling — агент будет просто отвечать текстом (fallback)
- `MAX_TOOL_ITERATIONS = 5` — защита от бесконечных циклов

## 13. Дорожная карта (из PLAN.md)

| Фаза | Статус | Описание |
|------|--------|----------|
| 1 | ✅ | Инициализация проекта и подготовка среды |
| 2 | ✅ | Overlay-окно на реальном рабочем столе |
| 3 | ✅ | UI текстового поля и статус |
| 4 | ✅ | Агентный луп и tool calling |
| 5 | ✅ | Анимации и полировка |

---

*Последнее обновление: 2026-06-08*
