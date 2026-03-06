"""Parser module for converting LLM output into structured quiz data."""

import re
from dataclasses import dataclass, field
from typing import Optional


# ============== Quiz Data Classes ==============


@dataclass
class Question:
    """Represents a single quiz question."""

    id: int
    content: str
    options: list[str]
    correct: int  # 0-based index (A=0, B=1, C=2, D=3)
    explanation: str  # Explanation of why the correct answer is right
    type: Optional[str] = "General"
    level: Optional[int] = None  # Question difficulty level (1, 2, 3)


@dataclass
class ParsedQuizData:
    """Represents parsed quiz data with questions only."""

    questions: list[Question] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore."""
        return {
            "questions": [
                {
                    "id": q.id,
                    "content": q.content,
                    "options": q.options,
                    "correct": q.correct,
                    "explanation": q.explanation,
                    "type": q.type,
                    "level": q.level,
                }
                for q in self.questions
            ],
        }


# ============== Single-Prompt Mode Parsers ==============


def parse_llm_output(output: str) -> ParsedQuizData:
    """
    Parse LLM output containing only questions in the format:

    ### [question text]
    - option 1
    - option 2
    - option 3
    - option 4
    > A|B|C|D
    > Explanation: explanation text

    Returns parsed quiz data with questions only (no metadata).
    """
    questions: list[Question] = []

    # Normalize the output: replace ##, ####, etc with ### for consistent parsing
    normalized_output = re.sub(r"^#{2,4}\s+", "###", output, flags=re.MULTILINE)

    # Split by ### to separate questions
    question_blocks = normalized_output.strip().split("###")

    question_id = 1

    for block in question_blocks:
        if not block.strip():
            continue

        # Split by newlines but keep only non-empty lines
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]

        # Check if this block contains at least one option line (starts with "-")
        # and one answer line (starts with ">")
        has_options = any(line.startswith("-") for line in lines)
        has_answer = any(
            line.startswith(">") and re.match(r"^>\s*[A-Da-d]\s*$", line)
            for line in lines
        )

        if not has_options or not has_answer:
            continue

        # Parse question content - first line after ### is the question
        content = lines[0].strip()

        # Remove question number prefix (e.g., "1. ", "2. ", "3. ")
        content = re.sub(r"^\d+\.\s+", "", content)

        # Normalize multiple consecutive underscores to a single underscore
        content = re.sub(r"_{2,}", "_", content)

        # Parse options - look for lines starting with "-"
        options: list[str] = []
        answer_line: Optional[str] = None
        explanation: str = ""
        answer_line_idx: int = -1

        for idx, line in enumerate(lines[1:], start=1):
            if line.startswith(">") and not answer_line:
                # Check if this is an answer line (single letter A-D)
                answer_check = line.replace(">", "").strip().upper()
                if answer_check in ["A", "B", "C", "D"]:
                    answer_line = line
                    answer_line_idx = idx
            elif line.startswith("-") and len(options) < 4:
                # Remove "- " prefix
                option_text = line[1:].strip()

                # Remove various option prefixes that LLM might add incorrectly
                option_text = re.sub(r"^[A-Da-d][.)/]?,?\s+", "", option_text)

                options.append(option_text)

        if not answer_line:
            continue

        # Parse the answer line "> A|B|C|D"
        answer_letter = answer_line.replace(">", "").strip().upper()
        correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
        correct_idx = correct_map.get(answer_letter)

        if correct_idx is None:
            continue

        # Extract explanation from the line after answer
        # Look for "> Explanation:" in remaining lines after answer
        for line in lines[answer_line_idx + 1 :]:
            if line.startswith(">") and "explanation:" in line.lower():
                # Extract explanation text after "Explanation:"
                explanation_match = re.search(
                    r">\s*explanation:\s*(.+)", line, re.IGNORECASE
                )
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                break

        # Default explanation if not found
        if not explanation:
            explanation = "No explanation provided."

        questions.append(
            Question(
                id=question_id,
                content=content,
                options=options,
                correct=correct_idx,
                explanation=explanation,
                type="General",
            )
        )
        question_id += 1

    return ParsedQuizData(questions=questions)


def parse_single_prompt_metadata(output: str) -> dict:
    """
    Parse metadata from single-prompt LLM output.

    Expected format at beginning of output:
    Title: [title]
    Topics: [topic1, topic2, ...]
    Description: [description]

    Returns dict with title, topics, description.
    """
    metadata = {
        "title": "Untitled Quiz",
        "topics": [],
        "description": "",
    }

    # Extract title
    title_match = re.search(r"^Title:\s*(.+)$", output, re.MULTILINE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()

    # Extract topics
    topics_match = re.search(r"^Topics:\s*(.+)$", output, re.MULTILINE)
    if topics_match:
        topics_str = topics_match.group(1).strip()
        # Parse comma-separated topics
        metadata["topics"] = [t.strip() for t in topics_str.split(",") if t.strip()]

    # Extract description
    desc_match = re.search(r"^Description:\s*(.+)$", output, re.MULTILINE)
    if desc_match:
        metadata["description"] = desc_match.group(1).strip()

    return metadata


def parse_analyzer_metadata(analyzer_output: str) -> dict:
    """
    Parse metadata from analyzer agent output.

    Handles multiple output variants robustly:
    - "- Title: ..."
    - "* **Title:** ..."
    - "**Title:** ..."
    - "Title: ..."

    Returns dict with title, topics, description.
    """
    metadata = {
        "title": "Untitled Quiz",
        "topics": [],
        "description": "",
    }

    if not analyzer_output or not analyzer_output.strip():
        return metadata

    try:
        # Flexible pattern: optional list markers (-, *), optional bold (**), key, colon, value
        def extract_field(key: str) -> str | None:
            pattern = rf"^[\-\*\s]*\**{re.escape(key)}\**:\s*(.+)$"
            match = re.search(pattern, analyzer_output, re.MULTILINE | re.IGNORECASE)
            if match:
                # Strip any remaining ** markdown bold markers from the value
                return match.group(1).replace("**", "").strip()
            return None

        title = extract_field("Title")
        if title:
            metadata["title"] = title

        topic = extract_field("Topic")
        if topic:
            # Split by comma or semicolon
            metadata["topics"] = [t.strip() for t in re.split(r"[,;]", topic) if t.strip()]

        summary = extract_field("Summary")
        if summary:
            metadata["description"] = summary

    except Exception as e:
        print(f"Warning: parse_analyzer_metadata failed: {e}")

    return metadata


# ============== Multi-Agent Mode Parsers ==============


def parse_generator_output(output: str, n: int, expected_level: int = None) -> list[dict]:
    """Parse generator output into structured questions.

    Expected format:
    ID: 1
    Question: Question text
    A: Option A
    B: Option B
    C: Option C
    D: Option D
    Answer: A

    Returns list of question dictionaries with keys:
    id, question, options, correct_idx, level
    """
    questions = []

    if not output or not output.strip():
        return questions

    try:
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
                question_text = block[question_pos + len("Question:"):a_pos].strip()

                # Extract options by finding text between prefixes
                if a_pos == -1 or b_pos == -1 or c_pos == -1 or d_pos == -1 or answer_pos == -1:
                    continue

                option_a = block[a_pos + len("\nA:"):b_pos].strip()
                option_b = block[b_pos + len("\nB:"):c_pos].strip()
                option_c = block[c_pos + len("\nC:"):d_pos].strip()
                option_d = block[d_pos + len("\nD:"):answer_pos].strip()

                options = [option_a, option_b, option_c, option_d]

                # Extract Answer letter
                answer_match = re.search(r"Answer:\s*([A-D])", block, re.IGNORECASE)
                answer_letter = answer_match.group(1).strip().upper() if answer_match else None

                # Only add if we have all 4 options and answer
                if len(options) == 4 and answer_letter:
                    correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
                    correct_idx = correct_map.get(answer_letter, -1)

                    # Parse ID from the block
                    id_match = re.match(r"ID:\s*(\d+)", block.strip())
                    q_id = int(id_match.group(1)) if id_match else None

                    if correct_idx != -1:
                        questions.append({
                            "id": q_id,
                            "question": question_text,
                            "options": options,
                            "correct_idx": correct_idx,
                            "level": expected_level,
                        })

            except Exception as e:
                print(f"Warning: Failed to parse question block: {str(e)}")
                continue

    except Exception as e:
        print(f"Warning: parse_generator_output failed: {str(e)}")

    return questions

def parse_validator_output(output: str) -> list[dict]:
    """Parse validator output into structured validation results.

    Expected format per question:
    ID: 1
    Solvability: PASS|FAIL
    Distractor Quality: PASS|FAIL
    Alignment: PASS|FAIL
    Verdict: PASS|FAIL
    Feedback: ...

    Returns list of {id, verdict, feedback}
    """
    results = []

    if not output or not output.strip():
        return results

    try:
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

                results.append({
                    "id": q_id,
                    "verdict": verdict,
                    "feedback": feedback,
                })
            except Exception as e:
                print(f"Warning: Failed to parse validator block: {str(e)}")
                continue

    except Exception as e:
        print(f"Warning: parse_validator_output failed: {str(e)}")

    return results


def format_questions_for_validation(questions: list[dict]) -> str:
    """Format questions list into text block for validator prompt.

    Args:
        questions: List of question dicts with question, options, correct_idx

    Returns:
        Formatted string
    """
    lines = []
    correct_map = {0: "A", 1: "B", 2: "C", 3: "D"}
    for idx, q in enumerate(questions, 1):
        lines.append(f"ID: {idx}")
        lines.append(f"Question: {q.get('question', '')}")
        options = q.get("options", [])
        for i, label in enumerate(["A", "B", "C", "D"]):
            if i < len(options):
                lines.append(f"{label}: {options[i]}")
        lines.append(f"Answer: {correct_map.get(q.get('correct_idx', 0), 'A')}")
        lines.append("")
    return "\n".join(lines)


def format_failed_questions_for_fixer(
    questions: list[dict], validation: list[dict]
) -> str:
    """Format failed questions with their feedback for the fixer prompt.

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
            feedback_map[v["id"]] = v.get("feedback", "No specific feedback")

    for idx, q in enumerate(questions, 1):
        feedback = feedback_map.get(idx)
        if feedback:
            lines.append(f"ID: {idx}")
            lines.append(f"Question: {q['question']}")
            for i, label in enumerate(["A", "B", "C", "D"]):
                lines.append(f"{label}: {q['options'][i]}")
            lines.append(f"Answer: {correct_map.get(q['correct_idx'], 'A')}")
            lines.append(f"Feedback: {feedback}")
            lines.append("")

    return "\n".join(lines)


