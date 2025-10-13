import json
import asyncio
import logging
from datetime import datetime
import os

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependency
    DOTENV_AVAILABLE = False

    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return None

# Load environment variables (ensure local .env alongside this file is read)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(DOTENV_PATH)

# Setup logging for knowledge graph operations
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

if not DOTENV_AVAILABLE:
    logger.warning("python-dotenv not installed. Environment variables from .env will not be loaded.")

# Groq client is optional – handle gracefully if SDK or key are missing
try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    Groq = None  # type: ignore
    GROQ_SDK_AVAILABLE = False
    logger.warning(
        "Groq SDK not installed. LLM-based query simplification will be skipped."
    )

# Graphiti-specific imports for knowledge graph search
try:
    from graphiti_core import Graphiti
    from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
    from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
    from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
    from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF
    GRAPHITI_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Graphiti imports failed: {e}. Knowledge graph search will use fallback mode.")
    GRAPHITI_AVAILABLE = False

# Knowledge Graph Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NEO4J_URI      = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "localtestkb123")

# Groq client configuration (optional)
groq_client = None
GROQ_MODEL_DEFAULT = "groq/compound-mini"

if GROQ_SDK_AVAILABLE:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            groq_client = Groq(api_key=groq_api_key)
        except Exception as exc:  # Defensive: avoid crashing on client init
            logger.warning(f"Groq client initialization failed: {exc}")
            groq_client = None
    else:
        logger.warning("GROQ_API_KEY not set. Groq-powered features will be disabled.")
else:
    logger.warning("Groq SDK unavailable. Some advanced features are disabled.")

try:
    from flight_tool import search_flights_with_context
    FLIGHT_TOOL_AVAILABLE = True
except ModuleNotFoundError as exc:
    FLIGHT_TOOL_AVAILABLE = False
    _flight_tool_import_error = exc

    def search_flights_with_context(*_args, **_kwargs):
        raise RuntimeError("Flight search dependencies are missing")

    logger.warning(
        "Flight tool import failed (%s). Flight search functionality will be limited.",
        exc,
    )

def tool(func):
    """Decorator to mark functions as tools"""
    func.is_tool = True
    return func

# =============================================================================
# TOOLS SECTION - Each tool is a separate function with @tool decorator
# =============================================================================

@tool
def flight_search_and_extraction_tool(user_input: str, current_context: dict = None, search_mode: bool = False) -> dict:
    """
    Flight Search and Travel Information Extraction Tool

    Purpose:
        Handles all user requests related to air travel — including extracting trip details from 
        natural language and performing live flight searches.

    Use this tool for:
        - Finding flights based on origin, destination, travel dates, and passenger details
        - Extracting structured travel details (cities, airports, dates, passenger counts, flight class) 
        from free-form user messages
        - Processing partial travel requests to fill in missing details before searching
        - Handling specific flight preferences (airlines, times, budget, class)
        - Updating or confirming existing flight booking details in context

    Behavior:
        - If the user provides complete trip information → search flights immediately
        - If information is incomplete → extract details and update the booking context
        - Automatically switches between "extraction mode" and "search mode" depending on input completeness

    Example triggers:
        "Find flights from Lahore to Dubai next Monday"
        "Book a return ticket from Islamabad to Karachi for two passengers"
        "I need a flight to London on the 15th, business class"

    Args:
        user_input (str): The user's message containing travel details or a flight search request
        current_context (dict): Existing booking context to help extract or refine details
        search_mode (bool): If True, forces flight search; if False, auto-detect mode

    Returns:
        dict: Extracted travel details, flight search results, or both (with operation status)
    """

    if not FLIGHT_TOOL_AVAILABLE:
        exc_info = globals().get("_flight_tool_import_error")
        details = str(exc_info) if exc_info else "missing optional dependencies"
        missing_msg = (
            "Flight search dependencies are not installed. "
            f"Install optional NLP packages to enable this feature ({details})."
        )
        return {
            "status": "error",
            "action": "dependency_missing",
            "message": missing_msg,
            "extracted_info": {},
            "updated_context": current_context or {},
            "missing_info": []
        }

    try:
        # Always extract travel information using contextual awareness - USE THE SAME LOGIC AS OLD AGENT
        from flight_tool import extract_travel_parameters
        
        # Start with current context to determine missing info for smart contextual query
        temp_context = current_context.copy() if current_context else {}
        
        # Calculate missing info for smart contextual query creation
        missing_info = []
        if not temp_context.get("source"):
            missing_info.append("departure_city")
        if not temp_context.get("destination"):
            missing_info.append("destination_city")
        if not temp_context.get("departure_date"):
            missing_info.append("departure_date")
        if temp_context.get("flight_type") == "return" and not temp_context.get("return_date"):
            missing_info.append("return_date")
        
        # Create contextual query with smart return date enhancement
        contextual_query = create_contextual_query(user_input, current_context, missing_info)
        # Pass None as current_context to prevent double contextualization in extract_travel_parameters
        extraction_result = extract_travel_parameters(contextual_query)
        
        # Start with current context
        updated_context = current_context.copy() if current_context else {}
        
        if extraction_result.get('status') == 'success':
            extracted_info = extraction_result.get('extracted_info', {})
            
        # Update context with newly extracted information - EXACTLY like old agent
        for key, value in extracted_info.items():
            if value is not None and value != '' and value != 'null':
                # Special handling for passengers to avoid resetting
                if key == 'passengers':
                    updated_context['passengers'] = value
                elif key not in ['departure_date', 'return_date'] or value:
                    # Special handling for location codes
                    if key in ['source', 'destination'] and (not value or len(str(value)) < 2):
                        continue
                    updated_context[key] = value
        
        # IMPORTANT FIX: If flight_type changed to one_way, clear return_date
        if extracted_info.get('flight_type') == 'one_way' and updated_context.get('return_date'):
            updated_context['return_date'] = None
            print("🔧 Cleared return_date because flight_type changed to one_way")        # Set defaults exactly like old agent - ONLY if not already set
        if not updated_context.get('passengers'):
            updated_context['passengers'] = {"adults": 1, "children": 0, "infants": 0}
        if not updated_context.get('flight_class'):
            updated_context['flight_class'] = 'economy'
        if not updated_context.get('flight_type'):
            updated_context['flight_type'] = 'one_way'
        
        # Recalculate missing info after extraction for final decision making
        final_missing_info = []
        if not updated_context.get("source"):
            final_missing_info.append("departure_city")
        if not updated_context.get("destination"):
            final_missing_info.append("destination_city")
        if not updated_context.get("departure_date"):
            final_missing_info.append("departure_date")
        if updated_context.get("flight_type") == "return" and not updated_context.get("return_date"):
            final_missing_info.append("return_date")

        # Determine if we should search for flights
        confirmation_words = ['yes', 'yeah', 'yep', 'correct', 'right', 'okay', 'ok', 'sure', 'confirm', 'search', 'find flights']
        is_confirmation = any(word in user_input.lower().strip() for word in confirmation_words)
        
        should_search = (
            search_mode or  # Forced search mode
            (not final_missing_info and is_confirmation) or  # User confirmed and we have complete info
            any(word in user_input.lower() for word in ['search', 'find flights', 'book', 'ready'])
        )
        
        if should_search and not final_missing_info:
            # Perform flight search - avoid double extraction when triggered by search keywords
            if any(word in user_input.lower() for word in ['search', 'find flights', 'book', 'ready']):
                # Pass a simple generic input to avoid re-processing the modification request
                search_result = search_flights_with_context("search for flights", updated_context)
            else:
                # Use original input for other cases
                search_result = search_flights_with_context(contextual_query, updated_context)

            search_status = search_result.get("status", "error")
            formatted_display = search_result.get("formatted_display")
            if not formatted_display:
                formatted_display = search_result.get("message", "Flight details not available")
            message = search_result.get(
                "message",
                "Flight search completed" if search_status == "success" else "Flight search could not be completed"
            )
            
            return {
                "status": search_status,
                "action": "flight_search",
                "message": message,
                "extracted_info": extraction_result.get('extracted_info', {}),
                "updated_context": updated_context,
                "flight_results": search_result.get("flight_results"),
                "formatted_display": formatted_display,
                "search_type": search_result.get("search_type"),
                "missing_info": []
            }
        else:
            # Return extraction results with missing information
            return {
                "status": "success", 
                "action": "info_extraction",
                "message": "Travel information extracted",
                "extracted_info": extraction_result.get('extracted_info', {}),
                "updated_context": updated_context,
                "missing_info": final_missing_info
            }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Flight tool failed: {str(e)}",
            "action": "error",
            "extracted_info": {},
            "missing_info": [],
            "formatted_display": "Unable to process flight request at this time."
        }

