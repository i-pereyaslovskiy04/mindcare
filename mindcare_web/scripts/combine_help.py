"""Полное руководство: campaigns + methodologies + participant → один markdown.

Якоря разделов получают префикс части (c-, m-, p-), ссылки между
руководствами становятся внутренними. Используется scripts/build_help.sh.
"""
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
PARTS = [("campaigns", "c", "Часть 1. Тестирование по ссылке"),
         ("methodologies", "m", "Часть 2. Методики"),
         ("participant", "p", "Приложение. Памятка участнику")]
FIRST = {"campaigns": "c-overview", "methodologies": "m-overview", "participant": "p-memo"}


def body(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)


def fix_links(text: str) -> str:
    def repl(m):
        guide, anchor = m.group(1), m.group(2)
        prefix = {"campaigns": "c", "methodologies": "m", "participant": "p"}[guide]
        return f"(#{prefix}-{anchor})" if anchor else f"(#{FIRST[guide]})"
    text = re.sub(r"\((campaigns|methodologies|participant)\.html(?:#([a-z0-9-]+))?\)", repl, text)
    return re.sub(r'href="(campaigns|methodologies|participant)\.html"',
                  lambda m: f'href="#{FIRST[m.group(1)]}"', text)


out = ["---", "title: \"Онлайн-тестирование студентов\"",
       "subtitle: \"Полное руководство — тестирование по ссылке, методики, памятка участнику\"",
       "audience: \"Для сотрудников центра психологии ДонГУ\"", "---", ""]
for guide, prefix, title in PARTS:
    text = body((SRC / f"{guide}.md").read_text(encoding="utf-8"))
    text = re.sub(r"\{#([a-z0-9-]+)\}", lambda m: "{#" + f"{prefix}-{m.group(1)}" + "}", text)
    text = fix_links(text)
    anchor = FIRST[guide]
    out.append(f"# {title} {{#{anchor}}}\n")
    out.append(text.strip() + "\n")
sys.stdout.write("\n".join(out))
