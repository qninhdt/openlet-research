import json
import argparse
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Tuple
from tqdm import tqdm
from tabulate import tabulate
import re
import torch.nn.functional as F

# Thư viện cho Lexical Metrics
import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer

# Thư viện cho Semantic Metrics
from sentence_transformers import SentenceTransformer, util

# Tải data cho NLTK (chạy 1 lần)
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

# Optional MAUVE metric
try:
    import mauve

    HAVE_MAUVE = True
except Exception:
    HAVE_MAUVE = False

# Optional FBD metric
try:
    import sys
    from pathlib import Path

    # Add third_party/fbd to path
    fbd_path = Path(__file__).parent / "third_party" / "fbd"
    if str(fbd_path) not in sys.path:
        sys.path.insert(0, str(fbd_path))

    from fbd_score import calculate_fbd

    HAVE_FBD = True
except Exception as e:
    HAVE_FBD = False
    print(f"Warning: FBD not available: {e}")

# Optional BLEURT metric
try:
    from bleurt_pytorch import (
        BleurtConfig,
        BleurtForSequenceClassification,
        BleurtTokenizer,
    )

    HAVE_BLEURT = True
except Exception as e:
    HAVE_BLEURT = False
    print(f"Warning: BLEURT not available: {e}")


def load_json(file_path: str) -> List[Dict]:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_source_from_data(data: List[Dict], sample_id: int) -> str:
    """Get source for a given sample ID from the original data"""
    for item in data:
        if item["id"] == sample_id:
            return item.get("source", "unknown")
    return "unknown"


def extract_questions(data: List[Dict]) -> Dict[int, List[Dict]]:
    questions_by_id = {}
    for item in data:
        # Hỗ trợ cả 2 format key thường gặp
        q_list = item.get("questions", item.get("generated_questions", []))

        # Kiểm tra xem có phải format mới (k sets) không
        # Format mới: generated_questions là list of lists
        # Format cũ: generated_questions là list of dicts
        if q_list and isinstance(q_list[0], list):
            # Format mới với k sets - flatten tất cả questions từ các sets
            flattened = []
            for question_set in q_list:
                flattened.extend(question_set)
            questions_by_id[item["id"]] = flattened
        else:
            # Format cũ hoặc ground truth
            questions_by_id[item["id"]] = q_list
    return questions_by_id


def format_question_text(question: Dict) -> str:
    """
    Format lại:
    1. Chỉ lấy đáp án ĐÚNG (Correct Answer).
    2. Nếu câu hỏi có "_", điền đáp án đúng vào đó.
    3. Nếu không, nối đáp án đúng vào sau cùng.
    -> Biến câu hỏi thành một câu khẳng định hoàn chỉnh (Fact).
    """
    content = question.get("content", question.get("question", ""))
    options = question.get("options", [])
    correct_idx = question.get(
        "correct", None
    )  # Có thể là int (0-3) hoặc str ('A'-'D')

    # 1. Tìm text của đáp án đúng
    correct_text = ""

    # Trường hợp không có key 'correct' hoặc options rỗng -> Giữ nguyên content
    if correct_idx is None or not options:
        return content

    # Xử lý lấy index thực tế
    idx = -1
    if isinstance(correct_idx, int):
        idx = correct_idx
    elif isinstance(correct_idx, str):
        # Nếu là 'A', 'B', 'C', 'D' -> chuyển sang 0, 1, 2, 3
        if len(correct_idx) == 1:
            idx = ord(correct_idx.upper()) - 65

    # Lấy text nếu index hợp lệ
    if 0 <= idx < len(options):
        raw_opt = options[idx]
        # Clean prefix kiểu "A. ", "B. ", "[A]" bằng Regex cho sạch
        # Pattern: Bắt đầu bằng A-D, theo sau là ., ), ] hoặc khoảng trắng
        correct_text = re.sub(r"^\[?[A-D][\.\)\]]?\s+", "", raw_opt).strip()
    else:
        # Fallback nếu index sai (hiếm gặp)
        return content

    # 2. Thực hiện ghép câu (Statement Construction)
    if "_" in content:
        # Thay thế dấu gạch dưới đầu tiên tìm thấy
        return content.replace("_", correct_text, 1)
    else:
        # Nối vào đuôi (thường là câu hỏi Wh- question)
        # Thêm dấu cách nếu chưa có
        return f"{content} {correct_text}"


