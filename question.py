import json
import os
from pathlib import Path
from typing import List, Dict
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from langchain_openai import ChatOpenAI
from tqdm import tqdm

from dotenv import load_dotenv

load_dotenv()


def load_prompts(prompt_folder: str = "prompts") -> Dict[str, str]:
    """Load prompts from prompts folder for each source

    Returns:
        Dictionary mapping source name to prompt content
    """
    prompts = {}
    prompt_dir = Path(prompt_folder)

    # Find all prompt files matching pattern: generate_{source}_questions.md
    for prompt_file in prompt_dir.glob("generate_*_questions.md"):
        # Extract source name from filename
        # e.g., "generate_race_questions.md" -> "race"
        source_name = prompt_file.stem.replace("generate_", "").replace(
            "_questions", ""
        )

        with open(prompt_file, "r", encoding="utf-8") as f:
            prompts[source_name] = f.read()

    if not prompts:
        raise FileNotFoundError(f"No prompt files found in {prompt_folder}")

    return prompts


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


def parse_llm_output(output: str) -> List[Dict]:
    """Parse LLM output in the format:

    ### [question text]
    - option 1
    - option 2
    - option 3
    - option 4
    > A|B|C|D

    Handles edge cases where LLM uses ##, #, or ### as separators

    Returns list of question dictionaries
    """
    questions = []

    # Normalize the output: replace ##, #, or #### with ### for consistent parsing
    # Use regex to find question markers and normalize them
    # Pattern: starts with 1-4 # at the beginning of a line
    normalized_output = re.sub(r"^#{1,4}\s+", "###", output, flags=re.MULTILINE)

    # Split by ### to separate questions
    question_blocks = normalized_output.strip().split("###")

    for block in question_blocks:
        if not block.strip():
            continue

        # Remove all unnecessary newlines and normalize whitespace
        # Split by newlines but keep only non-empty lines
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]

        # if (
        #     len(lines) < 5
        # ):  # Need at least: Question + 4 options + answer line (no more "Question:" prefix check)
        #     continue

        # Check if this block contains at least one option line (starts with "-")
        # and one answer line (starts with ">")
        # This helps filter out explanatory text blocks that LLM might add
        has_options = any(line.startswith("-") for line in lines)
        has_answer = any(line.startswith(">") for line in lines)

        if not has_options or not has_answer:
            # Skip blocks that don't look like questions
            continue

        # Parse question content - first line after ### is the question
        # Remove optional number prefix like "1.", "2.", etc.
        content = lines[0].strip()

        # Remove question number prefix (e.g., "1. ", "2. ", "3. ")
        # Pattern: starts with digits followed by . and space
        content = re.sub(r"^\d+\.\s+", "", content)

        # Normalize multiple consecutive underscores to a single underscore
        # Replace sequences of 2 or more underscores with a single underscore
        content = re.sub(r"_{2,}", "_", content)

        # Parse options - look for lines starting with "-"
        options = []
        correct_idx = -1
        answer_line = None

        for line in lines[1:]:
            if line.startswith(">"):
                # This is the answer line
                answer_line = line
                break
            elif line.startswith("-") and len(options) < 4:
                # Remove "- " prefix
                option_text = line[1:].strip()

                # Remove various option prefixes that LLM might add incorrectly
                # Patterns: A., B., C., D., A), B), C), D), A/, B/, C/, D/, A, B, C, D
                # Also handle lowercase: a., b., c., d., a), b), c), d), a/, b/, c/, d/
                # Pattern explanation:
                # ^[A-Da-d]     - Start with A, B, C, D (upper or lowercase)
                # [.)/]?        - Optionally followed by . or ) or /
                # ,?            - Optionally followed by comma
                # \s+           - Followed by one or more spaces
                option_text = re.sub(r"^[A-Da-d][.)/]?,?\s+", "", option_text)

                options.append(option_text)

        # if len(options) != 4 or not answer_line:
        #     continue

        # Parse the answer line "> A|B|C|D"
        answer_letter = answer_line.replace(">", "").strip().upper()
        correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        correct_idx = correct_map.get(answer_letter, -1)

        if correct_idx == -1:
            continue

        questions.append(
            {
                "content": content,
                "options": options,
                "correct": correct_idx,
                "type": "General",  # Default type
            }
        )

    return questions


