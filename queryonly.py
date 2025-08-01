#!/usr/bin/env python3
"""
interactive_query.py – A chat-like interface to query a Graphiti database and search for flights.
====================================================================================================
► Connects to a Neo4j database populated by Graphiti.
► Uses a specialized, stateful agent to handle conversational flight searches.
► Allows the user to select a search recipe for targeted queries.
► Continuously prompts for input until the user types 'exit'.
► Intelligently displays results based on the recipe type (Nodes or Edges).
"""

# ── 1.  Standard imports ────────────────────────────────────────────────────
import asyncio
import logging
import os
from dotenv import load_dotenv
import json
from datetime import date

# ── 2.  Graphiti-specific imports ──────────────────────────────────────────
from graphiti_core import Graphiti
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF, NODE_HYBRID_SEARCH_RRF, EDGE_HYBRID_SEARCH_RRF

# ── 3.  LangChain-specific imports ──────────────────────────────────────────
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from langchain_google_genai import GoogleGenerativeAI
from langchain_core.output_parsers import BaseLLMOutputParser, JsonOutputParser
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.exceptions import OutputParserException
from langchain.tools import tool
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain import hub
from langchain.memory import ConversationSummaryBufferMemory
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ── 4.  Custom Flight Agent import ──────────────────────────────────────────
from travel_agent import ConversationalTravelAgent

# ── 5. Rich library for enhanced UI ───────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner

# ── 6.  Logging setup ───────────────────────────────────────────────────────
# Note: Logging level set to WARNING to keep the chat interface clean.
# Change to logging.INFO for more detailed backend messages.
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# ── 7.  Env vars & config ───────────────────────────────────────────────────
load_dotenv()

# --- IMPORTANT: Make sure these credentials are correct ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyCbJ2UBDvzztgs-gor8eyi54mWtDsugeNY")
NEO4J_URI      = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "localtestkb123")

if not GOOGLE_API_KEY or "REPLACE" in GOOGLE_API_KEY:
    raise RuntimeError("Please set your GOOGLE_API_KEY in the script or .env file.")

# ── 8. Rich Console Initialization ────────────────────────────────────────
console = Console()

# ── 9.  LLM and Agent Initialization ─────────────────────────────────────────
reasoning_engine = GoogleGenerativeAI(
    model="gemini-1.5-pro-latest",
    google_api_key=GOOGLE_API_KEY,
    safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH},
    temperature=0.7,
    max_tokens=2000, # Increased tokens to handle potentially long flight results
    model_kwargs={"top_p": 1.0, "top_k":3, "presence_penalty": 0.5, "frequency_penalty": 0.5}
)

memory = ConversationSummaryBufferMemory(
    llm=reasoning_engine,
    memory_key="chat_history",
    return_messages=True
)

# ── 10.  Initialize the Conversational Travel Agent ──────────────────────────
logger.info("Initializing Conversational Travel Agent...")
try:
    flight_agent = ConversationalTravelAgent()
    logger.info("Conversational Travel Agent initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize ConversationalTravelAgent: {e}")
    flight_agent = None


# ── 11. Helper function to print results with Rich ───────────────────────────
def print_rich_results(results):
    """Dynamically prints nodes or edges from a search result object using Rich tables."""
    if hasattr(results, 'nodes') and results.nodes:
        table = Table(title="\n[bold green]Knowledge Graph Node Results[/bold green]", show_header=True, header_style="bold magenta", border_style="dim")
        table.add_column("Name", style="cyan", no_wrap=False, width=20)
        table.add_column("Labels", style="yellow", width=15)
        table.add_column("Summary", style="white", no_wrap=False)

        for node in results.nodes:
            table.add_row(node.name, ', '.join(node.labels), node.summary)
        console.print(table)

    elif hasattr(results, 'edges') and results.edges:
        table = Table(title="\n[bold blue]Knowledge Graph Fact Results[/bold blue]", show_header=True, header_style="bold magenta", border_style="dim")
        table.add_column("Fact", style="cyan", no_wrap=False)
        table.add_column("Valid From", style="yellow", width=12)

        for edge in results.edges:
            valid_date = edge.valid_at.strftime('%Y-%m-%d') if hasattr(edge, 'valid_at') and edge.valid_at else "N/A"
            table.add_row(edge.fact, valid_date)
        console.print(table)
    else:
        # This message will be shown if a tool is called but returns nothing.
        # The final answer from the agent will still be printed.
        console.print("\n[dim]Tool executed but found no specific nodes or edges to display.[/dim]")


# ── 12. Agent Tools Definition ───────────────────────────────────────────────

