You are an Expert Dialogue Assessment Developer and Linguistic Analyst specializing in the DREAM dataset style (Dialogue-based Reading Comprehension).

Your task is to generate a comprehensive set of multiple-choice questions based on the provided **Input Dialogue**. The questions must evaluate the reader's ability to comprehend conversational context, deduce relationships, and infer non-explicit information.

# 1. DIALOGUE ANALYSIS
Before generating questions, analyze the Input Dialogue to determine:
- **Context:** Identify the speakers, their relationship (e.g., husband-wife, teacher-student), and the setting (e.g., classroom, store).
- **Key Facts:** Isolate specific data points (times, prices, names, lists of items).
- **Implicit Clues:** Identify tone, emotions, and "world knowledge" required to understand the situation (Commonsense).
- **Logic Flows:** Identify connections between multiple turns of the conversation (Multi-sentence reasoning).

# 2. QUESTION GENERATION RULES (Strict Enforcement)

## A. Mandatory Question Types (Minimum 5 Questions)
You must generate **at least 1 question** for EACH of the following categories (unless the content strictly does not allow it, e.g., no numbers for Arithmetic):

1.  **Summary (Global Understanding):**
    - Ask about the main topic, the relationship between speakers, or the location/setting.
    - *Example:* "What are the speakers mainly talking about?", "What is the probable relationship between the two speakers?"
2.  **Logical Reasoning (Multi-sentence):**
    - The answer is NOT in a single sentence. It requires combining information from speaker A and speaker B, or across several turns.
    - *Goal:* Test Cause-Effect or Conditions.
3.  **Arithmetic (Numerical Reasoning):**
    - If the text contains numbers (time, money, quantity), force a calculation.
    - *Goal:* Determine the final price, the duration, or the age difference.
4.  **Commonsense / Inference:**
    - The answer requires outside world knowledge or social awareness not explicitly stated.
    - *Example:* If someone says "It's raining cats and dogs," ask about the weather condition, not the animals.
5.  **Detail / Matching:**
    - A specific detail retrieval question, but phrased to test attention.
    - *Goal:* Test accuracy on specific facts.

## B. Full Coverage Rule (Dynamic Quantity)
- After creating the mandatory types, scan the dialogue for any remaining plot points, conflict resolutions, or details not yet tested.
- **Generate additional questions** to ensure the entire content of the conversation is covered.
- **Total Question Count:** Minimum 5.

## C. Formatting Constraints (DREAM Style)
- **Option Count:** You must provide exactly **3 options** (A, B, C) for each question (Unlike RACE which has 4).
- **Distractor Quality (Crucial):**
    - **Lexical Overlap:** Distractors should utilize words/phrases that APPEAR in the text but are used in the wrong context or assigned to the wrong speaker.
    - **Plausibility:** Wrong answers must look reasonable to someone who only skimmed the text.
- **Question Style:**
    - Mix **Wh- questions** (What, Where, Why) and **Incomplete sentences** (e.g., "The man implies that...").

# 3. OUTPUT FORMAT
Output the questions directly. Do not include your analysis notes. Follow this pattern EXACTLY:

### 1. [Question Text]
- [Option A]
- [Option B]
- [Option C]
> [Correct Answer Letter]

### 2. [Question Text]
- [Option A]
- [Option B]
- [Option C]
> [Correct Answer Letter]

... [Continue for all generated questions]

---
**Example Output:**

### 1. Where does this conversation most likely take place?
- At a bookstore
- In a library
- At a hotel
> C

### 2. The man is surprised because _ .
- the price is too high
- the shop is closed
- the woman arrived early
> A

---
# INPUT DIALOGUE:
<dialogue>
{text}
</dialogue>