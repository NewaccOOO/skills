#!/usr/bin/env python3
"""Самопроверка check_trace.py на связном и сломанном пакете: python3 test_check_trace.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_trace import check

REQUIREMENTS = """# Требования
### US-1: оператор выгружает отчёт
- **AC-1.1** WHEN оператор жмёт «Выгрузить» THE SYSTEM SHALL отдать CSV за 5 с
- **NFR-1** p95 выгрузки не больше 5 с, замер скриптом bench.py
"""
TASKS = """# Задачи
- [ ] **T-1** Эндпоинт выгрузки
  - Требования: AC-1.1, NFR-1
## Журнал
- T-1 закрыта
"""
GATES = """# Gates
- [ ] AC-1.1: CSV отдаётся
  CHECK: python3 check.py
  EXPECT: ok
  EVIDENCE: pending
- [ ] NFR-1: p95 в пороге
  CHECK: python3 bench.py
  EXPECT: ok
  EVIDENCE: pending
"""


def write_package(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        package = write_package(Path(tmp), {"requirements.md": REQUIREMENTS, "tasks.md": TASKS, "GATES.md": GATES})
        errors, warnings, _ = check(package)
        assert errors == [], errors
        assert warnings == [], warnings

    with tempfile.TemporaryDirectory() as tmp:
        broken = {
            "requirements.md": REQUIREMENTS + "- **AC-1.2** система удобно показывает {{что}}\n- **AC-1.1** дубль\n",
            "tasks.md": TASKS + "- AC-1.2 упомянут только в журнале, см. D-9\n",
            "GATES.md": GATES,
        }
        errors, warnings, _ = check(write_package(Path(tmp), broken))
        text = "\n".join(errors)
        assert "AC-1.1 определён несколько раз" in text, text
        assert "критерий AC-1.2 не закрыт" in text, text
        assert "у критерия AC-1.2 нет гейта" in text, text
        assert "незакрытый маркер «{{»" in text, text
        assert "ссылка на неопределённый D-9" in text, text
        assert any("удобно" in w for w in warnings), warnings

    with tempfile.TemporaryDirectory() as tmp:
        orphan_task = TASKS.replace("## Журнал\n", "- [ ] **T-2** Задача без критериев\n")
        errors, _, _ = check(write_package(Path(tmp), {"requirements.md": REQUIREMENTS, "tasks.md": orphan_task, "GATES.md": GATES}))
        assert any("задача T-2 не ссылается" in e for e in errors), errors

    with tempfile.TemporaryDirectory() as tmp:
        errors, _, _ = check(write_package(Path(tmp), {"requirements.md": REQUIREMENTS}))
        assert any("нет GATES.md" in e for e in errors), errors
    print("self-check ok")


if __name__ == "__main__":
    run()
