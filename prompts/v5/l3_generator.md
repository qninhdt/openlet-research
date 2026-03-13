# Role
You are an expert exam creator. Generate **exactly {n}** multiple-choice questions based on the text.

# Source Text
"""
{content}
"""

# Positive Samples
Review these examples of excellent Level 3 questions that perfectly match the required cognitive level. Emulate their style and difficulty:
"""
{positive_samples}
"""

# Negative Samples
Review these failed attempts. These questions were generated for Level 3 but were classified as a different level (e.g. they were just basic inference, or factual). AVOID generating similar questions:
"""
{negative_samples}
"""

## Level 3: Complex Logic & Multi-hop Reasoning (LSAT/GMAT Standard)
Objective: Assess the ability to connect disjointed facts, evaluate argument structures, and identify logical flaws or unstated premises.
Question Generation Requirements: DO NOT generate simple factual questions. Create questions that demand multi-hop reasoning (e.g., connecting a premise in Paragraph A to a consequence in Paragraph C). Alternatively, generate logical reasoning questions such as: "What is the core unstated assumption of the author?", "Which of the following, if true, would most weaken/strengthen the argument?", or "Apply the principle discussed in the text to a novel hypothetical scenario."
Answer & Distractor Criteria: Arriving at the correct answer must require the reader to synthesize at least 2-3 pieces of information separated by significant distance within the text. Distractors must be sophisticated traps: they should misapply the text's logic, reverse cause-and-effect relationships, or present plausible real-world assumptions that are NOT supported by the provided text.

# Step-by-Step Reasoning
Step 1: Complex Logic & Argument Identification. Analyze the Source Text to identify overarching arguments, unstated premises, or cause-and-effect relationships that span across multiple paragraphs. Do NOT target explicit facts or single-paragraph inferences.
Step 2: Constraint Check. Cross-reference your intended concept with the Negative Constraints list. If the logical structure or question stem is already covered, discard it and return to Step 1.
Step 3: Question Drafting. Formulate a question demanding multi-hop reasoning or logical evaluation. Use structures such as "Which of the following, if true, would most weaken/strengthen the author's argument...", "What is the unstated assumption connecting [Premise A] to [Conclusion B]?", or require applying a principle from the text to a novel, hypothetical scenario. Ensure the drafted question aligns with the style/difficulty of the # Positive Samples and avoids the pitfalls of the # Negative Samples.
Step 4: Option Engineering. 
   - Correct Answer: Must accurately identify the logical bridge/flaw or demand the synthesis of at least 2-3 pieces of information separated by significant distance in the text.
   - Distractors: Craft three sophisticated traps. They must misapply the text's logic, reverse cause-and-effect relationships, or present highly plausible real-world assumptions that are NOT supported by the specific text provided. Do not use obviously false statements.
Step 5: Final Validation. Confirm that the correct answer absolutely cannot be found by reading a single section or scanning for keywords. Ensure distractors act as logical traps rather than mere factual errors.

Note: You MUST explicitly use GMAT/LSAT question stems (e.g., "weaken the argument", "strengthen", "unstated assumption", "logical flaw", "hypothetical scenario"). DO NOT use standard inference stems like 'What can be inferred' or 'What does the author suggest'.

# Output Format
Generate EXACTLY {n} questions.

ID: [Sequential ID starting from the next available number]
Reason: [Plan your question blueprint strictly based on Level 3 rules. 1. Identify the logical task (e.g., Find unstated assumption, Weaken argument, Multi-hop connection). 2. Map the text: Explicitly state "I will connect premise A from paragraph X with conclusion B from paragraph Y". 3. Plan the distractors: State what logical fallacies or reversed causalities you will use for the wrong options to trap the reader.]
Question: [text]
A: [option]
B: [option]
C: [option]
D: [option]
Answer: [A|B|C|D]
