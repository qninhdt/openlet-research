"""
DCP v5 — Multi-Agent Question Generation Pipeline (LangGraph)

    [content] → 3 Generators → Classifier → Student → [output]
                     ↑ regenerate (per level)    ↓ fail
                     └── failed stems ──┘     Fixer ──→ Student (retry)

Flow:
    1. Generate:  3 level-specific generators (L1/L2/L3) produce questions in parallel.
    2. Classify:  Classifier predicts each question's level; mismatches trigger
                  per-level regeneration with stem-only negative constraints.
    3. Student:   Passed questions are tested by a student agent.
                  Correct answers → final output.
                  Wrong answers   → option fixer.
    4. Fix:       Fixer returns either corrected options or STUDENT_WRONG
                  (student must re-answer the same batch).
    5. Merge:     Collect all fully-passed and unresolved questions.
"""

import argparse
import json
import os
import random
import re
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from rich.console import Console
from rich.panel import Panel

load_dotenv()

console = Console()

# ---------------------------------------------------------------------------
# Global cost tracking (thread-safe)
# ---------------------------------------------------------------------------
_cost_lock = threading.Lock()
_total_cost = 0.0
_item_cost_lock = threading.Lock()
_item_costs: Dict[str, float] = {}


def _extract_cost(meta: dict) -> float:
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


def _add_cost(response, item_id: str = "") -> float:
    global _total_cost
    try:
        meta = getattr(response, "response_metadata", {}) or {}
        cost = _extract_cost(meta)
        if cost > 0:
            with _cost_lock:
                _total_cost += cost
            if item_id:
                with _item_cost_lock:
                    _item_costs[str(item_id)] = (
                        _item_costs.get(str(item_id), 0.0) + cost
                    )
        return cost
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------
_prompt_cache: Dict[str, str] = {}


def load_prompt(name: str, base_dir: str = "prompts") -> str:
    key = f"{base_dir}/{name}"
    if key not in _prompt_cache:
        path = Path(base_dir) / f"{name}.md"
        _prompt_cache[key] = path.read_text(encoding="utf-8")
    return _prompt_cache[key]


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------
class WorkflowState(TypedDict, total=False):
    item_id: str
    content: str
    n: int
    verbose: bool
    max_loops: int
    error: Optional[str]

    active_questions: List[Dict]
    student_map: Dict[int, Dict]
    classifier_map: Dict[int, Dict]
    stem_passed_questions: List[Dict]
    classifier_failed_questions: List[Dict]
    stem_loop_count: int

    option_pending_questions: List[Dict]
    student_failed_questions: List[Dict]
    option_loop_count: int

    fully_passed_questions: List[Dict]
    stem_unpassed_questions: List[Dict]
    option_unpassed_questions: List[Dict]

    loop_count: int
    next_global_id: int
    final_questions: List[Dict]
    cost: float


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _normalize_llm_output(text: str) -> str:
    """Normalize LLM output to a standard format regardless of model quirks."""
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = re.sub(r"(?m)^#{1,4}\s+", "", text)

    text = re.sub(
        r"(?m)^\s*(\d+)\.\s*Question\s*:\s*",
        r"ID: \1\nQuestion: ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?m)^\s*(\d+)\.\s+(?!Question\b)(?=[A-Z])",
        r"ID: \1\nQuestion: ",
        text,
    )
    text = re.sub(r"(?m)^(?:#{1,4}\s*|\*{1,2})(ID:\s*\d+)\**", r"\1", text)

    text = re.sub(r"(?m)^\s*[-–•]\s*([A-D][.:\)])", r"\1", text)
    text = re.sub(
        r"(?m)^\s+((?:Answer|Correct|Solvability|Alignment|Reasoning|Reason|Verdict|Question|ID|Level|Choices)\s*[:\-])",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?m)^\s+([A-D][.:\)])", r"\1", text)

    return text


