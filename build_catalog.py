import argparse
import sqlite3
import re
from pathlib import Path
import time

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, default=Path("music_catalog.sqlite"))
args = parser.parse_args()
for name in ("artist_credit", "recording"):
    if not (args.source / name).is_file():
        parser.error("Missing source file: " + name)
if args.output.exists():
    parser.error("Output already exists; choose a new filename.")
temp = args.output.with_name(args.output.name + ".building")
if temp.exists():
    parser.error("Temporary build exists; rename or remove it before restarting.")
escapes = {"t":"\t", "n":"\n", "r":"\r", "b":"\b", "f":"\f", "v":"\v", "\\":"\\"}
pattern = re.compile(r"\\([0-7]{1,3}|x[0-9a-fA-F]{1,2}|.)")
def decode(s):
    def sub(m):
        v = m.group(1)
        if v in escapes: return escapes[v]
        if v.startswith("x") and len(v)>1: return chr(int(v[1:],16))
        if v[0] in "01234567": return chr(int(v,8))
        return v
    return pattern.sub(sub,s)
def rows(name):
    with (args.source / name).open(encoding="utf-8", newline="") as f:
        for line in f:
            yield line.rstrip("\r\n").split("\t")
db = sqlite3.connect(temp)
db.execute("PRAGMA journal_mode=OFF")
db.execute("PRAGMA synchronous=OFF")
db.execute("PRAGMA cache_size=-131072")
db.execute("PRAGMA temp_store=FILE")
db.execute("CREATE TABLE credits(id INTEGER PRIMARY KEY, artist TEXT NOT NULL)")
db.execute("CREATE TABLE songs(id INTEGER PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL, mbid TEXT NOT NULL, variants INTEGER NOT NULL DEFAULT 1)")
db.execute("CREATE UNIQUE INDEX song_unique ON songs(title COLLATE NOCASE, artist COLLATE NOCASE)")
db.execute("CREATE VIRTUAL TABLE songs_fts USING fts5(title, artist, content='songs', content_rowid='id', tokenize='unicode61 remove_diacritics 2', prefix='2 3')")
start=time.monotonic()
def load(name, sql, transform):
    batch=[]
    for n,r in enumerate(rows(name),1):
        batch.append(transform(r))
        if len(batch)>=20000:
            db.executemany(sql,batch)
            db.commit()
            batch.clear()
        if n%500000==0:
            print(f"{name}: {n:,} rows; {time.monotonic()-start:.0f}s",flush=True)
    if batch: db.executemany(sql,batch)
    db.commit()
load("artist_credit","INSERT INTO credits VALUES (?,?)",lambda r:(int(r[0]),decode(r[1])))
load("recording", """INSERT INTO songs(title,artist,mbid)
SELECT ?,artist,? FROM credits WHERE id=?
ON CONFLICT(title COLLATE NOCASE,artist COLLATE NOCASE)
DO UPDATE SET variants=variants+1, mbid=min(songs.mbid,excluded.mbid)""",
lambda r:(decode(r[2]),r[1],int(r[3])))
print("Building full-text index...",flush=True)
db.execute("INSERT INTO songs_fts(songs_fts) VALUES ('rebuild')")
db.execute("DROP TABLE credits")
db.commit()
print("Compacting database...",flush=True)
db.execute("VACUUM")
db.execute("PRAGMA journal_mode=DELETE")
print("Checking integrity...",flush=True)
if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
    raise RuntimeError("Database integrity check failed")
count=db.execute("SELECT count(*) FROM songs").fetchone()[0]
db.close()
temp.rename(args.output)
print(f"Finished: {count:,} songs; {args.output.stat().st_size/1024**3:.2f} GiB",flush=True)
