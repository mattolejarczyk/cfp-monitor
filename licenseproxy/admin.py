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

    p = sub.add_parser("billing", help="per-customer token/cost summary for invoicing")
    p.add_argument("--period", help="filter by month, e.g. 2026-07 (default: all time)")
    p.add_argument("--rate", type=float, default=0.0, help="$ per MILLION tokens -> adds a cost column")
    p.add_argument("--csv", action="store_true", help="output CSV instead of a table")

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
    elif a.cmd == "billing":
        rows = store.billing(a.period, a.rate)
        label = a.period or "all time"
        if a.csv:
            import csv, sys as _sys
            w = csv.DictWriter(_sys.stdout, fieldnames=["customer", "plan", "active", "calls", "tokens", "cost", "key"])
            w.writeheader(); w.writerows(rows)
        else:
            print(f"Billing — {label}" + (f" @ ${a.rate}/M tokens" if a.rate else ""))
            print(f"  {'customer':24} {'plan':8} {'calls':>7} {'tokens':>12} {'cost':>10}")
            tt = tc = 0
            for r in rows:
                tt += r["tokens"]; tc += r["cost"]
                flag = "" if r["active"] else " (revoked)"
                print(f"  {(r['customer'] or '')[:24]:24} {r['plan'][:8]:8} {r['calls']:>7} "
                      f"{r['tokens']:>12,} {('$'+format(r['cost'],'.2f')):>10}{flag}")
            print(f"  {'TOTAL':24} {'':8} {'':>7} {tt:>12,} {('$'+format(tc,'.2f')):>10}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