def parse_generator_output(
    output: str, n: int, expected_level: int = None
) -> List[Dict]:
    """Parse generator/fixer output into question dicts with shuffled options."""
    normalized = _normalize_llm_output(output)
    blocks = re.split(r"(?:^|\n)(?=ID:\s*\d+)", normalized.strip())
    questions = []

    opt_pat = re.compile(
        r"^\s*\(?([A-D])\)?[.:\)]\s*(.+?)(?=\n\s*\(?[A-D]\)?[.:\)]|\n\s*(?:Answer|Correct)\b|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )

    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"ID:\s*\d+", block):
            continue
        q_id = None
        try:
            id_m = re.match(r"ID:\s*(\d+)", block)
            q_id = int(id_m.group(1)) if id_m else None

            # Extract level if present (fixer output includes Level:)
            level_m = re.search(r"Level:\s*(\d+)", block, re.IGNORECASE)
            level = int(level_m.group(1)) if level_m else expected_level

            q_m = re.search(
                r"Question:\s*(.+?)(?=\n\s*(?:\(?[A-D][.:\)]|\([A-D]\)\s))",
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if not q_m:
                console.print(
                    f"[yellow]Warning: Block ID={q_id} — 'Question:' not found, skipped[/yellow]"
                )
                continue
            question_text = q_m.group(1).strip()

            reason_m = re.search(
                r"(?:Reasoning|Reason):\s*(.+?)(?=\n(?:Question|Level):)",
                block,
                re.DOTALL | re.IGNORECASE,
            )
            reason = reason_m.group(1).strip() if reason_m else None

            opts: Dict[str, str] = {}
            for m in opt_pat.finditer(block):
                label = m.group(1).upper()
                if label not in opts:
                    opts[label] = m.group(2).strip()

            if len(opts) < 4:
                console.print(
                    f"[yellow]Warning: Block ID={q_id} — only {len(opts)} options found, skipped[/yellow]"
                )
                continue

            ans_m = re.search(
                r"(?:Answer|Correct(?:\s+Answer)?)\s*[:\-]\s*\(?([A-D])\)?",
                block,
                re.IGNORECASE,
            )
            if not ans_m:
                console.print(
                    f"[yellow]Warning: Block ID={q_id} — 'Answer:' not found, skipped[/yellow]"
                )
                continue
            correct_letter = ans_m.group(1).upper()

            options_in_order = [opts.get(l, "") for l in ["A", "B", "C", "D"]]
            correct_text = opts.get(correct_letter, "")

            # Shuffle options
            shuffled = options_in_order[:]
            random.shuffle(shuffled)
            correct_idx = (
                shuffled.index(correct_text) if correct_text in shuffled else 0
            )

            questions.append(
                {
                    "id": q_id,
                    "reason": reason,
                    "question": question_text,
                    "options": shuffled,
                    "correct_idx": correct_idx,
                    "level": level,
                }
            )

        except Exception as e:
            console.print(
                f"[bold red]Warning: Failed to parse block ID={q_id}: {e}[/bold red]"
            )

    if len(questions) < n:
        console.print(
            f"[yellow]Warning: Expected {n} questions, got {len(questions)}[/yellow]"
        )
    return questions


def parse_student_output(output: str) -> List[Dict]:
    """Parse student agent output. Returns list of {id, choices: list[str], reason}."""
    normalized = _normalize_llm_output(output)
    blocks = re.split(r"(?:^|\n)(?=ID:\s*\d+)", normalized.strip())
    results = []

    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"ID:\s*\d+", block):
            continue
        try:
            id_m = re.match(r"ID:\s*(\d+)", block)
            if not id_m:
                continue
            q_id = int(id_m.group(1))

            reason_m = re.search(
                r"Reason:\s*(.+?)(?=\nChoices:)",
                block,
                re.DOTALL | re.IGNORECASE,
            )
            reason = reason_m.group(1).strip() if reason_m else ""

            choices_m = re.search(r"Choices:\s*(.+)", block, re.IGNORECASE)
            choices_raw = choices_m.group(1).strip().upper() if choices_m else "NONE"

            if choices_raw == "NONE" or choices_raw == "":
                choices = []
            else:
                # Parse comma-separated or concatenated letters: "A, B" or "AB" or "A,B"
                choices = re.findall(r"[A-D]", choices_raw)

            results.append(
                {
                    "id": q_id,
                    "choices": choices,
                    "reason": reason,
                }
            )
        except Exception as e:
            console.print(
                f"[bold red]Warning: Failed to parse student block: {e}[/bold red]"
            )

    return results


