"""Tiny eval harness:  python -m evals.run_evals

Edit evals/questions.json with 15-20 questions about YOUR repos whose answers you know.
A question passes if the reply contains at least one string from `must_contain_any`.
Run it after every change to chunking, retrieval or prompts and watch the score.
"""
import json
import time
from pathlib import Path

from app import agent, db

if __name__ == "__main__":
    db.init_db()
    items = json.loads((Path(__file__).parent / "questions.json").read_text())
    passed = 0
    for i, item in enumerate(items):
        res = agent.chat(f"eval-{int(time.time())}-{i}", item["question"])
        reply = res["reply"].lower()
        ok = any(s.lower() in reply for s in item["must_contain_any"])
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {item['question']}")
        if not ok:
            print("   reply:", res["reply"][:300].replace("\n", " "))
    print(f"\nScore: {passed}/{len(items)}")
