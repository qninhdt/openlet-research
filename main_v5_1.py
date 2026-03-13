"""
DCP v5 — Multi-Agent Question Generation Pipeline (LangGraph Refactored)

Architecture:
    Hub-and-Spoke with Dynamic Fan-out (Map-Reduce) and Pre-allocated Sequential IDs.

Key Mechanisms:
    - Independent Phase Loops: Generation Phase (Stem) and Evaluation Phase (Option)
      maintain isolated retry trackers (gen_loop, fix_count) per item.
    - Forced Progression: Items exceeding their phase-specific max_loops are forcefully
      progressed (STEM_FAILED -> PENDING_STUDENT, PENDING_FIX -> PASSED) to prevent infinite deadlocks.
    - ID Pre-allocation: Global sequential IDs (1 -> N) are pre-allocated by the Controller.
    - Anti-Bias Classification: Classifier evaluates via an ephemeral ID map (1 -> M).
"""

import argparse
import json
import os
import random
import re
import traceback
import operator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from typing_extensions import TypedDict, Annotated

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

load_dotenv()
console = Console()

DATA_PATH = "datasets/unified/data.json"


# ---------------------------------------------------------------------------
# Core Utilities & Prompt Management
# ---------------------------------------------------------------------------
def _extract_cost(meta: dict) -> float:
    """Extract inference cost securely from LLM response metadata."""
    for key in ["token_usage", "cost", "openrouter_cost"]:
        val = meta.get(key)
        if isinstance(val, dict) and "cost" in val:
            return float(val["cost"])
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue

    headers = meta.get("headers", {})
    if isinstance(headers, dict):
        for key in ["x-openrouter-cost", "X-Openrouter-Cost"]:
            if headers.get(key):
                try:
                    return float(headers[key])
                except (TypeError, ValueError):
                    pass
    return 0.0


_prompt_cache: Dict[str, str] = {}


def load_prompt(name: str, base_dir: str = "prompts") -> str:
    """Load and cache prompt templates from disk."""
    key = f"{base_dir}/{name}"
    if key not in _prompt_cache:
        path = Path(base_dir) / f"{name}.md"
        _prompt_cache[key] = path.read_text(encoding="utf-8")
    return _prompt_cache[key]


def load_data(sources: List[str], limit: int = None) -> Dict[str, List[dict]]:
    """Load data from the unified data file, grouped by source."""
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    sources_lower = [s.lower() for s in sources]
    grouped: Dict[str, List[dict]] = {s: [] for s in sources_lower}
    for item in data:
        src = item.get("source", "").lower()
        if src in grouped:
            grouped[src].append(item)

    if limit is not None:
        grouped = {s: items[:limit] for s, items in grouped.items()}

    return grouped


# ---------------------------------------------------------------------------
# State Schema & Reducers
# ---------------------------------------------------------------------------
def merge_dicts(a: dict, b: dict) -> dict:
    """Reducer: Merges state dictionaries seamlessly during Graph Fan-in."""
    c = a.copy() if a else {}
    if b:
        c.update(b)
    return c


class WorkflowState(TypedDict):
    item_id: str
    content: str
    n: int
    max_loops: int
    verbose: bool

    questions: Annotated[Dict[int, Any], merge_dicts]
    next_global_id: int

    gen_tasks: List[Dict]
    classify_queue: List[Dict]
    student_queue: List[Dict]
    fixer_queue: List[Dict]

    cost: Annotated[float, operator.add]
    loop_count: int
    stem_retries: int
    final_questions: List[Dict]
    error: str


