"""
Run the evaluation suite and print a before/after score table.

    python -m evals.run --label baseline
    python -m evals.run --label A2-prompt                 # compares with baseline + previous run
    python -m evals.run --label A2-prompt --compare baseline,A1-leadfix
    python -m evals.run --label dbg --cases F01,J01,D03   # subset; saved as .local.json (gitignored)
    python -m evals.run --show A2-prompt                  # re-print a saved run, no API calls

Evals NEVER touch production lead data: a temporary lead DB is set before any project import.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"

# --- isolation: must happen before importing any project module --------------------------
_TMP = Path(tempfile.mkdtemp(prefix="chatbot_evals_"))
os.environ["LEADS_DB_PATH"] = str(_TMP / "leads.db")
os.environ["LEADS_JSON_PATH"] = str(_TMP / "leads.json")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")  # don't ship eval traffic to LangSmith

from evals import metrics  # noqa: E402


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_turns(adapter, session_id: str, turns, delay: float):
    out = []
    for text in turns:
        t0 = time.time()
        try:
            res = adapter.turn(session_id, text)
        except Exception as e:  # record, don't abort the whole run
            res = {"answer": f"[ERROR] {type(e).__name__}: {e}", "contexts": [], "meta": {"error": True}}
        res["latency_s"] = round(time.time() - t0, 2)
        res["user"] = text
        out.append(res)
        if delay:
            time.sleep(delay)
    return out


def run_qa(adapter, judge, cases, run_id: str, delay: float):
    results = []
    for i, case in enumerate(cases, 1):
        sid = f"eval-{run_id}-{case['id']}"
        print(f"  [{i:>2}/{len(cases)}] {case['id']:<4} {case['category']:<12}", end="", flush=True)
        if case.get("inject_doc"):
            with adapter.temporary_document(case["inject_doc"]):
                turns = run_turns(adapter, sid, case["turns"], delay)
        else:
            turns = run_turns(adapter, sid, case["turns"], delay)
        final = turns[-1]
        verdict = judge.evaluate(case["turns"][:-1], final["contexts"], case["turns"][-1], final["answer"])
        score = metrics.score_qa_case(case, final, verdict)
        print("PASS" if score["passed"] else "FAIL", f"({final['latency_s']}s)")
        results.append({
            "id": case["id"], "category": case["category"], "lang": case.get("lang", "en"),
            "expect": case["expect"], "turns": case["turns"], "answer": final["answer"],
            "contexts": final["contexts"][: metrics.TOP_K], "latency_s": final["latency_s"],
            "verdict": verdict, "score": score,
        })
    return results


def run_leads(adapter, dialogues, run_id: str, delay: float):
    results = []
    for i, d in enumerate(dialogues, 1):
        sid = f"eval-{run_id}-{d['id']}"
        print(f"  [{i:>2}/{len(dialogues)}] {d['id']:<4} {d['desc'][:48]:<48}", end="", flush=True)
        turns = run_turns(adapter, sid, d["turns"], delay)
        lead = metrics.lead_matches(adapter.get_lead(sid), d.get("expected_lead"))
        checks = []
        for chk in d.get("answer_checks", []):
            ok = metrics.groups_match(turns[chk["turn"]]["answer"], chk["must_include"])
            checks.append({"turn": chk["turn"], "ok": ok})
        asked_again = False
        if "forbid_ask_after_turn" in d:
            asked_again = any(metrics.asks_for_contact(t["answer"]) for t in turns[d["forbid_ask_after_turn"] + 1:])
        passed = lead["lead_ok"] and all(c["ok"] for c in checks) and not asked_again
        print("PASS" if passed else "FAIL")
        results.append({
            "id": d["id"], "desc": d["desc"], "expected_lead": d.get("expected_lead"),
            "actual_lead": {k: v for k, v in (adapter.get_lead(sid) or {}).items() if k != "raw"} or None,
            "lead": lead, "answer_checks": checks, "asked_again": asked_again, "passed": passed,
            "transcript": [{"user": t["user"], "bot": t["answer"]} for t in turns],
        })
    return results


# --- reporting ------------------------------------------------------------------------------
def load_result(label: str):
    for name in (f"{label}.json", f"{label}.local.json"):
        p = RESULTS_DIR / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise SystemExit(f"No saved run named '{label}' in {RESULTS_DIR}")


def default_comparisons(current_label: str):
    runs = []
    for p in RESULTS_DIR.glob("*.json"):
        if p.name.endswith(".local.json"):
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if data["label"] != current_label:
            runs.append(data)
    runs.sort(key=lambda r: r["timestamp"])
    picked = [r for r in runs if r["label"] == "baseline"]
    others = [r for r in runs if r["label"] != "baseline"]
    if others:
        picked.append(others[-1])
    return picked


def fmt(v):
    return "   -  " if v is None else f"{v:6.2f}"


def print_table(current, comparisons):
    cols = comparisons + [current]
    width = max(12, *(len(c["label"]) for c in cols))
    keys = list(current["metrics"].keys())
    header = f"{'metric':<22}" + "".join(f"{c['label']:>{width + 2}}" for c in cols)
    if comparisons:
        header += f"{'Δ prev':>10}"
    print("\n" + header)
    print("-" * len(header))
    for k in keys:
        row = f"{k:<22}" + "".join(f"{fmt(c['metrics'].get(k)):>{width + 2}}" for c in cols)
        if comparisons:
            prev, cur = comparisons[-1]["metrics"].get(k), current["metrics"].get(k)
            if prev is not None and cur is not None:
                d = cur - prev
                better = (d < 0) if k in metrics.LOWER_IS_BETTER else (d > 0)
                mark = "" if abs(d) < 1e-9 else (" ▲" if better else " ▼")
                row += f"{d:+9.2f}{mark}"
        print(row)
    print()


def print_failures(current):
    fails = [c for c in current.get("qa", []) if not c["score"]["passed"]]
    fails += [d for d in current.get("leads", []) if not d["passed"]]
    if not fails:
        print("All cases passed.")
        return
    print(f"Failing cases ({len(fails)}):")
    for c in fails:
        if "score" in c:
            s = c["score"]
            why = []
            if c["expect"] == "answer" and not s["must_ok"]:
                why.append("missing expected fact")
            if s["hit"] is False:
                why.append("evidence not retrieved")
            if s["response_type"] != {"answer": "answer"}.get(c["expect"], s["response_type"]):
                why.append(f"type={s['response_type']}")
            if not s["forbid_ok"]:
                why.append("forbidden text")
            if s["makes_commitment"]:
                why.append("commitment")
            if s["followed_injection"]:
                why.append("followed injection")
            if c["expect"] in ("decline", "redirect") and s["response_type"] not in ("decline", "redirect"):
                why.append(f"expected {c['expect']}")
            print(f"  {c['id']:<4} {c['category']:<12} {', '.join(dict.fromkeys(why)) or 'see details'}")
        else:
            why = []
            if not c["lead"]["lead_ok"]:
                why.append(f"lead expected={c['expected_lead'] and {k: c['expected_lead'][k] for k in ('name', 'email', 'interest_category')}} got={c['actual_lead']}")
            if any(not x["ok"] for x in c["answer_checks"]):
                why.append("question not answered")
            if c["asked_again"]:
                why.append("asked for contact again after capture")
            print(f"  {c['id']:<4} lead         {'; '.join(why)}")
    print()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", help="name for this run (e.g. baseline, A2-prompt)")
    ap.add_argument("--only", choices=["qa", "lead"], help="run just one suite")
    ap.add_argument("--cases", help="comma-separated case ids (subset run, saved as .local.json)")
    ap.add_argument("--compare", help="comma-separated saved labels to compare against")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep between turns (rate limits)")
    ap.add_argument("--show", help="print a saved run without calling any API")
    args = ap.parse_args(argv)

    if args.show:
        current = load_result(args.show)
        comps = [load_result(x) for x in args.compare.split(",")] if args.compare else default_comparisons(current["label"])
        print_table(current, comps)
        print_failures(current)
        return

    if not args.label:
        ap.error("--label is required (or use --show)")

    from evals.adapter import get_adapter
    from evals.judge import Judge

    wanted = set(args.cases.split(",")) if args.cases else None
    qa_cases = [c for c in load_jsonl(EVAL_DIR / "golden.jsonl") if not wanted or c["id"] in wanted]
    dialogues = [d for d in load_jsonl(EVAL_DIR / "lead_dialogues.jsonl") if not wanted or d["id"] in wanted]
    if args.only == "qa":
        dialogues = []
    if args.only == "lead":
        qa_cases = []

    adapter, judge = get_adapter(), Judge()
    run_id = uuid.uuid4().hex[:6]
    print(f"Adapter: {adapter.name} | judge: {judge.model} | run {run_id}")
    qa = []
    if qa_cases:
        print(f"\nQA cases ({len(qa_cases)})")
        qa = run_qa(adapter, judge, qa_cases, run_id, args.delay)
    leads = []
    if dialogues:
        print(f"\nLead dialogues ({len(dialogues)})")
        leads = run_leads(adapter, dialogues, run_id, args.delay)

    partial = bool(wanted or args.only)
    current = {
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "adapter": adapter.name,
        "judge_model": judge.model,
        "partial": partial,
        "metrics": metrics.aggregate(qa, leads),
        "qa": qa,
        "leads": leads,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / (f"{args.label}.local.json" if partial else f"{args.label}.json")
    out.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")

    comps = [load_result(x) for x in args.compare.split(",")] if args.compare else ([] if partial else default_comparisons(args.label))
    print_table(current, comps)
    print_failures(current)
    print(f"Saved: {out.relative_to(EVAL_DIR.parent)}")


if __name__ == "__main__":
    sys.exit(main())
