import json
import os
from pathlib import Path
from typing import List, Dict, TypedDict, Annotated
import argparse
import re
import operator
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from dotenv import load_dotenv

load_dotenv()


# Define the state structure for the workflow
class WorkflowState(TypedDict):
    """State passed between agents in the workflow"""

    content: str  # Input text
    item_id: str  # Sample ID
    source: str  # Source name
    n: int  # Number of questions per level
    analyzer_output: str  # Output from analyzer agent
    level1_questions: List[Dict]  # Questions from level 1 generator
    level2_questions: List[Dict]  # Questions from level 2 generator
    level3_questions: List[Dict]  # Questions from level 3 generator
    final_questions: List[Dict]  # Combined final questions
    error: str  # Error message if any


def load_prompt(prompt_path: str) -> str:
    """Load prompt from file

    Args:
        prompt_path: Path to the prompt file

    Returns:
        Prompt content as string
    """
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def load_data(data_path: str, n: int = -1, sources: List[str] = None) -> List[dict]:
    """Load data from JSON file

    Args:
        data_path: Path to the data.json file
        n: Number of items to load (-1 for all)
        sources: List of sources to filter by (None for all sources)

    Returns:
        List of data items
    """
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Filter by sources if specified
    if sources:
        sources_lower = [s.lower() for s in sources]
        data = [
            item for item in data if item.get("source", "").lower() in sources_lower
        ]

    if n > 0:
        data = data[:n]

    return data


def analyzer_agent(
    state: WorkflowState, llm: ChatOpenAI, analyzer_prompt: str
) -> WorkflowState:
    """Analyzer agent - extracts useful information from text

    Args:
        state: Current workflow state
        llm: Language model
        analyzer_prompt: Prompt template for analyzer

    Returns:
        Updated state with analyzer_output
    """
    try:
        # Create prompt with content
        full_prompt = analyzer_prompt.replace("{content}", state["content"])

        # Invoke LLM
        response = llm.invoke(full_prompt)
        analyzer_output = response.content

        print(f"\n{'='*80}")
        print(f"Analyzer Output for {state['item_id']}:")
        print(f"{'='*80}")
        print(analyzer_output)
        print(f"{'='*80}\n")

        # Update state
        state["analyzer_output"] = analyzer_output

    except Exception as e:
        state["error"] = f"Analyzer failed: {str(e)}"
        print(f"Error in analyzer: {str(e)}")

    return state


def parse_generator_output(
    output: str, n: int, expected_level: int = None
) -> List[Dict]:
    """Parse generator output into structured questions

    Expected format:
    ID: 1
    Question: Question text
    A: Option A
    B: Option B
    C: Option C
    D: Option D
    Answer: A

    Args:
        output: Raw generator output
        n: Number of questions expected
        expected_level: Expected level (assigned to all questions)

    Returns:
        List of question dictionaries
    """
    questions = []

    # Split by ID: to separate questions
    blocks = re.split(r"\n(?=ID:\s*\d+)", output.strip())

    for block in blocks:
        if not block.strip():
            continue

        try:
            # Find positions of key prefixes
            question_pos = block.find("Question:")
            a_pos = block.find("\nA:")
            b_pos = block.find("\nB:")
            c_pos = block.find("\nC:")
            d_pos = block.find("\nD:")
            answer_pos = block.find("\nAnswer:")

            # Extract Question text (from "Question:" to "\nA:")
            if question_pos == -1 or a_pos == -1:
                continue
            question_text = block[question_pos + len("Question:") : a_pos].strip()

            # Extract options by finding text between prefixes
            if (
                a_pos == -1
                or b_pos == -1
                or c_pos == -1
                or d_pos == -1
                or answer_pos == -1
            ):
                continue

            option_a = block[a_pos + len("\nA:") : b_pos].strip()
            option_b = block[b_pos + len("\nB:") : c_pos].strip()
            option_c = block[c_pos + len("\nC:") : d_pos].strip()
            option_d = block[d_pos + len("\nD:") : answer_pos].strip()

            options = [option_a, option_b, option_c, option_d]

            # Extract Answer letter
            answer_match = re.search(r"Answer:\s*([A-D])", block, re.IGNORECASE)
            answer_letter = (
                answer_match.group(1).strip().upper() if answer_match else None
            )

            # Only add if we have all 4 options and answer
            if len(options) == 4 and answer_letter:
                # Map answer letter to index
                correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
                correct_idx = correct_map.get(answer_letter, -1)

                if correct_idx != -1:
                    questions.append(
                        {
                            "question": question_text,
                            "options": options,
                            "correct_idx": correct_idx,
                            "level": expected_level,  # Use the expected level from the generator
                        }
                    )

        except Exception as e:
            print(f"Warning: Failed to parse question block: {str(e)}")
            continue

    return questions


