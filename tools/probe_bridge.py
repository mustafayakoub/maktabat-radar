# -*- coding: utf-8 -*-
"""فحصُ بابِ الجسر: أيفتحُ للأصلِ المسمّى وحدَه بالترويسة، ويُغلقُ على ما عداه؟"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8731"
OK_ORIGIN = "https://radar.basaere.com"
ok, bad = 0, []


def check(label, cond, detail=""):
    global ok
    if cond:
        ok += 1
        print("  ✓ %s%s" % (label, (" — " + detail) if detail else ""))
    else:
        bad.append(label)
        print("  ⛔ %s%s" % (label, (" — " + detail) if detail else ""))


def go(path, headers=None, data=None, method=None):
    req = urllib.request.Request(BASE + path, headers=headers or {}, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


print("① البابُ يُغلَقُ على غيرِ المسمّى")
st, b, h = go("/api/ping", {"Origin": "https://evil.example", "X-Maktabat-Local": "1"})
check("أصلٌ غريبٌ يُرَدّ", st == 403, "رمز %d" % st)
st, b, h = go("/api/ping", {"Origin": OK_ORIGIN})
check("الأصلُ المسمّى بلا ترويسةٍ يُرَدّ", st == 403, "رمز %d" % st)
st, b, h = go("/api/ping", {"Origin": "http://radar.basaere.com", "X-Maktabat-Local": "1"})
check("بروتوكولٌ مختلفٌ (http) يُرَدّ", st == 403, "رمز %d" % st)

print("② ويُفتَحُ للمسمّى بالترويسة")
st, b, h = go("/api/ping", {"Origin": OK_ORIGIN, "X-Maktabat-Local": "1"})
allow = h.get("Access-Control-Allow-Origin")
check("النبضةُ تُجاب", st == 200 and json.loads(b).get("ok"), "رمز %d" % st)
check("ترويسةُ السماحِ للأصلِ المسمّى وحدَه", allow == OK_ORIGIN, str(allow))

print("③ الإذنُ المسبَق (preflight)")
st, b, h = go("/api/open_by_name", {
    "Origin": OK_ORIGIN, "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type,x-maktabat-local",
    "Access-Control-Request-Private-Network": "true"}, method="OPTIONS")
check("يُجابُ بـ204", st == 204, "رمز %d" % st)
check("يسمحُ بالترويسةِ الخاصّة",
      "x-maktabat-local" in (h.get("Access-Control-Allow-Headers") or "").lower())
check("يأذنُ بالشبكةِ الخاصّة (شرطُ كروم)",
      (h.get("Access-Control-Allow-Private-Network") or "") == "true")
st, b, h = go("/api/open_by_name", {"Origin": "https://evil.example",
                                    "Access-Control-Request-Method": "POST"}, method="OPTIONS")
check("الإذنُ المسبَقُ يُرفَضُ لغيرِ المسمّى", st == 403, "رمز %d" % st)

print("④ الفتحُ بالاسم")
body = json.dumps({"name": "لا-يوجد-كتاب-بهذا-الاسم.pdf", "shelf": "وهم"}).encode()
st, b, h = go("/api/open_by_name", {"Origin": OK_ORIGIN, "X-Maktabat-Local": "1",
                                    "Content-Type": "application/json"}, data=body, method="POST")
check("اسمٌ غيرُ موجودٍ يُعلَنُ لا يُفتَح", st == 200 and not json.loads(b).get("ok"),
      json.loads(b).get("error", "")[:40])

print()
print(("⛔ سقط: " + "، ".join(bad)) if bad else "✓ مرَّ %d بابًا — الجسرُ يفتحُ لواحدٍ ويُغلقُ على غيره." % ok)
raise SystemExit(1 if bad else 0)
