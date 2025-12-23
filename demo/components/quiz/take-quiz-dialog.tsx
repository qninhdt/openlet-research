"use client";

import { useState } from "react";
import { updateDoc, doc, Timestamp, arrayUnion } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { Quiz, UserAttempt } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  CheckCircle,
  XCircle,
  ChevronLeft,
  ChevronRight,
  Send,
  RotateCcw,
  Trophy,
} from "lucide-react";

interface TakeQuizDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  quiz: Quiz;
}

type ViewMode = "quiz" | "result";

export function TakeQuizDialog({
  open,
  onOpenChange,
  quiz,
}: TakeQuizDialogProps) {
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [userAnswers, setUserAnswers] = useState<Record<number, number>>({});
  const [viewMode, setViewMode] = useState<ViewMode>("quiz");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const questions = quiz.questions || [];
  const currentQuestion = questions[currentQuestionIndex];
  const totalQuestions = questions.length;

  const answeredCount = Object.keys(userAnswers).length;
  const progressPercent = (answeredCount / totalQuestions) * 100;

  const resetQuiz = () => {
    setCurrentQuestionIndex(0);
    setUserAnswers({});
    setViewMode("quiz");
  };

  const handleClose = () => {
    resetQuiz();
    onOpenChange(false);
  };

  const handleAnswerSelect = (questionId: number, optionIndex: number) => {
    if (viewMode === "result") return;
    setUserAnswers((prev) => ({
      ...prev,
      [questionId]: optionIndex,
    }));
  };

  const goToNext = () => {
    if (currentQuestionIndex < totalQuestions - 1) {
      setCurrentQuestionIndex((prev) => prev + 1);
    }
  };

  const goToPrev = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex((prev) => prev - 1);
    }
  };

  const calculateScore = (): number => {
    let correct = 0;
    for (const question of questions) {
      if (userAnswers[question.id] === question.correct) {
        correct++;
      }
    }
    return correct;
  };

  const handleSubmit = async () => {
    if (!quiz.id) return;

    setIsSubmitting(true);
    try {
      const score = calculateScore();
      const attempt: UserAttempt = {
        attemptAt: Timestamp.now(),
        score,
        total: totalQuestions,
        userAnswers,
      };

      await updateDoc(doc(db, "quizzes", quiz.id), {
        userAttempts: arrayUnion(attempt),
      });

      setViewMode("result");
    } catch (error) {
      console.error("Error submitting quiz:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getOptionLabel = (index: number) => {
    return ["A", "B", "C", "D"][index] || "";
  };

  const score = viewMode === "result" ? calculateScore() : 0;
  const scorePercent =
    viewMode === "result" ? (score / totalQuestions) * 100 : 0;

  if (!questions.length) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>
            {viewMode === "quiz"
              ? quiz.title || "Làm bài kiểm tra"
              : "Kết quả bài kiểm tra"}
          </DialogTitle>
        </DialogHeader>

        {viewMode === "quiz" ? (
          <>
            {/* Progress */}
            <div className="space-y-2">
              <div className="flex justify-between text-sm text-muted-foreground">
                <span>
                  Câu {currentQuestionIndex + 1}/{totalQuestions}
                </span>
                <span>
                  Đã trả lời: {answeredCount}/{totalQuestions}
                </span>
              </div>
              <Progress value={progressPercent} className="h-2" />
            </div>

            {/* Question */}
            <div className="flex-1 overflow-hidden">
              <ScrollArea className="h-full pr-4">
                <div className="space-y-6 py-4">
                  <div className="space-y-2">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary">
                      {currentQuestion.type || "General"}
                    </span>
                    <h3 className="text-lg font-medium leading-relaxed">
                      {currentQuestion.content}
                    </h3>
                  </div>

                  <RadioGroup
                    value={userAnswers[currentQuestion.id]?.toString() || ""}
                    onValueChange={(value) =>
                      handleAnswerSelect(currentQuestion.id, parseInt(value))
                    }
                  >
                    <div className="space-y-3">
                      {currentQuestion.options.map((option, index) => (
                        <label
                          key={index}
                          className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                            userAnswers[currentQuestion.id] === index
                              ? "border-primary bg-primary/5"
                              : "border-zinc-200 dark:border-zinc-800 hover:border-primary/50"
                          }`}
                        >
                          <RadioGroupItem
                            value={index.toString()}
                            id={`option-${index}`}
                          />
                          <div className="flex-1">
                            <Label
                              htmlFor={`option-${index}`}
                              className="font-medium cursor-pointer"
                            >
                              {getOptionLabel(index)}.{" "}
                            </Label>
                            <span className="text-zinc-700 dark:text-zinc-300">
                              {option}
                            </span>
                          </div>
                        </label>
                      ))}
                    </div>
                  </RadioGroup>
                </div>
              </ScrollArea>
            </div>

            {/* Navigation */}
            <div className="flex items-center justify-between pt-4 border-t">
              <Button
                variant="outline"
                onClick={goToPrev}
                disabled={currentQuestionIndex === 0}
              >
                <ChevronLeft className="w-4 h-4 mr-1" />
                Trước
              </Button>

              <div className="flex gap-2">
                {currentQuestionIndex < totalQuestions - 1 ? (
                  <Button onClick={goToNext}>
                    Tiếp
                    <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                ) : (
                  <Button
                    onClick={handleSubmit}
                    disabled={answeredCount < totalQuestions || isSubmitting}
                    className="gap-2"
                  >
                    <Send className="w-4 h-4" />
                    {isSubmitting ? "Đang nộp..." : "Nộp bài"}
                  </Button>
                )}
              </div>
            </div>
          </>
        ) : (
          /* Result View */
          <div className="flex-1 overflow-hidden">
            <ScrollArea className="h-full pr-4">
              <div className="space-y-6 py-4">
                {/* Score Summary */}
                <div className="text-center space-y-4 p-6 rounded-xl bg-linear-to-br from-primary/10 to-primary/5">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/20">
                    <Trophy className="w-8 h-8 text-primary" />
                  </div>
                  <div>
                    <p className="text-4xl font-bold text-primary">
                      {score}/{totalQuestions}
                    </p>
                    <p className="text-muted-foreground mt-1">
                      {scorePercent >= 80
                        ? "Xuất sắc! 🎉"
                        : scorePercent >= 60
                        ? "Tốt lắm! 👍"
                        : scorePercent >= 40
                        ? "Cố gắng thêm! 💪"
                        : "Cần học lại! 📚"}
                    </p>
                  </div>
                </div>

                <Separator />

                {/* Answer Review */}
                <div className="space-y-4">
                  <h4 className="font-semibold">Chi tiết câu trả lời</h4>
                  {questions.map((question, qIndex) => {
                    const userAnswer = userAnswers[question.id];
                    const isCorrect = userAnswer === question.correct;

                    return (
                      <div
                        key={question.id}
                        className={`p-4 rounded-lg border ${
                          isCorrect
                            ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-900/20"
                            : "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-900/20"
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          {isCorrect ? (
                            <CheckCircle className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
                          ) : (
                            <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                          )}
                          <div className="flex-1 space-y-2">
                            <p className="font-medium">
                              Câu {qIndex + 1}: {question.content}
                            </p>
                            <div className="text-sm space-y-1">
                              <p>
                                <span className="text-muted-foreground">
                                  Đáp án của bạn:{" "}
                                </span>
                                <span
                                  className={
                                    isCorrect
                                      ? "text-green-600"
                                      : "text-red-600"
                                  }
                                >
                                  {getOptionLabel(userAnswer)}.{" "}
                                  {question.options[userAnswer]}
                                </span>
                              </p>
                              {!isCorrect && (
                                <p>
                                  <span className="text-muted-foreground">
                                    Đáp án đúng:{" "}
                                  </span>
                                  <span className="text-green-600">
                                    {getOptionLabel(question.correct)}.{" "}
                                    {question.options[question.correct]}
                                  </span>
                                </p>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </ScrollArea>

            {/* Actions */}
            <div className="flex gap-3 pt-4 border-t">
              <Button
                variant="outline"
                onClick={handleClose}
                className="flex-1"
              >
                Đóng
              </Button>
              <Button onClick={resetQuiz} className="flex-1 gap-2">
                <RotateCcw className="w-4 h-4" />
                Làm lại
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
