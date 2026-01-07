"""
OCR API Script
Performs OCR on images using OpenRouter or Novita AI API
"""

import json
import argparse
import os
import re
import time
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm
import base64
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv()

# API Configuration
API_PROVIDERS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "novitaai": {
        "base_url": "https://api.novita.ai/openai",
        "api_key_env": "NOVITAAI_API_KEY",
    },
}

# Models that require specific API providers
PROVIDER_SPECIFIC_MODELS = {
    "paddlepaddle/paddleocr-vl": {
        "provider": "novitaai",
        "prompt": "OCR:",
    },
}

# Default prompt file
DEFAULT_PROMPT_FILE = "prompts/ocr.md"


def load_json(file_path: str) -> List[Dict]:
    """Load JSON file"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt_from_file(file_path: str = DEFAULT_PROMPT_FILE) -> str:
    """Load OCR prompt from file"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"⚠️  Warning: Prompt file not found at {file_path}, using default prompt")
        return "Extract all text from this image."


def get_provider_for_model(model: str) -> str:
    """
    Determine which API provider to use for a given model.

    Args:
        model: Model name

    Returns:
        Provider name ('openrouter' or 'novitaai')
    """
    if model in PROVIDER_SPECIFIC_MODELS:
        return PROVIDER_SPECIFIC_MODELS[model]["provider"]
    return "openrouter"  # Default provider


def get_prompt_for_model(model: str, custom_prompt: str = None) -> str:
    """
    Get the appropriate prompt for a model.

    Args:
        model: Model name
        custom_prompt: Custom prompt to use (overrides default)

    Returns:
        Prompt string
    """
    if custom_prompt:
        return custom_prompt

    # Check if model has a specific prompt
    if (
        model in PROVIDER_SPECIFIC_MODELS
        and "prompt" in PROVIDER_SPECIFIC_MODELS[model]
    ):
        return PROVIDER_SPECIFIC_MODELS[model]["prompt"]

    # Load from default prompt file
    return load_prompt_from_file()


def get_api_client(provider: str) -> OpenAI:
    """
    Create OpenAI client for the specified provider.

    Args:
        provider: API provider name ('openrouter' or 'novitaai')

    Returns:
        Configured OpenAI client

    Raises:
        ValueError: If API key is not found
    """
    if provider not in API_PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider}. Supported: {list(API_PROVIDERS.keys())}"
        )

    provider_config = API_PROVIDERS[provider]
    api_key = os.getenv(provider_config["api_key_env"])

    if not api_key:
        raise ValueError(
            f"{provider_config['api_key_env']} environment variable not set for provider '{provider}'"
        )

    return OpenAI(api_key=api_key, base_url=provider_config["base_url"])


def normalize_model_name(model: str) -> str:
    """
    Normalize model name to match directory naming convention.
    Replaces '/' with '_'

    Example: 'deepseek/deepseek-ocr' -> 'deepseek_deepseek-ocr'
    """
    return model.replace("/", "_")


def encode_image_to_base64(image_path: str) -> str:
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def perform_ocr(
    client: OpenAI, model: str, image_path: str, prompt: str, max_retries: int = 5
) -> str:
    """
    Perform OCR on an image using Novita AI API with retry logic for rate limiting.

    Args:
        client: OpenAI client configured with Novita API
        model: Model name
        image_path: Path to image file
        prompt: OCR prompt
        max_retries: Maximum number of retries for 429 errors

    Returns:
        Extracted text from image
    """
    retry_count = 0

    while retry_count <= max_retries:
        try:
            # Encode image
            base64_image = encode_image_to_base64(image_path)

            # Call API
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=4096,
                # temperature=0,
            )

            # Extract text from response
            extracted_text = response.choices[0].message.content

            return extracted_text

        except Exception as e:
            error_message = str(e)

            # Check if it's a 429 rate limit error
            if "429" in error_message or "rate_limit" in error_message.lower():
                retry_count += 1
                if retry_count <= max_retries:
                    tqdm.write(
                        f"\n⚠️  Rate limit hit (429) for {image_path}. Retrying in 10 seconds... (Attempt {retry_count}/{max_retries})"
                    )
                    time.sleep(10)
                    continue
                else:
                    tqdm.write(
                        f"\n❌ Max retries reached for {image_path} after {max_retries} attempts"
                    )
                    return ""
            else:
                # For non-429 errors, don't retry
                tqdm.write(f"\n❌ Error performing OCR on {image_path}: {e}")
                return ""

    return ""


