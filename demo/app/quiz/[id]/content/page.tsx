"use client";

import { useParams } from "next/navigation";
import { doc, onSnapshot, collection, query } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useEffect, useState } from "react";
import { Quiz, PublicAttempt } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { BookOpen } from "lucide-react";

export default function ContentPage() {
  const params = useParams();
  const quizId = params.id as string;
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [attempts, setAttempts] = useState<PublicAttempt[]>([]);

  // Subscribe to quiz document
  useEffect(() => {
    if (!quizId) return;
    const unsubscribe = onSnapshot(doc(db, "quizzes", quizId), (doc) => {
      if (doc.exists()) {
        setQuiz({ id: doc.id, ...doc.data() } as Quiz);
      }
    });
    return () => unsubscribe();
  }, [quizId]);

  // Subscribe to attempts subcollection
  useEffect(() => {
    if (!quizId) return;
    const attemptsQuery = query(collection(db, "quizzes", quizId, "attempts"));
    const unsubscribe = onSnapshot(attemptsQuery, (snapshot) => {
      const attemptsData = snapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      })) as PublicAttempt[];
      setAttempts(attemptsData);
    });
    return () => unsubscribe();
  }, [quizId]);

  if (!quiz) return null;

  const questions = quiz.questions || [];
  const passage = quiz.passage || "";

  interface QuestionStats {
    questionId: number;
    content: string;
    correctCount: number;
    totalAttempts: number;
    correctRate: number;
    options: {
      label: string;
      text: string;
      count: number;
      isCorrect: boolean;
    }[];
  }

  const questionStats: QuestionStats[] = questions.map((q) => {
    const optionCounts = [0, 0, 0, 0];
    let correctCount = 0;
    attempts.forEach((attempt) => {
      const userAnswer = attempt.userAnswers?.[q.id];
      if (userAnswer !== undefined && userAnswer >= 0 && userAnswer <= 3) {
        optionCounts[userAnswer]++;
        if (userAnswer === q.correct) correctCount++;
      }
    });
    return {
      questionId: q.id,
      content: q.content,
      correctCount,
      totalAttempts: attempts.length,
      correctRate:
        attempts.length > 0 ? (correctCount / attempts.length) * 100 : 0,
      options: q.options.map((opt, idx) => ({
        label: ["A", "B", "C", "D"][idx],
        text: opt,
        count: optionCounts[idx],
        isCorrect: idx === q.correct,
      })),
    };
  });

  return (
    <div className="space-y-6">
      {/* Passage Section */}
      {passage && (
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <BookOpen className="w-5 h-5 text-primary" />
            <h3 className="font-semibold">Reading Passage</h3>
          </div>
          <div className="p-4 bg-muted rounded-lg text-sm leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">
            {passage}
          </div>
        </Card>
      )}

      {/* Questions Section */}
      <div className="space-y-4">
        {questionStats.length === 0 ? (
          <Card className="p-8">
            <p className="text-center text-muted-foreground">
              No questions available
            </p>
          </Card>
        ) : (
          questionStats.map((stat, idx) => (
            <Card key={stat.questionId} className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary mb-2">
                    Question {idx + 1}
                  </span>
                  <h4 className="font-medium">{stat.content}</h4>
                </div>
                <div
                  className={`px-3 py-1 rounded-full text-sm font-medium ${
                    stat.correctRate >= 70
                      ? "bg-success/20 text-success"
                      : stat.correctRate >= 50
                        ? "bg-warning/20 text-warning"
                        : "bg-error/20 text-error"
                  }`}
                >
                  {stat.correctRate.toFixed(0)}% correct
                </div>
              </div>
              <div className="space-y-2">
                {stat.options.map((opt) => (
                  <div
                    key={opt.label}
                    className={`flex items-center gap-3 p-3 rounded-lg border ${
                      opt.isCorrect
                        ? "border-success/50 bg-success/5"
                        : "border-border"
                    }`}
                  >
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                        opt.isCorrect
                          ? "bg-success text-white"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {opt.label}
                    </div>
                    <div className="flex-1 min-w-0 text-sm truncate">
                      {opt.text}
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full ${opt.isCorrect ? "bg-success" : "bg-muted-foreground/40"}`}
                          style={{
                            width: `${stat.totalAttempts > 0 ? (opt.count / stat.totalAttempts) * 100 : 0}%`,
                          }}
                        />
                      </div>
                      <span className="text-sm text-muted-foreground w-12 text-right">
                        {opt.count}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
