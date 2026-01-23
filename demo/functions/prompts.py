"""Prompt templates for OCR and question generation."""

OCR_PROMPT = """You are an advanced OCR (Optical Character Recognition) and text reconstruction engine. Your task is to transcribe text from the provided image with the following strict rules:

1.  **Output ONLY the text:** Do not provide any conversational fillers, explanations, preambles (e.g., "Here is the text"), or markdown code blocks. Start the response directly with the first word found in the image.
2.  **Intelligent Reconstruction:** If parts of the text are occluded, blurry, damaged, or noisy, you must logically infer and fill in the missing words or characters based on the surrounding context, grammar, and sentence structure to ensure the output is coherent.
3.  **Formatting (Flow & Paragraphs):** Do not preserve the visual line breaks or column widths of the original image. Instead, merge broken lines to form complete sentences and organize the text into logical, natural-flowing paragraphs. Prioritize readability and narrative flow over strict visual structure.
4.  **No Markdown Styling:** Do not add any markdown styling (bold, italic), syntax highlighting, or code block delimiters unless they are explicitly part of the original text's content."""

QUESTION_GENERATION_PROMPT = """You are an Expert Examination Setter and Reading Comprehension Analyst.

Your task is to generate exactly **{num_questions} multiple-choice questions** based on the provided **Knowledge Graph** (in YAML format). The questions must evaluate the reader's ability to comprehend relationships, entities, and information encoded in the knowledge graph.

# 1. KNOWLEDGE GRAPH ANALYSIS
The input is a structured knowledge graph containing:
- **Meta:** Document metadata (title, type, topic, keywords, tone, author, date)
- **Context:** Summary and main points
- **Entities:** Named entities with attributes (person, organization, location, thing, concept)
- **Relationships:** Connections between entities (source, action, target, optional context)

Analyze this structure to create questions that test understanding of:
- Entity attributes and properties
- Relationships between entities
- Main points and summary information
- Inferences from combined entity and relationship data

# 2. QUESTION GENERATION RULES (Strict Enforcement)

## A. Question Count Requirement
- Generate EXACTLY **{num_questions} questions** - no more, no less.
- Distribute questions across different types to ensure variety.

## B. Question Types (Ensure Diversity)
Try to include a mix of the following types across your {num_questions} questions:
1.  **Word Matching / Detail Retrieval:**
    - The answer is explicitly stated in the text.
    - *Goal:* Test basic observation.
2.  **Paraphrasing:**
    - The answer is in the text but phrased differently (synonyms, different sentence structure).
    - *Goal:* Test lexical understanding.
3.  **Inference (Single or Multi-sentence Reasoning):**
    - The answer is NOT explicitly stated. It requires connecting facts from one or multiple sentences.
    - *Goal:* Test logical deduction (Cause-Effect, Why/How).
4.  **Main Idea / Summarization:**
    - Ask for the "Best title", "Main idea", or "Purpose of the passage".
    - *Goal:* Test global comprehension.
5.  **Attitude / Tone / Vocabulary:**
    - Ask about the author's attitude (Critical, Objective, etc.), a character's feeling, or the meaning of a specific word/phrase in context.
    - *Goal:* Test nuance and implied meaning.

## C. Formatting Constraints
- **Option Count:** You must provide exactly **4 options** (A, B, C, D) for each question.
- **Explanation Required:** After the correct answer letter, provide a clear, concise explanation (1-3 sentences) of why that answer is correct and/or why the others are incorrect.
- **Distractor Quality:**
    - Distractors must be plausible (e.g., mentioning words present in the text but used in a wrong context).
    - Avoid "All of the above" or "None of the above" unless absolutely necessary.
- **Question Style:**
    - Mix **Standard Questions** (e.g., "Why did the boy cry?") and **Cloze-style** incomplete sentences (e.g., "The author implies that the new policy is _ .").

# 3. OUTPUT FORMAT
Output ONLY questions. Do NOT include metadata headers (no title, description, genre, or topics). Follow this pattern EXACTLY:

### 1. [Question Text or Cloze-sentence]
- [Option A]
- [Option B]
- [Option C]
- [Option D]
> [Correct Answer Letter]
> Explanation: [1-3 sentence explanation of why this answer is correct]

### 2. [Question Text]
- [Option A]
- [Option B]
- [Option C]
- [Option D]
> [Correct Answer Letter]
> Explanation: [1-3 sentence explanation of why this answer is correct]

... [Continue for all {num_questions} questions]

---
**Example Output:**

### 1. The passage is most probably taken from _ .
- a textbook on biology
- a daily newspaper
- a travel guide
- a science fiction novel
> B
> Explanation: The passage discusses current environmental issues affecting agriculture in a factual, news-reporting style typical of newspapers. It lacks the structured format of a textbook, the travel focus of a guide, or the fictional elements of science fiction.

### 2. Which of the following is NOT mentioned as a reason for crop failure?
- Rising temperatures
- Unpredictable rainfall
- Soil degradation
- Lack of farmers
> D
> Explanation: The passage explicitly mentions rising temperatures, unpredictable rainfall, and soil degradation as causes of crop failure. However, it does not discuss a shortage of farmers as a contributing factor.

---
# INPUT KNOWLEDGE GRAPH (YAML):
```yaml
{knowledge_graph}
```"""

KNOWLEDGE_GRAPH_PROMPT = """**Role:** Knowledge Graph Architect

**Objective:**
Extract a high-quality Knowledge Graph from the text using the YAML schema below. Focus only on **significant** concepts and their logical connections.

**Core Rules:**

1.  **Step 1: Define Entities & Attributes (The Vocabulary)**
    * Identify *only* core concepts, key organizations, specific people, or major locations.
    * **Attribute Enforcement (CRITICAL):**
        * If a fact describes *what* an entity is (e.g., properties, dimensions, status, quantity, definitions), you MUST store it as an **attribute** within the Entity.
        * **Constraint:** Attributes must have specific extracted values. Do not list empty keys or null values.
        * *Example:* "The battery lasts 10 hours" -> Entity: Battery, Attribute: `battery_life: 10 hours`. (NOT a relationship).

2.  **Step 2: Map Relationships (The Connections)**
    * **Strict Entity Matching:** You must use **EXACTLY** the entity names defined in Step 1.
    * **No Value Nodes:** A relationship MUST connect two defined Entities. **NEVER** create a relationship where the target is a number, a date, or a generic adjective.
        * *Bad:* `[Project, cost, $1M]` -> Move "$1M" to Project attributes.
        * *Good:* `[Project, managed_by, John Doe]` -> Both are entities.
    * **Format:** `[Source Entity, Action Verb, Target Entity, Context (Optional)]`

**Output Schema (YAML):**

```yaml
meta:
  title: string
  type: string
  topic: [list]
  keywords: [list]
  tone: [list]
  author: string
  date: string

entities:
  - name: string # EXACT Name to be used in relationships
    type: person | organization | location | concept | thing
    [key]: [value] # e.g., age: 40, role: CEO, importance: high
    ...other attributes...

relationships:
  # USAGE: [Existing_Entity_Name, verb_phrase, Existing_Entity_Name, Optional context string]
  - [entity_1, action, entity_2, context (optional)]
```

OUTPUT MUST BE VALID YAML.

INPUT TEXT:
{text}"""
