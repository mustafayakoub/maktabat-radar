# -*- coding: utf-8 -*-
"""
عميلُ Everything عبر IPC المباشر (WM_COPYDATA) — بلا `es.exe` ولا `Everything64.dll`
ولا خادمِ HTTP ولا تغييرِ أيِّ إعدادٍ في برنامجِ المؤلّف.

لماذا IPC؟ لأنّ البديلَين كلفةٌ بلا عائد:
  • `es.exe` يحتاج تنزيلًا من الشبكة، وإطلاقَ عمليّةٍ جديدةٍ في كلِّ استعلام (~٣٠ م.ث لكلِّ نداء).
  • خادمُ HTTP في Everything 1.4 معطَّلٌ عند المؤلّف، وتفعيلُه تغييرٌ في إعداداته وفتحُ منفذ.
وIPC يعطي المسارَ والحجمَ وتاريخَ التعديلَ في رسالةٍ واحدةٍ (مقيسٌ: ٤٬٩٠٣ صفًّا في ٠٫٠٨ث).

البروتوكول (EVERYTHING_IPC_COPYDATA_QUERY2W = 18):
    نافذةُ Everything صنفُها "EVERYTHING_TASKBAR_NOTIFICATION"
    الطلب : 7×DWORD (نافذةُ الردّ · رسالةُ الردّ · أعلامُ البحث · الإزاحة · السقف · الحقول · الترتيب)
            ثمّ نصُّ البحث UTF-16LE منتهيًا بصفر.
    الردّ  : 5×DWORD (الكلّ · المعروض · الإزاحة · الحقول · الترتيب) ثمّ لكلِّ صفٍّ 2×DWORD
            (الأعلام · إزاحةُ بياناته)، وبياناتُ الصفِّ بترتيبِ أعلامِ الحقولِ تصاعديًّا:
            نصٌّ = DWORD طولٌ بالمحارف + المحارف + صفرٌ خاتم؛ حجمٌ = int64؛ تاريخٌ = FILETIME.

⚠ مقيسٌ لا مخمَّن: ترويسةُ ردِّ QUERY2 خمسةُ حقولٍ لا تسعة (خلافًا لردِّ QUERY الأوّل).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import threading
import time

# ── واجهاتُ ويندوز ───────────────────────────────────────────────────────────
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_u32.DefWindowProcW.restype = ctypes.c_longlong
_u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, ctypes.c_ulonglong, ctypes.c_longlong]
_u32.FindWindowW.restype = wt.HWND
_u32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
_u32.CreateWindowExW.restype = wt.HWND
_u32.SendMessageW.restype = ctypes.c_longlong
_u32.SendMessageTimeoutW.restype = ctypes.c_longlong

WM_COPYDATA = 0x004A
EV_CLASS = "EVERYTHING_TASKBAR_NOTIFICATION"
IPC_QUERY2W = 18
REPLY_MSG = 0x0401
SMTO_ABORTIFHUNG = 0x0002

# حقولٌ تُطلَب (أعلامٌ تصاعديّةٌ تحدِّد ترتيبَ البيانات في الردّ)
F_NAME = 0x0001
F_PATH = 0x0002
F_FULL = 0x0004
F_EXT = 0x0008
F_SIZE = 0x0010
F_CREATED = 0x0020
F_MODIFIED = 0x0040
F_ATTRS = 0x0100
FIELDS_DEFAULT = F_FULL | F_SIZE | F_MODIFIED

# ترتيبٌ (EVERYTHING_IPC_SORT_*)
SORT_NAME_ASC = 1
SORT_PATH_ASC = 3
SORT_SIZE_DESC = 6
SORT_MODIFIED_DESC = 14
ALL_RESULTS = 0xFFFFFFFF

FILETIME_INVALID = 0xFFFFFFFFFFFFFFFF
_EPOCH_SHIFT = 11644473600  # ثوانٍ بين 1601 و1970


class _CopyData(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_void_p), ("cbData", wt.DWORD), ("lpData", ctypes.c_void_p)]


_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wt.HWND, wt.UINT, ctypes.c_ulonglong, ctypes.c_longlong)


class _WndClass(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT), ("lpfnWndProc", _WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
    ]


class EverythingError(RuntimeError):
    pass


class NotRunning(EverythingError):
    """برنامجُ Everything غيرُ مشتغل — لا فهرسَ نسأله."""


# ── نافذةُ الاستلام: واحدةٌ لكلِّ خيط (الردُّ يُسلَّم في خيطِ المرسِل نفسِه) ──
_local = threading.local()
_cls_lock = threading.Lock()
_cls_ready = False
_CLASS_NAME = "MaktabatRadar_EverythingIPC"
_keep_alive: list = []  # يمنع جامعَ المهملات من إتلافِ دوالِّ النداء الحيّة


def _ensure_class() -> int:
    global _cls_ready
    hinst = _k32.GetModuleHandleW(None)
    with _cls_lock:
        if _cls_ready:
            return hinst

        def proc(hwnd, msg, wparam, lparam):
            if msg == WM_COPYDATA:
                cds = ctypes.cast(lparam, ctypes.POINTER(_CopyData)).contents
                st = getattr(_local, "state", None)
                if st is not None:
                    st["data"] = ctypes.string_at(cds.lpData, cds.cbData)
                return 1
            return _u32.DefWindowProcW(hwnd, msg, wparam, lparam)

        cb = _WNDPROC(proc)
        _keep_alive.append(cb)
        wc = _WndClass()
        wc.lpfnWndProc = cb
        wc.lpszClassName = _CLASS_NAME
        wc.hInstance = hinst
        if not _u32.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise ctypes.WinError(err)
        _cls_ready = True
    return hinst


def _window() -> int:
    hwnd = getattr(_local, "hwnd", None)
    if hwnd:
        return hwnd
    hinst = _ensure_class()
    hwnd = _u32.CreateWindowExW(0, _CLASS_NAME, "ipc", 0, 0, 0, 0, 0, None, None, hinst, None)
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    _local.hwnd = hwnd
    _local.state = {}
    return hwnd


def alive() -> bool:
    """هل Everything مشتغلٌ الآن؟"""
    return bool(_u32.FindWindowW(EV_CLASS, None))


def _raw_query(search: str, *, limit: int, offset: int, fields: int, sort: int, timeout: float) -> bytes:
    target = _u32.FindWindowW(EV_CLASS, None)
    if not target:
        raise NotRunning("برنامج Everything غير مشتغل — شغّله ثمّ أعِد المحاولة")
    hwnd = _window()
    state = _local.state
    state.pop("data", None)

    payload = struct.pack(
        "<7I", hwnd & 0xFFFFFFFF, REPLY_MSG, 0, offset & 0xFFFFFFFF, limit & 0xFFFFFFFF, fields, sort
    ) + search.encode("utf-16-le") + b"\x00\x00"
    buf = ctypes.create_string_buffer(payload, len(payload))
    cds = _CopyData(ctypes.c_void_p(IPC_QUERY2W), len(payload), ctypes.cast(buf, ctypes.c_void_p))

    sent = ctypes.c_ulonglong(0)
    ok = _u32.SendMessageTimeoutW(
        target, WM_COPYDATA, wt.WPARAM(hwnd), ctypes.byref(cds),
        SMTO_ABORTIFHUNG, int(timeout * 1000), ctypes.byref(sent),
    )
    if not ok:
        raise EverythingError("Everything لم يستجب للاستعلام (مهلة %.0f ث)" % timeout)
    if sent.value == 0:
        # نسخةٌ لا تعرف QUERY2 (أقدمُ من 1.4) — لا تخمينَ ولا سقوطٌ صامت
        raise EverythingError("نسخةُ Everything لا تدعم استعلامَ QUERY2 (يلزم 1.4 أو أحدث)")

    msg = wt.MSG()
    deadline = time.monotonic() + timeout
    while "data" not in state and time.monotonic() < deadline:
        while _u32.PeekMessageW(ctypes.byref(msg), _local.hwnd, 0, 0, 1):
            _u32.TranslateMessage(ctypes.byref(msg))
            _u32.DispatchMessageW(ctypes.byref(msg))
        if "data" in state:
            break
        time.sleep(0.002)
    data = state.pop("data", None)
    if data is None:
        raise EverythingError("لم يصل ردُّ Everything خلال %.0f ث" % timeout)
    if len(data) < 20:
        raise EverythingError("ردٌّ مبتورٌ من Everything (%d بايت)" % len(data))
    return data


def _parse(data: bytes) -> tuple[int, list[dict]]:
    total, shown, _offset, fields, _sort = struct.unpack_from("<5I", data, 0)
    out: list[dict] = []
    for i in range(shown):
        flags, p = struct.unpack_from("<2I", data, 20 + i * 8)
        rec: dict = {"is_dir": bool(flags & 1)}
        if fields & F_NAME:
            n, = struct.unpack_from("<I", data, p); p += 4
            rec["name"] = data[p:p + n * 2].decode("utf-16-le", "replace"); p += n * 2 + 2
        if fields & F_PATH:
            n, = struct.unpack_from("<I", data, p); p += 4
            rec["dir"] = data[p:p + n * 2].decode("utf-16-le", "replace"); p += n * 2 + 2
        if fields & F_FULL:
            n, = struct.unpack_from("<I", data, p); p += 4
            rec["path"] = data[p:p + n * 2].decode("utf-16-le", "replace"); p += n * 2 + 2
        if fields & F_EXT:
            n, = struct.unpack_from("<I", data, p); p += 4
            rec["ext"] = data[p:p + n * 2].decode("utf-16-le", "replace"); p += n * 2 + 2
        if fields & F_SIZE:
            size, = struct.unpack_from("<q", data, p); p += 8
            rec["size"] = None if size < 0 else size
        if fields & F_CREATED:
            ft, = struct.unpack_from("<Q", data, p); p += 8
            rec["ctime"] = None if ft >= FILETIME_INVALID or ft == 0 else ft / 1e7 - _EPOCH_SHIFT
        if fields & F_MODIFIED:
            ft, = struct.unpack_from("<Q", data, p); p += 8
            rec["mtime"] = None if ft >= FILETIME_INVALID or ft == 0 else ft / 1e7 - _EPOCH_SHIFT
        if fields & F_ATTRS:
            rec["attrs"], = struct.unpack_from("<I", data, p); p += 4
        out.append(rec)
    return total, out


def count(search: str, *, timeout: float = 30.0) -> int:
    """عددُ المطابقات وحدَه (بلا نقلِ صفوف) — مقيسٌ: ٠٫٠١–٠٫٠٤ ث على ١٢ مليون ملفّ."""
    data = _raw_query(search, limit=0, offset=0, fields=F_FULL, sort=SORT_NAME_ASC, timeout=timeout)
    return struct.unpack_from("<I", data, 0)[0]


def query(
    search: str, *, limit: int = 200, offset: int = 0,
    fields: int = FIELDS_DEFAULT, sort: int = SORT_MODIFIED_DESC, timeout: float = 120.0,
) -> tuple[int, list[dict]]:
    """صفحةٌ من النتائج: (العددُ الكلّيّ، الصفوف)."""
    data = _raw_query(search, limit=limit, offset=offset, fields=fields, sort=sort, timeout=timeout)
    return _parse(data)


def iter_rows(
    search: str, *, page: int = 100_000, fields: int = FIELDS_DEFAULT,
    sort: int = SORT_PATH_ASC, timeout: float = 300.0,
):
    """
    يمرُّ على كلِّ المطابقات صفحةً صفحةً. الترتيبُ بالمسارِ لأنّه أثبتُ ما يُرقَّم عليه
    (ترتيبُ التاريخِ يتزحزح إن تغيّرَ ملفٌّ بين صفحتين فيتكرّرُ صفٌّ أو يسقط).
    """
    offset = 0
    total = None
    while True:
        tot, rows = query(search, limit=page, offset=offset, fields=fields, sort=sort, timeout=timeout)
        if total is None:
            total = tot
        if not rows:
            break
        yield from rows
        offset += len(rows)
        if offset >= tot:
            break
