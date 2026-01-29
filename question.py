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


def load_prompt(prompt_path: str = "prompts/question.md") -> str:
    """Load the single prompt file

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


def parse_llm_output(output: str, total_questions: int) -> List[Dict]:
    """Parse LLM output in the format:

    ### [question text]
    - option 1
    - option 2
    - option 3
    - option 4
    > A|B|C|D

    Handles edge cases where LLM uses ##, #, or ### as separators

    Returns list of question dictionaries with level field (1/2/3)

    Args:
        output: Raw LLM output text
        total_questions: Total number of questions (3n), used to determine level boundaries
    """
    questions = []

    # Normalize the output: replace ##, #, or #### with ### for consistent parsing
    # Use regex to find question markers and normalize them
    # Pattern: starts with 1-4 # at the beginning of a line
    normalized_output = re.sub(r"^#{1,4}\s+", "###", output, flags=re.MULTILINE)

    # Also handle case where questions are numbered without ### (e.g., "1.", "2.", etc.)
    # Replace patterns like "1. " at the start of a line with "###"
    # But only if it's followed by text (not just a number in an option)
    normalized_output = re.sub(
        r"^\d+\.\s+(?=[A-Z])", "###", normalized_output, flags=re.MULTILINE
    )

    # Split by ### to separate questions
    question_blocks = normalized_output.strip().split("###")

    for block in question_blocks:
        if not block.strip():
            continue

        # Remove all unnecessary newlines and normalize whitespace
        # Split by newlines but keep only non-empty lines
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]

        # Skip empty blocks
        if not lines:
            continue

        # Check if this block contains at least one option line (starts with "-")
        # and one answer line (starts with ">")
        # This helps filter out explanatory text blocks that LLM might add
        # e.g., "### Level 3: Critical Reasoning..." or "# Introduction"
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
            # Strip again for extra safety (in case of nested whitespace)
            line = line.strip()

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

    # Assign level to each question based on order (1/3 level 1, 1/3 level 2, 1/3 level 3)
    n = total_questions // 3
    for i, question in enumerate(questions):
        if i < n:
            question["level"] = 1
        elif i < 2 * n:
            question["level"] = 2
        else:
            question["level"] = 3

    return questions


def generate_questions(
    text: str,
    model: str,
    prompt_template: str,
    openrouter_api_key: str,
    n: int = 1,
    max_retries: int = 3,
) -> List[Dict]:
    """Generate questions from text using simple text format

    Args:
        text: Input text to generate questions from
        model: Model ID to use
        prompt_template: Prompt template with {content} and {n} placeholders
        openrouter_api_key: OpenRouter API key
        n: Number of questions per level (total questions = 3*n)
        max_retries: Maximum number of retries

    Returns:
        List of question dictionaries with level field
    """
    # Initialize LLM
    llm = ChatOpenAI(
        model=model,
        openai_api_key=openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
    )

    # Create full prompt with content and n
    full_prompt = prompt_template.replace("{content}", text).replace("{n}", str(n))

    # Retry loop
    last_error = None
    total_questions = 3 * n

    for attempt in range(max_retries):
        try:
            # Generate questions
            response = llm.invoke(full_prompt)
            output = response.content

            print(output)

            # check if output is empty
            if not output.strip():
                print(f"Warning: LLM returned empty output")

            # Parse output
            questions = parse_llm_output(output, total_questions)

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
    model: str,
    prompt: str,
    api_key: str,
    n: int = 1,
) -> tuple:
    """Process a single job (one item)

    Args:
        item: Data item with 'content', 'id', and 'source'
        model: Model ID to use
        prompt: Prompt template string
        api_key: OpenRouter API key
        n: Number of questions per level

    Returns:
        Tuple of (item_id, question_list or error_dict)
    """
    try:
        result = generate_questions(
            text=item["content"],
            model=model,
            prompt_template=prompt,
            openrouter_api_key=api_key,
            n=n,
        )

        return (item["id"], result)

    except Exception as e:
        return (item["id"], {"error": str(e)})


def main():
    parser = argparse.ArgumentParser(
        description="Generate multiple-choice questions from text using LLMs"
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
        "--workers",
        type=int,
        default=128,
        help="Number of parallel workers (default: 128)",
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
        "--prompt-path",
        type=str,
        default="prompts/question.md",
        help="Path to the prompt file",
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

    # Load the single prompt file
    print(f"Loading prompt from {args.prompt_path}...")
    prompt = load_prompt(args.prompt_path)
    print(f"Prompt loaded successfully")

    # Validate sources parameter
    if not args.sources:
        raise ValueError(
            "Error: --sources parameter is required. Please specify which dataset(s) to generate questions for.\n"
            "Example: --sources reclor, --sources race, or --sources race dream"
        )

    # Get model_id from model name
    model_id = args.model.replace("/", "_")

    print(f"Using model: {args.model}")
    print(f"Model ID: {model_id}")
    print(f"Using {args.workers} parallel workers")
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

        # Output: outputs/{source}/{model_id}/
        output_dir = Path("outputs") / source_lower / model_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "predictions.json"

        print(f"Output will be saved to: {output_path}")

        # Process items in parallel with multithreading
        job_results = []
        total_jobs = len(data)

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            # Submit all jobs
            future_to_job = {}
            for item in data:
                future = executor.submit(
                    process_single_job,
                    item,
                    args.model,
                    prompt,
                    api_key,
                    args.n,
                )
                future_to_job[future] = item["id"]

            # Process completed jobs with progress bar
            with tqdm(
                total=total_jobs, desc=f"Generating {source}", unit="item"
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

        # Build final predictions
        predictions = []
        for item_id, question_list_or_error in job_results:
            if (
                isinstance(question_list_or_error, dict)
                and "error" in question_list_or_error
            ):
                predictions.append(
                    {
                        "id": item_id,
                        "source": next(
                            (
                                item.get("source", "unknown")
                                for item in data
                                if item["id"] == item_id
                            ),
                            "unknown",
                        ),
                        "error": question_list_or_error["error"],
                    }
                )
            else:
                predictions.append(
                    {
                        "id": item_id,
                        "source": next(
                            (
                                item.get("source", "unknown")
                                for item in data
                                if item["id"] == item_id
                            ),
                            "unknown",
                        ),
                        "generated_questions": question_list_or_error,
                    }
                )

        # Sort predictions by ID to maintain order
        predictions.sort(key=lambda x: x["id"])

        # Save predictions
        print(f"\nSaving predictions to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(predictions, f, indent=2, ensure_ascii=False)

        print(
            f"✓ Done! Processed {len(data)} items for {source}, saved to {output_path}"
        )

        # Print summary
        successful = sum(1 for p in predictions if "error" not in p)
        failed = len(predictions) - successful
        total_questions = successful * 3 * args.n

        print(f"\nSummary for {source}:")
        print(f"  Successful samples: {successful}")
        print(f"  Failed samples: {failed}")
        print(f"  Total questions generated: {total_questions}")
        print(f"  Questions per sample: {3 * args.n} ({args.n} per level)")

    print("\n" + "=" * 100)
    print("ALL SOURCES COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
