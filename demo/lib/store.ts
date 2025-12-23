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
}));

// UI State
interface UIState {
  showCreateDialog: boolean;
  setShowCreateDialog: (show: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  showCreateDialog: false,
  setShowCreateDialog: (showCreateDialog) => set({ showCreateDialog }),
}));
