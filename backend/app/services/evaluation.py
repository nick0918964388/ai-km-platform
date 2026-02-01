"""RAGAS evaluation service for RAG system quality assessment."""
import logging
import os
from datetime import datetime
from typing import Optional

from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import (
    LLMContextRecall,
    Faithfulness,
    FactualCorrectness,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.services import rag as rag_service
from app.models.schemas import SearchResult

logger = logging.getLogger(__name__)


# Built-in sample test dataset for EMU800 maintenance domain
SAMPLE_TEST_DATA = [
    {
        "user_input": "如何更換空氣彈簧？",
        "reference": "更換空氣彈簧步驟：1. 使用千斤頂將車體頂起 2. 釋放空氣彈簧內的壓力 3. 拆除固定螺栓 4. 取出舊空氣彈簧 5. 安裝新空氣彈簧 6. 鎖緊固定螺栓至規定扭力 7. 充氣測試",
    },
    {
        "user_input": "轉向架檢修的注意事項有哪些？",
        "reference": "轉向架檢修注意事項：1. 確認車輛已完全停止並設置防護 2. 檢查軸承磨損情況 3. 測量輪緣厚度 4. 檢查牽引馬達絕緣 5. 確認空氣彈簧無漏氣 6. 檢查制動缸作動正常",
    },
    {
        "user_input": "煞車系統的維護週期是多久？",
        "reference": "煞車系統維護週期：日常檢查每日執行，定期保養每3個月，大修每2年。檢查項目包含軔缸、制動管路、煞車來令片磨損程度。",
    },
]


def _get_llm():
    """Get the LLM wrapper for RAGAS evaluation."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=api_key,
        temperature=0,
    )
    return LangchainLLMWrapper(llm)


def _get_embeddings():
    """Get the embeddings wrapper for RAGAS evaluation."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key,
    )
    return LangchainEmbeddingsWrapper(embeddings)


def _extract_contexts(sources: list[SearchResult]) -> list[str]:
    """Extract context strings from search results."""
    return [source.content for source in sources if source.content]


def run_rag_pipeline(query: str, top_k: int = 5) -> dict:
    """
    Run the RAG pipeline and collect data for evaluation.

    Args:
        query: User query
        top_k: Number of documents to retrieve

    Returns:
        Dictionary containing response and retrieved_contexts
    """
    answer, sources = rag_service.chat(query, top_k=top_k)
    contexts = _extract_contexts(sources)

    return {
        "response": answer,
        "retrieved_contexts": contexts,
    }


def create_evaluation_dataset(
    test_data: Optional[list[dict]] = None,
    top_k: int = 5,
) -> EvaluationDataset:
    """
    Create an EvaluationDataset by running the RAG pipeline on test queries.

    Args:
        test_data: List of test cases with 'user_input' and 'reference' keys.
                   If None, uses built-in sample data.
        top_k: Number of documents to retrieve for each query

    Returns:
        EvaluationDataset ready for evaluation
    """
    if test_data is None:
        test_data = SAMPLE_TEST_DATA

    samples = []

    for test_case in test_data:
        user_input = test_case["user_input"]
        reference = test_case.get("reference", "")

        logger.info(f"Running RAG pipeline for: {user_input[:50]}...")

        # Run RAG pipeline
        rag_result = run_rag_pipeline(user_input, top_k=top_k)

        # Create SingleTurnSample
        sample = SingleTurnSample(
            user_input=user_input,
            response=rag_result["response"],
            retrieved_contexts=rag_result["retrieved_contexts"],
            reference=reference,
        )
        samples.append(sample)

    return EvaluationDataset(samples=samples)


def run_evaluation(
    test_data: Optional[list[dict]] = None,
    top_k: int = 5,
    metrics: Optional[list[str]] = None,
) -> dict:
    """
    Run RAGAS evaluation on the RAG system.

    Args:
        test_data: List of test cases with 'user_input' and 'reference' keys.
                   If None, uses built-in sample data.
        top_k: Number of documents to retrieve for each query
        metrics: List of metric names to evaluate.
                 Options: 'context_recall', 'faithfulness', 'factual_correctness'
                 If None, uses all metrics.

    Returns:
        Dictionary containing:
        - scores: Overall scores for each metric
        - details: Per-sample detailed results
        - metadata: Evaluation metadata (timestamp, sample count, etc.)
    """
    logger.info("Starting RAGAS evaluation...")

    # Get LLM and embeddings
    llm = _get_llm()
    embeddings = _get_embeddings()

    # Initialize metrics
    available_metrics = {
        "context_recall": LLMContextRecall(llm=llm),
        "faithfulness": Faithfulness(llm=llm),
        "factual_correctness": FactualCorrectness(llm=llm),
    }

    if metrics is None:
        metrics = list(available_metrics.keys())

    selected_metrics = [
        available_metrics[m] for m in metrics if m in available_metrics
    ]

    if not selected_metrics:
        raise ValueError(f"No valid metrics selected. Available: {list(available_metrics.keys())}")

    # Create evaluation dataset
    dataset = create_evaluation_dataset(test_data, top_k=top_k)

    logger.info(f"Evaluating {len(dataset.samples)} samples with metrics: {metrics}")

    # Run evaluation
    results = evaluate(
        dataset=dataset,
        metrics=selected_metrics,
        llm=llm,
        embeddings=embeddings,
    )

    # Extract scores
    scores = {}
    for metric_name in metrics:
        if metric_name in results:
            scores[metric_name] = float(results[metric_name])

    # Build detailed results
    details = []
    result_df = results.to_pandas()

    for idx, row in result_df.iterrows():
        detail = {
            "user_input": row.get("user_input", ""),
            "response": row.get("response", ""),
            "reference": row.get("reference", ""),
            "retrieved_contexts": row.get("retrieved_contexts", []),
        }

        # Add metric scores for this sample
        for metric_name in metrics:
            if metric_name in row:
                detail[metric_name] = float(row[metric_name]) if row[metric_name] is not None else None

        details.append(detail)

    # Build response
    evaluation_result = {
        "scores": scores,
        "details": details,
        "metadata": {
            "timestamp": datetime.utcnow().isoformat(),
            "sample_count": len(dataset.samples),
            "metrics_evaluated": metrics,
            "top_k": top_k,
            "model": "gpt-4o",
        },
    }

    logger.info(f"Evaluation completed. Scores: {scores}")

    return evaluation_result


def get_available_metrics() -> list[dict]:
    """Get list of available evaluation metrics with descriptions."""
    return [
        {
            "name": "context_recall",
            "display_name": "Context Recall",
            "description": "衡量檢索到的上下文是否包含回答問題所需的所有相關資訊",
        },
        {
            "name": "faithfulness",
            "display_name": "Faithfulness",
            "description": "衡量生成的回答是否忠實於檢索到的上下文，不包含幻覺或編造的資訊",
        },
        {
            "name": "factual_correctness",
            "display_name": "Factual Correctness",
            "description": "衡量生成的回答與參考答案相比的事實正確性",
        },
    ]