# ---------------------------------------------------------------------------
# UI Formatting
# ---------------------------------------------------------------------------
def _print_parsed_questions(items: List[Dict], title: str, border_style: str = "dim"):
    """Visually renders parsed data ensuring proper reason formatting and correct answer highlighting."""
    if not items:
        return
    lines = []
    for item in items:
        q_id = item.get("id", "?")
        lvl = item.get("level", "?")
        lines.append(f"[bold cyan]ID: {q_id}[/bold cyan] [dim](L{lvl})[/dim]")

        if item.get("reason"):
            lines.append(f"[dim italic]Reason: {item['reason']}[/dim italic]")

        if item.get("is_classifier"):
            color = "green" if item["val"] == item["level"] else "red"
            lines.append(
                f"Predicted Level: [bold {color}]{item['val']}[/bold {color}] (Expected: {item['level']})"
            )
        elif item.get("is_student"):
            ans_str = (
                ", ".join(item["val"])
                if isinstance(item["val"], list)
                else str(item["val"])
            )
            color = "green" if item["val"] == [item.get("correct_letter")] else "red"
            lines.append(
                f"Student Choice: [bold {color}]{ans_str}[/bold {color}] (Key: {item.get('correct_letter')})"
            )
        elif item.get("is_fixer_wrong"):
            if item.get("hint"):
                lines.append(f"[dim]Hint: {item['hint']}[/dim]")
            lines.append("[bold red]Verdict: STUDENT_WRONG[/bold red]")
        else:
            if item.get("question"):
                lines.append(f"[bold]Q:[/bold] {item['question']}")

            options = item.get("options", [])
            correct_idx = item.get("correct_idx", -1)
            for i, opt in enumerate(options):
                prefix = "[bold green]*[/bold green]" if i == correct_idx else " "
                lines.append(f"  {prefix} {chr(65+i)}: [white]{opt}[/white]")

        lines.append("")

    console.print(
        Panel(
            "\n".join(lines).strip(),
            title=f"[bold {border_style}]{title}[/bold {border_style}]",
            border_style=border_style,
        )
    )


# ---------------------------------------------------------------------------
# Parsing & Normalization
# ---------------------------------------------------------------------------
CORRECT_MAP = {0: "A", 1: "B", 2: "C", 3: "D"}


def _normalize_llm_output(text: str) -> str:
    """Standardize markdown variations and list formats from LLM outputs."""
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?m)^#{1,4}\s+", "", text)
    text = re.sub(
        r"(?m)^\s*(\d+)\.\s*Question\s*:\s*",
        r"ID: \1\nQuestion: ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?m)^\s*(\d+)\.\s+(?!Question\b)(?=[A-Z])", r"ID: \1\nQuestion: ", text
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
    output: str, expected_level: int, start_id: int, gen_loop: int
) -> List[Dict]:
    """Parse generated questions, attach sequential IDs and tracking metadata."""
    normalized = _normalize_llm_output(output)
    blocks = re.split(r"(?:^|\n)(?=ID:\s*\d+)", normalized.strip())
    questions = []
    opt_pat = re.compile(
        r"^\s*\(?([A-D])\)?[.:\)]\s*(.+?)(?=\n\s*\(?[A-D]\)?[.:\)]|\n\s*(?:Answer|Correct)\b|\Z)",
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )

    current_id = start_id
    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"ID:\s*\d+", block):
            continue
        try:
            level = expected_level

            q_m = re.search(
                r"Question:\s*(.+?)(?=\n\s*(?:\(?[A-D][.:\)]|\([A-D]\)\s))",
                block,
                re.DOTALL | re.IGNORECASE,
            )
            if not q_m:
                continue

            reason_m = re.search(
                r"(?:Reasoning|Reason):\s*(.+?)(?=\nQuestion:)",
                block,
                re.DOTALL | re.IGNORECASE,
            )

            opts = {
                m.group(1).upper(): m.group(2).strip() for m in opt_pat.finditer(block)
            }
            if len(opts) < 4:
                continue

            ans_m = re.search(
                r"(?:Answer|Correct(?:\s+Answer)?)\s*[:\-]\s*\(?([A-D])\)?",
                block,
                re.IGNORECASE,
            )
            if not ans_m:
                continue

            correct_letter = ans_m.group(1).upper()
            options_in_order = [opts.get(l, "") for l in ["A", "B", "C", "D"]]
            correct_text = opts.get(correct_letter, "")

            shuffled = options_in_order[:]
            random.shuffle(shuffled)
            correct_idx = (
                shuffled.index(correct_text) if correct_text in shuffled else 0
            )

            questions.append(
                {
                    "id": current_id,
                    "reason": reason_m.group(1).strip() if reason_m else None,
                    "question": q_m.group(1).strip(),
                    "options": shuffled,
                    "correct_idx": correct_idx,
                    "level": level,
                    "status": "PENDING_CLASSIFY",
                    "gen_loop": gen_loop,
                    "fix_count": 0,
                    "flags": [],
                }
            )
            current_id += 1
        except Exception:
            pass
    return questions


