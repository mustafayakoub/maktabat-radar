# -*- coding: utf-8 -*-
"""
لقطةُ الرادار: ما يُرفَعُ إلى الصفحةِ الخاصّةِ على radar.basaere.com ليراها المؤلّفُ
من جوّاله خارجَ البيت.

⛔ **لا مسارَ يخرجُ من هذا الجهاز.** يخرجُ اسمُ الكتابِ ورفُّه ومخزنُه ونوعُه وحجمُه
وتاريخاه — لا المسارُ الكاملُ ولا بنيةُ المجلّدات. والرفعُ لا يتمُّ إلّا بمفتاحٍ يكتبه
المؤلّفُ بيدِه في `secret.key` (مستثنًى من غيت، ولا يُطلَبُ في محادثةٍ ولا يُكتَبُ فيها).
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

from . import config as conf, db

ROOT = Path(__file__).resolve().parents[2]
KEY_FILE = ROOT / "secret.key"
OUT = ROOT / "data" / "snapshot.json"
MAX_ARRIVALS = 600
MAX_GONE = 120


def _row(r) -> dict:
    """صفٌّ بلا مسار — الاسمُ والرفُّ وحدَهما يكفيان لمعرفةِ ما وصل."""
    return {
        "n": r["name"],
        "s": r["shelf"],
        "st": r["store"],
        "k": r["kind"],
        "e": r["ext"],
        "z": r["size"],
        "m": r["mtime"],
        "f": r["first_seen"],
        "g": r["gone_at"],
    }


def _safe_root(r) -> dict:
    """
    وسمُ الجذرِ قد يحملُ اسمَ مشاركةِ الشبكةِ («السيرفر m21») — ولا حاجةَ به خارجَ
    الجهاز. فيُستبدَلُ باسمٍ عامٍّ لجذورِ الشبكة، ويبقى للأقراصِ المحلّيّةِ وسمُها.
    """
    out = dict(r)
    if out.get("store") == "nas":
        out["label"] = "السيرفر"
    out.pop("base_scan", None)
    return out


def _walk(node, path=()):
    """يمرُّ على كلِّ قيمةٍ نصّيّةٍ في اللقطةِ ومعها موضعُها."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk(item, path)
    elif isinstance(node, str):
        yield path, node


# حقولٌ تحملُ أسماءَ ملفّاتٍ وضعها المؤلّفُ — كلمةٌ عامّةٌ فيها عنوانٌ لا مسار
_NAME_FIELDS = {"n"}
_SEP = (chr(92), "/")


def _assert_clean(payload: dict, cfg: conf.Config) -> None:
    """حارسٌ في الأداةِ لا في المراجعة — ويرفعُ موضعَ التسريبِ لا مجرّدَ وجودِه."""
    # أسماءُ الرفوفِ **هي** أسماءُ مجلّداتٍ بالتصميم (اختارها المؤلّف)، فمنعُ كلِّ مقطعٍ
    # من مسارٍ محلّيٍّ يرفضُ رفًّا مشروعًا اسمُه «Users» مثلًا. المقاطعُ الممنوعةُ هي
    # هُويّةُ مشاركةِ الشبكةِ وحدَها (الخادمُ والمشاركة) — وهي التي سرّبت «m21» من قبل،
    # ولا تصلحُ اسمَ رفٍّ أبدًا. وما عداها يكفيه منعُ فاصلِ المسارِ وصيغةِ القرص.
    segs = set()
    for root in cfg.roots:
        p = root.path.replace("/", chr(92))
        if p.startswith(chr(92) * 2):
            for part in p[2:].split(chr(92))[:2]:
                if part:
                    segs.add(part.casefold())

    leaks = []
    for where, text in _walk(payload):
        field = where[-1] if where else ""
        # ① فاصلُ مسارٍ أو صيغةُ قرصٍ في أيِّ قيمةٍ كانت = مسارٌ تسرّب
        if any(sep in text for sep in _SEP) or re.search(r"(?i)\b[a-z]:[\\/]", text):
            leaks.append("%s ⟵ %s" % (".".join(where) or "?", text[:60]))
            continue
        # ② وأجزاءُ مسارِ الجذورِ في الحقولِ البنيويّةِ وحدَها
        if field in _NAME_FIELDS:
            continue
        low = text.casefold()
        hit = next((p for p in segs if p in low), None)
        if hit:
            leaks.append("%s ⟵ «%s» في %s" % (".".join(where) or "?", hit, text[:40]))

    if leaks:
        raise ValueError("اللقطةُ تحملُ مسارًا: " + " · ".join(leaks[:5]))


