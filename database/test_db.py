import db

db.init()
db.put("test", {"hello": "world", "n": 1})
print(db.get("test"))
db.delete("test")
print(db.get("test", "gone"))