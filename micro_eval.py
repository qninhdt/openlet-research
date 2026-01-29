import json
import os
from pathlib import Path
from typing import List, Dict, Tuple
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from langchain_openai import ChatOpenAI
from tqdm import tqdm

from dotenv import load_dotenv

load_dotenv()


def load_prompt(prompt_path: str = "prompts/micro_eval.md") -> str:
    """Load the evaluation prompt file

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


def format_questions_for_eval(questions: List[Dict]) -> str:
    """Format questions list into a string for evaluation prompt

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


def parse_eval_output(output: str, num_questions: int) -> List[Dict]:
    """Parse evaluation output from LLM

    Expected format:
    ### Question [number]
    Level: [1-3]
    1. Solvability:
    - Reasoning: [text]
    - Score: [0 or 1]
    2. Distractor Quality:
    - Reasoning: [text]
    - Score: [1-5]
    3. Alignment:
    - Reasoning: [text]
    - Score: [0 or 1]

    Args:
        output: Raw LLM output text
        num_questions: Expected number of questions

    Returns:
        List of evaluation dictionaries
    """
    evaluations = []

    # Normalize ### markers
    normalized_output = re.sub(r"^#{1,4}\s+", "###", output, flags=re.MULTILINE)

    # Split by ### Question
    blocks = re.split(r"###\s*Question\s+(\d+)", normalized_output, flags=re.IGNORECASE)

    # blocks[0] is text before first question, then alternating question numbers and content
    for i in range(1, len(blocks), 2):
        if i + 1 >= len(blocks):
            break

        question_num = blocks[i].strip()
        content = blocks[i + 1].strip()

        try:
            # Parse Solvability
            solvability_reasoning = ""
            solvability_score = None

            # Find solvability section
            solvability_match = re.search(
                r"1\.\s*Solvability:?\s*\n\s*-\s*Reasoning:?\s*(.+?)\n\s*-\s*Score:?\s*(\d+)",
                content,
                re.IGNORECASE | re.DOTALL,
            )
            if solvability_match:
                solvability_reasoning = solvability_match.group(1).strip()
                solvability_score = int(solvability_match.group(2))

            # Parse Distractor Quality
            distractor_reasoning = ""
            distractor_score = None

            distractor_match = re.search(
                r"2\.\s*Distractor Quality:?\s*\n\s*-\s*Reasoning:?\s*(.+?)\n\s*-\s*Score:?\s*(\d+)",
                content,
                re.IGNORECASE | re.DOTALL,
            )
            if distractor_match:
                distractor_reasoning = distractor_match.group(1).strip()
                distractor_score = int(distractor_match.group(2))

            # Parse Alignment
            alignment_reasoning = ""
            alignment_score = None

            alignment_match = re.search(
                r"3\.\s*Alignment:?\s*\n\s*-\s*Reasoning:?\s*(.+?)\n\s*-\s*Score:?\s*(\d+)",
                content,
                re.IGNORECASE | re.DOTALL,
            )
            if alignment_match:
                alignment_reasoning = alignment_match.group(1).strip()
                alignment_score = int(alignment_match.group(2))

            # Only add if we have at least some valid data
            if any(
                [
                    solvability_score is not None,
                    distractor_score is not None,
                    alignment_score is not None,
                ]
            ):
                evaluations.append(
                    {
                        "question_number": int(question_num),
                        "solvability": {
                            "reasoning": solvability_reasoning,
                            "score": solvability_score,
                        },
                        "distractor_quality": {
                            "reasoning": distractor_reasoning,
                            "score": distractor_score,
                        },
                        "alignment": {
                            "reasoning": alignment_reasoning,
                            "score": alignment_score,
                        },
                    }
                )

        except Exception as e:
            print(f"Warning: Failed to parse question {question_num}: {str(e)}")
            continue

    return evaluations


