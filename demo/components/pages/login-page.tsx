"use client";

import { LoginButton } from "@/components/auth/login-button";
import { useAuthStore } from "@/lib/store";
import { BookOpen, Brain, Camera, Sparkles } from "lucide-react";

export function LoginPage() {
  const { loading } = useAuthStore();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-linear-to-br from-blue-50 to-indigo-100 dark:from-zinc-900 dark:to-zinc-800">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-primary/20" />
          <div className="h-4 w-32 rounded bg-primary/20" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-linear-to-br from-blue-50 to-indigo-100 dark:from-zinc-900 dark:to-zinc-800 p-6">
      <div className="max-w-md w-full space-y-8">
        {/* Logo & Title */}
        <div className="text-center space-y-4">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-primary text-primary-foreground shadow-lg">
            <BookOpen className="w-10 h-10" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            Openlet
          </h1>
          <p className="text-muted-foreground">
            Create multiple-choice quizzes from document images in seconds
          </p>
        </div>

        {/* Features */}
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-4 rounded-xl bg-white/50 dark:bg-zinc-800/50 backdrop-blur">
            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
              <Camera className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-medium text-zinc-900 dark:text-white">
                Capture or Upload
              </h3>
              <p className="text-sm text-muted-foreground">
                Take a photo directly or upload an existing file
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-xl bg-white/50 dark:bg-zinc-800/50 backdrop-blur">
            <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400">
              <Brain className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-medium text-zinc-900 dark:text-white">
                Smart AI OCR
              </h3>
              <p className="text-sm text-muted-foreground">
                Extract text accurately with advanced OCR technology
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-xl bg-white/50 dark:bg-zinc-800/50 backdrop-blur">
            <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-medium text-zinc-900 dark:text-white">
                Auto-Generate Questions
              </h3>
              <p className="text-sm text-muted-foreground">
                Create diverse multiple-choice question sets
              </p>
            </div>
          </div>
        </div>

        {/* Login Button */}
        <div className="flex justify-center pt-4">
          <LoginButton />
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-muted-foreground">
          By signing in, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
    </div>
  );
}
