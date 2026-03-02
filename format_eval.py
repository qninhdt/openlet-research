import json
import os
import random
from pathlib import Path
from typing import List, Dict, Tuple
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from langchain_openai import ChatOpenAI
from tqdm import tqdm
from json_repair import json_repair

from dotenv import load_dotenv

load_dotenv()


# Prompt templates for different formats
PROMPT_JSON = """You are an Expert Examination Setter specializing in multiple-choice question generation.

Your task is to generate exactly {num_questions} multiple-choice questions based on the provided text. Each question must have exactly 4 options (A, B, C, D) and one correct answer.

Output the questions in JSON format as an array of objects. Each object must have:
- "content": the question text
- "options": array of 4 option strings
- "correct": the index of correct option (0 for A, 1 for B, 2 for C, 3 for D)

Example output format:
[
  {{
    "content": "What is the main idea of the passage?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct": 1
  }},
  {{
    "content": "According to the text, why did the event occur?",
    "options": ["Reason A", "Reason B", "Reason C", "Reason D"],
    "correct": 0
  }}
]

Generate exactly {num_questions} questions. Output ONLY valid JSON, no additional text.

Text:
{text}"""


PROMPT_CUSTOM_NO_INDEX = """You are an Expert Examination Setter specializing in multiple-choice question generation.

Your task is to generate exactly {num_questions} multiple-choice questions based on the provided text. Each question must have exactly 4 options and one correct answer.

Output the questions in this format:

### [Question text]
- [Option A]
- [Option B]
- [Option C]
- [Option D]
> [Correct answer: A|B|C|D]

Example:
### What is the main idea of the passage?
- The history of technology
- Modern innovations in science
- Environmental challenges
- Economic development strategies
> B

### According to the text, why did the event occur?
- Political pressure
- Economic factors
- Social unrest
- Natural causes
> A

Generate exactly {num_questions} questions. Follow the format exactly. Do not output empty text.

Text:
{text}"""


PROMPT_CUSTOM_WITH_INDEX = """You are an Expert Examination Setter specializing in multiple-choice question generation.

Your task is to generate exactly {num_questions} multiple-choice questions based on the provided text. Each question must have exactly 4 options and one correct answer.

Output the questions in this format with numbering:

### 1. [Question text]
- [Option A]
- [Option B]
- [Option C]
- [Option D]
> [Correct answer: A|B|C|D]

### 2. [Question text]
- [Option A]
- [Option B]
- [Option C]
- [Option D]
> [Correct answer: A|B|C|D]

Example:
### 1. What is the main idea of the passage?
- The history of technology
- Modern innovations in science
- Environmental challenges
- Economic development strategies
> B

### 2. According to the text, why did the event occur?
- Political pressure
- Economic factors
- Social unrest
- Natural causes
> A

Generate exactly {num_questions} questions. Number them sequentially starting from 1. Follow the format exactly. Do not output empty text

Text:
{text}"""


def load_data(data_path: str, n: int = -1, source: str = None) -> List[dict]:
    """Load data from JSON file

    Args:
        data_path: Path to the data.json file
        n: Number of items to load (-1 for all)
        source: Source to filter by (None for all sources)

    Returns:
        List of data items
    """
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Filter by source if specified
    if source:
        source_lower = source.lower()
        data = [item for item in data if item.get("source", "").lower() == source_lower]

    if n > 0:
        data = data[:n]

    return data


def parse_json_output(output: str, expected_count: int) -> Tuple[List[Dict], bool, int]:
    """Parse JSON output from LLM

    Returns:
        Tuple of (questions_list, has_syntax_error, actual_count)
    """
    try:
        # Try to parse as JSON
        questions = json_repair.loads(output)

        # remove json blocks if present
        # output = re.sub(r"```json(.*?)```", r"\1", output, flags=re.DOTALL).strip()
        # questions = json.loads(output)

        if not isinstance(questions, list):
            return [], True, 0

        # Validate each question has required fields
        valid_questions = []
        for q in questions:
            if (
                isinstance(q, dict)
                and "content" in q
                and "options" in q
                and "correct" in q
            ):
                if isinstance(q["options"], list) and isinstance(q["correct"], int):
                    valid_questions.append(q)

        # If no valid questions were parsed, it's a syntax error
        if len(valid_questions) == 0:
            return [], True, 0

        return valid_questions, False, len(valid_questions)

    except json.JSONDecodeError:
        return [], True, 0
    except Exception:
        return [], True, 0