def extract_query_answer(question: Dict) -> Tuple[str, str]:
    """
    Extract query and answer for FBD metric.
    Query = question content
    Answer = correct answer text

    Returns: (query, answer)
    """
    content = question.get("content", question.get("question", ""))
    options = question.get("options", [])
    correct_idx = question.get("correct", None)

    # Default query is the content
    query = content
    answer = ""

    if correct_idx is None or not options:
        # No correct answer available, return empty answer
        return query, answer

    # Get correct answer index
    idx = -1
    if isinstance(correct_idx, int):
        idx = correct_idx
    elif isinstance(correct_idx, str):
        if len(correct_idx) == 1:
            idx = ord(correct_idx.upper()) - 65

    # Extract answer text
    if 0 <= idx < len(options):
        raw_opt = options[idx]
        # Clean prefix like "A. ", "B. ", "[A]"
        answer = re.sub(r"^\[?[A-D][\.\)\]]?\s+", "", raw_opt).strip()

    return query, answer
    if 0 <= idx < len(options):
        raw_opt = options[idx]
        # Clean prefix kiểu "A. ", "B. ", "[A]" bằng Regex cho sạch
        # Pattern: Bắt đầu bằng A-D, theo sau là ., ), ] hoặc khoảng trắng
        correct_text = re.sub(r"^\[?[A-D][\.\)\]]?\s+", "", raw_opt).strip()
    else:
        # Fallback nếu index sai (hiếm gặp)
        return content

    # 2. Thực hiện ghép câu (Statement Construction)
    if "_" in content:
        # Thay thế dấu gạch dưới đầu tiên tìm thấy
        return content.replace("_", correct_text, 1)
    else:
        # Nối vào đuôi (thường là câu hỏi Wh- question)
        # Thêm dấu cách nếu chưa có
        return f"{content} {correct_text}"


# ==========================================
# 1. LEXICAL METRICS (BLEU & ROUGE)
# ==========================================
def compute_lexical_recall(
    gt_texts: List[str], pred_texts: List[str]
) -> Tuple[List[Tuple[float, float, int]], float, float]:
    """
    Tính BLEU-4 và ROUGE-L.
    Strategy: Recall (Max Score). Với mỗi GT, tìm Pred khớp nhất.
    Returns: (list of (bleu, rouge, best_pred_idx), mean_bleu, mean_rouge)
    """
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    smooth_fn = SmoothingFunction().method1  # Smooth cho câu ngắn đỡ bị điểm 0

    # Tokenize sơ bộ cho BLEU
    gt_tokens_list = [nltk.word_tokenize(t.lower()) for t in gt_texts]
    pred_tokens_list = [nltk.word_tokenize(t.lower()) for t in pred_texts]

    detailed_scores = []

    # Duyệt từng câu Ground Truth
    for i, gt_toks in enumerate(gt_tokens_list):
        current_gt_text = gt_texts[i]

        max_b = 0.0
        max_r = 0.0
        best_pred_idx = -1

        # So khớp với TOÀN BỘ câu Pred để tìm câu giống nhất
        for j, pred_toks in enumerate(pred_tokens_list):
            # BLEU-4
            # weights=(0.25, 0.25, 0.25, 0.25) là mặc định cho BLEU-4
            b_score = sentence_bleu([gt_toks], pred_toks, smoothing_function=smooth_fn)

            # ROUGE-L
            r_score = scorer.score(current_gt_text, pred_texts[j])["rougeL"].fmeasure

            # Use combined score to find best match
            combined = (b_score + r_score) / 2
            if combined > (max_b + max_r) / 2:
                max_b = b_score
                max_r = r_score
                best_pred_idx = j

        detailed_scores.append((max_b, max_r, best_pred_idx))

    mean_bleu = np.mean([s[0] for s in detailed_scores])
    mean_rouge = np.mean([s[1] for s in detailed_scores])

    return detailed_scores, mean_bleu, mean_rouge


