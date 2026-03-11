"""
eval_swebench.py — Evaluate DevAgent on SWE-Bench Lite.

Usage:
  python scripts/eval_swebench.py --limit 10
  python scripts/eval_swebench.py --limit 50 --output results.json

SWE-Bench Lite: 300 real GitHub issues from popular Python repos.
Download dataset: pip install swebench
"""
from __future__ import annotations

import json
import time
import argparse
import sys
import pathlib
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


def run_eval(limit: int = 10, output_file: str = "swebench_results.json") -> None:
    try:
        from swebench.harness.run_evaluation import main as swe_main
    except ImportError:
        print("ERROR: swebench not installed. Run: pip install swebench")
        return

    from config import cfg
    cfg.validate()

    from agent.graph import app
    from tools.github_client import fetch_issue, clone_repo

    # Load SWE-Bench Lite dataset
    try:
        import datasets
        dataset = datasets.load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    except Exception as e:
        print(f"ERROR loading dataset: {e}")
        print("Make sure: pip install datasets swebench")
        return

    results = []
    resolved = 0
    total = min(limit, len(dataset))

    print(f"\nEvaluating DevAgent on {total} SWE-Bench Lite instances...\n")

    for i, instance in enumerate(dataset.select(range(total))):
        instance_id = instance["instance_id"]
        issue_url = f"https://github.com/{instance['repo']}/issues/{instance['issue_number']}"

        print(f"[{i+1}/{total}] {instance_id}")
        print(f"  Issue: {instance['problem_statement'][:80]}...")

        start = time.time()
        status = "error"
        pr_url = None
        error_msg = None

        try:
            # Fetch and clone
            issue_data = fetch_issue(issue_url)
            repo_path = clone_repo(issue_data["repo_owner"], issue_data["repo_name"])

            # Build initial state
            initial_state = {
                "issue_url":    issue_url,
                "issue_number": issue_data["number"],
                "issue_title":  issue_data["title"],
                "issue_body":   issue_data["body"],
                "repo_owner":   issue_data["repo_owner"],
                "repo_name":    issue_data["repo_name"],
                "repo_path":    repo_path,
                "action_plan":  [],
                "files_to_edit": [],
                "messages":     [],
                "code_changes": [],
                "test_output":  None,
                "test_passed":  False,
                "retry_count":  0,
                "branch_name":  None,
                "pr_url":       None,
                "error":        None,
            }

            # Run agent
            final_state = app.invoke(initial_state)

            if final_state.get("test_passed"):
                status = "resolved"
                pr_url = final_state.get("pr_url")
                resolved += 1
                print(f"  ✓ RESOLVED in {time.time()-start:.1f}s  |  PR: {pr_url}")
            else:
                status = "failed"
                print(f"  ✗ FAILED in {time.time()-start:.1f}s")

        except Exception as e:
            error_msg = str(e)
            print(f"  ✗ ERROR: {error_msg[:100]}")

        results.append({
            "instance_id": instance_id,
            "status":      status,
            "pr_url":      pr_url,
            "error":       error_msg,
            "elapsed_s":   round(time.time() - start, 1),
        })

    # Summary
    resolution_rate = (resolved / total) * 100
    print(f"\n{'='*50}")
    print(f"RESULTS: {resolved}/{total} resolved ({resolution_rate:.1f}%)")
    print(f"{'='*50}\n")

    # Save results
    output = {
        "timestamp":       datetime.now().isoformat(),
        "model":           cfg.CEREBRAS_MODEL,
        "total":           total,
        "resolved":        resolved,
        "resolution_rate": f"{resolution_rate:.1f}%",
        "instances":       results,
    }
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate DevAgent on SWE-Bench Lite")
    parser.add_argument("--limit",  type=int, default=10, help="Number of instances to evaluate")
    parser.add_argument("--output", type=str, default="swebench_results.json", help="Output file")
    args = parser.parse_args()
    run_eval(args.limit, args.output)
