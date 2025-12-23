# Openlet - AI Quiz Generator

Ứng dụng tạo bài kiểm tra trắc nghiệm từ ảnh chụp tài liệu sử dụng AI.

## Tính năng

- 🔐 **Đăng nhập Google** - Xác thực người dùng với Firebase Auth
- 📷 **Upload/Chụp ảnh** - Hỗ trợ kéo thả hoặc chụp trực tiếp từ camera
- 🤖 **AI OCR** - Trích xuất văn bản từ ảnh với độ chính xác cao
- ✨ **Tự động tạo câu hỏi** - Tạo bộ câu hỏi trắc nghiệm đa dạng
- 📝 **Làm bài kiểm tra** - Giao diện làm bài trực quan
- 📊 **Xem kết quả** - Chi tiết đáp án đúng/sai và điểm số

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **UI**: Tailwind CSS + shadcn/ui
- **State Management**: Zustand
- **Backend**: Firebase (Auth, Firestore, Storage)
- **AI**: OpenRouter API (OCR + Question Generation)

## Cài đặt

### 1. Clone và cài đặt dependencies

```bash
cd demo
npm install
```

### 2. Cấu hình Firebase

1. Tạo project tại [Firebase Console](https://console.firebase.google.com)
2. Enable Authentication với Google Provider
3. Tạo Firestore Database
4. Tạo Storage bucket
5. Copy Firebase config vào file `.env.local`

### 3. Cấu hình OpenRouter

1. Đăng ký tài khoản tại [OpenRouter](https://openrouter.ai)
2. Tạo API key
3. Thêm vào file `.env.local`

### 4. Tạo file môi trường

Tạo file `.env.local` dựa trên `.env.example`:

```bash
cp .env.example .env.local
```

Điền các giá trị:

```env
# Firebase Configuration
NEXT_PUBLIC_FIREBASE_API_KEY=your_api_key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_project_id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your_project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
NEXT_PUBLIC_FIREBASE_APP_ID=your_app_id

# OpenRouter API Key
OPENROUTER_API_KEY=your_openrouter_api_key

# Optional: Custom models
OCR_MODEL=google/gemini-2.0-flash-exp:free
QUESTION_MODEL=anthropic/claude-3.5-sonnet
```

### 5. Cấu hình Firestore Rules

Vào Firebase Console > Firestore > Rules và thêm:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /quizzes/{quizId} {
      allow read, write: if request.auth != null && request.auth.uid == resource.data.userId;
      allow create: if request.auth != null;
    }
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

### 6. Cấu hình Storage Rules

Vào Firebase Console > Storage > Rules:

```javascript
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /quizzes/{userId}/{allPaths=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

### 7. Chạy ứng dụng

```bash
npm run dev
```

Mở [http://localhost:3000](http://localhost:3000) để xem ứng dụng.

## Cấu trúc thư mục

```
demo/
├── app/
│   ├── api/
│   │   ├── ocr/route.ts           # OCR API endpoint
│   │   └── generate-questions/route.ts  # Question gen API
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   ├── auth/
│   │   └── login-button.tsx
│   ├── pages/
│   │   ├── dashboard-page.tsx
│   │   └── login-page.tsx
│   ├── providers/
│   │   └── auth-provider.tsx
│   ├── quiz/
│   │   ├── create-quiz-dialog.tsx
│   │   ├── quiz-card.tsx
│   │   └── take-quiz-dialog.tsx
│   └── ui/                        # shadcn/ui components
├── hooks/
│   └── use-toast.ts
└── lib/
    ├── firebase.ts               # Firebase initialization
    ├── parser.ts                 # LLM output parser
    ├── prompts.ts                # OCR & Question prompts
    ├── store.ts                  # Zustand stores
    ├── types.ts                  # TypeScript types
    └── utils.ts
```

## Luồng hoạt động

1. **Đăng nhập** - User đăng nhập với tài khoản Google
2. **Tạo bài kiểm tra** - Upload hoặc chụp ảnh tài liệu
3. **OCR Processing** - API trích xuất văn bản từ ảnh
4. **Question Generation** - AI tạo câu hỏi trắc nghiệm
5. **Làm bài** - User làm bài kiểm tra
6. **Xem kết quả** - Hiển thị điểm và đáp án chi tiết

## Models được hỗ trợ

### OCR (Multimodal)
- `google/gemini-2.0-flash-exp:free` (mặc định)
- `qwen/qwen-2.5-vl-72b-instruct`
- `openai/gpt-4-vision-preview`

### Question Generation
- `anthropic/claude-3.5-sonnet` (mặc định)
- `openai/gpt-4`
- `meta-llama/llama-3.1-70b-instruct`

## License

MIT
