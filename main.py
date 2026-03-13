import json
import os
from pathlib import Path
from typing import List, Dict, TypedDict
import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from dotenv import load_dotenv
import threading

load_dotenv()

# ---------------------------------------------------------------------------
# Global cost tracking (thread-safe)
# ---------------------------------------------------------------------------
_cost_lock = threading.Lock()
_total_cost = 0.0
# Per-item cost tracked by item_id (works across LangGraph's internal threads)
_item_cost_lock = threading.Lock()
_item_costs: Dict[str, float] = {}


def _add_cost(response, item_id: str = "") -> float:
    """Thread-safely accumulate cost from an OpenRouter LLM response.

    Args:
        response: LangChain AIMessage response
        item_id: Sample ID to attribute cost to

    Returns:
        Cost of this call in USD (0.0 if unavailable)
    """
    global _total_cost
    try:
        meta = getattr(response, "response_metadata", {}) or {}
        cost = _extract_cost(meta)
        if cost > 0:
            with _cost_lock:
                _total_cost += cost
            if item_id:
                with _item_cost_lock:
                    _item_costs[item_id] = _item_costs.get(item_id, 0.0) + cost
        return cost
    except Exception:
        return 0.0


def _extract_cost(meta: dict) -> float:
    """Extract cost from LangChain response_metadata.

    OpenRouter puts `cost` inside token_usage (response_metadata["token_usage"]["cost"]).
    """
    token_usage = meta.get("token_usage") or {}
    if isinstance(token_usage, dict):
        val = token_usage.get("cost")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    for key in ("cost", "openrouter_cost"):
        val = meta.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    headers = meta.get("headers") or {}
    if isinstance(headers, dict):
        for key in ("x-openrouter-cost", "X-Openrouter-Cost"):
            val = headers.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass

    return 0.0


# Define the state structure for the workflow
class WorkflowState(TypedDict):
    """State passed between agents in the workflow"""

    content: str  # Input text
    item_id: str  # Sample ID
    source: str  # Source name
    n: int  # Number of questions per level
    analyzer_output: str  # Output from analyzer agent
    level1_questions: List[Dict]  # Questions from level 1 generator
    level2_questions: List[Dict]  # Questions from level 2 generator
    level3_questions: List[Dict]  # Questions from level 3 generator
    # Validation results: list of {id, verdict, feedback} per level
    level1_validation: List[Dict]
    level2_validation: List[Dict]
    level3_validation: List[Dict]
    # Post-fix questions per level (replaces originals if fixes were needed)
    level1_fixed: List[Dict]
    level2_fixed: List[Dict]
    level3_fixed: List[Dict]
    final_questions: List[Dict]  # Combined final questions
    error: str  # Error message if any
    verbose: bool  # Whether to print agent outputs


def load_prompt(prompt_path: str) -> str:
    """Load prompt from file

    Args:
        prompt_path: Path to the prompt file

    Returns:
        Prompt content as string
    """
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def load_data(data_path: str, n: int = -1, sources: List[str] = None) -> List[dict]:
    """Load data from JSON file

    Args:
        data_path: Path to the data.json file
        n: Number of items to load (-1 for all)
        sources: List of sources to filter by (None for all sources)

    Returns:
        List of data items
    """
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Filter by sources if specified
    if sources:
        sources_lower = [s.lower() for s in sources]
        data = [
            item for item in data if item.get("source", "").lower() in sources_lower
        ]

    if n > 0:
        data = data[:n]

    return data


def analyzer_agent(
    state: WorkflowState, llm: ChatOpenAI, analyzer_prompt: str
) -> WorkflowState:
    """Analyzer agent - extracts useful information from text

    Args:
        state: Current workflow state
        llm: Language model
        analyzer_prompt: Prompt template for analyzer

    Returns:
        Updated state with analyzer_output
    """
    try:
        # Create prompt with content
        full_prompt = analyzer_prompt.replace("{content}", state["content"])

        # Invoke LLM
        response = llm.invoke(full_prompt)
        _add_cost(response, item_id=state["item_id"])
        analyzer_output = response.content

        if state.get("verbose"):
            print(f"\n{'='*80}")
            print(f"Analyzer Output for {state['item_id']}:")
            print(f"{'='*80}")
            print(analyzer_output)
            print(f"{'='*80}\n")

        # Update state
        state["analyzer_output"] = analyzer_output

    except Exception as e:
        state["error"] = f"Analyzer failed: {str(e)}"
        print(f"Error in analyzer: {str(e)}")

    return state


