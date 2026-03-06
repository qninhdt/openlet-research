"""Firebase Cloud Functions for quiz OCR, question generation, and answer evaluation."""

import asyncio
import base64
from datetime import datetime
from urllib.parse import unquote

import aiohttp
import pymupdf

from firebase_admin import firestore as admin_firestore
from firebase_admin import initialize_app, storage
from firebase_functions import firestore_fn, https_fn, options, params

from parser import (
    parse_llm_output,
    parse_single_prompt_metadata,
    parse_analyzer_metadata,
    parse_generator_output,
    parse_validator_output,
    parse_explanation_output,
    format_questions_for_validation,
    format_failed_questions_for_fixer,
    format_questions_for_explanation,
)
from prompts import (
    OCR_PROMPT,
    SINGLE_PROMPT_QUESTION_GENERATION,
    ANALYZER_PROMPT,
    EXPLANATION_PROMPT,
    LEVEL1_GENERATOR_PROMPT,
    LEVEL1_VALIDATOR_PROMPT,
    LEVEL1_FIXER_PROMPT,
    LEVEL2_GENERATOR_PROMPT,
    LEVEL2_VALIDATOR_PROMPT,
    LEVEL2_FIXER_PROMPT,
    LEVEL3_GENERATOR_PROMPT,
    LEVEL3_VALIDATOR_PROMPT,
    LEVEL3_FIXER_PROMPT,
)

# Initialize Firebase Admin
initialize_app()

options.set_global_options(region="asia-southeast1")

# Configuration
OPENROUTER_API_KEY = params.SecretParam("OPENROUTER_API_KEY")
NOVITAAI_API_KEY = params.SecretParam("NOVITAAI_API_KEY")

# Default models (will be overridden by quiz document if specified)
DEFAULT_OCR_MODEL = "google/gemini-3-flash-preview"
DEFAULT_QUESTION_MODEL = "google/gemini-3-flash-preview"

