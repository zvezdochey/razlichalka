from fastapi import Request


def current_user(request: Request) -> str:
    """Имя пользователя из заголовка X-User; без заголовка — anonymous."""
    return request.headers.get("X-User") or "anonymous"
