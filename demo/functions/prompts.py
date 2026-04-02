"""Prompt templates for OCR, analysis, and multi-agent question generation."""

OCR_PROMPT = """You are an advanced OCR (Optical Character Recognition) and text reconstruction engine. Your task is to transcribe text from the provided image with the following strict rules:

1.  **Output ONLY the text:** Do not provide any conversational fillers, explanations, preambles (e.g., "Here is the text"), or markdown code blocks. Start the response directly with the first word found in the image.
2.  **Intelligent Reconstruction:** If parts of the text are occluded, blurry, damaged, or noisy, you must logically infer and fill in the missing words or characters based on the surrounding context, grammar, and sentence structure to ensure the output is coherent.
3.  **Formatting (Flow & Paragraphs):** Do not preserve the visual line breaks or column widths of the original image. Instead, merge broken lines to form complete sentences and organize the text into logical, natural-flowing paragraphs. Prioritize readability and narrative flow over strict visual structure.
4.  **No Markdown Styling:** Do not add any markdown styling (bold, italic), syntax highlighting, or code block delimiters unless they are explicitly part of the original text's content."""

# ============================================================================
# SINGLE PROMPT MODE
# ============================================================================

SINGLE_PROMPT_QUESTION_GENERATION = """# Role
You are an expert Psychometrician and Exam Creator specializing in standardized testing (IELTS, SAT, LSAT, GMAT).

# Task
Your task is to generate a total of **{total_questions}** multiple-choice questions based on the provided text.
You must generate exactly:
- **{n_1} questions for Level 1** (Retrieval)
- **{n_2} questions for Level 2** (Inference & Synthesis)
- **{n_3} questions for Level 3** (Critical Reasoning & Abstract Logic)

# Input Text
\"\"\"
{text}
\"\"\"

# Level Definitions & Constraints

## Level 1: Retrieval (Basic Information)
*Standard: Elementary Reading Comprehension / Basic Fact-Checking.*
*Goal: Test visual scanning and keyword matching.*

1. **Question Stem Features:**
   - **Explicit Inquiry:** Ask directly about Named Entities (Who, When, Where, How many, What specific item).
   - **Keyword Mapping:** Include 1-2 anchor words exactly as they appear in the text to allow easy location.
   - **Single-Sentence Focus:** The answer must be found within a single sentence.

2. **Correct Answer Features:**
   - **Verbatim Extraction:** Copy-paste the exact phrase, number, date, or name from the text.

3. **Distractor Features:**
   - **Factual Error:** Change the specific number or data point (e.g., change "50%" to "5%").
   - **Jumbled Context:** Use a correct keyword/entity from the text but from a different, unrelated paragraph.
   - **Visual Similarity:** Use words/numbers that look similar (e.g., "1945" vs "1954").

---

## Level 2: Inference & Synthesis (Comprehension)
*Standard: SAT Reading, TOEFL, IELTS (High Band).*
*Goal: Test understanding of meaning, connection, and paraphrasing. Defeat "keyword scanning".*

1. **Question Stem Features:**
   - **Synthesis:** Require combining information from at least 2 different sentences/paragraphs (e.g., A causes B, B causes C → What is the relation between A and C?).
   - **Paraphrased Inquiry:** **DO NOT** use keywords from the text. Use synonyms or rephrased descriptions.
   - **Global Comprehension:** Ask about Main Idea, Author's Purpose, Tone, or Implied Meaning ("It can be inferred that...").

2. **Correct Answer Features:**
   - **Semantic Equivalence:** The answer must mean the same as the text but use completely different vocabulary/structure (translation of meaning).

3. **Distractor Features (CRITICAL):**
   - **The Verbatim Trap (Copycat):** Options that contain **exact keywords** from the text but are factually incorrect or misused. (This traps Level 1 models.)
   - **Partial Truth:** One part is correct, the other part is false.
   - **Causality Confusion:** Reversing cause and effect.
   - **Over-generalization:** Changing "some" to "all/always".

---

## Level 3: Critical Reasoning & Abstract Logic (Application)
*Standard: LSAT Logical Reasoning, GMAT Critical Reasoning.*
*Goal: Test logic, application, and critical evaluation. Identify logical structure independent of content.*

1. **Question Stem Features:**
   - **Abstraction & Application:** Create a **Hypothetical Scenario** NOT mentioned in the text and ask to apply the text's rules/principles to it.
   - **Logical Evaluation:** Ask for Underlying Assumptions, Logical Flaws, or Strengthening/Weakening evidence.
   - **Structural Mapping:** Ask to identify a parallel argument with the same logical structure.

2. **Correct Answer Features:**
   - **Necessary Consequence:** Must be logically deduced.
   - **External Validator:** Can introduce NEW information (for strengthen/weaken questions) that logically impacts the argument.

3. **Distractor Features (CRITICAL):**
   - **The "So What?" (Irrelevance):** Facts that are true (even mentioned in text) but do not logically affect the specific argument being made.
   - **Out of Scope:** Generalizations that go beyond the text's evidence context.
   - **Reverse Causality:** Confusing the direction of logic.
   - **Emotional Trap:** Options that sound ethically/politically correct but are logically irrelevant.

---

# Metadata Extraction
Before generating questions, extract the following metadata from the text:
- **Title:** A concise title that captures the main topic of the text.
- **Topics:** A comma-separated list of 1-3 main topics covered in the text.
- **Description:** A 2-3 sentence summary of the text.

# Output Format
Generate the output in the following format. Do not include conversational fillers, intro or outro.
Start with the metadata block, then all {total_questions} questions numbered sequentially.
Each question MUST include a `Level:` tag immediately after the question heading.

Title: [Extracted title]
Topics: [Topic 1, Topic 2, ...]
Description: [Brief summary]

---

### [Number]. [Question Text]
Level: [1|2|3]
- [Option A]
- [Option B]
- [Option C]
- [Option D]
> [Correct Answer Letter]
> Explanation: [1-3 sentences explaining why this answer is correct and why the others are wrong]

### Example Output (For Reference Only)

### 1. According to the text, in which year was the Treaty of Paris signed?
Level: 1
- 1781
- 1783
- 1785
- 1873
> B
> Explanation: The text explicitly states "the Treaty of Paris was signed in 1783." The other options are plausible years near that period but are not mentioned in relation to this treaty.

### 2. What does the author imply about the relationship between industrialization and urbanization in the second paragraph?
Level: 2
- They are unrelated processes in the economic cycle.
- Urbanization is the primary cause of industrial decline.
- Industrialization acts as a catalyst for rapid urbanization.
- Urbanization prevents the spread of industrial technology.
> C
> Explanation: The author describes how factory growth drew workers into cities, implying industrialization drives urbanization. Option A contradicts this connection; B and D reverse the causal direction described in the passage."""