def generate_questions(
    text: str,
    model: str,
    prompt_template: str,
    openrouter_api_key: str,
    max_retries: int = 3,
) -> List[Dict]:
    """Generate questions from text using simple text format

    Args:
        text: Input text to generate questions from
        model: Model ID to use
        prompt_template: Prompt template with {text} placeholder
        openrouter_api_key: OpenRouter API key
        max_retries: Maximum number of retries

    Returns:
        List of question dictionaries
    """
    # Initialize LLM
    llm = ChatOpenAI(
        model=model,
        openai_api_key=openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
    )

    # Create full prompt
    full_prompt = prompt_template.replace("{text}", text)

    # Retry loop
    last_error = None
    for attempt in range(max_retries):
        try:
            # Generate questions
            response = llm.invoke(full_prompt)
            output = response.content

            # print(output)

            # check if output is empty
            if not output.strip():
                print(f"Warning: LLM returned empty output")

            # Parse output
            questions = parse_llm_output(output)

            # if len(questions) < 5:
            #     print(f"Warning: Only got {len(questions)} questions, need 5")

            return questions

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                continue
            else:
                raise Exception(
                    f"Failed after {max_retries} attempts. Last error: {str(e)}"
                )

    raise Exception(f"Unexpected failure: {str(last_error)}")


def process_single_job(
    item: dict,
    set_idx: int,
    model: str,
    prompts: Dict[str, str],
    api_key: str,
) -> tuple:
    """Process a single job (one item, one set)

    Args:
        item: Data item with 'content', 'id', and 'source'
        set_idx: Set index (0-based)
        model: Model ID to use
        prompts: Dictionary of prompts for each source
        api_key: OpenRouter API key

    Returns:
        Tuple of (item_id, set_idx, question_set or error_dict)
    """
    try:
        # Get the appropriate prompt for this item's source
        source = item.get("source", "").lower()

        # Try to find matching prompt
        # First try exact match, then try with "race-" prefix removed
        prompt_template = None
        if source in prompts:
            prompt_template = prompts[source]
        elif source.startswith("race-"):
            # Try "race" for "race-h" or "race-m"
            race_prompt = prompts.get("race")
            if race_prompt:
                prompt_template = race_prompt

        if not prompt_template:
            # Fallback: use any available prompt
            if prompts:
                prompt_template = list(prompts.values())[0]
                print(f"Warning: No prompt found for source '{source}', using fallback")
            else:
                raise ValueError(f"No prompts available for source '{source}'")

        result = generate_questions(
            text=item["content"],
            model=model,
            prompt_template=prompt_template,
            openrouter_api_key=api_key,
        )

        return (item["id"], set_idx, result)

    except Exception as e:
        return (item["id"], set_idx, {"error": str(e)})


