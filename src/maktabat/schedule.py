# -*- coding: utf-8 -*-
"""
الجدولةُ من داخلِ الصفحة: تثبيتُ مهمّةِ ويندوز وإيقافُها وقراءةُ حالتِها.

⚠ المهمّةُ تُسجَّلُ بحساب المؤلّفِ وتعملُ حين يكون داخلًا (`run only when user is logged
on`) — وهذا مقصودٌ لا نقص: مهمّةٌ تعملُ بحساب SYSTEM **لا ترى مشاركةَ السيرفر**، فتمسحُ
الهاردَ وحدَه ثمّ تحكمُ على ثلاثةِ ملايينِ ملفٍّ بالاختفاء. والتسجيلُ بالحسابِ الحاليِّ
لا يطلبُ كلمةَ سرٍّ ولا صلاحيّاتِ مديرِ النظام.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "tools" / "install_task.ps1"
TASK = "رادار المكتبات — مسحٌ دوريّ"

_QUERY = r"""
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'SilentlyContinue'
$t = Get-ScheduledTask -TaskName $env:MR_TASK
if (-not $t) { '{"exists": false}' ; exit 0 }
$i = Get-ScheduledTaskInfo -TaskName $env:MR_TASK
$rep = $t.Triggers[0].Repetition.Interval
[pscustomobject]@{
  exists   = $true
  state    = [string]$t.State
  interval = [string]$rep
  last     = if ($i.LastRunTime) { $i.LastRunTime.ToString('o') } else { $null }
  next     = if ($i.NextRunTime) { $i.NextRunTime.ToString('o') } else { $null }
  result   = $i.LastTaskResult
} | ConvertTo-Json -Compress
"""


def _ps(args: list[str], env_extra: dict | None = None, timeout: int = 90) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ)
    env["MR_TASK"] = TASK
    env.update(env_extra or {})
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env,
    )


def _iso_minutes(interval: str | None) -> int | None:
    """يحوّلُ مدّةَ ISO-8601 (PT1H · PT30M) إلى دقائق."""
    if not interval:
        return None
    import re
    m = re.match(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", interval.strip())
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    total = d * 1440 + h * 60 + mi + (1 if s and not (d or h or mi) else 0)
    return total or None


def status() -> dict:
    try:
        out = _ps(["-Command", _QUERY])
    except Exception as exc:
        return {"exists": False, "error": str(exc)}
    text = (out.stdout or "").strip()
    if not text:
        return {"exists": False, "error": (out.stderr or "").strip()[:200] or None}
    try:
        data = json.loads(text)
    except Exception:
        return {"exists": False, "error": text[:200]}
    if data.get("exists"):
        data["minutes"] = _iso_minutes(data.get("interval"))
    return data


def install(minutes: int) -> dict:
    minutes = max(5, min(int(minutes), 7 * 24 * 60))
    if not PS1.exists():
        return {"ok": False, "error": "لم أجد %s" % PS1}
    out = _ps(["-File", str(PS1), "-EveryMinutes", str(minutes), "-TaskName", TASK], timeout=150)
    ok = out.returncode == 0
    return {"ok": ok, "minutes": minutes,
            "message": (out.stdout or "").strip() or (out.stderr or "").strip()[:400]}


def remove() -> dict:
    out = _ps(["-File", str(PS1), "-Remove", "-TaskName", TASK], timeout=120)
    return {"ok": out.returncode == 0,
            "message": (out.stdout or "").strip() or (out.stderr or "").strip()[:400]}


def run_now() -> dict:
    out = _ps(["-Command", "Start-ScheduledTask -TaskName $env:MR_TASK"], timeout=60)
    return {"ok": out.returncode == 0, "message": (out.stderr or "").strip()[:300]}