def parse_agent_output(output: str, has_choices=False) -> List[Dict]:
    """Generic parser reading ID-mapped responses (Classifier / Student)."""
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
            parsed_id = int(id_m.group(1))

            target_key = "Choices" if has_choices else "Level"
            reason_m = re.search(
                rf"Reason:\s*(.+?)(?=\n{target_key}:)", block, re.DOTALL | re.IGNORECASE
            )

            if has_choices:
                choices_m = re.search(r"Choices:\s*(.+)", block, re.IGNORECASE)
                choices_raw = (
                    choices_m.group(1).strip().upper() if choices_m else "NONE"
                )
                val = (
                    []
                    if choices_raw in ["NONE", ""]
                    else re.findall(r"[A-D]", choices_raw)
                )
            else:
                level_m = re.search(r"Level:\s*(\d+)", block, re.IGNORECASE)
                val = int(level_m.group(1)) if level_m else 0

            results.append(
                {
                    "parsed_id": parsed_id,
                    "val": val,
                    "reason": reason_m.group(1).strip() if reason_m else "",
                }
            )
        except Exception:
            pass
    return results


def parse_option_fixer_output(output: str) -> Dict[int, Dict]:
    """Parse option-fixer output into structured resolutions."""
    normalized = _normalize_llm_output(output)
    blocks = re.split(r"(?:^|\n)(?=ID:\s*\d+)", normalized.strip())
    fixed_map = {}
    opt_pat = re.compile(r"(?m)^\s*([A-D])[.:\)]\s*(.+)$")

    for block in blocks:
        block = block.strip()
        if not block or not re.match(r"ID:\s*\d+", block):
            continue
        id_m = re.match(r"ID:\s*(\d+)", block)
        if not id_m:
            continue
        parsed_id = int(id_m.group(1))

        reason_m = re.search(r"Reason\s*:\s*(.+)", block, re.IGNORECASE)
        opts = {m.group(1).upper(): m.group(2).strip() for m in opt_pat.finditer(block)}
        if len(opts) != 4:
            continue

        ans_m = re.search(
            r"(?:Answer|Correct(?:\s+Answer)?)\s*[:\-]\s*\(?([A-D])\)?",
            block,
            re.IGNORECASE,
        )
        if not ans_m:
            continue

        fixed_map[parsed_id] = {
            "options": [opts.get(l, "") for l in ["A", "B", "C", "D"]],
            "correct_idx": ["A", "B", "C", "D"].index(ans_m.group(1).upper()),
            "reason": reason_m.group(1).strip() if reason_m else "",
        }
    return fixed_map


# ---------------------------------------------------------------------------
# Worker Nodes (LLM Execution)
# ---------------------------------------------------------------------------
def generator_node(request: dict, llm) -> Dict:
    level, count = request["level"], request["count"]
    prompt = (
        load_prompt(f"l{level}_generator", "prompts/v5")
        .replace("{content}", request["content"])
        .replace("{n}", str(count))
        .replace("{positive_samples}", request["positive_samples"])
        .replace("{negative_samples}", request["negative_samples"])
    )

    resp = llm.invoke(prompt)
    gen_loop = request.get("gen_loop", 0)
    start_id = request["start_id"]
    qs = parse_generator_output(resp.content, level, start_id, gen_loop)

    result: Dict[int, Dict] = {q["id"]: q for q in qs}

    parsed_count = len(qs)
    for offset in range(parsed_count, count):
        placeholder_id = start_id + offset
        result[placeholder_id] = {
            "id": placeholder_id,
            "question": "",
            "options": ["", "", "", ""],
            "correct_idx": 0,
            "level": level,
            "status": "STEM_FAILED",
            "gen_loop": gen_loop,
            "fix_count": 0,
            "flags": [],
        }

    if request.get("verbose"):
        _print_parsed_questions(
            qs, f"Generator L{level} Parsed Output", border_style="cyan"
        )
        if parsed_count < count:
            console.print(
                f"[yellow]Generator L{level}: {count - parsed_count} question(s) failed to parse[/yellow]"
            )

    return {
        "questions": result,
        "cost": _extract_cost(resp.response_metadata),
    }


