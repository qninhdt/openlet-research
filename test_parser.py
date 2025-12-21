#!/usr/bin/env python3
"""Test the parser with sample output"""

import re
from question import parse_llm_output

# Test case 1: Normal format with ### separator and > answer line
sample_output_1 = """### What is the main idea of the passage?
- The importance of education
- The history of technology
- The benefits of exercise
- The dangers of pollution
> A

### According to the passage, what happened first?
- The storm arrived
- People evacuated
- The warning was issued
- The power went out
> C

### The author's tone can be described as _.
- optimistic
- pessimistic
- neutral
- angry
> A

### Why did the character decide to leave?
- He was scared
- He was tired
- He was bored
- He was angry
> A

### The word "it" in paragraph 2 refers to _.
- the book
- the house
- the car
- the chair
> B"""

# Test case 2: With extra newlines (should handle gracefully)
sample_output_2 = """### What is the main theme?


- Love


- War
- Peace

- Freedom
> C

### Who is the protagonist?
- John

- Mary
- Bob
- Alice

> A
"""

# Test case 3: Mixed formatting with extra blank lines
sample_output_3 = """
### First question here?
- Option A
- Option B
- Option C
- Option D
> B

### Second question here?

- Another option A
- Another option B

- Another option C
- Another option D

> D
"""

# Test case 4: Edge case with ## (two hash marks)
sample_output_4 = """## What is the capital of France?
- London
- Paris
- Berlin
- Madrid
> B

## What is 2 + 2?
- 3
- 4
- 5
- 6
> B"""

# Test case 5: Edge case with # (single hash mark)
sample_output_5 = """# Who wrote Hamlet?
- Charles Dickens
- William Shakespeare
- Jane Austen
- Mark Twain
> B

# What color is the sky?
- Red
- Blue
- Green
- Yellow
> B"""

# Test case 6: Mixed hash marks (###, ##, #)
sample_output_6 = """### Question with three hashes?
- Option A
- Option B
- Option C
- Option D
> A

## Question with two hashes?
- Option A
- Option B
- Option C
- Option D
> C

# Question with one hash?
- Option A
- Option B
- Option C
- Option D
> D"""

# Test case 7: Multiple consecutive underscores in question
sample_output_7 = """### The word "brilliant" in paragraph 2 can be replaced by _______.
- smart
- dull
- average
- mediocre
> A

### According to the passage, the main theme is ____________.
- friendship
- betrayal
- adventure
- romance
> C

### The author's attitude towards technology can be described as _____.
- positive
- negative
- neutral
- indifferent
> A"""

# Test case 8: Options with various incorrect prefixes
sample_output_8 = """### What is the capital of France?
- A. Paris
- B. London
- C. Berlin
- D. Madrid
> A

### What color is the sky?
- A) Blue
- B) Red
- C) Green
- D) Yellow
> A

### Who invented the telephone?
- A/ Alexander Graham Bell
- B/ Thomas Edison
- C/ Nikola Tesla
- D/ Albert Einstein
> A

### What is 2 + 2?
- A, Four
- B, Three
- C, Five
- D, Six
> A"""

# Test case 9: Mixed incorrect prefixes
sample_output_9 = """### Mixed prefix question 1?
- a. lowercase option a
- b. lowercase option b
- c. lowercase option c
- d. lowercase option d
> B

### Mixed prefix question 2?
- A option with just letter and space
- B another option
- C third option
- D fourth option
> C

### Mixed prefix question 3?
- a) lowercase with parenthesis
- b) another lowercase
- c) third one
- d) fourth one
> D"""

# Test case 10: Multiple prefix patterns in one output
sample_output_10 = """### Question 1?
- A. First style
- B. Second option
- C. Third option
- D. Fourth option
> A

### Question 2?
- a/ different style
- b/ second option
- c/ third option
- d/ fourth option
> B

### Question 3?
- A, comma style
- B, second option
- C, third option
- D, fourth option
> C"""

# Test case 11: Explanatory text before questions
sample_output_11 = """Based on the input text, which is a narrative passage from Mark Twain's "The Adventures of Tom Sawyer," these high-quality reading comprehension questions are generated. Each question adheres to the structured requirements, blending recall, inference, and reasoning skills.

### What is the main theme of the passage?
- Adventure and freedom
- Education and learning
- Family relationships
- Work and responsibility
> A

### According to the text, how does Tom feel about his situation?
- He is excited
- He is bored
- He is scared
- He is confused
> B"""

# Test case 12: Explanatory text between questions
sample_output_12 = """### What is the author's purpose?
- To inform
- To persuade
- To entertain
- To describe
> C

The following question tests the reader's ability to make inferences about character motivation and understand deeper narrative themes.

### Why does the protagonist make this decision?
- For personal gain
- To help others
- Out of fear
- By accident
> B"""

# Test case 13: Explanatory text after questions
sample_output_13 = """### What is the setting of the story?
- A city
- A village
- A forest
- A school
> B

### Who is the main character?
- John
- Mary
- Tom
- Alice
> C

These questions aim to evaluate the reader's understanding and ability to make inferences, analyze the main idea, and interpret the narrative's tone and themes. Each question is designed to test a different cognitive level, ensuring a comprehensive examination of comprehension skills."""

