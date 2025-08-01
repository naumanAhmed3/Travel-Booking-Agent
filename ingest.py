#!/usr/bin/env python3
"""
ingest_concert_data.py
==========================
► Ingests data about upcoming Atif Aslam concerts into Neo4j using Graphiti.
► This script contains three separate functions to add concert episodes,
  each using a different set of keys for the data.
► It demonstrates how to add structured data with varying schemas.
"""

# ── 1. Standard imports ──────────────────────────────────────────────────
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
from logging import INFO

#################################################
# CONFIGURATION
#################################################
# Set up logging and environment variables for
# connecting to the Neo4j database.
#################################################

# Configure logging
logging.basicConfig(
    level=INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

load_dotenv()

# --- IMPORTANT: Make sure these credentials are correct ---
# It's recommended to use environment variables for sensitive data.
SIR_BILAL_API = "AIzaSyCbJ2UBDvzztgs-gor8eyi54mWtDsugeNY"
GOOGLE_API_KEY = "AIzaSyCbJ2UBDvzztgs-gor8eyi54mWtDsugeNY"

# --- IMPORTANT: Make sure these credentials are correct ---
NEO4J_URI      = "neo4j://127.0.0.1:7687"
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = "bookme_chatbot" # Use a valid password


if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set.")

async def add_concert_details_one(graphiti: Graphiti):
    """
    Adds concert details using the first set of key names.
    """
    episodes = [
        {
            'event_name': 'Atif Aslam Live In Concert',
            'artist': 'Atif Aslam',
            'concert_venue': 'Arie Crown Theater, Chicago, IL',
            'event_date': '2025-09-20',
            'start_time': '7:00 PM',
            'ticket_price_range': {
                'min_price': 86,
                'currency': 'USD'
            },
            'information_type': EpisodeType.text,
            'data_source': 'Arie Crown Theater Official Website'
        }
    ]
    

    for i, episode in enumerate(episodes):
        episode_type = episode['information_type']
        episode_body = {k: v for k, v in episode.items() if k not in ['information_type', 'data_source']}
        episode_body_json = json.dumps(episode_body)

        await graphiti.add_episode(
            name=f'Concert Details 1 - Ep {i+1}',
            episode_body=episode_body_json,
            source=episode_type,
            source_description=episode['data_source'],
            reference_time=datetime.now(timezone.utc),
        )
    print("Successfully added concert details with function one.")

async def add_concert_details_two(graphiti: Graphiti):
    """
    Adds concert details using the second set of key names.
    """
    episodes = [
        {'Update' : 'Bookme is offering 50% discount on tickets for buses from lahore to karachi only for women' , 
         'content_type': EpisodeType.text , 'data_source':'Bookme-updates-live'}
    ]

    for i, episode in enumerate(episodes):
        episode_type = episode['content_type']
        episode_body = episode['Update']
        data_source = episode['data_source']


        await graphiti.add_episode(
            name=f'new update on tikcets',
            episode_body=episode_body,
            source=episode_type,
            source_description=data_source,
            reference_time=datetime.now(timezone.utc),
        )
    print("Successfully added concert details with function two.")

async def add_concert_details_three(graphiti: Graphiti):
    """
    Adds concert details using the third set of key names.
    """
    episodes = [
        {
            'show_name': 'Atif Aslam Tour',
            'main_performer': 'Atif Aslam',
            'venue_address': 'Scotiabank Arena, Toronto, ON, Canada',
            'show_date': '2025-09-07',
            'timing': '8:00 PM',
            'ticket_information': {
                'lowest_price': 105,
                'price_unit': 'CAD'
            },
            'episode_kind': EpisodeType.json,
            'retrieval_source': 'Songkick'
        }
    ]

    for i, episode in enumerate(episodes):
        episode_type = episode['episode_kind']
        episode_body = {k: v for k, v in episode.items() if k not in ['episode_kind', 'retrieval_source']}
        episode_body_json = json.dumps(episode_body)

        await graphiti.add_episode(
            name=f'Concert Details 3 - Ep {i+1}',
            episode_body=episode_body_json,
            source=episode_type,
            source_description=episode['retrieval_source'],
            reference_time=datetime.now(timezone.utc),
        )
    print("Successfully added concert details with function three.")


async def main():
    """
    Main function to initialize Graphiti and run all the ingestion functions.
    """
    # Initialize Graphiti with Neo4j connection
    graphiti = Graphiti(
        NEO4J_URI,
        NEO4J_USER,
        NEO4J_PASSWORD,
        llm_client=GeminiClient(
            config=LLMConfig(api_key=GOOGLE_API_KEY, model="gemini-1.5-pro-latest"),
        ),
        embedder=GeminiEmbedder(
            config=GeminiEmbedderConfig(api_key=GOOGLE_API_KEY, embedding_model="embedding-001"),
        ),
        cross_encoder=GeminiRerankerClient(
            config=LLMConfig(api_key=GOOGLE_API_KEY, model="gemini-1.5-flash-latest"),
        )
    )

    try:
        # Initialize the graph database with Graphiti's indices.
        # This only needs to be done once per database.
        await graphiti.build_indices_and_constraints()

        # Add concert details using all three functions
        # await add_concert_details_one(graphiti)
        await add_concert_details_two(graphiti)
        # await add_concert_details_three(graphiti)

        print("\nAll concert episodes have been successfully added.")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Always close the connection to Neo4j when finished
        await graphiti.close()
        print('\nConnection closed')


if __name__ == '__main__':
    asyncio.run(main())