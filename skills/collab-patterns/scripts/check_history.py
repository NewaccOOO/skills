import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path, items):
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")


def expect_failure(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("Ожидался отказ")


def main():
    collector = load("collect")
    aggregator = load("aggregate")
    with tempfile.TemporaryDirectory(prefix="collab-history-check-") as temp:
        root = Path(temp).resolve()
        history = root / "history"
        history.mkdir()
        records = [
            {"type": "session_meta", "payload": {"id": "session", "cwd": "/project"}},
            {"type": "response_item", "payload": {"role": "user", "content": "Всегда отвечай по-русски"}},
            {"type": "response_item", "payload": {"type": "function_call", "arguments": "полная команда"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "output": "я" * 31000 + " КОНЕЦ РЕЗУЛЬТАТА"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "конец ответа"}]}},
            {"role": "user", "message": {"content": [{"text": "<user_query>поправка Cursor</user_query>"}]}},
        ]
        transcript = history / "chat.jsonl"
        raw = "\r\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\r\n"
        transcript.write_bytes(raw.encode())
        export = history / "export.json"
        export.write_text(json.dumps({"messages": records}, ensure_ascii=False), encoding="utf-8")
        (history / "plain.md").write_text("Полный текст другого агента", encoding="utf-8")
        nested = history / "subagents"
        nested.mkdir()
        write_jsonl(nested / "branch.jsonl", [{"role": "assistant", "text": "копия эпизода"}])
        (history / "loop").symlink_to(history, target_is_directory=True)
        work = root / "work"
        manifest = collector.collect(work, [("other", history)], "all")
        assert len(manifest["sources"]) == 4 and not manifest["errors"]
        for source in manifest["sources"]:
            joined = "".join((work / chunk["path"]).read_bytes().decode() for chunk in source["chunks"])
            assert joined == Path(source["path"]).read_bytes().decode()
            assert stat.S_IMODE((work / source["chunks"][0]["path"]).stat().st_mode) == 0o600
        assert stat.S_IMODE(work.stat().st_mode) == 0o700
        expect_failure(lambda: collector.collect(work, [("other", history)], "all"))
        expect_failure(lambda: aggregator.aggregate(work))
        receipts = [{"chunk": chunk["id"], "sha256": chunk["sha256"]} for source in manifest["sources"] for chunk in source["chunks"]]
        write_jsonl(work / "reviewed-test.jsonl", receipts)
        source = next(s for s in manifest["sources"] if s["path"] == str(transcript))
        evidence = {"chunk": source["chunks"][0]["id"], "quote": "Всегда отвечай по-русски"}
        finding = {"key": "answers.language", "source": source["id"], "rule": "Отвечай по-русски",
                   "basis": "explicit", "scope": "global", "scope_reason": "Прямая общая просьба",
                   "conditions": "При общении", "counterexamples": [], "evidence": [evidence]}
        write_jsonl(work / "result-test.jsonl", [finding])
        state = root / "state"
        state.mkdir()
        old = dict(finding, rule="Устаревшее правило", source_sha256="old")
        absent = dict(old, source="absent", key="another")
        write_jsonl(state / "findings.jsonl", [old, absent])
        result = aggregator.aggregate(work, state)
        findings = aggregator.read_jsonl(work / "findings.jsonl")
        assert result["sources_reviewed"] == 4 and result["retained_from_absent_sources"] == 1
        assert len(findings) == 2 and all(item["rule"] != old["rule"] for item in findings if item["source"] == source["id"])
        assert "сила:" not in (work / "patterns.md").read_text()
        write_jsonl(state / "findings.jsonl", [{"key": "legacy", "dialog": "old-chat"}])
        expect_failure(lambda: aggregator.aggregate(work, state))
        write_jsonl(state / "findings.jsonl", [old, absent])
        write_jsonl(work / "result-test.jsonl", [])
        aggregator.aggregate(work, state)
        assert [item["source"] for item in aggregator.read_jsonl(work / "findings.jsonl")] == ["absent"]
        bad = dict(finding, evidence=[dict(evidence, quote="такого текста нет")])
        write_jsonl(work / "result-test.jsonl", [bad])
        expect_failure(lambda: aggregator.aggregate(work))
        write_jsonl(work / "result-test.jsonl", [finding])
        write_jsonl(work / "reviewed-test.jsonl", receipts[:-1])
        expect_failure(lambda: aggregator.aggregate(work))
        write_jsonl(work / "reviewed-test.jsonl", receipts)
        chunk = work / source["chunks"][0]["path"]
        chunk.write_text("Изменённый текст", encoding="utf-8")
        expect_failure(lambda: aggregator.aggregate(work))
        corrupt = root / "bad.jsonl"
        corrupt.write_text('{"role":"user"}\nnot-json\n')
        broken = collector.collect(root / "broken", [("other", corrupt)], "all")
        assert broken["sources"][0]["parse_errors"] == [2]
        expect_failure(lambda: aggregator.aggregate(root / "broken"))
        missing = collector.collect(root / "missing", [("other", root / "absent")], "all")
        assert missing["errors"]
        db = root / "state.vscdb"
        db.write_bytes(b"sqlite placeholder")
        unsupported = collector.collect(root / "db", [("other", db)], "all")
        assert unsupported["locations"][0]["unsupported"] == [str(db)]
        expect_failure(lambda: aggregator.aggregate(root / "db"))
        if shutil.which("zstd"):
            compressed = root / "archive.jsonl.zst"
            result = subprocess.run(["zstd", "-qc", str(transcript)], capture_output=True, check=True)
            compressed.write_bytes(result.stdout)
            assert collector.read_text(compressed) == raw
            compressed.write_bytes(b"broken archive")
            expect_failure(lambda: collector.read_text(compressed))
        for name in ["collect", "aggregate"]:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name(name + ".py")), "--help"], capture_output=True)
            assert result.returncode == 0
    print("Проверены полная история и CRLF, форматы, архивы, вложенные источники, покрытие, цитаты и замена старых находок")


if __name__ == "__main__":
    main()