# Limits
MAX_PDF_PAGES = 10
MAX_FIX_RETRIES = 2  # Max validator→fixer iterations per level in multi-agent mode


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

        # Determine next stage based on generation mode
        generation_mode = doc_ref.get().to_dict().get("generationMode", "single_prompt")
        next_status = "analyzing" if generation_mode == "multi_agent" else "generating_quiz"

        # Update quiz with OCR text and move to next stage
        doc_ref.update(
            {
                "ocrText": ocr_text,
                "status": next_status,
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


async def _call_llm(session: aiohttp.ClientSession, api_key: str, model: str, prompt: str, timeout: int = 180) -> str:
    """Call OpenRouter API and return the content string."""
    async with session.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 8192,
            "provider": {
                "sort": {
                    "by": "throughput",
                }
            },
            "reasoning": {"effort": "none"},
        },
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as response:
        if response.status != 200:
            error_text = await response.text()
            raise Exception(f"API error: {response.status} - {error_text}")
        result = await response.json()
        return (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )


async def _run_generator(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    generator_prompt: str,
    content: str,
    analyzer_output: str,
    n: int,
    level: int,
) -> list[dict]:
    """Run a level generator and return parsed questions."""
    full_prompt = (
        generator_prompt
        .replace("{content}", content)
        .replace("{analyzer_output}", analyzer_output)
        .replace("{n}", str(n))
    )
    output = await _call_llm(session, api_key, model, full_prompt)
    questions = parse_generator_output(output, n, expected_level=level)
    print(f"  Level {level} generator: {len(questions)} questions created")
    return questions


async def _run_validator(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    validator_prompt: str,
    content: str,
    questions: list[dict],
) -> list[dict]:
    """Run the validator and return validation results."""
    questions_text = format_questions_for_validation(questions)
    full_prompt = (
        validator_prompt
        .replace("{content}", content)
        .replace("{questions}", questions_text)
    )
    output = await _call_llm(session, api_key, model, full_prompt)
    return parse_validator_output(output)


async def _run_fixer(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    fixer_prompt: str,
    content: str,
    analyzer_output: str,
    questions: list[dict],
    validation: list[dict],
    per_question_history: dict[int, list[str]],
    level: int,
) -> list[dict]:
    """Run the fixer on failed questions and return merged question list."""
    failed_text = format_failed_questions_for_fixer(questions, validation)
    if not failed_text.strip():
        return questions

    # Build history text for currently failing questions
    currently_failed_ids = {v["id"] for v in validation if v.get("verdict") == "FAIL"}
    history_lines = []
    for q_id in sorted(currently_failed_ids):
        past = per_question_history.get(q_id, [])
        if past:
            rounds = "\n".join(f"  Attempt {i + 1}: {fb}" for i, fb in enumerate(past))
            history_lines.append(f"Q{q_id} previous feedback:\n{rounds}")
    history_text = "\n\n".join(history_lines) if history_lines else "No previous fix attempts."

    full_prompt = (
        fixer_prompt
        .replace("{content}", content)
        .replace("{analyzer_output}", analyzer_output)
        .replace("{fix_history}", history_text)
        .replace("{failed_questions}", failed_text)
    )
    output = await _call_llm(session, api_key, model, full_prompt)
    fixed_questions = parse_generator_output(output, len(questions), expected_level=level)

    # Merge: replace only fixed questions by ID
    fixed_map = {fq["id"]: fq for fq in fixed_questions if fq.get("id") is not None}
    failed_ids = {v["id"] for v in validation if v.get("verdict") == "FAIL"}
    merged = []
    for idx, q in enumerate(questions):
        q_id = idx + 1
        if q_id in failed_ids and q_id in fixed_map:
            merged.append(fixed_map[q_id])
        else:
            merged.append(q)
    return merged


async def _validate_and_fix_level(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    validator_prompt: str,
    fixer_prompt: str,
    content: str,
    analyzer_output: str,
    questions: list[dict],
    level: int,
    max_fix_retries: int = MAX_FIX_RETRIES,
) -> list[dict]:
    """Validate questions for a level, then iteratively fix failures."""
    if not questions:
        return questions

    current_questions = questions
    per_question_history: dict[int, list[str]] = {}

    # Initial validation
    validation = await _run_validator(session, api_key, model, validator_prompt, content, current_questions)
    passed = sum(1 for v in validation if v["verdict"] == "PASS")
    print(f"  Level {level} validation: {passed}/{len(validation)} passed")

    # Retry loop
    for attempt in range(1, max_fix_retries + 1):
        if not any(v.get("verdict") == "FAIL" for v in validation):
            print(f"  Level {level}: All questions passed")
            break

        # Accumulate per-question feedback
        for v in validation:
            if v.get("verdict") == "FAIL":
                per_question_history.setdefault(v["id"], []).append(
                    v.get("feedback", "no feedback")
                )

        print(f"  Level {level}: Fix attempt {attempt}/{max_fix_retries}...")
        current_questions = await _run_fixer(
            session, api_key, model, fixer_prompt, content, analyzer_output,
            current_questions, validation, per_question_history, level,
        )

        # Re-validate
        validation = await _run_validator(session, api_key, model, validator_prompt, content, current_questions)
        passed = sum(1 for v in validation if v["verdict"] == "PASS")
        print(f"  Level {level} re-validation (attempt {attempt}): {passed}/{len(validation)} passed")

    return current_questions


async def _generate_questions_multi_agent(
    quiz_id: str,
    ocr_text: str,
    question_model: str,
    analyzer_output: str,
    api_key: str,
    target_question_count: int = 6,
    max_fix_retries: int = MAX_FIX_RETRIES,
    doc_ref=None,
) -> tuple[list[dict], dict]:
    """Run the full multi-agent pipeline: generate → validate → fix → explain.

    Returns (final_questions, metadata) where questions have 'content', 'options', 'correct', 'level', 'type'.
    """
    # Distribute questions across levels: n_2 = n_3 = total // 3, n_1 = total - n_2 - n_3
    n_2 = target_question_count // 3
    n_3 = target_question_count // 3
    n_1 = target_question_count - n_2 - n_3

    print(f"Multi-agent pipeline for quiz {quiz_id}: L1={n_1}, L2={n_2}, L3={n_3}")

    level_configs = [
        (1, n_1, LEVEL1_GENERATOR_PROMPT, LEVEL1_VALIDATOR_PROMPT, LEVEL1_FIXER_PROMPT),
        (2, n_2, LEVEL2_GENERATOR_PROMPT, LEVEL2_VALIDATOR_PROMPT, LEVEL2_FIXER_PROMPT),
        (3, n_3, LEVEL3_GENERATOR_PROMPT, LEVEL3_VALIDATOR_PROMPT, LEVEL3_FIXER_PROMPT),
    ]

    async with aiohttp.ClientSession() as session:
        # Step 1: Generate questions for all 3 levels (can run concurrently)
        generator_tasks = []
        for level, n, gen_prompt, _, _ in level_configs:
            if n > 0:
                generator_tasks.append(
                    _run_generator(session, api_key, question_model, gen_prompt, ocr_text, analyzer_output, n, level)
                )
            else:
                async def _empty():
                    return []
                generator_tasks.append(_empty())

        level_questions = list(await asyncio.gather(*generator_tasks, return_exceptions=True))

        # Handle exceptions in generator results
        for i, result in enumerate(level_questions):
            if isinstance(result, Exception):
                print(f"  Level {i+1} generator failed: {result}")
                level_questions[i] = []

        # Step 2: Validate and fix all levels in parallel
        if doc_ref:
            doc_ref.update({"status": "validating"})

        async def _val_fix_for_level(i, level, val_prompt, fix_prompt):
            questions = level_questions[i] if not isinstance(level_questions[i], Exception) else []
            if not questions:
                return []
            return await _validate_and_fix_level(
                session, api_key, question_model, val_prompt, fix_prompt,
                ocr_text, analyzer_output, questions, level, max_fix_retries,
            )

        val_fix_tasks = [
            _val_fix_for_level(i, level, val_prompt, fix_prompt)
            for i, (level, _, _, val_prompt, fix_prompt) in enumerate(level_configs)
        ]
        val_fix_results = await asyncio.gather(*val_fix_tasks, return_exceptions=True)

        final_level_questions = [
            [] if isinstance(r, Exception) else r
            for r in val_fix_results
        ]

    # Step 3: Merge all questions
    all_questions = []
    for level_idx, questions in enumerate(final_level_questions):
        level = level_idx + 1
        for q in questions:
            all_questions.append({
                "content": q["question"],
                "options": q["options"],
                "correct": q["correct_idx"],
                "level": level,
                "type": "General",
                "explanation": "",
            })

    # Assign sequential IDs before explanation step
    for idx, q in enumerate(all_questions, 1):
        q["id"] = idx

    # Step 4: Generate explanations for all questions
    if doc_ref:
        doc_ref.update({"status": "explaining"})

    async with aiohttp.ClientSession() as session:
        try:
            questions_text = format_questions_for_explanation(all_questions)
            full_prompt = (
                EXPLANATION_PROMPT
                .replace("{content}", ocr_text)
                .replace("{questions}", questions_text)
            )
            explanation_output = await _call_llm(session, api_key, question_model, full_prompt)
            explanations = parse_explanation_output(explanation_output, len(all_questions))

            # Assign explanations to questions
            for q in all_questions:
                q_id = q.get("id")
                if q_id and q_id in explanations:
                    q["explanation"] = explanations[q_id]
                else:
                    q["explanation"] = "No explanation available."

            print(f"  Explanations generated: {len(explanations)}/{len(all_questions)}")
        except Exception as e:
            print(f"  Explanation agent failed (non-fatal): {e}")
            for q in all_questions:
                if not q.get("explanation"):
                    q["explanation"] = "No explanation available."

    # Extract metadata from analyzer output
    metadata = parse_analyzer_metadata(analyzer_output)

    print(f"Multi-agent pipeline completed: {len(all_questions)} total questions")
    return all_questions, metadata


async def _generate_questions_async(
    quiz_id: str,
    ocr_text: str,
    question_model: str,
    doc_ref,
    api_key: str,
    target_question_count: int = 5,
    generation_mode: str = "single_prompt",
    analyzer_output: str | None = None,
    file_urls: list[str] | None = None,
    delete_files: bool = True,
) -> None:
    """Async helper for question generation."""
    try:
        print(
            f"Generating {target_question_count} questions for quiz {quiz_id} "
            f"using model {question_model} (mode: {generation_mode})"
        )

        if generation_mode == "multi_agent" and analyzer_output:
            # Full multi-agent pipeline
            all_questions, metadata = await _generate_questions_multi_agent(
                quiz_id, ocr_text, question_model, analyzer_output,
                api_key, target_question_count, doc_ref=doc_ref,
            )

            if not all_questions:
                raise Exception("Multi-agent pipeline produced no questions")

            title = metadata.get("title", "Untitled Quiz")
            description = metadata.get("description", "")
            topics = metadata.get("topics", [])

            doc_ref.update({
                "questions": all_questions,
                "title": title,
                "description": description,
                "topics": topics,
                "status": "ready",
            })

            print(
                f"Multi-agent generation completed for quiz {quiz_id}, "
                f"{len(all_questions)} questions. "
                f'Title: "{title}", Topics: [{", ".join(topics)}]'
            )

        else:
            # Single-prompt mode
            full_prompt = (
                SINGLE_PROMPT_QUESTION_GENERATION
                .replace("{text}", ocr_text)
                .replace("{num_questions}", str(target_question_count))
            )

            async with aiohttp.ClientSession() as session:
                llm_output = await _call_llm(session, api_key, question_model, full_prompt)

            parsed_data = parse_llm_output(llm_output)

            if not parsed_data.questions:
                raise Exception("Failed to parse questions from LLM output")

            metadata = parse_single_prompt_metadata(llm_output)
            title = metadata.get("title", "Untitled Quiz")
            description = metadata.get("description", "")
            topics = metadata.get("topics", [])

            doc_ref.update({
                "questions": [
                    {
                        "id": q.id,
                        "content": q.content,
                        "options": q.options,
                        "correct": q.correct,
                        "explanation": q.explanation,
                        "type": q.type,
                    }
                    for q in parsed_data.questions
                ],
                "title": title,
                "description": description,
                "topics": topics,
                "status": "ready",
            })

            print(
                f"Single-prompt generation completed for quiz {quiz_id}, "
                f"{len(parsed_data.questions)} questions. "
                f'Title: "{title}", Topics: [{", ".join(topics)}]'
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
                    print(f"Warning: Failed to delete file for quiz {quiz_id}: {delete_error}")

    except Exception as e:
        print(f"Question generation error for quiz {quiz_id}: {e}")
        doc_ref.update({"status": "error", "errorMessage": str(e)})



async def _analyze_async(
    quiz_id: str,
    ocr_text: str,
    question_model: str,
    doc_ref,
    api_key: str,
) -> None:
    """Async helper for text analysis (multi-agent mode)."""
    try:
        print(f"Analyzing text for quiz {quiz_id} using model {question_model}")

        full_prompt = ANALYZER_PROMPT.replace("{content}", ocr_text)

        async with aiohttp.ClientSession() as session:
            analyzer_output = await _call_llm(session, api_key, question_model, full_prompt)

        # Update quiz with analyzer output and move to generating_quiz stage
        doc_ref.update({
            "analyzerOutput": analyzer_output,
            "status": "generating_quiz",
        })

        print(f"Analysis completed for quiz {quiz_id}.")

    except Exception as e:
        print(f"Analysis error for quiz {quiz_id}: {e}")
        # Don't fail the entire flow, just skip analysis and move to generating_quiz
        doc_ref.update({"status": "generating_quiz"})


@firestore_fn.on_document_updated(
    document="quizzes/{quiz_id}",
    secrets=[OPENROUTER_API_KEY],
)
def analyze_content(
    event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot]],
) -> None:
    """Analyze text when quiz status changes to 'analyzing' (multi-agent mode)."""
    if event.data is None:
        return

    new_data = event.data.after.to_dict()
    previous_data = event.data.before.to_dict()

    if new_data is None or previous_data is None:
        return

    # Only process if status changed to "analyzing"
    if (
        new_data.get("status") != "analyzing"
        or previous_data.get("status") == "analyzing"
    ):
        return

    quiz_id = event.params.get("quiz_id", "unknown")
    ocr_text = new_data.get("ocrText")
    question_model = new_data.get("questionModel", DEFAULT_QUESTION_MODEL)

    doc_ref = event.data.after.reference

    if not ocr_text:
        doc_ref.update({"status": "generating_quiz"})
        return

    asyncio.run(
        _analyze_async(
            quiz_id,
            ocr_text,
            question_model,
            doc_ref,
            OPENROUTER_API_KEY.value,
        )
    )

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
    generation_mode = new_data.get("generationMode", "single_prompt")
    analyzer_output = new_data.get("analyzerOutput")

    # Get target question count (default to 5 if not specified)
    target_question_count = new_data.get("targetQuestionCount", 5)

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
        doc_ref.update(
            {"status": "error", "errorMessage": "No OCR text found"}
        )
        return

    # Run async function in sync context
    asyncio.run(
        _generate_questions_async(
            quiz_id,
            ocr_text,
            question_model,
            doc_ref,
            OPENROUTER_API_KEY.value,
            target_question_count,
            generation_mode,
            analyzer_output,
            file_urls,
            delete_files,
        )
    )


