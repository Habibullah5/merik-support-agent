"""
Run the 20 scripted scenarios (or the failure-mode reproductions) and write one trace per run.

    python run_scenarios.py --label before                  # REAL model, needs ANTHROPIC_API_KEY
    python run_scenarios.py --label before --only 12 18     # a subset
    python run_scenarios.py --label after  --failures --scripted   # replay failure-mode scripts (no API)
    python run_scenarios.py --label reference_golden --scripted     # replay golden paths (no API)

Traces land in traces/<label>/sNN.jsonl (or F1.jsonl ... for failure scenarios) and a
summary.json with the checker's verdicts.
"""
import argparse
import json
from pathlib import Path

from agent.llm import ScriptedClient
from agent.loop import run_agent
from evaluation.checker import analyse, load_trace

ROOT = Path(__file__).parent


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="folder under traces/, e.g. before | after")
    ap.add_argument("--only", nargs="*", help="scenario numbers (or F1..F4 with --failures)")
    ap.add_argument("--scripted", action="store_true", help="replay scripts instead of calling the model")
    ap.add_argument("--failures", action="store_true", help="run data/failure_scenarios.json (F1..F4)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    expectations = json.loads((ROOT / "data/expectations.json").rAead_text(encoding="utf-8"))
    out_dir = ROOT / "traces" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = []  # (run_id, sender, message, expectation, script_or_None)
    if args.failures:
        from scripted.failure_modes import SCRIPTS
        for fid, f in json.loads((ROOT / "data/failure_scenarios.json").read_text(encoding="utf-8")).items():
            jobs.append((fid, f["sender"], f["message"], expectations[str(f["scenario"])], SCRIPTS[f["script"]]))
    else:
        scenarios = json.loads((ROOT / "data/scenarios.json").read_text(encoding="utf-8"))
        golden = None
        if args.scripted:
            from scripted.golden import GOLDEN
            golden = GOLDEN
        for s in scenarios:
            jobs.append((f"s{s['id']:02d}", s["sender"], s["message"], expectations[str(s["id"])],
                         golden[s["id"]] if golden else None))

    if args.only:
        wanted = {w.lower().lstrip("s").lstrip("0") or "0" for w in args.only}
        jobs = [j for j in jobs if j[0].lower().lstrip("sf").lstrip("0") in wanted or j[0].lower() in {w.lower() for w in args.only}]

    summary = {}
    for run_id, sender, message, exp, script in jobs:
        print(f"\n=== {run_id}  {sender}: {message!r}")
        client = ScriptedClient(script) if (args.scripted and script is not None) else None
        path = out_dir / f"{run_id}.jsonl"
        res = run_agent(message, sender, client=client, scenario=run_id, log_path=str(path), verbose=not args.quiet)
        verdict = analyse(load_trace(path), exp)
        summary[run_id] = {"verdict": verdict["verdict"], "stop_reason": res["stop_reason"],
                           "cost_usd": round(res["cumulative_cost_usd"], 5), "path": verdict["path"]}
        print(f"  -> {verdict['verdict']}  ({res['stop_reason']})")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = sum(1 for v in summary.values() if v["verdict"] == "PASS")
    print(f"\n{ok}/{len(summary)} PASS  ->  {out_dir}")


if __name__ == "__main__":
    main()
