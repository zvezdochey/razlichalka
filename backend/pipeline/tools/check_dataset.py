"""Проверка правил массивов на настоящем датасете.

Запуск (из папки backend/):  python -m pipeline.tools.check_dataset <папка_датасета>
Прогоняет flatten_response по всем *.json и печатает сводку: файлы, строки,
листья на заявку (min/median/max), ошибки «нет правила»/«дубль ключа», число разных PATH.
"""

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from pipeline.array_rules import default_array_rules
from pipeline.errors import BadFile
from pipeline.flatten import flatten_response


def main(dataset_dir: Path) -> int:
    files = sorted(dataset_dir.rglob("*.json"))
    if not files:
        print(f"В {dataset_dir} нет *.json")
        return 1

    rules = default_array_rules()
    leaves: list[int] = []
    paths: set[str] = set()
    dup_keys = 0
    errors: Counter = Counter()
    examples: dict[str, str] = {}

    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            # как в прогоне без конфигурации: встроенные правила, не подошедшие к данным, откатываются на умолчание
            rows = flatten_response(doc, f.stem, "BEFORE", rules, soft_paths=rules)
        except BadFile as e:
            kind = "нет правила" if "нет правила" in e.message else "дубль ключа" if "дубль" in e.message else "другое"
            errors[kind] += 1
            examples.setdefault(kind, f"{f.name}: {e.message}")
            continue
        except (OSError, ValueError) as e:  # битый JSON / нечитаемый файл
            errors["битый файл"] += 1
            examples.setdefault("битый файл", f"{f.name}: {e}")
            continue
        leaves.append(len(rows))
        paths.update(r["PATH"] for r in rows)
        # ключ строки (APP_ID, PATH, ARRAY_KEY) должен быть уникален
        keys = Counter((r["APP_ID"], r["PATH"], r["ARRAY_KEY"]) for r in rows)
        dup_keys += sum(1 for c in keys.values() if c > 1)

    print(f"Файлов: {len(files)} (разобрано {len(leaves)})")
    print(f"Строк всего: {sum(leaves)}")
    if leaves:
        print(f"Листьев на заявку: min {min(leaves)}, median {int(statistics.median(leaves))}, max {max(leaves)}")
    print(f"Разных PATH: {len(paths)}")
    print(f"Повторов (APP_ID, PATH, ARRAY_KEY): {dup_keys}")
    print(f"Ошибок: {sum(errors.values())}")
    for kind, n in errors.items():
        print(f"  {kind}: {n}  (пример: {examples[kind]})")
    return 0 if not errors and not dup_keys else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # чтобы русский текст не ломался в консоли Windows
    if len(sys.argv) != 2:
        print("Использование: python -m pipeline.tools.check_dataset <папка_датасета>")
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
