"use client";

import { useParams } from "next/navigation";
import {
  doc,
  onSnapshot,
  collection,
  query,
  orderBy,
} from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useEffect, useState } from "react";
import { Quiz, PublicAttempt } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ResponseCard, formatDate } from "../_components/shared";

export default function ResponsesPage() {
  const params = useParams();
  const quizId = params.id as string;
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [attempts, setAttempts] = useState<PublicAttempt[]>([]);

  // Subscribe to quiz document (for questions)
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
    const attemptsQuery = query(
      collection(db, "quizzes", quizId, "attempts"),
      orderBy("attemptAt", "desc")
    );
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

  return (
    <Card>
      <ScrollArea className="h-[600px]">
        <div className="p-4 space-y-4">
          {attempts.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              No responses yet
            </p>
          ) : (
            attempts.map((attempt, idx) => (
              <ResponseCard
                key={idx}
                attempt={attempt}
                questions={questions}
                formatDate={formatDate}
                quizId={quizId}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </Card>
  );
}
