# -*- coding: utf-8 -*-
"""
سجلُّ الوصول (SQLite) — وظيفتُه الوحيدةُ ما لا يعرفه Everything: **متى وصلَ الملفُّ إلينا**.

لماذا سجلٌّ أصلًا وفهرسُ Everything حاضر؟ لأنّ تاريخَ التعديلِ يكذبُ في أهمِّ حالة:
كتابٌ نُسِخَ اليومَ من قرصٍ أو حُمِّلَ من الشبكةِ يحملُ تاريخَ منبعِه (٢٠٢١ مثلًا)، فلا
يظهرُ في «جديدِ اليوم» أبدًا. فالمسحُ الدوريُّ يقيسُ الفرقَ بين لقطتين، وما لم يكن
بالأمسِ وصارَ اليومَ فهو **واصلٌ** بشهادةِ الرادارِ نفسِه لا بشهادةِ ختمِ المِلفّ.

⚠ أوّلُ مسحٍ **لكلِّ جذرٍ** خطُّ أساسٍ لا وصول: ٣٫٢ مليونِ ملفٍّ رُئيَت أوّلَ مرّةٍ اليومَ
وليست «كتبًا وصلت اليوم». فتُوسَمُ `is_baseline=1` وتُستثنى من كلِّ عرضِ «الجديد».
⛔ والخطُّ **لكلِّ جذرٍ** لا للقاعدةِ كلِّها: فلو وُصِلَ قرصٌ جديدٌ بعد شهرٍ لأعلنَ رادارٌ
ساذجٌ أنّ مليونَ كتابٍ «وصلت الآن». جدولُ `root_state` يحفظُ منذ متى نرصدُ كلَّ جذر،
والصفحةُ تُعلِنُه — فلا يُقرأُ رقمٌ بلا مبدئه.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS dir(
  id      INTEGER PRIMARY KEY,
  path    TEXT NOT NULL UNIQUE,
  root_id TEXT NOT NULL,
  store   TEXT NOT NULL,
  shelf   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS dir_root  ON dir(root_id);
CREATE INDEX IF NOT EXISTS dir_shelf ON dir(shelf);

-- WITHOUT ROWID: المفتاحُ هو الجدولُ نفسُه، فلا فهرسَ يكرّرُ الأسماءَ ٣٫٣ ملايينِ مرّة
CREATE TABLE IF NOT EXISTS file(
  dir_id     INTEGER NOT NULL,
  name       TEXT NOT NULL,
  ext        TEXT,
  kind       TEXT,
  size       INTEGER,
  mtime      REAL,
  first_seen REAL NOT NULL,
  last_seen  REAL NOT NULL,
  gone_at    REAL,
  changed_at REAL,
  first_scan INTEGER NOT NULL,
  is_baseline INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(dir_id, name)
) WITHOUT ROWID;

-- فهارسُ جزئيّةٌ: الواصلُ والمفقودُ قليلان، فلا يُفهرَسُ الخطُّ الأساسُ كلُّه
CREATE INDEX IF NOT EXISTS file_arrival ON file(first_seen DESC) WHERE is_baseline = 0;
CREATE INDEX IF NOT EXISTS file_gone    ON file(gone_at DESC)    WHERE gone_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS file_changed ON file(changed_at DESC) WHERE changed_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS scan(
  id        INTEGER PRIMARY KEY,
  started   REAL NOT NULL,
  finished  REAL,
  baseline  INTEGER NOT NULL DEFAULT 0,
  seen      INTEGER DEFAULT 0,
  added     INTEGER DEFAULT 0,
  changed   INTEGER DEFAULT 0,
  gone      INTEGER DEFAULT 0,
  bytes     INTEGER DEFAULT 0,
  roots     TEXT,
  skipped   TEXT,
  secs      REAL,
  note      TEXT
);

-- منذ متى نرصدُ كلَّ جذر؟ بلا هذا لا يُقرأُ «الجديد» قراءةً صادقة
CREATE TABLE IF NOT EXISTS root_state(
  root_id    TEXT PRIMARY KEY,
  label      TEXT,
  store      TEXT,
  since      REAL NOT NULL,      -- لحظةُ خطِّ الأساسِ لهذا الجذر
  base_scan  INTEGER NOT NULL,
  base_files INTEGER DEFAULT 0,
  last_scan  INTEGER,
  last_at    REAL,
  scans      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path: Path | str, *, read_only: bool = False) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if read_only and path.exists():
        conn = sqlite3.connect("file:%s?mode=ro" % path.as_posix(), uri=True, timeout=30)
    else:
        conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-131072")  # ١٢٨ م.ب
    conn.execute("PRAGMA busy_timeout=20000")
    if not read_only:
        conn.executescript(SCHEMA)
    return conn


def get_meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return row["v"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                 (key, str(value)))


def last_scan(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM scan WHERE finished IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()


def scans(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM scan ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def baselined_roots(conn: sqlite3.Connection) -> set[str]:
    """الجذورُ التي سبقَ أن أُخِذَ لها خطُّ أساس — ما عداها أوّلُ مسحٍ له خطٌّ لا وصول."""
    return {r["root_id"] for r in conn.execute("SELECT root_id FROM root_state")}


def root_states(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM root_state ORDER BY since")]


def watching_since(conn: sqlite3.Connection, root_ids: list[str] | None = None) -> float | None:
    """أحدثُ خطِّ أساسٍ بين الجذورِ المعروضة — فلا يُدّعى رصدٌ أقدمُ من أحدثِ جذرٍ انضمّ."""
    rows = conn.execute("SELECT root_id, since FROM root_state").fetchall()
    vals = [r["since"] for r in rows if not root_ids or r["root_id"] in root_ids]
    return max(vals) if vals else None


# ── استعلاماتُ العرض ─────────────────────────────────────────────────────────
_SELECT = """
SELECT d.path AS dir, f.name, f.ext, f.kind, f.size, f.mtime,
       f.first_seen, f.changed_at, f.gone_at, d.store, d.shelf, d.root_id