def evaluate_questions(
    content: str,
    questions: List[Dict],
    model: str,
    prompt_template: str,
    openrouter_api_key: str,
    max_retries: int = 3,
) -> List[Dict]:
    """Evaluate questions using LLM

    Args:
        content: Source text content
        questions: List of generated questions
        model: Model ID to use
        prompt_template: Prompt template with {content} and {questions} placeholders
        openrouter_api_key: OpenRouter API key
        max_retries: Maximum number of retries

    Returns:
        List of evaluation dictionaries
    """
    # Initialize LLM
    llm = ChatOpenAI(
        model=model,
        openai_api_key=openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
    )

    # Format questions for prompt
    questions_text = format_questions_for_eval(questions)

    # Create full prompt
    full_prompt = prompt_template.replace("{content}", content).replace(
        "{questions}", questions_text
    )

    # Retry loop
    last_error = None
    for attempt in range(max_retries):
        try:
            # Generate evaluation
            response = llm.invoke(full_prompt)
            output = response.content

            print(output)

            # Check if output is empty
            if not output.strip():
                print(f"Warning: LLM returned empty output")
                return []

            # Parse output
            evaluations = parse_eval_output(output, len(questions))

            return evaluations

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


def print_sample_scores(item_id: str, evaluations: List[Dict]) -> None:
    """Print detailed scores for a sample

    Args:
        item_id: Item ID
        evaluations: List of evaluation dictionaries
    """
    print(f"\n{'='*80}")
    print(f"Sample ID: {item_id}")
    print(f"{'='*80}")

    for eval_item in evaluations:
        q_num = eval_item.get("question_number", "?")
        level = eval_item.get("level", "?")

        solv_score = eval_item.get("solvability", {}).get("score", "N/A")
        dist_score = eval_item.get("distractor_quality", {}).get("score", "N/A")
        align_score = eval_item.get("alignment", {}).get("score", "N/A")

        print(
            f"  Q{q_num} (L{level}): Solvability={solv_score}, Distractor={dist_score}, Alignment={align_score}"
        )

    print(f"{'='*80}\n")


def process_single_job(
    item_id: str,
    content: str,
    questions: List[Dict],
    model: str,
    prompt: str,
    api_key: str,
) -> Tuple[str, any]:
    """Process a single evaluation job

    Args:
        item_id: Item ID
        content: Source text content
        questions: List of questions to evaluate
        model: Model ID to use
        prompt: Prompt template string
        api_key: OpenRouter API key

    Returns:
        Tuple of (item_id, evaluations or error_dict)
    """
    try:
        result = evaluate_questions(
            content=content,
            questions=questions,
            model=model,
            prompt_template=prompt,
            openrouter_api_key=api_key,
        )

        # Add level information to each evaluation based on original question
        # Match evaluation to question by question_number
        if result and isinstance(result, list):
            for eval_item in result:
                q_num = eval_item.get("question_number")
                if q_num and q_num <= len(questions):
                    # Get level from original question (1-indexed)
                    eval_item["level"] = questions[q_num - 1].get("level")

            print_sample_scores(item_id, result)

        return (item_id, result)

    except Exception as e:
        return (item_id, {"error": str(e)})