def generator_level1_agent(
    state: WorkflowState, llm: ChatOpenAI, generator_prompt: str
) -> Dict:
    """Generator agent for Level 1 questions

    Args:
        state: Current workflow state
        llm: Language model
        generator_prompt: Prompt template for Level 1 generator

    Returns:
        Dict with level1_questions key only
    """
    if state.get("error"):
        return {}

    try:
        n = state["n"]

        # Create prompt
        full_prompt = (
            generator_prompt.replace("{content}", state["content"])
            .replace("{analyzer_output}", state["analyzer_output"])
            .replace("{n}", str(n))
        )

        # Invoke LLM
        response = llm.invoke(full_prompt)
        generator_output = response.content

        print(f"\n{'='*80}")
        print(f"Level 1 Generator Output for {state['item_id']}:")
        print(f"{'='*80}")
        print(generator_output)
        print(f"{'='*80}\n")

        # Parse output
        questions = parse_generator_output(generator_output, n, expected_level=1)

        # Return only the key this agent updates
        return {"level1_questions": questions}

    except Exception as e:
        error_msg = f"Level 1 Generator failed: {str(e)}"
        print(f"Error in Level 1 generator: {str(e)}")
        return {"error": error_msg}


def generator_level2_agent(
    state: WorkflowState, llm: ChatOpenAI, generator_prompt: str
) -> Dict:
    """Generator agent for Level 2 questions

    Args:
        state: Current workflow state
        llm: Language model
        generator_prompt: Prompt template for Level 2 generator

    Returns:
        Dict with level2_questions key only
    """
    if state.get("error"):
        return {}

    try:
        n = state["n"]

        # Create prompt
        full_prompt = (
            generator_prompt.replace("{content}", state["content"])
            .replace("{analyzer_output}", state["analyzer_output"])
            .replace("{n}", str(n))
        )

        # Invoke LLM
        response = llm.invoke(full_prompt)
        generator_output = response.content

        print(f"\n{'='*80}")
        print(f"Level 2 Generator Output for {state['item_id']}:")
        print(f"{'='*80}")
        print(generator_output)
        print(f"{'='*80}\n")

        # Parse output
        questions = parse_generator_output(generator_output, n, expected_level=2)

        # Return only the key this agent updates
        return {"level2_questions": questions}

    except Exception as e:
        error_msg = f"Level 2 Generator failed: {str(e)}"
        print(f"Error in Level 2 generator: {str(e)}")
        return {"error": error_msg}


def generator_level3_agent(
    state: WorkflowState, llm: ChatOpenAI, generator_prompt: str
) -> Dict:
    """Generator agent for Level 3 questions

    Args:
        state: Current workflow state
        llm: Language model
        generator_prompt: Prompt template for Level 3 generator

    Returns:
        Dict with level3_questions key only
    """
    if state.get("error"):
        return {}

    try:
        n = state["n"]

        # Create prompt
        full_prompt = (
            generator_prompt.replace("{content}", state["content"])
            .replace("{analyzer_output}", state["analyzer_output"])
            .replace("{n}", str(n))
        )

        # Invoke LLM
        response = llm.invoke(full_prompt)
        generator_output = response.content

        print(f"\n{'='*80}")
        print(f"Level 3 Generator Output for {state['item_id']}:")
        print(f"{'='*80}")
        print(generator_output)
        print(f"{'='*80}\n")

        # Parse output
        questions = parse_generator_output(generator_output, n, expected_level=3)

        # Return only the key this agent updates
        return {"level3_questions": questions}

    except Exception as e:
        error_msg = f"Level 3 Generator failed: {str(e)}"
        print(f"Error in Level 3 generator: {str(e)}")
        return {"error": error_msg}


