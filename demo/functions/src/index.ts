import * as admin from "firebase-admin";
import { onDocumentUpdated } from "firebase-functions/v2/firestore";
import { defineString } from "firebase-functions/params";
import { OCR_PROMPT, QUESTION_GENERATION_PROMPT } from "./prompts";
import { parseLLMOutput } from "./parser";

// Initialize Firebase Admin
admin.initializeApp();

// Configuration
const OPENROUTER_API_KEY = defineString("OPENROUTER_API_KEY");
// Default models (will be overridden by quiz document if specified)
const DEFAULT_OCR_MODEL = "qwen/qwen3-vl-8b-instruct";
const DEFAULT_QUESTION_MODEL = "google/gemini-2.5-flash";

/**
 * Process OCR when quiz is created with status "processing_ocr"
 */
export const processOCR = onDocumentUpdated(
  "quizzes/{quizId}",
  async (event) => {
    const newData = event.data?.after.data();
    const previousData = event.data?.before.data();

    // Only process if status changed to "processing_ocr"
    if (
      !event.data ||
      !newData ||
      newData.status !== "processing_ocr" ||
      previousData?.status === "processing_ocr"
    ) {
      return null;
    }

    const quizId = event.params.quizId;
    const imageUrl = newData.imageUrl;
    const ocrModel = newData.ocrModel || DEFAULT_OCR_MODEL;

    if (!imageUrl) {
      await event.data.after.ref.update({
        status: "error",
        errorMessage: "No image URL found",
      });
      return null;
    }

    try {
      console.log(`Processing OCR for quiz ${quizId} using model ${ocrModel}`);

      // Download image from Firebase Storage and convert to base64
      const bucket = admin.storage().bucket();
      const imagePath = imageUrl.split("/o/")[1].split("?")[0];
      const decodedPath = decodeURIComponent(imagePath);
      const file = bucket.file(decodedPath);

      const [imageBuffer] = await file.download();
      const base64Image = imageBuffer.toString("base64");
      const mimeType = "image/png"; // Default to PNG, can be made more intelligent
      const base64Data = `data:${mimeType};base64,${base64Image}`;

      // Call OpenRouter API for OCR
      const response = await fetch(
        "https://openrouter.ai/api/v1/chat/completions",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${OPENROUTER_API_KEY.value()}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: ocrModel,
            messages: [
              { role: "system", content: OCR_PROMPT },
              {
                role: "user",
                content: [
                  {
                    type: "image_url",
                    image_url: { url: base64Data },
                  },
                ],
              },
            ],
          }),
        }
      );

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`OCR API error: ${response.status} - ${errorText}`);
      }

      const result = await response.json();
      const ocrText = result.choices?.[0]?.message?.content?.trim() || "";

      if (!ocrText) {
        throw new Error("OCR returned empty text");
      }

      // Update quiz with OCR text and move to next stage
      await event.data.after.ref.update({
        ocrText,
        status: "generating_quiz",
      });

      console.log(`OCR completed for quiz ${quizId}`);
    } catch (error) {
      console.error(`OCR error for quiz ${quizId}:`, error);
      await event.data.after.ref.update({
        status: "error",
        errorMessage:
          error instanceof Error ? error.message : "OCR processing failed",
      });
    }

    return null;
  }
);

/**
 * Generate questions when quiz status changes to "generating_quiz"
 */
export const generateQuestions = onDocumentUpdated(
  "quizzes/{quizId}",
  async (event) => {
    const newData = event.data?.after.data();
    const previousData = event.data?.before.data();

    // Only process if status changed to "generating_quiz"
    if (
      !event.data ||
      !newData ||
      newData.status !== "generating_quiz" ||
      previousData?.status === "generating_quiz"
    ) {
      return null;
    }

    const quizId = event.params.quizId;
    const ocrText = newData.ocrText;
    const questionModel = newData.questionModel || DEFAULT_QUESTION_MODEL;

    if (!ocrText) {
      await event.data.after.ref.update({
        status: "error",
        errorMessage: "No OCR text found",
      });
      return null;
    }

    try {
      console.log(
        `Generating questions for quiz ${quizId} using model ${questionModel}`
      );

      // Create the full prompt with the text
      const fullPrompt = QUESTION_GENERATION_PROMPT.replace("{text}", ocrText);

      // Call OpenRouter API for question generation
      const response = await fetch(
        "https://openrouter.ai/api/v1/chat/completions",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${OPENROUTER_API_KEY.value()}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            model: questionModel,
            messages: [{ role: "user", content: fullPrompt }],
            temperature: 0.0,
          }),
        }
      );

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Question generation API error: ${response.status} - ${errorText}`
        );
      }

      const result = await response.json();
      const llmOutput = result.choices?.[0]?.message?.content?.trim() || "";

      // Parse the LLM output into structured questions with metadata
      const parsedData = parseLLMOutput(llmOutput);

      if (parsedData.questions.length === 0) {
        throw new Error("Failed to parse questions from LLM output");
      }

      // Update quiz with questions, metadata and mark as ready
      await event.data.after.ref.update({
        questions: parsedData.questions,
        title: parsedData.title,
        genre: parsedData.genre,
        topics: parsedData.topics,
        status: "ready",
      });

      console.log(
        `Question generation completed for quiz ${quizId}, ${parsedData.questions.length} questions created. ` +
          `Title: "${parsedData.title}", Genre: ${
            parsedData.genre
          }, Topics: [${parsedData.topics.join(", ")}]`
      );
    } catch (error) {
      console.error(`Question generation error for quiz ${quizId}:`, error);
      await event.data.after.ref.update({
        status: "error",
        errorMessage:
          error instanceof Error ? error.message : "Question generation failed",
      });
    }

    return null;
  }
);
