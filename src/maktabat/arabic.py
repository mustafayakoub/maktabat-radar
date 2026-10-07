# -*- coding: utf-8 -*-
"""
العربيّةُ في الرادار: تطبيعٌ وتسامحٌ في البحث، وأرقامٌ هنديّةٌ في العرض.

مقيسٌ على فهرسِ المؤلّف (١٢٬٠٢٢٬١٢٣ ملفًّا · 2026-10-07):
    • Everything **يطوي** همزاتِ الألف (أ إ آ ٱ ← ا) والألفَ الممدودة:
      «الاعجاز» و«الإعجاز» ٥٬٦٨٧ لكلتيهما.
    • و**لا يطوي**: التشكيلَ («مُحَمَّد» ٢٩ ملفًّا لا يراها بحثُ «محمد» وفيه ٢٣٧٬٣٢٦) ·
      الياءَ المقصورةَ (الفتاوى ٣٬٧١٧ / الفتاوي ١٥٠) · التاءَ المربوطةَ (الرسالة ١٧٬٠٠٩ /
      الرساله ٤٣٠) · التطويلَ · الياءَ الفارسيّة (تفسیر ٥٣٣).
فالتسامحُ يُبنى على ما لا يطويه هو — لا على كلِّ شيءٍ، لئلّا يُثقَلَ الاستعلامُ بلا عائد.

⛔ قاعدةٌ دائمة: تُبنى أصنافُ المحارفِ بنقاطِ الترميزِ (`chr`) لا بلصقِ حروفٍ عربيّةٍ في
   مدًى داخلَ `[...]`؛ فالمدى العربيُّ ينقلبُ بصريًّا عند النسخ فيصير `[ي-ا]` مدًى مقلوبًا.
"""
from __future__ import annotations

import re

# ── نقاطُ الترميز ────────────────────────────────────────────────────────────
TATWEEL = chr(0x0640)
_TASHKEEL_RANGES = ((0x064B, 0x065F), (0x0670, 0x0670), (0x06D6, 0x06ED), (0x08D3, 0x08E1), (0x08E3, 0x08FF))
TASHKEEL = frozenset(
    chr(c) for lo, hi in _TASHKEEL_RANGES for c in range(lo, hi + 1)
) | {TATWEEL, chr(0x200C), chr(0x200D), chr(0x200F), chr(0x200E)}

_ALEF = tuple(chr(c) for c in (0x0627, 0x0623, 0x0625, 0x0622, 0x0671, 0x0672, 0x0673))
_YA = tuple(chr(c) for c in (0x064A, 0x0649, 0x06CC, 0x0626, 0x06D2, 0x0620))
_WAW = tuple(chr(c) for c in (0x0648, 0x0624, 0x06C6, 0x06C7, 0x06CB))
_HA = tuple(chr(c) for c in (0x0647, 0x0629, 0x06C1, 0x06D5, 0x06BE))
_KAF = tuple(chr(c) for c in (0x0643, 0x06A9, 0x06AA, 0x06AB))
_LAM = tuple(chr(c) for c in (0x0644, 0x06B5, 0x06B6))
_HAMZA = tuple(chr(c) for c in (0x0621, 0x0674))

# صنفٌ لكلِّ حرفٍ له أشباه — المفتاحُ أيُّ عضوٍ من الصنف
_CLASSES: dict[str, tuple[str, ...]] = {}
for _group in (_ALEF, _YA, _WAW, _HA, _KAF, _LAM):
    for _ch in _group:
        _CLASSES[_ch] = _group

# التطبيعُ للمقارنةِ والتخزين (لا للبحثِ في Everything)
_FOLD = {}
for _ch in _ALEF:
    _FOLD[_ch] = chr(0x0627)
for _ch in _YA:
    _FOLD[_ch] = chr(0x064A)
for _ch in _WAW:
    _FOLD[_ch] = chr(0x0648)
for _ch in _HA:
    _FOLD[_ch] = chr(0x0647)
for _ch in _KAF:
    _FOLD[_ch] = chr(0x0643)
for _ch in _HAMZA:
    _FOLD[_ch] = ""
for _ch in TASHKEEL:
    _FOLD[_ch] = ""
# الأرقامُ الهنديّةُ والفارسيّةُ ← عربيّةٌ غربيّةٌ في المفتاح
for _i in range(10):
    _FOLD[chr(0x0660 + _i)] = str(_i)
    _FOLD[chr(0x06F0 + _i)] = str(_i)

_TRANS_FOLD = str.maketrans(_FOLD)


def fold(text: str) -> str:
    """نصٌّ مطبَّعٌ للمقارنة: بلا تشكيلٍ ولا تطويل، والهمزاتُ والياءاتُ والهاءاتُ موحَّدة."""
    return (text or "").translate(_TRANS_FOLD).casefold()


def needs_tolerance(word: str) -> bool:
    """هل في الكلمةِ ما لا يطويه Everything من نفسه؟ (فلا نُثقِلَ استعلامًا بلا سبب)"""
    return any(ch in TASHKEEL or ch in _CLASSES for ch in word)