# ==========================================
# 2. FAST SEMANTIC (BI-ENCODER)
# ==========================================
def compute_bi_encoder_score(
    gt_texts: List[str], pred_texts: List[str], model: SentenceTransformer, device: str
) -> Tuple[List[Tuple[float, int]], float]:
    """
    Dùng Bi-Encoder + Cosine Similarity.
    Nhanh, dùng để đo độ tương đồng tổng quát.
    Returns: (list of (score, best_pred_idx), mean_score)
    """
    # Encode thành Vector
    gt_emb = model.encode(
        gt_texts, convert_to_tensor=True, device=device, show_progress_bar=False
    )
    pred_emb = model.encode(
        pred_texts, convert_to_tensor=True, device=device, show_progress_bar=False
    )

    # Tính ma trận Cosine Similarity [n_gt, n_pred]
    cos_scores = util.cos_sim(gt_emb, pred_emb)

    # Recall Strategy: Lấy max theo hàng (mỗi GT khớp với Pred tốt nhất)
    # values, indices = torch.max(input, dim)
    max_scores, max_indices = torch.max(cos_scores, dim=1)

    detailed_scores = [
        (score.item(), idx.item()) for score, idx in zip(max_scores, max_indices)
    ]
    mean_score = torch.mean(max_scores).item()

    return detailed_scores, mean_score


