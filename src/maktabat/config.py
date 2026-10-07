# -*- coding: utf-8 -*-
"""
إعداداتُ الرادار: الجذورُ المرصودةُ وصيغُ الكتبِ وما يُستثنى — وبناءُ استعلامِ النطاق.

النطاقُ يُبنى مرّةً واحدةً ويُستعمَل في موضعين معًا، فلا يختلفُ المرصودُ عن المبحوثِ فيه:
    ① المسحُ الدوريُّ الذي يكتبُ سجلَّ الوصول.    ② البحثُ الحيُّ من الصفحة.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.json"
DATA_DIR = ROOT / "data"


@dataclass(frozen=True)
class Root:
    id: str
    path: str
    label: str
    store: str  # "nas" أو "local"

    @property
    def prefix(self) -> str:
        return self.path.rstrip("\\") + "\\"


@dataclass
class Config:
    roots: list[Root]
    exclude: list[str]
    types: dict[str, list[str]]
    host: str = "127.0.0.1"
    port: int = 8731
    page: int = 100_000
    db_path: Path = field(default_factory=lambda: DATA_DIR / "maktabat.db")
    source: Path | None = None

    # ── الصيغُ والأنواع ──────────────────────────────────────────────────────
    @property
    def all_exts(self) -> list[str]:
        seen: list[str] = []
        for exts in self.types.values():
            for e in exts:
                if e not in seen:
                    seen.append(e)
        return seen

    @property
    def ext_type(self) -> dict[str, str]:
        out = {}
        for kind, exts in self.types.items():
            for e in exts:
                out.setdefault(e, kind)
        return out

    def type_of(self, ext: str) -> str:
        return self.ext_type.get((ext or "").lower(), "أخرى")

    def root_of(self, path: str) -> Root | None:
        low = path.lower()
        for r in self.roots:
            if low.startswith(r.prefix.lower()):
                return r
        return None

    def shelf_of(self, path: str, root: Root | None = None) -> str:
        """«الرفّ» = أوّلُ مجلّدٍ تحتَ الجذر — وهو اسمُ المكتبةِ عمليًّا (مخطوط · رسائل جامعية …)."""
        root = root or self.root_of(path)
        if not root:
            return "—"
        rest = path[len(root.prefix):]
        head, sep, _ = rest.partition("\\")
        return head if sep else "(في جذر المكتبة)"

    # ── استعلامُ النطاق بصياغةِ Everything ───────────────────────────────────
    def ext_term(self, exts: list[str] | None = None) -> str:
        return "ext:" + ";".join(exts or self.all_exts)

    def roots_term(self, root_ids: list[str] | None = None) -> str:
        chosen = [r for r in self.roots if not root_ids or r.id in root_ids]
        if not chosen:
            return ""
        terms = ['path:"%s"' % r.prefix for r in chosen]
        return terms[0] if len(terms) == 1 else "<" + " | ".join(terms) + ">"

    def exclude_term(self) -> str:
        return " ".join('!path:"%s"' % frag for frag in self.exclude)

    def scope(self, *, root_ids: list[str] | None = None, exts: list[str] | None = None,
              extra: str = "") -> str:
        parts = [self.ext_term(exts), self.roots_term(root_ids), self.exclude_term()]
        if extra:
            parts.append(extra)
        return " ".join(p for p in parts if p)


_DEFAULT_TYPES: dict[str, list[str]] = {
    "كتاب": ["pdf", "djvu", "djv", "epub", "mobi", "azw", "azw3", "chm", "fb2", "doc", "docx",
             "rtf", "odt", "wps", "pdb", "lit"],
    "مكتبة برنامج": ["bok", "sh3", "shamela", "mkt", "nous"],
    "قاعدة بيانات": ["db", "db3", "sqlite", "sqlite3", "mdb", "accdb", "sql", "bak", "mdf", "dbf"],
    "حاوية": ["rar", "zip", "7z", "iso"],
}

_DEFAULT_EXCLUDE = [
    "\\Windows\\", "\\Windows.old\\", "\\AppData\\", "\\ProgramData\\",
    "\\Program Files\\", "\\Program Files (x86)\\", "\\$Recycle.Bin\\",
    "\\System Volume Information\\", "\\MSOCache\\", "\\node_modules\\",
    "\\__pycache__\\", "\\site-packages\\", "\\.git\\", "\\.venv\\",
    "\\Temp\\", "\\tdata\\", "\\@eaDir\\",
]


def discover_roots() -> list[Root]:
    """
    جذورٌ افتراضيّةٌ تُكتشَفُ من الجهاز: مشاركةُ السيرفرِ إن كانت موصولة، والأقراصُ
    الثابتةُ ما خلا قرصَ النظام (C:) — فالنظامُ ضجيجٌ لا مكتبة.
    """
    import string
    import os

    out: list[Root] = []
    nas = "\\\\m27\\m21"
    if os.path.isdir(nas):
        out.append(Root(id="nas", path=nas, label="السيرفر m21", store="nas"))
    for letter in string.ascii_uppercase:
        if letter == "C":
            continue
        drive = letter + ":\\"
        if os.path.isdir(drive):
            try:
                if not os.listdir(drive):
                    continue
            except OSError:
                continue
            out.append(Root(id=letter.lower(), path=drive, label="قرص %s" % letter, store="local"))
    return out


def default_config() -> Config:
    return Config(roots=discover_roots(), exclude=list(_DEFAULT_EXCLUDE), types=dict(_DEFAULT_TYPES))


def load(path: Path | str | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        cfg = default_config()
        cfg.source = None
        return cfg
    raw = json.loads(p.read_text(encoding="utf-8"))
    roots = [Root(id=r["id"], path=r["path"], label=r.get("label", r["path"]),
                  store=r.get("store", "local")) for r in raw.get("roots", [])]
    srv = raw.get("server", {})
    cfg = Config(
        roots=roots or discover_roots(),
        exclude=raw.get("exclude", list(_DEFAULT_EXCLUDE)),
        types=raw.get("types", dict(_DEFAULT_TYPES)),
        host=srv.get("host", "127.0.0.1"),
        port=int(srv.get("port", 8731)),
        page=int(raw.get("scan", {}).get("page", 100_000)),
    )
    db = raw.get("db_path")
    if db:
        cfg.db_path = Path(db) if Path(db).is_absolute() else ROOT / db
    cfg.source = p
    return cfg


def save_default(path: Path | str | None = None) -> Path:
    """يكتبُ ملفَّ إعداداتٍ أوّليًّا من المكتشَفِ على هذا الجهاز."""
    p = Path(path) if path else DEFAULT_CONFIG
    cfg = default_config()
    payload = {
        "_": "إعداداتُ رادار المكتبات — عدِّلْ هنا ولا تعدِّلْ في الشيفرة",
        "roots": [{"id": r.id, "path": r.path, "label": r.label, "store": r.store} for r in cfg.roots],
        "exclude": cfg.exclude,
        "types": cfg.types,
        "server": {"host": cfg.host, "port": cfg.port},
        "scan": {"page": cfg.page},
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
