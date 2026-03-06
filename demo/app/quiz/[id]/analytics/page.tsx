"use client";

import { useParams, useRouter } from "next/navigation";
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useEffect, useState } from "react";
import { Quiz } from "@/lib/types";
import { Brain } from "lucide-react";

export default function QuizAnalyticsPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = params.id as string;
  const [quiz, setQuiz] = useState<Quiz | null>(null);

  useEffect(() => {
    if (!quizId) return;
    const unsubscribe = onSnapshot(doc(db, "quizzes", quizId), (doc) => {
      if (doc.exists()) {
        const quizData = { id: doc.id, ...doc.data() } as Quiz;
        setQuiz(quizData);
      }
    });
    return () => unsubscribe();
  }, [quizId, router]);

  if (!quiz) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center text-muted-foreground">
          <Brain className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No analytics data available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="text-center text-muted-foreground">
        <Brain className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>Analytics coming soon</p>
      </div>
    </div>
  );
}
