"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { doc, getDoc, updateDoc } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useAuthStore, useQuizStore, useUIStore } from "@/lib/store";
import { QuestionEditorCard } from "@/components/quiz/question-editor-card";
import { ImportQuestionsDialog } from "@/components/quiz/import-questions-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { Loader2, Save, Plus, ArrowLeft, Sparkles, X } from "lucide-react";
import { Quiz } from "@/lib/types";

export default function QuizEditorPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const { user } = useAuthStore();
  const {
    currentQuiz,
    setCurrentQuiz,
    updateQuizMetadata,
    updateQuestion,
    deleteQuestion,
    addQuestion,
  } = useQuizStore();
  const { setShowImportDialog } = useUIStore();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newTag, setNewTag] = useState("");

  const quizId = params.id as string;
  const isNewQuiz = quizId === "new";

  // Fetch or create quiz
  useEffect(() => {
    const initQuiz = async () => {
      if (!user) return;
      
      // Redirect anonymous users
      if (user.isAnonymous) {
        router.push("/");
        return;
      }

      try {
        setLoading(true);

        if (isNewQuiz) {
          // Initialize a new empty quiz
          const newQuiz: Quiz = {
            userId: user.uid,
            status: "ready",
            title: "",
            description: "",
            genre: "",
            topics: [],
            questions: [],
            createdAt: new Date(),
          };
          setCurrentQuiz(newQuiz);
        } else {
          // Fetch existing quiz
          const quizDoc = await getDoc(doc(db, "quizzes", quizId));

          if (!quizDoc.exists()) {
            toast({
              title: "Quiz not found",
              description: "The quiz you're looking for doesn't exist.",
              variant: "destructive",
            });
            router.push("/");
            return;
          }

          const quizData = { id: quizDoc.id, ...quizDoc.data() } as Quiz;

          if (quizData.userId !== user.uid) {
            toast({
              title: "Access denied",
              description: "You don't have permission to edit this quiz.",
              variant: "destructive",
            });
            router.push("/");
            return;
          }

          setCurrentQuiz(quizData);
        }
      } catch (error) {
        console.error("Error initializing quiz:", error);
        toast({
          title: "Error",
          description: "Failed to load quiz. Please try again.",
          variant: "destructive",
        });
      } finally {
        setLoading(false);
      }
    };

    initQuiz();

    return () => {
      setCurrentQuiz(null);
    };
  }, [user, quizId, isNewQuiz, router, toast, setCurrentQuiz]);

  const handleSave = async () => {
    if (!currentQuiz || !user) return;

    try {
      setSaving(true);

      // Import Timestamp
      const { Timestamp } = await import("firebase/firestore");

      const quizData = {
        userId: user.uid,
        status: "ready" as const,
        title: currentQuiz.title || "Untitled Quiz",
        description: currentQuiz.description || "",
        passage: currentQuiz.passage || "",
        genre: currentQuiz.genre || "",
        topics: currentQuiz.topics || [],
        questions: currentQuiz.questions || [],
        updatedAt: Timestamp.now(),
      };

      if (isNewQuiz) {
        // Create new quiz
        const { addDoc, collection } = await import("firebase/firestore");
        const docRef = await addDoc(collection(db, "quizzes"), {
          ...quizData,
          createdAt: Timestamp.now(),
        });

        toast({
          title: "Quiz created",
          description: "Your quiz has been saved successfully.",
        });

        // Navigate to the new quiz's editor page
        router.replace(`/quiz/${docRef.id}/edit`);
      } else {
        // Update existing quiz
        await updateDoc(doc(db, "quizzes", quizId), quizData);

        toast({
          title: "Changes saved",
          description: "Your quiz has been updated successfully.",
        });
      }
    } catch (error) {
      console.error("Error saving quiz:", error);
      toast({
        title: "Error",
        description: "Failed to save quiz. Please try again.",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleAddTag = useCallback(() => {
    if (!newTag.trim() || !currentQuiz) return;
    const currentTopics = currentQuiz.topics || [];
    if (!currentTopics.includes(newTag.trim())) {
      updateQuizMetadata({ topics: [...currentTopics, newTag.trim()] });
    }
    setNewTag("");
  }, [newTag, currentQuiz, updateQuizMetadata]);

  const handleRemoveTag = useCallback(
    (tagToRemove: string) => {
      if (!currentQuiz) return;
      const currentTopics = currentQuiz.topics || [];
      updateQuizMetadata({
        topics: currentTopics.filter((t) => t !== tagToRemove),
      });
    },
    [currentQuiz, updateQuizMetadata]
  );

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-900">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading editor...</p>
        </div>
      </div>
    );
  }

  if (!currentQuiz) {
    return null;
  }

  return (
    <>
      {/* Sticky Header */}
      <div className="fixed top-0 left-0 right-0 z-50 bg-white dark:bg-zinc-800 border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  if (isNewQuiz) {
                    router.push("/");
                  } else {
                    router.push(`/quiz/${quizId}`);
                  }
                }}
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div>
                <h1 className="text-lg font-bold">
                  {isNewQuiz ? "Create New Quiz" : "Edit Quiz"}
                </h1>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => setShowImportDialog(true)}
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Import
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Save className="w-4 h-4 mr-2" />
                )}
                {isNewQuiz ? "Create" : "Save"}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Content with top padding for fixed header */}
      <div className="pt-20 space-y-6">

      {/* Main Content */}
      <div className="space-y-6">
        {/* Quiz Metadata Card */}
        <div className="bg-white dark:bg-zinc-800 rounded-xl border p-6 space-y-4">
          {/* Title */}
          <Input
            value={currentQuiz.title || ""}
            onChange={(e) => updateQuizMetadata({ title: e.target.value })}
            placeholder="Untitled Quiz"
            className="text-2xl font-bold border-0 border-b rounded-none px-0 focus-visible:ring-0 focus-visible:border-primary"
          />

          {/* Description */}
          <Textarea
            value={currentQuiz.description || ""}
            onChange={(e) =>
              updateQuizMetadata({ description: e.target.value })
            }
            placeholder="Add a description (optional)"
            className="resize-none border-0 px-0 focus-visible:ring-0 text-muted-foreground"
            rows={2}
          />

          {/* Passage/Document */}
          <div className="pt-2">
            <Label className="text-sm text-muted-foreground mb-2 block">
              Passage
            </Label>
            <Textarea
              value={currentQuiz.passage || ""}
              onChange={(e) => updateQuizMetadata({ passage: e.target.value })}
              placeholder="Paste the original passage or document text here (optional)..."
              className="resize-none min-h-[120px]"
              rows={5}
            />
          </div>

          {/* Tags */}
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              {(currentQuiz.topics || []).map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-sm bg-primary/10 text-primary"
                >
                  {tag}
                  <button
                    onClick={() => handleRemoveTag(tag)}
                    className="hover:bg-primary/20 rounded-full p-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              <div className="flex items-center gap-1">
                <Input
                  value={newTag}
                  onChange={(e) => setNewTag(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddTag();
                    }
                  }}
                  placeholder="Add tag..."
                  className="h-8 w-28 text-sm"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleAddTag}
                  disabled={!newTag.trim()}
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Questions List */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
              Questions ({currentQuiz.questions?.length || 0})
            </h2>
          </div>

          {currentQuiz.questions && currentQuiz.questions.length > 0 ? (
            <div className="space-y-4">
              {currentQuiz.questions.map((question, index) => (
                <QuestionEditorCard
                  key={question.id}
                  question={question}
                  index={index}
                  onUpdate={updateQuestion}
                  onDelete={deleteQuestion}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-12 bg-white dark:bg-zinc-800 rounded-xl border border-dashed">
              <p className="text-muted-foreground mb-4">
                No questions yet. Add your first question!
              </p>
            </div>
          )}

          {/* Add Question Button */}
          <Button
            onClick={addQuestion}
            variant="outline"
            className="w-full h-16 border-2 border-dashed hover:border-primary hover:bg-primary/5"
          >
            <Plus className="w-5 h-5 mr-2" />
            Add Question
          </Button>
        </div>
      </div>

      {/* Import Dialog */}
      <ImportQuestionsDialog />
      </div>
    </>
  );
}
