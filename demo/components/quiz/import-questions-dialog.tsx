"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { ref, uploadBytes, getDownloadURL } from "firebase/storage";
import { addDoc, collection, onSnapshot, Timestamp } from "firebase/firestore";
import { db, storage } from "@/lib/firebase";
import { useAuthStore, useQuizStore, useUIStore } from "@/lib/store";
import { AVAILABLE_MODELS, Question } from "@/lib/types";
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
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Upload,
  Loader2,
  CheckCircle,
  XCircle,
  Settings,
  FileText,
  Images,
  X,
  Sparkles,
} from "lucide-react";

type ImportStep = "config" | "uploading" | "processing" | "done" | "error";
type InputType = "images" | "pdf";

const MAX_IMAGES = 10;

export function ImportQuestionsDialog() {
  const { user } = useAuthStore();
  const { currentQuiz, appendQuestions, updateQuizMetadata } = useQuizStore();
  const { showImportDialog, setShowImportDialog } = useUIStore();

  const [step, setStep] = useState<ImportStep>("config");
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const [inputType, setInputType] = useState<InputType>("images");
  const [ocrModel, setOcrModel] = useState("google/gemini-2.5-flash");
  const [questionModel, setQuestionModel] = useState("google/gemini-2.5-flash");
  const [targetQuestionCount, setTargetQuestionCount] = useState(5);
  const [extractPassage, setExtractPassage] = useState(true);

  const resetState = () => {
    setStep("config");
    setProgress(0);
    setStatusMessage("");
    setError(null);
    setSelectedFiles([]);
    setPreviewUrls([]);
  };

  const handleClose = () => {
    if (step !== "uploading" && step !== "processing") {
      resetState();
      setShowImportDialog(false);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviewUrls((prev) => prev.filter((_, i) => i !== index));
  };

  const startImport = useCallback(async () => {
    if (!user || selectedFiles.length === 0) return;

    if (inputType === "images" && selectedFiles.length > MAX_IMAGES) {
      setError(`Maximum ${MAX_IMAGES} images allowed.`);
      return;
    }

    try {
      setError(null);
      setStep("uploading");
      setProgress(10);
      setStatusMessage("Creating import job...");

      // Create a temporary quiz document for AI processing
      const importJobRef = await addDoc(collection(db, "quizzes"), {
        userId: user.uid,
        status: "uploading",
        ocrModel,
        questionModel,
        targetQuestionCount,
        inputType,
        createdAt: Timestamp.now(),
        // Mark this as an import job (not a standalone quiz)
        isImportJob: true,
        parentQuizId: currentQuiz?.id || null,
      });

      setProgress(20);
      setStatusMessage("Uploading files...");

      if (inputType === "pdf") {
        const file = selectedFiles[0];
        const storageRef = ref(
          storage,
          `imports/${user.uid}/${importJobRef.id}/document.pdf`
        );
        await uploadBytes(storageRef, file);
        const pdfUrl = await getDownloadURL(storageRef);

        // Trigger OCR processing
        await import("firebase/firestore").then(({ updateDoc, doc }) =>
          updateDoc(doc(db, "quizzes", importJobRef.id), {
            pdfUrl,
            status: "processing_ocr",
          })
        );
      } else {
        const imageUrls: string[] = [];
        const totalFiles = selectedFiles.length;

        for (let i = 0; i < totalFiles; i++) {
          const file = selectedFiles[i];
          const storageRef = ref(
            storage,
            `imports/${user.uid}/${importJobRef.id}/image_${i + 1}`
          );
          await uploadBytes(storageRef, file);
          const imageUrl = await getDownloadURL(storageRef);
          imageUrls.push(imageUrl);
          setProgress(20 + Math.round(((i + 1) / totalFiles) * 30));
        }

        // Trigger OCR processing
        await import("firebase/firestore").then(({ updateDoc, doc }) =>
          updateDoc(doc(db, "quizzes", importJobRef.id), {
            imageUrls,
            status: "processing_ocr",
          })
        );
      }

      setStep("processing");
      setProgress(50);
      setStatusMessage("Processing with AI...");

      // Listen for status updates
      const unsubscribe = onSnapshot(
        (await import("firebase/firestore")).doc(
          db,
          "quizzes",
          importJobRef.id
        ),
        async (snapshot) => {
          const data = snapshot.data();
          if (!data) return;

          if (data.status === "processing_ocr") {
            setProgress(60);
            setStatusMessage("Extracting text from documents...");
          } else if (data.status === "generating_quiz") {
            setProgress(80);
            setStatusMessage("Generating questions with AI...");
          } else if (data.status === "ready" && data.questions) {
            setProgress(100);
            setStatusMessage("Import complete!");

            // Append the generated questions to the current quiz
            const importedQuestions: Question[] = data.questions;
            appendQuestions(importedQuestions);

            // Update metadata if current fields are empty
            const updates: Partial<typeof currentQuiz> = {};
            if (!currentQuiz?.title && data.title) {
              updates.title = data.title;
            }
            if (!currentQuiz?.description && data.description) {
              updates.description = data.description;
            }
            if (!currentQuiz?.genre && data.genre) {
              updates.genre = data.genre;
            }
            if (
              (!currentQuiz?.topics || currentQuiz.topics.length === 0) &&
              data.topics
            ) {
              updates.topics = data.topics;
            }
            // Extract passage from OCR text if checkbox is checked
            if (extractPassage && data.ocrText && !currentQuiz?.passage) {
              updates.passage = data.ocrText;
            }

            if (Object.keys(updates).length > 0) {
              updateQuizMetadata(updates);
            }

            // Clean up the import job document
            await import("firebase/firestore").then(({ deleteDoc, doc }) =>
              deleteDoc(doc(db, "quizzes", importJobRef.id))
            );

            unsubscribe();
            setStep("done");

            // Auto close after success
            setTimeout(() => {
              resetState();
              setShowImportDialog(false);
            }, 1500);
          } else if (data.status === "error") {
            unsubscribe();
            setError(data.errorMessage || "Import failed");
            setStep("error");

            // Clean up on error
            await import("firebase/firestore").then(({ deleteDoc, doc }) =>
              deleteDoc(doc(db, "quizzes", importJobRef.id))
            );
          }
        }
      );
    } catch (err) {
      console.error("Import error:", err);
      setError(err instanceof Error ? err.message : "An error occurred");
      setStep("error");
    }
  }, [
    user,
    selectedFiles,
    inputType,
    ocrModel,
    questionModel,
    targetQuestionCount,
    extractPassage,
    currentQuiz,
    appendQuestions,
    updateQuizMetadata,
    setShowImportDialog,
  ]);

  const onDropImages = useCallback(
    (acceptedFiles: File[]) => {
      const totalFiles = selectedFiles.length + acceptedFiles.length;
      if (totalFiles > MAX_IMAGES) {
        setError(`Maximum ${MAX_IMAGES} images allowed.`);
        setTimeout(() => setError(null), 3000);
        return;
      }
      setError(null);
      setSelectedFiles((prev) => [...prev, ...acceptedFiles]);
      setPreviewUrls((prev) => [
        ...prev,
        ...acceptedFiles.map((f) => URL.createObjectURL(f)),
      ]);
    },
    [selectedFiles.length]
  );

  const onDropPdf = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (file) {
      setSelectedFiles([file]);
      setPreviewUrls([URL.createObjectURL(file)]);
    }
  }, []);

  const {
    getRootProps: getImagesRootProps,
    getInputProps: getImagesInputProps,
    isDragActive: isImagesDragActive,
  } = useDropzone({
    onDrop: onDropImages,
    accept: { "image/*": [".png", ".jpg", ".jpeg", ".webp"] },
    disabled: step !== "config",
  });

  const {
    getRootProps: getPdfRootProps,
    getInputProps: getPdfInputProps,
    isDragActive: isPdfDragActive,
  } = useDropzone({
    onDrop: onDropPdf,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    disabled: step !== "config",
  });

  return (
    <Dialog open={showImportDialog} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            Import Questions with AI
          </DialogTitle>
        </DialogHeader>

        {step === "config" ? (
          <div className="space-y-6">
            {/* Model Configuration */}
            <div className="space-y-4 p-4 bg-zinc-50 dark:bg-zinc-900/50 rounded-lg border">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Settings className="w-4 h-4" />
                <span>AI Configuration</span>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="ocr-model" className="text-xs">
                    OCR Model
                  </Label>
                  <Select value={ocrModel} onValueChange={setOcrModel}>
                    <SelectTrigger id="ocr-model" className="h-9 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectLabel>Open Source</SelectLabel>
                        {AVAILABLE_MODELS.filter(
                          (m) => m.category === "open-source"
                        ).map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            {model.displayName}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                      <SelectGroup>
                        <SelectLabel>Proprietary</SelectLabel>
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
                  <Label htmlFor="question-model" className="text-xs">
                    Question Model
                  </Label>
                  <Select
                    value={questionModel}
                    onValueChange={setQuestionModel}
                  >
                    <SelectTrigger id="question-model" className="h-9 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectLabel>Open Source</SelectLabel>
                        {AVAILABLE_MODELS.filter(
                          (m) => m.category === "open-source"
                        ).map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            {model.displayName}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                      <SelectGroup>
                        <SelectLabel>Proprietary</SelectLabel>
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

              <div className="space-y-2">
                <Label htmlFor="question-count" className="text-xs">
                  Number of questions to generate
                </Label>
                <Input
                  id="question-count"
                  type="number"
                  min={1}
                  max={20}
                  value={targetQuestionCount}
                  onChange={(e) =>
                    setTargetQuestionCount(
                      Math.max(1, parseInt(e.target.value) || 5)
                    )
                  }
                  className="h-9 w-24"
                />
              </div>

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="extract-passage"
                  checked={extractPassage}
                  onChange={(e) => setExtractPassage(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                />
                <Label
                  htmlFor="extract-passage"
                  className="text-xs cursor-pointer"
                >
                  Extract passage from file
                </Label>
              </div>
            </div>

            {/* File Upload */}
            <Tabs
              value={inputType}
              onValueChange={(v) => {
                setInputType(v as InputType);
                setSelectedFiles([]);
                setPreviewUrls([]);
              }}
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="images">
                  <Images className="w-4 h-4 mr-2" />
                  Images
                </TabsTrigger>
                <TabsTrigger value="pdf">
                  <FileText className="w-4 h-4 mr-2" />
                  PDF
                </TabsTrigger>
              </TabsList>

              <TabsContent value="images" className="mt-4 space-y-4">
                <div
                  {...getImagesRootProps()}
                  className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                    isImagesDragActive
                      ? "border-primary bg-primary/5"
                      : "border-zinc-200 dark:border-zinc-800 hover:border-primary/50"
                  }`}
                >
                  <input {...getImagesInputProps()} />
                  <Upload className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
                  <p className="text-sm font-medium">Drop images here</p>
                  <p className="text-xs text-muted-foreground">
                    or click to select (max {MAX_IMAGES})
                  </p>
                </div>

                {previewUrls.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">
                        {selectedFiles.length} image(s) selected
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedFiles([]);
                          setPreviewUrls([]);
                        }}
                      >
                        Clear
                      </Button>
                    </div>
                    <div className="grid grid-cols-5 gap-2">
                      {previewUrls.map((url, idx) => (
                        <div
                          key={idx}
                          className="relative aspect-square rounded-lg overflow-hidden bg-zinc-100 dark:bg-zinc-800 group"
                        >
                          <img
                            src={url}
                            alt={`Preview ${idx + 1}`}
                            className="w-full h-full object-cover"
                          />
                          <button
                            onClick={() => removeFile(idx)}
                            className="absolute top-1 right-1 p-0.5 rounded-full bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="pdf" className="mt-4 space-y-4">
                <div
                  {...getPdfRootProps()}
                  className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                    isPdfDragActive
                      ? "border-primary bg-primary/5"
                      : "border-zinc-200 dark:border-zinc-800 hover:border-primary/50"
                  }`}
                >
                  <input {...getPdfInputProps()} />
                  <FileText className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
                  <p className="text-sm font-medium">Drop PDF here</p>
                  <p className="text-xs text-muted-foreground">
                    or click to select
                  </p>
                </div>

                {selectedFiles.length > 0 && inputType === "pdf" && (
                  <div className="flex items-center gap-3 p-3 bg-zinc-50 dark:bg-zinc-900/50 rounded-lg border">
                    <FileText className="w-6 h-6 text-red-500" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {selectedFiles[0].name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {(selectedFiles[0].size / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        setSelectedFiles([]);
                        setPreviewUrls([]);
                      }}
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                )}
              </TabsContent>
            </Tabs>

            {error && (
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            <Button
              onClick={startImport}
              disabled={selectedFiles.length === 0}
              className="w-full"
            >
              <Sparkles className="w-4 h-4 mr-2" />
              Generate {targetQuestionCount} Questions
            </Button>
          </div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Progress Display */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                {step === "done" ? (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                ) : step === "error" ? (
                  <XCircle className="w-5 h-5 text-red-500" />
                ) : (
                  <Loader2 className="w-5 h-5 text-primary animate-spin" />
                )}
                <span
                  className={`font-medium ${
                    step === "done"
                      ? "text-green-600"
                      : step === "error"
                      ? "text-red-600"
                      : ""
                  }`}
                >
                  {step === "done"
                    ? "Questions imported successfully!"
                    : step === "error"
                    ? "Import failed"
                    : statusMessage}
                </span>
              </div>
              {step !== "done" && step !== "error" && (
                <Progress value={progress} className="h-2" />
              )}
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

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