def parse_generator_output(
    output: str, n: int, expected_level: int = None
) -> List[Dict]:
    """Parse generator output into structured questions

    Expected format:
    ID: 1
    Question: Question text
    A: Option A
    B: Option B
    C: Option C
    D: Option D
    Answer: A

    Args:
        output: Raw generator output
        n: Number of questions expected
        expected_level: Expected level (assigned to all questions)

    Returns:
        List of question dictionaries
    """
    questions = []

    # Split by ID: to separate questions
    blocks = re.split(r"\n(?=ID:\s*\d+)", output.strip())

    for block in blocks:
        if not block.strip():
            continue

        try:
            # Find positions of key prefixes
            question_pos = block.find("Question:")
            a_pos = block.find("\nA:")
            b_pos = block.find("\nB:")
            c_pos = block.find("\nC:")
            d_pos = block.find("\nD:")
            answer_pos = block.find("\nAnswer:")

            # Extract Question text (from "Question:" to "\nA:")
            if question_pos == -1 or a_pos == -1:
                continue
            question_text = block[question_pos + len("Question:") : a_pos].strip()

            # Extract options by finding text between prefixes
            if (
                a_pos == -1
                or b_pos == -1
                or c_pos == -1
                or d_pos == -1
                or answer_pos == -1
            ):
                continue

            option_a = block[a_pos + len("\nA:") : b_pos].strip()
            option_b = block[b_pos + len("\nB:") : c_pos].strip()
            option_c = block[c_pos + len("\nC:") : d_pos].strip()
            option_d = block[d_pos + len("\nD:") : answer_pos].strip()

            options = [option_a, option_b, option_c, option_d]

            # Extract Answer letter
            answer_match = re.search(r"Answer:\s*([A-D])", block, re.IGNORECASE)
            answer_letter = (
                answer_match.group(1).strip().upper() if answer_match else None
            )

            # Only add if we have all 4 options and answer
            if len(options) == 4 and answer_letter:
                # Map answer letter to index
                correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
                correct_idx = correct_map.get(answer_letter, -1)

                # Parse ID from the block
                id_match = re.match(r"ID:\s*(\d+)", block.strip())
                q_id = int(id_match.group(1)) if id_match else None

                if correct_idx != -1:
                    questions.append(
                        {
                            "id": q_id,
                            "question": question_text,
                            "options": options,
                            "correct_idx": correct_idx,
                            "level": expected_level,  # Use the expected level from the generator
                        }
                    )

        except Exception as e:
            print(f"Warning: Failed to parse question block: {str(e)}")
            continue

    return questions


def format_questions_for_validation(questions: List[Dict]) -> str:
    """Format questions list into text block for validator prompt

    Args:
        questions: List of question dicts with question, options, correct_idx, level

    Returns:
        Formatted string
    """
    lines = []
    correct_map = {0: "A", 1: "B", 2: "C", 3: "D"}
    for idx, q in enumerate(questions, 1):
        lines.append(f"ID: {idx}")
        lines.append(f"Question: {q['question']}")
        for i, label in enumerate(["A", "B", "C", "D"]):
            lines.append(f"{label}: {q['options'][i]}")
        lines.append(f"Answer: {correct_map.get(q['correct_idx'], 'A')}")
        lines.append("")
    return "\n".join(lines)


def format_failed_questions_for_fixer(
    questions: List[Dict], validation: List[Dict]
) -> str:
    """Format failed questions with their feedback for the fixer prompt

    Args:
        questions: List of question dicts
        validation: List of validation result dicts with id, verdict, feedback

    Returns:
        Formatted string with failed questions and feedback, or empty string if none failed
    """
    lines = []
    correct_map = {0: "A", 1: "B", 2: "C", 3: "D"}

    # Build a map from validation id to feedback
    feedback_map = {}
    for v in validation:
        if v.get("verdict") == "FAIL":
            feedback_map[v["id"]] = v

    for idx, q in enumerate(questions, 1):
        v = feedback_map.get(idx)
        if v:
            lines.append(f"ID: {idx}")
            lines.append(f"Question: {q['question']}")
            for i, label in enumerate(["A", "B", "C", "D"]):
                lines.append(f"{label}: {q['options'][i]}")
            lines.append(f"Answer: {correct_map.get(q['correct_idx'], 'A')}")
            lines.append(f"Feedback: {v.get('feedback', 'No specific feedback')}")
            lines.append(f"Solvability: {v.get('solvability', 'FAIL')}")
            lines.append(f"Distractor Quality: {v.get('distractor_quality', 'FAIL')}")
            lines.append(f"Alignment: {v.get('alignment', 'FAIL')}")
            lines.append("")

    return "\n".join(lines)