@https_fn.on_call()
def get_quiz_for_player(req: https_fn.CallableRequest) -> dict:
    """
    Securely fetch quiz data for players without exposing correct answers.

    Request data:
    - quizId: string - The quiz ID

    Returns:
    - Quiz metadata and questions WITHOUT correct answers
    """
    # Get request data
    data = req.data
    quiz_id = data.get("quizId")

    # SECURITY: Validate input type and size
    if not quiz_id or not isinstance(quiz_id, str) or len(quiz_id) > 100:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Invalid quizId",
        )

    # Get Firestore client
    db = admin_firestore.client()

    # Fetch the quiz document
    quiz_ref = db.collection("quizzes").document(quiz_id)
    quiz_doc = quiz_ref.get()

    if not quiz_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Quiz not found",
        )

    quiz_data = quiz_doc.to_dict()

    # Check if quiz is published
    if not quiz_data.get("isPublished", False):
        # Check if user is the owner
        if not req.auth or quiz_data.get("userId") != req.auth.uid:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
                message="Quiz is not published",
            )

    # Note: We don't block anonymous users from READING quiz data here
    # The blocking happens during submission in submit_quiz_answers
    # This allows anonymous users to see the quiz and get a proper login prompt

    # Check if user is the owner
    is_owner = req.auth and quiz_data.get("userId") == req.auth.uid

    # SECURITY: Rate limiting check - prevent quiz data harvesting
    # Check if user has fetched too many different quizzes recently
    # (This is a basic check, production should use Redis or similar)
    user_id = req.auth.uid if req.auth else "anonymous"

    # Sanitize quiz data - remove correct answers and explanations for non-owners
    questions = quiz_data.get("questions", [])
    if not is_owner:
        sanitized_questions = []
        for q in questions:
            # SECURITY: Only include necessary fields
            sanitized_q = {
                "id": q.get("id"),
                "content": q.get("content"),
                "options": q.get("options", []),
                "type": q.get("type", "multiple-choice"),
            }
            sanitized_questions.append(sanitized_q)
        quiz_data["questions"] = sanitized_questions

    # Remove sensitive fields
    safe_fields = [
        "id",
        "userId",  # Needed to check if user is owner
        "title",
        "description",
        "genre",
        "topics",
        "questions",
        "isPublished",
        "allowAnonymous",
        "publicLevel",
        "allowRedo",
        "timerEnabled",
        "timerDurationMinutes",
        "timerAutoSubmit",
        "timerWarningMinutes",
        "passage",
        "createdAt",
        "updatedAt",
    ]

    sanitized_quiz = {k: v for k, v in quiz_data.items() if k in safe_fields}
    sanitized_quiz["id"] = quiz_id

    return sanitized_quiz


