"""
OCR Script using OpenRouter API
Performs OCR on augmented images and saves predictions.
"""

import json
import base64
import argparse
from pathlib import Path
from tqdm import tqdm
import requests
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()


class OCRProcessor:
    """
    OCR processor using OpenRouter API to extract text from images.
    """

    def __init__(
        self,
        model="google/gemini-2.0-flash-exp:free",
        api_key=None,
        base_dir="outputs",
    ):
        """
        Initialize OCR processor.

        Args:
            model: Model name to use on OpenRouter
            api_key: OpenRouter API key (if None, will read from OPENROUTER_API_KEY env var)
            base_dir: Base directory containing the images
        """
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key not found. Set OPENROUTER_API_KEY environment variable or pass api_key parameter."
            )

        self.base_dir = Path(base_dir)
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

        # Load OCR prompt
        prompt_path = Path("prompts/ocr.md")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read().strip()

        print(f"🤖 Model: {self.model}")
        print(f"📂 Base directory: {self.base_dir}")

    def encode_image_to_base64(self, image_path):
        """
        Encode image file to base64 string.

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded string with data URL prefix
        """
        with open(image_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("utf-8")
            # Detect image format from extension
            ext = image_path.suffix.lower()
            mime_type = "image/png" if ext == ".png" else "image/jpeg"
            return f"data:{mime_type};base64,{encoded}"

    def ocr_single_image(self, image_path):
        """
        Perform OCR on a single image.

        Args:
            image_path: Path to image file

        Returns:
            Extracted text or None if failed
        """
        try:
            # Encode image
            base64_image = self.encode_image_to_base64(image_path)

            # Prepare API request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": base64_image}}
                        ],
                    },
                ],
            }

            # Make API request
            response = requests.post(
                self.api_url, headers=headers, json=payload, timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                text = result["choices"][0]["message"]["content"].strip()
                return text
            else:
                print(f"\n❌ API Error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            print(f"\n❌ Error processing {image_path.name}: {e}")
            return None

    def process_single_job(self, image_path, image_id):
        """
        Process a single OCR job.

        Args:
            image_path: Path to image file
            image_id: ID extracted from filename

        Returns:
            Tuple of (image_id, result_dict or None)
        """
        try:
            extracted_text = self.ocr_single_image(image_path)

            print(extracted_text)

            if extracted_text is not None:
                return (
                    image_id,
                    {
                        "id": image_id,
                        "image_path": str(image_path.relative_to(self.base_dir)),
                        "extracted_text": extracted_text,
                    },
                )
            else:
                return (image_id, None)

        except Exception as e:
            tqdm.write(f"\n❌ Error processing {image_path.name}: {e}")
            return (image_id, None)

    def process_source(self, source_name, image_type="augmented", workers=5):
        """
        Process all images for a specific source.

        Args:
            source_name: Name of the dataset source (e.g., 'race', 'dream')
            image_type: Type of images to process ('clean' or 'augmented')
            workers: Number of parallel workers

        Returns:
            List of prediction results
        """
        # Find images
        image_dir = self.base_dir / source_name / "images" / image_type

        if not image_dir.exists():
            print(f"⚠️  Image directory not found: {image_dir}")
            return []

        image_files = sorted(
            list(image_dir.glob("*.png")) + list(image_dir.glob("*.jpg"))
        )

        if not image_files:
            print(f"⚠️  No images found in: {image_dir}")
            return []

        print(f"\n📦 Processing {source_name}: {len(image_files)} images")
        print(f"📂 Image directory: {image_dir}")
        print(f"⚙️  Using {workers} parallel workers")

        # Prepare jobs
        jobs = []
        for img_path in image_files:
            # Extract ID from filename (e.g., "0001.png" -> 1)
            try:
                image_id = int(img_path.stem)
                jobs.append((img_path, image_id))
            except ValueError:
                tqdm.write(f"\n⚠️  Cannot extract ID from filename: {img_path.name}")
                continue

        # Process jobs in parallel
        predictions = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all jobs
            future_to_job = {
                executor.submit(self.process_single_job, img_path, img_id): (
                    img_path,
                    img_id,
                )
                for img_path, img_id in jobs
            }

            # Process completed jobs with progress bar
            with tqdm(
                total=len(jobs), desc=f"🔍 OCR {source_name}", unit="img"
            ) as pbar:
                for future in as_completed(future_to_job):
                    img_path, img_id = future_to_job[future]
                    image_id, result = future.result()

                    if result is not None:
                        predictions.append(result)

                    pbar.update(1)

        return predictions

    def run(self, sources=None, image_type="augmented", workers=5):
        """
        Run OCR on specified sources.

        Args:
            sources: List of source names to process. If None, process all sources.
            image_type: Type of images to process ('clean' or 'augmented')
            workers: Number of parallel workers
        """
        # Find all sources if not specified
        if sources is None:
            sources = [d.name for d in self.base_dir.iterdir() if d.is_dir()]

        if not sources:
            print("⚠️  No sources found")
            return

        print(f"📊 Sources to process: {sources}")

        # Process each source
        for source in sources:
            source_dir = self.base_dir / source
            if not source_dir.exists():
                print(f"⚠️  Source directory not found: {source_dir}")
                continue

            # Process images
            predictions = self.process_source(source, image_type, workers)

            if not predictions:
                print(f"⚠️  No predictions generated for {source}")
                continue

            # Save predictions
            output_dir = self.base_dir / source / self.model.replace("/", "_")
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = output_dir / "ocr_predictions.json"

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(predictions, f, indent=2, ensure_ascii=False)

            print(f"✅ Saved {len(predictions)} predictions to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Perform OCR on images using OpenRouter API"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default="outputs",
        help="Base directory containing images (default: outputs)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="List of dataset sources to process (e.g., race dream logiqa reclor). If not specified, all sources will be processed.",
    )
    parser.add_argument(
        "--image-type",
        type=str,
        choices=["clean", "augmented"],
        default="augmented",
        help="Type of images to process (default: augmented)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="google/gemini-2.0-flash-exp:free",
        help="Model to use on OpenRouter (default: google/gemini-2.0-flash-exp:free)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenRouter API key (default: read from OPENROUTER_API_KEY env var)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=128,
        help="Number of parallel workers (default: 5)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("OCR PROCESSING")
    print("=" * 70)

    # Initialize processor
    processor = OCRProcessor(
        model=args.model,
        api_key=args.api_key,
        base_dir=args.base_dir,
    )

    # Run OCR
    processor.run(
        sources=args.sources, image_type=args.image_type, workers=args.workers
    )

    print("\n" + "=" * 70)
    print("✅ OCR processing completed")
    print("=" * 70)


if __name__ == "__main__":
    main()
