import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ITERATION_SIGNALS = {"correction", "abort", "repeat", "violates"}
DIRECT_SIGNALS = {"explicit", "violates"}
WEAK_ONLY_SIGNALS = {"observed", "accepted"}
STRENGTH_ORDER = {"strong": 0, "medium": 1, "weak": 2}
QUOTES_PER_PATTERN = 2
DIALOGS_PER_PATTERN = 8


def read_findings(path: Path) -> tuple[list[dict], int]:
    findings = []
    broken = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip(",")
        if not (line.startswith("{") and '"key"' in line):
            continue
        try:
            finding = json.loads(line)
        except json.JSONDecodeError:
            broken += 1
            continue
        if finding.get("key") and finding.get("dialog"):
            findings.append(finding)
        else:
            broken += 1
    return findings, broken


def read_decisions(path: Path) -> dict[str, tuple[str, int]]:
    decisions = {}
    if not path.exists():
        return decisions
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].isdigit():
            decisions[parts[0]] = (parts[1], int(parts[2]))
    return decisions


def strength(items: list[dict]) -> str:
    dialogs = {item["dialog"] for item in items}
    signals = {item.get("signal") for item in items}
    iteration_dialogs = {item["dialog"] for item in items if item.get("signal") in ITERATION_SIGNALS}
    if signals & DIRECT_SIGNALS or len(iteration_dialogs) >= 2:
        return "strong"
    if len(dialogs) >= 3 and not signals <= WEAK_ONLY_SIGNALS:
        return "strong"
    if len(dialogs) >= 2:
        return "medium"
    return "weak"


def render_pattern(key: str, items: list[dict], status: str) -> str:
    dialogs = sorted({item["dialog"] for item in items})
    folders = {item.get("folder", "") for item in items}
    signals = Counter(item.get("signal", "?") for item in items)
    rules = [rule for rule, _ in Counter(item.get("rule", "") for item in items if item.get("rule")).most_common(3)]
    quotes = []
    for item in items:
        if item.get("quote") and item["quote"] not in quotes:
            quotes.append(item["quote"])
    lines = [
        f"### {key}",
        f"- тема: {items[0].get('topic', '?')}; сила: {strength(items)}; статус: {status}",
        f"- диалогов: {len(dialogs)}; папок: {len(folders)}; сигналы: "
        + ", ".join(f"{signal}×{count}" for signal, count in signals.most_common()),
        f"- последний раз: {max(item.get('date', '') for item in items)}",
        f"- диалоги: {', '.join(dialogs[:DIALOGS_PER_PATTERN])}",
    ]
    lines += [f"- правило: {rule}" for rule in rules]
    lines += [f"- цитата: «{quote}»" for quote in quotes[:QUOTES_PER_PATTERN]]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Сводит находки субагентов в паттерны")
    parser.add_argument("work_dir")
    parser.add_argument("--state-dir", help="папка состояния с findings.jsonl и decisions.tsv прошлых запусков")
    parser.add_argument("--rename", action="append", default=[], help="старый_ключ=новый_ключ, можно несколько раз")
    args = parser.parse_args()
    renames = dict(pair.split("=", 1) for pair in args.rename)
    work_dir = Path(args.work_dir)
    state_dir = Path(args.state_dir).expanduser() if args.state_dir else None

    sources = sorted(work_dir.glob("result-*.md"))
    if state_dir and (state_dir / "findings.jsonl").exists():
        sources.append(state_dir / "findings.jsonl")
    findings = {}
    broken = 0
    for source in sources:
        source_findings, source_broken = read_findings(source)
        broken += source_broken
        for finding in source_findings:
            finding["key"] = renames.get(finding["key"], finding["key"])
            findings[(finding["key"], finding["dialog"], finding.get("quote", ""))] = finding
    decisions = read_decisions(state_dir / "decisions.tsv") if state_dir else {}

    by_key = defaultdict(list)
    for finding in findings.values():
        by_key[finding["key"]].append(finding)

    rendered = []
    for key, items in by_key.items():
        status = "новый"
        if key in decisions:
            decision, dialogs_then = decisions[key]
            dialogs_now = len({item["dialog"] for item in items})
            status = decision if dialogs_now <= dialogs_then else f"{decision}, но с тех пор новые диалоги"
        rendered.append((STRENGTH_ORDER[strength(items)], -len({item["dialog"] for item in items}), key, items, status))
    rendered.sort(key=lambda row: row[:3])

    (work_dir / "findings.jsonl").write_text(
        "".join(json.dumps(finding, ensure_ascii=False) + "\n" for finding in findings.values()), encoding="utf-8"
    )
    (work_dir / "known-keys.txt").write_text("\n".join(sorted(by_key)), encoding="utf-8")
    header = [
        f"Находок: {len(findings)}; паттернов: {len(by_key)}; битых строк пропущено: {broken}",
        "Сила: " + ", ".join(f"{name} {sum(1 for row in rendered if row[0] == order)}" for name, order in STRENGTH_ORDER.items()),
        "",
    ]
    patterns = "\n".join(header) + "\n\n".join(render_pattern(key, items, status) for *_, key, items, status in rendered)
    (work_dir / "patterns.md").write_text(patterns, encoding="utf-8")
    print(patterns)


if __name__ == "__main__":
    main()