def build(cfg: conf.Config | None = None) -> dict:
    cfg = cfg or conf.load()
    if not cfg.db_path.exists():
        raise FileNotFoundError("لا سجلَّ بعد — شغّلِ المسحَ أوّلًا")
    conn = db.connect(cfg.db_path, read_only=True)
    try:
        now = time.time()
        year = now - 365 * 86400
        _, arrivals = db.arrivals(conn, year, limit=MAX_ARRIVALS)
        _, gone = db.departures(conn, year, limit=MAX_GONE)
        last = db.last_scan(conn)
        payload = {
            "v": 1,
            "at": now,
            "watching_since": db.watching_since(conn),
            "totals": db.totals(conn),
            "buckets": db.arrival_buckets(conn, now),
            "shelves": db.shelves(conn, limit=60),
            "roots": [_safe_root(r) for r in db.root_states(conn)],
            "scan": dict(last) if last else None,
            "arrivals": [_row(r) for r in arrivals],
            "gone": [_row(r) for r in gone],
        }
    finally:
        conn.close()
    _assert_clean(payload, cfg)
    return payload


def write(payload: dict, path: Path | None = None) -> Path:
    path = path or OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def push(payload: dict, url: str, key: str, timeout: int = 90) -> dict:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # ⚠ ترويسةُ HTTP لاتينيّةٌ إلزامًا، والمفتاحُ قد يكون عربيًّا — فيُرمَّزُ ويُفكُّ في الوظيفة
    import urllib.parse
    req = urllib.request.Request(
        url.rstrip("/") + "/maktabat/push", data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "X-Maktabat-Key": urllib.parse.quote(key, safe=""),
                 "User-Agent": "MaktabatRadar/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def read_key() -> str | None:
    """المفتاحُ من `secret.key` بيدِ المؤلّفِ وحدَه — ولا يُطبَعُ في أيِّ مخرَج."""
    if KEY_FILE.exists():
        text = KEY_FILE.read_text(encoding="utf-8").strip()
        return text or None
    return None


def main(argv=None) -> int:
    import argparse
    from .arabic import ar_num, ar_size

    ap = argparse.ArgumentParser(description="بناءُ لقطةِ الرادارِ ورفعُها")
    ap.add_argument("--config", default=None)
    ap.add_argument("--url", default="https://radar.basaere.com", help="أصلُ الموقع")
    ap.add_argument("--push", action="store_true", help="ارفعْها بعد البناء")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    cfg = conf.load(args.config)
    payload = build(cfg)
    path = write(payload, Path(args.out) if args.out else None)
    size = path.stat().st_size
    print("اللقطة: %s — %s" % (path, ar_size(size)))
    print("   الواصلُ المرفوع: %s صفًّا · المفقود: %s · الرفوف: %s"
          % (ar_num(len(payload["arrivals"])), ar_num(len(payload["gone"])),
             ar_num(len(payload["shelves"]))))
    print("   ⛔ بلا مسارات: %s" % ("نعم" if not any("\\" in str(r.get("n", "")) for r in payload["arrivals"]) else "⚠ راجِع"))
    if args.push:
        key = read_key()
        if not key:
            print("⛔ لا مفتاح. اكتبْه بيدك في %s ثمّ أعِد." % KEY_FILE)
            return 1
        try:
            out = push(payload, args.url, key)
            print("   ✓ رُفعت: %s" % json.dumps(out, ensure_ascii=False))
        except Exception as exc:
            print("   ⛔ تعذّر الرفع: %s" % exc)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
