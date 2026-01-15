"use client";

import { useState } from "react";
import { Quiz, QuizStatus } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  FileText,
  Trash2,
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
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const statusInfo = getStatusInfo(quiz.status);
  const StatusIcon = statusInfo.icon;
  const isProcessing = [
    "uploading",
    "processing_ocr",
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

  const handleDelete = () => {
    setShowDeleteDialog(false);
    onDelete();
  };

  return (
    <>
      <Card
        className="hover:shadow-md transition-shadow cursor-pointer group"
        onClick={() =>
          quiz.status === "ready" && router.push(`/quiz/${quiz.id}`)
        }
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <CardTitle className="text-lg line-clamp-1">
                  {quiz.title || "Untitled Quiz"}
                </CardTitle>
                {quiz.isPublished ? (
                  <Globe className="w-4 h-4 text-green-600 shrink-0" />
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
            <Button
              variant="ghost"
              size="icon"
              className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setShowDeleteDialog(true);
              }}
              title="Delete quiz"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
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
            <p className="text-sm text-red-500 line-clamp-2">
              {quiz.errorMessage}
            </p>
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

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Quiz</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &quot;
              {quiz.title || "Untitled Quiz"}&quot;? This action cannot be
              undone.
              {publicAttemptCount > 0 && (
                <span className="block mt-2 text-yellow-600 dark:text-yellow-500">
                  ⚠️ This quiz has {publicAttemptCount} response(s) that will
                  also be deleted.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
            >
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
