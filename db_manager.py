import json
import threading
import os

DB_FILE = "database.json"
db_lock = threading.Lock()

def init_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({}, f)

def get_transaction(txid: str) -> dict:
    with db_lock:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            return data.get(txid)

def save_transaction(txid: str, payload: dict):
    with db_lock:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
        
        data[txid] = payload
        
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)