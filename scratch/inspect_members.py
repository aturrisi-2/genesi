import os
import json

def inspect():
    paths = ["memory/telegram/group_member", "memory/telegram/family_members"]
    for path in paths:
        if os.path.exists(path):
            print(f"\n--- CONTENTS of {path} ---")
            for root, dirs, files in os.walk(path):
                for f in files:
                    if f.endswith(".json"):
                        full_path = os.path.join(root, f)
                        print(f"File: {full_path}")
                        try:
                            with open(full_path, "r", encoding="utf-8") as file:
                                print(json.dumps(json.load(file), indent=2, ensure_ascii=False))
                        except Exception as e:
                            print(f"  Error: {e}")
        else:
            print(f"Path does not exist: {path}")

if __name__ == "__main__":
    inspect()