# ==========================================
# 3. BLEURT METRIC
# ==========================================
def compute_bleurt_score(
    gt_texts: List[str],
    pred_texts: List[str],
    model,
    tokenizer,
    device: str,
    batch_size: int = 32,
) -> Tuple[List[Tuple[float, int]], float]:
    """
    Dùng BLEURT để tính similarity.
    Returns: (list of (score, best_pred_idx), mean_score)
    """
    model.eval()

    # Create all pairs (GT, Pred) for scoring
    n_gt = len(gt_texts)
    n_pred = len(pred_texts)

    if n_gt == 0 or n_pred == 0:
        return [(0.0, -1)] * n_gt, 0.0

    # Compute scores for all pairs in batches
    all_scores = []

    with torch.no_grad():
        for i in range(0, n_gt * n_pred, batch_size):
            batch_refs = []
            batch_cands = []

            # Create batch of pairs
            for idx in range(i, min(i + batch_size, n_gt * n_pred)):
                gt_idx = idx // n_pred
                pred_idx = idx % n_pred
                batch_refs.append(gt_texts[gt_idx])
                batch_cands.append(pred_texts[pred_idx])

            # Tokenize and compute scores
            inputs = tokenizer(
                batch_refs, batch_cands, padding="longest", return_tensors="pt"
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            scores = model(**inputs).logits.flatten().tolist()
            all_scores.extend(scores)

    # Reshape to matrix [n_gt, n_pred]
    score_matrix = np.array(all_scores).reshape(n_gt, n_pred)

    # Recall Strategy: get max for each GT
    max_scores = np.max(score_matrix, axis=1)
    max_indices = np.argmax(score_matrix, axis=1)

    detailed_scores = [
        (float(score), int(idx)) for score, idx in zip(max_scores, max_indices)
    ]
    mean_score = float(np.mean(max_scores))

    return detailed_scores, mean_score


# ==========================================
# MAIN EVALUATION LOOP
# ==========================================
def evaluate_sample(
    sample_id: int,
    gt_questions: List[Dict],
    pred_questions: List[Dict],
    bi_model: SentenceTransformer,
    bleurt_model,
    bleurt_tokenizer,
    device: str,
) -> Dict:

    if not gt_questions or not pred_questions:
        return {
            "id": sample_id,
            "n_gt": len(gt_questions) if gt_questions else 0,
            "n_pred": len(pred_questions) if pred_questions else 0,
            "error": "Missing questions",
        }

    gt_texts = [format_question_text(q) for q in gt_questions]
    pred_texts = [format_question_text(q) for q in pred_questions]

    # 1. Lexical (BLEU/ROUGE)
    lexical_detailed, bleu, rouge = compute_lexical_recall(gt_texts, pred_texts)

    # 2. Simple Semantic (Bi-Encoder)
    bi_detailed, bi_score = compute_bi_encoder_score(
        gt_texts, pred_texts, bi_model, device
    )

    # 3. BLEURT
    bleurt_detailed, bleurt_score = compute_bleurt_score(
        gt_texts, pred_texts, bleurt_model, bleurt_tokenizer, device
    )

    # Build individual question scores
    question_scores = []
    for i, gt_q in enumerate(gt_questions):
        # Get best matching prediction index (use bleurt as primary)
        best_pred_idx = bleurt_detailed[i][1]

        # Get the matched prediction
        matched_pred = pred_questions[best_pred_idx] if best_pred_idx >= 0 else None

        question_scores.append(
            {
                "gt_question": gt_q,
                "gt_text": gt_texts[i],
                "matched_pred_idx": best_pred_idx,
                "matched_pred_question": matched_pred,
                "matched_pred_text": (
                    pred_texts[best_pred_idx] if best_pred_idx >= 0 else None
                ),
                "scores": {
                    "bleu4": lexical_detailed[i][0],
                    "rougeL": lexical_detailed[i][1],
                    "cosine_sim": bi_detailed[i][0],
                    "bleurt": bleurt_detailed[i][0],
                },
            }
        )

    return {
        "id": sample_id,
        "n_gt": len(gt_questions),
        "n_pred": len(pred_questions),
        "question_scores": question_scores,
    }


def compute_source_metrics(
    results: List[Dict],
    gt_data: List[Dict],
    gt_qs_map: Dict[int, List[Dict]],
    pred_qs_map: Dict[int, List[Dict]],
) -> Dict[str, Dict]:
    """Compute aggregate metrics for each source

    Args:
        results: List of evaluation results per sample
        gt_data: Original ground truth data (to get source info)
        gt_qs_map: Ground truth questions by sample ID
        pred_qs_map: Predicted questions by sample ID

    Returns:
        Dictionary mapping source name to aggregated metrics
    """
    # Group results by source
    results_by_source = {}

    for r in results:
        if "error" in r:
            continue

        # Get source for this sample
        source = get_source_from_data(gt_data, r["id"])

        if source not in results_by_source:
            results_by_source[source] = []

        results_by_source[source].append(r)

    # Compute metrics for each source
    source_metrics = {}

    for source, source_results in results_by_source.items():
        # Collect all question scores across samples in this source
        all_bleu = []
        all_rouge = []
        all_cosine = []
        all_bleurt = []

        total_gt = 0
        total_pred = 0

        # Collect all GT and Pred texts for this source (for MAUVE)
        source_gt_texts = []
        source_pred_texts = []

        # Collect query-answer pairs for FBD
        source_gt_queries = []
        source_gt_answers = []
        source_pred_queries = []
        source_pred_answers = []

        for r in source_results:
            scores = r["question_scores"]
            total_gt += r["n_gt"]
            total_pred += r["n_pred"]

            # Get questions for this sample
            sample_id = r["id"]
            gt_qs = gt_qs_map.get(sample_id, [])
            pred_qs = pred_qs_map.get(sample_id, [])

            # Select only best matching pred for each GT (for MAUVE/FBD)
            # This applies to ALL datasets to ensure fair comparison (n_pred = n_gt)
            selected_pred_qs = []
            for q_score in scores:
                best_pred_idx = q_score["matched_pred_idx"]
                if best_pred_idx >= 0 and best_pred_idx < len(pred_qs):
                    selected_pred_qs.append(pred_qs[best_pred_idx])

            # Use selected predictions for MAUVE/FBD (n_pred = n_gt for all sources)
            pred_qs_for_corpus = selected_pred_qs

            # Format to text for MAUVE
            source_gt_texts.extend([format_question_text(q) for q in gt_qs])
            source_pred_texts.extend(
                [format_question_text(q) for q in pred_qs_for_corpus]
            )

            # Extract query-answer pairs for FBD
            for q in gt_qs:
                query, answer = extract_query_answer(q)
                source_gt_queries.append(query)
                source_gt_answers.append(answer)

            for q in pred_qs_for_corpus:
                query, answer = extract_query_answer(q)
                source_pred_queries.append(query)
                source_pred_answers.append(answer)

            for q in scores:
                all_bleu.append(q["scores"]["bleu4"])
                all_rouge.append(q["scores"]["rougeL"])
                all_cosine.append(q["scores"]["cosine_sim"])
                all_bleurt.append(q["scores"]["bleurt"])

        # Compute MAUVE for this source
        mauve_score = None
        if HAVE_MAUVE and source_gt_texts and source_pred_texts:
            try:
                device_id = 0 if torch.cuda.is_available() else -1
                out = mauve.compute_mauve(
                    p_text=source_gt_texts,
                    q_text=source_pred_texts,
                    featurize_model_name="gpt2",
                    device_id=device_id,
                    verbose=False,
                )
                mauve_score = float(getattr(out, "mauve", out))
            except Exception as e:
                print(f"  Warning: MAUVE computation failed for source {source}: {e}")
                mauve_score = None

        # Compute FBD for this source
        fbd_score = None
        if HAVE_FBD and source_gt_queries and source_pred_queries:
            try:
                device_str = "gpu" if torch.cuda.is_available() else "cpu"
                # Use default BERT model path - FBD will use bert-base-uncased if not specified
                fbd_score = calculate_fbd(
                    source_querys=source_gt_queries,
                    source_answers=source_gt_answers,
                    target_querys=source_pred_queries,
                    target_answers=source_pred_answers,
                    is_chinese=0,  # English dataset
                    pretrained_model_path="bert-base-uncased",
                    batch_size=32,
                    device=device_str,
                )
            except Exception as e:
                print(f"  Warning: FBD computation failed for source {source}: {e}")
                fbd_score = None

        source_metrics[source] = {
            "n_samples": len(source_results),
            "total_gt_questions": total_gt,
            "total_pred_questions": total_pred,
            "avg_bleu": np.mean(all_bleu) if all_bleu else 0.0,
            "avg_rouge": np.mean(all_rouge) if all_rouge else 0.0,
            "avg_cosine": np.mean(all_cosine) if all_cosine else 0.0,
            "avg_bleurt": np.mean(all_bleurt) if all_bleurt else 0.0,
            "mauve": mauve_score,
            "fbd": fbd_score,
        }

    return source_metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ground-truth",
        type=str,
        default="./datasets/unified/data.json",
        help="Path JSON GT",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model ID (e.g., 'meta-llama_llama-3.1-8b-instruct')",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        required=True,
        help="Dataset source(s) to evaluate (e.g., 'race', 'dream', 'reclor')",
    )
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running on: {device}")
    print(f"Model: {args.model}")
    print(f"Evaluating sources: {', '.join(args.sources)}")

    # Format model ID for path (replace / with _)
    model_id = args.model.replace("/", "_")
    print(f"Model ID for paths: {model_id}")

    # --- LOAD DATA ---
    gt_data = load_json(args.ground_truth)

    # Filter GT data by sources
    sources_lower = [s.lower() for s in args.sources]
    gt_data = [
        item for item in gt_data if item.get("source", "").lower() in sources_lower
    ]

    if not gt_data:
        raise ValueError(
            f"No ground truth data found for sources: {', '.join(args.sources)}"
        )

    # Process each source separately
    for source in args.sources:
        source_lower = source.lower()
        print(f"\n{'='*100}")
        print(f"Processing source: {source.upper()}")
        print(f"{'='*100}")

        # Load predictions for this source
        predictions_path = Path(f"outputs/{source_lower}/{model_id}/predictions.json")
        if not predictions_path.exists():
            print(
                f"Warning: Predictions file not found at {predictions_path}, skipping..."
            )
            continue

        pred_data = load_json(str(predictions_path))

        # Filter GT and predictions for this source only
        source_gt_data = [
            item for item in gt_data if item.get("source", "").lower() == source_lower
        ]
        source_pred_data = [
            item for item in pred_data if item.get("source", "").lower() == source_lower
        ]

        if not source_gt_data:
            print(f"Warning: No ground truth data for source {source}, skipping...")
            continue

        if not source_pred_data:
            print(f"Warning: No prediction data for source {source}, skipping...")
            continue

        gt_qs_map = extract_questions(source_gt_data)
        pred_qs_map = extract_questions(source_pred_data)

        common_ids = sorted(list(set(gt_qs_map.keys()) & set(pred_qs_map.keys())))

        if not common_ids:
            print(
                f"Warning: No common samples between GT and predictions for {source}, skipping..."
            )
            continue

        # Calculate total questions for info
        total_gt_questions = sum(len(gt_qs_map[sid]) for sid in common_ids)
        total_pred_questions = sum(len(pred_qs_map[sid]) for sid in common_ids)

        print(f"Evaluating {len(common_ids)} common samples...")
        print(f"Total GT questions: {total_gt_questions}")
        print(f"Total Pred questions: {total_pred_questions} (from all sets)")

        # Detect if predictions use k-sets format
        sample_pred = source_pred_data[0] if source_pred_data else {}
        has_multiple_sets = "num_sets" in sample_pred
        if has_multiple_sets:
            num_sets = sample_pred.get("num_sets", 1)
            print(f"Detected k-sets format with k={num_sets} sets per sample")
            print(
                f"Evaluating with best score strategy across all questions from all sets"
            )

        # --- LOAD MODELS (only once, outside the loop would be better but keeping here for clarity) ---
        if source == args.sources[0]:  # Load models only once
            print("\nLoading evaluation models...")
            print("Loading Bi-Encoder (Fast Cosine)...")
            bi_model = SentenceTransformer(
                "sentence-transformers/all-MiniLM-L12-v2", device=device
            )

            print("Loading BLEURT (Learned Semantic Similarity)...")
            if not HAVE_BLEURT:
                print(
                    "Warning: BLEURT not available. Install bleurt-pytorch to use BLEURT metric."
                )
                bleurt_model = None
                bleurt_tokenizer = None
            else:
                from bleurt_pytorch import (
                    BleurtConfig,
                    BleurtForSequenceClassification,
                    BleurtTokenizer,
                )

                bleurt_model_name = "lucadiliello/BLEURT-20-D12"
                bleurt_config = BleurtConfig.from_pretrained(bleurt_model_name)
                bleurt_model = BleurtForSequenceClassification.from_pretrained(
                    bleurt_model_name
                )
                bleurt_tokenizer = BleurtTokenizer.from_pretrained(bleurt_model_name)
                bleurt_model.to(device)
                bleurt_model.eval()

        # --- EVALUATE EACH SAMPLE ---
        results = []

        for sid in tqdm(common_ids, desc=f"Evaluating {source}"):
            res = evaluate_sample(
                sid,
                gt_qs_map[sid],
                pred_qs_map[sid],
                bi_model,
                bleurt_model,
                bleurt_tokenizer,
                device,
            )
            results.append(res)

        # --- CALCULATE AGGREGATE METRICS FOR DISPLAY ---
        valid_res = [r for r in results if "error" not in r]

        if valid_res:
            # Compute metrics by source (including MAUVE per source)
            print(f"\nComputing metrics for {source} (including MAUVE and FBD)...")
            source_metrics = compute_source_metrics(
                results, source_gt_data, gt_qs_map, pred_qs_map
            )

            # Print metrics for this source
            for src, metrics in source_metrics.items():
                print(f"\n### Source: {src.upper()} ###")
                print(f"  Samples: {metrics['n_samples']}")
                print(f"  GT Questions: {metrics['total_gt_questions']}")
                print(f"  Pred Questions: {metrics['total_pred_questions']}")

                source_table = [
                    [
                        "BLEU-4",
                        f"{metrics['avg_bleu']:.4f}",
                        "Lexical Precision (n-grams)",
                    ],
                    ["ROUGE-L", f"{metrics['avg_rouge']:.4f}", "Lexical Recall (LCS)"],
                    [
                        "Cosine Sim",
                        f"{metrics['avg_cosine']:.4f}",
                        "Bi-Encoder (Surface Similarity)",
                    ],
                    [
                        "BLEURT",
                        f"{metrics['avg_bleurt']:.4f}",
                        "Learned Semantic Similarity",
                    ],
                ]

                # Add MAUVE if available for this source
                if metrics.get("mauve") is not None:
                    source_table.append(
                        [
                            "MAUVE",
                            f"{metrics['mauve']:.4f}",
                            "Corpus-level Semantic/Diversity",
                        ]
                    )

                # Add FBD if available for this source
                if metrics.get("fbd") is not None:
                    source_table.append(
                        [
                            "FBD",
                            f"{metrics['fbd']:.4f}",
                            "Frechet BERT Distance (lower is better)",
                        ]
                    )

                headers = ["Metric", "Score", "Description"]
                print(tabulate(source_table, headers=headers, tablefmt="fancy_grid"))

                # Print Excel-friendly format (tab-separated for easy copy-paste)
                print(f"\n📊 Copy to Excel:")
                print("-" * 80)
                # Header row
                excel_header = "BLEU-4 ROUGE-L Cosine Sim BLEURT MAUVE FBD"
                print(excel_header)
                # Data row
                excel_data = f"{metrics['avg_bleu']:.4f} {metrics['avg_rouge']:.4f} {metrics['avg_cosine']:.4f} {metrics['avg_bleurt']:.4f} "
                if metrics.get("mauve") is not None:
                    excel_data += f"{metrics['mauve']:.4f} "
                else:
                    excel_data += "N/A "
                if metrics.get("fbd") is not None:
                    excel_data += f"{metrics['fbd']:.4f}"
                else:
                    excel_data += "N/A"
                print(excel_data)
                print("-" * 80)

            # Count total questions
            total_questions = sum(len(r["question_scores"]) for r in valid_res)
            print(f"\nTotal processed: {len(valid_res)} samples")
            print(f"Total ground truth questions evaluated: {total_questions}")

            # --- SAVE RESULTS ---
            output_dir = Path(f"outputs/{source_lower}/{model_id}")
            output_dir.mkdir(parents=True, exist_ok=True)

            # Save detailed results
            eval_output_path = output_dir / "eval_results.json"
            print(f"\nSaving evaluation results to {eval_output_path}...")

            output_data = {
                "source_metrics": source_metrics,
                "detailed_results": results,
            }

            with open(eval_output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            print(
                f"✓ Evaluation complete for {source}! Results saved to {eval_output_path}"
            )

        else:
            print(f"\nNo valid results for {source}.")

    print("\n" + "=" * 100)
    print("ALL EVALUATIONS COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
