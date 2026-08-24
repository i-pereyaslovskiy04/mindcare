"""
Инвариант цепочки миграций: ровно один Alembic head.

Такой проверки в проекте раньше не было — расхождение ловилось только вручную
через `alembic heads`. У истории уже есть четыре merge-узла (`3b46b9d94c08`,
`27202a87a892`, `db0b2e177da5`, `be8d3ad39b3a`), то есть параллельные ветки
возникают регулярно; забытый merge означает, что `alembic upgrade head` падает
на разворачивании.

Тест не подключается к базе: `ScriptDirectory` читает только файлы ревизий.
"""
from __future__ import annotations

from tests.alembic_script import script_directory


def test_exactly_one_head():
    heads = script_directory().get_heads()
    assert len(heads) == 1, (
        f"Найдено несколько head'ов: {heads}. Требуется merge-ревизия "
        f"(`alembic merge -m ... {' '.join(heads)}`)."
    )


def test_every_revision_is_reachable_from_the_head():
    script = script_directory()
    (head,) = script.get_heads()

    reachable = {rev.revision for rev in script.iterate_revisions(head, "base")}
    all_revisions = {rev.revision for rev in script.walk_revisions()}
    assert reachable == all_revisions, (
        f"Недостижимые из head ревизии: {sorted(all_revisions - reachable)}"
    )


def test_base_is_unique():
    script = script_directory()
    bases = script.get_bases()
    assert len(bases) == 1, f"Ожидалась одна база миграций, найдено: {bases}"