# Test case 14: Mixed explanatory text (before, between, and after)
sample_output_14 = """Here are the carefully crafted questions based on the passage:

### First question about the main idea?
- Option one
- Option two
- Option three
- Option four
> A

This next question focuses on inference skills.

### Second question testing inference?
- Option A
- Option B
- Option C
- Option D
> C

### Third question on vocabulary?
- Word meaning 1
- Word meaning 2
- Word meaning 3
- Word meaning 4
> B

All questions are designed to test comprehension at various cognitive levels."""

# Test case 15: Numbered format (### 1., ### 2., etc.)
sample_output_15 = """### 1. What is the main theme of the passage?
- Love and friendship
- War and conflict
- Science and technology
- Nature and environment
> A

### 2. According to the author, the protagonist's main motivation is _.
- revenge
- survival
- love
- ambition
> B

### 3. Which of the following best describes the author's tone?
- pessimistic
- optimistic
- neutral
- sarcastic
> B"""

# Test case 16: Mixed numbered and non-numbered format
sample_output_16 = """### 1. First numbered question?
- Option A
- Option B
- Option C
- Option D
> A

### Second question without number?
- Option A
- Option B
- Option C
- Option D
> C

### 3. Third numbered question?
- Option A
- Option B
- Option C
- Option D
> D"""


def test_parser():
    print("Test Case 1: Normal format")
    print("=" * 60)
    result1 = parse_llm_output(sample_output_1)
    print(f"Parsed {len(result1)} questions")
    for i, q in enumerate(result1, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 2: Extra newlines")
    print("=" * 60)
    result2 = parse_llm_output(sample_output_2)
    print(f"Parsed {len(result2)} questions")
    for i, q in enumerate(result2, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 3: Mixed formatting")
    print("=" * 60)
    result3 = parse_llm_output(sample_output_3)
    print(f"Parsed {len(result3)} questions")
    for i, q in enumerate(result3, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 4: Two hash marks (##)")
    print("=" * 60)
    result4 = parse_llm_output(sample_output_4)
    print(f"Parsed {len(result4)} questions")
    for i, q in enumerate(result4, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 5: Single hash mark (#)")
    print("=" * 60)
    result5 = parse_llm_output(sample_output_5)
    print(f"Parsed {len(result5)} questions")
    for i, q in enumerate(result5, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 6: Mixed hash marks (###, ##, #)")
    print("=" * 60)
    result6 = parse_llm_output(sample_output_6)
    print(f"Parsed {len(result6)} questions")
    for i, q in enumerate(result6, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 7: Multiple consecutive underscores")
    print("=" * 60)
    result7 = parse_llm_output(sample_output_7)
    print(f"Parsed {len(result7)} questions")
    for i, q in enumerate(result7, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")
        # Show that multiple underscores were normalized
        if "_" in q["content"]:
            underscore_count = q["content"].count("_")
            consecutive_underscores = len(re.findall(r"_{2,}", q["content"]))
            print(
                f"  Note: Contains {underscore_count} underscore(s), {consecutive_underscores} consecutive sequences"
            )

    print("\n" + "=" * 60)
    print("Test Case 8: Options with various incorrect prefixes (A., B), C/, D,)")
    print("=" * 60)
    result8 = parse_llm_output(sample_output_8)
    print(f"Parsed {len(result8)} questions")
    for i, q in enumerate(result8, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 9: Mixed incorrect prefixes (lowercase and variations)")
    print("=" * 60)
    result9 = parse_llm_output(sample_output_9)
    print(f"Parsed {len(result9)} questions")
    for i, q in enumerate(result9, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 10: Multiple prefix patterns in one output")
    print("=" * 60)
    result10 = parse_llm_output(sample_output_10)
    print(f"Parsed {len(result10)} questions")
    for i, q in enumerate(result10, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 11: Explanatory text BEFORE questions")
    print("=" * 60)
    result11 = parse_llm_output(sample_output_11)
    print(f"Parsed {len(result11)} questions (should ignore intro text)")
    for i, q in enumerate(result11, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 12: Explanatory text BETWEEN questions")
    print("=" * 60)
    result12 = parse_llm_output(sample_output_12)
    print(f"Parsed {len(result12)} questions (should ignore middle text)")
    for i, q in enumerate(result12, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 13: Explanatory text AFTER questions")
    print("=" * 60)
    result13 = parse_llm_output(sample_output_13)
    print(f"Parsed {len(result13)} questions (should ignore outro text)")
    for i, q in enumerate(result13, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 14: Mixed explanatory text (before, between, after)")
    print("=" * 60)
    result14 = parse_llm_output(sample_output_14)
    print(f"Parsed {len(result14)} questions (should ignore all extra text)")
    for i, q in enumerate(result14, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")

    print("\n" + "=" * 60)
    print("Test Case 15: Numbered format (### 1., ### 2., etc.)")
    print("=" * 60)
    result15 = parse_llm_output(sample_output_15)
    print(f"Parsed {len(result15)} questions (should strip number prefixes)")
    for i, q in enumerate(result15, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")
        # Verify number prefix was removed
        if re.match(r"^\d+\.", q["content"]):
            print(f"  WARNING: Number prefix not removed!")

    print("\n" + "=" * 60)
    print("Test Case 16: Mixed numbered and non-numbered format")
    print("=" * 60)
    result16 = parse_llm_output(sample_output_16)
    print(f"Parsed {len(result16)} questions (should handle both formats)")
    for i, q in enumerate(result16, 1):
        print(f"\nQuestion {i}:")
        print(f"  Content: {q['content']}")
        print(f"  Options: {q['options']}")
        print(f"  Correct: {q['correct']} ({chr(65 + q['correct'])})")


if __name__ == "__main__":
    test_parser()
