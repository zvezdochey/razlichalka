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

# Встроенные процедуры — файлы с правилами разбора; этапы передают эту папку в pipeline (services/stages.py)
PROCEDURES_DIR = Path(os.environ.get("PROCEDURES_DIR", BACKEND_DIR / "procedures"))

# Адреса dev-серверов фронта
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

# По умолчанию считает настоящий пайплайн; USE_STUB_PIPELINE=1 — заглушки с sleep (тесты, разработка фронта)
USE_STUB_PIPELINE = os.environ.get("USE_STUB_PIPELINE", "0") == "1"
