import argparse
import json
from pathlib import Path
from .store import Store
from .crawler import Crawler
from .export import freeze, web_snapshot

parser = argparse.ArgumentParser(description="CPBench reproducible Codeforces corpus")
parser.add_argument("--data", default="data")
commands = parser.add_subparsers(dest="command", required=True)
server = commands.add_parser("serve")
server.add_argument("--port", type=int, default=8765)
commands.add_parser("sync")
seed = commands.add_parser("seed")
seed.add_argument("problemset")
seed.add_argument("contests")
exp = commands.add_parser("freeze")
exp.add_argument("destination")
snap = commands.add_parser("snapshot")
snap.add_argument("destination", default="dist", nargs="?")
crawl = commands.add_parser("crawl")
crawl.add_argument("kind", choices=["statements", "references"])
crawl.add_argument("--min-rating", type=int)
crawl.add_argument("--max-rating", type=int)
crawl.add_argument("--limit", type=int, default=0)
crawl.add_argument("--metadata-only", action="store_true")
crawl.add_argument("--verify-imported", action="store_true")
args = parser.parse_args()
if args.command == "serve":
    import uvicorn
    from .api import create_app

    uvicorn.run(create_app(args.data), host="127.0.0.1", port=args.port, workers=1)
else:
    store = Store(args.data)
    if args.command == "sync":
        from .locking import CollectorLock

        with CollectorLock(store.root):
            print(Crawler(store).sync_metadata())
    elif args.command == "seed":
        p = Path(args.problemset).read_bytes()
        c = Path(args.contests).read_bytes()
        pp = store.evidence("https://codeforces.com/api/problemset.problems", p)
        cp = store.evidence("https://codeforces.com/api/contest.list", c)
        print(store.ingest_catalog(json.loads(p), json.loads(c), pp, cp))
    elif args.command == "freeze":
        print(json.dumps(freeze(store, args.destination), ensure_ascii=False, indent=2))
    elif args.command == "snapshot":
        web_snapshot(store, args.destination)
        print("Web snapshot written")
    elif args.command == "crawl":
        from .jobs import JobManager
        import time

        m = JobManager(store)
        j = m.create(
            args.kind,
            dict(
                min_rating=args.min_rating,
                max_rating=args.max_rating,
                limit=args.limit,
                metadata_only=args.metadata_only,
                verify_imported=args.verify_imported,
            ),
        )
        while m.get(j["id"])["state"] in ("queued", "running"):
            time.sleep(1)
        result = m.get(j["id"])
        print(json.dumps(result, indent=2))
        m.close()
        raise SystemExit(0 if result["state"] == "completed" else 1)
