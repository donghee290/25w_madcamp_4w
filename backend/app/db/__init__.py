from pymongo import MongoClient

_client = None
_db = None


def init_db(app):
    global _client, _db
    uri = app.config["MONGO_URI"]
    db_name = app.config["MONGO_DB"]
    _client = MongoClient(uri)
    _db = _client[db_name]
    # 연결 확인
    _client.admin.command("ping")
    print(f"[DB] Connected to MongoDB ({db_name})")


def get_db():
    return _db
