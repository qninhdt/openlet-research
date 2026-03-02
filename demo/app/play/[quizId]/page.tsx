"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { httpsCallable, getFunctions } from "firebase/functions";
import { signOut } from "firebase/auth";
import { db, auth } from "@/lib/firebase";
import { signInAsGuest, getUserDisplayName } from "@/lib/auth";
import { useAuthStore } from "@/lib/store";
import { Quiz, PublicLevel } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Card } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import {
  Loader2,
  Send,
  CheckCircle,
  XCircle,
  Trophy,
  Lock,
  RotateCcw,
  User,
  BookOpen,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  LogOut,
  ArrowLeft,
  Chrome,
} from "lucide-react";

type PageState = "loading" | "nickname" | "quiz" | "submitting" | "result";

interface QuizResult {
  score: number;
  correctCount: number;
  total: number;
  publicLevel: PublicLevel;
  results?: {
    questionId: number;
    userAnswer: number;
    isCorrect: boolean;
    correctAnswer?: number;
    explanation?: string;
  }[];
}

export default function PlayQuizPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const { user, loading: authLoading } = useAuthStore();

  const quizId = params.quizId as string;

  const [pageState, setPageState] = useState<PageState>("loading");
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [fullQuiz, setFullQuiz] = useState<Quiz | null>(null); // For owner preview with answers
  const [nickname, setNickname] = useState("");
  const [userAnswers, setUserAnswers] = useState<Record<number, number>>({});
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isOwner, setIsOwner] = useState(false);

  // Timer state
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const [showWarning, setShowWarning] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const handleSubmitRef = useRef<() => void>(() => {});

  // Passage visibility
  const [showPassage, setShowPassage] = useState(true);

  // Fetch quiz data
  useEffect(() => {
    const fetchQuiz = async () => {
      try {
        // Wait for auth to finish loading before making decisions
        if (authLoading) {
          return;
        }

        setPageState("loading");

        let currentUser = user;

        // SECURITY: Use Cloud Function to fetch quiz data securely
        // This prevents exposing correct answers to clients
        const functions = getFunctions(undefined, "asia-southeast1");
        const getQuizForPlayer = httpsCallable(
          functions,
          "get_quiz_for_player"
        );

        let quizData: Quiz;
        let ownerMode = false;

        try {
          const response = await getQuizForPlayer({ quizId });
          quizData = response.data as Quiz;

          // Check if user is the owner (function returns full data for owners)
          ownerMode =
            currentUser?.uid === quizData.userId && !currentUser?.isAnonymous;
          setIsOwner(ownerMode);

          // Store full quiz for owner preview
          if (ownerMode) {
            setFullQuiz(quizData);
          }
        } catch (err: unknown) {
          // Handle specific errors from the Cloud Function
          if (
            typeof err === "object" &&
            err !== null &&
            "code" in err &&
            (err as { code?: string }).code === "functions/permission-denied"
          ) {
            const message =
              (err as { message?: string }).message || "Permission denied";
            if (message.includes("authentication")) {
              // Quiz requires authentication but user is not logged in
              // We need to fetch basic quiz info to show login page
              // Try to sign in anonymously first to get quiz metadata
              if (!currentUser) {
                try {
                  const { signInAnonymously } = await import("firebase/auth");
                  const { auth } = await import("@/lib/firebase");
                  const credential = await signInAnonymously(auth);
                  currentUser = credential.user;

                  // Retry fetching quiz
                  const retryResponse = await getQuizForPlayer({ quizId });
                  quizData = retryResponse.data as Quiz;
                } catch {
                  // If still fails, show generic login page
                  setQuiz({ id: quizId } as Quiz);
                  setPageState("nickname");
                  return;
                }
              } else {
                setError(
                  "This quiz requires you to sign in with a Google account"
                );
                return;
              }
            } else {
              setError(message);
              return;
            }
          } else if (
            typeof err === "object" &&
            err !== null &&
            "code" in err &&
            (err as { code?: string }).code === "functions/not-found"
          ) {
            setError("Quiz not found");
            return;
          } else {
            throw err;
          }
        }

        // Handle authentication for anonymous-allowed quizzes
        if (!currentUser && quizData.allowAnonymous) {
          const { signInAnonymously } = await import("firebase/auth");
          const { auth } = await import("@/lib/firebase");
          const credential = await signInAnonymously(auth);
          currentUser = credential.user;
        }

        // If no current user and anonymous not allowed, show login
        if (!currentUser && !quizData.allowAnonymous) {
          setQuiz(quizData);
          setPageState("nickname");
          return;
        }

        setQuiz(quizData);

        // Check for existing attempts if redo is disabled and not owner
        if (
          !ownerMode &&
          !quizData.allowRedo &&
          currentUser &&
          !currentUser.isAnonymous
        ) {
          // Query user's attempts
          const {
            collection,
            query: firestoreQuery,
            where: firestoreWhere,
            orderBy,
            limit: firestoreLimit,
            getDocs,
          } = await import("firebase/firestore");
          const attemptsRef = collection(db, "quizzes", quizId, "attempts");
          const q = firestoreQuery(
            attemptsRef,
            firestoreWhere("userId", "==", currentUser.uid),
            orderBy("attemptAt", "desc"),
            firestoreLimit(1)
          );
          const snapshot = await getDocs(q);

          if (!snapshot.empty) {
            // User has already taken this quiz, redirect to their latest attempt
            const latestAttemptId = snapshot.docs[0].id;
            router.push(`/play/${quizId}/attempt/${latestAttemptId}`);
            return;
          }
        }

        // Owner goes directly to quiz, others need nickname
        if (ownerMode) {
          setPageState("quiz");
        } else if (currentUser && !currentUser.isAnonymous) {
          setPageState("quiz");
        } else if (currentUser && currentUser.displayName) {
          setPageState("quiz");
        } else {
          setPageState("nickname");
        }
      } catch (err) {
        console.error("Error fetching quiz:", err);
        setError("Failed to load quiz");
      }
    };

    fetchQuiz();
  }, [quizId, user, authLoading, router]);

  // Timer effect
  useEffect(() => {
    if (
      pageState !== "quiz" ||
      !quiz?.timerEnabled ||
      timeRemaining === null ||
      isOwner
    )
      return;

    timerRef.current = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev === null || prev <= 0) {
          if (timerRef.current) clearInterval(timerRef.current);
          if (quiz?.timerAutoSubmit) {
            handleSubmitRef.current();
          }
          return 0;
        }

        // Show warning
        const warningSeconds = (quiz?.timerWarningMinutes || 5) * 60;
        if (prev <= warningSeconds && !showWarning) {
          setShowWarning(true);
          toast({
            title: "Time is running out!",
            description: `You have ${Math.floor(
              prev / 60
            )} minute(s) remaining`,
            variant: "destructive",
          });
        }

        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [
    pageState,
    quiz?.timerEnabled,
    quiz?.timerAutoSubmit,
    quiz?.timerWarningMinutes,
    timeRemaining,
    showWarning,
    toast,
    isOwner,
  ]);

  const handleStartQuiz = async () => {
    if (!nickname.trim()) {
      toast({
        title: "Nickname required",
        description: "Please enter a nickname to continue",
        variant: "destructive",
      });
      return;
    }

    try {
      await signInAsGuest(nickname.trim());

      // Initialize timer if enabled
      if (quiz?.timerEnabled && quiz?.timerDurationMinutes) {
        setTimeRemaining(quiz.timerDurationMinutes * 60);
      }

      setPageState("quiz");
    } catch (err) {
      console.error("Error signing in:", err);
      toast({
        title: "Error",
        description: "Failed to start quiz. Please try again.",
        variant: "destructive",
      });
    }
  };

  const handleAnswerSelect = (questionId: number, optionIndex: number) => {
    setUserAnswers((prev) => ({
      ...prev,
      [questionId]: optionIndex,
    }));
  };

  const handleSubmit = useCallback(async () => {
    if (!quiz?.id || !user) return;

    try {
      setPageState("submitting");
      if (timerRef.current) clearInterval(timerRef.current);

      // Owner preview: Calculate results locally, don't submit to server
      if (isOwner && fullQuiz) {
        const questions = fullQuiz.questions || [];
        let correctCount = 0;
        const results = questions.map((q) => {
          const userAnswer = userAnswers[q.id];
          const isCorrect = userAnswer === q.correct;
          if (isCorrect) correctCount++;
          return {
            questionId: q.id,
            userAnswer,
            isCorrect,
            correctAnswer: q.correct,
            explanation: q.explanation,
          };
        });

        const score =
          questions.length > 0 ? (correctCount / questions.length) * 100 : 0;

        setQuizResult({
          score,
          correctCount,
          total: questions.length,
          publicLevel: 4, // Owner sees everything
          results,
        });
        setPageState("result");
        return;
      }

      // Regular submission via server
      const functions = getFunctions(undefined, "asia-southeast1");
      const submitQuizAnswers = httpsCallable(functions, "submit_quiz_answers");

      const response = await submitQuizAnswers({
        quizId: quiz.id,
        userAnswers,
        displayName: getUserDisplayName(user),
        isAnonymous: user.isAnonymous,
      });

      const resultData = response.data as QuizResult & { attemptId?: string };

      // If attemptId is provided, redirect to the attempt page
      if (resultData.attemptId) {
        router.push(`/play/${quiz.id}/attempt/${resultData.attemptId}`);
        return;
      }

      // Fallback: show inline result (shouldn't happen with new backend)
      setQuizResult(resultData);
      setPageState("result");
    } catch (err: unknown) {
      console.error("Error submitting quiz:", err);
      const errorMessage =
        err instanceof Error ? err.message : "Failed to submit quiz";
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive",
      });
      setPageState("quiz");
    }
  }, [quiz?.id, user, userAnswers, toast, isOwner, fullQuiz, router]);

  // Keep ref updated for timer callback
  useEffect(() => {
    handleSubmitRef.current = handleSubmit;
  }, [handleSubmit]);

  const handleLogout = async () => {
    try {
      await signOut(auth);
      router.push("/");
    } catch (err) {
      console.error("Error signing out:", err);
    }
  };

  const questions = quiz?.questions || [];
  const totalQuestions = questions.length;
  const answeredCount = Object.keys(userAnswers).length;
  const progressPercent = (answeredCount / totalQuestions) * 100;

  const optionLabels = ["A", "B", "C", "D"];

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  // Loading state
  if (pageState === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading quiz...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <Card className="max-w-md p-8 text-center">
          <Lock className="w-12 h-12 mx-auto text-zinc-400 mb-4" />
          <h1 className="text-xl font-bold mb-2">Quiz Unavailable</h1>
          <p className="text-muted-foreground mb-4">{error}</p>
          <Button onClick={() => router.push("/")}>Go Home</Button>
        </Card>
      </div>
    );
  }

  // Nickname entry state
  if (pageState === "nickname") {
    const handleGoogleSignIn = async () => {
      try {
        const { signInWithPopup } = await import("firebase/auth");
        const { auth, googleProvider } = await import("@/lib/firebase");
        await signInWithPopup(auth, googleProvider);
        // After sign in, the useEffect will re-run and load the quiz
      } catch (err) {
        console.error("Error signing in:", err);
        toast({
          title: "Sign in failed",
          description: "Failed to sign in with Google. Please try again.",
          variant: "destructive",
        });
      }
    };

    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900 p-4">
        <Card className="max-w-md w-full p-8">
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
              <BookOpen className="w-8 h-8 text-primary" />
            </div>
            <h1 className="text-2xl font-bold mb-2">{quiz?.title || "Quiz"}</h1>
            {quiz?.description && (
              <p className="text-muted-foreground text-sm">
                {quiz.description}
              </p>
            )}
          </div>

          <div className="space-y-4">
            {quiz?.allowAnonymous !== false ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="nickname">Enter your nickname</Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="nickname"
                      value={nickname}
                      onChange={(e) => setNickname(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleStartQuiz()}
                      placeholder="Your name"
                      className="pl-10"
                    />
                  </div>
                </div>

                <Button
                  onClick={handleStartQuiz}
                  className="w-full"
                  disabled={!nickname.trim()}
                >
                  Start Quiz
                </Button>

                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-white dark:bg-zinc-800 px-2 text-muted-foreground">
                      Or
                    </span>
                  </div>
                </div>

                <Button
                  variant="outline"
                  className="w-full gap-2"
                  onClick={handleGoogleSignIn}
                >
                  <Chrome className="w-4 h-4" />
                  Sign in with Google
                </Button>
              </>
            ) : (
              <div className="space-y-4">
                <div className="text-center p-4 rounded-lg bg-warning-light dark:bg-warning-light border border-warning dark:border-warning">
                  <Lock className="w-8 h-8 mx-auto text-warning-foreground dark:text-warning-foreground mb-2" />
                  <p className="text-sm text-warning-foreground dark:text-warning-foreground font-medium">
                    Authentication Required
                  </p>
                  <p className="text-xs text-warning-foreground dark:text-warning-foreground mt-1">
                    This quiz requires you to sign in with a Google account
                  </p>
                </div>

                <Button className="w-full gap-2" onClick={handleGoogleSignIn}>
                  <Chrome className="w-4 h-4" />
                  Sign in with Google
                </Button>
              </div>
            )}

            <div className="flex items-center justify-center gap-4 text-sm text-muted-foreground pt-2">
              <span>{totalQuestions} questions</span>
              {quiz?.timerEnabled && (
                <span className="flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  {quiz.timerDurationMinutes} min
                </span>
              )}
            </div>
          </div>
        </Card>
      </div>
    );
  }

  // Submitting state
  if (pageState === "submitting") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-primary" />
          <p className="text-muted-foreground">Submitting your answers...</p>
        </div>
      </div>
    );
  }

  // Result state - Quiz-style view with highlights
  if (pageState === "result" && quizResult) {
    const { score, correctCount, total, publicLevel, results } = quizResult;
    const scorePercent = score || 0;

    return (
      <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-white dark:bg-zinc-800 border-b shadow-sm">
          <div className="max-w-3xl mx-auto px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => router.back()}
                >
                  <ArrowLeft className="w-5 h-5" />
                </Button>
                <div>
                  <div className="flex items-center gap-2">
                    <h1 className="font-semibold">{quiz?.title || "Quiz"}</h1>
                    {isOwner && (
                      <span className="text-xs px-2 py-0.5 rounded bg-warning-light text-warning-foreground dark:bg-warning-light dark:text-warning-foreground">
                        Preview
                      </span>
                    )}
                  </div>
                  {publicLevel >= 1 && (
                    <p className="text-sm text-muted-foreground">
                      Score: {correctCount}/{total} ({scorePercent.toFixed(1)}%)
                    </p>
                  )}
                </div>
              </div>
              <Button onClick={() => router.push("/")} variant="outline">
                Go Home
              </Button>
            </div>
          </div>
        </div>

        <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
          {/* Score Summary Card */}
          {publicLevel >= 1 && (
            <Card className="p-6">
              <div className="flex items-center gap-4">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10">
                  <Trophy className="w-8 h-8 text-primary" />
                </div>
                <div className="flex-1">
                  <h2 className="text-2xl font-bold mb-1">
                    {scorePercent >= 80
                      ? "Excellent! 🎉"
                      : scorePercent >= 60
                      ? "Good job! 👍"
                      : scorePercent >= 40
                      ? "Keep practicing! 💪"
                      : "Review the material! 📚"}
                  </h2>
                  <div className="flex items-center gap-3 mt-2">
                    <Progress value={scorePercent} className="h-2 flex-1" />
                    <span className="text-lg font-bold text-primary min-w-[60px] text-right">
                      {scorePercent.toFixed(1)}%
                    </span>
                  </div>
                </div>
              </div>
            </Card>
          )}

          {/* Passage Section */}
          {quiz?.passage && (
            <Card className="overflow-hidden">
              <button
                onClick={() => setShowPassage(!showPassage)}
                className="w-full flex items-center justify-between p-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <BookOpen className="w-5 h-5 text-primary" />
                  <span className="font-semibold">Reading Passage</span>
                </div>
                {showPassage ? (
                  <ChevronUp className="w-5 h-5" />
                ) : (
                  <ChevronDown className="w-5 h-5" />
                )}
              </button>
              {showPassage && (
                <div className="px-4 pb-4">
                  <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg text-sm leading-relaxed whitespace-pre-wrap max-h-80 overflow-y-auto">
                    {quiz.passage}
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* Questions with Results */}
          {questions.map((question, idx) => {
            const result = results?.find((r) => r.questionId === question.id);
            const userAnswerIdx =
              result?.userAnswer ?? userAnswers[question.id];
            const isCorrect = result?.isCorrect ?? false;
            const correctAnswerIdx = result?.correctAnswer;

            return (
              <Card key={question.id} className="p-6 space-y-4">
                {/* Question Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 space-y-2">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary">
                      Question {idx + 1}
                    </span>
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-lg">{question.content}</p>
                    </div>
                  </div>
                  {publicLevel >= 2 &&
                    (isCorrect ? (
                      <CheckCircle className="w-5 h-5 text-success shrink-0" />
                    ) : (
                      <XCircle className="w-5 h-5 text-error shrink-0" />
                    ))}
                </div>

                {/* Options */}
                <div className="space-y-2">
                  {question.options.map((option, optIdx) => {
                    const isUserAnswer = userAnswerIdx === optIdx;
                    const isCorrectAnswer =
                      publicLevel >= 3 && correctAnswerIdx === optIdx;
                    const showAsWrong =
                      publicLevel >= 2 && isUserAnswer && !isCorrect;

                    return (
                      <div
                        key={optIdx}
                        className={`flex items-center gap-3 p-3 rounded-lg border ${
                          isCorrectAnswer
                            ? "border-success/50 bg-success/5"
                            : showAsWrong
                            ? "border-error/50 bg-error/5"
                            : isUserAnswer
                            ? "border-primary bg-primary/5"
                            : "border-border"
                        }`}
                      >
                        <div
                          className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                            isCorrectAnswer
                              ? "bg-success text-white"
                              : showAsWrong
                              ? "bg-error text-white"
                              : isUserAnswer
                              ? "bg-primary text-primary-foreground"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {optionLabels[optIdx]}
                        </div>
                        <div className="flex-1 min-w-0 text-sm truncate">
                          {option}
                        </div>
                        {isCorrectAnswer && publicLevel >= 3 && (
                          <CheckCircle className="w-4 h-4 text-success ml-auto" />
                        )}
                        {showAsWrong && (
                          <XCircle className="w-4 h-4 text-error ml-auto" />
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Explanation */}
                {publicLevel >= 4 && result?.explanation && (
                  <div className="pl-11">
                    <div className="p-4 rounded-lg border border-zinc-200 dark:border-zinc-700">
                      <p className="text-sm font-medium mb-1">Explanation:</p>
                      <p className="text-sm text-muted-foreground">
                        {result.explanation}
                      </p>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}

          {/* Actions */}
          <Card className="p-6">
            <div className="flex gap-3">
              {!isOwner && quiz?.allowRedo && !quiz?.allowAnonymous && (
                <Button
                  className="flex-1 gap-2"
                  onClick={() => {
                    setUserAnswers({});
                    setQuizResult(null);
                    setShowWarning(false);
                    if (quiz?.timerEnabled && quiz?.timerDurationMinutes) {
                      setTimeRemaining(quiz.timerDurationMinutes * 60);
                    }
                    setPageState("quiz");
                  }}
                >
                  <RotateCcw className="w-4 h-4" />
                  Try Again
                </Button>
              )}
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => router.push("/")}
              >
                Go Home
              </Button>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  // Quiz state - Google Form style (all questions visible)
  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Sticky Header */}
      <div className="sticky top-0 z-10 bg-white dark:bg-zinc-800 border-b shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => window.close()}
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="font-semibold truncate">
                    {quiz?.title || "Quiz"}
                  </h1>
                  {isOwner && (
                    <span className="text-xs px-2 py-0.5 rounded bg-warning-light text-warning-foreground dark:bg-warning-light dark:text-warning-foreground">
                      Preview
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {answeredCount}/{totalQuestions} answered
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Timer - not shown for owner preview */}
              {!isOwner && quiz?.timerEnabled && timeRemaining !== null && (
                <div
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-full font-mono text-sm ${
                    showWarning
                      ? "bg-error-light text-error-foreground dark:bg-error-light dark:text-error-foreground animate-pulse"
                      : "bg-zinc-100 dark:bg-zinc-700"
                  }`}
                >
                  <Clock className="w-4 h-4" />
                  {formatTime(timeRemaining)}
                </div>
              )}
              {/* Logout button - not shown for owner preview */}
              {!isOwner && user && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleLogout}
                  title="Logout"
                >
                  <LogOut className="w-4 h-4" />
                </Button>
              )}
            </div>
          </div>
          <Progress value={progressPercent} className="h-1.5 mt-2" />
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        {/* Passage Section */}
        {quiz?.passage && (
          <Card className="overflow-hidden">
            <button
              onClick={() => setShowPassage(!showPassage)}
              className="w-full flex items-center justify-between p-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-primary" />
                <span className="font-semibold">Reading Passage</span>
              </div>
              {showPassage ? (
                <ChevronUp className="w-5 h-5" />
              ) : (
                <ChevronDown className="w-5 h-5" />
              )}
            </button>
            {showPassage && (
              <div className="px-4 pb-4">
                <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg text-sm leading-relaxed whitespace-pre-wrap max-h-80 overflow-y-auto">
                  {quiz.passage}
                </div>
              </div>
            )}
          </Card>
        )}

        {/* Timer Warning */}
        {showWarning && !isOwner && (
          <Card className="p-4 border-error bg-error-light dark:border-error dark:bg-error-light">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-error" />
              <div>
                <p className="font-medium text-error-foreground dark:text-error-foreground">
                  Time is running out!
                </p>
                <p className="text-sm text-error-foreground dark:text-error-foreground">
                  {quiz?.timerAutoSubmit
                    ? "Your quiz will be auto-submitted when time expires."
                    : "Please submit your answers soon."}
                </p>
              </div>
            </div>
          </Card>
        )}

        {/* All Questions */}
        {questions.map((question, idx) => (
          <Card
            key={question.id}
            className="p-6 space-y-4"
            id={`question-${question.id}`}
          >
            {/* Question Header */}
            <div className="flex items-start gap-3">
              <div className="flex-1 space-y-2">
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary">
                  Question {idx + 1}
                </span>
                <p className="font-medium text-lg">{question.content}</p>
                {userAnswers[question.id] === undefined && (
                  <p className="text-sm text-muted-foreground">
                    Select an answer
                  </p>
                )}
              </div>
            </div>

            {/* Options */}
            <div className="space-y-2">
              {question.options.map((option, optIdx) => (
                <div
                  key={optIdx}
                  onClick={() => handleAnswerSelect(question.id, optIdx)}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                    userAnswers[question.id] === optIdx
                      ? "border-primary bg-primary/10"
                      : "border-zinc-200 dark:border-zinc-700 hover:border-primary/50"
                  }`}
                >
                  <span
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                      userAnswers[question.id] === optIdx
                        ? "bg-primary text-primary-foreground"
                        : "bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400"
                    }`}
                  >
                    {optionLabels[optIdx]}
                  </span>
                  <span
                    className={
                      userAnswers[question.id] === optIdx ? "font-medium" : ""
                    }
                  >
                    {option}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        ))}

        {/* Submit Button at Bottom */}
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">
                {answeredCount === totalQuestions
                  ? "All questions answered!"
                  : `${totalQuestions - answeredCount} question(s) remaining`}
              </p>
              <p className="text-sm text-muted-foreground">
                {answeredCount === totalQuestions
                  ? "You can submit your answers now"
                  : "Answer all questions before submitting"}
              </p>
            </div>
            <Button
              size="lg"
              onClick={handleSubmit}
              disabled={answeredCount < totalQuestions}
            >
              <Send className="w-4 h-4 mr-2" />
              Submit Quiz
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
