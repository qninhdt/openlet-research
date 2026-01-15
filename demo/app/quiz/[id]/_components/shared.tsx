"use client";

import { useEffect, useState } from "react";
import { Timestamp } from "firebase/firestore";
import { PublicAttempt, Quiz, UserProfile } from "@/lib/types";
import {
  CheckCircle,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";
import { getUserProfile } from "@/lib/auth";
import { Button } from "@/components/ui/button";

const optionLabels = ["A", "B", "C", "D"];

export function ResponseCard({
  attempt,
  questions,
  formatDate,
  quizId,
}: {
  attempt: PublicAttempt;
  questions: Quiz["questions"];
  formatDate: (date: Timestamp | Date) => string;
  quizId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);

  // Fetch user profile for non-anonymous users
  useEffect(() => {
    if (!attempt.isAnonymous && attempt.userId) {
      getUserProfile(attempt.userId).then(setUserProfile);
    }
  }, [attempt.userId, attempt.isAnonymous]);

  const firstLetter = attempt.displayName?.[0]?.toUpperCase() || "A";
  const avatarUrl = !attempt.isAnonymous ? userProfile?.photoURL : null;

  return (
    <div className="border rounded-lg overflow-hidden">
      <div
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-4 p-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors cursor-pointer"
      >
        {avatarUrl ? (
          <img
            src={avatarUrl}
            alt={attempt.displayName}
            className="w-10 h-10 rounded-full object-cover shrink-0"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center font-semibold text-sm text-primary shrink-0">
            {firstLetter}
          </div>
        )}
        <div className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2">
            <p className="font-medium truncate">{attempt.displayName}</p>
            {attempt.isAnonymous && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-700">
                Guest
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="w-3 h-3" />
            <span>{formatDate(attempt.attemptAt)}</span>
          </div>
        </div>
        <div className="text-right mr-2">
          <p
            className={`text-lg font-bold ${
              attempt.score >= 70
                ? "text-success"
                : attempt.score >= 50
                ? "text-warning"
                : "text-error"
            }`}
          >
            {attempt.score.toFixed(1)}%
          </p>
          <div className="flex items-center gap-1 text-sm text-muted-foreground">
            <CheckCircle className="w-3 h-3 text-success" />
            <span>{attempt.correctCount}</span>
            <XCircle className="w-3 h-3 text-error ml-1" />
            <span>{attempt.total - attempt.correctCount}</span>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            if (attempt.id) {
              window.open(
                `/play/${quizId}/attempt/${attempt.id}`,
                "_blank",
                "noopener,noreferrer"
              );
            }
          }}
        >
          <ExternalLink className="w-4 h-4" />
        </Button>
        {expanded ? (
          <ChevronUp className="w-5 h-5 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-5 h-5 text-muted-foreground" />
        )}
      </div>

      {expanded && (
        <div className="border-t p-4 space-y-4 bg-zinc-50 dark:bg-zinc-900/50">
          {questions?.map((q, idx) => {
            const userAnswer = attempt.userAnswers?.[q.id];
            const isCorrect = userAnswer === q.correct;

            return (
              <div key={q.id} className="space-y-2">
                <div className="flex items-start gap-2">
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary font-semibold text-xs shrink-0">
                    {idx + 1}
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">{q.content}</p>
                      {isCorrect ? (
                        <CheckCircle className="w-4 h-4 text-success shrink-0" />
                      ) : (
                        <XCircle className="w-4 h-4 text-error shrink-0" />
                      )}
                    </div>
                  </div>
                </div>
                <div className="ml-8 space-y-1">
                  {q.options.map((opt, optIdx) => {
                    const isUserAnswer = userAnswer === optIdx;
                    const isCorrectAnswer = q.correct === optIdx;

                    return (
                      <div
                        key={optIdx}
                        className={`flex items-center gap-2 p-2 rounded text-sm ${"border border-transparent"}`}
                      >
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            isCorrectAnswer
                              ? "bg-success text-success-foreground"
                              : isUserAnswer && !isCorrect
                              ? "bg-error text-error-foreground"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {optionLabels[optIdx]}
                        </span>
                        <span
                          className={
                            isUserAnswer || isCorrectAnswer ? "font-medium" : ""
                          }
                        >
                          {opt}
                        </span>
                        {isUserAnswer && (
                          <span className="text-xs text-muted-foreground">
                            (User&apos;s answer)
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function formatDate(date: Timestamp | Date) {
  const d = "toDate" in date ? date.toDate() : date;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}