def parse_classifier_output(output: str) -> List[Dict]:
    """Parse classifier agent output. Returns list of {id, predicted_level, reason}."""
    normalized = _normalize_llm_output(output)
    blocks = re.split(r"(?:^|\n)(?=ID:\s*\d+)", normalized.strip())
    results = []

    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"ID:\s*\d+", block):
            continue
        try:
            id_m = re.match(r"ID:\s*(\d+)", block)
            if not id_m:
                continue
            q_id = int(id_m.group(1))

            reason_m = re.search(
                r"Reason:\s*(.+?)(?=\nLevel:)",
                block,
                re.DOTALL | re.IGNORECASE,
            )
            reason = reason_m.group(1).strip() if reason_m else ""

            level_m = re.search(r"Level:\s*(\d+)", block, re.IGNORECASE)
            predicted_level = int(level_m.group(1)) if level_m else 0

            results.append(
                {
                    "id": q_id,
                    "predicted_level": predicted_level,
                    "reason": reason,
                }
            )
        except Exception as e:
            console.print(
                f"[bold red]Warning: Failed to parse classifier block: {e}[/bold red]"
            )

    return results


def parse_option_fixer_output(output: str) -> Tuple[Dict[int, Dict], Dict[int, str]]:
    """Parse option-fixer output.

    Returns:
      fixed_map: gid -> {"options": [...], "correct_idx": int, "reason": str}
      student_wrong_map: gid -> reason
    """
    normalized = _normalize_llm_output(output)
    blocks = re.split(r"(?:^|\n)(?=ID:\s*\d+)", normalized.strip())
    fixed_map: Dict[int, Dict] = {}
    student_wrong_map: Dict[int, str] = {}

    opt_pat = re.compile(r"(?m)^\s*([A-D])[.:\)]\s*(.+)$")

    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"ID:\s*\d+", block):
            continue

        id_m = re.match(r"ID:\s*(\d+)", block)
        if not id_m:
            continue
        gid = int(id_m.group(1))

        if re.search(r"Verdict\s*:\s*STUDENT_WRONG", block, re.IGNORECASE):
            reason_m = re.search(r"Reason\s*:\s*(.+)", block, re.IGNORECASE)
            student_wrong_map[gid] = (
                reason_m.group(1).strip()
                if reason_m
                else "Student reasoning is flawed."
            )
            continue

        reason_m = re.search(r"Reason\s*:\s*(.+)", block, re.IGNORECASE)
        reason = reason_m.group(1).strip() if reason_m else ""

        opts: Dict[str, str] = {}
        for m in opt_pat.finditer(block):
            label = m.group(1).upper()
            if label not in opts:
                opts[label] = m.group(2).strip()

        if len(opts) != 4:
            console.print(
                f"[yellow]Warning: Option Fixer ID={gid} missing options, skipping[/yellow]"
            )
            continue

        ans_m = re.search(
            r"(?:Answer|Correct(?:\s+Answer)?)\s*[:\-]\s*\(?([A-D])\)?",
            block,
            re.IGNORECASE,
        )
        if not ans_m:
            console.print(
                f"[yellow]Warning: Option Fixer ID={gid} missing Answer, skipping[/yellow]"
            )
            continue

        answer_letter = ans_m.group(1).upper()
        options = [opts.get(l, "") for l in ["A", "B", "C", "D"]]
        correct_idx = ["A", "B", "C", "D"].index(answer_letter)
        fixed_map[gid] = {
            "options": options,
            "correct_idx": correct_idx,
            "reason": reason,
        }

    return fixed_map, student_wrong_map


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------
CORRECT_MAP = {0: "A", 1: "B", 2: "C", 3: "D"}


def format_quiz_for_student(questions: List[Dict]) -> str:
    """Format questions for the Student Agent (sequential order)."""
    lines = []
    for q in questions:
        lines.append(f"ID: {q['global_id']}")
        lines.append(f"Question: {q['question']}")
        for i, label in enumerate(["A", "B", "C", "D"]):
            lines.append(f"{label}: {q['options'][i]}")
        lines.append("")
    return "\n".join(lines)


def format_quiz_for_classifier(questions: List[Dict], shuffled_order: List[int]) -> str:
    """Format questions for the Classifier Agent (shuffled order, no answer keys)."""
    lines = []
    for idx in shuffled_order:
        q = questions[idx]
        lines.append(f"ID: {q['global_id']}")
        lines.append(f"Question: {q['question']}")
        for i, label in enumerate(["A", "B", "C", "D"]):
            lines.append(f"{label}: {q['options'][i]}")
        lines.append("")
    return "\n".join(lines)


def format_stem_negative_constraints(stem_passed_questions: List[Dict]) -> str:
    """Format stem-only negative constraints (no ID/options/answer to save tokens)."""
    if not stem_passed_questions:
        return "(none)"
    return "\n".join(f"- {q['question']}" for q in stem_passed_questions)


