"use client";

import { useEffect, useState } from "react";
import {
  collection,
  query,
  where,
  orderBy,
  onSnapshot,
  deleteDoc,
  doc,
} from "firebase/firestore";
import { useRouter } from "next/navigation";
import { db } from "@/lib/firebase";
import { useAuthStore } from "@/lib/store";
import { Quiz } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoginButton } from "@/components/auth/login-button";
import { QuizCard } from "@/components/quiz/quiz-card";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Plus, BookOpen, Loader2 } from "lucide-react";

export function DashboardPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) {
      // Use setTimeout to avoid synchronous setState in effect
      setTimeout(() => setLoading(false), 0);
      return;
    }

    // Subscribe to quizzes collection
    const q = query(
      collection(db, "quizzes"),
      where("userId", "==", user.uid),
      orderBy("createdAt", "desc")
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const quizData = snapshot.docs
        .map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }))
        .filter(
          (quiz) => !(quiz as Quiz & { isImportJob?: boolean }).isImportJob
        ) as Quiz[];
      setQuizzes(quizData);
      setLoading(false);
    });

    return () => unsubscribe();
  }, [user]);


  const handleCreateQuiz = () => {
    router.push("/quiz/new/edit");
  };

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Header */}
      <header className="border-b bg-white dark:bg-zinc-950 sticky top-0 z-40">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary text-primary-foreground">
              <BookOpen className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold">Openlet</h1>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <LoginButton />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">
              Your Quizzes
            </h2>
            <p className="text-muted-foreground mt-1">
              Manage and take your created quizzes
            </p>
          </div>
          <Button onClick={handleCreateQuiz} className="gap-2">
            <Plus className="w-4 h-4" />
            Create New
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : quizzes.length === 0 ? (
          <Card className="text-center py-16">
            <CardHeader>
              <CardTitle className="text-xl">No quizzes yet</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground mb-6">
                Create a quiz and add questions manually, or import from
                documents using AI
              </p>
              <Button onClick={handleCreateQuiz} className="gap-2">
                <Plus className="w-4 h-4" />
                Create your first quiz
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {quizzes.map((quiz) => (
              <QuizCard key={quiz.id} quiz={quiz} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
