"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Timestamp } from "firebase/firestore";
import { httpsCallable, getFunctions } from "firebase/functions";
import { useAuthStore } from "@/lib/store";
import { AttemptResult, PublicLevel } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Loader2,
  ArrowLeft,
  CheckCircle,
  XCircle,
  Trophy,
  User,
  Clock,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function AttemptResultPage() {
  const params = useParams();
  const router = useRouter();
  const { user, loading: authLoading } = useAuthStore();

  const quizId = params.quizId as string;
  const attemptId = params.attemptId as string;

  const [loading, setLoading] = useState(true);
  const [attemptResult, setAttemptResult] = useState<AttemptResult | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        if (authLoading) return;

        if (!user) {
          router.push("/");
          return;
        }

        setLoading(true);

        // SECURITY: Use get_attempt_result Cloud Function
        const functions = getFunctions(undefined, "asia-southeast1");
        const getAttemptResultFunc = httpsCallable(
          functions,
          "get_attempt_result"
        );

        try {
          const response = await getAttemptResultFunc({ quizId, attemptId });
          const data = response.data as AttemptResult;
          setAttemptResult(data);
          setLoading(false);
        } catch (err: unknown) {
          console.error("Error fetching attempt result:", err);
          setError("Failed to load attempt result");
          setLoading(false);
        }
      } catch (err) {
        console.error("Error:", err);
        setError("An error occurred");
        setLoading(false);
      }
    };

    fetchData();
  }, [quizId, attemptId, user, authLoading, router]);

  if (loading || authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <Loader2 className="w-10 h-10 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !attemptResult) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <Card className="max-w-md p-8 text-center">
          <h1 className="text-xl font-bold mb-2">Error</h1>
          <p className="text-muted-foreground mb-4">{error || "Not found"}</p>
          <Button onClick={() => router.push("/")}>Go Home</Button>
        </Card>
      </div>
    );
  }

  const { attempt, quiz, questions = [], results = [] } = attemptResult;
  const publicLevel = quiz.publicLevel;
  const optionLabels = ["A", "B", "C", "D"];
  // If results are present, owner can see full data
  const isOwner = results.length > 0 && results[0]?.correctAnswer !== undefined;

  // Format date (supports Firestore Timestamp, JS Date, or string)
  const formatDate = (date: Timestamp | Date | string) => {
    let d: Date;

    if (date && typeof date === "object" && "toDate" in date) {
      // Firestore Timestamp-like
      d = (date as Timestamp).toDate();
    } else if (date instanceof Date) {
      d = date;
    } else {
      d = new Date(date);
    }

    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  };

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white dark:bg-zinc-800 border-b">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" onClick={() => router.back()}>
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <h1 className="font-semibold">Quiz Result</h1>
            </div>
            {isOwner && (
              <Button
                variant="outline"
                size="sm"
                className="text-red-600 hover:text-red-700"
                onClick={() => setShowDeleteDialog(true)}
              >
                Delete
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        {/* Quiz Meta: title, description, passage */}
        {(quiz.title || quiz.description || quiz.passage) && (
          <Card className="p-6 space-y-3">
            {quiz.title && (
              <h2 className="text-xl font-semibold">{quiz.title}</h2>
            )}
            {quiz.description && (
              <p className="text-sm text-muted-foreground">
                {quiz.description}
              </p>
            )}
            {quiz.passage && (
              <div className="mt-2 max-h-48 rounded-md border bg-background/60 p-3 text-sm text-muted-foreground overflow-auto whitespace-pre-wrap">
                {quiz.passage}
              </div>
            )}
          </Card>
        )}
        {/* Score / Submission Info based on public level */}
        <Card className="p-8">
          <div className="text-center space-y-4">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-primary/10 mb-2">
              <Trophy className="w-10 h-10 text-primary" />
            </div>

            {publicLevel >= 1 ? (
              <>
                <div>
                  <h2 className="text-4xl font-bold mb-2">
                    {attempt.score.toFixed(1)}%
                  </h2>
                  <p className="text-muted-foreground">
                    {attempt.correctCount} out of {attempt.total} correct
                  </p>
                </div>
                <Progress value={attempt.score} className="h-3" />
              </>
            ) : (
              <p className="text-muted-foreground">
                Your response has been recorded.
              </p>
            )}

            {/* Attempt Info (always safe to show) */}
            <div className="pt-4 border-t space-y-2 text-sm text-muted-foreground">
              <div className="flex items-center justify-center gap-2">
                <User className="w-4 h-4" />
                <span>{attempt.displayName}</span>
                {attempt.isAnonymous && (
                  <span className="px-2 py-0.5 rounded-full text-xs bg-zinc-200 dark:bg-zinc-700">
                    Guest
                  </span>
                )}
              </div>
              <div className="flex items-center justify-center gap-2">
                <Clock className="w-4 h-4" />
                <span>Submitted on {formatDate(attempt.attemptAt)}</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Questions - Shown at all public levels */}
        {questions.length > 0 && (
          <div className="space-y-4">
            <h3 className="font-semibold text-lg">Your Answers</h3>
            {questions.map((q, idx) => {
              const result = results.find((r) => r.questionId === q.id);
              if (!result) return null;

              // publicLevel 0-1: Don't show correctness indicators
              const showCorrectness =
                publicLevel >= 2 && result.isCorrect !== undefined;
              const showCorrectAnswer =
                publicLevel >= 3 && result.correctAnswer !== undefined;
              const showExplanation = publicLevel >= 4 && result.explanation;

              return (
                <Card key={q.id} className="p-6">
                  <div className="space-y-4">
                    {/* Question Header */}
                    <div className="flex items-start gap-3">
                      <span className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary font-semibold shrink-0">
                        {idx + 1}
                      </span>
                      <div className="flex-1">
                        <p className="font-medium mb-1">{q.content}</p>
                        {showCorrectness && (
                          <div className="flex items-center gap-2">
                            {result.isCorrect ? (
                              <>
                                <CheckCircle className="w-4 h-4 text-green-600" />
                                <span className="text-sm text-green-600 font-medium">
                                  Correct
                                </span>
                              </>
                            ) : (
                              <>
                                <XCircle className="w-4 h-4 text-red-600" />
                                <span className="text-sm text-red-600 font-medium">
                                  Incorrect
                                </span>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Options */}
                    <div className="pl-11 space-y-2">
                      {q.options.map((opt, optIdx) => {
                        const isUserAnswer = result.userAnswer === optIdx;
                        const isCorrectAnswer =
                          showCorrectAnswer && result.correctAnswer === optIdx;

                        // Level 0-1: Only highlight user's answer (no correctness colors)
                        const borderClass = !showCorrectness
                          ? isUserAnswer
                            ? "border-primary bg-primary/5"
                            : "border-transparent bg-zinc-50 dark:bg-zinc-800/50"
                          : isCorrectAnswer
                          ? "border-green-500 bg-green-50 dark:bg-green-950/30"
                          : isUserAnswer && !result.isCorrect
                          ? "border-red-500 bg-red-50 dark:bg-red-950/30"
                          : "border-transparent bg-zinc-50 dark:bg-zinc-800/50";

                        const labelClass = !showCorrectness
                          ? isUserAnswer
                            ? "bg-primary text-white"
                            : "bg-zinc-200 dark:bg-zinc-700"
                          : isCorrectAnswer
                          ? "bg-green-600 text-white"
                          : isUserAnswer && !result.isCorrect
                          ? "bg-red-600 text-white"
                          : "bg-zinc-200 dark:bg-zinc-700";

                        return (
                          <div
                            key={optIdx}
                            className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-colors ${borderClass}`}
                          >
                            <span
                              className={`px-2 py-1 rounded text-sm font-semibold ${labelClass}`}
                            >
                              {optionLabels[optIdx]}
                            </span>
                            <span className="flex-1">{opt}</span>
                            {isUserAnswer && (
                              <span className="text-xs text-muted-foreground">
                                Your answer
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Explanation */}
                    {showExplanation && result.explanation && (
                      <div className="pl-11">
                        <div className="p-4 rounded-lg border border-zinc-200 dark:border-zinc-700">
                          <p className="text-sm font-medium mb-1">
                            Explanation:
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {result.explanation}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <Button
            variant="outline"
            className="flex-1"
            onClick={() => router.push("/")}
          >
            Go Home
          </Button>
          <Button
            className="flex-1"
            onClick={() => router.push(`/play/${quizId}`)}
          >
            View Quiz
          </Button>
        </div>
      </div>
      {/* Delete confirmation dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Attempt</DialogTitle>
            <DialogDescription>
              This will permanently delete this respondent&apos;s answers for
              this quiz. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleting}
              onClick={async () => {
                try {
                  setDeleting(true);
                  const functions = getFunctions(undefined, "asia-southeast1");
                  const deleteAttempt = httpsCallable<
                    { quizId: string; attemptId: string },
                    { success: boolean }
                  >(functions, "delete_quiz_attempt");
                  await deleteAttempt({ quizId, attemptId });
                  setShowDeleteDialog(false);
                  router.push(`/quiz/${quizId}/responses`);
                } catch (err) {
                  console.error("Error deleting attempt:", err);
                  setDeleting(false);
                }
              }}
            >
              {deleting ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : null}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