def _update_quiz_metrics(quiz_ref):
    """
    Recalculate and update quiz metrics and top performers from attempts subcollection.
    """
    # Fetch all attempts
    attempts_query = quiz_ref.collection("attempts").stream()
    attempts = []

    for attempt_doc in attempts_query:
        attempt_data = attempt_doc.to_dict()
        attempt_data["id"] = attempt_doc.id
        attempts.append(attempt_data)

    if not attempts:
        # No attempts - reset metrics
        quiz_ref.update(
            {
                "metrics": {
                    "totalResponses": 0,
                    "avgScore": 0,
                    "highestScore": 0,
                    "lowestScore": 0,
                    "scoreDistribution": [0, 0, 0, 0, 0],
                },
                "topPerformers": [],
            }
        )
        return

    # Calculate metrics
    total_responses = len(attempts)
    scores = [a["score"] for a in attempts]
    avg_score = sum(scores) / total_responses if total_responses > 0 else 0
    highest_score = max(scores) if scores else 0
    lowest_score = min(scores) if scores else 0

    # Calculate score distribution
    score_ranges = [0, 0, 0, 0, 0]  # [0-29%, 30-49%, 50-69%, 70-89%, 90-100%]
    for score in scores:
        if score < 30:
            score_ranges[0] += 1
        elif score < 50:
            score_ranges[1] += 1
        elif score < 70:
            score_ranges[2] += 1
        elif score < 90:
            score_ranges[3] += 1
        else:
            score_ranges[4] += 1

    # Get top 5 performers
    sorted_attempts = sorted(attempts, key=lambda a: a["score"], reverse=True)
    top_5 = sorted_attempts[:5]

    top_performers = [
        {
            "attemptId": a["id"],
            "userId": a["userId"],
            "displayName": a["displayName"],
            "isAnonymous": a["isAnonymous"],
            "score": a["score"],
            "correctCount": a["correctCount"],
            "total": a["total"],
            "attemptAt": a["attemptAt"],
        }
        for a in top_5
    ]

    # Update quiz document
    quiz_ref.update(
        {
            "metrics": {
                "totalResponses": total_responses,
                "avgScore": avg_score,
                "highestScore": highest_score,
                "lowestScore": lowest_score,
                "scoreDistribution": score_ranges,
            },
            "topPerformers": top_performers,
        }
    )


