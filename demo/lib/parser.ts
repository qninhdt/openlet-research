import { Question } from "./types";

/**
 * Parse LLM output in the format:
 *
 * ### [question text]
 * - option 1
 * - option 2
 * - option 3
 * - option 4
 * > A|B|C|D
 *
 * Returns list of question objects
 */
export function parseLLMOutput(output: string): Question[] {
  const questions: Question[] = [];

  // Normalize the output: replace ##, #, or #### with ### for consistent parsing
  const normalizedOutput = output.replace(/^#{1,4}\s+/gm, "###");

  // Split by ### to separate questions
  const questionBlocks = normalizedOutput.trim().split("###");

  let questionId = 1;

  for (const block of questionBlocks) {
    if (!block.trim()) {
      continue;
    }

    // Split by newlines but keep only non-empty lines
    const lines = block
      .trim()
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line);

    // Check if this block contains at least one option line (starts with "-")
    // and one answer line (starts with ">")
    const hasOptions = lines.some((line) => line.startsWith("-"));
    const hasAnswer = lines.some((line) => line.startsWith(">"));

    if (!hasOptions || !hasAnswer) {
      continue;
    }

    // Parse question content - first line after ### is the question
    let content = lines[0].trim();

    // Remove question number prefix (e.g., "1. ", "2. ", "3. ")
    content = content.replace(/^\d+\.\s+/, "");

    // Normalize multiple consecutive underscores to a single underscore
    content = content.replace(/_{2,}/g, "_");

    // Parse options - look for lines starting with "-"
    const options: string[] = [];
    let answerLine: string | null = null;

    for (const line of lines.slice(1)) {
      if (line.startsWith(">")) {
        answerLine = line;
        break;
      } else if (line.startsWith("-") && options.length < 4) {
        // Remove "- " prefix
        let optionText = line.slice(1).trim();

        // Remove various option prefixes that LLM might add incorrectly
        optionText = optionText.replace(/^[A-Da-d][.)/]?,?\s+/, "");

        options.push(optionText);
      }
    }

    if (!answerLine) {
      continue;
    }

    // Parse the answer line "> A|B|C|D"
    const answerLetter = answerLine.replace(">", "").trim().toUpperCase();
    const correctMap: Record<string, number> = { A: 0, B: 1, C: 2, D: 3 };
    const correctIdx = correctMap[answerLetter];

    if (correctIdx === undefined) {
      continue;
    }

    questions.push({
      id: questionId++,
      content,
      options,
      correct: correctIdx,
      type: "General",
    });
  }

  return questions;
}
