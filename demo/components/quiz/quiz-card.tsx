"use client";

import { Quiz, QuizStatus } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Clock,
  FileText,
  Trash2,
  Play,
  CheckCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { useRouter } from "next/navigation";

interface QuizCardProps {
  quiz: Quiz;
  onDelete: () => void;
}

function getStatusInfo(status: QuizStatus) {
  switch (status) {
    case "uploading":
      return {
        label: "Uploading...",
        icon: Loader2,
        color: "text-blue-500",
        progress: 15,
      };
    case "processing_ocr":
      return {
        label: "Reading text...",
        icon: Loader2,
        color: "text-purple-500",
        progress: 45,
      };
    case "generating_quiz":
      return {
        label: "Generating questions...",
        icon: Loader2,
        color: "text-orange-500",
        progress: 75,
      };
    case "ready":
      return {
        label: "Ready",
        icon: CheckCircle,
        color: "text-green-500",
        progress: 100,
      };
    case "error":
      return {
        label: "Error",
        icon: AlertCircle,
        color: "text-red-500",
        progress: 0,
      };
    default:
      return {
        label: "Unknown",
        icon: AlertCircle,
        color: "text-zinc-500",
        progress: 0,
      };
  }
}

export function QuizCard({ quiz, onDelete }: QuizCardProps) {
  const router = useRouter();
  const statusInfo = getStatusInfo(quiz.status);
  const StatusIcon = statusInfo.icon;
  const isProcessing = [
    "uploading",
    "processing_ocr",
    "generating_quiz",
  ].includes(quiz.status);

  const questionCount = quiz.questions?.length || 0;
  const attemptCount = quiz.userAttempts?.length || 0;
  const lastAttempt = quiz.userAttempts?.[quiz.userAttempts.length - 1];

  const formatDate = (date: Date | { toDate: () => Date }) => {
    const d = "toDate" in date ? date.toDate() : date;
    return new Intl.DateTimeFormat("en-US", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  };

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-lg line-clamp-2">
              {quiz.title || `Quiz ${quiz.id?.slice(-6)}`}
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              {quiz.genre && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
                  {quiz.genre}
                </span>
              )}
              {quiz.topics && quiz.topics.length > 0 && (
                <>
                  {quiz.topics.map((topic, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-primary/10 text-primary"
                    >
                      {topic}
                    </span>
                  ))}
                </>
              )}
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 text-muted-foreground hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status */}
        <div className="flex items-center gap-2">
          <StatusIcon
            className={`w-4 h-4 ${statusInfo.color} ${
              isProcessing ? "animate-spin" : ""
            }`}
          />
          <span className={`text-sm font-medium ${statusInfo.color}`}>
            {statusInfo.label}
          </span>
        </div>

        {/* Progress bar for processing states */}
        {isProcessing && (
          <Progress value={statusInfo.progress} className="h-1.5" />
        )}

        {/* Stats for ready quizzes */}
        {quiz.status === "ready" && (
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <div className="flex items-center gap-1">
              <FileText className="w-4 h-4" />
              <span>{questionCount} questions</span>
            </div>
            {attemptCount > 0 && (
              <div className="flex items-center gap-1">
                <Clock className="w-4 h-4" />
                <span>{attemptCount} attempts</span>
              </div>
            )}
          </div>
        )}

        {/* Last score - fixed height container to prevent layout shift */}
        {quiz.status === "ready" && (
          <div className="min-h-11">
            {lastAttempt && (
              <div className="p-2 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm">
                Last: {lastAttempt.score.toFixed(1)}% (
                {Math.round((lastAttempt.score * lastAttempt.total) / 100)}/
                {lastAttempt.total} correct)
              </div>
            )}
          </div>
        )}

        {/* Error message */}
        {quiz.status === "error" && quiz.errorMessage && (
          <p className="text-sm text-red-500 line-clamp-2">
            {quiz.errorMessage}
          </p>
        )}

        {/* Date */}
        <p className="text-xs text-muted-foreground">
          Created: {formatDate(quiz.createdAt)}
        </p>

        {/* Action Button */}
        {quiz.status === "ready" && (
          <Button
            className="w-full gap-2"
            onClick={() => router.push(`/quiz/${quiz.id}`)}
          >
            <Play className="w-4 h-4" />
            Take Quiz
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