def format_failed_for_option_fixer(
    failed_questions: List[Dict], student_map: Dict[int, Dict]
) -> str:
    """Format option-phase failures for the Option Fixer Agent."""
    lines = []
    for q in failed_questions:
        gid = q["global_id"]
        student = student_map.get(gid, {})

        correct_letter = CORRECT_MAP.get(q["correct_idx"], "A")
        student_choices = student.get("choices", [])
        student_choices_str = ", ".join(student_choices) if student_choices else "NONE"

        lines.append(f"ID: {gid}")
        lines.append(f"Level: {q['level']}")
        lines.append(f"Question: {q['question']}")
        for i, label in enumerate(["A", "B", "C", "D"]):
            lines.append(f"{label}: {q['options'][i]}")
        lines.append(f"Answer: {correct_letter}")
        lines.append(f"Student Choices: {student_choices_str}")
        lines.append(f"Student Reason: {student.get('reason', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rich display helpers
# ---------------------------------------------------------------------------
def _print_questions_panel(questions: List[Dict], title: str, border_style: str):
    if not questions:
        console.print(
            Panel(
                "[italic yellow]No questions parsed[/italic yellow]",
                title=f"[bold {border_style}]{title}[/bold {border_style}]",
                border_style=border_style,
            )
        )
        return
    lines = []
    for q in questions:
        lines.append(
            f"[bold cyan]ID: {q.get('global_id', q.get('id', '?'))}[/bold cyan] [dim](L{q.get('level', '?')})[/dim]"
        )
        if q.get("reason"):
            lines.append(f"[italic magenta]Reason: {q['reason']}[/italic magenta]")
        lines.append(f"[bold]Q:[/bold] {q.get('question', '')}")
        for i, opt in enumerate(q.get("options", [])):
            prefix = "[bold green]*[/bold green]" if i == q.get("correct_idx") else " "
            lines.append(f"  {prefix} {chr(65+i)}: [dim]{opt}[/dim]")
        lines.append("")
    console.print(
        Panel(
            "\n".join(lines).strip(),
            title=f"[bold {border_style}]{title}[/bold {border_style}]",
            border_style=border_style,
        )
    )


# ---------------------------------------------------------------------------
# Node: generate
# ---------------------------------------------------------------------------
def _generate_for_level(
    *,
    level: int,
    target_count: int,
    content: str,
    negative_constraints: str,
    item_id: str,
    verbose: bool,
    llm,
) -> List[Dict]:
    prompt = (
        load_prompt(f"l{level}_generator", "prompts/v5")
        .replace("{analysis}", content)
        .replace("{n}", str(target_count))
        .replace("{negative_constraints}", negative_constraints)
    )
    response = llm.invoke(prompt)
    _add_cost(response, item_id=item_id)
    if verbose:
        console.print(
            Panel(
                response.content,
                title=f"[dim]L{level} Generator RAW — {item_id}[/dim]",
                border_style="dim",
            )
        )
    return parse_generator_output(response.content, target_count, expected_level=level)


def generate_node(state: WorkflowState, llm) -> Dict:
    """Initial generation: create n questions per level (L1/L2/L3)."""
    if state.get("error"):
        return {}

    item_id = state["item_id"]
    content = state["content"]
    n = state["n"]
    verbose = state.get("verbose", False)

    results_by_level: Dict[int, List[Dict]] = {}

    def generate_level(level: int):
        questions = _generate_for_level(
            level=level,
            target_count=n,
            content=content,
            negative_constraints="(none)",
            item_id=item_id,
            verbose=verbose,
            llm=llm,
        )
        return level, questions

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(generate_level, lvl) for lvl in [1, 2, 3]]
        for future in as_completed(futures):
            level, questions = future.result()
            results_by_level[level] = questions

    all_questions: List[Dict] = []
    global_id = 1
    for level in [1, 2, 3]:
        for q in results_by_level.get(level, []):
            q["global_id"] = global_id
            all_questions.append(q)
            global_id += 1

    console.print(
        f"[green]Generated {len(all_questions)} questions "
        f"(L1={len(results_by_level.get(1,[]))}, "
        f"L2={len(results_by_level.get(2,[]))}, "
        f"L3={len(results_by_level.get(3,[]))})[/green]"
    )
    if verbose:
        _print_questions_panel(all_questions, f"Generated Quiz — {item_id}", "green")

    return {
        "active_questions": all_questions,
        "stem_passed_questions": [],
        "classifier_failed_questions": [],
        "option_pending_questions": [],
        "student_failed_questions": [],
        "fully_passed_questions": [],
        "stem_unpassed_questions": [],
        "option_unpassed_questions": [],
        "next_global_id": global_id,
        "stem_loop_count": 0,
        "option_loop_count": 0,
        "loop_count": 0,
    }


