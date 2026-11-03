import importlib.util
import pathlib
import tempfile

SPEC = importlib.util.spec_from_file_location("cursor_rules", pathlib.Path(__file__).with_name("check_rules.py"))
RULES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RULES)

with tempfile.TemporaryDirectory() as directory:
    root = pathlib.Path(directory)
    rule = root / "rules.mdc"
    rule.write_text("---\ndescription: Правила\nalwaysApply: true\n---\n" + "Понятная фраза.\n" * 200)
    assert not RULES.check_rule(rule)
    secret = root / "secret.env"
    secret.write_text("SERVICE_TOKEN='DemoOnly_123456'\n")
    assert RULES.read_secrets(secret) == ["DemoOnly_123456"]
    rule.write_text(rule.read_text() + "DemoOnly_123456")
    assert RULES.check_rule(rule, RULES.read_secrets(secret))
    assert not RULES.check_rule(rule, ["OtherOnly_123456"])
    rule.write_text("---\ndescription: Правила\nalwaysApply: unknown\n---\n")
    assert RULES.check_rule(rule)
print("Проверены формат, известные секреты и отсутствие лимита строк")
