# -*- coding: utf-8 -*-
"""
حارسُ رادار المكتبات — لا يُصدَّقُ وعدٌ في الصفحةِ حتّى يمرَّ هنا.

يُشغَّل:  PYTHONPATH=src python -m maktabat.verify [--server http://127.0.0.1:8731]
ويخرجُ بـ١ إن سقطَ بابٌ واحد.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import arabic, config as conf, db, everything as ev

OK, BAD = "✓", "⛔"
_fails: list[str] = []
_passes = 0


def check(label: str, cond: bool, detail: str = "") -> bool:
    global _passes
    if cond:
        _passes += 1
        print("  %s %s%s" % (OK, label, (" — " + detail) if detail else ""))
    else:
        _fails.append(label)
        print("  %s %s%s" % (BAD, label, (" — " + detail) if detail else ""))
    return cond


def section(title: str) -> None:
    print("\n" + title)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="حارسُ رادار المكتبات")
    ap.add_argument("--server", default=None, help="افحصِ الخادمَ الحيَّ أيضًا")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = conf.load(args.config)

    section("① الجسرُ إلى Everything")
    alive = ev.alive()
    check("Everything مشتغلٌ ونافذتُه موجودة", alive)
    if alive:
        t0 = time.perf_counter()
        n = ev.count("ext:pdf")
        check("العدُّ يردُّ رقمًا موجبًا", n > 0, "%s ملفَّ pdf في %s ثانية"
              % (arabic.ar_num(n), arabic.ar_num(time.perf_counter() - t0, 2)))
        tot, rows = ev.query("ext:pdf", limit=3)
        check("الصفُّ يحملُ مسارًا وحجمًا وتاريخًا",
              bool(rows) and all(r.get("path") and r.get("size") is not None for r in rows))
        check("التاريخُ معقولٌ (بين ١٩٩٠ وبعدَ الآنَ بيوم)",
              all(r.get("mtime") is None or 631152000 < r["mtime"] < time.time() + 86400 for r in rows))

    section("② التسامحُ العربيّ (ما لا يطويه Everything من نفسِه)")
    if alive:
        pairs = [("مُحَمَّد", "محمد"), ("الفتاوى", "الفتاوي")]
        for shakl, plain in pairs:
            raw = ev.count(shakl)
            tol = ev.count(arabic.tolerant_query(shakl))
            check("«%s» المتسامحُ يفوقُ الخامَّ" % shakl, tol > raw,
                  "%s ⟵ %s" % (arabic.ar_num(raw), arabic.ar_num(tol)))
        check("الصياغةُ الخاصّةُ بـEverything تُمرَّرُ بلا لمس",
              arabic.tolerant_query("ext:pdf محمد").startswith("ext:pdf"))
        check("الصنفُ يُبنى بنقاطِ الترميزِ لا بمدًى ملصوق",
              "-" not in arabic.tolerant_pattern("ايه").split("[")[1].split("]")[0])

    section("③ سجلُّ الوصول")
    if not cfg.db_path.exists():
        check("القاعدةُ موجودة", False, "لا سجلَّ بعد — شغّلْ `python -m maktabat.scan`")
    else:
        conn = db.connect(cfg.db_path, read_only=True)
        try:
            last = db.last_scan(conn)
            check("يوجدُ مسحٌ منتهٍ", last is not None)
            states = db.root_states(conn)
            check("لكلِّ جذرٍ ممسوحٍ خطُّ أساسٍ مسجَّل", bool(states),
                  "، ".join("%s منذ %s" % (s["root_id"], arabic.ar_ago(time.time() - s["since"]))
                            for s in states))
            base = conn.execute("SELECT COUNT(*) FROM file WHERE is_baseline=1").fetchone()[0]
            arr = conn.execute("SELECT COUNT(*) FROM file WHERE is_baseline=0").fetchone()[0]
            check("الخطُّ الأساسُ لا يُحسَبُ وصولًا", base > 0 and arr < base,
                  "أساسٌ %s مقابل واصلٍ %s" % (arabic.ar_num(base), arabic.ar_num(arr)))
            buckets = db.arrival_buckets(conn)
            mono = all(buckets[i]["count"] <= buckets[i + 1]["count"] for i in range(len(buckets) - 1))
            check("نوافذُ الجديدِ متزايدةٌ باتّساعِ المدّة", mono,
                  "، ".join("%s=%s" % (b["label"], arabic.ar_num(b["count"])) for b in buckets[:4]))
            if alive:
                live = ev.count(cfg.scope())
                stored = conn.execute("SELECT COUNT(*) FROM file WHERE gone_at IS NULL").fetchone()[0]
                drift = abs(live - stored)
                check("المسجَّلُ يطابقُ الفهرسَ الحيَّ (بفارقِ ما استجدَّ بعدَ المسح)",
                      drift <= max(50, live * 0.001),
                      "حيٌّ %s مقابلَ مسجَّلٍ %s" % (arabic.ar_num(live), arabic.ar_num(stored)))
            check("المخزونُ المحسوبُ مسبقًا حاضر", db.get_meta(conn, "stats_json") is not None)
        finally:
            conn.close()

    section("④ الخادمُ الحيّ")
    if not args.server:
        print("  (تُخطّى — مرّرْ --server http://127.0.0.1:8731 لفحصِها)")
    else:
        base = args.server.rstrip("/")

        def get(path):
            t0 = time.perf_counter()
            with urllib.request.urlopen(base + path, timeout=120) as r:
                return json.loads(r.read().decode("utf-8")), time.perf_counter() - t0

        try:
            st, took = get("/api/state")
            check("الحالةُ تردُّ بأقلَّ من ثانيتين", took < 2.0,
                  "%s ثانية" % arabic.ar_num(took, 2))
            check("الحالةُ تعلنُ حياةَ Everything", "alive" in st)
            srch, took = get("/api/search?" + urllib.parse.urlencode({"q": "تفسير", "limit": 5}))
            check("البحثُ يردُّ نتائجَ ومصدرَه", srch["total"] > 0 and srch["source"] == "everything",
                  "%s نتيجة في %s ثانية" % (arabic.ar_num(srch["total"]), arabic.ar_num(took, 2)))
            check("كلُّ صفٍّ يحملُ رفَّه ومخزنَه ونوعَه",
                  all(r.get("shelf") and r.get("store") and r.get("kind") for r in srch["rows"]))
            rec, _ = get("/api/recent?window=week&list=arrivals")
            check("قائمةُ الواصلِ تُعلنُ مصدرَها سجلًّا", rec["source"] == "ledger")
            # الخارجُ عن الجذورِ لا يُفتَح
            req = urllib.request.Request(
                base + "/api/open", method="POST",
                data=json.dumps({"path": "C:\\Windows\\notepad.exe", "mode": "file"}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read().decode("utf-8"))
            check("لا يُفتَحُ مسارٌ خارجَ الجذورِ المرصودة", out.get("ok") is False, out.get("error", ""))
        except urllib.error.URLError as exc:
            check("الخادمُ يستجيب", False, str(exc))

    print("\n" + "─" * 58)
    total = _passes + len(_fails)
    if _fails:
        print("%s سقطَ %d من %d: %s" % (BAD, len(_fails), total, "، ".join(_fails)))
        return 1
    print("%s مرَّ %d بابًا من %d." % (OK, _passes, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
