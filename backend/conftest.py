# pytest добавляет папку backend/ в sys.path, и тесты видят `import pipeline`.
import pytest

from app import settings


@pytest.fixture(autouse=True)
def _no_ollama_key(monkeypatch):
    """Ключ из окружения (Docker/.env) не должен уводить тесты в сеть: «Мнение ИИ» без ключа сразу «недоступно»."""
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "")
