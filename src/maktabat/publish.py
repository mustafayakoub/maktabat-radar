# -*- coding: utf-8 -*-
"""
ضبطُ سرِّ الصفحةِ الخاصّةِ على Cloudflare من الصفحةِ المحلّيّةِ — بلا طرفيّةٍ ولا لوحةِ تحكّم.

⛔ المفتاحُ **لا يمرُّ في سطرِ الأوامر** (سطورُ الأوامرِ تُقرَأُ من قائمةِ العمليّات)،
   بل عبرَ المدخلِ القياسيِّ إلى `wrangler`. ولا يُطبَعُ ولا يُسجَّلُ هنا البتّة.
   وإن ظهرَ في مخرَجِ الأداةِ نفسِها شيءٌ منه نُقِّيَ قبل الإعادة.

يحتاجُ قسمَ `publish` في `config.json`:
    "publish": { "wrangler_dir": "...", "project": "marsad-quran",
                 "secret": "MAKTABAT_KEY", "url": "https://radar.basaere.com" }
وإن غابَ فالزرُّ يقولُ إنّ الضبطَ بيدِ المؤلّفِ ولا يحاول.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def settings(cfg) -> dict:
    raw = {}
    if cfg.source and Path(cfg.source).exists():
        try:
            raw = json.loads(Path(cfg.source).read_text(encoding="utf-8")).get("publish", {}) or {}
        except Exception:
            raw = {}
    return {
        "dir": raw.get("wrangler_dir"),
        "project": raw.get("project"),
        "secret": raw.get("secret", "MAKTABAT_KEY"),
        "url": raw.get("url", "https://radar.basaere.com"),
    }


def available(cfg) -> bool:
    s = settings(cfg)
    return bool(s["dir"] and s["project"] and Path(s["dir"]).is_dir())


def _scrub(text: str, key: str) -> str:
    return (text or "").replace(key, "«المفتاح»")


def set_secret(cfg, key: str, timeout: int = 240) -> dict:
    """يضبطُ السرَّ على مشروع Pages. يعيدُ {ok, message} بلا أثرٍ للمفتاح."""
    s = settings(cfg)
    if not available(cfg):
        return {"ok": False, "error": "لا إعداداتِ نشرٍ في config.json — الضبطُ بيدك"}
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        return {"ok": False, "error": "npx غيرُ موجودٍ في المسار"}
    try:
        out = subprocess.run(
            [npx, "--no-install", "wrangler", "pages", "secret", "put", s["secret"],
             "--project-name", s["project"]],
            input=key + "\n", cwd=s["dir"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "لم تستجبْ أداةُ wrangler خلال %d ث" % timeout}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    blob = _scrub((out.stdout or "") + "\n" + (out.stderr or ""), key)
    ok = out.returncode == 0
    tail = [ln for ln in blob.splitlines() if ln.strip()][-3:]
    return {"ok": ok, "message": " · ".join(tail)[:400] or ("ضُبط" if ok else "تعذّر")}