def create_contextual_query(user_input: str, current_context: dict = None, missing_info: list = None) -> str:
    """Create a contextual query, then simplify it via Groq LLM into the target format."""
    contextual_query = user_input
    if not current_context:
        current_context = {}
    try:
        # ---- OLD AGENT STYLE STRING BUILD ----
        natural_parts = []
        if current_context.get('source') and current_context.get('destination'):
            natural_parts.append(f"travel from {current_context['source']} to {current_context['destination']}")
        elif current_context.get('source'):
            natural_parts.append(f"travel from {current_context['source']}")
        elif current_context.get('destination'):
            natural_parts.append(f"go to {current_context['destination']}")

        passengers = current_context.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
        passenger_parts = []
        if passengers['adults'] > 0:
            passenger_parts.append(f"{passengers['adults']} adult{'s' if passengers['adults'] > 1 else ''}")
        if passengers['children'] > 0:
            passenger_parts.append(f"{passengers['children']} child{'ren' if passengers['children'] > 1 else ''}")
        if passengers['infants'] > 0:
            passenger_parts.append(f"{passengers['infants']} infant{'s' if passengers['infants'] > 1 else ''}")
        if passenger_parts:
            natural_parts.append(f"with {' and '.join(passenger_parts)}")

        if current_context.get('departure_date'):
            natural_parts.append(f"departing on {current_context['departure_date']}")

        if (current_context.get('return_date') and 
            current_context.get('flight_type') == 'return'):
            natural_parts.append(f"returning on {current_context['return_date']}")

        if current_context.get('flight_class'):
            natural_parts.append(f"in {current_context['flight_class'].replace('_', ' ')} class")

        if current_context.get('flight_type') == 'return':
            natural_parts.append("round trip")
        elif current_context.get('flight_type') == 'one_way':
            natural_parts.append("one way")

        if current_context.get('content_provider'):
            natural_parts.append(f"with {current_context['content_provider'].replace('_', ' ').title()}")

        if natural_parts:
            base_context = " ".join(natural_parts)
            enhanced_user_input = user_input
            if (missing_info and 'return_date' in missing_info and 
                current_context.get('flight_type') == 'return' and 
                not current_context.get('return_date') and 
                current_context.get('departure_date')):
                if not any(word in user_input.lower() for word in ['return', 'back', 'returning', 'come back']):
                    enhanced_user_input = f"return {user_input}"
            contextual_query = f"{base_context}. NOW USER SAYS :{enhanced_user_input}"

            print(f"🔍 Contextual query created: {contextual_query}")

        # ---- GROQ LLM SIMPLIFICATION ----
        prompt = (
            "Simplify the following ambiguous travel query into the format:\n"
            "'I need a flight from <SOURCE> to <DESTINATION> on departing <DATE> "
            "and returning <RETURN_EXPRESSION>' "
            "(RETURN_EXPRESSION can be: 'after <N> days', 'on <DAY_OF_WEEK>', 'on <DATE>', or any other exact relative phrase given by the user. "
            "If no return is specified, say 'one way'). "
            "Preserve exact return details from the latest user input — do NOT replace them with an assumed number of days."
            "Never invent or guess a return duration or departure date"
            "Include passenger details only if explicitly specified.\n"
            "Dates can also be relative (e.g., 'tomorrow','next week','in 5 days','on Wednesday','first Monday after departure').\n"
            "Return ONLY in JSON format like:\n"
            "{\n    \"simplified_query\": \"...\"\n}"
            f"\nContext: {contextual_query}"
        )


        if not groq_client:
            logger.info("Groq client unavailable; returning contextual query without LLM simplification.")
            return contextual_query or user_input

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_DEFAULT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=150,
            response_format={"type": "json_object"}  # Enforce JSON output
        )

        # Extract JSON and return only the value
        simplified_json = json.loads(response.choices[0].message.content)
        simplified_query = simplified_json.get("simplified_query", "")
        print(f"🤖 Groq LLM simplified query: {simplified_query}")
        return simplified_query

    except Exception as e:
        print(f"Error creating contextual query: {e}")

    return user_input


