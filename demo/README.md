# Openlet - AI Quiz Generator

> Full-stack web application that converts document images into multi-level multiple-choice quizzes using a multi-agent LLM pipeline, with a real-time quiz-taking interface for students.

[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Firebase](https://img.shields.io/badge/Firebase-11-FFCA28?logo=firebase&logoColor=black)](https://firebase.google.com)
[![Python](https://img.shields.io/badge/Functions-Python_3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)

---

## Table of Contents

- [Openlet - AI Quiz Generator](#openlet--ai-quiz-generator)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Architecture](#architecture)
  - [Tech Stack](#tech-stack)
    - [Frontend](#frontend)
    - [Backend (Cloud Functions)](#backend-cloud-functions)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Firebase Setup](#firebase-setup)
    - [1. Create a Firebase project](#1-create-a-firebase-project)
    - [2. Enable services](#2-enable-services)
    - [3. Firestore security rules](#3-firestore-security-rules)
    - [4. Storage security rules](#4-storage-security-rules)
  - [Cloud Functions Setup](#cloud-functions-setup)
    - [Deployed functions](#deployed-functions)
  - [Project Structure](#project-structure)
  - [App Routes](#app-routes)
  - [Generation Modes](#generation-modes)
    - [Single Prompt](#single-prompt)
    - [Multi-Agent *(recommended for high-stakes quizzes)*](#multi-agent-recommended-for-high-stakes-quizzes)
  - [Security Model](#security-model)

---

## Features

| Role | Capabilities |
|---|---|
| **Teacher** | Upload photos / PDFs → AI generates MCQs → Review & edit questions → Publish with a shareable link → View analytics |
| **Student** | Open quiz link (no account needed) → Take timed quiz → Get instant feedback with AI explanations |

**Highlights:**

- 📷 **Multi-format upload** - JPEG/PNG photos or multi-page PDFs (auto-converted to images)
- 🤖 **Two AI modes** - Single Prompt (fast) or Multi-Agent pipeline (high quality)
- 🧠 **Three cognitive levels** - Retrieval, Inference, Critical Reasoning (Bloom's Taxonomy)
- ✏️ **Full question editor** - Edit stem, options, correct answer, and explanation
- ⏱️ **Configurable timer** - Optional countdown with auto-submit on expiry
- 🔒 **Server-side grading** - Correct answers never sent to the client
- 📊 **5 feedback levels** - From "score only" to "full explanation"
- 📈 **Analytics dashboard** - Score distribution, leaderboard, per-attempt records
- 👤 **Anonymous access** - Students can take quizzes without registering

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                  Presentation Tier                        │
│         Next.js 16  ·  React 19  ·  Tailwind CSS v4       │
└─────────────────────┬─────────────────────────────────────┘
                      │  Firestore real-time listeners
                      │  HTTPS Callable Functions
┌─────────────────────▼─────────────────────────────────────┐
│                   Service Tier (Firebase)                 │
│  Cloud Firestore  ·  Cloud Storage  ·  Cloud Functions v2 │
└─────────────────────┬─────────────────────────────────────┘
                      │  OpenRouter API
┌─────────────────────▼─────────────────────────────────────┐
│                      AI Tier                              │
│        OpenRouter API Gateway  →  Gemini / GPT / Llama    │
└───────────────────────────────────────────────────────────┘
```

**Event-driven quiz creation:** Each quiz document in Firestore has a `status` field that drives a server-side state machine. Cloud Functions listen for status changes and automatically trigger the next processing stage - enabling async, resumable workflows.

---

## Tech Stack

### Frontend

| Package | Version | Purpose |
|---|---|---|
| Next.js | 16 | Full-stack framework (App Router) |
| React | 19 | UI library |
| Tailwind CSS | v4 | Utility-first styling |
| shadcn/ui + Radix UI | latest | Accessible component primitives |
| Zustand | 5 | Client-side state management |
| Recharts | 2 | Analytics charts |
| React Dropzone | 14 | Drag-and-drop file upload |
| React Hook Form + Zod | latest | Form validation |
| Lucide React | latest | Icon set |

### Backend (Cloud Functions)

| Package | Purpose |
|---|---|
| `firebase-functions` | Cloud Functions v2 trigger framework |
| `firebase-admin` | Firestore, Storage, Auth admin SDK |
| `aiohttp` | Async HTTP client for OpenRouter API calls |
| `pymupdf` | PDF-to-image conversion |

---

## Prerequisites

- **Node.js** 18+ and **npm** 9+
- **Python** 3.12+ (for Cloud Functions)
- A [Firebase](https://firebase.google.com) project with Blaze (pay-as-you-go) plan
- An [OpenRouter](https://openrouter.ai) API key

---

## Installation

```bash
# From the repo root
cd demo

# Install Node dependencies
npm install

# Copy environment template
cp .env.example .env.local
# → Fill in values (see Environment Variables section below)

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

| Script | Description |
|---|---|
| `npm run dev` | Start development server with hot reload |
| `npm run build` | Production build |
| `npm run start` | Serve production build |
| `npm run lint` | Run ESLint |
| `npm run lint:fix` | Auto-fix lint issues |

---

## Environment Variables

Create `demo/.env.local` from `demo/.env.example`:

```env
# ── Firebase ──────────────────────────────────────────────
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=
NEXT_PUBLIC_FIREBASE_PROJECT_ID=
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=
NEXT_PUBLIC_FIREBASE_APP_ID=

# ── OpenRouter ────────────────────────────────────────────
OPENROUTER_API_KEY=
```

---

## Firebase Setup

### 1. Create a Firebase project

Go to [Firebase Console](https://console.firebase.google.com) → **Add project** → upgrade to **Blaze plan** (required for Cloud Functions).

### 2. Enable services

| Service | Configuration |
|---|---|
| **Authentication** | Enable **Email/Password** and **Anonymous** providers |
| **Firestore** | Create database in production mode |
| **Storage** | Create default bucket |
| **Functions** | Enabled automatically with Blaze plan |

### 3. Firestore security rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    match /quizzes/{quizId} {
      // Owner has full access
      allow read, write: if request.auth != null
                         && request.auth.uid == resource.data.createdBy;
      // Any authenticated user can create
      allow create: if request.auth != null;

      // Attempts sub-collection: anyone authenticated can read/write their own
      match /attempts/{attemptId} {
        allow read, write: if request.auth != null;
      }
    }

    match /users/{userId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
```

### 4. Storage security rules

```javascript
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /quizzes/{userId}/{allPaths=**} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
```

---

## Cloud Functions Setup

The backend logic runs as **Python Cloud Functions v2** in `demo/functions/`.

```bash
cd demo/functions

# Install Firebase CLI (if not already)
npm install -g firebase-tools

# Log in and select your project
firebase login
firebase use your-project-id

# Install Python dependencies into the functions venv
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Deploy functions
firebase deploy --only functions
```

### Deployed functions

| Function | Trigger | Description |
|---|---|---|
| `process_ocr` | Firestore `onDocumentUpdated` | Runs VLM OCR on uploaded images when status → `processing_ocr` |
| `analyze_content` | Firestore `onDocumentUpdated` | Runs Analyzer agent when status → `analyzing` (Multi-Agent only) |
| `generate_questions` | Firestore `onDocumentUpdated` | Runs question generation pipeline when status → `generating_quiz` |
| `get_quiz_for_player` | HTTPS Callable | Returns quiz data **without** answers for students |
| `submit_quiz_answers` | HTTPS Callable | Grades submission server-side and saves attempt |

---

## Project Structure

```
demo/
│
├── app/                          # Next.js App Router
│   ├── layout.tsx                # Root layout (providers, theme)
│   ├── page.tsx                  # Dashboard / login redirect
│   ├── quiz/[id]/                # Owner quiz management
│   │   ├── content/              # Question list preview
│   │   ├── edit/                 # Question editor
│   │   │   └── questions/        # Per-question edit view
│   │   ├── analytics/            # Score distribution & leaderboard
│   │   ├── responses/            # Per-attempt records
│   │   └── settings/             # Publish, timer, visibility settings
│   └── play/[quizId]/            # Student-facing pages
│       ├── page.tsx              # Quiz intro / start
│       └── attempt/[attemptId]/  # Quiz-taking interface & results
│
├── components/
│   ├── auth/                     # Login button
│   ├── pages/                    # Full-page components (dashboard, login)
│   ├── providers/                # Auth context provider
│   ├── quiz/
│   │   ├── import-questions-dialog.tsx  # AI import modal (mode + model picker)
│   │   ├── question-editor-card.tsx     # Single-question editor
│   │   ├── quiz-card.tsx                # Dashboard quiz card
│   │   └── take-quiz-dialog.tsx         # Legacy inline quiz dialog
│   └── ui/                       # shadcn/ui primitives
│
├── hooks/
│   ├── use-mobile.ts             # Responsive breakpoint hook
│   └── use-toast.ts              # Toast notification hook
│
├── lib/
│   ├── auth.ts                   # Firebase Auth helpers
│   ├── firebase.ts               # Firebase app initialization
│   ├── store.ts                  # Zustand global stores
│   ├── types.ts                  # TypeScript type definitions
│   └── utils.ts                  # Utility functions (cn, formatters …)
│
└── functions/                    # Firebase Cloud Functions (Python 3.12)
    ├── main.py                   # Function triggers & pipeline logic
    ├── parser.py                 # LLM output parsers
    ├── prompts.py                # Prompt templates
    └── requirements.txt          # Python dependencies
```

---

## App Routes

| Route | Access | Description |
|---|---|---|
| `/` | Owner | Dashboard - list of created quizzes |
| `/quiz/[id]` | Owner | Quiz overview redirect |
| `/quiz/[id]/content` | Owner | Read-only question list |
| `/quiz/[id]/edit` | Owner | Edit quiz metadata |
| `/quiz/[id]/edit/questions` | Owner | Full question editor |
| `/quiz/[id]/analytics` | Owner | Score distribution & leaderboard |
| `/quiz/[id]/responses` | Owner | All attempt records |
| `/quiz/[id]/settings` | Owner | Publish, timer, feedback visibility |
| `/play/[quizId]` | Public | Quiz intro page (shareable link) |
| `/play/[quizId]/attempt/[attemptId]` | Public | Take quiz + view results |

---

## Generation Modes

The **Import Questions with AI** dialog lets teachers choose between two modes:

### Single Prompt
One API call generates all questions at once. Fast and cheap, but may produce less precise cognitive-level targeting.

```
Upload → OCR → [Single LLM call] → Questions
```

### Multi-Agent *(recommended for high-stakes quizzes)*
A linear single-pass pipeline with specialised agents:

```
Upload → OCR → Analyzer → Generator (L1 ∥ L2 ∥ L3)
                              ↓
                         Classifier ──(rejected, once)──► Re-generate
                              ↓
                           Student ──(failed)──► Fixer
                              ↓
                          Explainer
                              ↓
                           Ready
```

| Agent | Role |
|---|---|
| **Analyzer** | Extracts key entities, causal chains, and confusable terms from the passage |
| **Generator L1/L2/L3** | Three parallel agents, each focused on one cognitive level |
| **Classifier** | Verifies cognitive level; triggers one regeneration round for rejected questions |
| **Student** | Simulates solving - flags questions with ambiguous or unsolvable answers |
| **Fixer** | Repairs answer options (stem is never changed) for questions the Student failed |
| **Explainer** | Generates per-question explanations for the results page |

---

## Security Model

- **Answers never reach the client.** `get_quiz_for_player` strips all `correctIndex` and `explanation` fields before returning quiz data.
- **Server-side grading.** `submit_quiz_answers` compares student answers against the database copy and applies the owner's visibility level before returning feedback.
- **Visibility levels** (set per quiz by the teacher):

| Level | What the student sees after submission |
|---|---|
| 0 | Nothing - submission acknowledged only |
| 1 | Total score (correct / total, percentage) |
| 2 | Score + per-question correct/incorrect status |
| 3 | Score + correct/incorrect + correct answer |
| 4 | Full feedback including AI-generated explanation |