def classify_stem_node(state: WorkflowState, llm) -> Dict:
    """Run classifier on current active batch and split stem pass/fail."""
    if state.get("error"):
        return {}

    item_id = state["item_id"]
    content = state["content"]
    n = state["n"]
    verbose = state.get("verbose", False)
    active_questions = state.get("active_questions", [])

    if not active_questions:
        return {}

    indices = list(range(len(active_questions)))
    random.shuffle(indices)
    classifier_quiz = format_quiz_for_classifier(active_questions, indices)
    classifier_prompt_template = load_prompt("classifier", "prompts/v5")
    clf_prompt = classifier_prompt_template.replace("{content}", content).replace(
        "{quiz}", classifier_quiz
    )
    clf_response = llm.invoke(clf_prompt)
    _add_cost(clf_response, item_id=item_id)

    if verbose:
        console.print(
            Panel(
                clf_response.content,
                title=f"[dim]Classifier RAW (Stem) — {item_id}[/dim]",
                border_style="dim",
            )
        )

    classifier_map: Dict[int, Dict] = {
        c["id"]: c for c in parse_classifier_output(clf_response.content)
    }

    existing_passed = state.get("stem_passed_questions", [])
    existing_passed_ids = {q["global_id"] for q in existing_passed}
    new_passed: List[Dict] = []
    failed: List[Dict] = []

    for q in active_questions:
        gid = q["global_id"]
        predicted = classifier_map.get(gid, {}).get("predicted_level", 0)
        if predicted == q["level"]:
            if gid not in existing_passed_ids:
                new_passed.append(q)
        else:
            failed.append(q)

    stem_passed_questions = existing_passed + new_passed

    passed_by_level = {1: 0, 2: 0, 3: 0}
    for q in stem_passed_questions:
        lvl = q.get("level", 0)
        if lvl in passed_by_level:
            passed_by_level[lvl] += 1

    stem_loop_count = state.get("stem_loop_count", 0) + 1
    console.print(
        f"[cyan]Stem loop {stem_loop_count}:"
        f" L1={passed_by_level[1]}/{n}, L2={passed_by_level[2]}/{n}, L3={passed_by_level[3]}/{n}"
        f" | failed batch={len(failed)}[/cyan]"
    )

    return {
        "classifier_map": classifier_map,
        "stem_passed_questions": stem_passed_questions,
        "classifier_failed_questions": failed,
        "stem_loop_count": stem_loop_count,
        "loop_count": max(stem_loop_count, state.get("option_loop_count", 0)),
        "active_questions": [],
        "stem_unpassed_questions": state.get("stem_unpassed_questions", []),
    }


def route_after_classifier(state: WorkflowState) -> str:
    n = state.get("n", 0)
    max_loops = state.get("max_loops", 5)
    passed_by_level = {1: 0, 2: 0, 3: 0}
    for q in state.get("stem_passed_questions", []):
        lvl = q.get("level", 0)
        if lvl in passed_by_level:
            passed_by_level[lvl] += 1

    stem_complete = all(passed_by_level[level] >= n for level in [1, 2, 3])
    if stem_complete:
        return "prepare_student"

    if state.get("stem_loop_count", 0) >= max_loops:
        return "prepare_student"

    failed = state.get("classifier_failed_questions", [])
    return "regenerate_stem" if failed else "prepare_student"