@tool
def knowledge_graph_search_tool(query: str) -> dict:
    """
    Knowledge Graph Search Tool — Company Information, Policies, and Offers

    Purpose:
        Retrieves answers from the company's internal knowledge base about fixed, non-real-time information.

    Use this tool for:
        - Company policies (refunds, cancellations, changes, baggage rules)
        - Current promotions, discounts, and special offers
        - Business hours, contact information, and location details
        - Product or service descriptions (e.g., bus routes, seat types, amenities)
        - Payment methods, fees, and procedural guides
        - Event schedules or announcements that are not live data

    Do NOT use this tool for:
        - Real-time flight, bus, or ticket searches
        - Live availability, pricing, or inventory checks

    Example triggers:
        "What is your refund policy for cancelled trips?"
        "Are there any discounts available for students?"
        "What payment methods do you accept?"
        "Tell me about your business class bus service."
        "When is your office open?"

    Args:
        query (str): The user's question about company policies, services, promotions, or general info.

    Returns:
        dict: Knowledge graph search results containing relevant company information
    """
    try:
        # Check if graphiti_core is available and all required environment variables are set
        if not GRAPHITI_AVAILABLE:
            raise Exception("Graphiti core libraries are not available")
            
        if not all([GOOGLE_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
            raise Exception("Missing required environment variables for knowledge graph")
            
        # Run the async knowledge graph search
        result = asyncio.run(_async_knowledge_graph_search(query))
        
        return {
            "status": "success",
            "source": "knowledge_graph",
            "data": result,
            "message": "Knowledge graph search completed successfully"
        }
        
    except Exception as e:
        logger.warning(f"Knowledge graph search failed: {e}. Using fallback information.")
        
        fallback_info = {
            "company": "BookMe.pk helps you compare and purchase bus, flight, and event tickets across Pakistan through the BookMe website and mobile apps.",
            "services": [
                "Domestic and international flight searches",
                "Bus tickets across major Pakistani routes",
                "Event and cinema ticketing",
                "Round-the-clock customer support via app, website, and helpline"
            ],
            "offers": [
                "Discount campaigns rotate frequently; check the BookMe app or website's deals section for the latest promotions.",
                "Enable app notifications or follow @BookMePk on social channels to catch limited-time promo codes.",
                "Bulk and corporate travelers can request tailored offers through support@bookme.pk."
            ],
            "support": "Need help? Contact BookMe support at support@bookme.pk, call (042) 111-266-563, or start a live chat in the BookMe app."
        }

        return {
            "status": "success",
            "source": "fallback",
            "info": fallback_info,
            "message": "Knowledge graph unavailable; responded with fallback information",
            "error": str(e)
        }

async def _async_knowledge_graph_search(query: str) -> str:
    """
    Internal async function to perform knowledge graph search.
    """
    if not GRAPHITI_AVAILABLE:
        raise Exception("Graphiti libraries not available")
        
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
        
        # Format results for return
        formatted_results = []
        
        # Process nodes
        if hasattr(results, 'nodes') and results.nodes:
            for node in results.nodes:
                formatted_results.append({
                    "type": "node",
                    "name": node.name,
                    "labels": node.labels if hasattr(node, 'labels') else [],
                    "summary": node.summary if hasattr(node, 'summary') else ""
                })
        
        # Process edges/facts
        if hasattr(results, 'edges') and results.edges:
            for edge in results.edges:
                formatted_results.append({
                    "type": "fact",
                    "fact": edge.fact if hasattr(edge, 'fact') else str(edge),
                    "valid_at": edge.valid_at.strftime('%Y-%m-%d') if hasattr(edge, 'valid_at') and edge.valid_at else "N/A"
                })
        
        return json.dumps(formatted_results, default=str)
        
    except Exception as e:
        logger.error(f"An error occurred during knowledge graph search: {e}")
        raise
    finally:
        logger.info("Closing connection to Neo4j...")
        await graphiti.close()

# =============================================================================
# AGENT SECTION - Conversation management and tool orchestration
# =============================================================================

class ConversationalTravelAgent:
    """
    Conversational travel agent that manages user interactions and orchestrates tools.
    
    The agent handles conversation flow, maintains context, and decides which tools
    to use based on user input and conversation state.
    """
    
    def __init__(self):
        # Initialize LLM client
        self.groq_client = groq_client
        self.model_name = "meta-llama/llama-4-scout-17b-16e-instruct"

        if not self.groq_client:
            logger.info("Groq client unavailable for ConversationalTravelAgent; operating without LLM calls.")
            self.model_name = None
        
        # Conversation state
        self.conversation_history = []
        self.current_booking_info = {}
        
        # Available tools - automatically discovered by @tool decorator
        self.available_tools = self._discover_tools()

    def _discover_tools(self) -> dict:
        """Discover all available tools marked with @tool decorator"""
        tools = {}
        
        # Get all functions in the current module
        import sys
        current_module = sys.modules[__name__]
        
        for name in dir(current_module):
            obj = getattr(current_module, name)
            if callable(obj) and hasattr(obj, 'is_tool') and obj.is_tool:
                tools[name] = {
                    'function': obj,
                    'docstring': obj.__doc__ or 'No description available'
                }
        
        return tools

    def _select_appropriate_tool(self, user_input: str, conversation_context: str) -> str:
        """Use LLM to intelligently select the most appropriate tool based on docstring analysis"""
        try:
            # Build comprehensive tool descriptions for intelligent selection
            tool_descriptions = ""
            for tool_name, tool_info in self.available_tools.items():
                # Get the full docstring for better context
                docstring = tool_info['docstring']
                # Extract the main description and use cases
                if docstring:
                    # Get first paragraph and use cases
                    lines = docstring.strip().split('\n')
                    description = lines[0].strip()
                    
                    # Find "Use this tool for:" section
                    use_cases = []
                    in_use_section = False
                    for line in lines:
                        line = line.strip()
                        if 'Use this tool for:' in line:
                            in_use_section = True
                            continue
                        elif in_use_section and line.startswith('- '):
                            use_cases.append(line[2:])  # Remove '- ' prefix
                        elif in_use_section and (line.startswith('Args:') or line.startswith('Returns:') or not line):
                            break
                    
                    tool_descriptions += f"\n{tool_name}:\n"
                    tool_descriptions += f"  Description: {description}\n"
                    if use_cases:
                        tool_descriptions += f"  Use cases:\n"
                        for use_case in use_cases:
                            tool_descriptions += f"    - {use_case}\n"
                else:
                    tool_descriptions += f"\n{tool_name}: No description available\n"

            prompt = f"""
                You are a travel assistant's intelligent tool selector.

                Your ONLY job: Choose exactly ONE tool name from this list:
                {', '.join(self.available_tools.keys())}

                ### Available Tools
                {tool_descriptions}

                ---

                ### Decision Rules:
                1. If the request is about flights, flight booking, searching flights, destinations, itineraries, dates, airports, tickets, or passengers → choose: flight_search_and_extraction_tool
                2. If the request is about the company, policies, offers, promotions, deals, services, buses, payments, cancellations, refunds, or general BookMe information → choose: knowledge_graph_search_tool
                3. Use the **conversation context** to disambiguate vague queries.
                4. Respond ONLY with the exact tool name from the list — no extra text, punctuation, or formatting.

                ---

                ### Examples:
                User: "Find flights from Lahore to Dubai for next Monday"
                → flight_search_and_extraction_tool

                User: "What's your refund policy for cancelled trips?"
                → knowledge_graph_search_tool

                User: "Book a return ticket from Islamabad to Karachi"
                → flight_search_and_extraction_tool

                User: "Do you have any promotions this week?"
                → knowledge_graph_search_tool

                ---

                ### Current Conversation Context:
                {conversation_context}

                ### User's Request:
                "{user_input}"

                ---

                Tool name:"""


            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model_name,
                    temperature=0.1,  # Low temperature for consistent tool selection
                    max_tokens=100
                )
                selected_tool = chat_completion.choices[0].message.content.strip()
                
                # Clean the response (remove any extra text)
                for tool_name in self.available_tools.keys():
                    if tool_name in selected_tool:
                        selected_tool = tool_name
                        break
                
                # Validate the selected tool exists
                if selected_tool in self.available_tools:
                    return selected_tool
                else:
                    # Use semantic fallback based on docstring analysis
                    return self._semantic_tool_fallback(user_input)
            else:
                # Use semantic fallback when LLM is not available
                return self._semantic_tool_fallback(user_input)
                    
        except Exception as e:
            print(f"Tool selection failed: {e}")
            return self._semantic_tool_fallback(user_input)

    def _semantic_tool_fallback(self, user_input: str) -> str:
        """Intelligent fallback tool selection based on semantic analysis of docstrings"""
        user_lower = user_input.lower()
        
        # Analyze each tool's docstring for semantic matching
        tool_scores = {}
        
        for tool_name, tool_info in self.available_tools.items():
            docstring = tool_info['docstring'].lower() if tool_info['docstring'] else ""
            score = 0
            
            # Extract key terms from docstring
            if 'flight' in docstring or 'travel' in docstring or 'extraction' in docstring:
                flight_terms = ['flight', 'fly', 'travel', 'trip', 'destination', 'departure', 'arrival', 
                               'airport', 'ticket', 'passenger', 'airline', 'book', 'search', 'date']
                score += sum(2 for term in flight_terms if term in user_lower)
                
            if 'knowledge' in docstring or 'company' in docstring or 'policies' in docstring:
                knowledge_terms = ['company', 'policy', 'information', 'about', 'service', 'support',
                                 'offer', 'deal', 'promotion', 'discount', 'bus', 'contact', 'help',
                                 'refund', 'payment', 'cancellation', 'bookme']
                score += sum(2 for term in knowledge_terms if term in user_lower)
            
            tool_scores[tool_name] = score
        
        # Select tool with highest score
        if tool_scores:
            best_tool = max(tool_scores, key=tool_scores.get)
            if tool_scores[best_tool] > 0:
                return best_tool
        
        # Default fallback
        return 'flight_search_and_extraction_tool'

    # =============================================================================
    # CONVERSATION MANAGEMENT METHODS
    # =============================================================================

    def add_to_conversation(self, message, sender="user"):
        """Add message to conversation history"""
        self.conversation_history.append({
            "message": message,
            "sender": sender,
            "timestamp": datetime.now().isoformat()
        })

    def generate_conversational_response(self, user_input, context_info=None, tool_result=None):
        """Generate natural conversational responses using LLM"""
        try:
            # Build conversation context
            recent_conversation = "\n".join([
                f"{msg['sender'].title()}: {msg['message']}" 
                for msg in self.conversation_history[-4:]  # Last 4 messages for context
            ])
            
            current_info_summary = self._build_booking_info_summary()
            
            # Include tool result context if available
            tool_context = ""
            extracted_data_context = ""
            if tool_result:
                if tool_result.get('status') == 'success':
                    tool_context = f"Tool executed successfully. Result available for user."
                    
                    # Include extracted information to prevent misinterpretation
                    extracted_info = tool_result.get('extracted_info', {})
                    if extracted_info:
                        extracted_items = []
                        for key, value in extracted_info.items():
                            if value is not None and value != '' and value != 'null':
                                extracted_items.append(f"{key}: {value}")
                        
                        if extracted_items:
                            extracted_data_context = f"\nIMPORTANT: The extraction tool has already processed the user's input and extracted: {', '.join(extracted_items)}. Use these extracted values as the truth - do NOT reinterpret the original user input."
                else:
                    tool_context = f"Tool execution had issues: {tool_result.get('message', 'Unknown error')}"

            prompt = f"""
                You are a friendly, helpful travel agent having a natural conversation with a traveler. Be conversational, warm, and efficient.

                CURRENT TRAVEL INFORMATION (This is the AUTHORITATIVE source - use EXACTLY this information):
                {current_info_summary}

                Recent conversation:
                {recent_conversation}

                Context: {context_info if context_info else "Continue natural conversation"}
                Tool context: {tool_context}{extracted_data_context}

                User just said: "{user_input}"

                CRITICAL INSTRUCTIONS:
                1. The CURRENT TRAVEL INFORMATION above shows the EXACT travel details after processing the user's request
                2. If it says "From: KHI, To: LHE" that means traveling FROM Karachi TO Lahore - use this EXACTLY
                3. If it says "From: LHE, To: KHI" that means traveling FROM Lahore TO Karachi - use this EXACTLY  
                4. DO NOT reinterpret the user's words like "vice versa" - the CURRENT TRAVEL INFORMATION already reflects any changes
                5. Always reference the cities using the information in CURRENT TRAVEL INFORMATION
                6. Be natural and conversational - like talking to a friend
                7. Don't repeat information unnecessarily 
                8. If you have most details, smoothly ask for what's still needed
                9. If confirming details, be concise and clear
                10. Show enthusiasm but don't overdo it
                11. Avoid repetitive questions about same information
                12. If user changes something, acknowledge the change naturally using the CURRENT TRAVEL INFORMATION
                13. Keep responses focused and helpful
                14. NEVER mention booking confirmation, payment, or ticket issuance - you are only SEARCHING for flights
                15. Use terms like "search for flights", "find options", "look for flights" - NOT "book", "confirm booking", or "process payment"

                Generate a response using the EXACT travel details from CURRENT TRAVEL INFORMATION:
                """
           
            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model_name,
                    temperature=0.7,
                    max_tokens=500,
                    top_p=0.9
                )
                return chat_completion.choices[0].message.content.strip()
            else:
                raise Exception("Groq client not initialized")
            
        except Exception as e:
            print(f"LLM generation failed: {e}")
            if "missing" in str(context_info).lower():
                return "I just need a couple more details to find your flights. What else can you tell me about your trip?"
            return "Tell me more about your travel plans!"

    def _build_booking_info_summary(self) -> str:
        """Build a summary of current booking information"""
        if not self.current_booking_info:
            return ""
            
        info_parts = []
        if self.current_booking_info.get('source'):
            info_parts.append(f"From: {self.current_booking_info['source']}")
        if self.current_booking_info.get('destination'):
            info_parts.append(f"To: {self.current_booking_info['destination']}")
        if self.current_booking_info.get('departure_date'):
            info_parts.append(f"Departure: {self.current_booking_info['departure_date']}")
        if self.current_booking_info.get('return_date'):
            info_parts.append(f"Return: {self.current_booking_info['return_date']}")
        if self.current_booking_info.get('flight_class'):
            info_parts.append(f"Class: {self.current_booking_info['flight_class']}")
        if self.current_booking_info.get('content_provider'):
            info_parts.append(f"Airline: {self.current_booking_info['content_provider']}")
        
        # Add passengers info properly
        passengers = self.current_booking_info.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
        total_passengers = passengers['adults'] + passengers['children'] + passengers['infants']
        info_parts.append(f"Passengers: {total_passengers} total ({passengers['adults']} adults, {passengers['children']} children, {passengers['infants']} infants)")
        
        if info_parts:
            return f"Current booking info: {', '.join(info_parts)}"
        return ""

    def update_booking_info_intelligently(self, extracted_info):
        """Update booking info while preserving existing information"""
        if not extracted_info:
            return
                
        # Special handling for passengers to avoid resetting
        if extracted_info.get('passengers'):
            self.current_booking_info['passengers'] = extracted_info['passengers']
        elif not self.current_booking_info.get('passengers'):
            self.current_booking_info['passengers'] = {"adults": 1, "children": 0, "infants": 0}
        
        # Update other fields - ONLY if the extracted value is not None/empty/null
        for key, value in extracted_info.items():
            if key != 'passengers' and value is not None and value != '' and value != 'null':
                if key in ['departure_date', 'return_date'] and not value:
                    continue
                if key in ['source', 'destination'] and (not value or len(str(value)) < 2):
                    continue
                self.current_booking_info[key] = value
        
        # IMPORTANT FIX: If flight_type changed to one_way, clear return_date
        if extracted_info.get('flight_type') == 'one_way' and self.current_booking_info.get('return_date'):
            self.current_booking_info['return_date'] = None
            print("🔧 Cleared return_date because flight_type changed to one_way")

    def identify_missing_information(self):
        """Identify what information is still needed"""
        missing = []
        
        if not self.current_booking_info.get("source"):
            missing.append("departure_city")
        if not self.current_booking_info.get("destination"):
            missing.append("destination_city")
        if not self.current_booking_info.get("departure_date"):
            missing.append("departure_date")
        # flight_class and flight_type are not required since we set defaults
        if self.current_booking_info.get("flight_type") == "return" and not self.current_booking_info.get("return_date"):
            missing.append("return_date")
            
        return missing

    def format_knowledge_graph_response(self, user_input, kg_data_json):
        """Format knowledge graph data into a conversational response"""
        try:
            import json
            kg_data = json.loads(kg_data_json) if isinstance(kg_data_json, str) else kg_data_json
            
            if not kg_data:
                return "I couldn't find specific information about that in our knowledge base. Is there anything else I can help you with?"
            
            response_parts = []
            
            # Process nodes and facts
            for item in kg_data:
                if item.get('type') == 'node':
                    if item.get('summary'):
                        response_parts.append(f"• {item['summary']}")
                elif item.get('type') == 'fact':
                    fact_text = item.get('fact', '')
                    valid_date = item.get('valid_at', '')
                    if fact_text:
                        if valid_date and valid_date != 'N/A':
                            response_parts.append(f"• {fact_text} (Valid from: {valid_date})")
                        else:
                            response_parts.append(f"• {fact_text}")
            
            if response_parts:
                intro = self.generate_knowledge_intro(user_input)
                return f"{intro}\n\n" + "\n".join(response_parts[:5])  # Limit to 5 items
            else:
                return "I found some information but couldn't format it properly. Is there anything specific you'd like to know?"
                
        except Exception as e:
            print(f"Error formatting knowledge graph response: {e}")
            return "I found some information but had trouble presenting it. Could you try asking in a different way?"
    
    def format_fallback_info_response(self, user_input, fallback_info):
        """Format fallback information into a conversational response"""
        try:
            if not fallback_info:
                return "I don't have specific information about that right now. Is there anything else I can help you with?"
            
            intro = self.generate_knowledge_intro(user_input)
            response_parts = [intro]
            
            # Format the fallback information
            if 'company' in fallback_info:
                response_parts.append(f"\n{fallback_info['company']}")
            
            if 'services' in fallback_info:
                services = ', '.join(fallback_info['services'])
                response_parts.append(f"\nOur services include: {services}")
            
            if 'support' in fallback_info:
                response_parts.append(f"\n{fallback_info['support']}")
            
            return ''.join(response_parts)
            
        except Exception as e:
            print(f"Error formatting fallback response: {e}")
            return "I have some information about BookMe, but I'm having trouble presenting it right now. Is there something specific you'd like to know?"
    
    def generate_knowledge_intro(self, user_input):
        """Generate an appropriate intro for knowledge-based responses"""
        if any(word in user_input.lower() for word in ['offer', 'offers', 'deal', 'deals', 'discount']):
            return "Here's what I found about current offers and deals:"
        elif any(word in user_input.lower() for word in ['bus', 'buses']):
            return "Here's information about bus services:"
        elif any(word in user_input.lower() for word in ['policy', 'policies']):
            return "Here are the relevant policies:"
        elif any(word in user_input.lower() for word in ['company', 'about']):
            return "Here's information about BookMe:"
        else:
            return "Here's what I found:"

    def generate_knowledge_based_response(self, user_input, knowledge_data, data_source):
        """Generate an intelligent response using LLM based on knowledge graph data"""
        try:
            # Prepare the knowledge data for the LLM
            if data_source == 'knowledge_graph':
                # Parse JSON data from knowledge graph
                import json
                try:
                    kg_data = json.loads(knowledge_data) if isinstance(knowledge_data, str) else knowledge_data
                    
                    if not kg_data:
                        return "I searched our knowledge base but couldn't find specific information about that. Is there anything else I can help you with?"
                    
                    # Format knowledge graph data for LLM
                    knowledge_context = "Knowledge Graph Search Results:\n"
                    for item in kg_data:
                        if item.get('type') == 'node':
                            if item.get('summary'):
                                knowledge_context += f"- {item['summary']}\n"
                        elif item.get('type') == 'fact':
                            fact_text = item.get('fact', '')
                            valid_date = item.get('valid_at', '')
                            if fact_text:
                                if valid_date and valid_date != 'N/A':
                                    knowledge_context += f"- {fact_text} (Valid from: {valid_date})\n"
                                else:
                                    knowledge_context += f"- {fact_text}\n"
                    
                except (json.JSONDecodeError, TypeError):
                    knowledge_context = f"Knowledge data: {str(knowledge_data)}"
                    
            else:  # fallback data
                # Format fallback data for LLM
                knowledge_context = "Company Information:\n"
                if isinstance(knowledge_data, dict):
                    for key, value in knowledge_data.items():
                        if isinstance(value, list):
                            knowledge_context += f"- {key.title()}: {', '.join(value)}\n"
                        else:
                            knowledge_context += f"- {key.title()}: {value}\n"
                else:
                    knowledge_context = f"Available information: {str(knowledge_data)}"

            # Generate LLM response with the knowledge data
            prompt = f"""You are a helpful travel assistant for BookMe. A user has asked a question and you have retrieved relevant information from the knowledge base.

                User's question: "{user_input}"

                Available information from knowledge base:
                {knowledge_context}

                Instructions:
                1. Answer the user's question directly and helpfully using the provided information
                2. Be conversational and friendly
                3. If the information directly answers their question, provide a clear response
                4. If the information is related but not exactly what they asked, acknowledge this and provide what you can
                5. If you don't have enough information to answer, be honest about it
                6. Always offer to help with anything else
                7. Keep the response focused and not too long

                Generate a helpful response:"""

            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model_name,
                    temperature=0.7,
                    max_tokens=500,
                    top_p=0.9
                )
                return chat_completion.choices[0].message.content.strip()
            else:
                # Fallback to simple formatting if LLM is not available
                if data_source == 'knowledge_graph':
                    return self.format_knowledge_graph_response(user_input, knowledge_data)
                else:
                    return self.format_fallback_info_response(user_input, knowledge_data)
                    
        except Exception as e:
            print(f"Error generating knowledge-based response: {e}")
            return "I found some information but had trouble processing it. Could you try asking in a different way?"

    # =============================================================================
    # MAIN CONVERSATION PROCESSING METHODS
    # =============================================================================

    def process_user_input_conversationally(self, user_input):
        """Process user input in a conversational manner - with proper tool selection"""
        self.add_to_conversation(user_input, "user")
        
        try:
            # First, determine which tool to use based on the user input
            conversation_context = self._build_booking_info_summary()
            selected_tool = self._select_appropriate_tool(user_input, conversation_context)
            
            print(f"🔧 Selected tool: {selected_tool}")  # Debug line
            
            # If it's a knowledge graph query, handle it differently
            if selected_tool == 'knowledge_graph_search_tool':
                tool_result = self.available_tools[selected_tool]['function'](user_input)
                
                # Generate conversational response based on knowledge graph result using LLM
                if tool_result.get('status') == 'success':
                    if tool_result.get('source') == 'knowledge_graph':
                        # Parse the knowledge graph data and let LLM generate intelligent response
                        kg_data = tool_result.get('data', '[]')
                        response = self.generate_knowledge_based_response(user_input, kg_data, 'knowledge_graph')
                    else:
                        # Fallback data - let LLM process this too
                        fallback_info = tool_result.get('info', {})
                        response = self.generate_knowledge_based_response(user_input, fallback_info, 'fallback')
                else:
                    response = "I'm sorry, I couldn't retrieve that information right now. Is there anything else I can help you with?"
                
                self.add_to_conversation(response, "assistant")
                return {
                    "response": response,
                    "type": "knowledge_graph_response",
                    "current_info": self.current_booking_info.copy(),
                    "missing_info": [],
                    "tool_used": selected_tool
                }
            
            # Otherwise, use the flight tool with contextual extraction
            tool_result = self.available_tools['flight_search_and_extraction_tool']['function'](user_input, self.current_booking_info, False)
            
            # Update current booking info intelligently like the old agent
            if tool_result.get('status') == 'success':
                self.current_booking_info = tool_result.get('updated_context', self.current_booking_info)
            
            # Set default values for common fields if not specified (only if not already set) - like old agent
            if not self.current_booking_info.get("flight_class"):
                self.current_booking_info["flight_class"] = "economy"
            if not self.current_booking_info.get("flight_type"):
                self.current_booking_info["flight_type"] = "one_way"
            if not self.current_booking_info.get('passengers'):
                self.current_booking_info['passengers'] = {"adults": 1, "children": 0, "infants": 0}
                            
            # Determine what's missing and generate appropriate response
            missing_info = self.identify_missing_information()
            
            # Handle flight search result first
            if tool_result.get('action') == 'flight_search':
                # Flight search attempt - show available results or fallback message
                response = tool_result.get('formatted_display')
                if not response:
                    response = tool_result.get('message', 'Flight search completed')
                response_type = "search_complete"
            elif not missing_info:
                # All required information is available - move to confirmation
                response = self.generate_confirmation_summary()
                response_type = "confirmation"
            elif len(missing_info) <= 2:
                # Just a few things missing - ask conversationally
                response = self.generate_conversational_response(
                    user_input, 
                    f"Still need: {', '.join(missing_info)}",
                    tool_result
                )
                response_type = "gathering_info"
            else:
                # Need more basic info - provide guidance
                response = self.generate_conversational_response(
                    user_input,
                    "User is providing initial travel information",
                    tool_result
                )
                response_type = "initial_guidance"
                
            self.add_to_conversation(response, "assistant")
            
            return {
                "response": response,
                "type": response_type,
                "current_info": self.current_booking_info.copy(),
                "missing_info": missing_info,
                "tool_used": "flight_search_and_extraction_tool"
            }
            
        except Exception as e:
            error_response = "I'd love to help you with your travel plans! Could you tell me where you'd like to go and when?"
            self.add_to_conversation(error_response, "assistant")
            return {
                "response": error_response,
                "type": "error",
                "current_info": self.current_booking_info.copy(),
                "missing_info": [],
                "tool_used": None
            }

    def handle_modification_request(self, user_input):
        """Handle user requests to modify booking information"""
        self.add_to_conversation(user_input, "user")
        
        try:
            # Use the combined flight tool to extract new information
            tool_result = self.available_tools['flight_search_and_extraction_tool']['function'](user_input, self.current_booking_info, False)
            
            # Store old info for comparison
            old_info = self.current_booking_info.copy()
            
            # Update current booking info from tool result
            if tool_result.get('status') == 'success':
                self.current_booking_info = tool_result.get('updated_context', self.current_booking_info)
            
            # Generate response about what was changed
            changes_made = []
            if tool_result.get('status') == 'success':
                extracted_info = tool_result.get('extracted_info', {})
                for key, new_value in extracted_info.items():
                    if new_value and new_value != '' and new_value != 'null' and old_info.get(key) != new_value:
                        if key == 'passengers':
                            old_total = sum(old_info.get('passengers', {'adults': 1, 'children': 0, 'infants': 0}).values())
                            new_total = sum(new_value.values()) if isinstance(new_value, dict) else new_value
                            changes_made.append(f"passengers: {old_total} → {new_total}")
                        else:
                            old_val = old_info.get(key, 'not set')
                            changes_made.append(f"{key}: {old_val} → {new_value}")
            
            if changes_made:
                context = f"Changes made: {', '.join(changes_made)}"
            else:
                context = "User requested modification but no specific changes detected"
            
            response = self.generate_conversational_response(user_input, context, tool_result)
            self.add_to_conversation(response, "assistant")
            
            return {
                "response": response,
                "type": "modification",
                "current_info": self.current_booking_info.copy(),
                "missing_info": self.identify_missing_information(),
                "tool_used": "flight_search_and_extraction_tool"
            }
            
        except Exception as e:
            response = "I'd be happy to help you make changes! Could you tell me what you'd like to modify?"
            self.add_to_conversation(response, "assistant")
            return {
                "response": response,
                "type": "modification_error",
                "current_info": self.current_booking_info.copy(),
                "missing_info": [],
                "tool_used": None
            }

    def execute_flight_search_with_conversation(self):
        """Execute flight search using the combined flight tool"""
        try:
            # Validate all required information is present
            missing = self.identify_missing_information()
            if missing:
                response = f"I still need a bit more information before I can search: {', '.join(missing)}. Could you help me with those details?"
                self.add_to_conversation(response, "assistant")
                return {
                    "response": response,
                    "type": "missing_info",
                    "status": "incomplete"
                }
            
            # Generate enthusiastic search start message
            search_start_msg = self.generate_search_start_message()
            self.add_to_conversation(search_start_msg, "assistant")
            
            # Execute the search using the combined flight tool (force search mode)
            search_result = self.available_tools['flight_search_and_extraction_tool']['function']("search for flights", self.current_booking_info, True)
            
            if search_result.get("status") == "success" and search_result.get("action") == "flight_search":
                # Generate conversational results presentation
                results_response = self.generate_flight_results_response(search_result)
                self.add_to_conversation(results_response, "assistant")
                
                return {
                    "response": f"{search_start_msg}\n\n{results_response}",
                    "type": "search_complete",
                    "status": "complete",
                    "flight_results": search_result.get("flight_results"),
                    "search_type": search_result.get("search_type"),
                    "tool_used": "flight_search_and_extraction_tool"
                }
            else:
                error_response = f"I encountered an issue while searching for flights: {search_result.get('message')}. Would you like me to try again?"
                self.add_to_conversation(error_response, "assistant")
                return {
                    "response": error_response,
                    "type": "search_error",
                    "status": "error",
                    "tool_used": "flight_search_and_extraction_tool"
                }
            
        except Exception as e:
            error_response = f"I encountered an issue while searching for flights: {str(e)}. Would you like me to try again?"
            self.add_to_conversation(error_response, "assistant")
            return {
                "response": error_response,
                "type": "search_error",
                "status": "error",
                "tool_used": None
            }

    def generate_search_start_message(self):
        """Generate an enthusiastic message about starting the search"""
        try:
            info = self.current_booking_info
            route = f"{info.get('source')} to {info.get('destination')}"
            
            prompt = f"""
                Generate a brief, enthusiastic message that you're about to start searching for flights from {route}.

                The message should:
                1. Be excited and positive
                2. Indicate you're starting the search process
                3. Be very brief (1-2 sentences max)
                4. Use terms like "searching", "looking", "finding" - NOT "booking" or "processing"

                Examples: "Excellent! Let me search for the best flights for you now!" or "Perfect! Searching for your flights right away!"

                Generate message:
                """
            
            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model_name,
                    temperature=0.5,
                    max_tokens=100,
                    top_p=0.9
                )
                return chat_completion.choices[0].message.content.strip()
            else:
                raise Exception("Groq client not initialized")
            
        except Exception as e:
            return "Excellent! Let me search for the best flight options for you now!"

    def generate_flight_results_response(self, search_result):
        """Generate a conversational response about flight results"""
        try:
            # Use the formatted display from the search tool
            formatted_results = search_result.get("formatted_display")
            if not formatted_results:
                formatted_results = search_result.get("message", "Flight details not available")
            
            # Add a brief conversational intro based on status
            status = search_result.get("status")
            if status == "success":
                intro = "Great news! I found some flight options for you:"
            elif status == "missing_info":
                intro = "I still need a bit more information before I can show specific flights:"
            else:
                intro = "I hit a snag while searching for flights:"
            
            return f"{intro}\n\n{formatted_results}"
            
        except Exception as e:
            formatted_results = search_result.get("formatted_display", "Flight details not available")
            return f"I've completed your flight search! Here are the results:\n\n{formatted_results}"

    def generate_confirmation_summary(self):
        """Generate a natural confirmation summary"""
        try:
            info = self.current_booking_info
            
            # Build a natural, concise summary
            summary_parts = []
            
            # Basic trip info
            if info.get('source') and info.get('destination'):
                trip_type = "round-trip" if info.get('flight_type') == 'return' else "one-way"
                summary_parts.append(f"{trip_type} from {info['source']} to {info['destination']}")
            
            # Date
            if info.get('departure_date'):
                summary_parts.append(f"on {info['departure_date']}")
            
            # Add return date if applicable
            if info.get('return_date'):
                summary_parts.append(f"returning {info['return_date']}")
            
            # Class and passengers
            passengers = info.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
            class_text = info.get('flight_class', 'economy').replace('_', ' ')
            
            total_passengers = passengers['adults'] + passengers['children'] + passengers['infants']
            if total_passengers == 1:
                passenger_text = "for 1 person"
            elif passengers['children'] > 0 or passengers['infants'] > 0:
                passenger_text = f"for {total_passengers} passengers ({passengers['adults']} adults"
                if passengers['children'] > 0:
                    passenger_text += f", {passengers['children']} children"
                if passengers['infants'] > 0:
                    passenger_text += f", {passengers['infants']} infants"
                passenger_text += ")"
            else:
                passenger_text = f"for {passengers['adults']} adults"
            
            summary_parts.append(f"in {class_text} class {passenger_text}")
            
            # Optional airline
            airline_text = ""
            if info.get('content_provider'):
                airline_text = f" with {info['content_provider'].replace('_', ' ').title()}"
            
            summary = "Perfect! I have " + ", ".join(summary_parts) + airline_text + "."
            
            prompt = f"""
                Create a brief, friendly confirmation message for this flight search:

                {summary}

                The message should:
                1. Confirm the details naturally
                2. Ask if they're ready to SEARCH for flights (not book - just search!)
                3. Be warm but concise
                4. Not repeat all the details again
                5. Use words like "search", "find flights", "look for options" - NOT "book", "confirm booking", or "process payment"

                Keep it short and conversational:
                """
            
            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model_name,
                    temperature=0.6,
                    max_tokens=300,
                    top_p=0.9
                )
                return chat_completion.choices[0].message.content.strip()
            else:
                raise Exception("Groq client not initialized")
            
        except Exception as e:
            # Fallback to simple confirmation
            route = f"{info.get('source', '?')} to {info.get('destination', '?')}"
            date = info.get('departure_date', 'your chosen date')
            passengers = info.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
            total = passengers['adults'] + passengers['children'] + passengers['infants']
            passenger_text = f"{total} passenger{'s' if total > 1 else ''}"
            return f"Great! I have your {route} flight for {date} with {passenger_text}. Ready to search for the best options?"

    def reset_conversation(self):
        """Reset conversation state for new booking"""
        self.conversation_history = []
        self.current_booking_info = {}
        
        welcome_msg = "Hello! I'm your travel assistant, and I'm excited to help you find the perfect flight! ✈️ Tell me about your travel plans - where would you like to go?"
        self.add_to_conversation(welcome_msg, "assistant")
        return welcome_msg