def format_questions_for_explanation(questions: list[dict]) -> str:
    """Format merged questions into text block for the explanation prompt.

    Args:
        questions: List of question dicts with content, options, correct, level, id

    Returns:
        Formatted string suitable for the EXPLANATION_PROMPT {questions} placeholder
    """
    lines = []
    correct_map = {0: "A", 1: "B", 2: "C", 3: "D"}
    for q in questions:
        q_id = q.get("id", "?")
        level = q.get("level", "?")
        lines.append(f"ID: {q_id}  (Level {level})")
        lines.append(f"Question: {q.get('content', q.get('question', ''))}")
        options = q.get("options", [])
        for i, label in enumerate(["A", "B", "C", "D"]):
            if i < len(options):
                lines.append(f"{label}: {options[i]}")
        correct = q.get("correct", q.get("correct_idx", 0))
        lines.append(f"Answer: {correct_map.get(correct, 'A')}")
        lines.append("")
    return "\n".join(lines)


def parse_explanation_output(output: str, num_questions: int) -> dict[int, str]:
    """Parse explanation agent output into a mapping of question ID → explanation.

    Handles multiple formats robustly:
    - Standard:  ID: 1\\nExplanation: ...
    - Multiline: Explanation text spanning several lines until next ID block
    - Missing IDs or malformed blocks are skipped gracefully

    Args:
        output: Raw LLM output from the explanation agent
        num_questions: Expected number of questions (used for fallback)

    Returns:
        Dict mapping question ID (int) → explanation string.
        If parsing fails entirely, returns an empty dict.
    """
    explanations: dict[int, str] = {}

    if not output or not output.strip():
        return explanations

    try:
        # Split by "ID:" blocks
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

                # Extract explanation — everything after "Explanation:" until end of block
                explanation_match = re.search(
                    r"Explanation:\s*(.+)", block, re.DOTALL
                )
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                    # Clean up: collapse multiple newlines into spaces for single-paragraph
                    explanation = re.sub(r"\n+", " ", explanation).strip()
                    if explanation:
                        explanations[q_id] = explanation
            except (ValueError, AttributeError):
                continue

    except Exception as e:
        print(f"Warning: Failed to parse explanation output: {e}")

    return explanations
