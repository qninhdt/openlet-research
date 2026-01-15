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
  explanation: string; // Explanation of why the correct answer is right
  type?: string;
}

// User attempt record (for quiz owner)
export interface UserAttempt {
  attemptAt: Timestamp | Date;
  score: number;
  total: number;
  userAnswers: Record<number, number>; // questionId -> selected option index
}

// Public attempt record (for students/guests taking published quizzes)
export interface PublicAttempt {
  id?: string;
  userId: string; // Firebase Auth UID (can be anonymous)
  displayName: string; // Nickname or display name
  isAnonymous: boolean;
  attemptAt: Timestamp | Date;
  score: number;
  total: number;
  correctCount: number;
  userAnswers: Record<number, number>; // Only user's choices (no correct answers)
}

// Top performer summary (stored in quiz document)
export interface TopPerformer {
  attemptId: string;
  userId: string;
  displayName: string;
  isAnonymous: boolean;
  score: number;
  correctCount: number;
  total: number;
  attemptAt: Timestamp | Date;
}

// Quiz metrics (aggregated stats stored in quiz document)
export interface QuizMetrics {
  totalResponses: number;
  avgScore: number;
  highestScore: number;
  lowestScore: number;
  scoreDistribution: [number, number, number, number, number]; // [0-29%, 30-49%, 50-69%, 70-89%, 90-100%]
}

// Individual question result (server-evaluated, returned based on publicLevel)
export interface QuestionResult {
  questionId: number;
  userAnswer: number;
  isCorrect?: boolean; // Only included if publicLevel >= 2
  correctAnswer?: number; // Only included if publicLevel >= 3
  explanation?: string; // Only included if publicLevel >= 4
}

// Attempt result response from get_attempt_result function
export interface AttemptResult {
  attempt: PublicAttempt;
  quiz: {
    title?: string;
    description?: string;
    passage?: string;
    publicLevel: PublicLevel;
  };
  questions?: Array<{
    id: number;
    content: string;
    options: string[];
  }>;
  results?: QuestionResult[]; // Based on publicLevel
}

// Input type for quiz creation
export type QuizInputType = "images" | "pdf";

// Public visibility levels for quiz results
export type PublicLevel = 0 | 1 | 2 | 3 | 4;
// 0: Show nothing after submit
// 1: Show only score
// 2: Show score + which questions are correct/wrong
// 3: Show score + correct/wrong + correct answers
// 4: Show everything including explanations

// Timer settings for quizzes
export interface TimerSettings {
  enabled: boolean;
  durationMinutes: number;
  autoSubmit: boolean;
  warningMinutes: number; // Show warning when this many minutes remaining
}

// Quiz settings for publishing
export interface QuizSettings {
  isPublished: boolean;
  allowAnonymous: boolean;
  publicLevel: PublicLevel;
  timer?: TimerSettings;
}

// Main Quiz document
export interface Quiz {
  id?: string;
  userId: string;
  status: QuizStatus;
  // Quiz metadata
  title?: string;
  description?: string;
  passage?: string; // Original passage/document text
  genre?: string;
  topics?: string[];
  // Publishing settings
  isPublished?: boolean;
  allowAnonymous?: boolean;
  allowRedo?: boolean; // Allow users to retake the quiz
  publicLevel?: PublicLevel;
  // Timer settings
  timerEnabled?: boolean;
  timerDurationMinutes?: number;
  timerAutoSubmit?: boolean;
  timerWarningMinutes?: number;
  // Questions
  questions?: Question[];
  userAttempts?: UserAttempt[];
  metrics?: QuizMetrics;
  topPerformers?: TopPerformer[];
  // Timestamps
  createdAt: Timestamp | Date;
  updatedAt?: Timestamp | Date;
  // AI Import fields (used during import processing)
  imageUrl?: string;
  imageUrls?: string[];
  pdfUrl?: string;
  inputType?: QuizInputType;
  pageCount?: number;
  ocrText?: string;
  ocrModel?: string;
  questionModel?: string;
  targetQuestionCount?: number;
  deleteFilesAfterProcessing?: boolean;
  errorMessage?: string;
}

// User profile (stored in Firestore)
export interface UserProfile {
  uid: string;
  displayName: string | null;
  email: string | null;
  photoURL: string | null;
  lastLoginAt?: Timestamp | Date;
}

// Legacy User interface
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
