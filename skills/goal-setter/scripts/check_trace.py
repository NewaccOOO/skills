#!/usr/bin/env python3
"""Проверка связей в пакете спеки: ID определены один раз, критерии закрыты задачами и гейтами.

    python3 check_trace.py --input docs/specs/<slug>

Выход 0 и строка TRACE OK — ошибок нет, 1 — есть ошибки. Предупреждения на выход не влияют.
Правила ID и связей — в references/package.md.
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ID = r"(?:ADR|NFR|NG|US|AC|G|C|A|R|D|T|Q)-\d+(?:\.\d+)?"
# определение — заголовок «### US-1» или пункт списка с жирным ID «- **AC-1.1**»
DEFINITION = re.compile(rf"^\s*(?:#{{1,6}}\s+({ID})\b|[-*]\s+(?:\[[ xX]\]\s+)?\*\*({ID})\*\*)")
REFERENCE = re.compile(rf"\b{ID}\b")
HEADING = re.compile(r"^\s*#{1,6}\s")
FENCE = re.compile(r"^\s*(```|~~~)")
# тот же формат строки гейта, что парсит unlazy
GATE = re.compile(r"^- \[[ xX]\] (\S+?):")
CRITERIA_PREFIXES = ("AC-", "NFR-")
OPEN_MARKERS = ("[НУЖНО УТОЧНИТЬ", "{{")
VAGUE = re.compile(
    r"по возможности|при необходимости|где возможно|и т\.\s?[дп]\.|достаточн\w*|удобн\w+|"
    r"эффективн\w+|оптимальн\w+|гибк\w+|качественн\w+|as appropriate|if necessary|where possible",
    re.IGNORECASE,
)
VAGUE_FILES = ("brief.md", "requirements.md")
TASKS_FILE = "tasks.md"
GATES_FILE = "GATES.md"


def unfenced_lines(path: Path) -> list[tuple[int, str]]:
    lines = []
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            lines.append((lineno, line))
    return lines


def check(package: Path) -> tuple[list[str], list[str], str]:
    errors: list[str] = []
    warnings: list[str] = []
    definitions: dict[str, list[str]] = defaultdict(list)
    references: dict[str, set[str]] = defaultdict(set)
    tasks_with_criteria: set[str] = set()
    covered_criteria: set[str] = set()
    task_ids: list[str] = []

    docs = sorted(p for p in package.rglob("*.md") if p.name != GATES_FILE)
    for doc in docs:
        rel = doc.relative_to(package)
        current_task = None
        for lineno, line in unfenced_lines(doc):
            where = f"{rel}:{lineno}"
            for marker in OPEN_MARKERS:
                if marker in line:
                    errors.append(f"{where}: незакрытый маркер «{marker}»")
            if doc.name in VAGUE_FILES and (vague := VAGUE.search(line)):
                warnings.append(f"{where}: размытое слово «{vague.group(0)}» — нужен порог или конкретика")

            defined = None
            if match := DEFINITION.match(line):
                defined = match.group(1) or match.group(2)
                definitions[defined].append(where)
            if doc.name == TASKS_FILE:
                if defined and defined.startswith("T-"):
                    current_task = defined
                    task_ids.append(defined)
                elif HEADING.match(line):
                    current_task = None

            refs = REFERENCE.findall(line)
            if defined:
                refs.remove(defined)
            for ref in refs:
                references[ref].add(str(rel))
                # упоминание в журнале исполнения не закрывает критерий, закрывает только блок задачи
                if current_task and ref.startswith(CRITERIA_PREFIXES):
                    tasks_with_criteria.add(current_task)
                    covered_criteria.add(ref)
                if doc.name == TASKS_FILE and ref.startswith("NG-"):
                    warnings.append(f"{where}: задача ссылается на не-цель {ref}")

    gates: set[str] = set()
    gates_path = package / GATES_FILE
    if gates_path.exists():
        for _, line in unfenced_lines(gates_path):
            if match := GATE.match(line):
                gates.add(match.group(1))
            for ref in REFERENCE.findall(line):
                references[ref].add(GATES_FILE)
    else:
        errors.append(f"нет {GATES_FILE}: критерии готовности не превращены в гейты unlazy")

    for id_, places in sorted(definitions.items()):
        if len(places) > 1:
            errors.append(f"{id_} определён несколько раз: {', '.join(places)}")
    for id_, files in sorted(references.items()):
        if id_ not in definitions:
            errors.append(f"ссылка на неопределённый {id_} в {', '.join(sorted(files))}")

    criteria = sorted(i for i in definitions if i.startswith(CRITERIA_PREFIXES))
    has_tasks = (package / TASKS_FILE).exists()
    for id_ in criteria:
        if has_tasks and id_ not in covered_criteria:
            errors.append(f"критерий {id_} не закрыт ни одной задачей в {TASKS_FILE}")
        if gates_path.exists() and id_ not in gates:
            errors.append(f"у критерия {id_} нет гейта в {GATES_FILE}")
    for id_ in task_ids:
        if id_ not in tasks_with_criteria:
            errors.append(f"задача {id_} не ссылается ни на один AC или NFR")

    stats = f"ID: {len(definitions)}, критериев: {len(criteria)}, задач: {len(task_ids)}, гейтов: {len(gates)}"
    return errors, warnings, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка связей в пакете спеки")
    parser.add_argument("--input", required=True, type=Path, help="папка пакета, например docs/specs/<slug>")
    args = parser.parse_args()
    if not args.input.is_dir():
        print(f"нет папки пакета: {args.input}", file=sys.stderr)
        return 1

    errors, warnings, stats = check(args.input)
    print(stats)
    for warning in warnings:
        print("  !", warning)
    for error in errors:
        print("  ✗", error)
    if errors:
        print(f"ошибок: {len(errors)}", file=sys.stderr)
        return 1
    print("TRACE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