def classifier_node(request: dict, llm) -> Dict:
    batch = [q for q in request["batch"] if q.get("status") != "STEM_FAILED"]
    if not batch:
        return {"questions": {}, "cost": 0.0}
    random.shuffle(batch)

    fake_map = {i + 1: q for i, q in enumerate(batch)}
    quiz_text = "\n".join(
        f"ID: {fake_id}\nQuestion: {q['question']}\n"
        + "\n".join(f"{chr(65+j)}: {opt}" for j, opt in enumerate(q["options"]))
        + "\n"
        for fake_id, q in fake_map.items()
    )

    prompt = (
        load_prompt("classifier", "prompts/v5")
        .replace("{content}", request["content"])
        .replace("{quiz}", quiz_text)
    )
    resp = llm.invoke(prompt)
    parsed = parse_agent_output(resp.content, has_choices=False)

    updates = {}
    display_list = []

    for p in parsed:
        fake_id = p["parsed_id"]
        if fake_id in fake_map:
            q = fake_map[fake_id].copy()
            q["classifier_reason"] = p["reason"]
            q["predicted_level"] = p["val"]
            if p["val"] == q["level"]:
                q["status"] = "PENDING_STUDENT"
            else:
                q["status"] = "STEM_FAILED"
            updates[q["id"]] = q
            if request.get("verbose"):
                display_list.append(
                    {
                        "id": q["id"],
                        "level": q["level"],
                        "reason": p["reason"],
                        "val": p["val"],
                        "is_classifier": True,
                    }
                )

    for q in fake_map.values():
        if q["id"] not in updates:
            q_copy = q.copy()
            q_copy["status"] = "STEM_FAILED"
            updates[q["id"]] = q_copy

    if request.get("verbose"):
        _print_parsed_questions(
            display_list, "Classifier Verification Results", border_style="blue"
        )

    return {"questions": updates, "cost": _extract_cost(resp.response_metadata)}


def student_node(request: dict, llm) -> Dict:
    batch = request["batch"]
    batch.sort(key=lambda x: (x["level"], x["id"]))

    def _build_question_block(q: dict) -> str:
        lines = [f"ID: {q['id']}\nQuestion: {q['question']}"]
        lines += [f"{chr(65+j)}: {opt}" for j, opt in enumerate(q["options"])]
        if q.get("fixer_hint"):
            lines.append(f"Hint: {q['fixer_hint']}")
        lines.append("")
        return "\n".join(lines)

    quiz_text = "\n".join(_build_question_block(q) for q in batch)

    prompt = (
        load_prompt("student", "prompts/v5")
        .replace("{content}", request["content"])
        .replace("{quiz}", quiz_text)
    )
    resp = llm.invoke(prompt)
    parsed = parse_agent_output(resp.content, has_choices=True)

    updates = {}
    batch_map = {q["id"]: q for q in batch}
    display_list = []

    for p in parsed:
        real_id = p["parsed_id"]
        if real_id in batch_map:
            q = batch_map[real_id].copy()
            correct_letter = CORRECT_MAP.get(q["correct_idx"], "A")
            q["status"] = "PASSED" if p["val"] == [correct_letter] else "PENDING_FIX"
            q["student_choices"] = p["val"]
            q["student_reason"] = p["reason"]
            q.pop("fixer_hint", None)
            updates[q["id"]] = q
            if request.get("verbose"):
                display_list.append(
                    {
                        "id": q["id"],
                        "level": q["level"],
                        "reason": p["reason"],
                        "val": p["val"],
                        "correct_letter": correct_letter,
                        "is_student": True,
                    }
                )

    for q in batch:
        if q["id"] not in updates:
            q_copy = q.copy()
            q_copy["status"] = "PENDING_FIX"
            q_copy.pop("fixer_hint", None)
            updates[q["id"]] = q_copy

    if request.get("verbose"):
        _print_parsed_questions(
            display_list, "Student Solving Results", border_style="magenta"
        )

    return {"questions": updates, "cost": _extract_cost(resp.response_metadata)}