# ============================================================================
# MULTI-AGENT MODE: ANALYZER
# ============================================================================

ANALYZER_PROMPT = """# Role
You are an Expert Knowledge Miner and Logic Analyst.
Your task is to extract all useful information from the text to build a "Knowledge Base" for creating standardized exam questions (IELTS/SAT/LSAT).

# Input Text
\"\"\"
{content}
\"\"\"

# Objective
Extract raw data and logical structures. **Do not categorize by Question Level.** Categorize by **Information Type**.
Keep the output specific, retaining the original context so the Question Generator understands the "Why" and "How".

# Extraction Schema

## 1. METADATA
* **Title:** A concise title that captures the main topic of the text.
* **Topic:** A list of 1-3 main topics covered in the text.
* **Domain:** The subject area (e.g., Science, History, Literature).
* **Tone:** The writing style (e.g., Academic, Narrative, Persuasive).
* **Summary:** A 2-3 sentence summary of the text.

## 2. ENTITY & FACT
*Goal: Extract specific nouns/data for Retrieval questions.*
* **Entity:** Proper Nouns (People, Organizations, Places).
* **Fact:** Technical Terms, Numbers, Dates, Statistics.
* **Requirement:** Brief context explaining its role.

## 3. MECHANISM
*Goal: Extract logic flow for Comprehension questions.*
* Find sentences explaining **WHY** something happens or **HOW** a process works.
* Find explicit purposes (e.g., "in order to...", "so that...").
* Format using arrows to show the flow.

## 4. ARGUMENTATION
*Goal: Extract reasoning for Critical Reasoning questions.*
* **Conclusion:** The main point/claim the author is proving.
* **Premise:** The evidence/reasons used to support the conclusion.
* **Constraint:** Specific limitations or conditions (Scope).

## 5. VERBATIM TRIGGERS
*Goal: Extract exact phrases for Distractor Traps.*
* Catchy phrases, specific lists, or complex terms that a careless reader might recognize visually but misunderstand.
* Must be exact quotes.

# Output Format

# Metadata
- Title: ...
- Topic: ...
- Domain: ...
- Tone: ...
- Summary: ...

# Entity
- Name: Context/Role
- Name: Context/Role

# Fact
- Term/Number: Context/Definition
- Term/Number: Context/Definition

# Mechanism
- Cause/Action -> Result/Purpose
- Cause/Action -> Result/Purpose

# Argumentation
- Conclusion: ...
- Premise: ...
- Constraint: ...

# Verbatim Triggers
- "..."
- "..." """

