# -*- coding: utf-8 -*-
"""فحصُ حارسِ اللقطة: أيعضُّ على تسريبٍ حقيقيٍّ ويسكتُ عن اسمٍ مشروع؟"""
import sys

sys.path.insert(0, r"C:\maktabat-radar\src")
from maktabat import config as conf, snapshot  # noqa: E402

cfg = conf.load()
B = chr(92)
ok, bad = 0, []


def case(label, mutate, should_fail):
    global ok
    payload = {"shelves": [{"shelf": "مخطوط"}], "arrivals": [{"n": "كتاب.pdf", "s": "رفّ"}],
               "roots": [{"label": "السيرفر"}]}
    mutate(payload)
    try:
        snapshot._assert_clean(payload, cfg)
        failed = False
        why = ""
    except ValueError as exc:
        failed = True
        why = str(exc)[:70]
    good = failed == should_fail
    print("  %s %-44s %s" % ("✓" if good else "⛔", label, why if failed else "مرّت"))
    if good:
        ok += 1
    else:
        bad.append(label)


print("يجبُ أن يعضّ:")
case("مسارٌ كاملٌ في رفّ", lambda p: p["shelves"].append({"shelf": "D:" + B + "كتب"}), True)
case("مسارُ شبكةٍ في اسم", lambda p: p["arrivals"].append({"n": B * 2 + "m27" + B + "m21" + B + "a.pdf"}), True)
case("اسمُ المشاركةِ في وسمِ جذر", lambda p: p["roots"].append({"label": "السيرفر m21"}), True)
case("اسمُ الخادمِ في رفّ", lambda p: p["shelves"].append({"shelf": "m27"}), True)
case("فاصلُ مسارٍ وحدَه", lambda p: p["arrivals"].append({"s": "كتب" + B + "فقه"}), True)
case("مسارٌ بشرطةٍ أماميّة", lambda p: p["shelves"].append({"shelf": "C:/Users"}), True)

print("ويجبُ أن يسكت:")
case("رفٌّ اسمُه Users (مشروع)", lambda p: p["shelves"].append({"shelf": "Users"}), False)
case("كتابٌ عنوانُه فيه Users", lambda p: p["arrivals"].append({"n": "Users Guide to Arabic.pdf"}), False)
case("رفٌّ اسمُه Downloads", lambda p: p["shelves"].append({"shelf": "Downloads"}), False)
case("رفٌّ عربيٌّ عاديّ", lambda p: p["shelves"].append({"shelf": "رسائل جامعية"}), False)
case("اسمُ كتابٍ فيه نقطتان", lambda p: p["arrivals"].append({"n": "الفقه: مدخل.pdf"}), False)

print()
print(("⛔ سقط: " + "، ".join(bad)) if bad else "✓ مرَّ %d بابًا — الحارسُ يعضُّ ويسكتُ في موضعه." % ok)
raise SystemExit(1 if bad else 0)