def fixer_node(request: dict, llm) -> Dict:
    batch = request["batch"]
    batch.sort(key=lambda x: (x["level"], x["id"]))

    lines = []
    for q in batch:
        lines.append(f"ID: {q['id']}\nLevel: {q['level']}\nQuestion: {q['question']}")
        for j, opt in enumerate(q["options"]):
            lines.append(f"{chr(65+j)}: {opt}")
        lines.append(f"Answer: {CORRECT_MAP.get(q['correct_idx'], 'A')}")
        lines.append(f"Student Choices: {', '.join(q.get('student_choices', []))}")
        lines.append(f"Student Reason: {q.get('student_reason', 'N/A')}\n")

    prompt = (
        load_prompt("fixer", "prompts/v5")
        .replace("{content}", request["content"])
        .replace("{failed_questions}", "\n".join(lines))
    )
    resp = llm.invoke(prompt)
    fixed_map = parse_option_fixer_output(resp.content)

    updates = {}
    display_list = []

    for q in batch:
        q_copy = q.copy()
        q_copy["fix_count"] = q_copy.get("fix_count", 0) + 1
        real_id = q_copy["id"]

        if real_id in fixed_map:
            fix = fixed_map[real_id]
            q_copy["status"] = "PENDING_STUDENT"
            q_copy["options"] = fix["options"]
            q_copy["correct_idx"] = fix["correct_idx"]
            q_copy["reason"] = fix.get("reason") or q_copy.get("reason")
            if request.get("verbose"):
                display_list.append(
                    {
                        "id": real_id,
                        "level": q["level"],
                        "question": q["question"],
                        "options": fix["options"],
                        "correct_idx": fix["correct_idx"],
                        "reason": fix["reason"],
                    }
                )
        else:
            q_copy["status"] = "PENDING_FIX"

        updates[q_copy["id"]] = q_copy

    if request.get("verbose"):
        _print_parsed_questions(
            display_list, "Fixer Resolutions", border_style="yellow"
        )

    return {"questions": updates, "cost": _extract_cost(resp.response_metadata)}


