"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { doc, getDoc, updateDoc, Timestamp } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useAuthStore } from "@/lib/store";
import type { Quiz } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ArrowLeft, BookOpen, FileText, CheckCircle2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function QuizPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuthStore();
  const { toast } = useToast();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState(true);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [submitted, setSubmitted] = useState(false);
  const [score, setScore] = useState<number | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const loadQuiz = async () => {
      if (!user) {
        router.push("/");
        return;
      }

      try {
        const quizId = params.id as string;
        const quizDoc = await getDoc(doc(db, "quizzes", quizId));

        if (!quizDoc.exists()) {
          toast({
            title: "Quiz not found",
            variant: "destructive",
          });
          router.push("/");
          return;
        }

        const quizData = { id: quizDoc.id, ...quizDoc.data() } as Quiz;

        if (quizData.userId !== user.uid) {
          toast({
            title: "Access denied",
            variant: "destructive",
          });
          router.push("/");
          return;
        }

        if (quizData.status !== "ready") {
          toast({
            title: "Quiz not ready",
            variant: "destructive",
          });
          router.push("/");
          return;
        }

        setQuiz(quizData);
      } catch (error) {
        console.error("Error loading quiz:", error);
        toast({
          title: "Error loading quiz",
          variant: "destructive",
        });
        router.push("/");
      } finally {
        setLoading(false);
      }
    };

    loadQuiz();
  }, [user, params.id, router, toast]);

  const handleAnswerChange = (questionId: number, answerIndex: number) => {
    setAnswers({ ...answers, [questionId]: answerIndex });
  };

  const handleSubmit = async () => {
    if (!quiz || !user) return;

    const questions = quiz.questions || [];
    let correctCount = 0;

    questions.forEach((q) => {
      if (answers[q.id] === q.correct) {
        correctCount++;
      }
    });

    const finalScore = (correctCount / questions.length) * 100;
    setScore(finalScore);
    setSubmitted(true);

    try {
      const userAttempts = quiz.userAttempts || [];
      userAttempts.push({
        attemptAt: Timestamp.now(),
        score: finalScore,
        total: questions.length,
        userAnswers: answers,
      });

      await updateDoc(doc(db, "quizzes", quiz.id!), {
        userAttempts,
      });

      toast({
        title: "Quiz submitted!",
        description: `You got ${correctCount}/${
          questions.length
        } correct (${finalScore.toFixed(1)}%)`,
      });
    } catch (error) {
      console.error("Error saving attempt:", error);
    }
  };

  const handleRetry = () => {
    setAnswers({});
    setSubmitted(false);
    setScore(null);
    setRetryKey((prev) => prev + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading quiz...</p>
        </div>
      </div>
    );
  }

  if (!quiz) {
    return null;
  }

  const questions = quiz.questions || [];
  const answeredCount = Object.keys(answers).length;
  const allAnswered = answeredCount === questions.length;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-white/95 dark:bg-zinc-950/95 backdrop-blur supports-[backdrop-filter]:bg-white/60 dark:supports-[backdrop-filter]:bg-zinc-950/60">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => router.push("/")}
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div className="flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-primary" />
              <h1 className="font-semibold text-lg hidden sm:block">
                {quiz.title || "Quiz"}
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {!submitted && (
              <div className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">
                  {answeredCount}
                </span>
                /{questions.length} questions
              </div>
            )}
            {submitted && score !== null && (
              <div className="flex items-center gap-2 text-sm font-medium">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span className="text-green-600 dark:text-green-500">
                  {score.toFixed(1)}%
                </span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        <div className="grid lg:grid-cols-2 gap-6">
          {/* Reading Passage */}
          <div className="lg:sticky lg:top-20 lg:self-start">
            <Card className="shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-primary" />
                  <CardTitle className="text-lg">Reading Passage</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <ScrollArea className="h-[calc(100vh-220px)] lg:h-[calc(100vh-200px)] pr-4">
                  <div className="prose prose-sm dark:prose-invert max-w-none pb-4">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {quiz.ocrText}
                    </p>
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </div>

          {/* Questions */}
          <div className="space-y-4">
            {questions.map((question, index) => {
              const userAnswer = answers[question.id];
              const isCorrect = submitted && userAnswer === question.correct;
              const isWrong =
                submitted &&
                userAnswer !== undefined &&
                userAnswer !== question.correct;

              return (
                <Card
                  key={question.id}
                  className={`shadow-sm transition-colors ${
                    isCorrect
                      ? "border-green-500 bg-green-50 dark:bg-green-950/20"
                      : isWrong
                      ? "border-red-500 bg-red-50 dark:bg-red-950/20"
                      : ""
                  }`}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start gap-3">
                      <div
                        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${
                          isCorrect
                            ? "bg-green-500 text-white"
                            : isWrong
                            ? "bg-red-500 text-white"
                            : "bg-primary/10 text-primary"
                        }`}
                      >
                        {index + 1}
                      </div>
                      <p className="text-sm leading-relaxed flex-1">
                        {question.content}
                      </p>
                    </div>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <RadioGroup
                      key={`question-${question.id}-${retryKey}`}
                      value={userAnswer?.toString()}
                      onValueChange={(value) =>
                        !submitted &&
                        handleAnswerChange(question.id, parseInt(value))
                      }
                      disabled={submitted}
                      className="space-y-2"
                    >
                      {question.options.map((option, optionIndex) => {
                        const isSelected = userAnswer === optionIndex;
                        const isCorrectOption =
                          submitted && optionIndex === question.correct;
                        const isWrongSelected =
                          submitted && isSelected && !isCorrectOption;

                        return (
                          <div
                            key={optionIndex}
                            className={`flex items-center space-x-3 rounded-lg p-3 transition-colors ${
                              isCorrectOption
                                ? "bg-green-100 dark:bg-green-950/30 border border-green-500"
                                : isWrongSelected
                                ? "bg-red-100 dark:bg-red-950/30 border border-red-500"
                                : isSelected
                                ? "bg-primary/5 border border-primary/20"
                                : "hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-transparent"
                            }`}
                          >
                            <RadioGroupItem
                              value={optionIndex.toString()}
                              id={`q${question.id}-option${optionIndex}`}
                            />
                            <Label
                              htmlFor={`q${question.id}-option${optionIndex}`}
                              className={`flex-1 text-sm leading-relaxed cursor-pointer ${
                                submitted ? "cursor-default" : ""
                              } ${
                                isCorrectOption
                                  ? "font-medium text-green-700 dark:text-green-400"
                                  : isWrongSelected
                                  ? "text-red-700 dark:text-red-400"
                                  : ""
                              }`}
                            >
                              <span className="font-semibold mr-2">
                                {String.fromCharCode(65 + optionIndex)}.
                              </span>
                              {option}
                            </Label>
                          </div>
                        );
                      })}
                    </RadioGroup>
                  </CardContent>
                </Card>
              );
            })}

            {/* Submit Button */}
            <div className="sticky bottom-0  bg-gradient-to-t from-zinc-50 dark:from-zinc-900 via-zinc-50 dark:via-zinc-900 to-transparent">
              <Card className="shadow-lg">
                <CardContent className="p-4">
                  {!submitted ? (
                    <Button
                      onClick={handleSubmit}
                      disabled={!allAnswered}
                      className="w-full"
                      size="lg"
                    >
                      {allAnswered
                        ? "Submit Quiz"
                        : `Please answer all ${questions.length} questions`}
                    </Button>
                  ) : (
                    <div className="space-y-3">
                      <div className="text-center py-2">
                        <p className="text-2xl font-bold text-green-600 dark:text-green-500">
                          {score?.toFixed(1)}%
                        </p>
                        <p className="text-sm text-muted-foreground mt-1">
                          {
                            questions.filter((q) => answers[q.id] === q.correct)
                              .length
                          }
                          /{questions.length} correct
                        </p>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <Button
                          variant="outline"
                          onClick={handleRetry}
                          className="w-full"
                        >
                          Retry
                        </Button>
                        <Button
                          onClick={() => router.push("/")}
                          className="w-full"
                        >
                          Back to Home
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
