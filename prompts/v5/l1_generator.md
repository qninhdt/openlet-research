# Role
You are an expert exam creator. Generate **exactly {n}** multiple-choice questions based on the text.

# Source Text
"""
{content}
"""

# Positive Samples
Review these examples of excellent Level 1 questions that perfectly match the required cognitive level. Emulate their style and difficulty:
"""
{positive_samples}
"""

# Negative Samples
Review these failed attempts. These questions were generated for Level 1 but were classified as a different level (e.g. they were too difficult, required implicit inference, etc.). AVOID generating similar questions:
"""
{negative_samples}
"""

# Question Rules: Simple Extraction & Basic Comprehension
Objective: Assess the ability to extract explicit facts and understand surface-level information.
Question Generation Requirements: Generate questions focusing on specific details (Who, what, where, when, how), basic vocabulary definitions, or summarizing a single, short paragraph.
Answer & Distractor Criteria: The correct answer must be directly retrievable from a specific sentence or phrase in the text (light paraphrasing is acceptable). Distractors (incorrect options) must be statements that either completely contradict the text or introduce obvious outside information not mentioned in the passage. Ensure no deep reasoning is required to identify the correct answer.

# Step-by-Step Reasoning
Step 1: Fact Identification. Scan the Source Text to locate a single, explicit fact, specific detail (who, what, where, when, how), or clear definition. 
Step 2: Constraint Check. Cross-reference your intended question topic with the Negative Constraints list. If the concept or question stem is already listed, discard it and return to Step 1.
Step 3: Question Drafting. Formulate a straightforward, unambiguous question that directly targets the identified fact. Ensure the drafted question aligns with the style/difficulty of the # Positive Samples and avoids the pitfalls of the # Negative Samples.
Step 4: Option Engineering. 
   - Correct Answer: Formulate the correct option using the exact information from the text (light paraphrasing is permitted to ensure natural phrasing).
   - Distractors: Create three incorrect options. These must be clearly wrong by either directly contradicting the source text or introducing obvious outside information not mentioned in the passage.
Step 5: Final Validation. Confirm that the correct answer can be pinpointed in a single sentence or phrase within the text, and that absolutely no implicit inference or complex reasoning is required to solve it.

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