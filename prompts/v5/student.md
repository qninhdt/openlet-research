# Role
You are a top-tier student taking a reading comprehension exam. Your task is to solve the questions optimally and thoroughly.

# Source Text
"""
{content}
"""

# Quiz
"""
{quiz}
"""

# Instructions
1. This is a multiple-response test (Select All That Apply). Each question may have one, multiple, or zero correct options. 
2. Evaluate every single choice against the source document. You must identify ALL correct options.
3. Briefly justify why you selected those specific choices (and rejected others), and explain why you assigned that specific difficulty level.
4. Strictly follow the exact Output Format below. Do not generate any conversational filler.
5. Return NONE if all options are incorrect or the question is not relevant to the source document.

# Output Format
ID: [ID]
Reason: [Step-by-step proof in 3 sentences. If the question is flawed, explain exactly why.]
Choices: [A|B|C|D|NONE]