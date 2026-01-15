"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, usePathname } from "next/navigation";
import { doc, onSnapshot, deleteDoc } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useAuthStore } from "@/lib/store";
import { Quiz } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import {
  ArrowLeft,
  Edit,
  Settings,
  Loader2,
  Trash2,
  Eye,
  BarChart3,
  Users,
  FileText,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function QuizLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const { toast } = useToast();
  const { user, loading: authLoading } = useAuthStore();
  const quizId = params.id as string;

  const [loading, setLoading] = useState(true);
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  useEffect(() => {
    // Wait for auth to finish loading before making decisions
    if (authLoading) {
      return;
    }

    if (!user) {
      router.push("/");
      return;
    }

    if (!quizId) return;

    // Special case: creating a new quiz (no Firestore document yet)
    if (quizId === "new") {
      return;
    }

    const unsubscribe = onSnapshot(
      doc(db, "quizzes", quizId),
      (doc) => {
        if (doc.exists()) {
          const quizData = { id: doc.id, ...doc.data() } as Quiz;
          if (quizData.userId !== user.uid) {
            setError("You don't have permission to view this quiz");
            router.push("/");
            return;
          }
          setQuiz(quizData);
        } else {
          setError("Quiz not found");
        }
        setLoading(false);
      },
      (err) => {
        console.error("Error fetching quiz:", err);
        setError("Failed to load quiz");
        setLoading(false);
      }
    );

    return () => unsubscribe();
  }, [quizId, user, authLoading, router]);

  const handleDelete = async () => {
    if (!quizId || deleting) return;

    try {
      setDeleting(true);
      await deleteDoc(doc(db, "quizzes", quizId));
      toast({ title: "Quiz deleted successfully" });
      router.push("/");
    } catch (err) {
      console.error("Error deleting quiz:", err);
      toast({ title: "Error deleting quiz", variant: "destructive" });
      setDeleting(false);
    }
  };

  // Determine active tab based on current route
  const getActiveTab = () => {
    if (pathname.endsWith("/edit")) return "edit";
    if (pathname.endsWith("/responses")) return "responses";
    if (pathname.endsWith("/questions")) return "questions";
    if (pathname.endsWith("/settings")) return "settings";
    return "overview";
  };

  const isEditPage = pathname.endsWith("/edit");
  const isNewQuiz = quizId === "new";

  if (!isNewQuiz && (loading || authLoading)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // For existing quizzes, show error state if quiz failed to load
  if (!isNewQuiz && (error || !quiz)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error || "Quiz not found"}</p>
          <Button onClick={() => router.push("/")}>Go Home</Button>
        </div>
      </div>
    );
  }

  const quizTitle =
    !isNewQuiz && quiz && quiz.title ? quiz.title : "Untitled Quiz";

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Header - Only show if not edit page and not new quiz */}
      {!isEditPage && !isNewQuiz && quiz && (
        <div className="bg-white dark:bg-zinc-800 border-b sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => router.push("/")}
                >
                  <ArrowLeft className="w-5 h-5" />
                </Button>
                <div>
                  <h1 className="text-lg font-bold">{quizTitle}</h1>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(`/play/${quizId}`, "_blank")}
                >
                  <Eye className="w-4 h-4 mr-2" />
                  Preview
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push(`/quiz/${quizId}/edit`)}
                >
                  <Edit className="w-4 h-4 mr-2" />
                  Edit
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:text-red-700"
                  onClick={() => setShowDeleteDialog(true)}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs - Only show if not on edit page and not new quiz */}
      {!isEditPage && !isNewQuiz && (
        <div className="bg-white dark:bg-zinc-800 border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <Tabs value={getActiveTab()}>
              <TabsList className="h-12 bg-transparent border-0">
                <TabsTrigger
                  value="overview"
                  onClick={() => router.push(`/quiz/${quizId}`)}
                  className="data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none"
                >
                  <BarChart3 className="w-4 h-4 mr-2" />
                  Overview
                </TabsTrigger>
                <TabsTrigger
                  value="responses"
                  onClick={() => router.push(`/quiz/${quizId}/responses`)}
                  className="data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none"
                >
                  <Users className="w-4 h-4 mr-2" />
                  Responses
                </TabsTrigger>
                <TabsTrigger
                  value="questions"
                  onClick={() => router.push(`/quiz/${quizId}/questions`)}
                  className="data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none"
                >
                  <FileText className="w-4 h-4 mr-2" />
                  Questions
                </TabsTrigger>
                <TabsTrigger
                  value="settings"
                  onClick={() => router.push(`/quiz/${quizId}/settings`)}
                  className="data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none"
                >
                  <Settings className="w-4 h-4 mr-2" />
                  Settings
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </div>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Quiz?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &ldquo;{quizTitle}&rdquo;? This
              action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
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
