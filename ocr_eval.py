"""
OCR Evaluation Script
Evaluates OCR predictions using CER (Character Error Rate) and WER (Word Error Rate)
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm
from tabulate import tabulate
import numpy as np

# Import jiwer for CER and WER computation
from jiwer import wer, cer


def load_json(file_path: str) -> List[Dict]:
    """Load JSON file"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_model_name(model: str) -> str:
    """
    Normalize model name to match directory naming convention.
    Replaces '/' with '_'

    Example: 'deepseek/deepseek-ocr' -> 'deepseek_deepseek-ocr'
    """
    return model.replace("/", "_")


def normalize_text(text: str) -> str:
    """
    Normalize text by removing extra whitespace, newlines, and other irrelevant characters.

    Args:
        text: Input text to normalize

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Replace newlines, tabs, and multiple spaces with single space
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Replace multiple spaces with single space
    text = " ".join(text.split())

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def get_ground_truth_text(data: List[Dict], sample_id: int) -> str:
    """Get ground truth content text for a given sample ID"""
    for item in data:
        if item["id"] == sample_id:
            return item.get("content", "")
    return ""


def compute_ocr_metrics(gt_text: str, pred_text: str) -> Dict[str, float]:
    """
    Compute OCR metrics: CER and WER
    Normalizes both texts before computing metrics.

    Args:
        gt_text: Ground truth text
        pred_text: OCR predicted text

    Returns:
        Dictionary with CER and WER scores
    """
    # Normalize both texts
    gt_text_norm = normalize_text(gt_text)
    pred_text_norm = normalize_text(pred_text)

    # Handle empty texts
    if not gt_text_norm or not pred_text_norm:
        return {
            "cer": 1.0 if gt_text_norm != pred_text_norm else 0.0,
            "wer": 1.0 if gt_text_norm != pred_text_norm else 0.0,
        }

    # Compute metrics
    try:
        cer_score = cer(gt_text_norm, pred_text_norm)
        wer_score = wer(gt_text_norm, pred_text_norm)
    except Exception as e:
        print(f"Warning: Error computing metrics: {e}")
        cer_score = 1.0
        wer_score = 1.0

    return {
        "cer": cer_score,
        "wer": wer_score,
    }


def evaluate_sample(
    sample_id: int,
    gt_text: str,
    pred_text: str,
) -> Dict:
    """
    Evaluate a single sample

    Args:
        sample_id: Sample ID
        gt_text: Ground truth text
        pred_text: OCR predicted text

    Returns:
        Dictionary with evaluation results, or None if should be skipped
    """
    if not gt_text:
        return {
            "id": sample_id,
            "error": "Missing ground truth text",
        }

    # Skip sample if prediction is None or empty
    if pred_text is None or not pred_text or not pred_text.strip():
        return {
            "id": sample_id,
            "skipped": True,
            "reason": "Empty or missing predicted text",
        }

    # Normalize texts for metrics computation
    gt_text_norm = normalize_text(gt_text)
    pred_text_norm = normalize_text(pred_text)

    # Compute metrics (normalization happens inside compute_ocr_metrics too)
    metrics = compute_ocr_metrics(gt_text, pred_text)

    return {
        "id": sample_id,
        "gt_length": len(gt_text_norm),
        "pred_length": len(pred_text_norm),
        "gt_word_count": len(gt_text_norm.split()),
        "pred_word_count": len(pred_text_norm.split()),
        "metrics": metrics,
    }


def compute_source_metrics(results: List[Dict]) -> Dict:
    """
    Compute aggregate metrics across all samples
    Excludes samples with errors or that were skipped

    Args:
        results: List of evaluation results per sample

    Returns:
        Dictionary with aggregated metrics
    """
    # Filter out samples with errors or that were skipped
    valid_results = [r for r in results if "error" not in r and "skipped" not in r]

    # Count skipped samples for reporting
    skipped_count = len([r for r in results if "skipped" in r])
    error_count = len([r for r in results if "error" in r])

    if not valid_results:
        return {
            "n_samples": 0,
            "n_skipped": skipped_count,
            "n_errors": error_count,
            "avg_cer": 0.0,
            "avg_wer": 0.0,
            "total_gt_chars": 0,
            "total_pred_chars": 0,
            "total_gt_words": 0,
            "total_pred_words": 0,
        }

    # Collect all CER and WER scores
    all_cer = [r["metrics"]["cer"] for r in valid_results]
    all_wer = [r["metrics"]["wer"] for r in valid_results]

    # Collect text statistics
    total_gt_chars = sum(r["gt_length"] for r in valid_results)
    total_pred_chars = sum(r["pred_length"] for r in valid_results)
    total_gt_words = sum(r["gt_word_count"] for r in valid_results)
    total_pred_words = sum(r["pred_word_count"] for r in valid_results)

    return {
        "n_samples": len(valid_results),
        "n_skipped": skipped_count,
        "n_errors": error_count,
        "avg_cer": np.mean(all_cer),
        "std_cer": np.std(all_cer),
        "min_cer": np.min(all_cer),
        "max_cer": np.max(all_cer),
        "avg_wer": np.mean(all_wer),
        "std_wer": np.std(all_wer),
        "min_wer": np.min(all_wer),
        "max_wer": np.max(all_wer),
        "total_gt_chars": total_gt_chars,
        "total_pred_chars": total_pred_chars,
        "total_gt_words": total_gt_words,
        "total_pred_words": total_pred_words,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate OCR predictions using CER and WER"
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
        help="Model name (e.g., 'deepseek/deepseek-ocr', 'paddlepaddle/paddleocr-vl')",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        required=True,
        help="Dataset source(s) to evaluate (e.g., 'race', 'dream', 'logiqa')",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default="outputs",
        help="Base directory containing OCR predictions (default: outputs)",
    )

    args = parser.parse_args()

    # Normalize model name
    model_id = normalize_model_name(args.model)

    print("=" * 100)
    print("OCR EVALUATION")
    print("=" * 100)
    print(f"Model: {args.model}")
    print(f"Model ID (normalized): {model_id}")
    print(f"Evaluating sources: {', '.join(args.sources)}")

    # Load ground truth data
    print(f"\nLoading ground truth from {args.dataset}...")
    gt_data = load_json(args.dataset)

    # Filter GT data by sources
    sources_lower = [s.lower() for s in args.sources]
    gt_data = [
        item for item in gt_data if item.get("source", "").lower() in sources_lower
    ]

    if not gt_data:
        raise ValueError(
            f"No ground truth data found for sources: {', '.join(args.sources)}"
        )

    print(f"Loaded {len(gt_data)} ground truth samples")

    # Process each source separately
    for source in args.sources:
        source_lower = source.lower()
        print(f"\n{'='*100}")
        print(f"Processing source: {source.upper()}")
        print(f"{'='*100}")

        # Load OCR predictions for this source
        predictions_path = (
            Path(args.base_dir) / source_lower / model_id / "ocr_predictions.json"
        )

        if not predictions_path.exists():
            print(
                f"Warning: OCR predictions file not found at {predictions_path}, skipping..."
            )
            continue

        print(f"Loading predictions from {predictions_path}...")
        pred_data = load_json(str(predictions_path))

        # Filter GT for this source only
        source_gt_data = [
            item for item in gt_data if item.get("source", "").lower() == source_lower
        ]

        if not source_gt_data:
            print(f"Warning: No ground truth data for source {source}, skipping...")
            continue

        if not pred_data:
            print(f"Warning: No prediction data for source {source}, skipping...")
            continue

        # Create mapping of ID to prediction
        # Support both "predicted_text" and "extracted_text" keys
        pred_map = {}
        for item in pred_data:
            predicted_text = item.get("predicted_text") or item.get(
                "extracted_text", ""
            )
            pred_map[item["id"]] = predicted_text

        # Find common IDs
        gt_ids = {item["id"] for item in source_gt_data}
        pred_ids = set(pred_map.keys())
        common_ids = sorted(list(gt_ids & pred_ids))

        if not common_ids:
            print(
                f"Warning: No common samples between GT and predictions for {source}, skipping..."
            )
            continue

        print(f"Evaluating {len(common_ids)} common samples...")

        # Evaluate each sample
        results = []

        for sample_id in tqdm(common_ids, desc=f"Evaluating {source}"):
            # Get ground truth text
            gt_text = get_ground_truth_text(source_gt_data, sample_id)

            # Get predicted text
            pred_text = pred_map.get(sample_id, "")

            # Evaluate
            result = evaluate_sample(sample_id, gt_text, pred_text)
            results.append(result)

        # Compute aggregate metrics
        print(f"\nComputing aggregate metrics for {source}...")
        metrics = compute_source_metrics(results)

        # Print results
        print(f"\n### Source: {source.upper()} ###")
        print(f"  Total Samples Evaluated: {len(common_ids)}")
        print(f"  Valid Samples (used in metrics): {metrics['n_samples']}")
        if metrics["n_skipped"] > 0:
            print(f"  ⚠️  Skipped Samples (empty predictions): {metrics['n_skipped']}")
        if metrics["n_errors"] > 0:
            print(f"  ❌ Error Samples: {metrics['n_errors']}")
        print(f"  Total GT Characters: {metrics['total_gt_chars']:,}")
        print(f"  Total Pred Characters: {metrics['total_pred_chars']:,}")
        print(f"  Total GT Words: {metrics['total_gt_words']:,}")
        print(f"  Total Pred Words: {metrics['total_pred_words']:,}")

        # Create table
        table = [
            [
                "CER (Character Error Rate)",
                f"{metrics['avg_cer']:.4f}",
                f"±{metrics['std_cer']:.4f}",
                f"[{metrics['min_cer']:.4f}, {metrics['max_cer']:.4f}]",
                "Lower is better (0.0 = perfect)",
            ],
            [
                "WER (Word Error Rate)",
                f"{metrics['avg_wer']:.4f}",
                f"±{metrics['std_wer']:.4f}",
                f"[{metrics['min_wer']:.4f}, {metrics['max_wer']:.4f}]",
                "Lower is better (0.0 = perfect)",
            ],
        ]

        headers = ["Metric", "Mean", "Std Dev", "Range [Min, Max]", "Description"]
        print(tabulate(table, headers=headers, tablefmt="fancy_grid"))

        # Print Excel-friendly format (tab-separated for easy copy-paste)
        print(f"\n📊 Copy to Excel:")
        print("-" * 80)
        # Header row
        excel_header = "CER\tWER"
        print(excel_header)
        # Data row
        excel_data = f"{metrics['avg_cer']:.4f}\t{metrics['avg_wer']:.4f}"
        print(excel_data)
        print("-" * 80)

        # Calculate accuracy (inverse of error rate)
        cer_accuracy = max(0.0, 1.0 - metrics["avg_cer"]) * 100
        wer_accuracy = max(0.0, 1.0 - metrics["avg_wer"]) * 100
        print(f"\n📈 Accuracy Metrics:")
        print(f"  Character Accuracy: {cer_accuracy:.2f}%")
        print(f"  Word Accuracy: {wer_accuracy:.2f}%")

        # Save results
        output_dir = Path(args.base_dir) / source_lower / model_id
        output_dir.mkdir(parents=True, exist_ok=True)

        eval_output_path = output_dir / "ocr_eval_results.json"
        print(f"\nSaving evaluation results to {eval_output_path}...")

        output_data = {
            "source": source,
            "model": args.model,
            "model_id": model_id,
            "metrics": metrics,
            "detailed_results": results,
        }

        with open(eval_output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(
            f"✓ Evaluation complete for {source}! Results saved to {eval_output_path}"
        )

    print("\n" + "=" * 100)
    print("ALL EVALUATIONS COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
