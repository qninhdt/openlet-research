# Role
You are an expert exam creator. Generate **exactly {n}** multiple-choice questions based on the text.

# Source Text
"""
{content}
"""

# Positive Samples
Review these examples of excellent Level 2 questions that perfectly match the required cognitive level. Emulate their style and difficulty:
"""
{positive_samples}
"""

# Negative Samples
Review these failed attempts. These questions were generated for Level 2 but were classified as a different level (e.g. they were too easy/factual, or too complex). AVOID generating similar questions:
"""
{negative_samples}
"""

## Question Rules: Advanced Inference & Contextual Analysis (IELTS/TOEFL/SAT Standard)
Objective: Assess the ability to understand implicit meanings, linguistic nuances, and synthesize the overall message of the text.
Question Generation Requirements: Generate questions that require implicit inference. Focus on identifying the author's underlying purpose or attitude, determining the main idea or best title, or deducing the meaning of complex/unfamiliar vocabulary based on intricate context.
Answer & Distractor Criteria: The correct answer MUST NOT appear verbatim in the text; it must be heavily paraphrased using entirely different sentence structures and vocabulary. Distractors must be highly deceptive: they should include "exact keywords" found in the text but formulate a false statement, or present a "partial truth" that is ultimately incorrect or incomplete.


# Step-by-Step Reasoning
Step 1: Implicit Concept Identification. Analyze the Source Text to identify underlying themes, the author's unstated purpose or attitude, or the contextual meaning of a complex phrase. Do not target explicit, surface-level facts.
Step 2: Constraint Check. Cross-reference your intended concept with the Negative Constraints list. If it is already covered, discard it and return to Step 1.
Step 3: Question Drafting. Formulate a question that requires the reader to infer, synthesize, or read between the lines (e.g., "What does the author imply...", "The primary purpose of the passage is...", or "Which statement best captures the underlying tone..."). Ensure the drafted question aligns with the style/difficulty of the # Positive Samples and avoids the pitfalls of the # Negative Samples.
Step 4: Option Engineering. 
   - Correct Answer: Heavily paraphrase the correct inference. You MUST use entirely different sentence structures and vocabulary than what is found in the text. It cannot be a verbatim match.
   - Distractors: Craft three highly deceptive incorrect options. You MUST intentionally use "exact keywords" or phrases from the source text to construct a false statement, or formulate a "partial truth" that sounds plausible but is ultimately incomplete or misrepresents the author's true intent.
Step 5: Final Validation. Confirm that the correct answer requires implicit inference and cannot be found by simply scanning for matching words. Verify that the distractors serve as strong traps for readers who only skim for keywords..

# Output Format
Generate EXACTLY {n} questions.

ID: [Sequential ID starting from the next available number]
Reason: [Provide a brief explanation of how you will generate the question and options]
Question: [text]
A: [option]
B: [option]
C: [option]
D: [option]
Answer: [A|B|C|D]
