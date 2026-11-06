"""Приведение всего среза в один CSV: 2002 JSON-файла -> normalized_<СРЕЗ>.csv (CONTRACTS §2.1, §4).

CLI для себя (из папки backend/):
    python -m pipeline.normalize <папка_датасета> <BEFORE|AFTER> <out.csv>
"""

import json
import sys
import time
from pathlib import Path

from .array_rules import DEFAULT_ARRAY_RULES, merge_array_rules
from .csvio import write_csv
from .dataset import list_source_files
from .errors import BadFile, Cancelled
from .flatten import COLUMNS, flatten_response

PROGRESS_EVERY = 50


def normalize_dataset(dataset_dir: Path, source: str, out_csv: Path, parse_cfg: dict,
                      on_progress=None, log=None, is_cancelled=None) -> int:
    """source = "BEFORE" | "AFTER". Возвращает число записанных строк."""
    parse_cfg = parse_cfg or {}
    files = list_source_files(dataset_dir, source)
    total = len(files)
    rules = merge_array_rules(DEFAULT_ARRAY_RULES, parse_cfg.get("array_modes") or {})
    ignore_paths = parse_cfg.get("ignore_paths") or []
    adjust = None
    if parse_cfg.get("buckets"):
        try:  # E4 может быть ещё не слита — тогда бакетизации нет (ADJUSTED_VALUE = VALUE)
            from .buckets import make_adjuster
            adjust = make_adjuster(parse_cfg["buckets"])
        except ImportError:
            adjust = None

    def say(level: str, message: str) -> None:
        if log:
            log(level, message)

    def rows():
        for done, file in enumerate(files, start=1):
            if is_cancelled and is_cancelled():
                raise Cancelled()
            try:
                doc = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise BadFile(f"файл {file.name} не разобрать: {e}") from None
            app_data = doc.get("appData") if isinstance(doc, dict) else None
            app_id = app_data.get("application_id") if isinstance(app_data, dict) else None
            if app_id != file.stem:
                raise BadFile(f"в файле {file.name} appData.application_id = {app_id!r}, а имя файла говорит {file.stem!r}")
            try:
                yield from flatten_response(doc, file.stem, source, rules, ignore_paths, adjust)
            except BadFile as e:
                raise BadFile(f"файл {file.name}: {e.message}") from None
            if done % PROGRESS_EVERY == 0 or done == total:
                if on_progress:
                    on_progress(done)
                say("info", f"Обработано {done} из {total}")

    say("info", f"Срез {source}: {total} файлов")
    return write_csv(Path(out_csv), COLUMNS, rows())


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Использование: python -m pipeline.normalize <папка_датасета> <BEFORE|AFTER> <out.csv>")
        return 1
    dataset_dir, source, out_csv = argv
    cfg = {"ignore_paths": ["appData.request_id", "appData.createDateTime"]}
    start = time.time()
    n = normalize_dataset(Path(dataset_dir), source, Path(out_csv), cfg, log=lambda lvl, msg: print(f"[{lvl}] {msg}"))
    print(f"Готово: {n} строк за {time.time() - start:.1f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
