import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

# ── 2. Graphiti imports ──────────────────────────────────────────────────
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.utils.maintenance.graph_data_operations import clear_data




GOOGLE_API_KEY = "AIzaSyAqZTHJi6zXK4bJlm7_D-6psC_qayMdlDE"

client=GeminiRerankerClient(
            config=LLMConfig(api_key=GOOGLE_API_KEY, model="gemini-2.5-flash-lite-preview-06-17"),
        )

query = "What is the capital of France?"
passages = [
    "Paris is the capital of France and is known for its art, history, and culture.",
    "Berlin is the capital of Germany and has a rich history.",
    "Madrid is the capital of Spain, a country in Southern Europe."
]

# Call the rank method to rank the passages based on their relevance to the query
# Since rank is an asynchronous method, you'll need to run it in an asynchronous context


async def rank_passages():
    ranked_results = await client.rank(query, passages)
    for passage, score in ranked_results:
        print(f"Passage: {passage}\nScore: {score}\n")

# Run the async function
asyncio.run(rank_passages())