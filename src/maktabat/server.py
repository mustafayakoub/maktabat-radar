# -*- coding: utf-8 -*-
"""
الخادمُ المحليُّ لرادار المكتبات — مكتبةُ بايثون القياسيّةُ وحدَها (بلا أيِّ تبعيّة).

يُنصَتُ على 127.0.0.1 وحدَه، فلا تُرى مسارات مكتبةِ المؤلّفِ من الشبكة. وكلُّ ما يخرج
من الجهازِ لا شيء: البحثُ يسألُ Everything في الذاكرة، و«الجديد» يسألُ قاعدةً محلّيّة.

تقسيمُ العمل بين المصدرين — وهو جوهرُ التصميم:
  • **البحثُ** ⟵ Everything حيًّا (أحدثُ من أيِّ لقطة، ومقيسٌ ٠٫٠٨ث لآلافِ الصفوف).
  • **«متى وصل؟»** ⟵ سجلُّ الوصولِ المحليّ (لأنّ ختمَ المِلفِّ يكذب).
وتُدمَجُ الشهادتان في الصفِّ الواحد.
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import subprocess
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import arabic, config as conf, db, everything as ev, publish, scan as scanner, schedule, snapshot

WEB = Path(__file__).resolve().parents[2] / "web"
MAX_PAGE = 500

WINDOWS = {
    "hour": 3600, "day": 86400, "3days": 3 * 86400, "week": 7 * 86400,
    "month": 30 * 86400, "quarter": 90 * 86400, "year": 365 * 86400, "all": None,
}

SORTS = {
    "modified": ev.SORT_MODIFIED_DESC,
    "name": ev.SORT_NAME_ASC,
    "path": ev.SORT_PATH_ASC,
    "size": ev.SORT_SIZE_DESC,
}

_scan_state: dict = {"running": False, "lines": [], "result": None, "started": None}
_scan_lock = threading.Lock()
_ev_lock = threading.Lock()  # استعلامٌ واحدٌ في كلِّ لحظةٍ: نافذةُ IPC ليست للتزاحم


class Radar:
    def __init__(self, cfg: conf.Config):
        self.cfg = cfg

    # ── مساعداتٌ ─────────────────────────────────────────────────────────────
    def conn(self):
        return db.connect(self.cfg.db_path, read_only=True)

    def _enrich(self, rows: list[dict]) -> list[dict]:
        """يضمُّ شهادةَ سجلِّ الوصولِ (متى رآه الرادارُ أوّلَ مرّة) إلى صفوفِ Everything."""
        if not rows:
            return rows
        try:
            conn = self.conn()
        except Exception:
            return rows
        try:
            pairs: dict[tuple[str, str], dict] = {}
            for r in rows:
                folder, _, name = (r["path"] or "").rpartition("\\")
                r["dir"] = folder
                r["name"] = name
                pairs[(folder, name)] = r
            dirs = sorted({d for d, _ in pairs})
            for i in range(0, len(dirs), 400):
                chunk = dirs[i:i + 400]
                marks = ",".join("?" * len(chunk))
                sql = ("SELECT d.path AS dir, f.name, f.first_seen, f.is_baseline, f.changed_at, "
                       "d.shelf, d.store, d.root_id FROM file f JOIN dir d ON d.id=f.dir_id "
                       "WHERE d.path IN (%s)" % marks)
                for row in conn.execute(sql, chunk):
                    target = pairs.get((row["dir"], row["name"]))
                    if target is not None:
                        target["first_seen"] = row["first_seen"]
                        target["is_baseline"] = bool(row["is_baseline"])
                        target["changed_at"] = row["changed_at"]
                        target["shelf"] = row["shelf"]
                        target["store"] = row["store"]
                        target["root_id"] = row["root_id"]
        finally:
            conn.close()
        for r in rows:
            if "shelf" not in r:
                root = self.cfg.root_of(r["path"])
                r["root_id"] = root.id if root else None
                r["store"] = root.store if root else None
                r["shelf"] = self.cfg.shelf_of(r["path"], root)
            ext = r["path"].rpartition(".")[2].lower() if "." in r["path"] else ""
            r["ext"] = ext
            r["kind"] = self.cfg.type_of(ext)
        return rows

    # ── نقاطُ الواجهة ───────────────────────────────────────────────────────
    def state(self) -> dict:
        alive = ev.alive()
        out: dict = {
            "alive": alive,
            "roots": [{"id": r.id, "path": r.path, "label": r.label, "store": r.store}
                      for r in self.cfg.roots],
            "types": {k: v for k, v in self.cfg.types.items()},
            "exts": self.cfg.all_exts,
            "now": time.time(),
            "db": None,
            "scan": None,
            "root_states": [],
            "buckets": [],
            "totals": None,
            "watching_since": None,
            "live": {},
            "scan_running": _scan_state["running"],
        }
        if self.cfg.db_path.exists():
            conn = self.conn()
            try:
                last = db.last_scan(conn)
                out["scan"] = dict(last) if last else None
                out["root_states"] = db.root_states(conn)
                out["buckets"] = db.arrival_buckets(conn)
                out["totals"] = db.totals(conn)
                out["watching_since"] = db.watching_since(conn)
                out["db"] = {"path": str(self.cfg.db_path),
                             "bytes": self.cfg.db_path.stat().st_size}
            finally:
                conn.close()
        if alive:
            try:
                with _ev_lock:
                    out["live"] = {"scope": ev.count(self.cfg.scope())}
            except Exception as exc:
                out["live"] = {"error": str(exc)}
        return out

    def search(self, p: dict) -> dict:
        q = arabic.tidy(p.get("q", ""))
        tolerant = p.get("tolerant", "1") not in ("0", "false", "")
        limit = min(int(p.get("limit", 120) or 120), MAX_PAGE)
        offset = max(0, int(p.get("offset", 0) or 0))
        sort = SORTS.get(p.get("sort", "modified"), ev.SORT_MODIFIED_DESC)
        exts = [e for e in (p.get("ext") or "").split(",") if e]
        roots = [r for r in (p.get("root") or "").split(",") if r]
        if p.get("kind"):
            kinds = [k for k in p["kind"].split(",") if k]
            picked = [e for k in kinds for e in self.cfg.types.get(k, [])]
            exts = [e for e in exts if e in picked] if exts else picked
        if p.get("store"):
            stores = set(p["store"].split(","))
            ids = [r.id for r in self.cfg.roots if r.store in stores]
            roots = [r for r in roots if r in ids] if roots else ids

        extra_terms = []
        term = arabic.tolerant_query(q) if tolerant else q
        if term:
            extra_terms.append(term)
        if p.get("shelf"):
            for shelf in p["shelf"].split("|"):
                if shelf:
                    extra_terms.append('path:"\\%s\\"' % shelf.strip("\\"))
        window = WINDOWS.get(p.get("window") or "all")
        if window and p.get("measure") == "mtime":
            extra_terms.append("dm:>=%s" % _dm_literal(window))

        search = self.cfg.scope(root_ids=roots or None, exts=exts or None,
                               extra=" ".join(extra_terms))
        t0 = time.perf_counter()
        with _ev_lock:
            total, rows = ev.query(search, limit=limit, offset=offset, sort=sort)
        took = time.perf_counter() - t0
        return {
            "total": total, "rows": self._enrich([dict(r) for r in rows]),
            "took": took, "query": search, "offset": offset, "limit": limit,
            "source": "everything",
        }

    def recent(self, p: dict) -> dict:
        """«الجديد» بمقياسِ سجلِّ الوصول — من القاعدةِ المحلّيّة لا من ختمِ المِلفّ."""
        if not self.cfg.db_path.exists():
            return {"total": 0, "rows": [], "source": "ledger", "empty": "لا سجلَّ بعد — امسحْ أوّلًا"}
        secs = WINDOWS.get(p.get("window") or "day") or (365 * 86400 * 50)
        kind = p.get("list", "arrivals")
        limit = min(int(p.get("limit", 200) or 200), MAX_PAGE)
        offset = max(0, int(p.get("offset", 0) or 0))
        filters = {k: p.get(k) for k in ("store", "root", "shelf", "kind", "ext") if p.get(k)}
        since = time.time() - secs
        conn = self.conn()
        try:
            if kind == "gone":
                total, rows = db.departures(conn, since, limit=limit, offset=offset, **filters)
            elif kind == "changed":
                total, rows = db.changes(conn, since, limit=limit, offset=offset, **filters)
            else:
                total, rows = db.arrivals(conn, since, limit=limit, offset=offset,
                                          order=p.get("sort", "first_seen"), **filters)
            out = []
            needle = arabic.fold(arabic.tidy(p.get("q", "")))
            for r in rows:
                d = dict(r)
                d["path"] = d["dir"] + "\\" + d["name"]
                if needle and needle not in arabic.fold(d["name"]):
                    continue
                out.append(d)
            watching = db.watching_since(conn, list(filters.get("root", "").split(",")) or None)
        finally:
            conn.close()
        return {"total": total, "rows": out, "source": "ledger", "watching_since": watching}

    def shelves(self, p: dict) -> dict:
        if not self.cfg.db_path.exists():
            return {"rows": []}
        conn = self.conn()
        try:
            return {"rows": db.shelves(conn, limit=int(p.get("limit", 80) or 80))}
        finally:
            conn.close()

    def open_path(self, payload: dict) -> dict:
        """فتحُ المِلفِّ أو مجلّدِه في ويندوز — فعلٌ محلِّيٌّ على جهازِ المؤلّفِ وحدَه."""
        path = payload.get("path") or ""
        mode = payload.get("mode") or "folder"
        if not path or not self.cfg.root_of(path):
            return {"ok": False, "error": "مسارٌ خارجَ الجذورِ المرصودة"}
        if not os.path.exists(path):
            return {"ok": False, "error": "المسارُ غيرُ موجودٍ الآن"}
        try:
            if mode == "file":
                os.startfile(path)  # noqa: S606 — فتحٌ بالبرنامجِ المسجَّلِ في ويندوز
            else:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── مفتاحُ الصفحةِ الخاصّة ولقطتُها ───────────────────────────────────────
    def key_state(self) -> dict:
        """هل كُتِبَ المفتاح؟ — لا تُعادُ قيمتُه أبدًا، الوجودُ فقط."""
        key = snapshot.read_key()
        return {"exists": bool(key), "path": str(snapshot.KEY_FILE),
                "can_publish": publish.available(self.cfg)}

    def save_key(self, payload: dict) -> dict:
        """
        يكتبُ المفتاحَ في `secret.key` كما كتبه المؤلّفُ في صفحتِه المحلّيّة.
        ⛔ لا يُطبَعُ ولا يُسجَّلُ ولا يُعادُ في أيِّ ردّ — يُكتَبُ ويُنسى.
        """
        key = (payload.get("key") or "").strip()
        if not key:
            if snapshot.KEY_FILE.exists():
                snapshot.KEY_FILE.unlink()
                return {"ok": True, "cleared": True}
            return {"ok": False, "error": "لا مفتاحَ مكتوب"}
        if len(key) < 8:
            return {"ok": False, "error": "المفتاحُ قصيرٌ — ثمانيةُ محارفَ فأكثر"}
        snapshot.KEY_FILE.write_text(key + chr(10), encoding="utf-8")
        out = {"ok": True, "saved": True}
        # والسرُّ نفسُه على الموقع — فلا يكتبه المؤلّفُ مرّتين ولا يفتحُ لوحةَ تحكّم
        if payload.get("remote", True) and publish.available(self.cfg):
            out["remote"] = publish.set_secret(self.cfg, key)
        return out

    def push_snapshot(self, payload: dict) -> dict:
        key = snapshot.read_key()
        if not key:
            return {"ok": False, "error": "اكتبِ المفتاحَ أوّلًا"}
        try:
            data = snapshot.build(self.cfg)
            snapshot.write(data)
            out = snapshot.push(data, payload.get("url") or "https://radar.basaere.com", key)
            return {"ok": True, "sent": out,
                    "arrivals": len(data["arrivals"]), "gone": len(data["gone"])}
        except Exception as exc:
            return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}

    def start_scan(self, payload: dict) -> dict:
        with _scan_lock:
            if _scan_state["running"]:
                return {"ok": False, "error": "مسحٌ جارٍ بالفعل"}
            _scan_state.update(running=True, lines=[], result=None, started=time.time())

        roots = payload.get("roots") or None

        def work():
            try:
                out = scanner.run(self.cfg, root_ids=roots, note="من الصفحة",
                                  progress=lambda m: _scan_state["lines"].append(m))
                _scan_state["result"] = out
            except Exception as exc:
                _scan_state["result"] = {"error": str(exc)}
                _scan_state["lines"].append("⛔ " + str(exc))
            finally:
                _scan_state["running"] = False

        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    def scan_status(self) -> dict:
        return {
            "running": _scan_state["running"],
            "lines": _scan_state["lines"][-40:],
            "result": _scan_state["result"],
            "started": _scan_state["started"],
        }

    def export_csv(self, p: dict) -> bytes:
        data = self.recent(p) if p.get("src") == "ledger" else self.search(dict(p, limit=MAX_PAGE))
        buf = io.StringIO()
        buf.write("﻿الاسم,النوع,الصيغة,الحجم بالبايت,تاريخ التعديل,وصل إلينا,الرفّ,المخزن,المسار\n")
        for r in data["rows"]:
            cells = [
                r.get("name", ""), r.get("kind", ""), r.get("ext", ""), str(r.get("size") or ""),
                _iso(r.get("mtime")), _iso(r.get("first_seen")) if not r.get("is_baseline") else "",
                r.get("shelf", ""), r.get("store", ""), r.get("path", ""),
            ]
            buf.write(",".join('"%s"' % str(c).replace('"', '""') for c in cells) + "\n")
        return buf.getvalue().encode("utf-8")


def _iso(ts) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _dm_literal(secs: int) -> str:
    """صياغةُ تاريخٍ يفهمها Everything لحدِّ «منذ»."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - secs))


