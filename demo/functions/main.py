"""Firebase Cloud Functions for quiz OCR and question generation."""

import asyncio
import base64
import io
from urllib.parse import unquote

import aiohttp
import pymupdf
from firebase_admin import initialize_app, storage
from firebase_functions import firestore_fn, options, params

from parser import parse_llm_output
from prompts import OCR_PROMPT, QUESTION_GENERATION_PROMPT

# Initialize Firebase Admin
initialize_app()

options.set_global_options(region="asia-southeast1")

# Configuration
OPENROUTER_API_KEY = params.SecretParam("OPENROUTER_API_KEY")
NOVITAAI_API_KEY = params.SecretParam("NOVITAAI_API_KEY")

# Default models (will be overridden by quiz document if specified)
DEFAULT_OCR_MODEL = "google/gemini-2.5-flash"
DEFAULT_QUESTION_MODEL = "google/gemini-2.5-flash"

# Limits
MAX_PDF_PAGES = 10


def _get_mime_type(file_path: str) -> str:
    """Get MIME type based on file extension."""
    lower_path = file_path.lower()
    if lower_path.endswith(".png"):
        return "image/png"
    elif lower_path.endswith(".jpg") or lower_path.endswith(".jpeg"):
        return "image/jpeg"
    elif lower_path.endswith(".gif"):
        return "image/gif"
    elif lower_path.endswith(".webp"):
        return "image/webp"
    elif lower_path.endswith(".pdf"):
        return "application/pdf"
    return "image/png"  # Default


def _extract_images_from_pdf(pdf_buffer: bytes) -> list[bytes]:
    """
    Extract page images from PDF using PyMuPDF (pymupdf).
    Returns a list of PNG image bytes, one per page.
    Max pages: MAX_PDF_PAGES
    """
    images: list[bytes] = []

    with pymupdf.open(stream=pdf_buffer, filetype="pdf") as doc:
        page_count = min(len(doc), MAX_PDF_PAGES)

        for page_num in range(page_count):
            page = doc[page_num]
            # Render page to image (2x zoom for better quality)
            mat = pymupdf.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            images.append(img_bytes)

    return images


def _download_file_from_storage(file_url: str) -> tuple[bytes, str]:
    """
    Download file from Firebase Storage.
    Returns (file_bytes, decoded_path).
    """
    bucket = storage.bucket()
    file_path = file_url.split("/o/")[1].split("?")[0]
    decoded_path = unquote(file_path)
    blob = bucket.blob(decoded_path)
    file_buffer = blob.download_as_bytes()
    return file_buffer, decoded_path


async def _ocr_single_image(
    session: aiohttp.ClientSession,
    image_bytes: bytes,
    ocr_model: str,
    api_key: str,
    page_index: int,
) -> tuple[int, str]:
    """
    Process OCR for a single image.
    Returns (page_index, ocr_text) for ordering results.
    """
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    base64_data = f"data:image/png;base64,{base64_image}"

    async with session.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": ocr_model,
            "messages": [
                {"role": "system", "content": OCR_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": base64_data},
                        },
                    ],
                },
            ],
        },
        timeout=aiohttp.ClientTimeout(total=120),
    ) as response:
        if response.status != 200:
            error_text = await response.text()
            raise Exception(
                f"OCR API error for page {page_index + 1}: {response.status} - {error_text}"
            )

        result = await response.json()
        ocr_text = (
            result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        )

        return (page_index, ocr_text)


async def _process_multiple_images_ocr(
    image_bytes_list: list[bytes],
    ocr_model: str,
    api_key: str,
) -> str:
    """
    Process OCR for multiple images in parallel.
    Returns combined OCR text from all pages, ordered by page number.
    """
    async with aiohttp.ClientSession() as session:
        # Create tasks for parallel processing
        tasks = [
            _ocr_single_image(session, img_bytes, ocr_model, api_key, idx)
            for idx, img_bytes in enumerate(image_bytes_list)
        ]

        # Run all OCR requests in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results and handle errors
    ocr_texts: list[tuple[int, str]] = []
    errors: list[str] = []

    for result in results:
        if isinstance(result, Exception):
            errors.append(str(result))
        else:
            page_idx, text = result
            if text:
                ocr_texts.append((page_idx, text))

    if errors and not ocr_texts:
        raise Exception(f"All OCR requests failed: {'; '.join(errors)}")

    if errors:
        print(f"Warning: Some OCR requests failed: {'; '.join(errors)}")

    # Sort by page index and combine texts
    ocr_texts.sort(key=lambda x: x[0])
    combined_text = "\n\n".join(text for _, text in ocr_texts)

    return combined_text


