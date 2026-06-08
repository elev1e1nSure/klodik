🇬🇧 [English version](README.md)

# 🤖 Клодик

[![Tauri](https://img.shields.io/badge/Tauri-v2-24C8DB?logo=tauri)](https://tauri.app)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6?logo=typescript)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?logo=tailwindcss)](https://tailwindcss.com)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python)](https://python.org)
[![Groq](https://img.shields.io/badge/Groq-API-F55036?logo=openai)](https://groq.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Твой компаньон на рабочем столе.** Клодик — пиксельный ИИ-агент, который живёт прямо на экране, разговаривает с тобой по-русски и реально делает всякое — открывает программы, печатает текст, гуглит, двигает мышкой и запоминает твои привычки.

<p align="center">
  <img src="public/app-icon.png" width="128" alt="Спрайт Клодика">
</p>

---

## ✨ Возможности

| Фича | Описание |
|---------|-------------|
| 🎮 **Оверлей** | Прозрачное окно без рамок поверх всех окон. Тяни куда хочешь |
| 🔧 **Инструменты** | 15+ тулов: терминал, файлы, мышь, клавиатура, браузер, поиск |
| 🧠 **Мультимодельность** | Groq, OpenAI, Gemini, Ollama — выбирай провайдера |
| 📝 **Память** | SQLite база помнит последние разговоры и предпочтения |
| 🎬 **Анимации** | Lottie анимация во время работы, пиксель-арт в покое |
| 🪟 **Панель задач** | Виден в таскбаре — легко найти и переключиться |
| 💬 **Инициатива** | Скучает и сам начинает разговор после 60 секунд молчания |

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────┐
│  Tauri Window (прозрачный оверлей)   │
│  ┌─────────────────────────────┐    │
│  │  React 19 + Tailwind v4    │    │
│  │  ├── Agent.tsx (спрайт)    │    │
│  │  ├── useWebSocket.ts       │    │
│  │  └── ErrorBoundary.tsx      │    │
│  └─────────────────────────────┘    │
└──────────────┬────────────────────────┘
               │ WebSocket  ws://localhost:8765
               ▼
┌─────────────────────────────────────┐
│  Python Sidecar (FastAPI + uvicorn) │
│  ├── WebSocket /ws                  │
│  │   └── agent_loop()              │
│  │       ├── LLM (litellm)         │
│  │       ├── SQLite Memory         │
│  │       └── 15+ инструментов      │
│  ├── connection.py (WS manager)     │
│  ├── log.py (цветной лог)           │
│  └── /health                        │
└─────────────────────────────────────┘
               │
               ▼ HTTPS
        ┌──────────────┐
        │  Groq Cloud  │
        │  70B параметров│
        └──────────────┘
```

---

<p align="center">
  <img src="screenshots/klodik-idle.png" width="320" alt="Клодик в покое">
</p>

---

## 🚀 Быстрый старт

### Требования
- [Node.js](https://nodejs.org/) + [pnpm](https://pnpm.io/)
- [Python 3.12+](https://python.org)
- [Rust](https://rustup.rs/) (для Tauri)
- Windows 10+ / macOS 12+ / Linux с X11/Wayland (для pyautogui)

### Установка

```bash
# Клонировать
git clone https://github.com/elev1e1nSure/klodik.git
cd klodik

# JS зависимости
pnpm install

# Python venv + зависимости
python -m venv sidecar\.venv
sidecar\.venv\Scripts\pip install -r sidecar\requirements.txt

# Создать .env (обязательно!)
copy .env.example sidecar\.env
# Отредактировать sidecar\.env и вставить свой GROQ_API_KEY
```

### Запуск

```bash
# Красивый лаунчер с выбором модели и провайдера
pnpm launch

# Или классический запуск
pnpm dev:all
```

Или отдельно:
```bash
# Терминал 1
sidecar\.venv\Scripts\python.exe sidecar\main.py

# Терминал 2
pnpm tauri dev
```

---

## 🛠️ Инструменты

Агент умеет выполнять реальные действия на компьютере:

| Инструмент | Что делает |
|------|-------------|
| `terminal` | Запускать shell-команды |
| `read_file` / `write_file` | Работа с файлами |
| `mkdir` / `list_dir` | Управление папками |
| `search` | Поиск файлов по имени или содержимому |
| `move_file` | Перемещать/переименовывать |
| `move_mouse` / `click` | Управлять курсором |
| `type_text` / `press_key` | Ввод с клавиатуры |
| `open_app` | Запускать программы |
| `open_url` | Открывать ссылки в браузере |
| `google` | Искать в Google и возвращать результаты |
| `read_url` | Читать содержимое страниц |

---

## 🧠 Память

Разговоры хранятся в `sidecar/memory.db` (SQLite). Агент подгружает последние 5 взаимодействий перед каждой задачей, чтобы помнить контекст и предпочтения.

---

## 📁 Структура проекта

```
klodik/
├── src/               # React фронтенд
├── src-tauri/         # Tauri (Rust) — оболочка
├── sidecar/           # Python бэкенд (FastAPI + агент)
│   ├── connection.py  # WebSocket менеджер соединений
│   ├── log.py         # Структурированный цветной логгер
│   └── tools/         # Реестр и реализация тулов
├── scripts/           # dev.cjs — единый скрипт запуска
├── public/            # Спрайты и ассеты
└── AGENTS.md          # Правила и конвенции проекта
```

---

## 🧠 Провайдеры и модели

| Провайдер | Модели | Требуется ключ |
|-----------|--------|---------------|
| ⚡ **Groq** | llama-3.3-70b, mixtral, gemma2 | Да ([console.groq.com](https://console.groq.com/keys)) |
| 🌐 **OpenAI** | gpt-4o, gpt-4o-mini, gpt-4-turbo | Да ([platform.openai.com](https://platform.openai.com/api-keys)) |
| 💎 **Gemini** | gemini-1.5-pro, gemini-1.5-flash | Да ([aistudio.google.com](https://aistudio.google.com/app/apikey)) |
| 🦙 **Ollama** | llama3, mistral, codellama и др. | Нет (локально) |

Выбор провайдера через `pnpm launch` или в `.env` (`PROVIDER=...`).

## 🩹 Troubleshooting

| Проблема | Решение |
|---------|---------|
| `GROQ_API_KEY not set` | Скопируй `.env.example` в `sidecar\.env`, вставь ключ из [console.groq.com](https://console.groq.com/keys) |
| Порт 8765 занят | Измени `WS_PORT` в `.env` или убей процесс на 8765 |
| `pyautogui not installed` | Установи зависимости: `pip install -r sidecar\requirements.txt` |
| macOS: pyautogui не работает | System Preferences → Security → Accessibility → добавь Python/терминал |
| Окно не перетаскивается | Убедись, что `data-tauri-drag-region` на корневом div |

## 📜 Лицензия

MIT