def parse_custom_output(
    output: str, expected_count: int
) -> Tuple[List[Dict], bool, int]:
    """Parse custom format output (with or without index)

    This is adapted from the parse_llm_output function in question.py

    Handles edge cases where LLM uses ##, #, or ### as separators

    Returns:
        Tuple of (questions_list, has_syntax_error, actual_count)
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

        if len(options) != 4 or not answer_line:
            # Invalid question format
            continue

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
            }
        )

    # Determine if there's a syntax error
    # A syntax error occurs if we couldn't parse ANY valid questions
    has_syntax_error = len(questions) == 0

    return questions, has_syntax_error, len(questions)


def generate_questions(
    text: str,
    model: str,
    format_type: str,
    num_questions: int,
    openrouter_api_key: str,
    max_retries: int = 3,
) -> Tuple[List[Dict], bool, int, int]:
    """Generate questions from text using specified format

    Args:
        text: Input text
        model: Model ID
        format_type: One of 'json', 'custom', 'custom-indexed'
        num_questions: Expected number of questions to generate
        openrouter_api_key: API key
        max_retries: Maximum number of retries for empty output (default: 3)

    Returns:
        Tuple of (questions_list, has_syntax_error, expected_count, actual_count)
    """
    # Initialize LLM
    llm = ChatOpenAI(
        model=model,
        openai_api_key=openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
    )

    # Select prompt based on format
    if format_type == "json":
        prompt_template = PROMPT_JSON
    elif format_type == "custom":
        prompt_template = PROMPT_CUSTOM_NO_INDEX
    elif format_type == "custom-indexed":
        prompt_template = PROMPT_CUSTOM_WITH_INDEX
    else:
        raise ValueError(f"Unknown format type: {format_type}")

    # Create full prompt
    full_prompt = prompt_template.format(text=text, num_questions=num_questions)

    last_error = None

    for attempt in range(max_retries):
        # Generate questions
        response = llm.invoke(full_prompt)
        output = response.content

        # print(output)

        # Check empty output and retry
        if not output.strip():
            if attempt < max_retries - 1:
                print(
                    f"Empty output detected on attempt {attempt + 1}/{max_retries}, retrying..."
                )
                continue
            else:
                print(
                    f"Empty output detected on final attempt {attempt + 1}/{max_retries}"
                )
                return [], True, num_questions, 0

        # Parse based on format
        if format_type == "json":
            questions, has_syntax_error, actual_count = parse_json_output(
                output, num_questions
            )
        else:  # custom or custom-indexed
            questions, has_syntax_error, actual_count = parse_custom_output(
                output, num_questions
            )

        return questions, has_syntax_error, num_questions, actual_count

    # Should not reach here, but just in case
    return [], True, num_questions, 0


def process_single_sample(
    item: dict,
    model: str,
    format_type: str,
    api_key: str,
) -> dict:
    """Process a single sample

    Args:
        item: Data item with 'content' and 'id'
        model: Model ID
        format_type: Format type ('json', 'custom', 'custom-indexed')
        api_key: API key

    Returns:
        Result dictionary
    """
    num_questions = random.randint(10, 20)

    try:
        questions, has_syntax_error, expected, actual = generate_questions(
            text=item["content"],
            model=model,
            format_type=format_type,
            num_questions=num_questions,
            openrouter_api_key=api_key,
        )

        return {
            "id": item["id"],
            "has_syntax_error": has_syntax_error,
            "expected_count": expected,
            "actual_count": actual,
            "over_generated": actual > expected if not has_syntax_error else None,
            "under_generated": actual < expected if not has_syntax_error else None,
        }

    except Exception as e:
        return {
            "id": item["id"],
            "has_syntax_error": True,
            "expected_count": num_questions,
            "actual_count": 0,
            "over_generated": None,
            "under_generated": None,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate different output formats for question generation"
    )
    parser.add_argument(
        "-n", type=int, default=-1, help="Number of samples to process (-1 for all)"
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model ID to use (e.g., 'anthropic/claude-3.5-sonnet')",
    )
    parser.add_argument(
        "--format",
        type=str,
        required=True,
        choices=["json", "custom", "custom-indexed"],
        help="Output format: 'json' (traditional JSON), 'custom' (no index), 'custom-indexed' (with index)",
    )
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="Dataset source (e.g., 'race', 'dream', 'reclor')",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=128,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="datasets/unified/data.json",
        help="Path to the data.json file",
    )

    args = parser.parse_args()

    # Get API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")

    print(f"Model: {args.model}")
    print(f"Format: {args.format}")
    print(f"Source: {args.source}")
    print(f"Workers: {args.workers}")
    print("=" * 80)

    # Load data
    print(f"Loading data from {args.data_path}...")
    data = load_data(args.data_path, args.n, args.source)
    print(f"Loaded {len(data)} samples\n")

    if not data:
        print(f"No data found for source: {args.source}")
        return

    # Process samples in parallel
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_item = {
            executor.submit(
                process_single_sample, item, args.model, args.format, api_key
            ): item
            for item in data
        }

        with tqdm(total=len(data), desc="Processing", unit="sample") as pbar:
            for future in as_completed(future_to_item):
                result = future.result()
                results.append(result)
                pbar.update(1)

    # Calculate metrics
    total_samples = len(results)
    syntax_errors = sum(1 for r in results if r["has_syntax_error"])
    syntax_error_rate = syntax_errors / total_samples if total_samples > 0 else 0

    # For over/under generation, only count samples without syntax errors
    valid_samples = [r for r in results if not r["has_syntax_error"]]
    total_valid = len(valid_samples)

    if total_valid > 0:
        over_generated = sum(1 for r in valid_samples if r["over_generated"])
        under_generated = sum(1 for r in valid_samples if r["under_generated"])

        over_generation_rate = over_generated / total_valid
        under_generation_rate = under_generated / total_valid
    else:
        over_generation_rate = 0
        under_generation_rate = 0

    # Print results
    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80)
    print(f"Model: {args.model}")
    print(f"Format: {args.format}")
    print(f"Source: {args.source}")
    print(f"Total samples: {total_samples}")
    print("-" * 80)
    print(
        f"Syntax error rate: {syntax_error_rate:.2%} ({syntax_errors}/{total_samples})"
    )
    print(f"Valid samples: {total_valid}")

    if total_valid > 0:
        print(
            f"Over-generation rate: {over_generation_rate:.2%} ({sum(1 for r in valid_samples if r['over_generated'])}/{total_valid})"
        )
        print(
            f"Under-generation rate: {under_generation_rate:.2%} ({sum(1 for r in valid_samples if r['under_generated'])}/{total_valid})"
        )

        # Additional statistics
        total_expected = sum(r["expected_count"] for r in valid_samples)
        total_actual = sum(r["actual_count"] for r in valid_samples)
        print(f"\nTotal questions expected: {total_expected}")
        print(f"Total questions generated: {total_actual}")
        print(f"Accuracy: {total_actual / total_expected:.2%}")

    print("=" * 80)


if __name__ == "__main__":
    main()
