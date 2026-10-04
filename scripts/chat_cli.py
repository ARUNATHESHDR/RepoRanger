"""Terminal chat:  python -m scripts.chat_cli   (handy for debugging without the UI)"""
from app import agent, db

if __name__ == "__main__":
    db.init_db()
    thread = "cli"
    print("Repo agent. Ctrl+C to quit.")
    while True:
        res = agent.chat(thread, input("\nyou > "))
        while res["pending"]:
            print("\n[approval needed]", res["pending"]["actions"])
            ok = input("approve? (y/n) > ").strip().lower() == "y"
            res = agent.resume(thread, ok)
        print("\nagent >", res["reply"])
