"""The ARR Network from the command line.

    python -m arrnet.run seed|courier|read --reader X|verify|index|audit|direct|work|all
        [--only COMMISSION[,..]] [--limit N] [--manifest FILE ...] [--dry-run DIR]

Each step records ``agent_runs``.  Without ``--dry-run`` rows go to the ingest API
(INGEST_URL, INGEST_TOKEN); with it they are written as JSONL to DIR.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from . import auditor, courier, director, librarian, manifest, reference, store, verifier
from .ingest import Sink, make_sink
from .readers.base import Reader
from .runs import Run

READERS = ("textlayer", "docling", "llamaparse", "llm")


def make_reader(name: str, args: argparse.Namespace) -> Reader:
    if name == "textlayer":
        from .readers.textlayer import TextLayerReader

        return TextLayerReader()
    if name == "docling":
        from .readers.docling_reader import DoclingReader
        from .spend import policy

        d = policy()["docling"]
        return DoclingReader(
            max_pages=args.max_pages or int(d["max_pages_per_order"]),
            max_ocr_pages=int(d.get("max_ocr_pages_per_order", 6)),
        )
    if name == "llamaparse":
        from .readers.llamaparse_reader import LlamaParseReader

        return LlamaParseReader(max_total_pages=args.max_total_pages)
    if name == "llm":
        from .readers.llm_extractor import Extractor

        return Extractor()
    raise SystemExit(f"unknown reader {name}")


def read(orders: list[dict[str, Any]], sink: Sink, reader: Reader, log=print) -> dict[str, Any]:
    stats: dict[str, Any] = {"orders": 0, "tables": 0, "values": 0, "seconds": 0.0, "status": {}}
    orders, _ = manifest.unique_files(orders)
    for i, o in enumerate(orders, 1):
        path = manifest.pdf_path(o)
        if not o.get("sha256"):
            continue
        run = Run(f"reader:{reader.name}", reader.version, order_url=o["url"])
        try:
            res = reader.read(o, path)
        except Exception as e:  # one order's failure does not stop the others
            res = reader.skipped(f"{type(e).__name__}: {e}"[:300])
            res.status = "failed"
        prev = store.read(o["sha256"], reader.name)
        if res.status == "skipped" and prev and prev.get("status") in ("ok", "partial"):
            # a skipped run (no key, no budget) never replaces an earlier reading
            run.post(sink, "skipped", f"{res.note}; the earlier {prev['reader_version']} reading is kept")
            stats["status"]["skipped"] = stats["status"].get("skipped", 0) + 1
            continue
        store.write(o["sha256"], reader.name, res.to_dict())
        sink.post("parses", [res.parse_row(o["url"])])
        if reader.name == "textlayer" and res.status == "ok":
            doc = store.read(o["sha256"], "pages")
            if doc:
                sink.post("orders", [{**doc["order"], "read_status": res.extra["read_status"]}])
        run.post(
            sink,
            res.status,
            res.note,
            provider=res.provider,
            model=res.model,
            is_real=res.is_real,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            cost_usd=round(res.cost_usd, 6),
        )
        stats["orders"] += 1
        stats["tables"] += len(res.tables)
        stats["values"] += len(res.values)
        stats["seconds"] += res.seconds
        stats["status"][res.status] = stats["status"].get(res.status, 0) + 1
        log(f"[{i}/{len(orders)}] {reader.name} {o['commission']} {o['title'][:50]!r}: {res.status} — {res.note}")
    stats["seconds"] = round(stats["seconds"], 1)
    return stats


def verify(orders: list[dict[str, Any]], sink: Sink, log=print) -> dict[str, Any]:
    orders, _ = manifest.unique_files(orders)
    results, runs = [], []
    for o in orders:
        r = Run("verifier", verifier.VERSION, order_url=o["url"])
        v = verifier.verify_order(o)
        if v is None:
            continue
        results.append(v)
        runs.append(r)
    set_aside = verifier.set_aside_outliers([f for v in results for f in v["facts"]])
    totals: dict[str, Any] = {
        "orders": 0,
        "facts": 0,
        "set_aside": set_aside,
        "rejected": {},
        "consensus": {},
        "duplicate_fact_keys": 0,
        "duplicate_same_value": 0,
        "duplicate_other_value": 0,
        "api_rejected": 0,
    }
    for v, r in zip(results, runs, strict=True):
        store.write(v["order"]["sha256"], "verified", v)
        if v["rejections"]:
            store.append_jsonl("rejections", v["rejections"])
        n = verifier.post_order(sink, v)
        rej = len(v["rejections"])
        r.post(
            sink,
            "ok" if not n["rejected"] else "partial",
            f"{len(v['facts'])} facts; {rej} readings rejected for evidence; {n['rejected']} rows refused by the API",
            rows_written=n["written"],
            rows_rejected=rej,
        )
        totals["orders"] += 1
        totals["facts"] += len(v["facts"])
        for k in ("duplicate_fact_keys", "duplicate_same_value", "duplicate_other_value"):
            totals[k] += v[k]
        totals["api_rejected"] += n["rejected"]
        for x in v["rejections"]:
            totals["rejected"][x["reader"]] = totals["rejected"].get(x["reader"], 0) + 1
        for f in v["facts"]:
            totals["consensus"][f["consensus"]] = totals["consensus"].get(f["consensus"], 0) + 1
    log(json.dumps(totals))
    return totals


def index(orders: list[dict[str, Any]], sink: Sink, embed: bool = True, log=print) -> dict[str, Any]:
    orders, _ = manifest.unique_files(orders)
    tot: dict[str, int] = {}
    t0 = time.monotonic()
    for o in orders:
        if not o.get("sha256") or not store.exists(o["sha256"], "pages"):
            continue
        s = librarian.index_order(o, sink, embed=embed)
        for k, v in s.items():
            if isinstance(v, int):
                tot[k] = tot.get(k, 0) + v
        tot["orders"] = tot.get("orders", 0) + 1
    tot["seconds"] = round(time.monotonic() - t0, 1)
    log(json.dumps(tot))
    return tot


def work(orders: list[dict[str, Any]], sink: Sink, args: argparse.Namespace, log=print) -> dict[str, Any]:
    """Run the queued work items, lowest priority number first."""
    q = director.Queue()
    by_sha = {o["sha256"]: o for o in orders if o.get("sha256")}
    by_url = {o["url"]: o for o in orders}
    readers: dict[str, Reader] = {}
    done: dict[str, int] = {}
    verify_batch: list[dict[str, Any]] = []
    while True:
        items = q.claim(limit=1)
        if not items:
            break
        it = items[0]
        kind, target = it["kind"], it["target"]
        o = by_sha.get(target) or by_url.get(target)
        try:
            if kind == "audit":
                if verify_batch:
                    verify(verify_batch, sink, log)
                    verify_batch = []
                auditor.run(orders, sink)
            elif o is None:
                raise RuntimeError("target not in the manifest selection")
            elif kind == "fetch":
                courier.run([o], sink, download=True)
            elif kind.startswith("parse:") or kind == "extract":
                name = "llm" if kind == "extract" else kind.split(":", 1)[1]
                readers.setdefault(name, make_reader(name, args))
                read([o], sink, readers[name], log)
                if store.read(o["sha256"], name)["status"] == "failed":
                    raise RuntimeError(store.read(o["sha256"], name).get("note"))
            elif kind == "verify":
                verify_batch.append(o)  # verified together, so that outliers are judged across orders
            elif kind == "index":
                index([o], sink, embed=not args.no_embed, log=lambda *_: None)
            q.complete(kind, target, True)
            done[kind] = done.get(kind, 0) + 1
        except Exception as e:
            q.complete(kind, target, False, f"{type(e).__name__}: {e}"[:300])
            log(f"{kind} {target[:16]} failed: {e}")
        q.save()
    if verify_batch:
        verify(verify_batch, sink, log)
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m arrnet.run", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("step", choices=["seed", "courier", "read", "verify", "index", "audit", "direct", "work", "all"])
    ap.add_argument("--reader", choices=READERS)
    ap.add_argument("--only", help="commission code(s), comma-separated")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--manifest", action="append", help="orders file (default tools/arrdb/data/orders.json)")
    ap.add_argument("--dry-run", metavar="DIR", help="write the batches as JSONL to DIR instead of the ingest API")
    ap.add_argument("--max-pages", type=int, help="Docling: pages converted per order")
    ap.add_argument("--max-total-pages", type=int, help="LlamaParse: pages sent across all orders of this run")
    ap.add_argument("--no-embed", action="store_true", help="Librarian: post chunks without embeddings")
    ap.add_argument("--download", action="store_true", help="Courier: download orders missing from the cache")
    a = ap.parse_args(argv)
    sink = make_sink(a.dry_run, reference.known_codes())
    every = manifest.load(a.manifest)
    orders = manifest.select(every, a.only, a.limit)
    out: Any
    if a.step == "seed":
        r = Run("seed", "reference 1")
        out = reference.seed(sink)
        r.post(sink, "ok", "reference rows", rows_written=sum(v["written"] for v in out.values()))
    elif a.step == "courier":
        out = courier.run(orders, sink, download=a.download)
    elif a.step == "read":
        if not a.reader:
            ap.error("read needs --reader")
        out = read(orders, sink, make_reader(a.reader, a))
    elif a.step == "verify":
        out = verify(orders, sink)
    elif a.step == "index":
        out = index(orders, sink, embed=not a.no_embed)
    elif a.step == "audit":
        out = auditor.run(orders, sink)
        out = {k: v for k, v in out.items() if k not in ("gold",)} | {
            "gold": {
                r: {
                    k: g[k]
                    for k in (
                        "found",
                        "comparable_nonzero",
                        "voice_agrees",
                        "voice_checked",
                        "licensee_agrees",
                        "licensee_checked",
                    )
                }
                for r, g in out["gold"].items()
            }
        }
        for k in ("gold_common_set",):
            out[k] = {
                r: {kk: g[kk] for kk in ("found", "comparable_nonzero", "voice_agrees", "voice_checked")}
                for r, g in out.get(k, {}).items()
            }
    elif a.step == "direct":
        res = director.direct(orders, sink)
        print(res["brief"])
        out = res["planned"]
    elif a.step == "work":
        out = work(orders, sink, a)
    else:  # all
        r = Run("seed", "reference 1")
        seeded = reference.seed(sink)
        r.post(sink, "ok", "reference rows", rows_written=sum(v["written"] for v in seeded.values()))
        courier.run(orders, sink, download=a.download)
        read(orders, sink, make_reader("textlayer", a))
        director.direct(orders, sink)
        done = work(orders, sink, a)
        res = director.direct(orders, sink)
        print(res["brief"])
        out = {"work": done, "planned": res["planned"]}
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
