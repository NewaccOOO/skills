import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def read_jsonl(path):
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Некорректный JSON: {path.name}:{number}") from error
        if not isinstance(item, dict):
            raise ValueError(f"Ожидался объект: {path.name}:{number}")
        items.append(item)
    return items


def aggregate(work, state_dir=None):
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 2:
        raise ValueError("Неизвестная версия манифеста")
    if manifest["errors"] or any(location["unsupported"] for location in manifest["locations"]):
        raise ValueError("Есть непрочитанные источники; сначала разреши ошибки манифеста")
    sources = {source["id"]: source for source in manifest["sources"]}
    if not sources or any(source["parse_errors"] for source in sources.values()):
        raise ValueError("Нет источников или есть повреждённые записи; требуется разбор исходников")
    chunks = {}
    for source in sources.values():
        parts = []
        for chunk in source["chunks"]:
            text = (work / chunk["path"]).read_bytes().decode("utf-8")
            if hashlib.sha256(text.encode()).hexdigest() != chunk["sha256"]:
                raise ValueError("Часть истории изменилась после сбора")
            chunks[chunk["id"]] = {"source": source["id"], "text": text, "sha256": chunk["sha256"]}
            parts.append(text)
        if hashlib.sha256("".join(parts).encode()).hexdigest() != source["sha256"]:
            raise ValueError("Нарушен порядок или полнота частей диалога")
    receipts = {}
    for path in sorted(work.glob("reviewed-*.jsonl")):
        for item in read_jsonl(path):
            if not isinstance(item.get("chunk"), str) or not isinstance(item.get("sha256"), str):
                raise ValueError("Некорректная запись прочитанной части")
            if item["chunk"] in receipts and receipts[item["chunk"]] != item["sha256"]:
                raise ValueError("Противоречивые отметки чтения")
            receipts[item["chunk"]] = item["sha256"]
    if set(receipts) != set(chunks) or any(receipts[key] != chunk["sha256"] for key, chunk in chunks.items()):
        raise ValueError("Не все части истории отмечены прочитанными в текущей версии")
    findings = []
    for path in sorted(work.glob("result-*.jsonl")):
        for item in read_jsonl(path):
            if not all(isinstance(item.get(key), str) and item[key] for key in
                       ("key", "source", "rule", "basis", "scope", "scope_reason", "conditions")):
                raise ValueError("У находки отсутствуют обязательные поля")
            if item["source"] not in sources:
                raise ValueError("Находка ссылается на неизвестный источник")
            if item["scope"] not in {"global", "project", "task", "uncertain"}:
                raise ValueError("Неизвестная область правила")
            if item["basis"] not in {"explicit", "correction", "observed", "hypothesis"}:
                raise ValueError("Неизвестное основание правила")
            if not isinstance(item.get("counterexamples"), list) or not isinstance(item.get("evidence"), list) or not item["evidence"]:
                raise ValueError("Нужны свидетельства и список исключений")
            for evidence in item["evidence"]:
                if not isinstance(evidence, dict) or evidence.get("chunk") not in chunks:
                    raise ValueError("Неизвестная часть в свидетельстве")
                chunk = chunks[evidence["chunk"]]
                quote = evidence.get("quote")
                if chunk["source"] != item["source"] or not isinstance(quote, str) or not quote or quote not in chunk["text"]:
                    raise ValueError("Цитата не найдена в указанном источнике")
            item["source_sha256"] = sources[item["source"]]["sha256"]
            findings.append(item)
    retained = []
    if state_dir and (state_dir / "findings.jsonl").exists():
        for item in read_jsonl(state_dir / "findings.jsonl"):
            if not item.get("source") or not item.get("source_sha256"):
                raise ValueError("Старое состояние не содержит происхождения находок; сохрани его отдельно и выполни полный анализ")
            if item["source"] not in sources:
                retained.append(item)
    combined = retained + findings
    groups = defaultdict(list)
    for item in combined:
        groups[item["key"]].append(item)
    os.umask(0o077)
    (work / "findings.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in combined), encoding="utf-8")
    lines = ["# Наблюдения для смыслового синтеза", "", "Число эпизодов не определяет достоверность или область правила.", ""]
    for key, items in sorted(groups.items()):
        lines.extend([f"## {key}", "", json.dumps(items, ensure_ascii=False, indent=2), ""])
    (work / "patterns.md").write_text("\n".join(lines), encoding="utf-8")
    return {"sources_reviewed": len(sources), "chunks_reviewed": len(chunks), "new_findings": len(findings),
            "retained_from_absent_sources": len(retained), "patterns": len(groups)}


def main():
    parser = argparse.ArgumentParser(description="Проверка покрытия, происхождения и обновление наблюдений без оценки их силы")
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--state-dir", type=Path)
    args = parser.parse_args()
    try:
        result = aggregate(args.work_dir.expanduser().resolve(), args.state_dir.expanduser().resolve() if args.state_dir else None)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Анализ не завершён: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