# ============================================================================
# MULTI-AGENT MODE: LEVEL 1 (Retrieval)
# ============================================================================

LEVEL1_GENERATOR_PROMPT = """# Role
You are an expert Psychometrician and Exam Creator specializing in standardized testing (IELTS, SAT, LSAT, GMAT).

# Task
Your task is to generate exactly {n} Question and Option pairs for **Level 1: Retrieval (Basic Information)**.

Strictly control output length. The Question Stem must be concise and the Correct Answer must be succinct to ensure readability in a standard multiple-choice layout.

# Input Data

## 1. Original Text
\"\"\"
{content}
\"\"\"

## 2. Structured Analysis
\"\"\"
{analyzer_output}
\"\"\"

# Level 1: Retrieval (Basic Information)
*Standard: Elementary Reading Comprehension / Basic Fact-Checking.*
*Goal: Test visual scanning and keyword matching.*

1. Question Stem Features:
   - Explicit Inquiry: Ask directly about Named Entities (Who, When, Where, How many, What specific item).
   - Keyword Mapping: Include 1-2 anchor words exactly as they appear in the text to allow easy location.
   - Single-Sentence Focus: The answer must be found within a single sentence.

2. Correct Answer Features:
   - Verbatim Extraction: Copy-paste the exact phrase, number, date, or name from the text.

3. Distractor Features:
   - Factual Error: Change the specific number or data point (e.g., change "50%" to "5%").
   - Jumbled Context: Use a correct keyword/entity from the text but from a different, unrelated paragraph.
   - Visual Similarity: Use words/numbers that look similar (e.g., "1945" vs "1954").

# Output Format
Provide the output in the following format. Do not output conversational fillers. No headings between questions.

You must generate exactly 4 options (A, B, C, D) for each question. One option is the correct answer, and three are distractors.

## Template

ID: Index Number
Question: Question Text
A: Option A
B: Option B
C: Option C
D: Option D
Answer: A|B|C|D"""


# ============================================================================
# MULTI-AGENT MODE: LEVEL 2 (Inference & Synthesis)
# ============================================================================