def process_single_job(
    client: OpenAI,
    model: str,
    prompt: str,
    image_path: Path,
    sample_id: int,
    base_dir: Path,
):
    """
    Process a single OCR job.

    Args:
        client: OpenAI client
        model: Model name
        prompt: OCR prompt
        image_path: Path to image file
        sample_id: Sample ID
        base_dir: Base directory for relative path calculation

    Returns:
        Tuple of (sample_id, result_dict or None)
    """
    try:
        extracted_text = perform_ocr(client, model, str(image_path), prompt)

        print(extracted_text)

        if extracted_text:
            return (
                sample_id,
                {
                    "id": sample_id,
                    "predicted_text": extracted_text,
                },
            )
        else:
            return (sample_id, {"id": sample_id, "predicted_text": ""})

    except Exception as e:
        tqdm.write(f"\n❌ Error processing ID {sample_id}: {e}")
        return (sample_id, {"id": sample_id, "predicted_text": ""})


def find_image_path(
    base_dir: Path, source_name: str, sample_id: int, image_type: str = "augmented"
) -> Path:
    """
    Find image path for a given sample ID.
    Images are stored with 4-digit leading zeros (e.g., 0001.png, 0042.png)

    Args:
        base_dir: Base directory containing images
        source_name: Name of the source (e.g., 'race', 'dream')
        sample_id: Sample ID
        image_type: Type of images ('clean' or 'augmented')

    Returns:
        Path to image file, or None if not found
    """
    # Format ID with 4-digit leading zeros
    image_filename = f"{sample_id:04d}.png"

    # Construct path based on image_type
    image_path = base_dir / source_name / "images" / image_type / image_filename

    if image_path.exists():
        return image_path

    # Try jpg extension
    image_path_jpg = image_path.with_suffix(".jpg")
    if image_path_jpg.exists():
        return image_path_jpg

    return None


def process_source(
    client: OpenAI,
    model: str,
    prompt: str,
    source_data: List[Dict],
    source_name: str,
    base_dir: Path,
    image_type: str = "augmented",
    workers: int = 5,
) -> List[Dict]:
    """
    Process all samples for a specific source with parallel workers.

    Args:
        client: OpenAI client
        model: Model name
        prompt: OCR prompt
        source_data: List of data items for this source
        source_name: Name of the source
        base_dir: Base directory
        image_type: Type of images to process ('clean' or 'augmented')
        workers: Number of parallel workers

    Returns:
        List of prediction results
    """
    print(f"\n📦 Processing {source_name}: {len(source_data)} samples")
    print(f"📂 Image type: {image_type}")
    print(f"⚙️  Using {workers} parallel workers")

    # Prepare jobs
    jobs = []
    for item in source_data:
        sample_id = item["id"]

        # Find image path based on sample ID with 4-digit leading zeros
        image_path = find_image_path(
            base_dir, source_name.lower(), sample_id, image_type
        )

        if image_path is None or not image_path.exists():
            tqdm.write(
                f"\n⚠️  Image not found for ID {sample_id} ({sample_id:04d}.png) in {image_type}, skipping..."
            )
            jobs.append((sample_id, None))  # Will be handled as empty prediction
        else:
            jobs.append((sample_id, image_path))

    # Process jobs in parallel
    predictions = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submit all jobs
        future_to_job = {}
        for sample_id, image_path in jobs:
            if image_path is None:
                # Add empty prediction for missing images
                predictions.append({"id": sample_id, "predicted_text": ""})
            else:
                future = executor.submit(
                    process_single_job,
                    client,
                    model,
                    prompt,
                    image_path,
                    sample_id,
                    base_dir,
                )
                future_to_job[future] = (sample_id, image_path)

        # Process completed jobs with progress bar
        with tqdm(
            total=len(future_to_job), desc=f"🔍 OCR {source_name}", unit="img"
        ) as pbar:
            for future in as_completed(future_to_job):
                sample_id, image_path = future_to_job[future]
                _, result = future.result()

                if result is not None:
                    predictions.append(result)

                pbar.update(1)

    # Sort predictions by ID
    predictions.sort(key=lambda x: x["id"])

    return predictions


