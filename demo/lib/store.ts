"use client";

import { create } from "zustand";
import { User as FirebaseUser } from "firebase/auth";
import { Quiz, QuizStatus, Question } from "./types";

interface AuthState {
  user: FirebaseUser | null;
  loading: boolean;
  setUser: (user: FirebaseUser | null) => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user }),
  setLoading: (loading) => set({ loading }),
}));

interface QuizState {
  currentQuiz: Quiz | null;
  quizzes: Quiz[];
  isCreating: boolean;
  setCurrentQuiz: (quiz: Quiz | null) => void;
  setQuizzes: (quizzes: Quiz[]) => void;
  setIsCreating: (isCreating: boolean) => void;
  updateQuizStatus: (quizId: string, status: QuizStatus) => void;
  updateQuizOcrText: (quizId: string, ocrText: string) => void;
  updateQuizQuestions: (quizId: string, questions: Question[]) => void;
  // Editor actions
  updateQuizMetadata: (updates: Partial<Quiz>) => void;
  updateQuestion: (questionId: number, updates: Partial<Question>) => void;
  deleteQuestion: (questionId: number) => void;
  addQuestion: () => void;
  duplicateQuestion: (questionId: number) => void;
  appendQuestions: (newQuestions: Question[]) => void;
}

export const useQuizStore = create<QuizState>((set) => ({
  currentQuiz: null,
  quizzes: [],
  isCreating: false,
  setCurrentQuiz: (quiz) => set({ currentQuiz: quiz }),
  setQuizzes: (quizzes) => set({ quizzes }),
  setIsCreating: (isCreating) => set({ isCreating }),
  updateQuizStatus: (quizId, status) =>
    set((state) => ({
      quizzes: state.quizzes.map((q) =>
        q.id === quizId ? { ...q, status } : q
      ),
      currentQuiz:
        state.currentQuiz?.id === quizId
          ? { ...state.currentQuiz, status }
          : state.currentQuiz,
    })),
  updateQuizOcrText: (quizId, ocrText) =>
    set((state) => ({
      quizzes: state.quizzes.map((q) =>
        q.id === quizId ? { ...q, ocrText } : q
      ),
      currentQuiz:
        state.currentQuiz?.id === quizId
          ? { ...state.currentQuiz, ocrText }
          : state.currentQuiz,
    })),
  updateQuizQuestions: (quizId, questions) =>
    set((state) => ({
      quizzes: state.quizzes.map((q) =>
        q.id === quizId ? { ...q, questions } : q
      ),
      currentQuiz:
        state.currentQuiz?.id === quizId
          ? { ...state.currentQuiz, questions }
          : state.currentQuiz,
    })),
  // Editor actions
  updateQuizMetadata: (updates) =>
    set((state) => {
      if (!state.currentQuiz) return state;
      return {
        currentQuiz: {
          ...state.currentQuiz,
          ...updates,
        },
      };
    }),
  updateQuestion: (questionId, updates) =>
    set((state) => {
      if (!state.currentQuiz?.questions) return state;
      return {
        currentQuiz: {
          ...state.currentQuiz,
          questions: state.currentQuiz.questions.map((q) =>
            q.id === questionId ? { ...q, ...updates } : q
          ),
        },
      };
    }),
  deleteQuestion: (questionId) =>
    set((state) => {
      if (!state.currentQuiz?.questions) return state;
      const filteredQuestions = state.currentQuiz.questions.filter(
        (q) => q.id !== questionId
      );
      // Renumber questions after deletion
      const renumberedQuestions = filteredQuestions.map((q, idx) => ({
        ...q,
        id: idx + 1,
      }));
      return {
        currentQuiz: {
          ...state.currentQuiz,
          questions: renumberedQuestions,
        },
      };
    }),
  addQuestion: () =>
    set((state) => {
      if (!state.currentQuiz) return state;
      const currentQuestions = state.currentQuiz.questions || [];
      const newId = currentQuestions.length + 1;
      const newQuestion: Question = {
        id: newId,
        content: "",
        options: ["", "", "", ""],
        correct: 0,
        explanation: "",
        type: "General",
      };
      return {
        currentQuiz: {
          ...state.currentQuiz,
          questions: [...currentQuestions, newQuestion],
        },
      };
    }),
  duplicateQuestion: (questionId) =>
    set((state) => {
      if (!state.currentQuiz?.questions) return state;
      const questionToDuplicate = state.currentQuiz.questions.find(
        (q) => q.id === questionId
      );
      if (!questionToDuplicate) return state;
      const newId = state.currentQuiz.questions.length + 1;
      const duplicatedQuestion: Question = {
        ...questionToDuplicate,
        id: newId,
      };
      return {
        currentQuiz: {
          ...state.currentQuiz,
          questions: [...state.currentQuiz.questions, duplicatedQuestion],
        },
      };
    }),
  appendQuestions: (newQuestions) =>
    set((state) => {
      if (!state.currentQuiz) return state;
      const currentQuestions = state.currentQuiz.questions || [];
      const startId = currentQuestions.length + 1;
      // Renumber the new questions to continue from current list
      const renumberedNewQuestions = newQuestions.map((q, idx) => ({
        ...q,
        id: startId + idx,
      }));
      return {
        currentQuiz: {
          ...state.currentQuiz,
          questions: [...currentQuestions, ...renumberedNewQuestions],
        },
      };
    }),
}));

// UI State
interface UIState {
  showImportDialog: boolean;
  setShowImportDialog: (show: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  showImportDialog: false,
  setShowImportDialog: (showImportDialog) => set({ showImportDialog }),
}));