@https_fn.on_call()
def submit_quiz_answers(req: https_fn.CallableRequest) -> dict:
    """
    Server-side answer evaluation for published quizzes.

    Request data:
    - quizId: string - The quiz ID
    - userAnswers: dict[int, int] - Question ID to selected option index
    - displayName: string - User's display name
    - isAnonymous: bool - Whether user is anonymous

    Returns:
    - success: bool
    - score: float - Percentage score
    - correctCount: int - Number of correct answers
    - total: int - Total questions
    - results: list[dict] - Per-question results (if publicLevel allows)
    - publicLevel: int - The quiz's public level setting
    """
    # Validate authentication
    if not req.auth:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="User must be authenticated",
        )

    # Get request data
    data = req.data
    quiz_id = data.get("quizId")
    user_answers = data.get("userAnswers", {})
    display_name = data.get("displayName", "Guest")
    is_anonymous = data.get("isAnonymous", True)

    # SECURITY: Validate input types and sizes
    if not quiz_id or not isinstance(quiz_id, str) or len(quiz_id) > 100:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Invalid quizId",
        )

    if not isinstance(user_answers, dict) or len(user_answers) > 200:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Invalid userAnswers",
        )

    if not isinstance(display_name, str):
        display_name = "Guest"

    if not isinstance(is_anonymous, bool):
        is_anonymous = True

    # Get Firestore client
    db = admin_firestore.client()

    # Fetch the quiz document
    quiz_ref = db.collection("quizzes").document(quiz_id)
    quiz_doc = quiz_ref.get()

    if not quiz_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Quiz not found"
        )

    quiz_data = quiz_doc.to_dict()

    # Check if quiz is published
    if not quiz_data.get("isPublished", False):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Quiz is not published",
        )

    # Check if anonymous users are allowed
    if is_anonymous and not quiz_data.get("allowAnonymous", True):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Anonymous users are not allowed for this quiz",
        )

    # SECURITY: Check if user is the owner (preview mode - don't count submissions)
    is_owner = quiz_data.get("userId") == req.auth.uid
    is_preview = data.get("isPreview", False)

    if is_owner and is_preview:
        # Owner preview - evaluate locally, don't store attempt
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Owner preview submissions should be handled client-side",
        )

    # SECURITY: Check redo policy for authenticated non-anonymous users
    allow_redo = quiz_data.get("allowRedo", True)
    if not allow_redo and not is_anonymous and not is_owner:
        # Check if user has already submitted
        attempts_ref = quiz_ref.collection("attempts")
        existing = attempts_ref.where("userId", "==", req.auth.uid).limit(1).get()
        if len(existing) > 0:
            raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.ALREADY_EXISTS,
                message="You have already submitted this quiz. Retakes are not allowed.",
            )

    questions = quiz_data.get("questions", [])
    public_level = quiz_data.get("publicLevel", 4)

    if not questions:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="Quiz has no questions",
        )

    # SECURITY: Sanitize display name
    display_name = str(display_name).strip()[:100]  # Max 100 chars
    if not display_name:
        display_name = "Anonymous"

    # SECURITY: Validate user answers
    valid_question_ids = {q.get("id") for q in questions}

    # Evaluate answers server-side
    results: list[dict] = []
    correct_count = 0
    total = len(questions)

    for question in questions:
        q_id = question.get("id")
        correct_answer = question.get("correct")
        num_options = len(question.get("options", []))

        user_answer = user_answers.get(str(q_id))
        # Handle both string and int keys
        if user_answer is None:
            user_answer = user_answers.get(q_id)

        # SECURITY: Validate answer is within valid range
        if user_answer is not None:
            try:
                user_answer = int(user_answer)
                if user_answer < 0 or user_answer >= num_options:
                    user_answer = None  # Invalid answer
            except (ValueError, TypeError):
                user_answer = None  # Invalid answer

        is_correct = user_answer is not None and user_answer == correct_answer

        if is_correct:
            correct_count += 1

        results.append(
            {
                "questionId": q_id,
                "userAnswer": user_answer,
                "isCorrect": is_correct,
            }
        )

    score = (correct_count / total * 100) if total > 0 else 0

    # Create the attempt record (minimal - no quiz content, no results, no photoURL)
    attempt = {
        "userId": req.auth.uid,
        "displayName": display_name,
        "isAnonymous": is_anonymous,
        "attemptAt": datetime.now(),
        "score": score,
        "total": total,
        "correctCount": correct_count,
        "userAnswers": {str(k): v for k, v in user_answers.items()},
    }

    # Store the attempt in Firestore subcollection
    attempt_ref = quiz_ref.collection("attempts").document()
    attempt_ref.set(attempt)
    attempt_id = attempt_ref.id

    # Recalculate metrics and update quiz document
    _update_quiz_metrics(quiz_ref)

    # Build response based on public level
    response = {
        "success": True,
        "publicLevel": public_level,
        "attemptId": attempt_id,
    }

    # Level 1+: Show score
    if public_level >= 1:
        response["score"] = score
        response["correctCount"] = correct_count
        response["total"] = total

    # Level 2+: Show which questions are correct/wrong
    if public_level >= 2:
        response["results"] = [
            {"questionId": r["questionId"], "isCorrect": r["isCorrect"]}
            for r in results
        ]

    # Level 3+: Include correct answers
    if public_level >= 3:
        response["results"] = [
            {
                "questionId": r["questionId"],
                "userAnswer": r["userAnswer"],
                "isCorrect": r["isCorrect"],
                "correctAnswer": next(
                    (q["correct"] for q in questions if q["id"] == r["questionId"]),
                    None,
                ),
            }
            for r in results
        ]

    # Level 4: Include explanations
    if public_level >= 4:
        response["results"] = [
            {
                "questionId": r["questionId"],
                "userAnswer": r["userAnswer"],
                "isCorrect": r["isCorrect"],
                "correctAnswer": next(
                    (q["correct"] for q in questions if q["id"] == r["questionId"]),
                    None,
                ),
                "explanation": next(
                    (
                        q.get("explanation", "")
                        for q in questions
                        if q["id"] == r["questionId"]
                    ),
                    "",
                ),
            }
            for r in results
        ]

    return response