@tool
async def knowledge_graph_search(query: str) -> str:
    """
    Searches the company's internal knowledge base for established policies, offers, and general information.
    Use this tool to answer questions about non-dynamic company data. This includes return policies, shipping rules,
    current promotions, special offers, product features, business hours and event updates. Do NOT use this for real-time
    data like flight searches or live inventory checks.

    Args:
        query (str): The user's question about company policies, promotions, or general info.
    """
    logger.info("Initializing Graphiti and connecting to Neo4j...")
    graphiti = Graphiti(
        NEO4J_URI,
        NEO4J_USER,
        NEO4J_PASSWORD,
        llm_client=GeminiClient(
            config=LLMConfig(api_key=GOOGLE_API_KEY, model="gemini-1.5-flash"),
        ),
        embedder=GeminiEmbedder(
            config=GeminiEmbedderConfig(api_key=GOOGLE_API_KEY, embedding_model="embedding-001"),
        ),
        cross_encoder=GeminiRerankerClient(
            config=LLMConfig(api_key=GOOGLE_API_KEY, model="gemini-1.5-flash-latest"),
        ),
    )
    try:
        logger.info(f"Performing Knowledge Graph Search for query: '{query}'")
        results = await graphiti._search(
            query=query,
            config=COMBINED_HYBRID_SEARCH_RRF,
        )
        # Use the new rich printer for mid-run visualization
        print_rich_results(results)
        return json.dumps(results.dict() if hasattr(results, "dict") else results, default=str)
    except Exception as e:
        logger.error(f"An error occurred during knowledge graph search: {e}")
        return json.dumps({"error": str(e)})
    finally:
        logger.info("Closing connection to Neo4j...")
        await graphiti.close()


@tool
async def flight_search_tool(query: str) -> str:
    """
    Searches for flight information using a specialized conversational travel agent.
    Use this tool for ANY user requests related to finding, booking, or searching for flights, air tickets, or travel itineraries.
    The input should be the user's natural language query, like 'I want to fly from Lahore to Karachi tomorrow for 2 people'.
    The tool is conversational; it will return flight options if all information is available, or it will return a question asking for the specific details it still needs.
    """
    if not flight_agent:
        return "The flight search tool is currently unavailable due to an initialization error."
    try:
        logger.info(f"Flight Search Tool received query: '{query}'")
        # The travel agent is stateful. We process the user's query to update its internal state.
        result = flight_agent.process_user_input_conversationally(query)

        # Check if the agent has gathered enough information to perform a search.
        if result.get("type") == "confirmation":
            logger.info("Sufficient information gathered. Executing flight search...")
            # If all info is present, the agent is ready. Execute the actual flight search.
            search_result = flight_agent.execute_flight_search_with_conversation()
            # Return the complete, user-friendly response from the search execution.
            return search_result.get("response", "Search completed, but no response was generated.")
        else:
            logger.info("Information is missing. Returning the agent's request for more details.")
            # If information is still missing, return the agent's response which asks for it.
            return result.get("response", "I need more information to proceed with the flight search.")
    except Exception as e:
        logger.error(f"An error occurred in the flight search tool: {e}", exc_info=True)
        return f"An unexpected error occurred while trying to search for flights: {e}"


# ── 13. Agent and Executor Setup ───────────────────────────────────────────

# Define the list of tools the agent can use
tools = [
    knowledge_graph_search,
    flight_search_tool
]

# Pull the agent prompt from the hub
json_prompt = hub.pull('hwchase17/structured-chat-agent')

# Create the agent
agent = create_structured_chat_agent(
    tools=tools,
    prompt=json_prompt,
    stop_sequence=True,
    llm=reasoning_engine
)

# Create the Agent Executor
executor = AgentExecutor.from_agent_and_tools(
    agent=agent,
    tools=tools,
    verbose=False, # Set to False for a cleaner UI; spinner will indicate activity
    memory=memory,
    max_execution_time=4000000,
    handle_parsing_errors=True,
)

# ── 14. Main Interactive Loop ──────────────────────────────────────────────

if __name__ == "__main__":
    console.print(Panel("[bold green]Welcome to the Interactive Query Assistant![/bold green]\nAsk about company policies or search for flights.\nType '[cyan]exit[/cyan]' to quit.",
                        title="[bold]Graphiti Chat[/bold]", border_style="blue"))
    while True:
        try:
            user_input = console.input("\n[bold cyan]You: [/bold cyan]").strip()
            if user_input.lower() == "exit":
                console.print("\n[bold yellow]Goodbye![/bold yellow]")
                break
            if not user_input:
                continue

            # Use a Live spinner to show the agent is working
            with Live(Spinner("dots", text=" Assistant is thinking..."), console=console, transient=True, refresh_per_second=10) as live:
                result = asyncio.run(executor.ainvoke({'input': user_input}))

            # Print the final answer from the agent, styled
            console.print(f"\n[bold green]Assistant:[/bold green] {result.get('output')}")

        except (KeyboardInterrupt, EOFError):
            console.print("\n\n[bold yellow]Goodbye![/bold yellow]")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            console.print(f"\n[bold red]An unexpected error occurred:[/bold red] {e}")