def parse_validator_output(output: str) -> List[Dict]:
    """Parse validator output into structured validation results

    Expected format per question:
    ID: 1
    Solvability: PASS|FAIL
    Distractor Quality: PASS|FAIL
    Alignment: PASS|FAIL
    Verdict: PASS|FAIL
    Feedback: ...

    Returns:
        List of {id, solvability, distractor_quality, alignment, verdict, feedback}
    """
    results = []
    blocks = re.split(r"\n(?=ID:\s*\d+)", output.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        try:
            # Extract ID
            id_match = re.match(r"ID:\s*(\d+)", block)
            if not id_match:
                continue
            q_id = int(id_match.group(1))

            # Extract verdict
            verdict_match = re.search(r"Verdict:\s*(PASS|FAIL)", block, re.IGNORECASE)
            verdict = verdict_match.group(1).upper() if verdict_match else "FAIL"

            # Extract feedback
            feedback_match = re.search(r"Feedback:\s*(.+)", block)
            feedback = feedback_match.group(1).strip() if feedback_match else "None"

            # Extract individual checks
            solv_match = re.search(r"Solvability:\s*(PASS|FAIL)", block, re.IGNORECASE)
            dist_match = re.search(
                r"Distractor Quality:\s*(PASS|FAIL)", block, re.IGNORECASE
            )
            align_match = re.search(r"Alignment:\s*(PASS|FAIL)", block, re.IGNORECASE)

            results.append(
                {
                    "id": q_id,
                    "solvability": (
                        solv_match.group(1).upper() if solv_match else "FAIL"
                    ),
                    "distractor_quality": (
                        dist_match.group(1).upper() if dist_match else "FAIL"
                    ),
                    "alignment": (
                        align_match.group(1).upper() if align_match else "FAIL"
                    ),
                    "verdict": verdict,
                    "feedback": feedback,
                }
            )
        except Exception as e:
            print(f"Warning: Failed to parse validator block: {str(e)}")
            continue

    return results


def generator_level1_agent(
    state: WorkflowState, llm: ChatOpenAI, generator_prompt: str
) -> Dict:
    """Generator agent for Level 1 questions

    Args:
        state: Current workflow state
        llm: Language model
        generator_prompt: Prompt template for Level 1 generator

    Returns:
        Dict with level1_questions key only
    """
    if state.get("error"):
        return {}

    try:
        n = state["n"]

        # Create prompt
        full_prompt = (
            generator_prompt.replace("{content}", state["content"])
            .replace("{analyzer_output}", state["analyzer_output"])
            .replace("{n}", str(n))
        )

        # Invoke LLM
        response = llm.invoke(full_prompt)
        _add_cost(response, item_id=state["item_id"])
        generator_output = response.content

        if state.get("verbose"):
            print(f"\n{'='*80}")
            print(f"Level 1 Generator Output for {state['item_id']}:")
            print(f"{'='*80}")
            print(generator_output)
            print(f"{'='*80}\n")

        # Parse output
        questions = parse_generator_output(generator_output, n, expected_level=1)

        # Return only the key this agent updates
        return {"level1_questions": questions}

    except Exception as e:
        error_msg = f"Level 1 Generator failed: {str(e)}"
        print(f"Error in Level 1 generator: {str(e)}")
        return {"error": error_msg}


def generator_level2_agent(
    state: WorkflowState, llm: ChatOpenAI, generator_prompt: str
) -> Dict:
    """Generator agent for Level 2 questions

    Args:
        state: Current workflow state
        llm: Language model
        generator_prompt: Prompt template for Level 2 generator

    Returns:
        Dict with level2_questions key only
    """
    if state.get("error"):
        return {}

    try:
        n = state["n"]

        # Create prompt
        full_prompt = (
            generator_prompt.replace("{content}", state["content"])
            .replace("{analyzer_output}", state["analyzer_output"])
            .replace("{n}", str(n))
        )

        # Invoke LLM
        response = llm.invoke(full_prompt)
        _add_cost(response, item_id=state["item_id"])
        generator_output = response.content

        if state.get("verbose"):
            print(f"\n{'='*80}")
            print(f"Level 2 Generator Output for {state['item_id']}:")
            print(f"{'='*80}")
            print(generator_output)
            print(f"{'='*80}\n")

        # Parse output
        questions = parse_generator_output(generator_output, n, expected_level=2)

        # Return only the key this agent updates
        return {"level2_questions": questions}

    except Exception as e:
        error_msg = f"Level 2 Generator failed: {str(e)}"
        print(f"Error in Level 2 generator: {str(e)}")
        return {"error": error_msg}


def generator_level3_agent(
    state: WorkflowState, llm: ChatOpenAI, generator_prompt: str
) -> Dict:
    """Generator agent for Level 3 questions

    Args:
        state: Current workflow state
        llm: Language model
        generator_prompt: Prompt template for Level 3 generator

    Returns:
        Dict with level3_questions key only
    """
    if state.get("error"):
        return {}

    try:
        n = state["n"]

        # Create prompt
        full_prompt = (
            generator_prompt.replace("{content}", state["content"])
            .replace("{analyzer_output}", state["analyzer_output"])
            .replace("{n}", str(n))
        )

        # Invoke LLM
        response = llm.invoke(full_prompt)
        _add_cost(response, item_id=state["item_id"])
        generator_output = response.content

        if state.get("verbose"):
            print(f"\n{'='*80}")
            print(f"Level 3 Generator Output for {state['item_id']}:")
            print(f"{'='*80}")
            print(generator_output)
            print(f"{'='*80}\n")

        # Parse output
        questions = parse_generator_output(generator_output, n, expected_level=3)

        # Return only the key this agent updates
        return {"level3_questions": questions}

    except Exception as e:
        error_msg = f"Level 3 Generator failed: {str(e)}"
        print(f"Error in Level 3 generator: {str(e)}")
        return {"error": error_msg}


def _run_validator(
    questions: List[Dict],
    llm: ChatOpenAI,
    validator_prompt: str,
    content: str,
    item_id: str,
    level: int,
    attempt: int,
    verbose: bool = False,
) -> List[Dict]:
    """Run the validator LLM on a list of questions and return validation results."""
    questions_text = format_questions_for_validation(questions)
    full_prompt = validator_prompt.replace("{content}", content).replace(
        "{questions}", questions_text
    )
    response = llm.invoke(full_prompt)
    _add_cost(response, item_id=item_id)
    validator_output = response.content

    if verbose:
        print(f"\n{'='*80}")
        print(f"Validator Level {level} (attempt {attempt}) for {item_id}:")
        print(f"{'='*80}")
        print(validator_output)
        print(f"{'='*80}\n")

    return parse_validator_output(validator_output)


def _run_fixer(
    questions: List[Dict],
    validation: List[Dict],
    llm: ChatOpenAI,
    fixer_prompt: str,
    content: str,
    analyzer_output: str,
    item_id: str,
    level: int,
    attempt: int,
    per_question_history: Dict[int, List[str]],
    verbose: bool = False,
) -> List[Dict]:
    """Run the fixer LLM on failed questions and return the merged question list."""
    failed_text = format_failed_questions_for_fixer(questions, validation)
    if not failed_text.strip():
        return questions

    # Build history text showing only past feedback for questions that are
    # CURRENTLY still failing — avoids noise from already-resolved questions
    currently_failed_ids = {v["id"] for v in validation if v.get("verdict") == "FAIL"}
    history_lines = []
    for q_id in sorted(currently_failed_ids):
        past = per_question_history.get(q_id, [])
        if past:
            rounds = "\n".join(f"  Attempt {i + 1}: {fb}" for i, fb in enumerate(past))
            history_lines.append(f"Q{q_id} previous feedback:\n{rounds}")
    history_text = (
        "\n\n".join(history_lines) if history_lines else "No previous fix attempts."
    )

    full_prompt = (
        fixer_prompt.replace("{content}", content)
        .replace("{analyzer_output}", analyzer_output)
        .replace("{fix_history}", history_text)
        .replace("{failed_questions}", failed_text)
    )
    response = llm.invoke(full_prompt)
    _add_cost(response, item_id=item_id)
    fixer_output = response.content

    if verbose:
        print(f"\n{'='*80}")
        print(f"Fixer Level {level} (attempt {attempt}) for {item_id}:")
        print(f"{'='*80}")
        print(fixer_output)
        print(f"{'='*80}\n")

    fixed_questions = parse_generator_output(
        fixer_output, len(questions), expected_level=level
    )
    # Use the ID parsed from the fixer output ("ID: N") rather than enumerate position,
    # so ordering/missing questions in LLM response don't cause mismatches.
    fixed_map = {fq["id"]: fq for fq in fixed_questions if fq.get("id") is not None}

    failed_ids = {v["id"] for v in validation if v.get("verdict") == "FAIL"}
    merged = []
    for idx, q in enumerate(questions):
        q_id = idx + 1
        if q_id in failed_ids and q_id in fixed_map:
            merged.append(fixed_map[q_id])
            if verbose:
                print(f"  Level {level} Q{q_id}: FIXED (attempt {attempt})")
        else:
            merged.append(q)
            if verbose:
                print(f"  Level {level} Q{q_id}: kept (passed)")
    return merged


def validate_and_fix_agent(
    state: WorkflowState,
    llm: ChatOpenAI,
    validator_prompt: str,
    fixer_prompt: str,
    level: int,
    max_fix_retries: int,
) -> Dict:
    """Validate questions for a level then iteratively fix failures.

    Loop:
      1. Validate all current questions.
      2. If no failures → done.
      3. Fix only the failed questions (with per-question feedback).
      4. Re-validate the fixed questions in-place.
      5. Repeat up to max_fix_retries times.
      6. After exhausting retries, log a WARNING for any remaining failures.

    Args:
        state: Current workflow state
        llm: Language model
        validator_prompt: Prompt template for this level's validator
        fixer_prompt: Prompt template for this level's fixer
        level: Question level (1, 2, or 3)
        max_fix_retries: Maximum number of fix-then-revalidate attempts

    Returns:
        Dict with level{N}_validation and level{N}_fixed keys
    """
    level_key = f"level{level}_questions"
    validation_key = f"level{level}_validation"
    fixed_key = f"level{level}_fixed"

    questions = state.get(level_key, [])
    if not questions or state.get("error"):
        return {validation_key: [], fixed_key: questions}

    content = state["content"]
    analyzer_output = state.get("analyzer_output", "")
    item_id = state["item_id"]
    verbose = state.get("verbose", False)

    current_questions = questions
    validation: List[Dict] = []
    # per_question_history[q_id] = list of feedback strings from each failed round
    per_question_history: Dict[int, List[str]] = {}

    try:
        # ── Initial validation ──────────────────────────────────────────────
        validation = _run_validator(
            current_questions,
            llm,
            validator_prompt,
            content,
            item_id,
            level,
            attempt=0,
            verbose=verbose,
        )
        passed = sum(1 for v in validation if v["verdict"] == "PASS")
        failed_count = len(validation) - passed
        if verbose:
            print(
                f"Level {level} validation (attempt 0): {passed} passed, {failed_count} failed"
            )

        # ── Retry loop ──────────────────────────────────────────────────────
        for attempt in range(1, max_fix_retries + 1):
            if not any(v.get("verdict") == "FAIL" for v in validation):
                if verbose:
                    print(
                        f"Level {level}: All questions passed — stopping after attempt {attempt - 1}"
                    )
                break

            # Accumulate per-question feedback before calling fixer
            for v in validation:
                if v.get("verdict") == "FAIL":
                    q_id = v["id"]
                    per_question_history.setdefault(q_id, []).append(
                        v.get("feedback", "no feedback")
                    )

            if verbose:
                print(
                    f"Level {level}: Running fix attempt {attempt}/{max_fix_retries}..."
                )
            current_questions = _run_fixer(
                current_questions,
                validation,
                llm,
                fixer_prompt,
                content,
                analyzer_output,
                item_id,
                level,
                attempt,
                per_question_history,
                verbose=verbose,
            )

            # Re-validate to measure progress
            validation = _run_validator(
                current_questions,
                llm,
                validator_prompt,
                content,
                item_id,
                level,
                attempt,
                verbose=verbose,
            )
            passed = sum(1 for v in validation if v["verdict"] == "PASS")
            failed_count = len(validation) - passed
            if verbose:
                print(
                    f"Level {level} re-validation (attempt {attempt}): {passed} passed, {failed_count} failed"
                )

            # Warn if still failing after the last attempt
            if attempt == max_fix_retries:
                still_failing = [v for v in validation if v.get("verdict") == "FAIL"]
                if still_failing:
                    failed_ids = [str(v["id"]) for v in still_failing]
                    feedbacks = "; ".join(
                        f"Q{v['id']}: {v.get('feedback', 'no feedback')}"
                        for v in still_failing
                    )
                    print(
                        f"WARNING: Level {level} — {len(still_failing)} question(s) still failing "
                        f"after {max_fix_retries} fix attempt(s) for item '{item_id}'. "
                        f"Failing IDs: [{', '.join(failed_ids)}]. "
                        f"Feedback: {feedbacks}"
                    )

        return {validation_key: validation, fixed_key: current_questions}

    except Exception as e:
        print(f"Error in validate_and_fix level {level}: {str(e)}")
        # On error, return original questions without blocking the pipeline
        return {validation_key: validation, fixed_key: questions}


def merge_questions_agent(state: WorkflowState) -> WorkflowState:
    """Merge questions from all 3 levels into final_questions

    Uses fixed questions if available, otherwise falls back to originals.

    Args:
        state: Current workflow state

    Returns:
        Updated state with final_questions
    """
    if state.get("error"):
        return state

    try:
        # Combine all questions — prefer fixed versions
        all_questions = []

        for level in [1, 2, 3]:
            fixed_key = f"level{level}_fixed"
            orig_key = f"level{level}_questions"
            questions = state.get(fixed_key, []) or state.get(orig_key, [])

            for q in questions:
                all_questions.append(
                    {
                        "content": q["question"],
                        "options": q["options"],
                        "correct": q["correct_idx"],
                        "level": level,
                        "type": "General",
                    }
                )

        # Sort by level, then by original order
        all_questions.sort(key=lambda x: x["level"])

        if state.get("verbose"):
            print(f"\n{'='*80}")
            print(f"Merged {len(all_questions)} questions for {state['item_id']}:")
            print(f"{'='*80}")
            for idx, q in enumerate(all_questions, 1):
                print(f"Q{idx} (Level {q['level']}): {q['content'][:80]}...")
            print(f"{'='*80}\n")

        state["final_questions"] = all_questions

    except Exception as e:
        state["error"] = f"Merge failed: {str(e)}"
        print(f"Error in merge: {str(e)}")

    return state


def create_workflow(
    llm: ChatOpenAI,
    analyzer_prompt: str,
    generator_level1_prompt: str,
    generator_level2_prompt: str,
    generator_level3_prompt: str,
    validator_level1_prompt: str,
    validator_level2_prompt: str,
    validator_level3_prompt: str,
    fixer_level1_prompt: str,
    fixer_level2_prompt: str,
    fixer_level3_prompt: str,
    max_fix_retries: int = 1,
) -> StateGraph:
    """Create the multi-agent workflow using LangGraph

    Flow:
        analyzer
            → [generator_level1, generator_level2, generator_level3]  (parallel)
                → [validate_and_fix_level1, validate_and_fix_level2, validate_and_fix_level3]  (parallel)
                    (each runs: validate → fix failed → re-validate, up to max_fix_retries times)
                        → merge → END

    Args:
        llm: Language model
        analyzer_prompt: Prompt for analyzer agent
        generator_level1_prompt: Prompt for Level 1 generator
        generator_level2_prompt: Prompt for Level 2 generator
        generator_level3_prompt: Prompt for Level 3 generator
        validator_level1_prompt: Prompt for Level 1 validator
        validator_level2_prompt: Prompt for Level 2 validator
        validator_level3_prompt: Prompt for Level 3 validator
        fixer_level1_prompt: Prompt for Level 1 fixer
        fixer_level2_prompt: Prompt for Level 2 fixer
        fixer_level3_prompt: Prompt for Level 3 fixer
        max_fix_retries: Maximum validate→fix loop iterations per level (default: 1)

    Returns:
        Compiled workflow graph
    """
    # Create workflow graph
    workflow = StateGraph(WorkflowState)

    # ── Nodes ──────────────────────────────────────────────────────────────
    workflow.add_node(
        "analyzer", lambda state: analyzer_agent(state, llm, analyzer_prompt)
    )

    # Generators (parallel after analyzer)
    workflow.add_node(
        "generator_level1",
        lambda state: generator_level1_agent(state, llm, generator_level1_prompt),
    )
    workflow.add_node(
        "generator_level2",
        lambda state: generator_level2_agent(state, llm, generator_level2_prompt),
    )
    workflow.add_node(
        "generator_level3",
        lambda state: generator_level3_agent(state, llm, generator_level3_prompt),
    )

    # Validate-and-fix nodes (parallel, one per level)
    # Each node runs the full validate → fix → re-validate loop internally
    workflow.add_node(
        "validate_and_fix_level1",
        lambda state: validate_and_fix_agent(
            state,
            llm,
            validator_level1_prompt,
            fixer_level1_prompt,
            level=1,
            max_fix_retries=max_fix_retries,
        ),
    )
    workflow.add_node(
        "validate_and_fix_level2",
        lambda state: validate_and_fix_agent(
            state,
            llm,
            validator_level2_prompt,
            fixer_level2_prompt,
            level=2,
            max_fix_retries=max_fix_retries,
        ),
    )
    workflow.add_node(
        "validate_and_fix_level3",
        lambda state: validate_and_fix_agent(
            state,
            llm,
            validator_level3_prompt,
            fixer_level3_prompt,
            level=3,
            max_fix_retries=max_fix_retries,
        ),
    )

    # Merge
    workflow.add_node("merge", merge_questions_agent)

    # ── Edges ──────────────────────────────────────────────────────────────
    # analyzer → generators (fan-out)
    workflow.set_entry_point("analyzer")
    workflow.add_edge("analyzer", "generator_level1")
    workflow.add_edge("analyzer", "generator_level2")
    workflow.add_edge("analyzer", "generator_level3")

    # generators → validate-and-fix (each level feeds its own node)
    workflow.add_edge("generator_level1", "validate_and_fix_level1")
    workflow.add_edge("generator_level2", "validate_and_fix_level2")
    workflow.add_edge("generator_level3", "validate_and_fix_level3")

    # validate-and-fix → merge (fan-in)
    workflow.add_edge("validate_and_fix_level1", "merge")
    workflow.add_edge("validate_and_fix_level2", "merge")
    workflow.add_edge("validate_and_fix_level3", "merge")

    workflow.add_edge("merge", END)

    # Compile the graph
    return workflow.compile()


def process_item(
    item: dict, n: int, workflow: StateGraph, verbose: bool = False
) -> Dict:
    """Process a single item through the workflow

    Args:
        item: Data item with 'id', 'content', 'source'
        n: Number of questions per level
        workflow: Compiled workflow graph
        verbose: Whether to print agent outputs

    Returns:
        Result dictionary
    """
    # Initialize state
    initial_state = WorkflowState(
        content=item["content"],
        item_id=item["id"],
        source=item.get("source", "unknown"),
        n=n,
        analyzer_output="",
        level1_questions=[],
        level2_questions=[],
        level3_questions=[],
        level1_validation=[],
        level2_validation=[],
        level3_validation=[],
        level1_fixed=[],
        level2_fixed=[],
        level3_fixed=[],
        final_questions=[],
        error="",
        verbose=verbose,
    )

    try:
        # Reset per-item cost accumulator
        with _item_cost_lock:
            _item_costs[item["id"]] = 0.0

        # Run workflow
        final_state = workflow.invoke(initial_state)
        item_cost = _item_costs.get(item["id"], 0.0)
        with _item_cost_lock:
            _item_costs.pop(item["id"], None)

        # Check for errors
        if final_state.get("error"):
            return {
                "id": item["id"],
                "source": item.get("source", "unknown"),
                "cost": item_cost,
                "error": final_state["error"],
            }

        result = {
            "id": item["id"],
            "source": item.get("source", "unknown"),
            "cost": item_cost,
            "generated_questions": final_state["final_questions"],
        }

        if verbose:
            print(f"\n{'='*80}")
            print(f"✓ Completed item {item['id']}:")
            print(f"{'='*80}")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"{'='*80}\n")

        return result

    except Exception as e:
        item_cost = _item_costs.get(item["id"], 0.0)
        with _item_cost_lock:
            _item_costs.pop(item["id"], None)
        error_result = {
            "id": item["id"],
            "source": item.get("source", "unknown"),
            "cost": item_cost,
            "error": str(e),
        }

        print(f"✗ Error for item {item['id']}: {str(e)}")

        return error_result