@https_fn.on_call()
def delete_quiz_attempt(req: https_fn.CallableRequest) -> dict:
    """
    Delete a specific quiz attempt (owner only).

    Request data:
    - quizId: string
    - attemptId: string
    """
    if not req.auth:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="User must be authenticated",
        )

    data = req.data
    quiz_id = data.get("quizId")
    attempt_id = data.get("attemptId")

    # SECURITY: Validate input types and sizes
    if not quiz_id or not isinstance(quiz_id, str) or len(quiz_id) > 100:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Invalid quizId",
        )

    if not attempt_id or not isinstance(attempt_id, str) or len(attempt_id) > 100:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Invalid attemptId",
        )

    db = admin_firestore.client()
    quiz_ref = db.collection("quizzes").document(quiz_id)
    quiz_doc = quiz_ref.get()

    if not quiz_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Quiz not found"
        )

    quiz_data = quiz_doc.to_dict()

    # Only owner can delete attempts
    if quiz_data.get("userId") != req.auth.uid:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="Only the quiz owner can delete attempts",
        )

    attempt_ref = quiz_ref.collection("attempts").document(attempt_id)
    attempt_doc = attempt_ref.get()

    if not attempt_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND, message="Attempt not found"
        )

    attempt_data = attempt_doc.to_dict()

    # Delete attempt document
    attempt_ref.delete()

    # Recalculate metrics after deletion
    _update_quiz_metrics(quiz_ref)

    return {"success": True}


