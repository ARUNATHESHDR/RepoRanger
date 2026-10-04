"""CLI sync:  python -m scripts.sync [--force]"""
import sys

from app import db
from app.indexer import sync_all

if __name__ == "__main__":
    db.init_db()
    for row in sync_all(force="--force" in sys.argv):
        print(row)
