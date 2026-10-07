# -*- coding: utf-8 -*-
"""
المسحُ الدوريّ: يسألُ Everything عن كلِّ ملفٍّ في النطاق، ويكتبُ الفرقَ في سجلِّ الوصول.

قاعدتان لا تُكسَران:
  ⛔ **جذرٌ غيرُ موصولٍ لا يُمسَح.** فهرسُ Everything يحفظُ ملفّاتِ مشاركةٍ شبكيّةٍ بعد
     انفصالِها، فلو مسحناها وهي مفصولةٌ لأعلنّا «اختفى ٣ ملايينِ كتاب». فيُفحَصُ وجودُ
     الجذرِ أوّلًا، وإن غاب سُجِّلَ «غيرُ موصول» ولم يُحكَم على ملفّاته بشيء.
  ⛔ **المسحُ الأوّلُ خطُّ أساسٍ** يُوسَمُ `baseline` ولا يُحسَبُ وصولًا (انظر `db.py`).
"""
from __future__ import annotations

import os
import sqlite3
import time

from . import db, everything as ev
from .config import Config, Root

BATCH = 20_000

UPSERT = """
INSERT INTO file(dir_id,name,ext,kind,size,mtime,first_seen,last_seen,first_scan,is_baseline,first_seen_src)
VALUES(?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(dir_id,name) DO UPDATE SET
  last_seen  = excluded.last_seen,
  gone_at    = NULL,
  changed_at = CASE WHEN file.size IS NOT excluded.size OR file.mtime IS NOT excluded.mtime
                    THEN excluded.last_seen ELSE file.changed_at END,
  size       = excluded.size,
  mtime      = excluded.mtime
"""