def merge_questions_agent(state: WorkflowState) -> WorkflowState:
    """Merge questions from all 3 levels into final_questions

    Args:
        state: Current workflow state

    Returns:
        Updated state with final_questions
    """
    if state.get("error"):
        return state

    try:
        # Combine all questions
        all_questions = []

        for q in state.get("level1_questions", []):
            all_questions.append(
                {
                    "content": q["question"],
                    "options": q["options"],
                    "correct": q["correct_idx"],
                    "level": 1,
                    "type": "General",
                }
            )

        for q in state.get("level2_questions", []):
            all_questions.append(
                {
                    "content": q["question"],
                    "options": q["options"],
                    "correct": q["correct_idx"],
                    "level": 2,
                    "type": "General",
                }
            )

        for q in state.get("level3_questions", []):
            all_questions.append(
                {
                    "content": q["question"],
                    "options": q["options"],
                    "correct": q["correct_idx"],
                    "level": 3,
                    "type": "General",
                }
            )

        # Sort by level, then by original order
        all_questions.sort(key=lambda x: x["level"])

        print(f"\n{'='*80}")
        print(f"Merged {len(all_questions)} questions for {state['item_id']}:")
        print(f"{'='*80}")
        for idx, q in enumerate(all_questions, 1):
            print(f"Q{idx} (Level {q['level']}): {q['content'][:80]}...")
        print(f"{'='*80}\n")

        state["final_questions"] = all_questions

    except Exception as e:
        state["error"] = f"Merge failed: {str(e)}"
        print(f"Error in merge: {str(e)}")

    return state


def create_workflow(
    llm: ChatOpenAI,
    analyzer_prompt: str,
    generator_level1_prompt: str,
    generator_level2_prompt: str,
    generator_level3_prompt: str,
) -> StateGraph:
    """Create the multi-agent workflow using LangGraph

    Args:
        llm: Language model
        analyzer_prompt: Prompt for analyzer agent
        generator_level1_prompt: Prompt for Level 1 generator agent
        generator_level2_prompt: Prompt for Level 2 generator agent
        generator_level3_prompt: Prompt for Level 3 generator agent

    Returns:
        Compiled workflow graph
    """
    # Create workflow graph
    workflow = StateGraph(WorkflowState)

    # Add nodes (agents)
    workflow.add_node(
        "analyzer", lambda state: analyzer_agent(state, llm, analyzer_prompt)
    )
    workflow.add_node(
        "generator_level1",
        lambda state: generator_level1_agent(state, llm, generator_level1_prompt),
    )
    workflow.add_node(
        "generator_level2",
        lambda state: generator_level2_agent(state, llm, generator_level2_prompt),
    )
    workflow.add_node(
        "generator_level3",
        lambda state: generator_level3_agent(state, llm, generator_level3_prompt),
    )
    workflow.add_node("merge", merge_questions_agent)

    # Define edges (flow): analyzer -> [level1, level2, level3] -> merge -> END
    workflow.set_entry_point("analyzer")
    workflow.add_edge("analyzer", "generator_level1")
    workflow.add_edge("analyzer", "generator_level2")
    workflow.add_edge("analyzer", "generator_level3")
    workflow.add_edge("generator_level1", "merge")
    workflow.add_edge("generator_level2", "merge")
    workflow.add_edge("generator_level3", "merge")
    workflow.add_edge("merge", END)

    # Compile the graph
    return workflow.compile()


