"""Настройки бэка. Читаем переменные окружения (CONTRACTS §3), по умолчанию — для локального запуска."""
import os
from pathlib import Path

# backend/app/settings.py -> корень репозитория на два уровня выше папки backend
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
STUB_RUN_DIR = BACKEND_DIR / "tests" / "fixtures" / "run_mini"

# Папка с датасетами (только читаем)
DATASETS_DIR = Path(os.environ.get("DATASETS_DIR", REPO_DIR / "ПАКЕТ" / "ЗАДАНИЕ" / "data"))
# Папка, куда пишет бэк: конфигурации, запуски, результаты
DATA_DIR = Path(os.environ.get("DATA_DIR", BACKEND_DIR / "var"))

# Адреса dev-серверов фронта
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

# Пока настоящий пайплайн (S5) не подключён, этапы — заглушки с sleep
USE_STUB_PIPELINE = os.environ.get("USE_STUB_PIPELINE", "1") == "1"