async def _process_ocr_async(
    quiz_id: str,
    doc_ref,
    api_key: str,
    ocr_model: str,
    image_urls: list[str] | None = None,
    pdf_url: str | None = None,
) -> None:
    """
    Async helper for OCR processing.
    Supports:
    - Multiple image URLs (image_urls)
    - Single PDF URL (pdf_url) - extracts pages as images
    """
    try:
        image_bytes_list: list[bytes] = []
        input_type = "unknown"

        if pdf_url:
            # Handle PDF input
            input_type = "pdf"
            print(f"Processing PDF for quiz {quiz_id} using model {ocr_model}")

            pdf_buffer, _ = _download_file_from_storage(pdf_url)
            image_bytes_list = _extract_images_from_pdf(pdf_buffer)

            if not image_bytes_list:
                raise Exception("PDF contains no pages or could not be processed")

            print(f"Extracted {len(image_bytes_list)} pages from PDF")

        elif image_urls:
            # Handle multiple images input
            input_type = "images"
            print(
                f"Processing {len(image_urls)} images for quiz {quiz_id} using model {ocr_model}"
            )

            for url in image_urls:
                img_buffer, _ = _download_file_from_storage(url)
                image_bytes_list.append(img_buffer)

        else:
            raise Exception("No input provided: imageUrls or pdfUrl required")

        # Process all images in parallel
        print(f"Starting parallel OCR for {len(image_bytes_list)} pages...")
        ocr_text = await _process_multiple_images_ocr(
            image_bytes_list, ocr_model, api_key
        )

        if not ocr_text:
            raise Exception("OCR returned empty text")

        # Update quiz with OCR text and move to next stage
        doc_ref.update(
            {
                "ocrText": ocr_text,
                "status": "generating_quiz",
                "pageCount": len(image_bytes_list),
                "inputType": input_type,
            }
        )

        print(
            f"OCR completed for quiz {quiz_id}: {len(image_bytes_list)} pages processed"
        )

    except Exception as e:
        print(f"OCR error for quiz {quiz_id}: {e}")
        doc_ref.update({"status": "error", "errorMessage": str(e)})


@firestore_fn.on_document_updated(
    document="quizzes/{quiz_id}",
    secrets=[OPENROUTER_API_KEY],
)
def process_ocr(
    event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]],
) -> None:
    """
    Process OCR when quiz is created with status 'processing_ocr'.

    Supports two input types:
    - imageUrls: list of image URLs (multiple images)
    - pdfUrl: single PDF URL (pages extracted as images, max 10 pages)

    Legacy support: imageUrl (single image) is converted to imageUrls
    """
    if event.data is None:
        return

    new_data = event.data.after.to_dict()
    previous_data = event.data.before.to_dict()

    if new_data is None or previous_data is None:
        return

    # Only process if status changed to "processing_ocr"
    if (
        new_data.get("status") != "processing_ocr"
        or previous_data.get("status") == "processing_ocr"
    ):
        return

    quiz_id = event.params.get("quiz_id", "unknown")
    ocr_model = new_data.get("ocrModel", DEFAULT_OCR_MODEL)
    doc_ref = event.data.after.reference

    # Get input: imageUrls (array), pdfUrl, or legacy imageUrl
    image_urls = new_data.get("imageUrls")
    pdf_url = new_data.get("pdfUrl")

    # Legacy support: convert single imageUrl to array
    if not image_urls and not pdf_url:
        legacy_url = new_data.get("imageUrl")
        if legacy_url:
            image_urls = [legacy_url]

    if not image_urls and not pdf_url:
        doc_ref.update(
            {
                "status": "error",
                "errorMessage": "No input provided: imageUrls or pdfUrl required",
            }
        )
        return

    # Run async function in sync context
    asyncio.run(
        _process_ocr_async(
            quiz_id,
            doc_ref,
            OPENROUTER_API_KEY.value,
            ocr_model,
            image_urls,
            pdf_url,
        )
    )


