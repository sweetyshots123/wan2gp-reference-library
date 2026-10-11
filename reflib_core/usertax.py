"""User taxonomy (1.5.1): custom groups and tags in <data>/user_taxonomy.json, merged over the shipped taxonomy.json
at load time, so they survive plugin updates. Shipped nodes are never modified; only custom ones ("u_" ids) can be
renamed, moved or deleted. Every change keeps an undo snapshot. Same safety rules as the shipped taxonomy: no tags for
genitals or sexual anatomy, nothing that targets minors, and nothing under the apparent-age group."""
from __future__ import annotations
import json, os, re, threading, time, unicodedata
from typing import Dict, List, Optional

FORMAT = 1
_lock = threading.RLock()
MAX_UNDO = 30

# safety blocklist (folded, accent-free, whole words or word starts)
_BLOCK_ANATOMY = ["genital", "genitales", "vagina", "vulva", "labia", "labios vaginales", "clitoris", "pene", "penis", "testicul",
                  "escroto", "scrotum", "ano", "anus", "pezon", "pezones", "nipple", "areola", "pubis", "pubic", "vello pubico",
                  "coño", "cono", "polla", "verga", "pussy", "cock", "dick", "tits", "tetas", "teta", "culo abierto", "camel toe", "cameltoe"]
_BLOCK_MINOR = ["nino", "nina", "ninos", "ninas", "menor", "menores", "infantil", "child", "children", "kid", "kids", "teen", "teens",
                "teenager", "adolescente", "adolescentes", "preteen", "underage", "loli", "lolita", "shota", "colegiala", "schoolgirl",
                "school girl", "jovencita", "chiquilla", "nena", "bebe", "baby", "toddler", "pubescent", "prepubescent", "minor", "minors",
                "young girl", "little girl", "chica joven"]
_AGE_RE = re.compile(r"\b(1[0-7]|[1-9])\s*(anos|ano|years?|yo|y o|yrs?)\b")
_BLOCK_EXPLICIT = ["sexo", "sex", "sexual", "sexuales", "follar", "follando", "coito", "penetracion", "felacion", "mamada",
                   "masturbacion", "masturbandose", "masturbation", "masturbating", "orgasmo", "orgasm", "porno", "porn", "xxx",
                   "intercourse", "fellatio", "blowjob", "handjob", "cunnilingus", "anal", "oral sex", "sexo oral", "cum", "corrida",
                   "fucking", "fuck", "eyaculacion", "ejaculation", "orgia", "orgy", "explicit act", "acto sexual", "nsfw act"]
FORBIDDEN_PARENTS = {"age_band", "review"}

MSG = {
    "anatomy": {"es": "No se permiten etiquetas sobre genitales o anatomía sexual.", "en": "Tags about genitals or sexual anatomy are not allowed."},
    "minor": {"es": "No se permiten etiquetas que se refieran a menores. La librería es solo para personas adultas.",
              "en": "Tags that refer to minors are not allowed. The library is for adults only."},
    "explicit": {"es": "No se permiten etiquetas de actos sexuales o explícitos. Usa la marca «Revisión › contenido explícito».",
                 "en": "Tags for sexual or explicit acts are not allowed. Use the “Review › explicit content” flag."},
    "age": {"es": "La edad aparente es un grupo fijo (solo adultos); no admite etiquetas propias.",
            "en": "Apparent age is a fixed, adults-only group; it does not accept custom tags."},
    "parent": {"es": "Elige una categoría o grupo válido.", "en": "Pick a valid category or group."},
    "label": {"es": "Escribe un nombre (ES o EN).", "en": "Enter a name (ES or EN)."},
    "dup": {"es": "Ya existe una etiqueta con ese nombre en ese grupo.", "en": "A tag with that name already exists in that group."},
    "shipped": {"es": "Las etiquetas de serie no se pueden cambiar; crea una propia.", "en": "Built-in tags can't be changed; create your own."},
    "missing": {"es": "No existe.", "en": "Not found."},
    "nothing": {"es": "Nada que deshacer.", "en": "Nothing to undo."},
}


