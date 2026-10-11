"""Standalone CLI (proves the core runs without WanGP / Gradio):
  python -m reflib_core --data DIR add-folder PATH          index a folder (read-only)
  python -m reflib_core --data DIR tag [PATH|all] [--model fake|wd|qwen|wd+qwen|jev|jev+qwen|…]
  python -m reflib_core --data DIR search QUERY             e.g. "pelo corto", "arena", "cintura<65", "90-60-90 ±5"
  python -m reflib_core --data DIR show HASH                auto tags + body-shape estimate
  python -m reflib_core taxonomy [--lang es]                print the taxonomy tree
"""
import argparse, json, os, sys, time
from . import configure, taxonomy


def main(argv=None):
    ap = argparse.ArgumentParser(prog="reflib_core")
    ap.add_argument("--data", default=os.environ.get("REFLIB_DATA_DIR") or os.path.join(os.getcwd(), "reflib_data"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-folder"); a.add_argument("path"); a.add_argument("--flat", action="store_true")
    t = sub.add_parser("tag"); t.add_argument("target", nargs="?", default="all"); t.add_argument("--model"); t.add_argument("--force", action="store_true")
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=50)
    sh = sub.add_parser("show"); sh.add_argument("hash")
    tx = sub.add_parser("taxonomy"); tx.add_argument("--lang", default="en")
    a = ap.parse_args(argv)
    if a.cmd == "taxonomy":
        def walk(nid, d):
            n = taxonomy.node(nid)
            print("  " * d + f"{taxonomy.label(nid, a.lang)}  [{nid}]" + ("  (one of)" if n.get("exclusive") else ""))
            for k in taxonomy.load()["kids"].get(nid, []):
                walk(k, d + 1)
        for r in [n["id"] for n in taxonomy.load()["nodes"].values() if not n["parent"]]:
            walk(r, 0)
        return 0
    os.makedirs(a.data, exist_ok=True)
    configure(a.data)
    from . import imagelib
    from .autotag import AutoTagService
    svc = AutoTagService(a.data, log=lambda m: print(m, file=sys.stderr))
    if a.cmd == "add-folder":
        r = imagelib.add_folder(a.path, recursive=not a.flat)
        print(json.dumps(r, default=str)[:400])
        while imagelib.scan_status().get("running"):
            time.sleep(0.2)
        imagelib.invalidate()
        print(f"{imagelib.meta()['total']} images indexed")
        return 0
    if a.cmd == "tag":
        if a.model:
            svc.save_settings({"model": a.model})
        f = {}
        if a.target != "all":
            p = os.path.abspath(a.target)
            if os.path.isdir(p) and not any(os.path.normcase(x["path"]) == os.path.normcase(p) for x in imagelib.list_folders()):
                imagelib.add_folder(p, recursive=True)
                while imagelib.scan_status().get("running"):
                    time.sleep(0.2)
                imagelib.invalidate()
            fid = next((x["id"] for x in imagelib.list_folders() if os.path.normcase(x["path"]) == os.path.normcase(p)), None)
            f = {"node": {"fid": fid, "rel": ""}} if fid else {}
        hs = imagelib.resolve_selection({"all": True, "f": f})
        print("estimate:", json.dumps(svc.estimate(len(hs))))
        print("queued:", svc.enqueue(hs, force=a.force))
        last = None
        while True:
            st = svc.queue.status()
            line = f"{st['done']}/{st['total']} review={st['review']} failed={st['failed']} {st['waiting']} {st['error']}"
            if line != last:
                print(line, file=sys.stderr); last = line
            if not st["running"]:
                break
            time.sleep(0.3)
        svc.queue.unload()
        return 0 if not st["error"] else 1
    if a.cmd == "search":
        imagelib.invalidate()
        r = imagelib.query({"q": a.query}, 0, a.limit)
        print(f"{r['total']} match")
        for i in r["items"]:
            print(i["hash"][:12], i["name"])
        return 0
    if a.cmd == "show":
        h = next((x for x in svc.store.load() if x.startswith(a.hash)), a.hash)
        print(json.dumps(svc.image_tags(h), indent=1, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    sys.exit(main())