def regenerate_stem_node(state: WorkflowState, llm) -> Dict:
    """Regenerate only levels that have failed stem samples in current batch."""
    if state.get("error"):
        return {}

    item_id = state["item_id"]
    content = state["content"]
    verbose = state.get("verbose", False)
    failed = state.get("classifier_failed_questions", [])
    next_global_id = state.get("next_global_id", 1)

    failed_by_level: Dict[int, List[Dict]] = {1: [], 2: [], 3: []}
    for q in failed:
        lvl = q.get("level", 0)
        if lvl in failed_by_level:
            failed_by_level[lvl].append(q)

    stem_passed_questions = state.get("stem_passed_questions", [])
    passed_by_level: Dict[int, List[Dict]] = {1: [], 2: [], 3: []}
    for q in stem_passed_questions:
        lvl = q.get("level", 0)
        if lvl in passed_by_level:
            passed_by_level[lvl].append(q)

    levels_to_regen = [
        (level, len(failed_by_level[level]))
        for level in [1, 2, 3]
        if len(failed_by_level[level]) > 0
    ]

    results_by_level: Dict[int, List[Dict]] = {}

    def regen_level(level: int, need: int) -> Tuple[int, List[Dict]]:
        negatives = format_stem_negative_constraints(passed_by_level[level])
        return level, _generate_for_level(
            level=level,
            target_count=need,
            content=content,
            negative_constraints=negatives,
            item_id=item_id,
            verbose=verbose,
            llm=llm,
        )

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(regen_level, level, need) for level, need in levels_to_regen
        ]
        for future in as_completed(futures):
            level, questions = future.result()
            results_by_level[level] = questions

    regenerated: List[Dict] = []
    for level in [1, 2, 3]:
        for q in results_by_level.get(level, []):
            q["global_id"] = next_global_id
            next_global_id += 1
            regenerated.append(q)

    return {
        "active_questions": regenerated,
        "next_global_id": next_global_id,
    }


def prepare_student_node(state: WorkflowState) -> Dict:
    """Prepare stem-passed questions for student validation."""
    n = state.get("n", 0)
    max_loops = state.get("max_loops", 5)
    stem_passed_questions = state.get("stem_passed_questions", [])

    by_level: Dict[int, List[Dict]] = {1: [], 2: [], 3: []}
    for q in stem_passed_questions:
        lvl = q.get("level", 0)
        if lvl in by_level and len(by_level[lvl]) < n:
            by_level[lvl].append(q)

    option_pending = by_level[1] + by_level[2] + by_level[3]
    option_pending.sort(key=lambda q: (q.get("level", 0), q.get("global_id", 0)))

    stem_unpassed = state.get("stem_unpassed_questions", [])
    if state.get("stem_loop_count", 0) >= max_loops:
        stem_unpassed = state.get("classifier_failed_questions", [])

    return {
        "option_pending_questions": option_pending,
        "fully_passed_questions": state.get("fully_passed_questions", []),
        "option_unpassed_questions": state.get("option_unpassed_questions", []),
        "stem_unpassed_questions": stem_unpassed,
        "option_loop_count": state.get("option_loop_count", 0),
    }


def student_node(state: WorkflowState, llm) -> Dict:
    """Run student on current option-pending set and split pass/fail."""
    if state.get("error"):
        return {}

    item_id = state["item_id"]
    content = state["content"]
    verbose = state.get("verbose", False)
    option_pending = state.get("option_pending_questions", [])

    if not option_pending:
        return {
            "student_map": {},
            "student_failed_questions": [],
            "option_loop_count": state.get("option_loop_count", 0),
        }

    student_prompt_template = load_prompt("student", "prompts/v5")
    student_quiz = format_quiz_for_student(option_pending)
    stu_prompt = student_prompt_template.replace("{content}", content).replace(
        "{quiz}", student_quiz
    )
    stu_response = llm.invoke(stu_prompt)
    _add_cost(stu_response, item_id=item_id)

    if verbose:
        console.print(
            Panel(
                stu_response.content,
                title=f"[dim]Student RAW (Option) — {item_id}[/dim]",
                border_style="dim",
            )
        )

    student_map: Dict[int, Dict] = {
        s["id"]: s for s in parse_student_output(stu_response.content)
    }

    fully_passed = state.get("fully_passed_questions", [])
    failed: List[Dict] = []
    for q in option_pending:
        gid = q["global_id"]
        correct_letter = CORRECT_MAP.get(q["correct_idx"], "A")
        s_choices = student_map.get(gid, {}).get("choices", [])
        if s_choices == [correct_letter]:
            fully_passed.append(q)
        else:
            failed.append(q)

    option_loop_count = state.get("option_loop_count", 0) + 1
    console.print(
        f"[green]Option loop {option_loop_count}: pass_total={len(fully_passed)} | failed={len(failed)}[/green]"
    )

    return {
        "student_map": student_map,
        "student_failed_questions": failed,
        "fully_passed_questions": fully_passed,
        "option_loop_count": option_loop_count,
        "loop_count": max(state.get("stem_loop_count", 0), option_loop_count),
    }