LEVEL2_GENERATOR_PROMPT = """# Role
You are an expert Psychometrician and Exam Creator specializing in standardized testing (IELTS, SAT, LSAT, GMAT).

# Task
Your task is to generate exactly {n} Question and Option pairs for **Level 2: Inference & Synthesis (Comprehension)**.

Strictly control output length. The Question Stem must be concise and the Correct Answer must be succinct to ensure readability in a standard multiple-choice layout.

# Input Data

## 1. Original Text
\"\"\"
{content}
\"\"\"

## 2. Structured Analysis
\"\"\"
{analyzer_output}
\"\"\"

# Level 2: Inference & Synthesis (Comprehension)
*Standard: SAT Reading, TOEFL, IELTS (High Band).*
*Goal: Test understanding of meaning, connection, and paraphrasing. Defeat "keyword scanning".*

1. Question Stem Features:
   - Synthesis: Require combining information from at least 2 different sentences/paragraphs (e.g., A causes B, B causes C -> What is relation between A and C?).
   - Paraphrased Inquiry: DO NOT use keywords from the text. Use synonyms or rephrased descriptions.
   - Global Comprehension: Ask about Main Idea, Author's Purpose, Tone, or Implied Meaning ("It can be inferred that...").

2. Correct Answer Features:
   - Semantic Equivalence: The answer must mean the same as the text but use completely different vocabulary/structure (Translation of meaning).

3. Distractor Features (CRITICAL):
   - The Verbatim Trap (Copycat): Options that contain exact keywords from the text but are factually incorrect or misused. (This traps Level 1 models).
   - Partial Truth: One part is correct, the other part is false.
   - Causality Confusion: Reversing cause and effect.
   - Over-generalization: Changing "some" to "all/always".

# Output Format
Provide the output in the following format. Do not output conversational fillers. No headings between questions.

You must generate exactly 4 options (A, B, C, D) for each question. One option is the correct answer, and three are distractors.

## Template

ID: Index Number
Question: Question Text
A: Option A
B: Option B
C: Option C
D: Option D
Answer: A|B|C|D"""


# ============================================================================
# MULTI-AGENT MODE: LEVEL 3 (Critical Reasoning)
# ============================================================================

LEVEL3_GENERATOR_PROMPT = """# Role
You are an expert Psychometrician and Exam Creator specializing in standardized testing (IELTS, SAT, LSAT, GMAT).

# Task
Your task is to generate exactly {n} Question and Option pairs for **Level 3: Critical Reasoning & Abstract Logic (Application)**.

Strictly control output length. The Question Stem must be concise and the Correct Answer must be succinct to ensure readability in a standard multiple-choice layout.

# Input Data

## 1. Original Text
\"\"\"
{content}
\"\"\"

## 2. Structured Analysis
\"\"\"
{analyzer_output}
\"\"\"

# Level 3: Critical Reasoning & Abstract Logic (Application)
*Standard: LSAT Logical Reasoning, GMAT Critical Reasoning.*
*Goal: Test logic, application, and critical evaluation. Identify logical structure independent of content.*

1. Question Stem Features:
   - Abstraction & Application: Create a Hypothetical Scenario NOT mentioned in the text and ask to apply the text's rules/principles to it.
   - Logical Evaluation: Ask for Underlying Assumptions, Logical Flaws, or Strengthening/Weakening evidence.
   - Structural Mapping: Ask to identify a parallel argument with the same logical structure.

2. Correct Answer Features:
   - Necessary Consequence: Must be logically deduced.
   - External Validator: Can introduce NEW information (for strengthen/weaken questions) that logically impacts the argument.

3. Distractor Features (CRITICAL):
   - The "So What?" (Irrelevance): Facts that are true (even mentioned in text) but do not logically affect the specific argument being made.
   - Out of Scope: Generalizations that go beyond the text's evidence context.
   - Reverse Causality: Confusing the direction of logic.
   - Emotional Trap: Options that sound ethically/politically correct but are logically irrelevant.

# Output Format
Provide the output in the following format. Do not output conversational fillers. No headings between questions.

You must generate exactly 4 options (A, B, C, D) for each question. One option is the correct answer, and three are distractors.

## Template

ID: Index Number
Question: Question Text
A: Option A
B: Option B
C: Option C
D: Option D
Answer: A|B|C|D"""