# ---------------------------------------------------------------------------
# Hub Routing & Execution Management
# ---------------------------------------------------------------------------
def _print_status_table(
    qs: Dict,
    max_loops: int,
    gen_counts: Dict[int, int],
    n: int,
    stem_retries: int = 0,
):
    """Rich UI Helper: Renders the processing matrix with Phase 1/2 retry counters.

    STEM_FAILED is computed as remainder (N - others) per level so every column
    always sums to exactly N and the grand total is always 3*N.
    """
    curr_p1 = max(stem_retries, 0)
    curr_p2 = max((q.get("fix_count", 0) for q in qs.values()), default=0)

    table_title = (
        f"🚀 Processing Matrix | "
        f"Phase 1 (Stem): [bold yellow]{curr_p1}/{max_loops}[/bold yellow] | "
        f"Phase 2 (Option): [bold green]{curr_p2}/{max_loops}[/bold green]"
    )

    table = Table(title=table_title, box=box.ROUNDED, expand=True)
    table.add_column("Phase", style="cyan", justify="left")
    table.add_column("Level 1", justify="center")
    table.add_column("Level 2", justify="center")
    table.add_column("Level 3", justify="center")
    table.add_column("Total", style="bold magenta", justify="center")

    stats = {
        "PASSED": {1: 0, 2: 0, 3: 0},
        "PENDING_CLASSIFY": {1: 0, 2: 0, 3: 0},
        "PENDING_STUDENT": {1: 0, 2: 0, 3: 0},
        "PENDING_FIX": {1: 0, 2: 0, 3: 0},
    }

    for q in qs.values():
        lvl = q.get("level", 1)
        st = q["status"]
        if st in stats and lvl in stats[st]:
            stats[st][lvl] += 1

    stem_failed_display = {1: 0, 2: 0, 3: 0}
    for lvl in [1, 2, 3]:
        other = (
            gen_counts[lvl]
            + stats["PENDING_CLASSIFY"][lvl]
            + stats["PENDING_STUDENT"][lvl]
            + stats["PENDING_FIX"][lvl]
            + stats["PASSED"][lvl]
        )
        stem_failed_display[lvl] = max(0, n - other)

    fmt = lambda d: f"{sum(d.values())}"

    table.add_row(
        "⚙️  Generate",
        f"[yellow]{gen_counts[1]}[/yellow]",
        f"[yellow]{gen_counts[2]}[/yellow]",
        f"[yellow]{gen_counts[3]}[/yellow]",
        f"[bold yellow]{sum(gen_counts.values())}[/bold yellow]",
    )
    table.add_row(
        "❌ Stem Failed",
        f"[red]{stem_failed_display[1]}[/red]",
        f"[red]{stem_failed_display[2]}[/red]",
        f"[red]{stem_failed_display[3]}[/red]",
        f"[bold red]{fmt(stem_failed_display)}[/bold red]",
    )
    table.add_row(
        "⏳ Classify",
        f"{stats['PENDING_CLASSIFY'][1]}",
        f"{stats['PENDING_CLASSIFY'][2]}",
        f"{stats['PENDING_CLASSIFY'][3]}",
        fmt(stats["PENDING_CLASSIFY"]),
    )
    table.add_row(
        "⏳ Solve",
        f"{stats['PENDING_STUDENT'][1]}",
        f"{stats['PENDING_STUDENT'][2]}",
        f"{stats['PENDING_STUDENT'][3]}",
        fmt(stats["PENDING_STUDENT"]),
    )
    table.add_row(
        "🔧 Fixer",
        f"{stats['PENDING_FIX'][1]}",
        f"{stats['PENDING_FIX'][2]}",
        f"{stats['PENDING_FIX'][3]}",
        fmt(stats["PENDING_FIX"]),
    )
    table.add_row(
        "✅ Passed",
        f"{stats['PASSED'][1]}",
        f"{stats['PASSED'][2]}",
        f"{stats['PASSED'][3]}",
        fmt(stats["PASSED"]),
    )

    console.print(table)


def controller_node(state: WorkflowState) -> Dict:
    qs = state.get("questions", {})
    loop = state.get("loop_count", 0) + 1
    next_id = state.get("next_global_id", 1)
    stem_retries = state.get("stem_retries", -1)
    n = state["n"]

    updates = {}
    for q_id, q in qs.items():
        st = q["status"]
        changed = False

        if st == "STEM_FAILED" and q.get("gen_loop", 0) >= state["max_loops"] - 1:
            q["status"] = "PENDING_STUDENT"
            q.setdefault("flags", []).append("stem_forced")
            changed = True

        if st == "PENDING_FIX" and q.get("fix_count", 0) >= state["max_loops"]:
            q["status"] = "PASSED"
            q.setdefault("flags", []).append("option_forced")
            changed = True

        if changed:
            updates[q_id] = q

    if updates:
        qs = {**qs, **updates}

    valid = {1: 0, 2: 0, 3: 0}
    positive_samples = {1: [], 2: [], 3: []}
    negative_samples = {1: [], 2: [], 3: []}
    queues = {"classify": [], "student": [], "fixer": []}

    for q in qs.values():
        st, lvl = q["status"], q["level"]
        if st != "STEM_FAILED":
            valid[lvl] += 1
            positive_samples[lvl].append(f"- {q['question']}")
        else:
            if "predicted_level" in q and q["predicted_level"] != lvl:
                 negative_samples[lvl].append(f"- {q['question']}")
                 
        if st == "PENDING_CLASSIFY":
            queues["classify"].append(q)
        elif st == "PENDING_STUDENT":
            queues["student"].append(q)
        elif st == "PENDING_FIX":
            queues["fixer"].append(q)

    gen_counts = {1: 0, 2: 0, 3: 0}
    gen_tasks = []

    for lvl in [1, 2, 3]:
        need = n - valid[lvl]
        if need > 0:
            gen_counts[lvl] = need

    if any(v > 0 for v in gen_counts.values()):
        stem_retries += 1
        for lvl in [1, 2, 3]:
            if gen_counts[lvl] > 0:
                pos_samples_text = "\n".join(random.sample(positive_samples[lvl], min(5, len(positive_samples[lvl])))) if positive_samples[lvl] else "(none yet)"
                neg_samples_text = "\n".join(negative_samples[lvl]) if negative_samples[lvl] else "(none yet)"
                
                gen_tasks.append(
                    {
                        "level": lvl,
                        "count": gen_counts[lvl],
                        "content": state["content"],
                        "positive_samples": pos_samples_text,
                        "negative_samples": neg_samples_text,
                        "start_id": next_id,
                        "verbose": state["verbose"],
                        "gen_loop": state.get("loop_count", 0),
                    }
                )
                next_id += gen_counts[lvl]

    if state.get("verbose"):
        _print_status_table(qs, state["max_loops"], gen_counts, n, stem_retries)

    return {
        "questions": updates,
        "loop_count": loop,
        "stem_retries": stem_retries,
        "next_global_id": next_id,
        "gen_tasks": gen_tasks,
        "classify_queue": queues["classify"],
        "student_queue": queues["student"],
        "fixer_queue": queues["fixer"],
    }


