"""Admin CLI for license keys — issue, revoke, reactivate, floor, quota, list, usage.

  python -m licenseproxy.admin issue --customer "PRIME|PR" --plan pro --version-floor 1.0.0 \
                                     --features crawl,export --quota 20000000
  python -m licenseproxy.admin revoke <key>          # the kill switch
  python -m licenseproxy.admin floor  <key> 1.3.0    # force-upgrade old versions
  python -m licenseproxy.admin list
  python -m licenseproxy.admin usage [<key>]

DB path defaults to ./licenses.db (override with LICENSE_DB).
"""
from __future__ import annotations

import argparse
import os

from .policy import LicenseStore

DB = os.getenv("LICENSE_DB", "licenses.db")


def _fmt(lic: dict) -> str:
    state = "ACTIVE" if lic["active"] else "REVOKED"
    q = "unlimited" if lic["quota_tokens"] < 0 else f"{lic['used_tokens']}/{lic['quota_tokens']}"
    floor = lic["version_floor"] or "-"
    return (f"[{state:7}] {lic['key']}  customer={lic['customer']!r} plan={lic['plan']} "
            f"floor>={floor} features={lic['features'] or '-'} tokens={q}")


def main() -> int:
    ap = argparse.ArgumentParser(description="cfp-monitor license admin")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("issue")
    p.add_argument("--customer", required=True)
    p.add_argument("--plan", default="standard")
    p.add_argument("--version-floor", default="")
    p.add_argument("--features", default="")
    p.add_argument("--quota", type=int, default=-1, help="token cap for the period (-1 = unlimited)")

    for name in ("revoke", "reactivate"):
        sp = sub.add_parser(name)
        sp.add_argument("key")

    p = sub.add_parser("floor")
    p.add_argument("key"); p.add_argument("version")

    p = sub.add_parser("quota")
    p.add_argument("key"); p.add_argument("tokens", type=int)
    p.add_argument("--reset-used", action="store_true")

    sub.add_parser("list")
    p = sub.add_parser("usage"); p.add_argument("key", nargs="?")

    a = ap.parse_args()
    store = LicenseStore(DB)

    if a.cmd == "issue":
        feats = [f for f in a.features.split(",") if f]
        key = store.issue(a.customer, a.plan, a.version_floor, feats, a.quota)
        print("issued:", key)
        print(_fmt(store.get(key)))
    elif a.cmd == "revoke":
        print("revoked" if store.revoke(a.key) else "no such key",
              "- that customer's crawling stops on the next extraction call." if True else "")
    elif a.cmd == "reactivate":
        print("reactivated" if store.reactivate(a.key) else "no such key")
    elif a.cmd == "floor":
        print("floor set" if store.set_version_floor(a.key, a.version) else "no such key")
    elif a.cmd == "quota":
        print("quota set" if store.set_quota(a.key, a.tokens, a.reset_used) else "no such key")
    elif a.cmd == "list":
        rows = store.all()
        print(f"{len(rows)} license(s):")
        for lic in rows:
            print(" ", _fmt(lic))
    elif a.cmd == "usage":
        print(store.usage_summary(a.key))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