# ============================================================================
# MULTI-AGENT MODE: EXPLANATION AGENT (runs after merge)
# ============================================================================

EXPLANATION_PROMPT = """# Role
You are an expert educator who provides clear, precise explanations for multiple-choice exam questions.

# Task
For each question below, write a concise explanation (2-4 sentences) that:
1. States **why the correct answer is right**, referencing the source text.
2. Briefly explains **why at least one popular distractor is wrong** (optional but helpful).
3. Uses simple, student-friendly language.

# Input Data

## Source Text
\"\"\"
{content}
\"\"\"

## Questions
{questions}

# Output Format

For **each** question, output in this exact format. Do not skip any question.

ID: [Question ID]
Explanation: [2-4 sentence explanation]

## Example

ID: 1
Explanation: The text states in paragraph 2 that photosynthesis converts carbon dioxide into glucose, making option B correct. Option A is wrong because it reverses the process - glucose is a product, not an input.

ID: 2
Explanation: According to the passage, the treaty was signed in 1648, which matches option C. Option D (1658) is a common date-confusion distractor based on a nearby event mentioned later in the text."""

# ============================================================================
# MULTI-AGENT MODE: CLASSIFIER (verifies difficulty level)
# ============================================================================

CLASSIFIER_PROMPT = """# Role
You are an expert psychometrician. Your task is to verify the cognitive level of each multiple-choice question.

# Source Text
\"\"\"
{content}
\"\"\"

# Quiz
\"\"\"
{quiz}
\"\"\"

# Level Definitions

## Level 1: Simple Extraction & Basic Comprehension
Objective: Assess the ability to extract explicit facts and understand surface-level information.
Question Generation Requirements: Generate questions focusing on specific details (Who, what, where, when, how), basic vocabulary definitions, or summarizing a single, short paragraph.
Answer & Distractor Criteria: The correct answer must be directly retrievable from a specific sentence or phrase in the text (light paraphrasing is acceptable). Distractors (incorrect options) must be statements that either completely contradict the text or introduce obvious outside information not mentioned in the passage. Ensure no deep reasoning is required to identify the correct answer.

## Level 2: Advanced Inference & Contextual Analysis (IELTS/TOEFL/SAT Standard)
Objective: Assess the ability to understand implicit meanings, linguistic nuances, and synthesize the overall message of the text.
Question Generation Requirements: Generate questions that require implicit inference. Focus on identifying the author's underlying purpose or attitude, determining the main idea or best title, or deducing the meaning of complex/unfamiliar vocabulary based on intricate context.
Answer & Distractor Criteria: The correct answer MUST NOT appear verbatim in the text; it must be heavily paraphrased using entirely different sentence structures and vocabulary. Distractors must be highly deceptive: they should include "exact keywords" found in the text but formulate a false statement, or present a "partial truth" that is ultimately incorrect or incomplete.

## Level 3: Complex Logic & Multi-hop Reasoning (LSAT/GMAT Standard)
Objective: Assess the ability to connect disjointed facts, evaluate argument structures, and identify logical flaws or unstated premises.
Question Generation Requirements: DO NOT generate simple factual questions. Create questions that demand multi-hop reasoning (e.g., connecting a premise in Paragraph A to a consequence in Paragraph C). Alternatively, generate logical reasoning questions such as: "What is the core unstated assumption of the author?", "Which of the following, if true, would most weaken/strengthen the argument?", or "Apply the principle discussed in the text to a novel hypothetical scenario."
Answer & Distractor Criteria: Arriving at the correct answer must require the reader to synthesize at least 2-3 pieces of information separated by significant distance within the text. Distractors must be sophisticated traps: they should misapply the text's logic, reverse cause-and-effect relationships, or present plausible real-world assumptions that are NOT supported by the provided text.

# Instructions
Step 1: Evidence Tracing (The "Hop" Test). Identify exactly where the evidence for the correct answer is located. Is it in one sentence (L1), one paragraph's context (L2), or does it strictly require connecting independent facts from completely different paragraphs (L3)?
Step 2: Distractor Diagnostic. Are distractors obvious lies (L1), deceptive partial truths (L2), or sophisticated logical fallacies/unsupported assumptions (L3)?
Step 3: Output Level based strictly on the highest cognitive hurdle identified in Steps 1 and 2.

# Output Format
ID: [ID]
Reason: [Explanation of the cognitive level]
Level: [1|2|3]"""

