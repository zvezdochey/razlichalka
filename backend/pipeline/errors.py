"""Ошибки конвейера (CONTRACTS §4). `app` превращает их в {"error": {"code", "message"}}."""


class PipelineError(Exception):
    """Базовая ошибка конвейера: машинный `code` и понятный человеку `message`."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BadFile(PipelineError):
    """Файл не разобрать или он не подходит под правила (нет правила для массива, дубль ключа...)."""

    def __init__(self, message: str):
        super().__init__("bad_file", message)


class Cancelled(PipelineError):
    """Пользователь нажал «Стоп»."""

    def __init__(self, message: str = "Запуск остановлен пользователем"):
        super().__init__("cancelled", message)