def route_after_student(state: WorkflowState) -> str:
    failed = state.get("student_failed_questions", [])
    if not failed:
        return "merge"
    if state.get("option_loop_count", 0) >= state.get("max_loops", 5):
        return "merge"
    return "option_fixer"


def option_fixer_node(state: WorkflowState, llm) -> Dict:
    """Fix failed options only; keep student_wrong in retry set and print it."""
    if state.get("error"):
        return {}

    item_id = state["item_id"]
    content = state["content"]
    verbose = state.get("verbose", False)
    failed_questions = state.get("student_failed_questions", [])
    student_map = state.get("student_map", {})

    if not failed_questions:
        return {"option_pending_questions": []}

    fixer_prompt_template = load_prompt("fixer", "prompts/v5")
    fixer_prompt = fixer_prompt_template.replace("{analysis}", content).replace(
        "{failed_questions}",
        format_failed_for_option_fixer(failed_questions, student_map),
    )
    fixer_response = llm.invoke(fixer_prompt)
    _add_cost(fixer_response, item_id=item_id)

    if verbose:
        console.print(
            Panel(
                fixer_response.content,
                title=f"[dim]Option Fixer RAW — {item_id}[/dim]",
                border_style="dim",
            )
        )

    fixed_map, student_wrong_map = parse_option_fixer_output(fixer_response.content)

    next_pending: List[Dict] = []
    for q in failed_questions:
        gid = q["global_id"]
        if gid in student_wrong_map:
            console.print(
                f"[yellow]ID {gid}: STUDENT_WRONG — {student_wrong_map[gid]}[/yellow]"
            )
            next_pending.append(q)
            continue

        fix = fixed_map.get(gid)
        if fix:
            next_pending.append(
                {
                    **q,
                    "options": fix["options"],
                    "correct_idx": fix["correct_idx"],
                    "reason": fix.get("reason") or q.get("reason"),
                }
            )
        else:
            next_pending.append(q)

    return {"option_pending_questions": next_pending}


# ---------------------------------------------------------------------------
# Node: merge
# ---------------------------------------------------------------------------
def merge_node(state: WorkflowState) -> Dict:
    """Assemble final questions from fully passed and unresolved buckets."""
    if state.get("error"):
        return {"final_questions": []}

    all_output_questions = (
        state.get("fully_passed_questions", [])
        + (
            state.get("student_failed_questions", [])
            if state.get("option_loop_count", 0) >= state.get("max_loops", 5)
            else state.get("option_unpassed_questions", [])
        )
        + state.get("stem_unpassed_questions", [])
    )
    all_output_questions.sort(key=lambda q: (q.get("level", 0), q.get("global_id", 0)))

    final_questions = [
        {
            "content": q["question"],
            "options": q["options"],
            "correct": q["correct_idx"],
            "level": q.get("level", 0),
            "type": "General",
        }
        for q in all_output_questions
    ]

    cost = _item_costs.get(str(state["item_id"]), 0.0)
    console.print(
        Panel(
            (
                f"{len(final_questions)} questions assembled\n"
                f"- fully passed: {len(state.get('fully_passed_questions', []))}\n"
                f"- option unpassed: {len(state.get('student_failed_questions', [])) if state.get('option_loop_count', 0) >= state.get('max_loops', 5) else len(state.get('option_unpassed_questions', []))}\n"
                f"- stem unpassed: {len(state.get('stem_unpassed_questions', []))}"
            ),
            title=f"[bold cyan]Merge — {state['item_id']}[/bold cyan]",
            border_style="cyan",
        )
    )
    return {"final_questions": final_questions, "cost": cost}