# ============================================================================
# MULTI-AGENT MODE: STUDENT (attempts to solve questions)
# ============================================================================

STUDENT_PROMPT = """# Role
You are a top-tier student taking a reading comprehension exam. Your task is to solve the questions optimally and thoroughly.

# Source Text
\"\"\"
{content}
\"\"\"

# Quiz
\"\"\"
{quiz}
\"\"\"

# Instructions
1. This is a multiple-response test (Select All That Apply). Each question may have one, multiple, or zero correct options.
2. Evaluate every single choice against the source document. You must identify ALL correct options.
3. Briefly justify why you selected those specific choices (and rejected others), and explain why you assigned that specific difficulty level.
4. Strictly follow the exact Output Format below. Do not generate any conversational filler.
5. Return NONE if all options are incorrect or the question is not relevant to the source document.

# Output Format
ID: [ID]
Reason: [Step-by-step proof in 3 sentences. If the question is flawed, explain exactly why.]
Choices: [A|B|C|D|NONE]"""

# ============================================================================
# MULTI-AGENT MODE: FIXER (fixes options for questions the student got wrong)
# ============================================================================

FIXER_PROMPT = """# Role
You are an expert question repair specialist. Your task is to analyze and fix flawed multiple-choice questions based on diagnostic feedback from a Student Agent.

# Source Text
\"\"\"
{content}
\"\"\"

# Structured Analysis
\"\"\"
{analyzer_output}
\"\"\"

# Questions to Fix
\"\"\"
{failed_questions}
\"\"\"

# Level Definitions

## Level 1: Simple Extraction & Basic Comprehension
Objective: Assess the ability to extract explicit facts and understand surface-level information.
Answer & Distractor Criteria: The correct answer must be directly retrievable from a specific sentence or phrase in the text. Distractors must either completely contradict the text or introduce obvious outside information.

## Level 2: Advanced Inference & Contextual Analysis (IELTS/TOEFL/SAT Standard)
Objective: Assess the ability to understand implicit meanings, linguistic nuances, and synthesize the overall message of the text.
Answer & Distractor Criteria: The correct answer MUST NOT appear verbatim in the text. Distractors must include "exact keywords" found in the text but formulate a false statement, or present a "partial truth."

## Level 3: Complex Logic & Multi-hop Reasoning (LSAT/GMAT Standard)
Objective: Assess the ability to connect disjointed facts, evaluate argument structures, and identify logical flaws or unstated premises.
Answer & Distractor Criteria: Arriving at the correct answer must require synthesizing at least 2-3 pieces of information. Distractors must misapply logic, reverse cause-and-effect, or present unsupported assumptions.

# Diagnostic Information

Each question to fix includes:
- **Student Choices**: What the Student Agent selected (correct letter, multiple letters, or NONE)
- **Student Reason**: Why the Student Agent made that choice
- **Current Question Stem**
- **Current 4 Options (A-D)**
- **Correct Answer**

# Fix Rules
- You may modify only the options and answer key.
- Do not change the question text, level, or topic.
- Use the student's reasoning and choices to identify the flaw in the options (e.g., ambiguity, multiple correct options, or no correct options).
- Rewrite the options to remove the overlap or fix the ambiguity.
- Each question must have exactly 4 options (A, B, C, D) with exactly one correct answer.

# Output Format

ID: [Original ID]
Reason: [Why the original options were flawed and how you fixed them]
A: [Option A]
B: [Option B]
C: [Option C]
D: [Option D]
Answer: [A|B|C|D]"""
