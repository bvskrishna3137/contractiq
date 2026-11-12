"""Command line: `contractiq extract` and `contractiq evaluate`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .evaluate import evaluate, format_report
from .export import requirements_csv, to_json, to_xlsx
from .pipeline import run
from .schema import Extraction


def _progress(i: int, n: int) -> None:
    print(f"  LLM request {i}/{n}...", file=sys.stderr, flush=True)


def _summary(ex: Extraction) -> str:
    s = ex.stats()
    lines = [f"{ex.metadata.source_file}: {ex.metadata.page_count} pages, mode={ex.metadata.mode}"
             + (f" ({ex.metadata.model})" if ex.metadata.model else ""),
             f"  {s['requirements']} requirements ({s['mandatory']} mandatory), {s['key_dates']} key dates, "
             f"{s['evaluation_factors']} evaluation factors, {s['deliverables']} CDRLs, {s['clins']} CLINs"]
    if ex.terms.contract_type:
        lines.append(f"  contract type: {ex.terms.contract_type}")
    if s["ungrounded"]:
        lines.append(f"  ! {s['ungrounded']} item(s) could not be matched to the document text")
    lines += [f"  warning: {w}" for w in ex.warnings]
    return "\n".join(lines)


def _cmd_extract(a: argparse.Namespace) -> int:
    if a.mode == "llm" and a.dry_run:
        from .extractors.llm import estimate
        from .pdf import read_pages
        e = estimate(read_pages(a.file))
        print(f"LLM mode would make {e['calls']} request(s), roughly {e['approx_input_tokens']:,} input tokens. "
              "No request was sent.")
        return 0
    ex = run(a.file, mode=a.mode, model=a.model, progress=_progress if a.mode == "llm" else None)
    print(_summary(ex))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(a.file).stem
    fmts = {f.strip() for f in a.format.split(",")}
    written = []
    if "json" in fmts:
        (out / f"{stem}.json").write_text(to_json(ex), encoding="utf-8")
        written.append(f"{stem}.json")
    if "csv" in fmts:
        (out / f"{stem}_requirements.csv").write_text(requirements_csv(ex), encoding="utf-8", newline="")
        written.append(f"{stem}_requirements.csv")
    if "xlsx" in fmts:
        to_xlsx(ex, out / f"{stem}.xlsx")
        written.append(f"{stem}.xlsx")
    print(f"  wrote {', '.join(written)} to {out}/")
    return 0


def _cmd_evaluate(a: argparse.Namespace) -> int:
    gold = Extraction.model_validate_json(Path(a.gold).read_text(encoding="utf-8"))
    ex = run(a.file, mode=a.mode, model=a.model, progress=_progress if a.mode == "llm" else None)
    rep = evaluate(ex, gold)
    print(json.dumps(rep, indent=2) if a.json else f"{_summary(ex)}\n\n{format_report(rep)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="contractiq", description="Extract a compliance matrix from a federal solicitation PDF.")
    p.add_argument("--version", action="version", version=f"contractiq {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("file", help="PDF (or .txt) solicitation")
        sp.add_argument("--mode", choices=["rules", "llm"], default="rules",
                        help="rules = offline, no key (default); llm = Anthropic API (needs ANTHROPIC_API_KEY)")
        sp.add_argument("--model", help="LLM model name (default: $CONTRACTIQ_MODEL or claude-sonnet-5-5)")

    e = sub.add_parser("extract", help="extract and write JSON / CSV / Excel")
    common(e)
    e.add_argument("--out", default="output", help="output folder (default: output)")
    e.add_argument("--format", default="json,csv,xlsx", help="comma list of json,csv,xlsx")
    e.add_argument("--dry-run", action="store_true", help="llm mode: show the number of requests and size, send nothing")
    e.set_defaults(fn=_cmd_extract)

    v = sub.add_parser("evaluate", help="score an extraction against a hand-labelled answer key")
    common(v)
    v.add_argument("--gold", required=True, help="answer key JSON (see samples/gold.json)")
    v.add_argument("--json", action="store_true", help="print the full report as JSON")
    v.set_defaults(fn=_cmd_evaluate)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (RuntimeError, FileNotFoundError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
