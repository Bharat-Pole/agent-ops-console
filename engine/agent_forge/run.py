"""CLI: python -m agent_forge <AgentRecord.json> --out dist/ [--zip] [--llm-target=…]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generate import generate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent_forge", description="spec→code LangGraph generator")
    ap.add_argument("config", help="path to a console AgentRecord JSON export")
    ap.add_argument("--out", default="dist", help="output directory (default: dist)")
    ap.add_argument("--zip", action="store_true", help="also write <slug>.zip")
    ap.add_argument("--llm-target", choices=["aistudio", "vertex"], default="aistudio")
    args = ap.parse_args(argv)

    res = generate(args.config, llm_target=args.llm_target)
    out = Path(args.out) / res.agent.slug
    res.write(out)

    print(f"agent    : {res.agent.name}  ({res.agent.agent_id})")
    print(f"topology : {res.topology.value}")
    print(f"llm      : {args.llm_target} model={res.agent.model.primary}")
    print(f"wrote    : {len(res.files)} files -> {out}")

    b = res.blockers
    active = {k: v for k, v in b.items() if k != "has_hard_blockers" and v}
    if active:
        print("blockers :", active, file=sys.stderr)
        if b["has_hard_blockers"]:
            print("  (hard blockers present — review before deploying; write tools are never bound)",
                  file=sys.stderr)

    if args.zip:
        zp = Path(args.out) / f"{res.agent.slug}.zip"
        zp.write_bytes(res.zip_bytes())
        print(f"zip      : {zp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
