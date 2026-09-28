"""
ORM-модели ↔ схема после `alembic upgrade head` не расходятся.

`alembic check` на изолированной test-БД (её runner уже мигрировал до head)
должен не находить upgrade-операций. Иначе `alembic revision --autogenerate`
предложит лишние изменения — в том числе DROP индексов, которые есть только в
миграциях (например ux_users_email_normalized: без него возможны дубли email
Ivan@x / ivan@x). При добавлении индекса/constraint в миграцию описывайте его
и в модели.
"""
import os
import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]


def test_alembic_check_reports_no_drift():
    env = dict(os.environ)
    env["PGCLIENTENCODING"] = "UTF8"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=str(API_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        "ORM-модели расходятся со схемой миграций (alembic check):\n" + output[-3000:]
    )
    assert "No new upgrade operations detected" in output