def dispatch_edges(state: WorkflowState) -> List[Send]:
    tasks = []
    for task in state.get("gen_tasks", []):
        tasks.append(Send("generator", task))

    if state.get("classify_queue"):
        tasks.append(
            Send(
                "classifier",
                {
                    "batch": state["classify_queue"],
                    "content": state["content"],
                    "verbose": state["verbose"],
                },
            )
        )
    if state.get("student_queue"):
        tasks.append(
            Send(
                "student",
                {
                    "batch": state["student_queue"],
                    "content": state["content"],
                    "verbose": state["verbose"],
                },
            )
        )
    if state.get("fixer_queue"):
        tasks.append(
            Send(
                "fixer",
                {
                    "batch": state["fixer_queue"],
                    "content": state["content"],
                    "verbose": state["verbose"],
                },
            )
        )

    return tasks if tasks else ["merge"]


def merge_node(state: WorkflowState) -> Dict:
    n = state["n"]
    qs = state.get("questions", {})

    by_level: Dict[int, List[Dict]] = {1: [], 2: [], 3: []}
    for q in sorted(qs.values(), key=lambda x: x.get("id", 0)):
        if q["status"] == "PASSED":
            by_level.setdefault(q["level"], []).append(q)

    final_questions = []
    for lvl in [1, 2, 3]:
        for q in by_level[lvl][:n]:
            final_questions.append(
                {
                    "id": q["id"],
                    "content": q["question"],
                    "options": q["options"],
                    "correct": q["correct_idx"],
                    "level": lvl,
                    "flags": q.get("flags", []),
                }
            )

    flagged = [q for q in final_questions if q["flags"]]
    if flagged:
        lines = [
            f"Q{q['id']} (L{q['level']}): {', '.join(q['flags'])}" for q in flagged
        ]
        console.print(
            Panel("\n".join(lines), title="Flagged Questions", border_style="yellow")
        )

    console.print(
        Panel(
            Text.assemble(
                ("Output: ", "bold"),
                (f"{len(final_questions)}\n", "green"),
                ("Flagged: ", "bold"),
                (f"{len(flagged)}\n", "yellow" if flagged else "green"),
                ("Cost: ", "bold"),
                (f"${state.get('cost', 0):.4f}", "yellow"),
            ),
            title=f"Done [{state['item_id']}]",
            border_style="green",
        )
    )
    return {"final_questions": final_questions}


# ---------------------------------------------------------------------------
# Pipeline Constructor
# ---------------------------------------------------------------------------
def build_workflow(llm, student_llm):
    workflow = StateGraph(WorkflowState)
    workflow.add_node("controller", controller_node)
    workflow.add_node("generator", lambda req: generator_node(req, llm))
    workflow.add_node("classifier", lambda req: classifier_node(req, llm))
    workflow.add_node("student", lambda req: student_node(req, student_llm))
    workflow.add_node("fixer", lambda req: fixer_node(req, llm))
    workflow.add_node("merge", merge_node)

    workflow.set_entry_point("controller")
    workflow.add_conditional_edges(
        "controller",
        dispatch_edges,
        ["generator", "classifier", "student", "fixer", "merge"],
    )

    for node in ["generator", "classifier", "student", "fixer"]:
        workflow.add_edge(node, "controller")

    workflow.add_edge("merge", END)
    return workflow.compile()


