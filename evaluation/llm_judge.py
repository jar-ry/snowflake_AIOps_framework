"""
llm_judge.py
LLM-as-a-Judge evaluation for Semantic View SQL results and ambiguous questions.
Uses Snowflake Cortex COMPLETE for judging.

Note: Agent evaluation uses Snowflake's native EXECUTE_AI_EVALUATION with
built-in GPA metrics (answer_correctness, logical_consistency) and custom
metrics. See audit_agent.py for the native agent evaluation workflow.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_connection, llm_complete, get_llm_model


SEMANTIC_VIEW_JUDGE_PROMPT = """You are an expert SQL evaluator. Compare the generated SQL with the expected SQL
and determine if they produce equivalent results for the given question.

Question: {question}

Expected SQL:
{expected_sql}

Generated SQL:
{generated_sql}

Expected Result (first 10 rows):
{expected_result}

Generated Result (first 10 rows):
{generated_result}

Evaluate on these criteria:
1. CORRECTNESS: Do both queries answer the question? (0-1)
2. EQUIVALENCE: Do the results match or are semantically equivalent? (0-1)
3. EFFICIENCY: Is the generated SQL reasonably efficient? (0-1)

Return a JSON object with:
- "correctness": float (0-1)
- "equivalence": float (0-1)
- "efficiency": float (0-1)
- "overall_score": float (0-1, weighted average: correctness=0.5, equivalence=0.4, efficiency=0.1)
- "reasoning": string explaining your assessment
- "passed": boolean (true if overall_score >= 0.7)

Return ONLY valid JSON, no other text."""


AMBIGUOUS_JUDGE_PROMPT = """You are an expert data analyst evaluator. Assess if the generated SQL
reasonably answers an ambiguous business question.

Question: {question}

Evaluation Criteria:
{evaluation_criteria}

Generated SQL:
{generated_sql}

Generated Result (first 10 rows):
{generated_result}

Evaluate on these criteria:
1. RELEVANCE: Does the query address the question? (0-1)
2. REASONABLENESS: Is the approach reasonable given the ambiguity? (0-1)
3. COMPLETENESS: Does it provide useful insight? (0-1)

Return a JSON object with:
- "relevance": float (0-1)
- "reasonableness": float (0-1)
- "completeness": float (0-1)
- "overall_score": float (0-1, average of above)
- "reasoning": string explaining your assessment
- "passed": boolean (true if overall_score >= 0.6)

Return ONLY valid JSON, no other text."""


def judge_sql_result(
    conn, question: str, expected_sql: str, generated_sql: str,
    expected_result: list, generated_result: list, model: str = None
) -> dict:
    model = model or get_llm_model("judge_model")
    prompt = SEMANTIC_VIEW_JUDGE_PROMPT.format(
        question=question,
        expected_sql=expected_sql,
        generated_sql=generated_sql,
        expected_result=json.dumps(expected_result[:10], default=str),
        generated_result=json.dumps(generated_result[:10], default=str),
    )
    response = llm_complete(conn, model, prompt)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {
            "overall_score": 0,
            "reasoning": f"Failed to parse LLM response: {response[:200]}",
            "passed": False,
        }


def judge_ambiguous_result(
    conn, question: str, evaluation_criteria: str,
    generated_sql: str, generated_result: list, model: str = None
) -> dict:
    model = model or get_llm_model("judge_model")
    prompt = AMBIGUOUS_JUDGE_PROMPT.format(
        question=question,
        evaluation_criteria=evaluation_criteria,
        generated_sql=generated_sql,
        generated_result=json.dumps(generated_result[:10], default=str),
    )
    response = llm_complete(conn, model, prompt)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {
            "overall_score": 0,
            "reasoning": f"Failed to parse LLM response: {response[:200]}",
            "passed": False,
        }


if __name__ == "__main__":
    print("LLM Judge module loaded. Import and use judge_* functions directly.")