def calculate_statistics(eval_results: List[dict]) -> Dict:
    """Calculate statistics from evaluation results

    Args:
        eval_results: List of evaluation result items

    Returns:
        Dictionary with statistics
    """
    stats = {
        "overall": {
            "total_items": len(eval_results),
            "successful_items": 0,
            "failed_items": 0,
            "total_questions": 0,
        },
        "by_level": {
            1: {
                "count": 0,
                "solvability": [],
                "distractor_quality": [],
                "alignment": [],
            },
            2: {
                "count": 0,
                "solvability": [],
                "distractor_quality": [],
                "alignment": [],
            },
            3: {
                "count": 0,
                "solvability": [],
                "distractor_quality": [],
                "alignment": [],
            },
        },
        "averages": {"overall": {}, "by_level": {}},
    }

    for item in eval_results:
        if "error" in item:
            stats["overall"]["failed_items"] += 1
            continue

        stats["overall"]["successful_items"] += 1

        if "evaluations" in item:
            for eval_item in item["evaluations"]:
                level = eval_item.get("level")
                if level not in [1, 2, 3]:
                    continue

                stats["overall"]["total_questions"] += 1
                stats["by_level"][level]["count"] += 1

                # Collect scores
                if eval_item.get("solvability", {}).get("score") is not None:
                    stats["by_level"][level]["solvability"].append(
                        eval_item["solvability"]["score"]
                    )

                if eval_item.get("distractor_quality", {}).get("score") is not None:
                    stats["by_level"][level]["distractor_quality"].append(
                        eval_item["distractor_quality"]["score"]
                    )

                if eval_item.get("alignment", {}).get("score") is not None:
                    stats["by_level"][level]["alignment"].append(
                        eval_item["alignment"]["score"]
                    )

    # Calculate averages
    all_solvability = []
    all_distractor = []
    all_alignment = []

    for level in [1, 2, 3]:
        level_data = stats["by_level"][level]
        level_stats = {}

        if level_data["solvability"]:
            avg = sum(level_data["solvability"]) / len(level_data["solvability"])
            level_stats["solvability"] = round(avg, 3)
            all_solvability.extend(level_data["solvability"])

        if level_data["distractor_quality"]:
            avg = sum(level_data["distractor_quality"]) / len(
                level_data["distractor_quality"]
            )
            level_stats["distractor_quality"] = round(avg, 3)
            all_distractor.extend(level_data["distractor_quality"])

        if level_data["alignment"]:
            avg = sum(level_data["alignment"]) / len(level_data["alignment"])
            level_stats["alignment"] = round(avg, 3)
            all_alignment.extend(level_data["alignment"])

        stats["averages"]["by_level"][level] = level_stats

    # Overall averages
    if all_solvability:
        stats["averages"]["overall"]["solvability"] = round(
            sum(all_solvability) / len(all_solvability), 3
        )

    if all_distractor:
        stats["averages"]["overall"]["distractor_quality"] = round(
            sum(all_distractor) / len(all_distractor), 3
        )

    if all_alignment:
        stats["averages"]["overall"]["alignment"] = round(
            sum(all_alignment) / len(all_alignment), 3
        )

    # Remove raw score lists (keep only averages)
    for level in [1, 2, 3]:
        del stats["by_level"][level]["solvability"]
        del stats["by_level"][level]["distractor_quality"]
        del stats["by_level"][level]["alignment"]

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate generated multiple-choice questions using LLMs"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="anthropic/claude-3.5-sonnet",
        help="Model ID to use for evaluation (e.g., 'anthropic/claude-3.5-sonnet', 'openai/gpt-4')",
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
        default="prompts/micro_eval.md",
        help="Path to the evaluation prompt file",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Judge model ID to use for evaluation (defaults to --model if not specified)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="Filter by source(s) (e.g., 'race', 'dream'). Default: all sources",
    )

    args = parser.parse_args()

    # Set judge model (defaults to main model if not specified)
    judge_model = args.judge_model if args.judge_model else args.model
    judge_model_id = judge_model.replace("/", "_")

    # Get model_id from model name
    model_id = args.model.replace("/", "_")

    # Validate sources parameter
    if not args.sources:
        raise ValueError(
            "Error: --sources parameter is required. Please specify which dataset(s) to evaluate.\n"
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

    print(f"\nQuestion generation model: {args.model}")
    print(f"Model ID: {model_id}")
    print(f"Judge model: {judge_model}")
    print(f"Judge model ID: {judge_model_id}")
    print(f"Using {args.workers} parallel workers")
    print(f"Processing sources: {', '.join(args.sources)}")

    # Process each source separately
    for source in args.sources:
        source_lower = source.lower()
        print(f"\n{'='*100}")
        print(f"Processing source: {source.upper()}")
        print(f"{'='*100}")

        # Construct predictions path: outputs/{source}/{model_id}/predictions.json
        predictions_path = (
            Path("outputs") / source_lower / model_id / "predictions.json"
        )

        if not predictions_path.exists():
            print(
                f"Warning: Predictions file not found at {predictions_path}, skipping..."
            )
            continue

        # Load predictions for this source
        print(f"Loading predictions from {predictions_path}...")
        predictions = load_predictions(str(predictions_path))
        print(f"Loaded {len(predictions)} predictions")

        # Determine output path (same directory as predictions.json)
        output_path = predictions_path.parent / "eval.json"
        print(f"Output will be saved to: {output_path}")

        # Process items in parallel with multithreading
        job_results = []
        total_jobs = 0

        # Count valid jobs (predictions with questions and matching data)
        valid_predictions = []
        for pred in predictions:
            if "error" in pred or "generated_questions" not in pred:
                continue
            if pred["id"] not in data_dict:
                print(f"Warning: No matching data found for prediction ID {pred['id']}")
                continue
            valid_predictions.append(pred)

        total_jobs = len(valid_predictions)
        print(f"Total jobs to process: {total_jobs}")

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            # Submit all jobs
            future_to_job = {}
            for pred in valid_predictions:
                item_id = pred["id"]
                content = data_dict[item_id]["content"]
                questions = pred["generated_questions"]

                future = executor.submit(
                    process_single_job,
                    item_id,
                    content,
                    questions,
                    judge_model,
                    prompt,
                    api_key,
                )
                future_to_job[future] = item_id

            # Process completed jobs with progress bar
            with tqdm(
                total=total_jobs, desc=f"Evaluating {source}", unit="item"
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

        # Build final evaluation results
        eval_results = []
        for item_id, evaluations_or_error in job_results:
            if (
                isinstance(evaluations_or_error, dict)
                and "error" in evaluations_or_error
            ):
                eval_results.append(
                    {
                        "id": item_id,
                        "source": data_dict[item_id].get("source", "unknown"),
                        "error": evaluations_or_error["error"],
                    }
                )
            else:
                eval_results.append(
                    {
                        "id": item_id,
                        "source": data_dict[item_id].get("source", "unknown"),
                        "evaluations": evaluations_or_error,
                    }
                )

        # Sort by ID
        eval_results.sort(key=lambda x: x["id"])

        # Calculate statistics
        print("\nCalculating statistics...")
        stats = calculate_statistics(eval_results)

        # Prepare final output
        output_data = {
            "metadata": {
                "predictions_path": str(predictions_path),
                "data_path": args.data_path,
                "question_generation_model": args.model,
                "judge_model": judge_model,
                "judge_model_id": judge_model_id,
                "prompt_path": args.prompt_path,
                "source": source,
            },
            "statistics": stats,
            "results": eval_results,
        }

        # Save evaluation results
        print(f"\nSaving evaluation results to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(
            f"✓ Done! Evaluated {len(valid_predictions)} items for {source}, saved to {output_path}"
        )

        # Print summary for this source
        print(f"\nSummary for {source}:")
        print(f"  Total items: {stats['overall']['total_items']}")
        print(f"  Successful: {stats['overall']['successful_items']}")
        print(f"  Failed: {stats['overall']['failed_items']}")
        print(f"  Total questions evaluated: {stats['overall']['total_questions']}")

        print(f"\n  Average Scores (Overall):")
        for metric, score in stats["averages"]["overall"].items():
            print(f"    {metric.replace('_', ' ').title()}: {score}")

        print(f"\n  Average Scores by Level:")
        for level in [1, 2, 3]:
            level_stats = stats["averages"]["by_level"].get(level, {})
            count = stats["by_level"][level]["count"]
            print(f"    Level {level} ({count} questions):")
            for metric, score in level_stats.items():
                print(f"      {metric.replace('_', ' ').title()}: {score}")

    print("\n" + "=" * 100)
    print("ALL SOURCES COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
