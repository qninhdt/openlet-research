"""Parser module for converting LLM output into structured quiz data."""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Question:
    """Represents a single quiz question."""

    id: int
    content: str
    options: list[str]
    correct: int  # 0-based index (A=0, B=1, C=2, D=3)
    explanation: str  # Explanation of why the correct answer is right
    type: Optional[str] = "General"


@dataclass
class ParsedQuizData:
    """Represents parsed quiz data with metadata and questions."""

    title: str = "Untitled Quiz"
    description: str = ""
    genre: str = "General"
    topics: list[str] = field(default_factory=lambda: ["General"])
    questions: list[Question] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore."""
        return {
            "title": self.title,
            "description": self.description,
            "genre": self.genre,
            "topics": self.topics,
            "questions": [
                {
                    "id": q.id,
                    "content": q.content,
                    "options": q.options,
                    "correct": q.correct,
                    "explanation": q.explanation,
                    "type": q.type,
                }
                for q in self.questions
            ],
        }


def parse_llm_output(output: str) -> ParsedQuizData:
    """
    Parse LLM output in the format:

    # [Title]
    > Genre: [genre]
    > Topics: [topic1, topic2, topic3]

    ### [question text]
    - option 1
    - option 2
    - option 3
    - option 4
    > A|B|C|D
    > Explanation: explanation text

    Returns parsed quiz data with metadata and questions.
    """
    title = "Untitled Quiz"
    description = ""
    genre = "General"
    topics: list[str] = []
    questions: list[Question] = []

    # Extract title from first # line
    title_match = re.search(r"^#\s+(.+?)$", output, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()

    # Extract description from > Description: line
    description_match = re.search(
        r">\s*Description:\s*(.+?)$", output, re.MULTILINE | re.IGNORECASE
    )
    if description_match:
        description = description_match.group(1).strip()

    # Extract genre from > Genre: line
    genre_match = re.search(
        r">\s*Genre:\s*(.+?)$", output, re.MULTILINE | re.IGNORECASE
    )
    if genre_match:
        genre = genre_match.group(1).strip()

    # Extract topics from > Topics: line (comma-separated)
    topics_match = re.search(
        r">\s*Topics?:\s*(.+?)$", output, re.MULTILINE | re.IGNORECASE
    )
    if topics_match:
        topics = [t.strip() for t in topics_match.group(1).split(",") if t.strip()]

    # Default to "General" if no topics found
    if not topics:
        topics = ["General"]

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

    return ParsedQuizData(
        title=title,
        description=description,
        genre=genre,
        topics=topics,
        questions=questions,
    )
