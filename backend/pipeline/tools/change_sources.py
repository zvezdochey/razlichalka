"""Разведка для E10: где различаются заявки со сменой решения — во входе или в том, что посчитала СПР.

Запуск (из папки backend/):  python -m pipeline.tools.change_sources <comparison.csv> <segments.csv>
segments.csv — построенный с витриной (есть колонка CHANGE_SOURCE), например из папки запуска.

Печатает:
  - сколько заявок со сменой решения различаются в каждом PREFIX / CLASS;
  - какие пути входа (INPUT_PREFIXES из backend/procedures/builtin_segments.py) различаются и у скольких заявок;
  - главное число: сколько смен решения — из-за входных данных (CHANGE_SOURCE).
"""

import sys
from pathlib import Path

from pipeline.csvio import read_csv
from pipeline.segments import input_prefixes, is_input_path


def main(comparison_csv: Path, segments_csv: Path) -> int:
    cmp_ = read_csv(comparison_csv)
    seg = read_csv(segments_csv)
    changed = set(seg.loc[seg["DECISION_CHANGED"] == "1", "APP_ID"])
    diff = cmp_[(cmp_["DIFF_FLAG"] == "1") & cmp_["APP_ID"].isin(changed)]
    print(f"Заявок со сменой решения: {len(changed)}\n")

    print("Различаются (число заявок) по PREFIX / CLASS:")
    by_class = diff.groupby(["PREFIX", "CLASS"])["APP_ID"].nunique().sort_values(ascending=False)
    for (prefix, cls), n in by_class.items():
        print(f"  {n:5}  {prefix} / {cls or '—'}")

    prefixes = input_prefixes()
    inputs = diff[diff["PATH"].map(lambda p: is_input_path(p, prefixes))]
    print(f"\nПути входа ({', '.join(prefixes)}), которые различаются:")
    for path, n in inputs.groupby("PATH")["APP_ID"].nunique().sort_values(ascending=False).items():
        print(f"  {n:5}  {path}")
    if inputs.empty:
        print("  — нет")

    if "CHANGE_SOURCE" in seg.columns:
        counts = seg.loc[seg["DECISION_CHANGED"] == "1", "CHANGE_SOURCE"].value_counts().to_dict()
        print(f"\nCHANGE_SOURCE у смен решения: {counts}")
        print(f"Из {len(changed)} смен решения {counts.get('data', 0)} — из-за входных данных")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