def _fold(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s or "").casefold()) if not unicodedata.combining(c))
    return re.sub(r"[\s_\-/.,;:]+", " ", s).strip()


def safety_check(texts: List[str]) -> Optional[str]:
    """None when fine, else 'anatomy' | 'minor' | 'explicit'."""
    for t in texts:
        f = " " + _fold(t) + " "
        if _AGE_RE.search(f):
            return "minor"
        for w in _BLOCK_MINOR:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", f):
                return "minor"
        for w in _BLOCK_ANATOMY:
            pat = r"(?<![a-z])" + re.escape(w) + (r"[a-z]*" if w in ("genital", "testicul") else r"(?![a-z])")
            if re.search(pat, f):
                return "anatomy"
        for w in _BLOCK_EXPLICIT:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", f):
                return "explicit"
    return None


class UserTaxError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

    def msg(self, lang="es"):
        return MSG.get(self.code, {}).get(lang[:2], self.code)


def path() -> Optional[str]:
    from . import taxonomy
    return taxonomy.USER_PATH


def read() -> Dict:
    p = path()
    if not p or not os.path.exists(p):
        return {"format": FORMAT, "nodes": [], "undo": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("nodes", []); d.setdefault("undo", [])
        return d
    except Exception:
        return {"format": FORMAT, "nodes": [], "undo": []}


def _write(d: Dict) -> None:
    from . import taxonomy
    p = path()
    if not p:
        raise UserTaxError("missing")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    taxonomy.reload()


def _snapshot(d: Dict, what: str) -> None:
    d["undo"] = (d.get("undo") or [])[-(MAX_UNDO - 1):] + [{"at": time.time(), "what": what, "nodes": json.loads(json.dumps(d["nodes"]))}]


def _clean_syn(v) -> List[str]:
    if isinstance(v, str):
        v = v.split(",")
    return [s.strip()[:60] for s in (v or []) if str(s).strip()][:20]


def _validate(n: Dict, nodes_by_id: Dict) -> None:
    from . import taxonomy
    if not (n.get("es") or n.get("en")):
        raise UserTaxError("label")
    par = n.get("parent")
    if n["kind"] == "category":   # 1.5.2: new top-level categories
        if par:
            raise UserTaxError("parent")
        chain = []
    else:
        pn = nodes_by_id.get(par) or taxonomy.node(par)
        if not pn or pn["kind"] == "tag":
            raise UserTaxError("parent")
        chain = [par] + [a for a in taxonomy.ancestors(par)] if taxonomy.node(par) else [par]
    if any(c in FORBIDDEN_PARENTS for c in chain):
        raise UserTaxError("age")
    bad = safety_check([n.get("es", ""), n.get("en", "")] + n["syn"]["es"] + n["syn"]["en"])
    if bad:
        raise UserTaxError(bad)


def _ensure_group(d: Dict, parent: str) -> str:
    """A tag placed straight under a category goes into that category's own "Mis etiquetas" group (multi-label)."""
    from . import taxonomy
    pn = taxonomy.node(parent) or next((x for x in d["nodes"] if x["id"] == parent), None)
    if not pn or pn["kind"] != "category":
        return parent
    gid = "u_mine_" + parent
    if not taxonomy.node(gid) and not any(x["id"] == gid for x in d["nodes"]):
        g = {"id": gid, "parent": parent, "kind": "group", "es": "Mis etiquetas", "en": "My tags", "syn": {"es": [], "en": []},
             "custom": True, "exclusive": False}
        if taxonomy.is_sensitive(parent):
            g["sensitive"] = True
        d["nodes"].append(g)
    return gid


def add(kind: str, parent: str, es: str = "", en: str = "", syn_es=None, syn_en=None, exclusive: bool = False) -> Dict:
    from . import taxonomy
    with _lock:
        d = read()
        n = {"id": "", "parent": str(parent or ""), "kind": kind if kind in ("category", "group") else "tag",
             "es": str(es or en or "").strip()[:80], "en": str(en or es or "").strip()[:80],
             "syn": {"es": _clean_syn(syn_es), "en": _clean_syn(syn_en)}, "custom": True}
        if n["kind"] == "group":
            n["exclusive"] = bool(exclusive)
        if n["kind"] == "category":
            n["parent"] = None
        _validate(n, {x["id"]: x for x in d["nodes"]})
        sibs = [taxonomy.node(k) for k in taxonomy.load()["kids"].get(n["parent"], [])] if n["parent"] else \
            [x for x in taxonomy.load()["nodes"].values() if not x.get("parent")]
        if any(s and _fold(s["es"]) == _fold(n["es"]) for s in sibs):
            raise UserTaxError("dup")
        base = "u_" + (re.sub(r"[^a-z0-9]+", "_", _fold(n["en"] or n["es"])).strip("_") or "tag")[:40]
        nid, i = base, 2
        while taxonomy.node(nid) or any(x["id"] == nid for x in d["nodes"]):
            nid, i = f"{base}_{i}", i + 1
        n["id"] = nid
        p = taxonomy.node(n["parent"]) if n["parent"] else None
        if p and taxonomy.is_sensitive(n["parent"]):
            n["sensitive"] = True   # the minor gate drops it like the shipped body/nudity tags
        _snapshot(d, "add")
        d["nodes"].append(n)
        _write(d)
        return n


def update(nid: str, **ch) -> Dict:
    from . import taxonomy
    with _lock:
        d = read()
        by = {x["id"]: x for x in d["nodes"]}
        if nid not in by:
            raise UserTaxError("shipped" if taxonomy.node(nid) else "missing")
        n = json.loads(json.dumps(by[nid]))
        for k in ("es", "en"):
            if k in ch and ch[k] is not None:
                n[k] = str(ch[k]).strip()[:80]
        for k in ("syn_es", "syn_en"):
            if k in ch and ch[k] is not None:
                n["syn"][k[-2:]] = _clean_syn(ch[k])
        if ch.get("parent") and n["kind"] != "category":
            if ch["parent"] == nid or ch["parent"] in taxonomy.descendants(nid):
                raise UserTaxError("parent")
            n["parent"] = str(ch["parent"])
        if "exclusive" in ch and n["kind"] == "group":
            n["exclusive"] = bool(ch["exclusive"])
        _validate(n, by)
        n["sensitive"] = bool(n["parent"] and taxonomy.is_sensitive(n["parent"])) or None
        if not n["sensitive"]:
            n.pop("sensitive")
        _snapshot(d, "update")
        d["nodes"] = [n if x["id"] == nid else x for x in d["nodes"]]
        _write(d)
        return n


def delete(nid: str) -> List[str]:
    from . import taxonomy
    with _lock:
        d = read()
        ids = {x["id"] for x in d["nodes"]}
        if nid not in ids:
            raise UserTaxError("shipped" if taxonomy.node(nid) else "missing")
        gone = {nid} | (taxonomy.descendants(nid) & ids)
        _snapshot(d, "delete")
        d["nodes"] = [x for x in d["nodes"] if x["id"] not in gone]
        _write(d)
        return sorted(gone)


def undo() -> str:
    with _lock:
        d = read()
        if not d.get("undo"):
            raise UserTaxError("nothing")
        last = d["undo"].pop()
        d["nodes"] = last["nodes"]
        _write(d)
        return last["what"]


def listing() -> Dict:
    d = read()
    return {"nodes": d["nodes"], "undo": len(d.get("undo") or []), "last": (d["undo"][-1]["what"] if d.get("undo") else None)}