def main():
    parser = argparse.ArgumentParser(
        description="Perform OCR on images using OpenRouter or Novita AI API"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="./datasets/unified/data.json",
        help="Path to dataset JSON file",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model to use for OCR (e.g., 'google/gemini-2.0-flash-exp:free', 'paddlepaddle/paddleocr-vl')",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        required=True,
        help="Dataset source(s) to process (e.g., 'race', 'dream', 'logiqa')",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=list(API_PROVIDERS.keys()),
        default=None,
        help="API provider to use (default: auto-detect based on model, or 'openrouter')",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Custom OCR prompt (default: load from prompts/ocr.md or model-specific prompt)",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default="outputs",
        help="Base directory for outputs (default: outputs)",
    )
    parser.add_argument(
        "--image-type",
        type=str,
        choices=["clean", "augmented"],
        default="clean",
        help="Type of images to process (default: clean)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=128,
        help="Number of parallel workers (default: 128)",
    )

    args = parser.parse_args()

    # Determine provider (auto-detect or use specified)
    provider = args.provider if args.provider else get_provider_for_model(args.model)

    # Get API client for the provider
    client = get_api_client(provider)

    # Get prompt for model
    prompt = get_prompt_for_model(args.model, args.prompt)
    model_id = normalize_model_name(args.model)
    base_dir = Path(args.base_dir)

    print("=" * 100)
    print("OCR API - MULTI-PROVIDER")
    print("=" * 100)
    print(f"🤖 Model: {args.model}")
    print(f"🌐 Provider: {provider.upper()}")
    print(f"📝 Model ID (normalized): {model_id}")
    print(
        f"💬 Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"💬 Prompt: {prompt}"
    )
    print(f"📊 Sources to process: {', '.join(args.sources)}")
    print(f"📂 Image type: {args.image_type}")
    print(f"⚙️  Workers: {args.workers}")

    # Load dataset
    print(f"\nLoading dataset from {args.dataset}...")
    data = load_json(args.dataset)

    # Filter by sources
    sources_lower = [s.lower() for s in args.sources]
    data = [item for item in data if item.get("source", "").lower() in sources_lower]

    if not data:
        raise ValueError(f"No data found for sources: {', '.join(args.sources)}")

    print(f"Loaded {len(data)} samples")

    # Process each source separately
    for source in args.sources:
        source_lower = source.lower()
        print(f"\n{'='*100}")
        print(f"Processing source: {source.upper()}")
        print(f"{'='*100}")

        # Filter data for this source
        source_data = [
            item for item in data if item.get("source", "").lower() == source_lower
        ]

        if not source_data:
            print(f"⚠️  Warning: No data for source {source}, skipping...")
            continue

        # Prepare output directory
        output_dir = base_dir / source_lower / model_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Process samples with parallel workers
        predictions = process_source(
            client=client,
            model=args.model,
            prompt=prompt,
            source_data=source_data,
            source_name=source,
            base_dir=base_dir,
            image_type=args.image_type,
            workers=args.workers,
        )

        if not predictions:
            print(f"⚠️  No predictions generated for {source}")
            continue

        # Save predictions
        output_path = output_dir / "ocr_predictions.json"
        print(f"\n💾 Saving predictions to {output_path}...")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(predictions, f, indent=2, ensure_ascii=False)

        print(f"✅ Saved {len(predictions)} predictions for {source}")

    print("\n" + "=" * 100)
    print("✅ ALL OCR PROCESSING COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
