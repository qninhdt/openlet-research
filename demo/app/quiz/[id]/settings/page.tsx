"use client";

import { useParams, useRouter } from "next/navigation";
import { doc, onSnapshot, updateDoc } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useEffect, useState } from "react";
import { Quiz, PublicLevel } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { Timestamp } from "firebase/firestore";
import { Globe, Lock, Copy, Check, Users, Timer, Eye, Loader2 } from "lucide-react";

const PUBLIC_LEVEL_OPTIONS = [
  { level: 0 as PublicLevel, label: "Show nothing", description: "Only 'Submitted' message" },
  { level: 1 as PublicLevel, label: "Score only", description: "Total score (8/10)" },
  { level: 2 as PublicLevel, label: "Correct/Wrong", description: "Which questions were right" },
  { level: 3 as PublicLevel, label: "Show answers", description: "Reveal correct answers" },
  { level: 4 as PublicLevel, label: "Full feedback", description: "Everything + explanations" },
];

export default function SettingsPage() {
  const params = useParams();
  const router = useRouter();
  const { toast } = useToast();
  const quizId = params.id as string;
  
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const [isPublished, setIsPublished] = useState(false);
  const [allowAnonymous, setAllowAnonymous] = useState(true);
  const [allowRedo, setAllowRedo] = useState(false);
  const [publicLevel, setPublicLevel] = useState<PublicLevel>(4);
  const [timerEnabled, setTimerEnabled] = useState(false);
  const [timerDuration, setTimerDuration] = useState(30);
  const [timerAutoSubmit, setTimerAutoSubmit] = useState(true);
  const [timerWarning, setTimerWarning] = useState(5);

  useEffect(() => {
    if (!quizId) return;
    const unsubscribe = onSnapshot(doc(db, "quizzes", quizId), (doc) => {
      if (doc.exists()) {
        const quizData = { id: doc.id, ...doc.data() } as Quiz;
        setQuiz(quizData);
        setIsPublished(quizData.isPublished ?? false);
        setAllowAnonymous(quizData.allowAnonymous ?? true);
        setAllowRedo(quizData.allowRedo ?? false);
        setPublicLevel(quizData.publicLevel ?? 4);
        setTimerEnabled(quizData.timerEnabled ?? false);
        setTimerDuration(quizData.timerDurationMinutes ?? 30);
        setTimerAutoSubmit(quizData.timerAutoSubmit ?? true);
        setTimerWarning(quizData.timerWarningMinutes ?? 5);
      }
    });
    return () => unsubscribe();
  }, [quizId]);

  const quizUrl = typeof window !== "undefined" ? `${window.location.origin}/play/${quizId}` : "";

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(quizUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ title: "Failed to copy", variant: "destructive" });
    }
  };

  const handleTogglePublish = async () => {
    const newPublishState = !isPublished;
    setIsPublished(newPublishState);
    
    if (!quizId) return;
    try {
      await updateDoc(doc(db, "quizzes", quizId), {
        isPublished: newPublishState,
        updatedAt: Timestamp.now(),
      });
      toast({
        title: newPublishState ? "Quiz published!" : "Quiz unpublished",
        description: newPublishState ? "Anyone with the link can now take this quiz" : "Quiz is now private",
      });
    } catch {
      setIsPublished(!newPublishState);
      toast({ title: "Error", variant: "destructive" });
    }
  };

  const handleSaveSettings = async () => {
    if (!quizId) return;

    try {
      setSaving(true);
      await updateDoc(doc(db, "quizzes", quizId), {
        isPublished,
        allowAnonymous,
        allowRedo,
        publicLevel,
        timerEnabled,
        timerDurationMinutes: timerDuration,
        timerAutoSubmit,
        timerWarningMinutes: timerWarning,
        updatedAt: Timestamp.now(),
      });

      toast({
        title: "Settings saved",
        description: isPublished ? "Quiz is now published!" : "Settings updated successfully",
      });
    } catch (err) {
      console.error("Error saving:", err);
      toast({ title: "Error saving settings", variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (!quiz) return null;

  return (
    <div className="space-y-6">
      {/* Publish Card */}
      <Card className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <h3 className="font-semibold flex items-center gap-2">
              {isPublished ? <Globe className="w-5 h-5 text-green-600" /> : <Lock className="w-5 h-5 text-zinc-400" />}
              {isPublished ? "Quiz is Published" : "Quiz is Private"}
            </h3>
            <p className="text-sm text-muted-foreground">
              {isPublished ? "Anyone with the link can take this quiz" : "Only you can see this quiz"}
            </p>
          </div>
          <Button variant={isPublished ? "outline" : "default"} onClick={handleTogglePublish}>
            {isPublished ? "Unpublish" : "Publish"}
          </Button>
        </div>

        {isPublished && (
          <div className="mt-4 space-y-2">
            <Label>Share Link</Label>
            <div className="flex gap-2">
              <div className="flex-1 px-3 py-2 text-sm bg-zinc-100 dark:bg-zinc-800 rounded-md truncate font-mono">
                {quizUrl}
              </div>
              <Button variant="outline" size="icon" onClick={handleCopyLink}>
                {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Visibility Settings */}
      <Card className="p-6 space-y-4">
        <h3 className="font-semibold flex items-center gap-2">
          <Eye className="w-5 h-5" />
          Results Visibility
        </h3>
        <p className="text-sm text-muted-foreground">What students see after submitting</p>
        <div className="grid gap-2">
          {PUBLIC_LEVEL_OPTIONS.map((option) => (
            <div
              key={option.level}
              onClick={() => setPublicLevel(option.level)}
              className={`flex items-center gap-3 p-3 rounded-lg border-2 cursor-pointer transition-colors ${
                publicLevel === option.level
                  ? "border-primary bg-primary/5"
                  : "border-zinc-200 dark:border-zinc-700 hover:border-zinc-300"
              }`}
            >
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                publicLevel === option.level ? "bg-primary text-primary-foreground" : "bg-zinc-200 dark:bg-zinc-700"
              }`}>
                {option.level}
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium">{option.label}</p>
                <p className="text-xs text-muted-foreground">{option.description}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Access Settings */}
      <Card className="p-6 space-y-4">
        <h3 className="font-semibold flex items-center gap-2">
          <Users className="w-5 h-5" />
          Access Settings
        </h3>
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label>Allow anonymous participants</Label>
            <p className="text-xs text-muted-foreground">Guests can take quiz with just a nickname</p>
          </div>
          <Checkbox checked={allowAnonymous} onCheckedChange={(c) => setAllowAnonymous(!!c)} />
        </div>
        {!allowAnonymous && (
          <>
            <Separator />
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Allow retake quiz</Label>
                <p className="text-xs text-muted-foreground">
                  Authenticated users can retake the quiz
                </p>
              </div>
              <Checkbox checked={allowRedo} onCheckedChange={(c) => setAllowRedo(!!c)} />
            </div>
          </>
        )}
      </Card>

      {/* Timer Settings */}
      <Card className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold flex items-center gap-2">
            <Timer className="w-5 h-5" />
            Timer Settings
          </h3>
          <Checkbox checked={timerEnabled} onCheckedChange={(c) => setTimerEnabled(!!c)} />
        </div>

        {timerEnabled && (
          <div className="space-y-4 pt-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Duration (minutes)</Label>
                <Input
                  type="number"
                  value={timerDuration}
                  onChange={(e) => setTimerDuration(parseInt(e.target.value) || 30)}
                  min={1}
                  max={180}
                />
              </div>
              <div className="space-y-2">
                <Label>Warning (minutes before)</Label>
                <Input
                  type="number"
                  value={timerWarning}
                  onChange={(e) => setTimerWarning(parseInt(e.target.value) || 5)}
                  min={1}
                  max={timerDuration - 1}
                />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Auto-submit when time runs out</Label>
                <p className="text-xs text-muted-foreground">Automatically submit answers when timer ends</p>
              </div>
              <Checkbox checked={timerAutoSubmit} onCheckedChange={(c) => setTimerAutoSubmit(!!c)} />
            </div>
          </div>
        )}
      </Card>

      <Button onClick={handleSaveSettings} disabled={saving} className="w-full">
        {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
        Save Settings
      </Button>
    </div>
  );
}
