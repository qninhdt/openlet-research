"use client";

import { Question } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";

interface QuestionEditorCardProps {
  question: Question;
  index: number;
  onUpdate: (questionId: number, updates: Partial<Question>) => void;
  onDelete: (questionId: number) => void;
}

export function QuestionEditorCard({
  question,
  index,
  onUpdate,
  onDelete,
}: QuestionEditorCardProps) {
  const handleContentChange = (value: string) => {
    onUpdate(question.id, { content: value });
  };

  const handleOptionChange = (optionIndex: number, value: string) => {
    const newOptions = [...question.options];
    newOptions[optionIndex] = value;
    onUpdate(question.id, { options: newOptions });
  };

  const handleCorrectChange = (value: string) => {
    onUpdate(question.id, { correct: parseInt(value) });
  };

  const handleExplanationChange = (value: string) => {
    onUpdate(question.id, { explanation: value });
  };

  const optionLabels = ["A", "B", "C", "D"];

  return (
    <Card className="p-6 space-y-4">
      {/* Header with question number and actions */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
          Question {index + 1}
        </h3>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onDelete(question.id)}
          title="Delete question"
          className="text-error hover:text-error hover:bg-error-light dark:hover:bg-error-light"
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>

      {/* Question Content */}
      <div className="space-y-2">
        <Label htmlFor={`question-${question.id}`}>Question Text</Label>
        <Input
          id={`question-${question.id}`}
          value={question.content}
          onChange={(e) => handleContentChange(e.target.value)}
          placeholder="Enter your question here..."
          className="text-base"
        />
      </div>

      {/* Options with Radio Selection */}
      <div className="space-y-3">
        <Label>Answer Options</Label>
        <div className="space-y-2">
          {question.options.map((option, idx) => (
              <div
                key={idx}
                onClick={() => handleCorrectChange(idx.toString())}
                className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-colors cursor-pointer ${
                  question.correct === idx
                    ? "border-success bg-success-light dark:bg-success-light"
                    : "border-zinc-200 dark:border-zinc-700 hover:border-zinc-300 dark:hover:border-zinc-600"
                }`}
              >
                <span
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                    question.correct === idx
                      ? "bg-success text-success-foreground"
                      : "bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400"
                  }`}
                >
                  {optionLabels[idx]}
                </span>
              <Input
                id={`question-${question.id}-option-input-${idx}`}
                value={option}
                onChange={(e) => {
                  e.stopPropagation();
                  handleOptionChange(idx, e.target.value);
                }}
                onClick={(e) => e.stopPropagation()}
                placeholder={`Option ${optionLabels[idx]}`}
                className={`flex-1 border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 ${
                  question.correct === idx
                    ? "font-medium"
                    : ""
                }`}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Explanation */}
      <div className="space-y-2">
        <Label htmlFor={`explanation-${question.id}`}>Explanation</Label>
        <Textarea
          id={`explanation-${question.id}`}
          value={question.explanation || ""}
          onChange={(e) => handleExplanationChange(e.target.value)}
          placeholder="Explain why the correct answer is right..."
          rows={3}
          className="resize-none"
        />
      </div>
    </Card>
  );
}
