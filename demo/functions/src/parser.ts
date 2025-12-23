export interface Question {
  id: number;
  content: string;
  options: string[];
  correct: number; // 0-based index (A=0, B=1, C=2, D=3)
  type?: string;
}

export interface ParsedQuizData {
  title: string;
  genre: string;
  topics: string[];
  questions: Question[];
}

/**
 * Parse LLM output in the format:
 *
 * # [Title]
 * > Genre: [genre]
 * > Topics: [topic1, topic2, topic3]
 *
 * ### [question text]
 * - option 1
 * - option 2
 * - option 3
 * - option 4
 * > A|B|C|D
 *
 * Returns parsed quiz data with metadata and questions
 */
export function parseLLMOutput(output: string): ParsedQuizData {
  let title = "Untitled Quiz";
  let genre = "General";
  let topics: string[] = [];
  const questions: Question[] = [];

  // Extract title from first # line
  const titleMatch = output.match(/^#\s+(.+?)$/m);
  if (titleMatch) {
    title = titleMatch[1].trim();
  }

  // Extract genre from > Genre: line
  const genreMatch = output.match(/>\s*Genre:\s*(.+?)$/im);
  if (genreMatch) {
    genre = genreMatch[1].trim();
  }

  // Extract topics from > Topics: line (comma-separated)
  const topicsMatch = output.match(/>\s*Topics?:\s*(.+?)$/im);
  if (topicsMatch) {
    topics = topicsMatch[1]
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t.length > 0);
  }

  // Default to "General" if no topics found
  if (topics.length === 0) {
    topics = ["General"];
  }

  // Normalize the output: replace ##, ####, etc with ### for consistent parsing
  const normalizedOutput = output.replace(/^#{2,4}\s+/gm, "###");

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
    const hasAnswer = lines.some(
      (line) => line.startsWith(">") && /^>\s*[A-Da-d]\s*$/.test(line)
    );

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

  return {
    title,
    genre,
    topics,
    questions,
  };
}
