import { Timestamp } from "firebase/firestore";

// Model configuration
export interface ModelInfo {
  id: string;
  displayName: string;
  category: "open-source" | "proprietary";
}

export const AVAILABLE_MODELS: ModelInfo[] = [
  {
    id: "google/gemma-3-12b-it",
    displayName: "Gemma 3 12B",
    category: "open-source",
  },
  {
    id: "qwen/qwen3-vl-8b-instruct",
    displayName: "Qwen3 VL 8B",
    category: "open-source",
  },
  {
    id: "nvidia/nemotron-nano-12b-v2-vl",
    displayName: "Nemotron Nano 12B",
    category: "open-source",
  },
  {
    id: "meta-llama/llama-3.2-11b-vision-instruct",
    displayName: "Llama 3.2 11B Vision",
    category: "open-source",
  },
  {
    id: "google/gemini-2.5-flash",
    displayName: "Gemini 2.5 Flash",
    category: "proprietary",
  },
  {
    id: "openai/gpt-5-mini",
    displayName: "GPT-5 Mini",
    category: "proprietary",
  },
  {
    id: "x-ai/grok-4.1-fast",
    displayName: "Grok 4.1 Fast",
    category: "proprietary",
  },
];

// Quiz status enum
export type QuizStatus =
  | "uploading"
  | "processing_ocr"
  | "generating_quiz"
  | "ready"
  | "error";

// Question type for generated questions
export interface Question {
  id: number;
  content: string;
  options: string[];
  correct: number; // 0-based index (A=0, B=1, C=2, D=3)
  type?: string;
}

// User attempt record
export interface UserAttempt {
  attemptAt: Timestamp | Date;
  score: number;
  total: number;
  userAnswers: Record<number, number>; // questionId -> selected option index
}

// Main Quiz document
export interface Quiz {
  id?: string;
  userId: string;
  status: QuizStatus;
  imageUrl?: string;
  ocrText?: string;
  questions?: Question[];
  userAttempts?: UserAttempt[];
  createdAt: Timestamp | Date;
  updatedAt?: Timestamp | Date;
  errorMessage?: string;
  title?: string;
  genre?: string;
  topics?: string[];
  ocrModel?: string;
  questionModel?: string;
}

// User profile
export interface User {
  uid: string;
  displayName: string | null;
  email: string | null;
  photoURL: string | null;
  createdAt: Timestamp | Date;
}

// API Request/Response types
export interface OCRRequest {
  imageBase64: string;
}

export interface OCRResponse {
  text: string;
  error?: string;
}

export interface GenerateQuestionsRequest {
  text: string;
}

export interface GenerateQuestionsResponse {
  questions: Question[];
  error?: string;
}

// Quiz result after completing
export interface QuizResult {
  score: number;
  total: number;
  correctAnswers: number[];
  userAnswers: Record<number, number>;
  questions: Question[];
}
