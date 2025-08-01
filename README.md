# Conversational AI Travel Agent

This project is a conversational AI-powered flight search assistant that allows users to find flights using natural language. It leverages natural language processing (NLP) to understand user queries, extract travel parameters, and interact with a flight search API to retrieve real-time flight information.

## Features

- **Natural Language Understanding:** The agent can understand and process user queries in natural language, extracting key information such as origin, destination, travel dates, passenger count, and flight class.
- **Conversational Interaction:** The agent engages in a conversation with the user to gather any missing information required for a flight search.
- **Multi-Airline Search:** The agent can search for flights across multiple airlines to provide a wide range of options.
- **Flexible User Interfaces:** The project offers two user interfaces:
    - A web-based interface built with Streamlit (`streamlit_ui.py`).
    - A terminal-based interface for command-line users (`terminal_ui.py`).
- **Stateful Conversation:** The agent maintains the context of the conversation, allowing users to make modifications to their search queries conversationally.

## Project Structure

-   `extract_parameters.py`: Contains the core logic for extracting travel-related parameters (cities, dates, passenger count, etc.) from user queries using NLP techniques.
-   `travel_agent.py`: Implements the `ConversationalTravelAgent` class, which manages the conversation flow, interacts with the flight search API, and processes user input.
-   `streamlit_ui.py`: A user-friendly web interface for interacting with the travel agent, built with Streamlit.
-   `terminal_ui.py`: A command-line interface for interacting with the travel agent in a terminal.
-   `queryonly.py`: An interactive query tool that connects to a Graphiti knowledge base and can be used for more advanced querying.
-   `ingest.py`: A script for ingesting data into the Neo4j database using Graphiti.
-   `requirements2.txt`: A list of Python dependencies required for the project.
-   `test_parameter_parsing.py`: Unit tests for the parameter extraction logic.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/naumanAhmed3/bookiebee-revamped-prototype-.git
    cd bookiebee-revamped-prototype-
    ```

2.  **Create a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements2.txt
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the root of the project and add your API keys:
    ```
    GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"
    GROQ_API_KEY="YOUR_GROQ_API_KEY"
    NEO4J_USER="your_neo4j_user"
    NEO4J_PASSWORD="your_neo4j_password"
    ```

## Usage

You can interact with the travel agent through either the Streamlit UI or the terminal UI.

### Streamlit UI

To run the web-based interface, use the following command:

```bash
streamlit run streamlit_ui.py
```

This will start a local web server, and you can interact with the agent through your browser.

### Terminal UI

To run the terminal-based interface, use the following command:

```bash
python terminal_ui.py
```

This will launch the conversational agent in your terminal.

## How It Works

1.  **User Input:** The user provides a travel query in natural language (e.g., "I want to fly from Lahore to Karachi tomorrow").
2.  **Parameter Extraction:** The `extract_parameters.py` script uses NLP to parse the user's query and extract key travel parameters.
3.  **Conversational Flow:** The `travel_agent.py` script manages the conversation. If any information is missing, it asks the user for the required details.
4.  **API Interaction:** Once all the necessary information is gathered, the agent constructs a payload and sends a request to the flight search API.
5.  **Results:** The agent receives the flight search results from the API, formats them, and presents them to the user.

## Dependencies

-   **Streamlit:** For the web-based UI.
-   **spaCy:** For natural language processing.
-   **rapidfuzz:** For fuzzy string matching.
-   **parsedatetime:** For parsing human-readable date and time expressions.
-   **autocorrect:** For spelling correction.
-   **Groq:** For interacting with the Groq LLM.
-   **Ably:** For real-time messaging (used in the terminal UI).
-   **Graphiti:** For knowledge graph interactions.
-   **LangChain:** For building language model applications.