# ---------------------------------------------------------------------------
# Build LangGraph workflow
# ---------------------------------------------------------------------------
def build_workflow(llm):
    graph = StateGraph(WorkflowState)
    graph.add_node("generate", lambda s: generate_node(s, llm))
    graph.add_node("classify_stem", lambda s: classify_stem_node(s, llm))
    graph.add_node("regenerate_stem", lambda s: regenerate_stem_node(s, llm))
    graph.add_node("prepare_student", prepare_student_node)
    graph.add_node("student", lambda s: student_node(s, llm))
    graph.add_node("option_fixer", lambda s: option_fixer_node(s, llm))
    graph.add_node("merge", merge_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", "classify_stem")
    graph.add_conditional_edges(
        "classify_stem",
        route_after_classifier,
        {
            "regenerate_stem": "regenerate_stem",
            "prepare_student": "prepare_student",
        },
    )
    graph.add_edge("regenerate_stem", "classify_stem")
    graph.add_edge("prepare_student", "student")
    graph.add_conditional_edges(
        "student",
        route_after_student,
        {
            "option_fixer": "option_fixer",
            "merge": "merge",
        },
    )
    graph.add_edge("option_fixer", "student")
    graph.add_edge("merge", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Per-item entry point
# ---------------------------------------------------------------------------
def process_item(item: Dict, n: int, workflow, max_loops: int, verbose: bool) -> Dict:
    """Run a single item through the LangGraph v5 workflow."""
    item_id = item["id"]
    source = item.get("source", "unknown")

    console.print(f"\n[bold blue]{'='*60}[/bold blue]")
    console.print(f"[bold blue]Processing: {item_id}[/bold blue]")
    console.print(f"[bold blue]{'='*60}[/bold blue]")

    init_state: WorkflowState = {
        "item_id": item_id,
        "content": item["content"],
        "n": n,
        "verbose": verbose,
        "max_loops": max_loops,
        "error": None,
    }
    try:
        final_state = workflow.invoke(init_state)
        cost = _item_costs.get(str(item_id), 0.0)
        result = {
            "id": item_id,
            "source": source,
            "cost": cost,
            "generated_questions": final_state.get("final_questions", []),
        }
        console.print(
            f"[bold green]✓ {item_id}: {len(result['generated_questions'])} questions, cost=${cost:.6f}[/bold green]"
        )
        return result
    except Exception as e:
        console.print(f"[bold red]✗ {item_id}: error — {e}[/bold red]")
        traceback.print_exc()
        return {"id": item_id, "source": source, "cost": 0.0, "error": str(e)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="DCP v5 — Multi-Agent Testing & Classification Pipeline (LangGraph)"
    )
    parser.add_argument("--model", type=str, default="google/gemma-3-12b-it")
    parser.add_argument("--data-path", type=str, default="datasets/unified/data.json")
    parser.add_argument("--output-dir", type=str, default="outputs")
    parser.add_argument("--sources", type=str, nargs="+", default=None)
    parser.add_argument(
        "--n", type=int, default=5, help="Questions per level (total = 3×n)"
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=5,
        help="Max testing→evaluation→refinement iterations",
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Parallel items to process"
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    llm = ChatOpenAI(
        model=args.model,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
        max_tokens=8192,
    )

    workflow = build_workflow(llm)

    with open(args.data_path, encoding="utf-8") as f:
        data: List[Dict] = json.load(f)

    if args.sources:
        data = [
            d
            for d in data
            if d.get("source", "").lower() in [s.lower() for s in args.sources]
        ]
    if args.limit:
        data = data[: args.limit]

    console.print(f"[bold]Pipeline:[/bold] DCP v5 (LangGraph)")
    console.print(f"[bold]Model:[/bold]   {args.model}")
    console.print(
        f"[bold]Items:[/bold]   {len(data)}, [bold]N per level:[/bold] {args.n}, [bold]Workers:[/bold] {args.workers}"
    )
    console.print(f"[bold]Max loops:[/bold] {args.max_loops}")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_item, item, args.n, workflow, args.max_loops, args.verbose
            ): item
            for item in data
        }
        for i, future in enumerate(as_completed(futures), 1):
            item = futures[future]
            result = future.result()
            results.append(result)
            console.print(f"Item {i}/{len(data)}: {item['id']}")

    results.sort(key=lambda x: x["id"])

    source_groups: Dict[str, List] = {}
    for r in results:
        src = r.get("source", "unknown")
        source_groups.setdefault(src, []).append(r)

    model_id = args.model.replace("/", "_") + "-v5"
    for src, src_results in source_groups.items():
        out_dir = Path(args.output_dir) / src / model_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "predictions.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(src_results, f, ensure_ascii=False, indent=2)
        total_cost = sum(r.get("cost", 0.0) for r in src_results)
        console.print(
            f"\n[bold green]✓ {src}: {len(src_results)} items → {out_path} "
            f"(total cost: ${total_cost:.4f})[/bold green]"
        )

    console.print(f"\n[bold cyan]Grand total cost: ${_total_cost:.4f}[/bold cyan]")


if __name__ == "__main__":
    main()