async def _generate_questions_async(
    quiz_id: str,
    ocr_text: str,
    question_model: str,
    doc_ref,
    api_key: str,
    file_urls: list[str] | None = None,
    delete_files: bool = True,
) -> None:
    """Async helper for question generation."""
    try:
        print(f"Generating questions for quiz {quiz_id} using model {question_model}")

        # Create the full prompt with the text
        full_prompt = QUESTION_GENERATION_PROMPT.replace("{text}", ocr_text)

        # Call OpenRouter API for question generation (async)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": question_model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "temperature": 0.0,
                },
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Question generation API error: {response.status} - {error_text}"
                    )

                result = await response.json()
                llm_output = (
                    result.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

        # Parse the LLM output into structured questions with metadata
        parsed_data = parse_llm_output(llm_output)

        if not parsed_data.questions:
            raise Exception("Failed to parse questions from LLM output")

        # Update quiz with questions, metadata and mark as ready
        doc_ref.update(
            {
                "questions": [
                    {
                        "id": q.id,
                        "content": q.content,
                        "options": q.options,
                        "correct": q.correct,
                        "type": q.type,
                    }
                    for q in parsed_data.questions
                ],
                "title": parsed_data.title,
                "genre": parsed_data.genre,
                "topics": parsed_data.topics,
                "status": "ready",
            }
        )

        print(
            f"Question generation completed for quiz {quiz_id}, "
            f"{len(parsed_data.questions)} questions created. "
            f'Title: "{parsed_data.title}", Genre: {parsed_data.genre}, '
            f"Topics: [{', '.join(parsed_data.topics)}]"
        )

        # Delete temporary files after successful question generation
        if delete_files and file_urls:
            bucket = storage.bucket()
            for file_url in file_urls:
                try:
                    file_path = file_url.split("/o/")[1].split("?")[0]
                    decoded_path = unquote(file_path)
                    blob = bucket.blob(decoded_path)
                    blob.delete()
                    print(f"Deleted temporary file for quiz {quiz_id}: {decoded_path}")
                except Exception as delete_error:
                    # Don't fail the whole function if file deletion fails
                    print(
                        f"Warning: Failed to delete file for quiz {quiz_id}: {delete_error}"
                    )

    except Exception as e:
        print(f"Question generation error for quiz {quiz_id}: {e}")
        doc_ref.update({"status": "error", "errorMessage": str(e)})


@firestore_fn.on_document_updated(
    document="quizzes/{quiz_id}",
    secrets=[OPENROUTER_API_KEY],
)
def generate_questions(
    event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]],
) -> None:
    """Generate questions when quiz status changes to 'generating_quiz'."""
    if event.data is None:
        return

    new_data = event.data.after.to_dict()
    previous_data = event.data.before.to_dict()

    if new_data is None or previous_data is None:
        return

    # Only process if status changed to "generating_quiz"
    if (
        new_data.get("status") != "generating_quiz"
        or previous_data.get("status") == "generating_quiz"
    ):
        return

    quiz_id = event.params.get("quiz_id", "unknown")
    ocr_text = new_data.get("ocrText")
    question_model = new_data.get("questionModel", DEFAULT_QUESTION_MODEL)

    # Collect all file URLs for cleanup
    file_urls: list[str] = []
    if image_urls := new_data.get("imageUrls"):
        file_urls.extend(image_urls)
    if pdf_url := new_data.get("pdfUrl"):
        file_urls.append(pdf_url)
    # Legacy support
    if legacy_url := new_data.get("imageUrl"):
        if legacy_url not in file_urls:
            file_urls.append(legacy_url)

    # Allow users to control whether to delete files (default: True)
    delete_files = new_data.get("deleteFilesAfterProcessing", True)

    doc_ref = event.data.after.reference

    if not ocr_text:
        doc_ref.update({"status": "error", "errorMessage": "No OCR text found"})
        return

    # Run async function in sync context
    asyncio.run(
        _generate_questions_async(
            quiz_id,
            ocr_text,
            question_model,
            doc_ref,
            OPENROUTER_API_KEY.value,
            file_urls,
            delete_files,
        )
    )