def main():
    parser = argparse.ArgumentParser(
        description="Generate multiple-choice questions from text using LLMs"
    )
    parser.add_argument(
        "-n", type=int, default=-1, help="Number of items to process (-1 for all)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="anthropic/claude-3.5-sonnet",
        help="Model ID to use (e.g., 'anthropic/claude-3.5-sonnet', 'openai/gpt-4')",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=128,
        help="Number of parallel workers (default: 5)",
    )
    parser.add_argument(
        "-k",
        "--num-sets",
        type=int,
        default=1,
        help="Number of independent question sets to generate per sample (default: 1)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="datasets/unified/data.json",
        help="Path to the data.json file",
    )
    parser.add_argument(
        "--prompts-folder",
        type=str,
        default="prompts",
        help="Folder containing prompt files",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="Filter by source(s) (e.g., 'race', 'dream'). Default: all sources",
    )

    args = parser.parse_args()

    # Get API key from environment variable
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenRouter API key not found. Please set OPENROUTER_API_KEY environment variable"
        )

    # Load prompts for each source
    print(f"Loading prompts from {args.prompts_folder}...")
    prompts = load_prompts(args.prompts_folder)
    print(f"Loaded prompts for sources: {', '.join(prompts.keys())}")

    # Load data
    print(f"Loading data from {args.data_path}...")
    data = load_data(args.data_path, args.n, args.sources)

    if args.sources:
        print(f"Filtered by sources: {', '.join(args.sources)}")
    print(f"Loaded {len(data)} items")

    # Prepare output directory
    # Determine dataset name based on sources
    if not args.sources:
        raise ValueError(
            "Error: --sources parameter is required. Please specify which dataset(s) to generate questions for.\n"
            "Example: --sources reclor, --sources race-h, or --sources race-h dream"
        )

    if len(args.sources) == 1:
        # Single source: use source name
        dataset_name = args.sources[0].lower()
    else:
        # Multiple sources: use combined name
        dataset_name = "_".join(sorted([s.lower() for s in args.sources]))

    # Get model_id from model name
    model_id = args.model.replace("/", "_")

    # Output: outputs/{dataset_name}/{model_id}/
    output_dir = Path("outputs") / dataset_name / model_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "predictions.json"

    print(f"Using model: {args.model}")
    print(f"Using {args.workers} parallel workers")
    print(f"Generating {args.num_sets} question set(s) per sample")
    print(
        f"Output will be saved to: {output_path}"
    )  # Create all jobs (k jobs per sample)
    total_jobs = len(data) * args.num_sets
    print(f"Total jobs: {total_jobs} ({len(data)} samples × {args.num_sets} sets)")

    # Process items in parallel with multithreading
    # Each job generates one set for one item
    job_results = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all jobs (k * n jobs total)
        future_to_job = {}
        for item in data:
            for set_idx in range(args.num_sets):
                future = executor.submit(
                    process_single_job,
                    item,
                    set_idx,
                    args.model,
                    prompts,
                    api_key,
                )
                future_to_job[future] = (item["id"], set_idx)

        # Process completed jobs with progress bar
        with tqdm(total=total_jobs, desc="Generating questions", unit="job") as pbar:
            for future in as_completed(future_to_job):
                item_id, set_idx = future_to_job[future]
                result = future.result()
                job_results.append(result)

                # Log errors without stopping progress bar
                if (
                    len(result) == 3
                    and isinstance(result[2], dict)
                    and "error" in result[2]
                ):
                    tqdm.write(
                        f"✗ Error in item {item_id} set {set_idx}: {result[2]['error']}"
                    )

                pbar.update(1)

    # Organize results by item_id
    results_by_id = {}
    for item_id, set_idx, question_set_or_error in job_results:
        if item_id not in results_by_id:
            results_by_id[item_id] = {}
        results_by_id[item_id][set_idx] = question_set_or_error

    # Build final predictions
    predictions = []
    for item in data:
        item_id = item["id"]

        if item_id not in results_by_id:
            # All jobs failed
            predictions.append(
                {
                    "id": item_id,
                    "source": item.get("source", "unknown"),
                    "error": "All jobs failed",
                }
            )
            continue

        # Collect all sets for this item
        sets_dict = results_by_id[item_id]
        all_sets = []
        has_error = False
        error_msg = None

        for set_idx in range(args.num_sets):
            if set_idx in sets_dict:
                result = sets_dict[set_idx]
                if isinstance(result, dict) and "error" in result:
                    has_error = True
                    error_msg = result["error"]
                    break
                all_sets.append(result)
            else:
                has_error = True
                error_msg = f"Missing set {set_idx}"
                break

        if has_error:
            predictions.append(
                {
                    "id": item_id,
                    "source": item.get("source", "unknown"),
                    "error": error_msg,
                }
            )
        else:
            # Success
            if args.num_sets == 1:
                # Backward compatibility
                predictions.append(
                    {
                        "id": item_id,
                        "source": item.get("source", "unknown"),
                        "generated_questions": all_sets[0],
                    }
                )
            else:
                predictions.append(
                    {
                        "id": item_id,
                        "source": item.get("source", "unknown"),
                        "generated_questions": all_sets,
                        "num_sets": args.num_sets,
                    }
                )

    # Sort predictions by ID to maintain order
    predictions.sort(key=lambda x: x["id"])

    # Save predictions
    print(f"\nSaving predictions to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)

    print(f"✓ Done! Processed {len(data)} items, saved to {output_path}")

    # Print summary
    successful = sum(1 for p in predictions if "error" not in p)
    failed = len(predictions) - successful
    total_question_sets = successful * args.num_sets

    print(f"\nSummary:")
    print(f"  Successful samples: {successful}")
    print(f"  Failed samples: {failed}")
    print(f"  Total question sets generated: {total_question_sets}")
    print(f"  Question sets per sample: {args.num_sets}")


if __name__ == "__main__":
    main()
