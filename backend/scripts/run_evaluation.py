#!/usr/bin/env python3
"""
RAGAS Evaluation Script for AIKM RAG System

This script runs RAGAS evaluation on the RAG system and generates a detailed report.

Usage:
    # Run with built-in sample data
    python scripts/run_evaluation.py

    # Run with custom test data file
    python scripts/run_evaluation.py --test-data path/to/test_data.json

    # Run specific metrics only
    python scripts/run_evaluation.py --metrics context_recall faithfulness

    # Save results to file
    python scripts/run_evaluation.py --output results.json

Example test_data.json format:
[
    {
        "user_input": "如何更換空氣彈簧？",
        "reference": "更換空氣彈簧步驟：1. 使用千斤頂將車體頂起..."
    },
    {
        "user_input": "轉向架檢修的注意事項有哪些？",
        "reference": "轉向架檢修注意事項：1. 確認車輛已完全停止..."
    }
]
"""
import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.services import evaluation as evaluation_service


def print_separator(char: str = "=", length: int = 70):
    """Print a separator line."""
    print(char * length)


def print_header(title: str):
    """Print a section header."""
    print_separator()
    print(f" {title}")
    print_separator()


def format_score(score: float) -> str:
    """Format score as percentage with color indicator."""
    percentage = score * 100
    if percentage >= 80:
        indicator = "✅"
    elif percentage >= 60:
        indicator = "⚠️"
    else:
        indicator = "❌"
    return f"{indicator} {percentage:.1f}%"


def run_evaluation(
    test_data_path: str | None = None,
    metrics: list[str] | None = None,
    top_k: int = 5,
    output_path: str | None = None,
):
    """Run the evaluation and print results."""
    print_header("AIKM RAG System - RAGAS Evaluation")
    print()

    # Load custom test data if provided
    test_data = None
    if test_data_path:
        print(f"📂 Loading test data from: {test_data_path}")
        with open(test_data_path, "r", encoding="utf-8") as f:
            test_data = json.load(f)
        print(f"   Loaded {len(test_data)} test cases")
    else:
        print("📂 Using built-in sample test data")
        print(f"   {len(evaluation_service.SAMPLE_TEST_DATA)} test cases")

    print()

    # Show configuration
    print("⚙️  Configuration:")
    print(f"   - Top K: {top_k}")
    print(f"   - Metrics: {metrics or ['all']}")
    print()

    # Run evaluation
    print("🔄 Running evaluation...")
    print("   This may take several minutes depending on the number of test cases.")
    print()

    try:
        result = evaluation_service.run_evaluation(
            test_data=test_data,
            top_k=top_k,
            metrics=metrics,
        )
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        sys.exit(1)

    # Print overall scores
    print_header("Overall Scores")
    print()

    metric_names = {
        "context_recall": "Context Recall",
        "faithfulness": "Faithfulness",
        "factual_correctness": "Factual Correctness",
    }

    for metric, score in result["scores"].items():
        display_name = metric_names.get(metric, metric)
        print(f"  {display_name:25} {format_score(score)}")

    print()

    # Print per-sample details
    print_header("Per-Sample Details")
    print()

    for i, detail in enumerate(result["details"], 1):
        print(f"📝 Sample {i}: {detail['user_input'][:60]}...")
        print(f"   Response: {detail['response'][:80]}...")
        print(f"   Contexts: {len(detail['retrieved_contexts'])} retrieved")

        # Print individual scores
        scores_str = []
        for metric in result["metadata"]["metrics_evaluated"]:
            if metric in detail and detail[metric] is not None:
                scores_str.append(f"{metric_names.get(metric, metric)}: {detail[metric]:.2f}")
        print(f"   Scores: {', '.join(scores_str)}")
        print()

    # Print metadata
    print_header("Metadata")
    print()
    meta = result["metadata"]
    print(f"  Timestamp:        {meta['timestamp']}")
    print(f"  Sample Count:     {meta['sample_count']}")
    print(f"  Metrics:          {', '.join(meta['metrics_evaluated'])}")
    print(f"  Top K:            {meta['top_k']}")
    print(f"  Model:            {meta['model']}")
    print()

    # Save results if output path provided
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"💾 Results saved to: {output_path}")
        print()

    # Print summary
    print_header("Summary")
    print()
    avg_score = sum(result["scores"].values()) / len(result["scores"])
    print(f"  Average Score: {format_score(avg_score)}")

    if avg_score >= 0.8:
        print("  🎉 RAG system is performing excellently!")
    elif avg_score >= 0.6:
        print("  ⚠️  RAG system has room for improvement.")
    else:
        print("  ❌ RAG system needs significant improvements.")

    print()
    print_separator()


def main():
    parser = argparse.ArgumentParser(
        description="Run RAGAS evaluation on the AIKM RAG system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--test-data",
        type=str,
        help="Path to custom test data JSON file",
    )

    parser.add_argument(
        "--metrics",
        nargs="+",
        choices=["context_recall", "faithfulness", "factual_correctness"],
        help="Specific metrics to evaluate (default: all)",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of documents to retrieve (default: 5)",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Path to save evaluation results as JSON",
    )

    args = parser.parse_args()

    run_evaluation(
        test_data_path=args.test_data,
        metrics=args.metrics,
        top_k=args.top_k,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