class Handler(BaseHTTPRequestHandler):
    server_version = "MaktabatRadar/1.0"
    radar: Radar = None  # يُضبَطُ عند الإقلاع

    def log_message(self, fmt, *args):  # صمتٌ إلّا الأخطاء
        if not str(args[0] if args else "").startswith(("GET /api/scan/status", "GET /assets")):
            return

    # ── أدواتُ الردّ ─────────────────────────────────────────────────────────
    def _json(self, payload, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._json({"error": "غير موجود"}, 404)
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if path.suffix in (".html", ".js", ".css") else "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def _guard(self) -> bool:
        """لا يُخدَمُ إلّا من هذا الجهاز — ولو أُسيءَ ضبطُ العنوانِ المُنصَتِ عليه."""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "[::1]", "::1"):
            self._json({"error": "الرادارُ محلِّيٌّ فقط"}, 403)
            return False
        return True

    # ── الطرقُ ───────────────────────────────────────────────────────────────
    def do_GET(self):
        if not self._guard():
            return
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        try:
            if route in ("/", "/index.html"):
                self._file(WEB / "index.html")
            elif route.startswith("/assets/"):
                rel = route[len("/assets/"):]
                target = (WEB / rel).resolve()
                if WEB.resolve() not in target.parents and target != WEB.resolve():
                    self._json({"error": "ممنوع"}, 403)
                    return
                self._file(target)
            elif route == "/api/state":
                self._json(self.radar.state())
            elif route == "/api/search":
                self._json(self.radar.search(params))
            elif route == "/api/recent":
                self._json(self.radar.recent(params))
            elif route == "/api/shelves":
                self._json(self.radar.shelves(params))
            elif route == "/api/schedule":
                self._json(schedule.status())
            elif route == "/api/key":
                self._json(self.radar.key_state())
            elif route == "/api/scan/status":
                self._json(self.radar.scan_status())
            elif route == "/api/export.csv":
                body = self.radar.export_csv(params)
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition",
                                 'attachment; filename="maktabat-radar-%s.csv"'
                                 % time.strftime("%Y-%m-%d-%H%M"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json({"error": "لا مسارَ بهذا الاسم"}, 404)
        except ev.NotRunning as exc:
            self._json({"error": str(exc), "everything": False}, 503)
        except Exception as exc:
            traceback.print_exc()
            self._json({"error": "%s: %s" % (type(exc).__name__, exc)}, 500)

    def do_POST(self):
        if not self._guard():
            return
        route = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        try:
            if route == "/api/open":
                self._json(self.radar.open_path(payload))
            elif route == "/api/scan":
                self._json(self.radar.start_scan(payload))
            elif route == "/api/key":
                self._json(self.radar.save_key(payload))
            elif route == "/api/snapshot":
                self._json(self.radar.push_snapshot(payload))
            elif route == "/api/schedule":
                if payload.get("remove"):
                    self._json(schedule.remove())
                else:
                    self._json(schedule.install(payload.get("minutes", 60)))
            else:
                self._json({"error": "لا مسارَ بهذا الاسم"}, 404)
        except Exception as exc:
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)


def serve(cfg: conf.Config | None = None, *, open_browser: bool = True) -> None:
    cfg = cfg or conf.load()
    Handler.radar = Radar(cfg)
    srv = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    url = "http://%s:%d/" % (cfg.host, cfg.port)
    print("رادار المكتبات يعمل على %s" % url)
    print("  Everything: %s" % ("حيٌّ" if ev.alive() else "⛔ غيرُ مشتغل"))
    print("  القاعدة: %s%s" % (cfg.db_path, "" if cfg.db_path.exists() else " (لا سجلَّ بعد — شغّل المسح)"))
    print("  للإيقاف: Ctrl+C")
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nتوقّف الرادار.")
    finally:
        srv.server_close()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="خادمُ رادار المكتبات المحلّيّ")
    ap.add_argument("--config", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    cfg = conf.load(args.config)
    if args.port:
        cfg.port = args.port
    serve(cfg, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