FROM file f JOIN dir d ON d.id = f.dir_id
"""


def _filters(params: dict, where: list, args: list) -> None:
    if params.get("store"):
        where.append("d.store = ?")
        args.append(params["store"])
    if params.get("root"):
        where.append("d.root_id = ?")
        args.append(params["root"])
    if params.get("shelf"):
        where.append("d.shelf = ?")
        args.append(params["shelf"])
    if params.get("kind"):
        where.append("f.kind = ?")
        args.append(params["kind"])
    if params.get("ext"):
        where.append("f.ext = ?")
        args.append(str(params["ext"]).lower())


def arrivals(conn: sqlite3.Connection, since: float, *, limit: int = 300, offset: int = 0,
             order: str = "first_seen", **params) -> tuple[int, list[sqlite3.Row]]:
    """ما وصلَ إلينا بعد لحظةٍ معيّنة — بشهادةِ المسحِ لا بختمِ المِلفّ."""
    where = ["f.is_baseline = 0", "f.gone_at IS NULL", "f.first_seen >= ?"]
    args: list = [since]
    _filters(params, where, args)
    clause = " WHERE " + " AND ".join(where)
    total = conn.execute("SELECT COUNT(*) FROM file f JOIN dir d ON d.id=f.dir_id" + clause,
                         args).fetchone()[0]
    col = "f.mtime" if order == "mtime" else ("f.size" if order == "size" else "f.first_seen")
    rows = conn.execute(
        _SELECT + clause + " ORDER BY %s DESC NULLS LAST LIMIT ? OFFSET ?" % col,
        args + [limit, offset],
    ).fetchall()
    return total, rows


def departures(conn: sqlite3.Connection, since: float, *, limit: int = 300,
               offset: int = 0, **params):
    where = ["f.gone_at IS NOT NULL", "f.gone_at >= ?"]
    args: list = [since]
    _filters(params, where, args)
    clause = " WHERE " + " AND ".join(where)
    total = conn.execute("SELECT COUNT(*) FROM file f JOIN dir d ON d.id=f.dir_id" + clause,
                         args).fetchone()[0]
    rows = conn.execute(_SELECT + clause + " ORDER BY f.gone_at DESC LIMIT ? OFFSET ?",
                        args + [limit, offset]).fetchall()
    return total, rows


def changes(conn: sqlite3.Connection, since: float, *, limit: int = 300,
            offset: int = 0, **params):
    where = ["f.changed_at IS NOT NULL", "f.changed_at >= ?", "f.gone_at IS NULL"]
    args: list = [since]
    _filters(params, where, args)
    clause = " WHERE " + " AND ".join(where)
    total = conn.execute("SELECT COUNT(*) FROM file f JOIN dir d ON d.id=f.dir_id" + clause,
                         args).fetchone()[0]
    rows = conn.execute(_SELECT + clause + " ORDER BY f.changed_at DESC LIMIT ? OFFSET ?",
                        args + [limit, offset]).fetchall()
    return total, rows


def arrival_buckets(conn: sqlite3.Connection, now: float | None = None) -> list[dict]:
    """عدُّ الواصلِ في كلِّ نافذةٍ زمنيّةٍ — وهي أزرارُ «الجديد» في الصفحة."""
    now = now or time.time()
    windows = [("ساعة", 3600), ("٢٤ ساعة", 86400), ("٣ أيّام", 3 * 86400),
               ("أسبوع", 7 * 86400), ("شهر", 30 * 86400), ("٣ أشهر", 90 * 86400),
               ("سنة", 365 * 86400)]
    out = []
    for label, secs in windows:
        n = conn.execute(
            "SELECT COUNT(*) FROM file WHERE is_baseline = 0 AND gone_at IS NULL AND first_seen >= ?",
            (now - secs,),
        ).fetchone()[0]
        b = conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM file WHERE is_baseline = 0 AND gone_at IS NULL AND first_seen >= ?",
            (now - secs,),
        ).fetchone()[0]
        out.append({"label": label, "secs": secs, "count": n, "bytes": b})
    return out


def shelves(conn: sqlite3.Connection, *, limit: int = 60, cached: bool = True) -> list[dict]:
    if cached:
        got = _cached(conn, "shelves")
        if got is not None:
            return got[:limit]
    rows = conn.execute("""
        SELECT d.store, d.root_id, d.shelf,
               COUNT(*) AS n, COALESCE(SUM(f.size),0) AS bytes,
               SUM(CASE WHEN f.is_baseline = 0 THEN 1 ELSE 0 END) AS arrived
        FROM file f JOIN dir d ON d.id = f.dir_id
        WHERE f.gone_at IS NULL
        GROUP BY d.store, d.root_id, d.shelf
        ORDER BY n DESC LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def cache_stats(conn: sqlite3.Connection) -> dict:
    """
    يُحسَبُ الجمعُ الثقيلُ مرّةً واحدةً في ذيلِ المسحِ ويُخزَّنُ جاهزًا.
    (قيسَ: `totals` + `shelves` على ٣٫٥ ملايينِ صفٍّ = ٤٫٣ ث لكلِّ فتحةِ صفحة — وهو
    عملٌ لا يتغيّرُ إلّا بالمسح، فحسابُه في كلِّ طلبٍ هدرٌ محض.)
    """
    import json
    payload = {"totals": totals(conn, cached=False), "shelves": shelves(conn, limit=200, cached=False),
               "at": time.time()}
    set_meta(conn, "stats_json", json.dumps(payload, ensure_ascii=False))
    return payload