_RE_META = set(r"\^$.[]|()?*+{}")
_SEP = "[%s]*" % "".join(
    r"\x{%04x}-\x{%04x}" % (lo, hi) for lo, hi in ()
)  # غيرُ مستخدم: محرّكُ Everything لا يعرف \x{..} — نكتب المحارفَ صريحةً أدناه


def _tashkeel_class() -> str:
    """صنفُ التشكيلِ والتطويلِ مكتوبًا بمحارفه (محرّكُ Everything لا يعرف `\\x{…}`)."""
    chars = []
    for lo, hi in _TASHKEEL_RANGES:
        for c in range(lo, hi + 1):
            chars.append(chr(c))
    chars.append(TATWEEL)
    return "[" + "".join(chars) + "]*"


_TASH_OPT = _tashkeel_class()


def _esc(ch: str) -> str:
    return "\\" + ch if ch in _RE_META else ch


def tolerant_pattern(word: str) -> str:
    """
    يبني تعبيرًا نمطيًّا لكلمةٍ واحدةٍ يتسامح مع التشكيلِ والتطويلِ وأشباهِ الحروف.
    «محمد» ⟵ م[تشكيل]*ح[تشكيل]*م[تشكيل]*د  فتُدرَكُ «مُحَمَّد» و«محـمـد».
    """
    parts = []
    letters = [ch for ch in word if ch not in TASHKEEL]
    for i, ch in enumerate(letters):
        group = _CLASSES.get(ch)
        parts.append("[" + "".join(group) + "]" if group else _esc(ch))
        if i < len(letters) - 1:
            parts.append(_TASH_OPT)
    return "".join(parts)


def tolerant_query(text: str) -> str:
    """
    يحوّلُ ما كتبه المؤلّفُ إلى استعلامِ Everything متسامح. كلُّ كلمةٍ حدٌّ مستقلٌّ
    (فالفراغُ عند Everything «و») وما كان من صياغةِ Everything نفسِها (`ext:` · `!` ·
    `<` · `"`) يُمرَّرُ كما هو بلا لمسٍ — ليبقى بابُ الصياغةِ الكاملةِ مفتوحًا.
    """
    out = []
    for token in (text or "").split():
        if ":" in token or token[0] in "!<>|\"(" or token.startswith("regex:"):
            out.append(token)
        elif needs_tolerance(token):
            out.append("regex:" + tolerant_pattern(token))
        else:
            out.append(token)
    return " ".join(out)


# ── الأرقامُ والمقاديرُ في العرض ─────────────────────────────────────────────
_AR_DIGITS = str.maketrans("0123456789", "".join(chr(0x0660 + i) for i in range(10)))


def ar_num(n: int | float | None, decimals: int = 0) -> str:
    """رقمٌ هنديٌّ بفاصلِ آلافٍ «٬» وفاصلةٍ عشريّةٍ «٫»."""
    if n is None:
        return "—"
    s = f"{n:,.{decimals}f}"
    return s.replace(",", "٬").replace(".", "٫").translate(_AR_DIGITS)


def ar_size(nbytes: int | None) -> str:
    """حجمٌ بوحدةٍ عربيّة — عشريٌّ (÷١٠٠٠) موافقًا لما تعرضه ويندوز في خصائصِ المِلفّ."""
    if nbytes is None:
        return "—"
    units = ((1e12, "ت.ب"), (1e9, "ج.ب"), (1e6, "م.ب"), (1e3, "ك.ب"))
    for scale, unit in units:
        if nbytes >= scale:
            return "%s %s" % (ar_num(nbytes / scale, 1 if nbytes < scale * 100 else 0), unit)
    return "%s بايت" % ar_num(nbytes)


def ar_ago(seconds: float | None) -> str:
    """«قبل ٣ ساعات» — صياغةٌ عربيّةٌ صحيحةُ التثنيةِ والجمع."""
    if seconds is None:
        return "—"
    s = max(0, int(seconds))
    if s < 60:
        return "الآن"
    steps = ((60, "دقيقة", "دقيقتين", "دقائق"), (3600, "ساعة", "ساعتين", "ساعات"),
             (86400, "يوم", "يومين", "أيّام"), (86400 * 30, "شهر", "شهرين", "أشهر"),
             (86400 * 365, "سنة", "سنتين", "سنوات"))
    unit = 1
    label = steps[0]
    for size, *names in steps:
        if s >= size:
            unit, label = size, (size, *names)
    n = s // unit
    _, one, two, many = label
    if n == 1:
        return "قبل %s" % one
    if n == 2:
        return "قبل %s" % two
    if n <= 10:
        return "قبل %s %s" % (ar_num(n), many)
    return "قبل %s %s" % (ar_num(n), one)


_RE_WS = re.compile(r"\s+")


def tidy(text: str) -> str:
    return _RE_WS.sub(" ", (text or "").strip())
