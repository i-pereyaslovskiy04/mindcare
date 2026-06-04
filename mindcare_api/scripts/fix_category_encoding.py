"""
Fix category names that were stored as UTF-8 bytes interpreted as CP1251.
Run once: python scripts/fix_category_encoding.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.db.models import Category


def fix(s: str) -> str:
    return s.encode('cp1251').decode('utf-8')


with SessionLocal() as db:
    cats = db.query(Category).all()
    if not cats:
        print("No categories found.")
        sys.exit(0)

    print(f"Found {len(cats)} categories. Fixing...\n")

    for c in cats:
        try:
            fixed_name = fix(c.name)
            fixed_slug = fix(c.slug) if c.slug else c.slug
        except (UnicodeEncodeError, UnicodeDecodeError):
            print(f"  SKIP (already correct or unrecognised encoding): {c.name!r}")
            continue

        print(f"  {c.name!r}")
        print(f"  → {fixed_name!r}\n")
        c.name = fixed_name
        c.slug = fixed_slug

    db.commit()
    print("Done. All categories updated.")