def _cached(conn: sqlite3.Connection, key: str):
    import json
    raw = get_meta(conn, "stats_json")
    if not raw:
        return None
    try:
        return json.loads(raw).get(key)
    except Exception:
        return None


def totals(conn: sqlite3.Connection, *, cached: bool = True) -> dict:
    if cached:
        got = _cached(conn, "totals")
        if got is not None:
            return got
    row = conn.execute("""
        SELECT COUNT(*) AS files, COALESCE(SUM(size),0) AS bytes
        FROM file WHERE gone_at IS NULL
    """).fetchone()
    kinds = conn.execute("""
        SELECT kind, COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes
        FROM file WHERE gone_at IS NULL GROUP BY kind ORDER BY n DESC
    """).fetchall()
    stores = conn.execute("""
        SELECT d.store, COUNT(*) AS n, COALESCE(SUM(f.size),0) AS bytes
        FROM file f JOIN dir d ON d.id=f.dir_id
        WHERE f.gone_at IS NULL GROUP BY d.store ORDER BY n DESC
    """).fetchall()
    gone = conn.execute("SELECT COUNT(*) FROM file WHERE gone_at IS NOT NULL").fetchone()[0]
    return {
        "files": row["files"], "bytes": row["bytes"], "gone": gone,
        "kinds": [dict(r) for r in kinds], "stores": [dict(r) for r in stores],
    }
