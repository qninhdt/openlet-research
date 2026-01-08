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
  Loader2,
  CheckCircle,
  XCircle,
  Settings,
  FileText,
  Images,
  X,
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
import { AVAILABLE_MODELS, QuizInputType } from "@/lib/types";

interface CreateQuizDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type ProcessingStep = "idle" | "uploading" | "done" | "error";

const MAX_IMAGES = 10;
const MAX_PDF_PAGES = 10;

export function CreateQuizDialog({
  open,
  onOpenChange,
}: CreateQuizDialogProps) {
  const { user } = useAuthStore();
  const [step, setStep] = useState<ProcessingStep>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const [inputType, setInputType] = useState<QuizInputType>("images");
  const [ocrModel, setOcrModel] = useState("google/gemini-2.5-flash");
  const [questionModel, setQuestionModel] = useState("google/gemini-2.5-flash");

  const resetState = () => {
    setStep("idle");
    setProgress(0);
    setError(null);
    setSelectedFiles([]);
    setPreviewUrls([]);
  };

  const handleClose = () => {
    if (step !== "uploading") {
      resetState();
      onOpenChange(false);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviewUrls((prev) => prev.filter((_, i) => i !== index));
  };

  const processFiles = useCallback(async () => {
    if (!user || selectedFiles.length === 0) return;

    // Validate image count
    if (inputType === "images" && selectedFiles.length > MAX_IMAGES) {
      setError(
        `Maximum ${MAX_IMAGES} images allowed. Please remove ${
          selectedFiles.length - MAX_IMAGES
        } image${selectedFiles.length - MAX_IMAGES > 1 ? "s" : ""}.`
      );
      return;
    }

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
        inputType,
        createdAt: Timestamp.now(),
      });

      setProgress(20);

      if (inputType === "pdf") {
        // Upload single PDF
        const file = selectedFiles[0];
        const storageRef = ref(
          storage,
          `quizzes/${user.uid}/${quizRef.id}/document.pdf`
        );
        await uploadBytes(storageRef, file);
        const pdfUrl = await getDownloadURL(storageRef);

        setProgress(60);

        // Update quiz with PDF URL and trigger OCR processing
        await updateDoc(doc(db, "quizzes", quizRef.id), {
          pdfUrl,
          status: "processing_ocr",
        });
      } else {
        // Upload multiple images
        const imageUrls: string[] = [];
        const totalFiles = selectedFiles.length;

        for (let i = 0; i < totalFiles; i++) {
          const file = selectedFiles[i];
          const storageRef = ref(
            storage,
            `quizzes/${user.uid}/${quizRef.id}/image_${i + 1}`
          );
          await uploadBytes(storageRef, file);
          const imageUrl = await getDownloadURL(storageRef);
          imageUrls.push(imageUrl);

          // Update progress based on upload
          setProgress(20 + Math.round(((i + 1) / totalFiles) * 40));
        }

        // Update quiz with image URLs and trigger OCR processing
        await updateDoc(doc(db, "quizzes", quizRef.id), {
          imageUrls,
          status: "processing_ocr",
        });
      }

      setStep("done");
      setProgress(100);

      // Auto close after success
      setTimeout(() => {
        resetState();
        onOpenChange(false);
      }, 1500);
    } catch (err) {
      console.error("Processing error:", err);
      setError(err instanceof Error ? err.message : "An error occurred");
      setStep("error");
    }
  }, [user, selectedFiles, inputType, ocrModel, questionModel, onOpenChange]);

  const onDropImages = useCallback(
    (acceptedFiles: File[]) => {
      const totalFiles = selectedFiles.length + acceptedFiles.length;

      if (totalFiles > MAX_IMAGES) {
        setError(
          `Maximum ${MAX_IMAGES} images allowed. You selected ${
            acceptedFiles.length
          } image${acceptedFiles.length > 1 ? "s" : ""}, but you already have ${
            selectedFiles.length
          } image${selectedFiles.length > 1 ? "s" : ""} selected.`
        );
        setTimeout(() => setError(null), 5000);
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
    accept: {
      "image/*": [".png", ".jpg", ".jpeg", ".webp"],
    },
    disabled: step !== "idle",
  });

  const {
    getRootProps: getPdfRootProps,
    getInputProps: getPdfInputProps,
    isDragActive: isPdfDragActive,
  } = useDropzone({
    onDrop: onDropPdf,
    accept: {
      "application/pdf": [".pdf"],
    },
    maxFiles: 1,
    disabled: step !== "idle",
  });

  const getStepInfo = () => {
    switch (step) {
      case "uploading":
        return {
          label:
            inputType === "pdf" ? "Uploading PDF..." : "Uploading images...",
          icon: Loader2,
        };
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
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
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
            <Tabs
              value={inputType}
              onValueChange={(v) => {
                setInputType(v as QuizInputType);
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

              {/* Multiple Images Upload */}
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
                  <Upload className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                  {isImagesDragActive ? (
                    <p className="text-primary font-medium">
                      Drop images here...
                    </p>
                  ) : (
                    <>
                      <p className="font-medium text-zinc-900 dark:text-white mb-1">
                        Drag and drop images here
                      </p>
                      <p className="text-sm text-muted-foreground">
                        or click to select
                        <br />
                        <span className="text-xs">
                          On mobile, you can choose camera from the file picker
                        </span>
                      </p>
                    </>
                  )}
                </div>

                {/* Image Previews */}
                {previewUrls.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">
                        Selected: {selectedFiles.length} image
                        {selectedFiles.length > 1 ? "s" : ""}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedFiles([]);
                          setPreviewUrls([]);
                        }}
                      >
                        Clear all
                      </Button>
                    </div>
                    <div className="grid grid-cols-4 gap-2">
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
                            className="absolute top-1 right-1 p-1 rounded-full bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <X className="w-3 h-3" />
                          </button>
                          <span className="absolute bottom-1 left-1 text-xs bg-black/50 text-white px-1.5 py-0.5 rounded">
                            {idx + 1}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Upload Button */}
                {selectedFiles.length > 0 && (
                  <Button onClick={processFiles} className="w-full">
                    <Upload className="w-4 h-4 mr-2" />
                    Upload {selectedFiles.length} Image
                    {selectedFiles.length > 1 ? "s" : ""}
                  </Button>
                )}
              </TabsContent>

              {/* PDF Upload */}
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
                  <FileText className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                  {isPdfDragActive ? (
                    <p className="text-primary font-medium">Drop PDF here...</p>
                  ) : (
                    <>
                      <p className="font-medium text-zinc-900 dark:text-white mb-1">
                        Drag and drop PDF here
                      </p>
                      <p className="text-sm text-muted-foreground">
                        or click to select
                      </p>
                    </>
                  )}
                </div>

                {/* PDF Preview */}
                {selectedFiles.length > 0 && inputType === "pdf" && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3 p-3 bg-zinc-50 dark:bg-zinc-900/50 rounded-lg border">
                      <FileText className="w-8 h-8 text-red-500" />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">
                          {selectedFiles[0].name}
                        </p>
                        <p className="text-sm text-muted-foreground">
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
                    <Button onClick={processFiles} className="w-full">
                      <Upload className="w-4 h-4 mr-2" />
                      Upload PDF
                    </Button>
                  </div>
                )}
              </TabsContent>
            </Tabs>

            {/* Error Message (shown in idle state) */}
            {error && step === "idle" && (
              <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Preview */}
            {previewUrls.length > 0 && (
              <div className="space-y-2">
                {inputType === "pdf" ? (
                  <div className="flex items-center gap-3 p-4 bg-zinc-50 dark:bg-zinc-900/50 rounded-lg border">
                    <FileText className="w-10 h-10 text-red-500" />
                    <div>
                      <p className="font-medium">{selectedFiles[0]?.name}</p>
                      <p className="text-sm text-muted-foreground">
                        Processing PDF...
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-4 gap-2">
                    {previewUrls.slice(0, 8).map((url, idx) => (
                      <div
                        key={idx}
                        className="relative aspect-square rounded-lg overflow-hidden bg-zinc-100 dark:bg-zinc-800"
                      >
                        <img
                          src={url}
                          alt={`Preview ${idx + 1}`}
                          className="w-full h-full object-cover"
                        />
                        {step !== "done" && step !== "error" && (
                          <div className="absolute inset-0 bg-black/30 flex items-center justify-center">
                            <Loader2 className="w-4 h-4 text-white animate-spin" />
                          </div>
                        )}
                      </div>
                    ))}
                    {previewUrls.length > 8 && (
                      <div className="aspect-square rounded-lg bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center">
                        <span className="text-sm font-medium text-muted-foreground">
                          +{previewUrls.length - 8}
                        </span>
                      </div>
                    )}
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
