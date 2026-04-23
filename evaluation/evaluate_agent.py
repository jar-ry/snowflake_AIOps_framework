"""
evaluate_agent.py
Batch evaluation of a Cortex Agent against question banks.
Measures the RAG Triad (Context Relevance, Groundedness, Answer Relevance)
plus safety and boundary testing.

Usage:
    python evaluate_agent.py --environment test --agent-name RETAIL_AI_TEST.SEMANTIC.RETAIL_AGENT
    python evaluate_agent.py --environment test --categories answerable,out_of_scope,adversarial
    python evaluate_agent.py --environment test --git-sha abc123 --output results.json
"""
import argparse
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    get_connection, load_question_bank, load_thresholds,
    call_cortex_agent, log_eval_run,
)
from llm_judge import judge_agent_response


def evaluate_agent_question(conn, agent_name: str, question: dict) -> dict:
    start_time = time.time()
    result = {
        "question_id": question["id"],
        "question_text": question["question"],
        "category": question.get("category", "unknown"),
        "should_answer": question.get("should_answer", True),
    }

    try:
        agent_response = call_cortex_agent(conn, agent_name, question["question"])
        response_text = ""
        tool_calls = []

        if isinstance(agent_response, dict):
            choices = agent_response.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                response_text = content if isinstance(content, str) else json.dumps(content)
            tool_calls = agent_response.get("tool_calls", [])
        else:
            response_text = str(agent_response)

        result["agent_response"] = response_text
        result["tool_calls_made"] = tool_calls
        result["did_answer"] = bool(response_text and len(response_text.strip()) > 10)

    except Exception as e:
        result["agent_response"] = f"ERROR: {str(e)}"
        result["did_answer"] = False
        result["tool_calls_made"] = []

    result["latency_ms"] = int((time.time() - start_time) * 1000)

    additional_context = ""
    if question.get("expected_answer_contains"):
        additional_context += f"Expected answer should contain: {question['expected_answer_contains']}\n"
    if question.get("expected_behavior"):
        additional_context += f"Expected behavior: {question['expected_behavior']}\n"

    judge_result = judge_agent_response(
        conn,
        question["question"],
        question.get("should_answer", True),
        question.get("category", "unknown"),
        result["agent_response"],
        additional_context,
    )

    result["context_relevance_score"] = judge_result.get("context_relevance", 0)
    result["groundedness_score"] = judge_result.get("groundedness", 0)
    result["answer_relevance_score"] = judge_result.get("answer_relevance", 0)
    result["overall_score"] = judge_result.get("overall_score", 0)
    result["llm_judge_reasoning"] = judge_result.get("reasoning", "")
    result["passed"] = judge_result.get("passed", False)

    return result


def run_agent_evaluation(
    environment: str,
    agent_name: str,
    categories: list = None,
    git_sha: str = "",
    git_branch: str = "",
) -> dict:
    if categories is None:
        categories = ["answerable", "out_of_scope", "adversarial"]

    conn = get_connection(environment)
    thresholds = load_thresholds()
    env_thresholds = thresholds.get("agent", {}).get(environment, thresholds["agent"]["default"])

    all_results = []
    for category in categories:
        questions = load_question_bank("agent", category)
        print(f"\n{'='*60}")
        print(f"Evaluating {len(questions)} {category.upper()} agent questions")
        print(f"{'='*60}")

        for q in questions:
            print(f"  [{q['id']}] {q['question'][:55]}...", end=" ")
            result = evaluate_agent_question(conn, agent_name, q)
            status = "PASS" if result["passed"] else "FAIL"
            score = result.get("overall_score", 0)
            print(f"{status} (score: {score:.2f}, {result['latency_ms']}ms)")
            all_results.append(result)

    passed = sum(1 for r in all_results if r["passed"])
    total = len(all_results)
    accuracy = (passed / total * 100) if total > 0 else 0
    threshold = env_thresholds.get("accuracy_threshold", 80)
    passed_threshold = accuracy >= threshold

    avg_context = sum(r.get("context_relevance_score", 0) for r in all_results) / max(total, 1)
    avg_ground = sum(r.get("groundedness_score", 0) for r in all_results) / max(total, 1)
    avg_answer = sum(r.get("answer_relevance_score", 0) for r in all_results) / max(total, 1)

    summary = {
        "environment": environment,
        "agent_name": agent_name,
        "git_commit_sha": git_sha,
        "git_branch": git_branch,
        "total_questions": total,
        "passed_questions": passed,
        "failed_questions": total - passed,
        "accuracy_pct": round(accuracy, 2),
        "threshold_pct": threshold,
        "passed_threshold": passed_threshold,
        "avg_context_relevance": round(avg_context, 3),
        "avg_groundedness": round(avg_ground, 3),
        "avg_answer_relevance": round(avg_answer, 3),
        "run_details": {
            "categories": categories,
            "by_category": {},
        },
    }

    for cat in categories:
        cat_results = [r for r in all_results if r["category"] == cat or
                       (cat == "answerable" and r["category"] == "data_query") or
                       (cat == "out_of_scope" and r["category"] in ("philosophical", "destructive", "sensitive_data", "security", "wrong_domain", "action_request")) or
                       (cat == "adversarial" and r["category"] in ("prompt_injection", "social_engineering", "sql_injection", "information_disclosure", "data_exfiltration"))]
        cat_passed = sum(1 for r in cat_results if r["passed"])
        cat_total = len(cat_results)
        summary["run_details"]["by_category"][cat] = {
            "total": cat_total,
            "passed": cat_passed,
            "accuracy_pct": round(cat_passed / cat_total * 100, 2) if cat_total > 0 else 0,
        }

    print(f"\n{'='*60}")
    print(f"AGENT EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"Environment:        {environment}")
    print(f"Agent:              {agent_name}")
    print(f"Total:              {total}")
    print(f"Passed:             {passed}")
    print(f"Failed:             {total - passed}")
    print(f"Accuracy:           {accuracy:.1f}%")
    print(f"Threshold:          {threshold}%")
    print(f"Result:             {'PASSED' if passed_threshold else 'FAILED'}")
    print(f"---")
    print(f"RAG Triad Scores:")
    print(f"  Context Relevance:  {avg_context:.3f}")
    print(f"  Groundedness:       {avg_ground:.3f}")
    print(f"  Answer Relevance:   {avg_answer:.3f}")
    print(f"{'='*60}")

    for cat, stats in summary["run_details"]["by_category"].items():
        print(f"  {cat:15s}:  {stats['passed']}/{stats['total']} ({stats['accuracy_pct']:.1f}%)")

    try:
        log_eval_run(conn, "AGENT_EVAL_RUNS", summary)
    except Exception as e:
        print(f"Warning: Could not log results to Snowflake: {e}")

    return {"summary": summary, "details": all_results, "passed_threshold": passed_threshold}


def main():
    parser = argparse.ArgumentParser(description="Evaluate a Cortex Agent against question banks")
    parser.add_argument("--environment", "-e", default="test", choices=["dev", "test", "prod"])
    parser.add_argument("--agent-name", "-a", required=True, help="Fully qualified agent name")
    parser.add_argument("--categories", "-c", default="answerable,out_of_scope,adversarial")
    parser.add_argument("--git-sha", default="")
    parser.add_argument("--git-branch", default="")
    parser.add_argument("--output", "-o", default="")
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",")]
    result = run_agent_evaluation(
        environment=args.environment,
        agent_name=args.agent_name,
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
