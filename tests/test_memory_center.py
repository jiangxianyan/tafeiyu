"""Data-layer tests for the embedded memory dashboard."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher"
if str(LAUNCHER) not in sys.path:
    sys.path.insert(0, str(LAUNCHER))

import memory_center  # noqa: E402


class MemoryCenterDataTest(unittest.TestCase):
    def test_habits_and_persona_scoped_memory_layers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            style = temp / "style.txt"
            style.write_text(
                "默认使用短句。\n不要写成长段说明。\n称呼主人为小洋。",
                encoding="utf-8",
            )
            db_path = temp / "memory.db"
            db = sqlite3.connect(db_path)
            db.execute(
                """
                CREATE TABLE memories (
                    content TEXT,
                    session TEXT,
                    sender TEXT,
                    created_at REAL,
                    priority INTEGER
                )
                """
            )
            db.execute(
                """
                CREATE TABLE memory_state (
                    memory_rowid INTEGER,
                    heat REAL,
                    last_accessed REAL,
                    access_count INTEGER,
                    pinned INTEGER
                )
                """
            )
            now = time.time()
            db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?)",
                ("主人喜欢吃草莓", "persona:tafei|group:1", "小洋", now, 9),
            )
            first = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute(
                "INSERT INTO memory_state VALUES (?, ?, ?, ?, ?)",
                (first, 2.5, now, 3, 1),
            )
            db.execute(
                "INSERT INTO memories VALUES (?, ?, ?, ?, ?)",
                ("另一个角色不应出现", "persona:dafeiyu|group:2", "群友", now, 1),
            )
            second = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute(
                "INSERT INTO memory_state VALUES (?, ?, ?, ?, ?)",
                (second, 1.0, now, 0, 0),
            )
            db.commit()
            db.close()

            persona = {
                "id": "tafei",
                "display_name": "塔菲",
                "style_file": str(style),
            }
            with patch.object(memory_center, "MEMORY_DB", db_path):
                habits = memory_center._persona_habits(persona)
                records = memory_center._memory_records("tafei")

            self.assertEqual(len(habits), 3)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["text"], "主人喜欢吃草莓")
            self.assertEqual(records[0]["layer"], "fixed")
            self.assertIn("relation", records[0]["tags"])
            self.assertEqual(records[0]["access_count"], 3)


if __name__ == "__main__":
    unittest.main()