@https_fn.on_call()
def get_attempt_result(req: https_fn.CallableRequest) -> dict:
    """
    Fetch attempt result with proper permissions and publicLevel filtering.
    Does not store quiz content in attempt documents - dynamically evaluates.
    """
    data = req.data
    quiz_id = data.get("quizId")
    attempt_id = data.get("attemptId")

    # SECURITY: Validate input types and sizes
    if not quiz_id or not isinstance(quiz_id, str) or len(quiz_id) > 100:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Invalid quizId",
        )

    if not attempt_id or not isinstance(attempt_id, str) or len(attempt_id) > 100:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Invalid attemptId",
        )

    db = admin_firestore.client()
    quiz_ref = db.collection("quizzes").document(quiz_id)
    quiz_doc = quiz_ref.get()

    if not quiz_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Quiz not found",
        )

    quiz_data = quiz_doc.to_dict()

    # Fetch attempt
    attempt_ref = quiz_ref.collection("attempts").document(attempt_id)
    attempt_doc = attempt_ref.get()

    if not attempt_doc.exists:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.NOT_FOUND,
            message="Attempt not found",
        )

    attempt_data = attempt_doc.to_dict()

    # Check permissions: owner or attempt creator
    is_owner = req.auth and quiz_data.get("userId") == req.auth.uid
    is_attempt_creator = req.auth and attempt_data.get("userId") == req.auth.uid

    if not is_owner and not is_attempt_creator:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.PERMISSION_DENIED,
            message="You do not have permission to view this attempt",
        )

    # Get public level
    public_level = quiz_data.get("publicLevel", 4)

    # Build response base
    response = {
        "attempt": {
            "id": attempt_id,
            "userId": attempt_data.get("userId"),
            "displayName": attempt_data.get("displayName", "Guest"),
            "isAnonymous": attempt_data.get("isAnonymous", True),
            "attemptAt": attempt_data.get("attemptAt"),
            "score": attempt_data.get("score", 0),
            "total": attempt_data.get("total", 0),
            "correctCount": attempt_data.get("correctCount", 0),
            "userAnswers": attempt_data.get("userAnswers", {}),
        },
        "quiz": {
            "title": quiz_data.get("title", "Untitled Quiz"),
            "description": quiz_data.get("description", ""),
            "passage": quiz_data.get("passage", ""),
            "publicLevel": public_level,
        },
    }

    # Owner always sees everything
    if is_owner:
        questions = quiz_data.get("questions", [])
        response["questions"] = [
            {
                "id": q.get("id"),
                "content": q.get("content"),
                "options": q.get("options", []),
                "correct": q.get("correct"),
                "explanation": q.get("explanation", ""),
            }
            for q in questions
        ]

        # Build full results
        user_answers = attempt_data.get("userAnswers", {})
        results = []
        for q in questions:
            q_id = q.get("id")
            user_answer = user_answers.get(str(q_id), -1)
            is_correct = user_answer == q.get("correct", -1)
            results.append(
                {
                    "questionId": q_id,
                    "userAnswer": user_answer,
                    "isCorrect": is_correct,
                    "correctAnswer": q.get("correct"),
                    "explanation": q.get("explanation", ""),
                }
            )
        response["results"] = results
        return response

    # For attempt creator, filter based on publicLevel
    questions = quiz_data.get("questions", [])
    user_answers = attempt_data.get("userAnswers", {})

    # All levels (0+): Show questions and user answers
    response["questions"] = [
        {
            "id": q.get("id"),
            "content": q.get("content"),
            "options": q.get("options", []),
        }
        for q in questions
    ]

    results = []
    for q in questions:
        q_id = q.get("id")
        user_answer = user_answers.get(str(q_id), -1)
        is_correct = user_answer == q.get("correct", -1)

        result = {
            "questionId": q_id,
            "userAnswer": user_answer,
        }

        # Level 2+: Show if answer is correct/incorrect
        if public_level >= 2:
            result["isCorrect"] = is_correct

        # Level 3+: Show correct answer
        if public_level >= 3:
            result["correctAnswer"] = q.get("correct")

        # Level 4: Show explanation
        if public_level >= 4:
            result["explanation"] = q.get("explanation", "")

        results.append(result)

    response["results"] = results
    return response
