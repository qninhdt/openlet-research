import json
import os
from pathlib import Path
from typing import List, Dict, Tuple
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import random

from langchain_openai import ChatOpenAI
from tqdm import tqdm

from dotenv import load_dotenv

load_dotenv()


def load_prompt(prompt_path: str = "prompts/macro_eval.md") -> str:
    """Load the macro evaluation prompt file

    Args:
        prompt_path: Path to the prompt file

    Returns:
        Prompt content as string
    """
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def load_data(data_path: str) -> List[dict]:
    """Load unified data from JSON file

    Args:
        data_path: Path to the data.json file

    Returns:
        List of data items
    """
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_predictions(predictions_path: str) -> List[dict]:
    """Load predictions from JSON file

    Args:
        predictions_path: Path to the predictions.json file

    Returns:
        List of prediction items
    """
    with open(predictions_path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_questions_for_comparison(questions: List[Dict]) -> str:
    """Format questions list into a string for comparison

    Args:
        questions: List of question dictionaries

    Returns:
        Formatted string representation of questions
    """
    lines = []
    for i, q in enumerate(questions, 1):
        lines.append(f"### Question {i}")
        lines.append(f"Level: {q.get('level', 'Unknown')}")
        lines.append(f"Question: {q['content']}")
        lines.append("Options:")
        for j, opt in enumerate(q["options"]):
            letter = chr(65 + j)  # A, B, C, D
            lines.append(f"  {letter}. {opt}")
        correct_letter = chr(65 + q["correct"])
        lines.append(f"Correct Answer: {correct_letter}")
        lines.append("")
    return "\n".join(lines)


def parse_macro_eval_output(output: str) -> Dict:
    """Parse macro evaluation output from LLM

    Expected format:
    # A
    - [analysis points]
    ...

    # B
    - [analysis points]
    ...

    # Conclusion
    - [conclusion points]
    ...

    # Result
    [0/1/2]

    Args:
        output: Raw LLM output text

    Returns:
        Dictionary with analysis and result
    """
    result_dict = {
        "analysis_a": [],
        "analysis_b": [],
        "conclusion": [],
        "result": None,  # 0: Tie, 1: Model A wins, 2: Model B wins
        "raw_output": output,
    }

    try:
        # Extract section A
        a_match = re.search(
            r"#\s*A\s*\n(.*?)(?=#\s*B|\Z)", output, re.IGNORECASE | re.DOTALL
        )
        if a_match:
            a_content = a_match.group(1).strip()
            # Extract bullet points
            bullets = re.findall(r"^\s*[-*]\s*(.+)$", a_content, re.MULTILINE)
            result_dict["analysis_a"] = [b.strip() for b in bullets]

        # Extract section B
        b_match = re.search(
            r"#\s*B\s*\n(.*?)(?=#\s*Conclusion|\Z)", output, re.IGNORECASE | re.DOTALL
        )
        if b_match:
            b_content = b_match.group(1).strip()
            bullets = re.findall(r"^\s*[-*]\s*(.+)$", b_content, re.MULTILINE)
            result_dict["analysis_b"] = [b.strip() for b in bullets]

        # Extract Conclusion
        conclusion_match = re.search(
            r"#\s*Conclusion\s*\n(.*?)(?=#\s*Result|\Z)",
            output,
            re.IGNORECASE | re.DOTALL,
        )
        if conclusion_match:
            conclusion_content = conclusion_match.group(1).strip()
            bullets = re.findall(r"^\s*[-*]\s*(.+)$", conclusion_content, re.MULTILINE)
            result_dict["conclusion"] = [b.strip() for b in bullets]

        # Extract Result (0, 1, or 2)
        result_match = re.search(
            r"#\s*Result\s*\n\s*(\d+)", output, re.IGNORECASE | re.DOTALL
        )
        if result_match:
            result_value = int(result_match.group(1).strip())
            if result_value in [0, 1, 2]:
                result_dict["result"] = result_value

    except Exception as e:
        print(f"Warning: Failed to parse macro eval output: {str(e)}")

    return result_dict


def compare_models(
    content: str,
    questions_a: List[Dict],
    questions_b: List[Dict],
    judge_model: str,
    prompt_template: str,
    openrouter_api_key: str,
    max_retries: int = 3,
) -> Dict:
    """Compare two models' outputs using judge LLM with position randomization

    Args:
        content: Source text content
        questions_a: List of questions from model A
        questions_b: List of questions from model B
        judge_model: Judge model ID to use
        prompt_template: Prompt template with placeholders
        openrouter_api_key: OpenRouter API key
        max_retries: Maximum number of retries

    Returns:
        Dictionary with comparison results (including position swap info)
    """
    # Initialize LLM
    llm = ChatOpenAI(
        model=judge_model,
        openai_api_key=openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
    )

    # Randomly swap positions to avoid position bias
    swap_positions = random.choice([True, False])
    
    if swap_positions:
        # Model A -> Position 2, Model B -> Position 1
        output_position_1 = format_questions_for_comparison(questions_b)
        output_position_2 = format_questions_for_comparison(questions_a)
    else:
        # Model A -> Position 1, Model B -> Position 2
        output_position_1 = format_questions_for_comparison(questions_a)
        output_position_2 = format_questions_for_comparison(questions_b)

    # Create full prompt
    full_prompt = (
        prompt_template.replace("{content}", content)
        .replace("{output_model_a}", output_position_1)
        .replace("{output_model_b}", output_position_2)
    )

    # Retry loop
    last_error = None
    for attempt in range(max_retries):
        try:
            # Generate comparison
            response = llm.invoke(full_prompt)
            output = response.content

            print(output)

            # Check if output is empty
            if not output.strip():
                print(f"Warning: LLM returned empty output")
                return {"error": "Empty output", "position_swapped": swap_positions}

            # Parse output
            comparison = parse_macro_eval_output(output)
            
            # Adjust result if positions were swapped
            # If swapped: Judge's 1 means Model B wins, 2 means Model A wins
            # We need to flip back to original: 1 = Model A, 2 = Model B
            if swap_positions and comparison.get("result") is not None:
                original_result = comparison["result"]
                if original_result == 1:
                    comparison["result"] = 2  # Judge said position 1 wins -> Model B wins
                elif original_result == 2:
                    comparison["result"] = 1  # Judge said position 2 wins -> Model A wins
                # result == 0 (tie) stays the same
            
            # Add metadata about position swap
            comparison["position_swapped"] = swap_positions

            return comparison

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {str(e)}, retrying...")
                continue
            else:
                raise Exception(
                    f"Failed after {max_retries} attempts. Last error: {str(e)}"
                )

    raise Exception(f"Unexpected failure: {str(last_error)}")


def print_comparison_result(item_id: str, comparison: Dict, model_a_id: str, model_b_id: str) -> None:
    """Print comparison result for a sample

    Args:
        item_id: Item ID
        comparison: Comparison result dictionary
        model_a_id: Model A identifier
        model_b_id: Model B identifier
    """
    print(f"\n{'='*80}")
    print(f"Sample ID: {item_id}")
    print(f"{'='*80}")

    result_value = comparison.get("result")
    if result_value == 0:
        result_str = "TIE"
    elif result_value == 1:
        result_str = f"Model A ({model_a_id}) WINS"
    elif result_value == 2:
        result_str = f"Model B ({model_b_id}) WINS"
    else:
        result_str = "INVALID RESULT"

    print(f"Result: {result_str}")
    print(f"{'='*80}\n")


def process_single_comparison(
    item_id: str,
    content: str,
    questions_a: List[Dict],
    questions_b: List[Dict],
    judge_model: str,
    prompt: str,
    api_key: str,
    model_a_id: str,
    model_b_id: str,
) -> Tuple[str, any]:
    """Process a single comparison job

    Args:
        item_id: Item ID
        content: Source text content
        questions_a: List of questions from model A
        questions_b: List of questions from model B
        judge_model: Judge model ID to use
        prompt: Prompt template string
        api_key: OpenRouter API key
        model_a_id: Model A identifier
        model_b_id: Model B identifier

    Returns:
        Tuple of (item_id, comparison or error_dict)
    """
    try:
        result = compare_models(
            content=content,
            questions_a=questions_a,
            questions_b=questions_b,
            judge_model=judge_model,
            prompt_template=prompt,
            openrouter_api_key=api_key,
        )

        # Print comparison result
        if result and isinstance(result, dict) and "result" in result:
            print_comparison_result(item_id, result, model_a_id, model_b_id)

        return (item_id, result)

    except Exception as e:
        return (item_id, {"error": str(e)})


def calculate_statistics(comparison_results: List[dict]) -> Dict:
    """Calculate statistics from comparison results

    Args:
        comparison_results: List of comparison result items

    Returns:
        Dictionary with statistics
    """
    stats = {
        "total_items": len(comparison_results),
        "successful_comparisons": 0,
        "failed_comparisons": 0,
        "model_a_wins": 0,
        "model_b_wins": 0,
        "ties": 0,
        "invalid_results": 0,
    }

    for item in comparison_results:
        if "error" in item:
            stats["failed_comparisons"] += 1
            continue

        stats["successful_comparisons"] += 1

        if "comparison" in item:
            result = item["comparison"].get("result")
            if result == 0:
                stats["ties"] += 1
            elif result == 1:
                stats["model_a_wins"] += 1
            elif result == 2:
                stats["model_b_wins"] += 1
            else:
                stats["invalid_results"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Compare two models' question generation using a judge LLM"
    )
    parser.add_argument(
        "--model-a",
        type=str,
        required=True,
        help="Model A ID (e.g., 'anthropic/claude-3.5-sonnet')",
    )
    parser.add_argument(
        "--model-b",
        type=str,
        required=True,
        help="Model B ID (e.g., 'openai/gpt-4o')",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="anthropic/claude-3.5-sonnet",
        help="Judge model ID to use for comparison (default: anthropic/claude-3.5-sonnet)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=128,
        help="Number of parallel workers (default: 128)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="datasets/unified/data.json",
        help="Path to the unified data.json file",
    )
    parser.add_argument(
        "--prompt-path",
        type=str,
        default="prompts/macro_eval.md",
        help="Path to the macro evaluation prompt file",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="Filter by source(s) (e.g., 'race', 'dream'). Default: all sources",
    )

    args = parser.parse_args()

    # Get model IDs
    model_a_id = args.model_a.replace("/", "_")
    model_b_id = args.model_b.replace("/", "_")
    judge_model_id = args.judge_model.replace("/", "_")

    # Validate sources parameter
    if not args.sources:
        raise ValueError(
            "Error: --sources parameter is required. Please specify which dataset(s) to compare.\n"
            "Example: --sources reclor, --sources race, or --sources race dream"
        )

    # Get API key from environment variable
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenRouter API key not found. Please set OPENROUTER_API_KEY environment variable"
        )

    # Load the evaluation prompt
    print(f"Loading prompt from {args.prompt_path}...")
    prompt = load_prompt(args.prompt_path)
    print(f"Prompt loaded successfully")

    # Load unified data
    print(f"Loading data from {args.data_path}...")
    data = load_data(args.data_path)
    data_dict = {item["id"]: item for item in data}
    print(f"Loaded {len(data)} items")

    print(f"\nModel A: {args.model_a} ({model_a_id})")
    print(f"Model B: {args.model_b} ({model_b_id})")
    print(f"Judge model: {args.judge_model} ({judge_model_id})")
    print(f"Using {args.workers} parallel workers")
    print(f"Processing sources: {', '.join(args.sources)}")

    # Process each source separately
    for source in args.sources:
        source_lower = source.lower()
        print(f"\n{'='*100}")
        print(f"Processing source: {source.upper()}")
        print(f"{'='*100}")

        # Construct predictions paths for both models
        predictions_a_path = (
            Path("outputs") / source_lower / model_a_id / "predictions.json"
        )
        predictions_b_path = (
            Path("outputs") / source_lower / model_b_id / "predictions.json"
        )

        if not predictions_a_path.exists():
            print(
                f"Warning: Model A predictions not found at {predictions_a_path}, skipping..."
            )
            continue

        if not predictions_b_path.exists():
            print(
                f"Warning: Model B predictions not found at {predictions_b_path}, skipping..."
            )
            continue

        # Load predictions for both models
        print(f"Loading Model A predictions from {predictions_a_path}...")
        predictions_a = load_predictions(str(predictions_a_path))
        predictions_a_dict = {p["id"]: p for p in predictions_a}
        print(f"Loaded {len(predictions_a)} Model A predictions")

        print(f"Loading Model B predictions from {predictions_b_path}...")
        predictions_b = load_predictions(str(predictions_b_path))
        predictions_b_dict = {p["id"]: p for p in predictions_b}
        print(f"Loaded {len(predictions_b)} Model B predictions")

        # Determine output path (in outputs/{source}/)
        output_dir = Path("outputs") / source_lower
        output_path = output_dir / f"macro_eval_{model_a_id}_vs_{model_b_id}.json"
        print(f"Output will be saved to: {output_path}")

        # Process items in parallel with multithreading
        job_results = []
        total_jobs = 0

        # Find common items (items that exist in both model outputs)
        common_ids = set()
        for item_id in predictions_a_dict.keys():
            if item_id in predictions_b_dict:
                # Check if both have valid questions
                pred_a = predictions_a_dict[item_id]
                pred_b = predictions_b_dict[item_id]

                if (
                    "error" not in pred_a
                    and "generated_questions" in pred_a
                    and "error" not in pred_b
                    and "generated_questions" in pred_b
                    and item_id in data_dict
                ):
                    common_ids.add(item_id)

        total_jobs = len(common_ids)
        print(f"Total comparisons to process: {total_jobs}")

        if total_jobs == 0:
            print("Warning: No common valid items found for comparison, skipping...")
            continue

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            # Submit all jobs
            future_to_job = {}
            for item_id in common_ids:
                content = data_dict[item_id]["content"]
                questions_a = predictions_a_dict[item_id]["generated_questions"]
                questions_b = predictions_b_dict[item_id]["generated_questions"]

                future = executor.submit(
                    process_single_comparison,
                    item_id,
                    content,
                    questions_a,
                    questions_b,
                    args.judge_model,
                    prompt,
                    api_key,
                    model_a_id,
                    model_b_id,
                )
                future_to_job[future] = item_id

            # Process completed jobs with progress bar
            with tqdm(
                total=total_jobs, desc=f"Comparing {source}", unit="item"
            ) as pbar:
                for future in as_completed(future_to_job):
                    item_id = future_to_job[future]
                    result = future.result()
                    job_results.append(result)

                    # Log errors without stopping progress bar
                    if (
                        len(result) == 2
                        and isinstance(result[1], dict)
                        and "error" in result[1]
                    ):
                        tqdm.write(f"✗ Error in item {item_id}: {result[1]['error']}")

                    pbar.update(1)

        # Build final comparison results
        comparison_results = []
        for item_id, comparison_or_error in job_results:
            if isinstance(comparison_or_error, dict) and "error" in comparison_or_error:
                comparison_results.append(
                    {
                        "id": item_id,
                        "source": data_dict[item_id].get("source", "unknown"),
                        "error": comparison_or_error["error"],
                    }
                )
            else:
                comparison_results.append(
                    {
                        "id": item_id,
                        "source": data_dict[item_id].get("source", "unknown"),
                        "comparison": comparison_or_error,
                    }
                )

        # Sort by ID
        comparison_results.sort(key=lambda x: x["id"])

        # Calculate statistics
        print("\nCalculating statistics...")
        stats = calculate_statistics(comparison_results)

        # Prepare final output
        output_data = {
            "metadata": {
                "model_a": args.model_a,
                "model_a_id": model_a_id,
                "model_b": args.model_b,
                "model_b_id": model_b_id,
                "judge_model": args.judge_model,
                "judge_model_id": judge_model_id,
                "data_path": args.data_path,
                "prompt_path": args.prompt_path,
                "source": source,
            },
            "statistics": stats,
            "results": comparison_results,
        }

        # Save comparison results
        print(f"\nSaving comparison results to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(
            f"✓ Done! Compared {total_jobs} items for {source}, saved to {output_path}"
        )

        # Print summary for this source
        print(f"\nSummary for {source}:")
        print(f"  Total items: {stats['total_items']}")
        print(f"  Successful comparisons: {stats['successful_comparisons']}")
        print(f"  Failed comparisons: {stats['failed_comparisons']}")
        print(
            f"  Model A wins: {stats['model_a_wins']} ({stats['model_a_wins']/max(stats['successful_comparisons'], 1)*100:.1f}%)"
        )
        print(
            f"  Model B wins: {stats['model_b_wins']} ({stats['model_b_wins']/max(stats['successful_comparisons'], 1)*100:.1f}%)"
        )
        print(
            f"  Ties: {stats['ties']} ({stats['ties']/max(stats['successful_comparisons'], 1)*100:.1f}%)"
        )
        if stats["invalid_results"] > 0:
            print(f"  Invalid results: {stats['invalid_results']}")

    print("\n" + "=" * 100)
    print("ALL SOURCES COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
