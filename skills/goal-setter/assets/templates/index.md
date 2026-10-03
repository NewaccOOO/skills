# {{Название цели}}

- **Статус:** {{черновик | согласовано | в работе | готово | передано с долгом}}
- **Размер:** {{Quick | Standard | Full}}
- **Тип:** {{ресёрч | фича | аналитика | автоматизация | миграция}}
- **Исполнение:** {{solo | параллельно, unlazy scope `<slug>`}}
- **Согласовал:** {{кто и когда}}

## Документы

Порядок чтения для исполнителя сверху вниз. Факт живёт в одном документе, остальные ссылаются на его ID.

| Документ | Что в нём |
|---|---|
| [brief.md](brief.md) | зачем, цели `G-`, не-цели `NG-`, бюджет, границы автономии |
| [research.md](research.md) | находки `R-` с источниками, что говорит против, допущения |
| [requirements.md](requirements.md) | истории `US-`, критерии `AC-` и `NFR-`, ограничения `C-`, допущения `A-`, журнал уточнений `Q-` |
| [design.md](design.md) | решения `D-`, альтернативы, выкатка и откат (только Full) |
| [tasks.md](tasks.md) | задачи `T-` со ссылками на критерии, файлы и зависимости, журнал исполнения |
| [GATES.md](GATES.md) | гейты unlazy: у каждого `AC-` и `NFR-` свой гейт с тем же ID |

Строки документов, которых нет в пакете этого размера, удали.

## Проверка пакета

```bash
python3 ~/.claude/skills/goal-setter/scripts/check_trace.py --input {{docs/specs/<slug>}}
node ~/.claude/skills/unlazy/scripts/gate-lint.mjs {{docs/specs/<slug>}}/GATES.md
node ~/.claude/skills/unlazy/scripts/gate-check.mjs --status {{docs/specs/<slug>}}/GATES.md
```

## Промт запуска

```text
{{Промт запуска из references/execution.md, с путями этого пакета}}
```