def process_item(item: Dict, n: int, workflow, max_loops: int, verbose: bool) -> Dict:
    item_id = item["id"]

    console.print(
        f"\n[bold black on white] STARTING ITEM: {item_id} [/bold black on white]"
    )

    init_state = {
        "item_id": item_id,
        "content": item["content"],
        "n": n,
        "max_loops": max_loops,
        "verbose": verbose,
        "questions": {},
        "next_global_id": 1,
        "cost": 0.0,
        "loop_count": 0,
        "stem_retries": -1,
    }

    try:
        final_state = workflow.invoke(init_state, {"recursion_limit": 100})
        return {
            "id": item_id,
            "cost": final_state.get("cost", 0.0),
            "generated_questions": final_state.get("final_questions", []),
        }
    except Exception as e:
        console.print(f"[bold red]❌ Critical Failure on {item_id}: {e}[/bold red]")
        traceback.print_exc()
        return {"id": item_id, "cost": 0.0, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="DCP v5 — Optimized LangGraph Pipeline"
    )
    parser.add_argument("--model", type=str, default="google/gemma-3-12b-it")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--max-loops", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sources", type=str, nargs="+", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY must not be empty!")

    llm = ChatOpenAI(
        model=args.model,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
        max_tokens=8192,
        extra_body={
            "reasoning": {"effort": "none"},
            "provider": {"sort": "price"},
        },
    )

    student_llm = ChatOpenAI(
        model=args.model,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.3,
        max_tokens=8192,
        extra_body={
            "reasoning": {"effort": "none"},
            "provider": {"sort": "price"},
        },
    )

    workflow = build_workflow(llm, student_llm)

    try:
        grouped = load_data(args.sources, args.limit)
    except FileNotFoundError:
        console.print(f"[bold red]Data file not found: {DATA_PATH}[/bold red]")
        return

    model_id = args.model.replace("/", "_")
    grand_total_cost = 0.0

    for source in args.sources:
        source_lower = source.lower()
        data = grouped.get(source_lower, [])
        console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
        console.print(
            f"[bold]Processing source:[/bold] {source.upper()} — {len(data)} items"
        )
        console.print(f"[bold cyan]{'='*80}[/bold cyan]")

        if not data:
            console.print(
                f"[yellow]Warning: No data found for source '{source}', skipping.[/yellow]"
            )
            continue

        output_dir = Path("outputs") / source_lower / (model_id + "-v5")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "predictions.json"

        results, source_cost = [], 0.0

        if args.workers == 1:
            for item in data:
                res = process_item(item, args.n, workflow, args.max_loops, args.verbose)
                results.append(res)
                source_cost += res.get("cost", 0.0)
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [
                    executor.submit(
                        process_item,
                        item,
                        args.n,
                        workflow,
                        args.max_loops,
                        args.verbose,
                    )
                    for item in data
                ]
                for future in as_completed(futures):
                    res = future.result()
                    results.append(res)
                    source_cost += res.get("cost", 0.0)

        results.sort(key=lambda x: x["id"])

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        grand_total_cost += source_cost
        successful = sum(1 for r in results if "error" not in r)
        total_questions = sum(
            len(r.get("generated_questions", [])) for r in results if "error" not in r
        )

        console.print(
            Panel(
                f"Successful: [green]{successful}/{len(data)}[/green]  |  "
                f"Questions generated: [cyan]{total_questions}[/cyan]  |  "
                f"Cost: [yellow]${source_cost:.4f}[/yellow]\n"
                f"Saved to: [bold]{output_path}[/bold]",
                title=f"[bold green]✅ {source.upper()} Complete[/bold green]",
                border_style="green",
            )
        )

    console.print(
        Panel(
            f"Total API cost: [bold yellow]${grand_total_cost:.4f}[/bold yellow]",
            title="[bold green]🎉 All Sources Complete[/bold green]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
