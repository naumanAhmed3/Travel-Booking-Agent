import asyncio
import os
from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_react_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langchain_groq import ChatGroq

# Load environment variables
load_dotenv()

# Import the original tool functions from travel_agent
# Note: We are assuming the original functions can be imported.
# If they are not designed for direct import, we might need to refactor them.
try:
    from travel_agent import flight_search_and_extraction_tool, knowledge_graph_search_tool
except ImportError:
    print("Could not import tools from travel_agent.py. Using placeholder functions.")
    # Define placeholder functions if the import fails
    def flight_search_and_extraction_tool(user_input: str, current_context: dict = None, search_mode: bool = False) -> dict:
        return {"status": "error", "message": "Placeholder function: flight tool not implemented."}

    def knowledge_graph_search_tool(query: str) -> dict:
        return {"status": "error", "message": "Placeholder function: knowledge graph tool not implemented."}

# --- 1. Wrap existing functions as Langchain tools ---

@tool(return_direct=True)
def flight_search_tool(user_input: str, search_mode: bool = False) -> dict:
    """
    Handles all flight-related functionality including travel information extraction and flight search.
    Use this for extracting travel information from user's natural language input, searching for flights,
    and processing travel data like cities, dates, passenger counts, and flight class.
    """
    # This tool acts as a wrapper. We'll manage the context internally.
    # For a real implementation, context would be managed in a more robust way (e.g., session state).
    current_context = {} # Simplified context management for this example
    return flight_search_and_extraction_tool(user_input, current_context, search_mode)

@tool
def company_knowledge_base_tool(query: str) -> dict:
    """
    Searches the company's internal knowledge base for policies, offers, and general information.
    Use this to answer questions about return policies, shipping rules, promotions, product features,
    business hours, and event updates. Do NOT use this for real-time data like flight searches.
    """
    return knowledge_graph_search_tool(query)


# --- 2. Set up the Langchain Agent ---

def create_langchain_agent():
    """
    Creates and configures a Langchain agent with the defined tools.
    """
    # Define the prompt template
    prompt_template = """
    You are a helpful travel assistant. Your goal is to assist users with their travel plans and answer their questions.
    You have access to the following tools:

    {tools}

    Use the following format:

    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I now know the final answer
    Final Answer: the final answer to the original input question

    Begin!

    Previous conversation history:
    {chat_history}

    New question: {input}
    Thought:{agent_scratchpad}
    """

    prompt = PromptTemplate.from_template(prompt_template)

    # Initialize the LLM
    llm = ChatGroq(temperature=0, model_name="llama3-70b-8192", groq_api_key=os.getenv("GROQ_API_KEY"))

    # Define the tools for the agent
    tools = [flight_search_tool, company_knowledge_base_tool]

    # Create the agent
    agent = create_react_agent(llm, tools, prompt)

    # Create the memory
    memory = ConversationBufferMemory(memory_key="chat_history")

    # Create the agent executor
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)

    return agent_executor


# --- 3. Main conversational loop ---

def run_conversation():
    """
    Runs a conversational loop to interact with the Langchain agent.
    """
    print("✈️  Langchain Travel Assistant is ready!")
    print("Type 'quit' to exit.")
    print("-" * 50)

    agent_executor = create_langchain_agent()

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["quit", "exit"]:
                print("Goodbye! Safe travels!")
                break

            if user_input:
                response = agent_executor.invoke({"input": user_input})
                print(f"Assistant: {response['output']}")

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! Safe travels!")
            break
        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    # Ensure API keys are set
    if not os.getenv("GROQ_API_KEY") or not os.getenv("GOOGLE_API_KEY"):
        print("Error: GROQ_API_KEY and GOOGLE_API_KEY must be set in your .env file.")
    else:
        run_conversation()
