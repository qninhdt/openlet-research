"""Parser module for converting LLM output into structured quiz data."""

import re
import yaml
from dataclasses import dataclass, field
from typing import Optional, Any


# ============== Knowledge Graph Data Classes ==============


def fix_broken_quotes(yaml_string: str) -> str:
    """
    Fix malformed YAML lines caused by LLMs producing unbalanced/dangling double quotes.

    Typical bad input:
        conflict_status: "little fires" burning now
    Fixed output:
        conflict_status: "\"little fires\" burning now"

    Strategy:
    - Scan YAML line-by-line for simple "key: value" patterns.
    - If the value contains a double quote but is not wrapped as a single valid
      double-quoted YAML scalar, escape existing quotes and wrap the whole value
      in double quotes.
    - Skip nested structures (values starting with '{' or '[').
    """
    lines = yaml_string.split("\n")
    fixed_lines: list[str] = []

    # Match: [indent][optional '- '][key]:
    # Group 1: "  key:" including trailing spaces after colon
    # Group 2: the value part
    pattern = r"^(\s*-?\s*[\w\-_]+:\s*)(.+)$"

    for line in lines:
        match = re.match(pattern, line)
        if match:
            prefix = match.group(1)
            value = match.group(2).strip()

            # Skip empty objects/arrays or nested structures
            if value.startswith("{") or value.startswith("["):
                fixed_lines.append(line)
                continue

            if '"' in value:
                # If not already a clean double-quoted scalar, wrap it safely
                if not (value.startswith('"') and value.endswith('"')):
                    clean_value = value.replace('"', '\\"')
                    fixed_lines.append(f'{prefix}"{clean_value}"')
                    continue

        fixed_lines.append(line)

    return "\n".join(fixed_lines)


@dataclass
class KnowledgeGraphMeta:
    """Metadata about the extracted knowledge graph."""

    title: str = ""
    type: str = ""
    topic: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    tone: list[str] = field(default_factory=list)
    author: str = ""
    date: str = ""


@dataclass
class KnowledgeGraphContext:
    """Context information including summary and main points."""

    summary: str = ""
    main_points: list[str] = field(default_factory=list)


@dataclass
class KnowledgeGraphEntity:
    """An entity in the knowledge graph with dynamic attributes."""

    name: str
    type: str  # person | organization | location | thing | concept
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGraphRelationship:
    """A relationship between two entities."""

    source: str
    action: str
    target: str
    context: Optional[str] = None


@dataclass
class KnowledgeGraph:
    """Complete knowledge graph data structure."""

    meta: KnowledgeGraphMeta = field(default_factory=KnowledgeGraphMeta)
    context: KnowledgeGraphContext = field(default_factory=KnowledgeGraphContext)
    entities: list[KnowledgeGraphEntity] = field(default_factory=list)
    relationships: list[KnowledgeGraphRelationship] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore."""
        return {
            "meta": {
                "title": self.meta.title,
                "type": self.meta.type,
                "topic": self.meta.topic,
                "keywords": self.meta.keywords,
                "tone": self.meta.tone,
                "author": self.meta.author,
                "date": self.meta.date,
            },
            "context": {
                "summary": self.context.summary,
                "mainPoints": self.context.main_points,
            },
            "entities": [
                {
                    "name": e.name,
                    "type": e.type,
                    "attributes": e.attributes,
                }
                for e in self.entities
            ],
            "relationships": [
                {
                    "source": r.source,
                    "action": r.action,
                    "target": r.target,
                    "context": r.context,
                }
                for r in self.relationships
            ],
        }


def parse_knowledge_graph(output: str) -> KnowledgeGraph:
    """
    Parse LLM output containing a YAML knowledge graph.

    Expected format:
    ```yaml
    meta:
      title: ...
      type: ...
      ...
    context:
      summary: ...
      main_points:
        - ...
    entities:
      - name: ...
        type: ...
        {attr}: ...
    relationships:
      - [entity1, action, entity2]
      - [entity1, action, entity2, context]
    ```

    Returns parsed KnowledgeGraph data structure.
    """
    kg = KnowledgeGraph()

    # Extract YAML content from code block
    yaml_match = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", output, re.DOTALL)
    if yaml_match:
        yaml_content = yaml_match.group(1)
    else:
        # Try to parse the entire output as YAML
        yaml_content = output

    try:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            print(f"Warning: YAML parsing returned non-dict type: {type(data)}")
            return kg
    except yaml.YAMLError as e:
        # Retry once after fixing common broken-quote issues
        try:
            fixed_yaml = fix_broken_quotes(yaml_content)
            data = yaml.safe_load(fixed_yaml)
            if not isinstance(data, dict):
                print(
                    f"Warning: YAML parsing (after fix) returned non-dict type: {type(data)}"
                )
                return kg
        except yaml.YAMLError as e2:
            print(f"Error parsing YAML (original): {e}")
            print(f"Error parsing YAML (after fix_broken_quotes): {e2}")
            return kg

    # Parse meta section
    if "meta" in data and isinstance(data["meta"], dict):
        meta = data["meta"]
        kg.meta = KnowledgeGraphMeta(
            title=str(meta.get("title", "")),
            type=str(meta.get("type", "")),
            topic=_ensure_list(meta.get("topic", [])),
            keywords=_ensure_list(meta.get("keywords", [])),
            tone=_ensure_list(meta.get("tone", [])),
            author=str(meta.get("author", "")),
            date=str(meta.get("date", "")),
        )

    # Parse context section
    if "context" in data and isinstance(data["context"], dict):
        context = data["context"]
        kg.context = KnowledgeGraphContext(
            summary=str(context.get("summary", "")),
            main_points=_ensure_list(context.get("main_points", [])),
        )

    # Parse entities section
    if "entities" in data and isinstance(data["entities"], list):
        for entity_data in data["entities"]:
            if not isinstance(entity_data, dict):
                continue
            name = str(entity_data.get("name", ""))
            entity_type = str(entity_data.get("type", "thing"))
            # Extract all other attributes (excluding name and type)
            attributes = {
                k: v for k, v in entity_data.items() if k not in ("name", "type")
            }
            if name:
                kg.entities.append(
                    KnowledgeGraphEntity(
                        name=name,
                        type=entity_type,
                        attributes=attributes,
                    )
                )

    # Parse relationships section
    if "relationships" in data and isinstance(data["relationships"], list):
        for rel_data in data["relationships"]:
            if isinstance(rel_data, list) and len(rel_data) >= 3:
                source = str(rel_data[0])
                action = str(rel_data[1])
                target = str(rel_data[2])
                context = str(rel_data[3]) if len(rel_data) > 3 else None
                kg.relationships.append(
                    KnowledgeGraphRelationship(
                        source=source,
                        action=action,
                        target=target,
                        context=context,
                    )
                )

    return kg


def _ensure_list(value: Any) -> list[str]:
    """Ensure a value is a list of strings."""
    if isinstance(value, list):
        return [str(item) for item in value]
    elif value:
        return [str(value)]
    return []


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
                }
                for q in self.questions
            ],
        }


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
