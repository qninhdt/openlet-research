"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import {
  addDoc,
  collection,
  updateDoc,
  doc,
  Timestamp,
} from "firebase/firestore";
import { ref, uploadBytes, getDownloadURL } from "firebase/storage";
import { db, storage } from "@/lib/firebase";
import { useAuthStore } from "@/lib/store";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Upload,
  Camera,
  Loader2,
  CheckCircle,
  XCircle,
  Settings,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { AVAILABLE_MODELS } from "@/lib/types";

interface CreateQuizDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type ProcessingStep = "idle" | "uploading" | "done" | "error";

export function CreateQuizDialog({
  open,
  onOpenChange,
}: CreateQuizDialogProps) {
  const { user } = useAuthStore();
  const [step, setStep] = useState<ProcessingStep>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [ocrModel, setOcrModel] = useState("qwen/qwen3-vl-8b-instruct");
  const [questionModel, setQuestionModel] = useState("google/gemini-2.5-flash");

  const resetState = () => {
    setStep("idle");
    setProgress(0);
    setError(null);
    setPreviewUrl(null);
  };

  const handleClose = () => {
    if (step !== "uploading") {
      resetState();
      onOpenChange(false);
    }
  };

  const processImage = useCallback(
    async (file: File) => {
      if (!user) return;

      try {
        setError(null);
        setStep("uploading");
        setProgress(10);

        // Create quiz document with uploading status and model selections
        const quizRef = await addDoc(collection(db, "quizzes"), {
          userId: user.uid,
          status: "uploading",
          ocrModel,
          questionModel,
          createdAt: Timestamp.now(),
        });

        setProgress(30);

        // Upload image to Firebase Storage
        const storageRef = ref(
          storage,
          `quizzes/${user.uid}/${quizRef.id}/image`
        );
        await uploadBytes(storageRef, file);
        const imageUrl = await getDownloadURL(storageRef);

        setProgress(50);

        // Update quiz with image URL and trigger OCR processing
        // Firebase Function will automatically process OCR when status changes to "processing_ocr"
        await updateDoc(doc(db, "quizzes", quizRef.id), {
          imageUrl,
          status: "processing_ocr",
        });

        // Now we just wait for Firebase Functions to complete the processing
        // The UI will show progress through Firestore real-time updates
        setStep("done");
        setProgress(100);

        // Auto close after success
        setTimeout(() => {
          if (step !== "uploading") {
            resetState();
            onOpenChange(false);
          }
        }, 1500);
      } catch (err) {
        console.error("Processing error:", err);
        setError(err instanceof Error ? err.message : "An error occurred");
        setStep("error");
      }
    },
    [user, ocrModel, questionModel, step, onOpenChange]
  );

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (file) {
        setPreviewUrl(URL.createObjectURL(file));
        await processImage(file);
      }
    },
    [processImage]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/*": [".png", ".jpg", ".jpeg", ".webp"],
    },
    maxFiles: 1,
    disabled: step !== "idle",
  });

  const handleCameraCapture = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];
    if (file) {
      setPreviewUrl(URL.createObjectURL(file));
      await processImage(file);
    }
  };

  const getStepInfo = () => {
    switch (step) {
      case "uploading":
        return { label: "Uploading image...", icon: Loader2 };
      case "done":
        return { label: "Complete!", icon: CheckCircle };
      case "error":
        return { label: "An error occurred", icon: XCircle };
      default:
        return null;
    }
  };

  const stepInfo = getStepInfo();

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create New Quiz</DialogTitle>
        </DialogHeader>

        {step === "idle" ? (
          <div className="space-y-6">
            {/* Model Selection Section */}
            <div className="space-y-4 p-4 bg-zinc-50 dark:bg-zinc-900/50 rounded-lg border">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Settings className="w-4 h-4" />
                <span>Model Configuration</span>
              </div>

              <div className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="ocr-model" className="text-sm font-medium">
                    OCR Model (Text Recognition)
                  </Label>
                  <Select value={ocrModel} onValueChange={setOcrModel}>
                    <SelectTrigger id="ocr-model">
                      <SelectValue placeholder="Select OCR model" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectLabel>Open Source sLLMs</SelectLabel>
                        {AVAILABLE_MODELS.filter(
                          (m) => m.category === "open-source"
                        ).map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            {model.displayName}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                      <SelectGroup>
                        <SelectLabel>Proprietary LLMs</SelectLabel>
                        {AVAILABLE_MODELS.filter(
                          (m) => m.category === "proprietary"
                        ).map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            {model.displayName}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label
                    htmlFor="question-model"
                    className="text-sm font-medium"
                  >
                    Question Generation Model
                  </Label>
                  <Select
                    value={questionModel}
                    onValueChange={setQuestionModel}
                  >
                    <SelectTrigger id="question-model">
                      <SelectValue placeholder="Select question model" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectLabel>Open Source sLLMs</SelectLabel>
                        {AVAILABLE_MODELS.filter(
                          (m) => m.category === "open-source"
                        ).map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            {model.displayName}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                      <SelectGroup>
                        <SelectLabel>Proprietary LLMs</SelectLabel>
                        {AVAILABLE_MODELS.filter(
                          (m) => m.category === "proprietary"
                        ).map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            {model.displayName}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            {/* Upload Section */}
            <Tabs defaultValue="upload" className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="upload">
                  <Upload className="w-4 h-4 mr-2" />
                  Upload
                </TabsTrigger>
                <TabsTrigger value="camera">
                  <Camera className="w-4 h-4 mr-2" />
                  Camera
                </TabsTrigger>
              </TabsList>

              <TabsContent value="upload" className="mt-4">
                <div
                  {...getRootProps()}
                  className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                    isDragActive
                      ? "border-primary bg-primary/5"
                      : "border-zinc-200 dark:border-zinc-800 hover:border-primary/50"
                  }`}
                >
                  <input {...getInputProps()} />
                  <Upload className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                  {isDragActive ? (
                    <p className="text-primary font-medium">
                      Drop image here...
                    </p>
                  ) : (
                    <>
                      <p className="font-medium text-zinc-900 dark:text-white mb-1">
                        Drag and drop image here
                      </p>
                      <p className="text-sm text-muted-foreground">
                        or click to select file (PNG, JPG, WEBP)
                      </p>
                    </>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="camera" className="mt-4">
                <label className="flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-8 cursor-pointer hover:border-primary/50 transition-colors">
                  <Camera className="w-12 h-12 text-muted-foreground mb-4" />
                  <p className="font-medium text-zinc-900 dark:text-white mb-1">
                    Capture document photo
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Click to open camera
                  </p>
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="hidden"
                    onChange={handleCameraCapture}
                  />
                </label>
              </TabsContent>
            </Tabs>
          </div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Preview Image */}
            {previewUrl && (
              <div className="relative aspect-4/3 rounded-lg overflow-hidden bg-zinc-100 dark:bg-zinc-800">
                <img
                  src={previewUrl}
                  alt="Preview"
                  className="w-full h-full object-contain"
                />
                {step !== "done" && step !== "error" && (
                  <div className="absolute inset-0 bg-black/30 flex items-center justify-center">
                    <Loader2 className="w-8 h-8 text-white animate-spin" />
                  </div>
                )}
              </div>
            )}

            {/* Progress */}
            {stepInfo && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <stepInfo.icon
                    className={`w-5 h-5 ${
                      step === "done"
                        ? "text-green-500"
                        : step === "error"
                        ? "text-red-500"
                        : "text-primary animate-spin"
                    }`}
                  />
                  <span
                    className={`font-medium ${
                      step === "done"
                        ? "text-green-600"
                        : step === "error"
                        ? "text-red-600"
                        : ""
                    }`}
                  >
                    {stepInfo.label}
                  </span>
                </div>
                {step !== "done" && step !== "error" && (
                  <Progress value={progress} className="h-2" />
                )}
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* Retry Button */}
            {step === "error" && (
              <Button onClick={resetState} variant="outline" className="w-full">
                Try Again
              </Button>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