class _Dirs:
    """ذاكرةُ المجلّدات: المسارُ يُخزَّنُ مرّةً واحدةً لا مرّةً لكلِّ ملفٍّ فيه."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.cache: dict[str, int] = {
            r["path"]: r["id"] for r in conn.execute("SELECT id, path FROM dir")
        }

    def id_of(self, path: str, root: Root, shelf: str) -> int:
        got = self.cache.get(path)
        if got is not None:
            return got
        cur = self.conn.execute(
            "INSERT INTO dir(path, root_id, store, shelf) VALUES(?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET shelf=excluded.shelf RETURNING id",
            (path, root.id, root.store, shelf),
        )
        new_id = cur.fetchone()[0]
        self.cache[path] = new_id
        return new_id


def _split(path: str) -> tuple[str, str]:
    i = path.rfind("\\")
    return (path[:i] if i > 0 else path, path[i + 1:])


def run(cfg: Config, *, root_ids: list[str] | None = None, note: str = "",
        progress=None, page: int | None = None) -> dict:
    if not ev.alive():
        raise ev.NotRunning("برنامج Everything غير مشتغل — لا فهرسَ نسأله")

    page = page or cfg.page
    conn = db.connect(cfg.db_path)
    known = db.baselined_roots(conn)
    stamp = time.time()
    chosen_ids = [r.id for r in cfg.roots if not root_ids or r.id in root_ids]
    baseline = 1 if any(rid not in known for rid in chosen_ids) else 0
    cur = conn.execute(
        "INSERT INTO scan(started, baseline, note) VALUES(?,?,?) RETURNING id",
        (stamp, baseline, note or None),
    )
    sid = cur.fetchone()[0]
    conn.commit()

    dirs = _Dirs(conn)
    ext_type = cfg.ext_type
    chosen = [r for r in cfg.roots if not root_ids or r.id in root_ids]
    scanned: list[str] = []
    skipped: list[str] = []
    fresh: list[str] = []  # جذورٌ أُخِذَ لها خطُّ الأساسِ في هذا المسح
    seen = 0

    def say(msg: str) -> None:
        if progress:
            progress(msg)

    for root in chosen:
        if not os.path.isdir(root.path):
            skipped.append(root.id)
            say("⏭ %s غيرُ موصولٍ — لم يُمسَح ولم يُحكَم على ملفّاته" % root.label)
            continue
        search = cfg.scope(root_ids=[root.id])
        t0 = time.time()
        total = ev.count(search)
        is_base = 1 if root.id not in known else 0
        # جذرٌ محلّيٌّ يُمسَحُ أوّلَ مرّة: تاريخُ إنشاءِ المِلفِّ على القرصِ هو تاريخُ وصولِه
        # حقًّا — أصدقُ من «خطِّ أساسٍ» يُسقِطُ كتبَ اليومِ كلَّها. والشبكةُ تُستثنى: ملايينُ
        # استدعاءِ stat عبر SMB تُقعِدُ المسح، فتبقى على فرقِ اللقطتين.
        seed_ct = bool(is_base and root.store == "local")
        if is_base:
            fresh.append(root.id)
        say("⟳ %s: %d ملفًّا في النطاق (%.2fث للعدّ)%s" % (
            root.label, total, time.time() - t0, " — خطُّ أساسٍ أوّل" if is_base else ""))

        rows: list[tuple] = []
        n = 0
        prefix_len = len(root.prefix)
        for rec in ev.iter_rows(search, page=page):
            path = rec.get("path") or ""
            if rec.get("is_dir") or not path:
                continue
            folder, name = _split(path)
            rest = path[prefix_len:] if len(path) > prefix_len else ""
            head, sep, _ = rest.partition("\\")
            shelf = head if sep else "(في جذر المكتبة)"
            dot = name.rfind(".")
            ext = name[dot + 1:].lower() if dot > 0 else ""
            rows.append((
                dirs.id_of(folder, root, shelf), name, ext, ext_type.get(ext, "أخرى"),
                rec.get("size"), rec.get("mtime"), stamp, stamp, sid, is_base,
            ))
            if seed_ct:
                try:
                    st = os.stat(path)
                    born = getattr(st, "st_birthtime", None) or st.st_ctime
                except OSError:
                    born = None
                if born:
                    row = list(rows[-1])
                    row[6] = born        # first_seen = تاريخُ الإنشاءِ على القرص
                    row[9] = 0           # ليس خطَّ أساسٍ: له تاريخُ وصولٍ حقيقيّ
                    rows[-1] = tuple(row) + ("ctime",)
                else:
                    rows[-1] = rows[-1] + ("scan",)
            else:
                rows[-1] = rows[-1] + ("scan",)
            n += 1
            if len(rows) >= BATCH:
                conn.executemany(UPSERT, rows)
                conn.commit()
                rows.clear()
                say("   … %d/%d" % (n, total))
        if rows:
            conn.executemany(UPSERT, rows)
            conn.commit()
        seen += n
        scanned.append(root.id)
        if is_base:
            conn.execute(
                "INSERT INTO root_state(root_id,label,store,since,base_scan,base_files,"
                "last_scan,last_at,scans) VALUES(?,?,?,?,?,?,?,?,1)",
                (root.id, root.label, root.store, stamp, sid, n, sid, time.time()),
            )
        else:
            conn.execute(
                "UPDATE root_state SET last_scan=?, last_at=?, scans=scans+1, label=? WHERE root_id=?",
                (sid, time.time(), root.label, root.id),
            )
        conn.commit()
        say("✓ %s: %d صفًّا في %.1fث" % (root.label, n, time.time() - t0))

    # المفقود: ما لم يُرَ في هذا المسحِ من جذورٍ **مُسِحَت فعلًا** وحدَها
    gone = 0
    if scanned:
        marks = ",".join("?" * len(scanned))
        cur = conn.execute(
            "UPDATE file SET gone_at=? WHERE gone_at IS NULL AND last_seen < ? AND dir_id IN "
            "(SELECT id FROM dir WHERE root_id IN (%s))" % marks,
            [stamp, stamp, *scanned],
        )
        gone = cur.rowcount or 0

    added = conn.execute(
        "SELECT COUNT(*) FROM file WHERE first_scan=? AND is_baseline=0", (sid,)
    ).fetchone()[0]
    based = conn.execute(
        "SELECT COUNT(*) FROM file WHERE first_scan=? AND is_baseline=1", (sid,)
    ).fetchone()[0]
    changed = conn.execute(
        "SELECT COUNT(*) FROM file WHERE changed_at=? AND first_scan<>?", (stamp, sid)
    ).fetchone()[0]
    total_bytes = conn.execute(
        "SELECT COALESCE(SUM(size),0) FROM file WHERE gone_at IS NULL"
    ).fetchone()[0]
    finished = time.time()
    conn.execute(
        "UPDATE scan SET finished=?, seen=?, added=?, changed=?, gone=?, bytes=?, roots=?, "
        "skipped=?, secs=? WHERE id=?",
        (finished, seen, added, changed, gone, total_bytes, ",".join(scanned),
         ",".join(skipped), finished - stamp, sid),
    )
    db.set_meta(conn, "last_scan_at", finished)
    db.cache_stats(conn)          # الجمعُ الثقيلُ مرّةً هنا لا في كلِّ فتحةِ صفحة
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    return {
        "scan": sid, "baseline": bool(baseline), "baselined": fresh, "base_files": based,
        "seen": seen, "added": added, "changed": changed, "gone": gone, "bytes": total_bytes,
        "roots": scanned, "skipped": skipped, "secs": finished - stamp,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    from . import config as conf
    from .arabic import ar_num, ar_size

    ap = argparse.ArgumentParser(description="مسحُ المكتبات وتحديثُ سجلِّ الوصول")
    ap.add_argument("--config", default=None)
    ap.add_argument("--roots", default=None, help="جذورٌ بعينها مفصولةٌ بفاصلة (nas,d,e)")
    ap.add_argument("--note", default="")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    cfg = conf.load(args.config)
    roots = [s.strip() for s in args.roots.split(",")] if args.roots else None
    out = run(cfg, root_ids=roots, note=args.note,
              progress=None if args.quiet else lambda m: print(m, flush=True))
    print("— المسح %s —" % ar_num(out["scan"]))
    if out["baselined"]:
        print("   خطُّ أساسٍ أوّلُ لجذور (%s): %s ملفًّا لا تُحسَبُ وصولًا"
              % (", ".join(out["baselined"]), ar_num(out["base_files"])))
    print("   رُئي: %s · واصلٌ جديد: %s · متغيّر: %s · مفقود: %s" % (
        ar_num(out["seen"]), ar_num(out["added"]), ar_num(out["changed"]), ar_num(out["gone"])))
    print("   الحجم: %s · الزمن: %s ثانية" % (ar_size(out["bytes"]), ar_num(out["secs"], 1)))
    if out["skipped"]:
        print("   ⏭ غيرُ موصول (لم يُمسَح): %s" % ", ".join(out["skipped"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