def process_item(item: dict, n: int, workflow: StateGraph) -> Dict:
    """Process a single item through the workflow

    Args:
        item: Data item with 'id', 'content', 'source'
        n: Number of questions per level
        workflow: Compiled workflow graph

    Returns:
        Result dictionary
    """
    # Initialize state
    initial_state = WorkflowState(
        content=item["content"],
        item_id=item["id"],
        source=item.get("source", "unknown"),
        n=n,
        analyzer_output="",
        level1_questions=[],
        level2_questions=[],
        level3_questions=[],
        final_questions=[],
        error="",
    )

    try:
        # Run workflow
        final_state = workflow.invoke(initial_state)

        # Check for errors
        if final_state.get("error"):
            return {
                "id": item["id"],
                "source": item.get("source", "unknown"),
                "error": final_state["error"],
            }

        result = {
            "id": item["id"],
            "source": item.get("source", "unknown"),
            "generated_questions": final_state["final_questions"],
        }

        # Log the completed result as JSON
        print(f"\n{'='*80}")
        print(f"✓ Completed item {item['id']}:")
        print(f"{'='*80}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"{'='*80}\n")

        return result

    except Exception as e:
        error_result = {
            "id": item["id"],
            "source": item.get("source", "unknown"),
            "error": str(e),
        }

        # Log the error result as JSON
        print(f"\n{'='*80}")
        print(f"✗ Error for item {item['id']}:")
        print(f"{'='*80}")
        print(json.dumps(error_result, indent=2, ensure_ascii=False))
        print(f"{'='*80}\n")

        return error_result


def main():
    parser = argparse.ArgumentParser(
        description="Multi-agent workflow for generating questions from text"
    )
    parser.add_argument(
        "--num-items",
        type=int,
        default=-1,
        help="Number of items to process (-1 for all)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="anthropic/claude-3.5-sonnet",
        help="Model ID to use (e.g., 'anthropic/claude-3.5-sonnet', 'openai/gpt-4')",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="Number of questions per level (total = 3*n questions per sample, default: 1)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="datasets/unified/data.json",
        help="Path to the data.json file",
    )
    parser.add_argument(
        "--analyzer-prompt-path",
        type=str,
        default="prompts/analyzer.md",
        help="Path to the analyzer prompt file",
    )
    parser.add_argument(
        "--generator-level1-prompt-path",
        type=str,
        default="prompts/generator_level1.md",
        help="Path to the Level 1 generator prompt file",
    )
    parser.add_argument(
        "--generator-level2-prompt-path",
        type=str,
        default="prompts/generator_level2.md",
        help="Path to the Level 2 generator prompt file",
    )
    parser.add_argument(
        "--generator-level3-prompt-path",
        type=str,
        default="prompts/generator_level3.md",
        help="Path to the Level 3 generator prompt file",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="Filter by source(s) (e.g., 'race', 'dream'). Default: all sources",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers for processing items (default: 1, sequential processing)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs/workflow",
        help="Directory to save output files",
    )

    args = parser.parse_args()

    # Get API key from environment variable
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenRouter API key not found. Please set OPENROUTER_API_KEY environment variable"
        )

    # Validate sources parameter
    if not args.sources:
        raise ValueError(
            "Error: --sources parameter is required. Please specify which dataset(s) to process.\n"
            "Example: --sources reclor, --sources race, or --sources race dream"
        )

    # Load prompts
    print(f"Loading analyzer prompt from {args.analyzer_prompt_path}...")
    analyzer_prompt = load_prompt(args.analyzer_prompt_path)
    print(f"Analyzer prompt loaded successfully")

    print(
        f"Loading Level 1 generator prompt from {args.generator_level1_prompt_path}..."
    )
    generator_level1_prompt = load_prompt(args.generator_level1_prompt_path)
    print(f"Level 1 generator prompt loaded successfully")

    print(
        f"Loading Level 2 generator prompt from {args.generator_level2_prompt_path}..."
    )
    generator_level2_prompt = load_prompt(args.generator_level2_prompt_path)
    print(f"Level 2 generator prompt loaded successfully")

    print(
        f"Loading Level 3 generator prompt from {args.generator_level3_prompt_path}..."
    )
    generator_level3_prompt = load_prompt(args.generator_level3_prompt_path)
    print(f"Level 3 generator prompt loaded successfully")

    # Initialize LLM
    llm = ChatOpenAI(
        model=args.model,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.0,
    )

    # Create workflow
    print("Creating multi-agent workflow...")
    workflow = create_workflow(
        llm,
        analyzer_prompt,
        generator_level1_prompt,
        generator_level2_prompt,
        generator_level3_prompt,
    )
    print("Workflow created successfully\n")

    # Get model_id from model name with suffix
    model_id = args.model.replace("/", "_") + "-new"

    print(f"\nUsing model: {args.model}")
    print(f"Model ID: {model_id}")
    print(f"Generating {3 * args.n} questions per sample ({args.n} per level)")
    print(f"Processing sources: {', '.join(args.sources)}")

    # Process each source separately
    for source in args.sources:
        source_lower = source.lower()
        print(f"\n{'='*100}")
        print(f"Processing source: {source.upper()}")
        print(f"{'='*100}")

        # Load data for this source only
        print(f"Loading data from {args.data_path}...")
        data = load_data(args.data_path, args.num_items, [source])
        print(f"Loaded {len(data)} items for {source}")

        if not data:
            print(f"Warning: No data found for source {source}, skipping...")
            continue

        # Create output directory similar to question.py
        output_dir = Path("outputs") / source_lower / model_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "predictions.json"

        print(f"Output will be saved to: {output_path}")
        print(f"Using {args.workers} worker(s) for parallel processing")

        # Process items with ThreadPoolExecutor
        results = []

        if args.workers == 1:
            # Sequential processing
            for i, item in enumerate(data, 1):
                print(f"\n{'='*100}")
                print(f"Processing item {i}/{len(data)}: {item['id']}")
                print(f"{'='*100}")

                result = process_item(item, args.n, workflow)
                results.append(result)

                # Print summary for this item
                if "error" in result:
                    print(f"✗ Error: {result['error']}")
                else:
                    print(
                        f"✓ Successfully generated {len(result['generated_questions'])} questions"
                    )
        else:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                # Submit all jobs
                future_to_item = {
                    executor.submit(process_item, item, args.n, workflow): item
                    for item in data
                }

                # Process completed jobs with progress bar
                with tqdm(total=len(data), desc=f"Processing {source}") as pbar:
                    for future in as_completed(future_to_item):
                        item = future_to_item[future]
                        try:
                            result = future.result()
                            results.append(result)

                            # Print summary for this item
                            if "error" in result:
                                tqdm.write(f"✗ {item['id']}: Error - {result['error']}")
                            else:
                                tqdm.write(
                                    f"✓ {item['id']}: Generated {len(result['generated_questions'])} questions"
                                )
                        except Exception as e:
                            tqdm.write(f"✗ {item['id']}: Exception - {str(e)}")
                            results.append(
                                {
                                    "id": item["id"],
                                    "source": item.get("source", "unknown"),
                                    "content": item["content"],
                                    "error": str(e),
                                }
                            )
                        pbar.update(1)

        # Sort results by ID to maintain order (like question.py)
        results.sort(key=lambda x: x["id"])

        # Save results
        print(f"\nSaving results to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(
            f"✓ Done! Processed {len(data)} items for {source}, saved to {output_path}"
        )

        # Print summary
        successful = sum(1 for r in results if "error" not in r)
        failed = len(results) - successful
        total_questions = sum(
            len(r.get("generated_questions", [])) for r in results if "error" not in r
        )

        print(f"\nSummary for {source}:")
        print(f"  Successful samples: {successful}")
        print(f"  Failed samples: {failed}")
        print(f"  Total questions generated: {total_questions}")
        print(f"  Questions per sample: {3 * args.n} ({args.n} per level)")

    print("\n" + "=" * 100)
    print("ALL SOURCES COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
