"""
eval.py — Compute Solvability & Alignment for generated questions.

A single LLM prompt acts as a student solving a shuffled multiple-select quiz
AND classifies each question's cognitive level (type).

Metrics
-------
  Solvability = 1  if the LLM's chosen answers exactly match the correct answer.
  Alignment   = 1  if the LLM's predicted type matches the ground-truth level.
"""

import argparse
import json
import os
import random
import re
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

load_dotenv()

console = Console()

# ---------------------------------------------------------------------------
# Global cost tracking (thread-safe)
# ---------------------------------------------------------------------------
_cost_lock = threading.Lock()
_total_cost = 0.0
_thread_local = threading.local()


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


def _add_cost(response) -> float:
    global _total_cost
    try:
        meta = getattr(response, "response_metadata", {}) or {}
        cost = _extract_cost(meta)
        if cost > 0:
            with _cost_lock:
                _total_cost += cost
            _thread_local.cost = getattr(_thread_local, "cost", 0.0) + cost
        return cost
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------
_prompt_cache: Dict[str, str] = {}


def load_prompt(path: str) -> str:
    if path not in _prompt_cache:
        _prompt_cache[path] = Path(path).read_text(encoding="utf-8")
    return _prompt_cache[path]


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def load_data(data_path: str) -> List[dict]:
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_predictions(predictions_path: str) -> List[dict]:
    with open(predictions_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Quiz formatting
# ---------------------------------------------------------------------------
CORRECT_MAP = {0: "A", 1: "B", 2: "C", 3: "D"}


def format_quiz(questions: List[Dict]) -> str:
    """Format a (pre-shuffled) list of questions for the eval prompt."""
    lines = []
    for q in questions:
        lines.append(f"ID: {q['eval_id']}")
        lines.append(f"Question: {q['content']}")
        for i, label in enumerate(["A", "B", "C", "D"]):
            lines.append(f"{label}: {q['options'][i]}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?m)^#{1,4}\s+", "", text)
    return text


def parse_eval_output(output: str) -> List[Dict]:
    """Parse LLM output → list of {id, predicted_type, choices}."""
    blocks = re.split(r"(?:^|\n)(?=ID:\s*\d+)", _normalize(output).strip())
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

            type_m = re.search(r"Type:\s*(\d+)", block, re.IGNORECASE)
            predicted_type = int(type_m.group(1)) if type_m else 0

            choices_m = re.search(r"Choices:\s*(.+)", block, re.IGNORECASE)
            choices_raw = choices_m.group(1).strip().upper() if choices_m else "NONE"
            choices = (
                []
                if choices_raw in ("NONE", "")
                else sorted(re.findall(r"[A-D]", choices_raw))
            )

            results.append(
                {"id": q_id, "predicted_type": predicted_type, "choices": choices}
            )
        except Exception as e:
            console.print(f"[yellow][warn][/yellow] Failed to parse block: {e}")
    return results


# ---------------------------------------------------------------------------
# Single-item evaluation
# ---------------------------------------------------------------------------
def evaluate_item(
    item_id: int,
    content: str,
    questions: List[Dict],
    model: str,
    api_key: str,
    api_base: str,
    prompt_template: str,
    max_retries: int = 3,
) -> Tuple[int, object, float]:
    _thread_local.cost = 0.0

    # Shuffle first, then assign sequential eval IDs 1→N
    # so LLM sees clean sequential IDs; map back via position in shuffled list
    shuffled = list(questions)
    random.shuffle(shuffled)
    indexed = [{**q, "eval_id": i + 1} for i, q in enumerate(shuffled)]

    full_prompt = prompt_template.replace("{content}", content).replace(
        "{quiz}", format_quiz(indexed)
    )

    llm_config: Dict[str, Any] = {
        "model": model,
        "openai_api_key": api_key,
        "openai_api_base": api_base,
        "temperature": 0.0,
        "max_tokens": 16384,  # allow for long outputs
        "extra_body": {"reasoning": {"effort": "none"}},
    }
    llm = ChatOpenAI(**llm_config)

    last_error: Exception = Exception("No attempts made")
    for attempt in range(max_retries):
        try:
            response = llm.invoke(full_prompt)
            _add_cost(response)
            output = str(response.content)

            if not output.strip():
                last_error = Exception("Empty LLM output")
                continue

            parsed = {p["id"]: p for p in parse_eval_output(output)}

            results = []
            for q in indexed:
                eid = q["eval_id"]
                p = parsed.get(eid, {})
                correct_letter = CORRECT_MAP.get(q["correct"], "A")
                student_choices = p.get("choices", [])
                predicted_type = p.get("predicted_type", 0)

                results.append(
                    {
                        "eval_id": eid,
                        "level": q["level"],
                        "question": q.get("content", ""),
                        "options": q.get("options", []),
                        "correct": correct_letter,
                        "student_choices": student_choices,
                        "predicted_type": predicted_type,
                        "solvability": 1 if student_choices == [correct_letter] else 0,
                        "alignment": 1 if predicted_type == q["level"] else 0,
                        "acceptance": 1 if student_choices == [correct_letter] and predicted_type == q["level"] else 0,
                    }
                )
            return (
                item_id,
                {"question_results": results, "raw_output": output},
                getattr(_thread_local, "cost", 0.0),
            )

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                console.print(
                    f"[yellow]Attempt {attempt + 1} failed for item {item_id}: {e}[/yellow]"
                )

    return (item_id, {"error": str(last_error)}, getattr(_thread_local, "cost", 0.0))


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def calculate_statistics(all_results: List[dict]) -> Dict:
    stats: Dict = {
        "overall": {
            "total_items": 0,
            "successful_items": 0,
            "failed_items": 0,
            "total_questions": 0,
            "solvability": 0.0,
            "alignment": 0.0,
            "acceptance": 0.0,
        },
        "by_level": {},
    }

    solv_all, align_all, acc_all = [], [], []
    level_solv: Dict[int, list] = {}
    level_align: Dict[int, list] = {}
    level_acc: Dict[int, list] = {}

    for item in all_results:
        stats["overall"]["total_items"] += 1
        if "error" in item:
            stats["overall"]["failed_items"] += 1
            continue
        stats["overall"]["successful_items"] += 1
        for qr in item.get("question_results", []):
            level = qr["level"]
            solv_all.append(qr["solvability"])
            align_all.append(qr["alignment"])
            acc_all.append(qr.get("acceptance", 0))
            level_solv.setdefault(level, []).append(qr["solvability"])
            level_align.setdefault(level, []).append(qr["alignment"])
            level_acc.setdefault(level, []).append(qr.get("acceptance", 0))

    stats["overall"]["total_questions"] = len(solv_all)
    if solv_all:
        stats["overall"]["solvability"] = round(sum(solv_all) / len(solv_all), 4)
    if align_all:
        stats["overall"]["alignment"] = round(sum(align_all) / len(align_all), 4)
    if acc_all:
        stats["overall"]["acceptance"] = round(sum(acc_all) / len(acc_all), 4)

    for level in sorted(set(list(level_solv) + list(level_align))):
        ls = level_solv.get(level, [])
        la = level_align.get(level, [])
        l_acc = level_acc.get(level, [])
        stats["by_level"][level] = {
            "count": len(ls),
            "solvability": round(sum(ls) / len(ls), 4) if ls else 0.0,
            "alignment": round(sum(la) / len(la), 4) if la else 0.0,
            "acceptance": round(sum(l_acc) / len(l_acc), 4) if l_acc else 0.0,
        }

    return stats


# ---------------------------------------------------------------------------
# Rich display helpers
# ---------------------------------------------------------------------------
def _print_verbose_results(all_results: List[dict]) -> None:
    """Print per-item detailed outputs showing questions, answers, and types."""
    for item in all_results:
        item_id = item["id"]
        if "error" in item:
            console.print(
                f"[bold red]Item {item_id}: ERROR — {item['error']}[/bold red]"
            )
            continue

        qrs = item.get("question_results", [])
        if not qrs:
            continue

        console.print(f"\n[bold cyan]=== Item {item_id} ===[/bold cyan]")

        for i, qr in enumerate(qrs, 1):
            solv_str = (
                "[green]Correct[/green]"
                if qr["solvability"]
                else "[red]Incorrect[/red]"
            )
            align_str = (
                "[green]Matched[/green]" if qr["alignment"] else "[red]Mismatched[/red]"
            )

            console.print(f"\n[bold]Question {i}:[/bold] {qr.get('question', '')}")

            opts = qr.get("options", [])
            for lbl, opt in zip(["A", "B", "C", "D"], opts):
                console.print(f"  {lbl}: {opt}")

            chosen = (
                ", ".join(qr["student_choices"]) if qr["student_choices"] else "None"
            )
            
            acc_str = "[green]Acc[/green]" if qr.get("acceptance", 0) else "[red]Rej[/red]"

            console.print(
                f"[bold]Output:[/bold] Correct: {qr['correct']} | Chosen: {chosen} -> {solv_str} | {acc_str}"
            )
            console.print(
                f"[bold]Type:[/bold] Ground Truth L{qr['level']} | Predicted L{qr['predicted_type']} -> {align_str}"
            )

        if item.get("raw_output"):
            console.print(
                f"\n[cyan]--- Judge Raw Text ---[/cyan]\n{item['raw_output']}\n"
            )


def _print_summary_table(stats: Dict, source: str, cost: float) -> None:
    table = Table(title=f"Results — {source.upper()}", show_lines=True)
    table.add_column("Level", style="cyan", justify="center")
    table.add_column("Questions", justify="right")
    table.add_column("Solvability", justify="right", style="green")
    table.add_column("Alignment", justify="right", style="yellow")
    table.add_column("Acceptance", justify="right", style="magenta")

    for level in sorted(stats["by_level"]):
        ls = stats["by_level"][level]
        table.add_row(
            f"L{level}",
            str(ls["count"]),
            f"{ls['solvability']:.4f}",
            f"{ls['alignment']:.4f}",
            f"{ls.get('acceptance', 0.0):.4f}",
        )

    ov = stats["overall"]
    table.add_row(
        "[bold]Overall[/bold]",
        f"[bold]{ov['total_questions']}[/bold]",
        f"[bold green]{ov['solvability']:.4f}[/bold green]",
        f"[bold yellow]{ov['alignment']:.4f}[/bold yellow]",
        f"[bold magenta]{ov.get('acceptance', 0.0):.4f}[/bold magenta]",
    )

    console.print(table)
    console.print(
        f"  [dim]Items: {ov['successful_items']}/{ov['total_items']} ok"
        f"  |  Failed: {ov['failed_items']}"
        f"  |  Cost: [bold magenta]${cost:.6f}[/bold magenta][/dim]"
    )


def _build_live_eval_renderable(
    source: str,
    progress: Progress,
    completed: float,
    total: int,
    running_solv: List[int],
    running_align: List[int],
    running_acc: List[int],
    recent_items: deque,
) -> Panel:
    metrics = Table.grid(expand=True)
    metrics.add_column(justify="left")
    metrics.add_column(justify="right")

    n_q = len(running_solv)
    solv = sum(running_solv) / n_q if n_q else 0.0
    align = sum(running_align) / n_q if n_q else 0.0
    acc = sum(running_acc) / n_q if n_q else 0.0

    metrics.add_row("Completed", f"[bold]{completed}[/bold]/{total}")
    metrics.add_row("Questions", f"[bold]{n_q}[/bold]")
    metrics.add_row("Solvability", f"[green]{solv:.4f}[/green]")
    metrics.add_row("Alignment", f"[yellow]{align:.4f}[/yellow]")
    metrics.add_row("Acceptance", f"[magenta]{acc:.4f}[/magenta]")

    recent_table = Table(title="Recent Items", expand=True, show_lines=True)
    recent_table.add_column("Item", width=8, justify="right")
    recent_table.add_column("Status", width=10, justify="center")
    recent_table.add_column("Solv", width=8, justify="right")
    recent_table.add_column("Align", width=8, justify="right")
    recent_table.add_column("Acc", width=8, justify="right")
    recent_table.add_column("Cost", width=12, justify="right")
    recent_table.add_column("Note", overflow="fold")

    if recent_items:
        for item in recent_items:
            recent_table.add_row(
                str(item["id"]),
                item["status"],
                item["solv"],
                item["align"],
                item["acc"],
                item["cost"],
                item["note"],
            )
    else:
        recent_table.add_row("—", "—", "—", "—", "—", "—", "Waiting for results...")

    live_table = Table.grid(expand=True)
    live_table.add_row(progress)
    live_table.add_row(Panel(metrics, title="Running Metrics", border_style="green"))
    live_table.add_row(recent_table)

    return Panel(
        live_table,
        title=f"[bold cyan]Live Eval — {source.upper()}[/bold cyan]",
        border_style="cyan",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Evaluate generated MCQs for solvability and alignment"
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Generation model ID whose predictions to evaluate "
        "(used to locate outputs/{source}/{model_id}/predictions.json)",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Judge LLM (defaults to --model if not specified)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=128,
        help="Parallel workers (default: 128)",
    )
    parser.add_argument(
        "--num-items",
        type=int,
        default=None,
        help="Only process the first N valid items",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="datasets/unified/data.json",
    )
    parser.add_argument(
        "--prompt-path",
        type=str,
        default="prompts/eval.md",
        help="Path to the eval prompt markdown file",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        required=True,
        help="Dataset source(s) to evaluate (e.g., race)",
    )
    parser.add_argument("--api-base", type=str, default="https://openrouter.ai/api/v1")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-item tables showing questions, answers, and types",
    )
    args = parser.parse_args()

    if args.num_items is not None and args.num_items <= 0:
        raise ValueError("--num-items must be > 0")

    judge_model = args.judge_model or args.model
    model_id = args.model.replace("/", "_")
    judge_model_id = judge_model.replace("/", "_")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set")

    console.print(f"[dim]Loading prompt  : {args.prompt_path}[/dim]")
    prompt_template = load_prompt(args.prompt_path)

    console.print(f"[dim]Loading data     : {args.data_path}[/dim]")
    data = load_data(args.data_path)
    data_dict = {item["id"]: item for item in data}

    console.print(
        Panel(
            f"[bold]Generation model:[/bold] {args.model}  [dim]({model_id})[/dim]\n"
            f"[bold]Judge model:      [/bold] {judge_model}  [dim]({judge_model_id})[/dim]\n"
            f"[bold]API base:         [/bold] {args.api_base}\n"
            f"[bold]Workers:          [/bold] {args.workers}\n"
            f"[bold]Sources:          [/bold] {', '.join(args.sources)}\n"
            f"[bold]Data items:       [/bold] {len(data)}",
            title="[bold cyan]Eval Config[/bold cyan]",
            border_style="cyan",
        )
    )

    for source in args.sources:
        source_lower = source.lower()
        console.print(f"\n[bold blue]{'=' * 80}[/bold blue]")
        console.print(f"[bold blue]  Source: {source.upper()}[/bold blue]")
        console.print(f"[bold blue]{'=' * 80}[/bold blue]")

        predictions_path = (
            Path("outputs") / source_lower / model_id / "predictions.json"
        )
        if not predictions_path.exists():
            console.print(
                f"[bold yellow]⚠  {predictions_path} not found, skipping...[/bold yellow]"
            )
            continue

        predictions = load_predictions(str(predictions_path))
        console.print(
            f"[dim]Loaded {len(predictions)} predictions from {predictions_path}[/dim]"
        )

        output_path = predictions_path.parent / "eval.json"

        # Filter valid predictions
        valid = []
        for pred in predictions:
            if "error" in pred or "generated_questions" not in pred:
                continue
            if pred["id"] not in data_dict:
                console.print(
                    f"[yellow]Warning: no data entry for ID {pred['id']}[/yellow]"
                )
                continue
            valid.append(pred)

        if args.num_items is not None:
            valid = valid[: args.num_items]
            console.print(
                f"[dim]Limiting to first {args.num_items} valid item(s) via --num-items[/dim]"
            )

        console.print(f"[dim]Valid jobs: {len(valid)}[/dim]")

        source_cost_start = _total_cost
        all_results = []
        _running_solv: list = []
        _running_align: list = []
        _running_acc: list = []
        recent_items = deque(maxlen=8)
        _lock = threading.Lock()

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            expand=True,
        )
        task_id = progress.add_task(f"Evaluating {source}", total=len(valid))

        def process_result(rid_res, qr_or_err_res, cost_res):
            if isinstance(qr_or_err_res, dict) and "error" in qr_or_err_res:
                all_results.append(
                    {"id": rid_res, "cost": cost_res, "error": qr_or_err_res["error"]}
                )
                recent_items.appendleft(
                    {
                        "id": rid_res,
                        "status": "[red]ERROR[/red]",
                        "solv": "—",
                        "align": "—",
                        "acc": "—",
                        "cost": f"${cost_res:.6f}",
                        "note": qr_or_err_res["error"],
                    }
                )
            else:
                qr_list = qr_or_err_res.get("question_results", [])
                raw_output = qr_or_err_res.get("raw_output", "")
                all_results.append(
                    {
                        "id": rid_res,
                        "cost": cost_res,
                        "question_results": qr_list,
                        "raw_output": raw_output,
                    }
                )
                item_solv = (
                    sum(qr["solvability"] for qr in qr_list) / len(qr_list)
                    if qr_list
                    else 0.0
                )
                item_align = (
                    sum(qr["alignment"] for qr in qr_list) / len(qr_list)
                    if qr_list
                    else 0.0
                )
                item_acc = (
                    sum(qr.get("acceptance", 0) for qr in qr_list) / len(qr_list)
                    if qr_list
                    else 0.0
                )
                with _lock:
                    for qr in qr_list:
                        _running_solv.append(qr["solvability"])
                        _running_align.append(qr["alignment"])
                        _running_acc.append(qr.get("acceptance", 0))
                recent_items.appendleft(
                    {
                        "id": rid_res,
                        "status": "[green]OK[/green]",
                        "solv": f"{item_solv:.2f}",
                        "align": f"{item_align:.2f}",
                        "acc": f"{item_acc:.2f}",
                        "cost": f"${cost_res:.6f}",
                        "note": f"{len(qr_list)} questions",
                    }
                )

                if args.verbose:
                    with _lock:
                        _print_verbose_results(
                            [
                                {
                                    "id": rid_res,
                                    "question_results": qr_list,
                                    "raw_output": raw_output,
                                }
                            ]
                        )

            progress.advance(task_id)
            live.update(
                _build_live_eval_renderable(
                    source,
                    progress,
                    completed=progress.tasks[0].completed,
                    total=len(valid),
                    running_solv=_running_solv,
                    running_align=_running_align,
                    running_acc=_running_acc,
                    recent_items=recent_items,
                )
            )

        with Live(
            _build_live_eval_renderable(
                source,
                progress,
                completed=0,
                total=len(valid),
                running_solv=_running_solv,
                running_align=_running_align,
                running_acc=_running_acc,
                recent_items=recent_items,
            ),
            console=console,
            refresh_per_second=4,
        ) as live:
            if args.workers == 1:
                sorted_valid = sorted(valid, key=lambda x: x["id"])
                for pred in sorted_valid:
                    rid, qr_or_err, cost = evaluate_item(
                        pred["id"],
                        data_dict[pred["id"]]["content"],
                        pred["generated_questions"],
                        judge_model,
                        api_key,
                        args.api_base,
                        prompt_template,
                    )
                    process_result(rid, qr_or_err, cost)
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    future_map = {
                        executor.submit(
                            evaluate_item,
                            pred["id"],
                            data_dict[pred["id"]]["content"],
                            pred["generated_questions"],
                            judge_model,
                            api_key,
                            args.api_base,
                            prompt_template,
                        ): pred["id"]
                        for pred in valid
                    }
                    for future in as_completed(future_map):
                        rid, qr_or_err, cost = future.result()
                        process_result(rid, qr_or_err, cost)

        all_results.sort(key=lambda x: x["id"])
        stats = calculate_statistics(all_results)
        source_cost = _total_cost - source_cost_start

        output_data = {
            "metadata": {
                "predictions_path": str(predictions_path),
                "data_path": args.data_path,
                "prompt_path": args.prompt_path,
                "generation_model": args.model,
                "judge_model": judge_model,
                "api_base": args.api_base,
                "source": source,
            },
            "statistics": stats,
            "results": all_results,
        }

        console.print(f"\n[dim]Saving → {output_path}[/dim]")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        console.print(f"[bold green]✓ Saved {output_path}[/bold green]")

        _print_summary_table(stats, source, source_cost)

    console.print(
        Panel(
            f"Grand total cost: [bold magenta]${_total_cost:.6f}[/bold magenta]",
            title="[bold cyan]All Sources Complete[/bold cyan]",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
