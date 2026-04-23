"""
evaluate_semantic_view.py
Batch evaluation of a semantic view against question banks.

Usage:
    python evaluate_semantic_view.py --environment test --semantic-view RETAIL_AI_TEST.SEMANTIC.RETAIL_ANALYTICS_SV
    python evaluate_semantic_view.py --environment dev --categories easy,hard
    python evaluate_semantic_view.py --environment test --git-sha abc123 --git-branch feature/update-sv
"""
import argparse
import json
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    get_connection, load_question_bank, load_thresholds,
    execute_sql, call_cortex_analyst, log_eval_run, format_results_table,
)
from llm_judge import judge_sql_result, judge_ambiguous_result


def extract_sql_from_analyst_response(response: dict) -> str:
    try:
        choices = response.get("choices", [])
        if choices:
            messages = choices[0].get("messages", []) or choices[0].get("message", {}).get("content", [])
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict) and msg.get("type") == "sql":
                        return msg.get("statement", "")
            elif isinstance(messages, str):
                return messages
    except Exception:
        pass
    return ""


def evaluate_question(conn, semantic_view: str, question: dict, env_database: str) -> dict:
    start_time = time.time()
    result = {
        "question_id": question["id"],
        "question_text": question["question"],
        "difficulty": question.get("category", "unknown"),
    }

    analyst_response = call_cortex_analyst(conn, semantic_view, question["question"])
    generated_sql = extract_sql_from_analyst_response(analyst_response)
    result["generated_sql"] = generated_sql
    result["latency_ms"] = int((time.time() - start_time) * 1000)

    if not generated_sql:
        result["match_status"] = "NO_SQL_GENERATED"
        result["llm_judge_score"] = 0.0
        result["llm_judge_reasoning"] = "Cortex Analyst did not generate SQL"
        return result

    if question.get("category") == "ambiguous":
        generated_result = execute_sql(conn, generated_sql)
        result["generated_result"] = generated_result
        judge_result = judge_ambiguous_result(
            conn,
            question["question"],
            question.get("evaluation_criteria", ""),
            generated_sql,
            generated_result,
        )
        result["match_status"] = "PASSED" if judge_result.get("passed") else "FAILED"
        result["llm_judge_score"] = judge_result.get("overall_score", 0)
        result["llm_judge_reasoning"] = judge_result.get("reasoning", "")
    else:
        expected_sql = question.get("expected_sql", "")
        expected_result = execute_sql(conn, expected_sql) if expected_sql else []
        generated_result = execute_sql(conn, generated_sql)
        result["expected_sql"] = expected_sql
        result["expected_result"] = expected_result
        result["generated_result"] = generated_result

        judge_result = judge_sql_result(
            conn, question["question"], expected_sql, generated_sql,
            expected_result, generated_result,
        )
        result["match_status"] = "PASSED" if judge_result.get("passed") else "FAILED"
        result["llm_judge_score"] = judge_result.get("overall_score", 0)
        result["llm_judge_reasoning"] = judge_result.get("reasoning", "")

    return result


def run_evaluation(
    environment: str,
    semantic_view: str,
    categories: list = None,
    git_sha: str = "",
    git_branch: str = "",
) -> dict:
    if categories is None:
        categories = ["easy", "hard", "ambiguous"]

    conn = get_connection(environment)
    thresholds = load_thresholds()
    env_thresholds = thresholds.get("semantic_view", {}).get(environment, thresholds["semantic_view"]["default"])

    all_results = []
    for category in categories:
        questions = load_question_bank("semantic_view", category)
        print(f"\n{'='*60}")
        print(f"Evaluating {len(questions)} {category.upper()} questions")
        print(f"{'='*60}")

        for q in questions:
            print(f"  [{q['id']}] {q['question'][:60]}...", end=" ")
            result = evaluate_question(
                conn, semantic_view, q,
                env_database=f"RETAIL_AI_{environment.upper()}"
            )
            status = result["match_status"]
            score = result.get("llm_judge_score", 0)
            print(f"{'PASS' if status == 'PASSED' else 'FAIL'} (score: {score:.2f}, {result['latency_ms']}ms)")
            all_results.append(result)

    passed = sum(1 for r in all_results if r["match_status"] == "PASSED")
    total = len(all_results)
    accuracy = (passed / total * 100) if total > 0 else 0
    threshold = env_thresholds.get("accuracy_threshold", 80)
    passed_threshold = accuracy >= threshold

    summary = {
        "environment": environment,
        "semantic_view_name": semantic_view,
        "git_commit_sha": git_sha,
        "git_branch": git_branch,
        "total_questions": total,
        "passed_questions": passed,
        "failed_questions": total - passed,
        "accuracy_pct": round(accuracy, 2),
        "threshold_pct": threshold,
        "passed_threshold": passed_threshold,
        "run_details": {
            "categories": categories,
            "by_category": {},
        },
    }

    for cat in categories:
        cat_results = [r for r in all_results if r["difficulty"] == cat]
        cat_passed = sum(1 for r in cat_results if r["match_status"] == "PASSED")
        cat_total = len(cat_results)
        summary["run_details"]["by_category"][cat] = {
            "total": cat_total,
            "passed": cat_passed,
            "accuracy_pct": round(cat_passed / cat_total * 100, 2) if cat_total > 0 else 0,
        }

    print(f"\n{'='*60}")
    print(f"EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Environment:    {environment}")
    print(f"Semantic View:  {semantic_view}")
    print(f"Total:          {total}")
    print(f"Passed:         {passed}")
    print(f"Failed:         {total - passed}")
    print(f"Accuracy:       {accuracy:.1f}%")
    print(f"Threshold:      {threshold}%")
    print(f"Result:         {'PASSED' if passed_threshold else 'FAILED'}")
    print(f"{'='*60}")

    for cat, stats in summary["run_details"]["by_category"].items():
        print(f"  {cat:12s}:  {stats['passed']}/{stats['total']} ({stats['accuracy_pct']:.1f}%)")

    try:
        log_eval_run(conn, "SEMANTIC_VIEW_EVAL_RUNS", summary)
        for r in all_results:
            log_eval_run(conn, "SEMANTIC_VIEW_EVAL_DETAILS", {
                "eval_run_id": summary.get("eval_run_id", ""),
                **{k: v for k, v in r.items() if k not in ("expected_result", "generated_result")},
                "expected_result": json.dumps(r.get("expected_result", []), default=str),
                "generated_result": json.dumps(r.get("generated_result", []), default=str),
            })
    except Exception as e:
        print(f"Warning: Could not log results to Snowflake: {e}")

    return {"summary": summary, "details": all_results, "passed_threshold": passed_threshold}


def main():
    parser = argparse.ArgumentParser(description="Evaluate a semantic view against question banks")
    parser.add_argument("--environment", "-e", default="test", choices=["dev", "test", "prod"])
    parser.add_argument("--semantic-view", "-s", required=True, help="Fully qualified semantic view name")
    parser.add_argument("--categories", "-c", default="easy,hard,ambiguous", help="Comma-separated categories")
    parser.add_argument("--git-sha", default="", help="Git commit SHA for tracking")
    parser.add_argument("--git-branch", default="", help="Git branch name for tracking")
    parser.add_argument("--output", "-o", default="", help="Output JSON file path")
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",")]
    result = run_evaluation(
        environment=args.environment,
        semantic_view=args.semantic_view,
        categories=categories,
        git_sha=args.git_sha,
        git_branch=args.git_branch,
    )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nResults written to {args.output}")

    sys.exit(0 if result["passed_threshold"] else 1)


if __name__ == "__main__":
    main()
