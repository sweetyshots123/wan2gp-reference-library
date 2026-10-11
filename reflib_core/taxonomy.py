"""Hierarchical bilingual taxonomy (taxonomy.json): lookup, labels, search expansion (synonyms + hierarchy, EN/ES)."""
from __future__ import annotations
import json, os, re, unicodedata
from typing import Dict, List, Optional, Set

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taxonomy.json")
_T: Dict = {}
USER_PATH: Optional[str] = None   # 1.5.1: <data>/user_taxonomy.json (custom groups/tags), merged over the shipped file
REV = [0]
# 1.5.1 renamed apparent-age bands; tags stored by 1.5.0 are read through this map (approximate for the wide old bands)
ALIASES = {"age_18_25": "age_18_24", "age_26_35": "age_25_34", "age_36_50": "age_35_44", "age_50_plus": "age_55_64"}


def fold(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s or "").casefold()) if not unicodedata.combining(c))
    return re.sub(r"[\s_\-/]+", " ", s).strip()


def load(path: Optional[str] = None) -> Dict:
    if _T and not path:
        return _T
    with open(path or _PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not path and USER_PATH and os.path.exists(USER_PATH):
        try:
            with open(USER_PATH, "r", encoding="utf-8") as f:
                ids = {n["id"] for n in data["nodes"]}
                user = [n for n in json.load(f).get("nodes", []) if n.get("id") and n["id"] not in ids]
            known = ids | {n["id"] for n in user}
            ok = [n for n in user if (n.get("parent") in known) or (not n.get("parent") and n.get("kind") == "category")]
            data = dict(data, nodes=data["nodes"] + [dict(n, parent=n.get("parent") or None, syn=n.get("syn") or {"es": [], "en": []}) for n in ok])
        except Exception:
            pass
    nodes = {n["id"]: n for n in data["nodes"]}
    kids: Dict[str, List[str]] = {}
    for n in data["nodes"]:
        if n["parent"]:
            kids.setdefault(n["parent"], []).append(n["id"])
    terms: Dict[str, Set[str]] = {}
    for n in data["nodes"]:
        for t in [n["en"], n["es"], n["id"].replace("_", " ")] + n["syn"]["en"] + n["syn"]["es"]:
            terms.setdefault(fold(t), set()).add(n["id"])
    _T.clear()
    _T.update(nodes=nodes, kids=kids, terms=terms, raw=data)
    return _T


def reload() -> Dict:
    _T.clear()
    REV[0] += 1
    return load()


def node(nid: str) -> Optional[Dict]:
    return load()["nodes"].get(nid)


def ancestors(nid: str) -> List[str]:
    out, n = [], node(nid)
    while n and n["parent"]:
        out.append(n["parent"]); n = node(n["parent"])
    return out


def descendants(nid: str) -> Set[str]:
    out, stack = set(), [nid]
    while stack:
        for k in load()["kids"].get(stack.pop(), []):
            if k not in out:
                out.add(k); stack.append(k)
    return out


def group_of(nid: str) -> Optional[str]:
    for a in [nid] + ancestors(nid):
        if node(a) and node(a)["kind"] == "group":
            return a
    return None


def groups() -> List[Dict]:
    return [n for n in load()["raw"]["nodes"] if n["kind"] == "group"]


def tags_in_group(gid: str) -> List[str]:
    d = descendants(gid)
    return [t for t in load()["nodes"] if t in d and node(t)["kind"] == "tag"]   # file order


def is_sensitive(nid: str) -> bool:
    return any((node(a) or {}).get("sensitive") for a in [nid] + ancestors(nid))


def tag_ids() -> List[str]:
    return [i for i, n in load()["nodes"].items() if n["kind"] == "tag"]


def label(nid: str, lang: str = "en") -> str:
    n = node(nid)
    return (n.get(lang) or n["en"]) if n else nid


def match_terms(query: str) -> Set[str]:
    """Nodes named by `query` in either language (label, synonym or id): exact phrase first, otherwise nodes whose
    terms contain it as whole words (3+ letters)."""
    q = fold(query)
    if not q:
        return set()
    terms = load()["terms"]
    if q in terms:
        return set(terms[q])
    if len(q) < 3:
        return set()
    pat = re.compile(r"(^| )" + re.escape(q) + r"( |$)")
    out: Set[str] = set()
    for t, ids in terms.items():
        if pat.search(t):
            out |= ids
    return out


def expand(query: str) -> Set[str]:
    """Matched nodes plus all their children ("curvy" also finds "hourglass", "peinado" every hair style). Images keep
    their tags with all ancestors, so searching a child never needs the parent."""
    out: Set[str] = set()
    for nid in match_terms(query):
        out.add(nid); out |= descendants(nid)
    return out


def with_ancestors(ids) -> Set[str]:
    out = set()
    for i in ids:
        out.add(i); out.update(ancestors(i))
    return out


def compact() -> List[Dict]:
    """For UIs: id, parent, kind initial, both labels, exclusive flag."""
    return [{"id": n["id"], "p": n["parent"], "k": n["kind"][0], "en": n["en"], "es": n["es"], "x": bool(n.get("exclusive")), "u": bool(n.get("custom")), **({"s": n.get("syn")} if n.get("custom") else {})}
            for n in load()["raw"]["nodes"]]


def expand_loose(term: str) -> Set[str]:
    """For "field:value" search terms ("cadera:ancha"): tries the words as given, singular/plural variants and both
    orders, so "cadera ancha" finds "caderas anchas" and "ancha cadera"."""
    words = fold(term).split()
    if not words:
        return set()
    def variants(ws):
        yield ws
        yield [w + "s" if not w.endswith("s") else w for w in ws]
        yield [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in ws]
    for order in (words, list(reversed(words))):
        for ws in variants(order):
            r = expand(" ".join(ws))
            if r:
                return r
    return set()