def main():
    parser = argparse.ArgumentParser(
        description="Multi-agent workflow for generating questions from text"
    )
    parser.add_argument(
        "--num-items",
        type=int,
        default=-1,
        help="Number of items to process (-1 for all)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="anthropic/claude-3.5-sonnet",
        help="Model ID to use (e.g., 'anthropic/claude-3.5-sonnet', 'openai/gpt-4')",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="Number of questions per level (total = 3*n questions per sample, default: 1)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="datasets/unified/data.json",
        help="Path to the data.json file",
    )
    parser.add_argument(
        "--analyzer-prompt-path",
        type=str,
        default="prompts/analyzer.md",
        help="Path to the analyzer prompt file",
    )
    parser.add_argument(
        "--generator-level1-prompt-path",
        type=str,
        default="prompts/level1/generator.md",
        help="Path to the Level 1 generator prompt file",
    )
    parser.add_argument(
        "--generator-level2-prompt-path",
        type=str,
        default="prompts/level2/generator.md",
        help="Path to the Level 2 generator prompt file",
    )
    parser.add_argument(
        "--generator-level3-prompt-path",
        type=str,
        default="prompts/level3/generator.md",
        help="Path to the Level 3 generator prompt file",
    )
    parser.add_argument(
        "--validator-level1-prompt-path",
        type=str,
        default="prompts/level1/validator.md",
        help="Path to the Level 1 validator prompt file",
    )
    parser.add_argument(
        "--validator-level2-prompt-path",
        type=str,
        default="prompts/level2/validator.md",
        help="Path to the Level 2 validator prompt file",
    )
    parser.add_argument(
        "--validator-level3-prompt-path",
        type=str,
        default="prompts/level3/validator.md",
        help="Path to the Level 3 validator prompt file",
    )
    parser.add_argument(
        "--fixer-level1-prompt-path",
        type=str,
        default="prompts/level1/fixer.md",
        help="Path to the Level 1 fixer prompt file",
    )
    parser.add_argument(
        "--fixer-level2-prompt-path",
        type=str,
        default="prompts/level2/fixer.md",
        help="Path to the Level 2 fixer prompt file",
    )
    parser.add_argument(
        "--fixer-level3-prompt-path",
        type=str,
        default="prompts/level3/fixer.md",
        help="Path to the Level 3 fixer prompt file",
    )
    parser.add_argument(
        "--max-fix-retries",
        type=int,
        default=5,
        help="Maximum number of validate→fix iterations per level (default: 1)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="Filter by source(s) (e.g., 'race', 'dream'). Default: all sources",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for processing items (default: 1, sequential processing)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs/workflow",
        help="Directory to save output files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print full agent outputs (LLM responses, validation details). Default: off (progress bar only)",
    )

    args = parser.parse_args()

    # Get API key from environment variable
    api_key = os.environ.get("OPENROUTER_API_KEY")
    # api_key = os.environ.get("NOVITAAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenRouter API key not found. Please set OPENROUTER_API_KEY environment variable"
        )

    # Validate sources parameter
    if not args.sources:
        raise ValueError(
            "Error: --sources parameter is required. Please specify which dataset(s) to process.\n"
            "Example: --sources reclor, --sources race, or --sources race dream"
        )

    # Load prompts
    print(f"Loading analyzer prompt from {args.analyzer_prompt_path}...")
    analyzer_prompt = load_prompt(args.analyzer_prompt_path)
    print(f"Analyzer prompt loaded successfully")

    print(
        f"Loading Level 1 generator prompt from {args.generator_level1_prompt_path}..."
    )
    generator_level1_prompt = load_prompt(args.generator_level1_prompt_path)
    print(f"Level 1 generator prompt loaded successfully")

    print(
        f"Loading Level 2 generator prompt from {args.generator_level2_prompt_path}..."
    )
    generator_level2_prompt = load_prompt(args.generator_level2_prompt_path)
    print(f"Level 2 generator prompt loaded successfully")

    print(
        f"Loading Level 3 generator prompt from {args.generator_level3_prompt_path}..."
    )
    generator_level3_prompt = load_prompt(args.generator_level3_prompt_path)
    print(f"Level 3 generator prompt loaded successfully")

    # Load validator prompts
    print(f"Loading validator prompts...")
    validator_level1_prompt = load_prompt(args.validator_level1_prompt_path)
    validator_level2_prompt = load_prompt(args.validator_level2_prompt_path)
    validator_level3_prompt = load_prompt(args.validator_level3_prompt_path)
    print(f"Validator prompts loaded successfully")

    # Load fixer prompts
    print(f"Loading fixer prompts...")
    fixer_level1_prompt = load_prompt(args.fixer_level1_prompt_path)
    fixer_level2_prompt = load_prompt(args.fixer_level2_prompt_path)
    fixer_level3_prompt = load_prompt(args.fixer_level3_prompt_path)
    print(f"Fixer prompts loaded successfully")

    # Initialize LLM
    llm = ChatOpenAI(
        model=args.model,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        # openai_api_base="https://api.novita.ai/openai",
        temperature=0.0,
        extra_body={
            "reasoning": {"effort": "none"},
            "provider": {
                "sort": "price",
            },
        },
    )

    # Create workflow
    print("Creating multi-agent workflow...")
    workflow = create_workflow(
        llm,
        analyzer_prompt,
        generator_level1_prompt,
        generator_level2_prompt,
        generator_level3_prompt,
        validator_level1_prompt,
        validator_level2_prompt,
        validator_level3_prompt,
        fixer_level1_prompt,
        fixer_level2_prompt,
        fixer_level3_prompt,
        max_fix_retries=args.max_fix_retries,
    )
    print("Workflow created successfully\n")

    # Get model_id from model name with suffix
    model_id = args.model.replace("/", "_") + "-new"

    print(f"\nUsing model: {args.model}")
    print(f"Model ID: {model_id}")
    print(f"Generating {3 * args.n} questions per sample ({args.n} per level)")
    print(f"Processing sources: {', '.join(args.sources)}")

    # Process each source separately
    for source in args.sources:
        source_lower = source.lower()
        print(f"\n{'='*100}")
        print(f"Processing source: {source.upper()}")
        print(f"{'='*100}")

        # Load data for this source only
        print(f"Loading data from {args.data_path}...")
        data = load_data(args.data_path, args.num_items, [source])
        print(f"Loaded {len(data)} items for {source}")

        if not data:
            print(f"Warning: No data found for source {source}, skipping...")
            continue

        # Create output directory similar to question.py
        output_dir = Path("outputs") / source_lower / model_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "predictions.json"

        print(f"Output will be saved to: {output_path}")
        print(f"Using {args.workers} worker(s) for parallel processing")

        # Process items with ThreadPoolExecutor
        # Track cost for this source
        source_cost_start = _total_cost
        results = []

        if args.workers == 1:
            # Sequential processing
            with tqdm(
                total=len(data), desc=f"Processing {source}", disable=args.verbose
            ) as pbar:
                for i, item in enumerate(data, 1):
                    if args.verbose:
                        print(f"\n{'='*100}")
                        print(f"Processing item {i}/{len(data)}: {item['id']}")
                        print(f"{'='*100}")

                    result = process_item(item, args.n, workflow, verbose=args.verbose)
                    results.append(result)

                    # Print summary for this item
                    if "error" in result:
                        tqdm.write(f"✗ {item['id']}: Error - {result['error']}")
                    else:
                        tqdm.write(
                            f"✓ {item['id']}: cost=${result.get('cost', 0.0):.6f}"
                        )
                    pbar.update(1)
        else:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                # Submit all jobs
                future_to_item = {
                    executor.submit(
                        process_item, item, args.n, workflow, args.verbose
                    ): item
                    for item in data
                }

                # Process completed jobs with progress bar
                with tqdm(total=len(data), desc=f"Processing {source}") as pbar:
                    for future in as_completed(future_to_item):
                        item = future_to_item[future]
                        try:
                            result = future.result()
                            results.append(result)

                            # Print summary for this item
                            if "error" in result:
                                tqdm.write(f"✗ {item['id']}: Error - {result['error']}")
                            else:
                                tqdm.write(
                                    f"✓ {item['id']}: cost=${result.get('cost', 0.0):.6f}"
                                )
                        except Exception as e:
                            tqdm.write(f"✗ {item['id']}: Exception - {str(e)}")
                            results.append(
                                {
                                    "id": item["id"],
                                    "source": item.get("source", "unknown"),
                                    "cost": 0.0,
                                    "content": item["content"],
                                    "error": str(e),
                                }
                            )
                        pbar.update(1)

        # Sort results by ID to maintain order (like question.py)
        results.sort(key=lambda x: x["id"])

        # Save results
        print(f"\nSaving results to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(
            f"✓ Done! Processed {len(data)} items for {source}, saved to {output_path}"
        )

        # Print summary
        successful = sum(1 for r in results if "error" not in r)
        failed = len(results) - successful
        total_questions = sum(
            len(r.get("generated_questions", [])) for r in results if "error" not in r
        )

        source_cost = _total_cost - source_cost_start

        print(f"\nSummary for {source}:")
        print(f"  Successful samples: {successful}")
        print(f"  Failed samples: {failed}")
        print(f"  Total questions generated: {total_questions}")
        print(f"  Questions per sample: {3 * args.n} ({args.n} per level)")
        print(f"  Cost (this source): ${source_cost:.6f}")

    print("\n" + "=" * 100)
    print("ALL SOURCES COMPLETE")
    print(f"Total cost (all sources): ${_total_cost:.6f}")
    print("=" * 100)


if __name__ == "__main__":
    main()
