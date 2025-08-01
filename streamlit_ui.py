import streamlit as st
import json
from datetime import datetime
import sys
import os

# Add the current directory to the path to import the travel agent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from travel_agent import TravelAgent
except ImportError:
    st.error("Could not import TravelAgent. Make sure travel_agent.py is in the same directory.")
    st.stop()

# Configure Streamlit page
st.set_page_config(
    page_title="✈️ Travel Flight Search",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    
    .info-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #1e3c72;
        margin: 1rem 0;
    }
    
    .success-box {
        background-color: #d4edda;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #28a745;
        margin: 1rem 0;
    }
    
    .error-box {
        background-color: #f8d7da;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #dc3545;
        margin: 1rem 0;
    }
    
    .chat-message {
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 10px;
    }
    
    .user-message {
        background-color: #e3f2fd;
        margin-left: 2rem;
    }
    
    .agent-message {
        background-color: #f5f5f5;
        margin-right: 2rem;
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize session state variables"""
    if 'agent' not in st.session_state:
        st.session_state.agent = TravelAgent()
    
    if 'conversation_state' not in st.session_state:
        st.session_state.conversation_state = 'initial'  # initial, missing_info, confirmation, complete
    
    if 'extracted_info' not in st.session_state:
        st.session_state.extracted_info = {}
    
    if 'missing_attributes' not in st.session_state:
        st.session_state.missing_attributes = []
    
    if 'current_missing_index' not in st.session_state:
        st.session_state.current_missing_index = 0
    
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    if 'final_results' not in st.session_state:
        st.session_state.final_results = None

def add_to_chat(message, sender="user"):
    """Add message to chat history"""
    st.session_state.chat_history.append({
        "message": message,
        "sender": sender,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })

def display_chat_history():
    """Display the chat history"""
    for chat in st.session_state.chat_history:
        if chat["sender"] == "user":
            st.markdown(f"""
            <div class="chat-message user-message">
                <strong>You ({chat['timestamp']}):</strong><br>
                {chat['message']}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="chat-message agent-message">
                <strong>Assistant ({chat['timestamp']}):</strong><br>
                {chat['message']}
            </div>
            """, unsafe_allow_html=True)

def display_editable_info(info):
    """Display travel information with editing capabilities"""
    st.markdown("### ✏️ Review and Edit Your Travel Details")
    st.markdown("Please review the information below and make any necessary changes:")
    
    # Create form for editing
    with st.form("edit_travel_info"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🛫 Flight Details:**")
            
            # Source city
            source_options = ["LHE", "KHI", "ISB", "MUX", "PEW", "UET", "LYP", "SKT", "KDU", "GIL", "SKZ", "GWD", "TUK", "BHV", "DEA", "CJL", "PJG", "MJD", "PAJ", "PZH", "DBA", "MFG", "RYK", "WNS"]
            source_index = source_options.index(info.get('source', 'LHE')) if info.get('source') in source_options else 0
            edited_source = st.selectbox("From (IATA Code):", source_options, index=source_index)
            
            # Destination city
            dest_index = source_options.index(info.get('destination', 'KHI')) if info.get('destination') in source_options else 1
            edited_destination = st.selectbox("To (IATA Code):", source_options, index=dest_index)
            
            # Flight type
            flight_types = ["one_way", "return"]
            type_index = flight_types.index(info.get('flight_type', 'one_way')) if info.get('flight_type') in flight_types else 0
            edited_flight_type = st.selectbox("Trip Type:", flight_types, index=type_index)
            
            # Flight class
            flight_classes = ["economy", "business", "first", "premium_economy"]
            class_index = flight_classes.index(info.get('flight_class', 'economy')) if info.get('flight_class') in flight_classes else 0
            edited_flight_class = st.selectbox("Travel Class:", flight_classes, index=class_index)
            
            # Airline (optional)
            airline_options = ["", "airblue", "serene_air", "pia", "emirates", "qatar_airways", "etihad", "turkish_airlines"]
            airline_index = airline_options.index(info.get('content_provider', '')) if info.get('content_provider') in airline_options else 0
            edited_airline = st.selectbox("Preferred Airline:", airline_options, index=airline_index)
        
        with col2:
            st.markdown("**📅 Travel Dates:**")
            
            # Departure date
            departure_date = info.get('departure_date')
            if departure_date:
                try:
                    departure_datetime = datetime.strptime(departure_date, "%Y-%m-%d")
                except:
                    departure_datetime = datetime.now()
            else:
                departure_datetime = datetime.now()
            
            edited_departure_date = st.date_input("Departure Date:", departure_datetime)
            
            # Return date (only if return flight)
            edited_return_date = None
            if edited_flight_type == "return":
                return_date = info.get('return_date')
                if return_date:
                    try:
                        return_datetime = datetime.strptime(return_date, "%Y-%m-%d")
                    except:
                        return_datetime = departure_datetime
                else:
                    return_datetime = departure_datetime
                
                edited_return_date = st.date_input("Return Date:", return_datetime)
            
            st.markdown("**👥 Passengers:**")
            passengers = info.get('passengers', {"adults": 1, "children": 0, "infants": 0})
            
            edited_adults = st.number_input("Adults:", min_value=1, max_value=9, value=passengers.get('adults', 1))
            edited_children = st.number_input("Children (2-11 years):", min_value=0, max_value=9, value=passengers.get('children', 0))
            edited_infants = st.number_input("Infants (under 2 years):", min_value=0, max_value=9, value=passengers.get('infants', 0))
        
        # Submit button
        submitted = st.form_submit_button("✅ Confirm and Search Flights", type="primary", use_container_width=True)
        
        if submitted:
            # Validate the data
            if edited_source == edited_destination:
                st.error("❌ Source and destination cannot be the same!")
                return None
            
            if edited_flight_type == "return" and edited_return_date and edited_return_date <= edited_departure_date:
                st.error("❌ Return date must be after departure date!")
                return None
            
            # Build the updated info
            updated_info = {
                "source": edited_source,
                "destination": edited_destination,
                "flight_type": edited_flight_type,
                "flight_class": edited_flight_class,
                "departure_date": edited_departure_date.strftime("%Y-%m-%d"),
                "passengers": {
                    "adults": int(edited_adults),
                    "children": int(edited_children),
                    "infants": int(edited_infants)
                }
            }
            
            if edited_airline:
                updated_info["content_provider"] = edited_airline
            
            if edited_flight_type == "return" and edited_return_date:
                updated_info["return_date"] = edited_return_date.strftime("%Y-%m-%d")
            
            return updated_info
    
    return None

def display_readonly_info(info):
    """Display travel information in a read-only format"""
    st.markdown("### 📝 Your Travel Details")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🛫 Flight Details:**")
        st.write(f"**From (IATA Code):** {info.get('source', '-')}")
        st.write(f"**To (IATA Code):** {info.get('destination', '-')}")
        st.write(f"**Trip Type:** {info.get('flight_type', '-')}")
        st.write(f"**Travel Class:** {info.get('flight_class', '-')}")
        st.write(f"**Preferred Airline:** {info.get('content_provider', '-')}")
    with col2:
        st.markdown("**📅 Travel Dates:**")
        st.write(f"**Departure Date:** {info.get('departure_date', '-')}")
        if info.get('flight_type') == "return":
            st.write(f"**Return Date:** {info.get('return_date', '-')}")
        st.markdown("**👥 Passengers:**")
        passengers = info.get('passengers', {})
        st.write(f"**Adults:** {passengers.get('adults', '-')}")
        st.write(f"**Children (2-11 years):** {passengers.get('children', '-')}")
        st.write(f"**Infants (under 2 years):** {passengers.get('infants', '-')}")

def main():
    # Initialize session state
    initialize_session_state()
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>✈️ AI Travel Flight Search Assistant</h1>
        <p>Tell me about your travel plans and I'll help you find the best flights!</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Chat interface
    st.markdown("### 💬 Chat with Travel Assistant")
    
    # Display chat history
    chat_container = st.container()
    with chat_container:
        display_chat_history()
    
    # Handle different conversation states
    if st.session_state.conversation_state == 'initial':
        # Initial query input - Use a form to ensure proper submission
        with st.form("initial_query_form"):
            user_query = st.text_input(
                "🗣️ **Describe your travel plans:**",
                placeholder="e.g., I want to fly from Lahore to Karachi tomorrow for 2 people",
                key="initial_query"
            )
            
            submitted = st.form_submit_button("🔍 Search Flights", type="primary", use_container_width=True)
            
            if submitted and user_query:
                add_to_chat(user_query, "user")
                
                with st.spinner("🔄 Processing your request..."):
                    result = st.session_state.agent.process_full_request(user_query)
                
                if result["status"] == "missing_info":
                    st.session_state.conversation_state = 'missing_info'
                    st.session_state.extracted_info = result["extracted_info"]
                    st.session_state.missing_attributes = result["missing_attributes"]
                    st.session_state.prompts = result["prompts"]
                    st.session_state.current_missing_index = 0
                    
                    add_to_chat("I need some additional information to search for flights. Let me ask you a few questions.", "agent")
                    st.rerun()
                
                elif result["status"] == "ready_for_confirmation":
                    st.session_state.conversation_state = 'confirmation'
                    st.session_state.extracted_info = result["extracted_info"]
                    add_to_chat("Great! I've gathered all the information. Please review and confirm your travel details below.", "agent")
                    st.rerun()
                
                elif result["status"] == "error":
                    add_to_chat(f"❌ Error: {result['message']}", "agent")
            elif submitted and not user_query:
                st.warning("Please enter your travel query.")
    
    elif st.session_state.conversation_state == 'missing_info':
        # Handle missing information collection - Use a form for proper submission
        if st.session_state.current_missing_index < len(st.session_state.missing_attributes):
            current_attr = st.session_state.missing_attributes[st.session_state.current_missing_index]
            current_prompt = st.session_state.prompts[st.session_state.current_missing_index]
            
            st.markdown(f"""
            <div class="info-box">
                <strong>Question {st.session_state.current_missing_index + 1} of {len(st.session_state.missing_attributes)}:</strong><br>
                {current_prompt}
            </div>
            """, unsafe_allow_html=True)
            
            with st.form(f"missing_info_form_{st.session_state.current_missing_index}"):
                user_input = st.text_input(
                    f"Your answer:",
                    key=f"missing_info_{st.session_state.current_missing_index}"
                )
                
                submitted = st.form_submit_button("➡️ Submit", type="primary", use_container_width=True)
                
                if submitted and user_input:
                    add_to_chat(f"Q: {current_prompt}", "agent")
                    add_to_chat(user_input, "user")
                    
                    # Process the missing attribute
                    st.session_state.extracted_info = st.session_state.agent.process_missing_attribute(
                        current_attr, user_input, st.session_state.extracted_info
                    )
                    
                    st.session_state.current_missing_index += 1
                    st.rerun()
                elif submitted and not user_input:
                    st.warning("Please provide an answer.")
        
        else:
            # All missing info collected, move to confirmation
            st.session_state.conversation_state = 'confirmation'
            st.rerun()
    
    elif st.session_state.conversation_state == 'confirmation':
        # Show editable information for confirmation
        st.markdown("---")
        updated_info = display_editable_info(st.session_state.extracted_info)
        
        if updated_info:
            # User confirmed and wants to search
            add_to_chat("Perfect! Searching for flights with your confirmed details...", "agent")
            
            with st.spinner("🔍 Searching for flights..."):
                search_result = st.session_state.agent.execute_flight_search(updated_info)
            
            if search_result["status"] == "complete":
                st.session_state.conversation_state = 'complete'
                st.session_state.extracted_info = updated_info
                st.session_state.final_results = search_result
                add_to_chat(search_result["llm_response"], "agent")
                st.rerun()
            else:
                add_to_chat(f"❌ Error during search: {search_result.get('message', 'Unknown error')}", "agent")
        
        # Option to start over
        st.markdown("---")
        with st.form("start_over_form"):
            if st.form_submit_button("🔄 Start Over", use_container_width=True):
                st.session_state.conversation_state = 'initial'
                st.session_state.extracted_info = {}
                st.session_state.missing_attributes = []
                st.session_state.current_missing_index = 0
                st.session_state.chat_history = []
                st.session_state.final_results = None
                st.rerun()
    
    elif st.session_state.conversation_state == 'complete':
        # Show final results
        st.markdown("### 🎉 Flight Search Complete!")
        
        display_readonly_info(st.session_state.extracted_info)
        
        # Show technical details in expandable sections
        if st.session_state.final_results:
            with st.expander("🔧 API Request Details"):
                st.json(st.session_state.final_results.get("api_payload", {}))
            
            with st.expander("✈️ Raw Flight Results"):
                st.json(st.session_state.final_results.get("flight_results", {}))
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            with st.form("new_search_form"):
                if st.form_submit_button("🔍 New Search", type="primary", use_container_width=True):
                    st.session_state.conversation_state = 'initial'
                    st.session_state.extracted_info = {}
                    st.session_state.missing_attributes = []
                    st.session_state.current_missing_index = 0
                    st.session_state.chat_history = []
                    st.session_state.final_results = None
                    st.rerun()
        
        with col2:
            with st.form("modify_search_form"):
                if st.form_submit_button("🔄 Modify Search", use_container_width=True):
                    st.session_state.conversation_state = 'confirmation'
                    st.rerun()
    
    # Sidebar with help
    with st.sidebar:
        st.markdown("### 🛟 Help & Tips")
        st.markdown("""
        **How to use:**
        1. Describe your travel plans naturally
        2. Answer any follow-up questions
        3. Confirm your details
        4. Get flight results!
        
        **Example queries:**
        - "I want to fly from Lahore to Karachi tomorrow"
        - "Business class flight to Dubai next week for 2 people"
        - "Return ticket ISB to LHE on 15th December"
        
        **Supported cities:**
        Lahore, Karachi, Islamabad, Multan, Peshawar, and more!
        """)
        
        if st.session_state.chat_history:
            with st.form("clear_chat_form"):
                if st.form_submit_button("🗑️ Clear Chat", use_container_width=True):
                    st.session_state.chat_history = []
                    st.session_state.conversation_state = 'initial'
                    st.session_state.extracted_info = {}
                    st.session_state.missing_attributes = []
                    st.session_state.current_missing_index = 0
                    st.session_state.final_results = None
                    st.rerun()

if __name__ == "__main__":
    main()