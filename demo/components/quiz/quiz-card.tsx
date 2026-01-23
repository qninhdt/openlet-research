"use client";

import { Quiz, QuizStatus } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  FileText,
  CheckCircle,
  AlertCircle,
  Loader2,
  Globe,
  Lock,
  Users,
  ExternalLink,
} from "lucide-react";
import { useRouter } from "next/navigation";

interface QuizCardProps {
  quiz: Quiz;
}

function getStatusInfo(status: QuizStatus) {
  switch (status) {
    case "uploading":
      return {
        label: "Uploading...",
        icon: Loader2,
        color: "text-info",
        progress: 15,
      };
    case "processing_ocr":
      return {
        label: "Reading text...",
        icon: Loader2,
        color: "text-purple-500",
        progress: 35,
      };
    case "extracting_info":
      return {
        label: "Extracting insights...",
        icon: Loader2,
        color: "text-cyan-500",
        progress: 55,
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
        color: "text-success",
        progress: 100,
      };
    case "error":
      return {
        label: "Error",
        icon: AlertCircle,
        color: "text-error",
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

export function QuizCard({ quiz }: QuizCardProps) {
  const router = useRouter();

  const statusInfo = getStatusInfo(quiz.status);
  const StatusIcon = statusInfo.icon;
  const isProcessing = [
    "uploading",
    "processing_ocr",
    "extracting_info",
    "generating_quiz",
  ].includes(quiz.status);

  const questionCount = quiz.questions?.length || 0;
  const publicAttemptCount = quiz.metrics?.totalResponses || 0;

  const formatDate = (date: Date | { toDate: () => Date }) => {
    const d = "toDate" in date ? date.toDate() : date;
    return new Intl.DateTimeFormat("en-US", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(d);
  };

  return (
    <Card
      className="hover:shadow-md transition-shadow cursor-pointer group"
      onClick={() => quiz.status === "ready" && router.push(`/quiz/${quiz.id}`)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <CardTitle className="text-lg line-clamp-1">
                {quiz.title || "Untitled Quiz"}
              </CardTitle>
              {quiz.isPublished ? (
                <Globe className="w-4 h-4 text-success shrink-0" />
              ) : (
                <Lock className="w-4 h-4 text-zinc-400 shrink-0" />
              )}
            </div>
            {quiz.description && (
              <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                {quiz.description}
              </p>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
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
            {publicAttemptCount > 0 && (
              <div className="flex items-center gap-1">
                <Users className="w-4 h-4" />
                <span>{publicAttemptCount} responses</span>
              </div>
            )}
          </div>
        )}

        {/* Tags */}
        {quiz.topics && quiz.topics.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {quiz.topics.slice(0, 3).map((topic, idx) => (
              <span
                key={idx}
                className="inline-flex items-center px-2 py-0.5 rounded-md text-xs bg-primary/10 text-primary"
              >
                {topic}
              </span>
            ))}
            {quiz.topics.length > 3 && (
              <span className="text-xs text-muted-foreground">
                +{quiz.topics.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Error message */}
        {quiz.status === "error" && quiz.errorMessage && (
          <p className="text-sm text-error line-clamp-2">{quiz.errorMessage}</p>
        )}

        {/* Date */}
        <p className="text-xs text-muted-foreground">
          Created: {formatDate(quiz.createdAt)}
        </p>

        {/* Action hint for ready quizzes */}
        {quiz.status === "ready" && (
          <div className="flex items-center gap-1 text-xs text-primary opacity-0 group-hover:opacity-100 transition-opacity">
            <ExternalLink className="w-3 h-3" />
            <span>Click to view details</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
