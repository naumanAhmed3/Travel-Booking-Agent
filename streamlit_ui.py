import streamlit as st
import json
from datetime import datetime
import sys
import os

# Add the current directory to the path to import the travel agent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from travel_agent import ConversationalTravelAgent
    from extract_parameters import extract_travel_info
except ImportError as e:
    st.error(f"Could not import required modules: {e}. Make sure travel_agent.py and extract_parameters.py are in the same directory.")
    st.stop()

# Configure Streamlit page
st.set_page_config(
    page_title="✈️ Flight Search Chatbot",
    page_icon="✈️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS for chatbot-like styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 2rem 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 20px;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
    }
    
    .chat-container {
        max-height: 500px;
        overflow-y: auto;
        padding: 1rem;
        border: 2px solid #f0f0f0;
        border-radius: 20px;
        background: #fafafa;
        margin-bottom: 1rem;
    }
    
    .user-message {
        background: #667eea;
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 20px 20px 5px 20px;
        margin: 1rem 0 1rem 20%;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }
    
    .assistant-message {
        background: white;
        color: #333;
        padding: 1rem 1.5rem;
        border-radius: 20px 20px 20px 5px;
        margin: 1rem 20% 1rem 0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border: 2px solid #f0f0f0;
    }
    
    .booking-info {
        background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }
    
    .flight-results {
        background: white;
        border: 2px solid #e0e0e0;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }
    
    .flight-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .fare-table {
        background: white;
        border-radius: 8px;
        padding: 0.5rem;
        margin: 0.5rem 0;
    }
    
    .input-container {
        position: sticky;
        bottom: 0;
        background: white;
        padding: 1rem;
        border-radius: 20px;
        box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);
        margin-top: 2rem;
    }
    
    .stTextInput > div > div > input {
        border-radius: 25px;
        border: 2px solid #667eea;
        padding: 1rem 1.5rem;
        font-size: 16px;
    }
    
    .stButton > button {
        border-radius: 25px;
        padding: 0.75rem 2rem;
        font-weight: bold;
        border: none;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize session state variables for the conversational agent"""
    if 'agent' not in st.session_state:
        st.session_state.agent = ConversationalTravelAgent()
    
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    
    if 'current_booking_info' not in st.session_state:
        st.session_state.current_booking_info = {}
    
    if 'conversation_started' not in st.session_state:
        st.session_state.conversation_started = False
    
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    
    if 'awaiting_confirmation' not in st.session_state:
        st.session_state.awaiting_confirmation = False
    
    if 'awaiting_modification' not in st.session_state:
        st.session_state.awaiting_modification = False

def add_to_chat(message, sender="user"):
    """Add message to chat history"""
    st.session_state.conversation_history.append({
        "message": message,
        "sender": sender,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })

def detect_user_intent(user_input: str) -> str:
    """Detect what the user intends to do based on their input and context"""
    input_lower = user_input.lower().strip()
    
    # Confirmation-related responses
    confirmation_yes = ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'correct', 'right', 'perfect', 'good', 
                       'looks good', 'that\'s right', 'proceed', 'go ahead', 'search', 'find flights',
                       'everything is great', 'everything looks good', 'that\'s perfect', 'you can search',
                       'ready', 'lets go', 'let\'s go', 'do it', 'find them', 'search now']
    confirmation_no = ['no', 'nope', 'not quite', 'incorrect', 'wrong', 'change', 'modify', 'edit', 'update']
    
    # Modification-related phrases
    modification_phrases = ['change', 'modify', 'edit', 'update', 'different', 'instead', 'actually', 'correction']
    
    # Search-related phrases
    search_phrases = ['search', 'find', 'look for', 'show me', 'get flights', 'book']
    
    if st.session_state.awaiting_confirmation:
        if any(phrase in input_lower for phrase in confirmation_yes):
            return "confirm_and_search"
        elif any(phrase in input_lower for phrase in confirmation_no):
            return "request_modification"
        elif any(phrase in input_lower for phrase in modification_phrases):
            return "request_modification"
    
    if st.session_state.awaiting_modification or any(phrase in input_lower for phrase in modification_phrases):
        return "modify_details"
    
    if any(phrase in input_lower for phrase in search_phrases):
        return "search_request"
    
    return "general_chat"

def process_conversation_turn(user_input: str):
    """Process a single turn in the conversation like terminal UI"""
    # Detect user intent
    current_context = {
        "awaiting_confirmation": st.session_state.awaiting_confirmation,
        "awaiting_modification": st.session_state.awaiting_modification,
        "current_info": st.session_state.agent.current_booking_info
    }
    
    intent = detect_user_intent(user_input)
    
    if intent == "confirm_and_search":
        # User confirmed, proceed with search automatically
        st.session_state.awaiting_confirmation = False
        
        with st.spinner("🔍 Searching for flights..."):
            search_result = st.session_state.agent.execute_flight_search_with_conversation()
        
        add_to_chat(search_result["response"], "assistant")
        
        # Don't store separate flight results since they're already in the chat response
        # if search_result.get("flight_results"):
        #     st.session_state.search_results = search_result["flight_results"]
        
        return True  # Indicates search was performed
    
    elif intent == "request_modification" or intent == "modify_details":
        # User wants to modify something
        st.session_state.awaiting_confirmation = False
        st.session_state.awaiting_modification = True
        
        with st.spinner("🤖 Processing changes..."):
            modification_result = st.session_state.agent.handle_modification_request(user_input)
        
        add_to_chat(modification_result["response"], "assistant")
        st.session_state.current_booking_info = modification_result.get("current_info", {})
        
        # Check if we have all info after modification
        missing_info = modification_result.get("missing_info", [])
        if not missing_info:
            # Move to confirmation state
            st.session_state.awaiting_confirmation = True
            st.session_state.awaiting_modification = False
        
        return False
    
    else:
        # General conversation - process normally
        with st.spinner("🤖 Thinking..."):
            result = st.session_state.agent.process_user_input_conversationally(user_input)
        
        add_to_chat(result["response"], "assistant")
        st.session_state.current_booking_info = result.get("current_info", {})
        
        # Update conversation state based on result
        if result["type"] == "confirmation":
            st.session_state.awaiting_confirmation = True
            st.session_state.awaiting_modification = False
        elif result["type"] == "gathering_info":
            st.session_state.awaiting_confirmation = False
            st.session_state.awaiting_modification = False
        elif result["type"] == "modification":
            st.session_state.awaiting_modification = True
            st.session_state.awaiting_confirmation = False
        
        return False

def display_chat_history():
    """Display the chat history in a simple chatbot interface"""
    if st.session_state.conversation_history:
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        
        for chat in st.session_state.conversation_history:
            if chat["sender"] == "user":
                st.markdown(f"""
                <div class="user-message">
                    {chat['message']}
                </div>
                """, unsafe_allow_html=True)
            else:
                # Check if this is a flight search response (contains markdown flight formatting)
                message = chat['message']
                if ('🛫' in message and '**Flight' in message) or ('Flight Options Found' in message):
                    # This is a flight search response with markdown - render it properly
                    st.markdown('<div class="assistant-message">', unsafe_allow_html=True)
                    st.markdown("🤖")
                    st.markdown(message)  # Let Streamlit render the markdown
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    # Regular message - display as before
                    st.markdown(f"""
                    <div class="assistant-message">
                        🤖 {chat['message']}
                    </div>
                    """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="chat-container">
            <div class="assistant-message">
                👋 Hi! I'm your flight search assistant. Tell me where you'd like to go!
            </div>
        </div>
        """, unsafe_allow_html=True)

def display_current_booking_info():
    """Display current booking information only during confirmation phase like terminal UI"""
    # Only show booking info when awaiting confirmation (like terminal UI)
    if (st.session_state.current_booking_info and 
        st.session_state.awaiting_confirmation):
        info = st.session_state.current_booking_info
        
        st.markdown('<div class="booking-info">', unsafe_allow_html=True)
        st.markdown("### � Your Trip Details")
        
        # Route
        if info.get('source') and info.get('destination'):
            st.markdown(f"**🛫 Route:** {info['source']} → {info['destination']}")
        
        # Date
        if info.get('departure_date'):
            st.markdown(f"**📅 Date:** {info['departure_date']}")
        
        # Passengers
        passengers = info.get('passengers', {})
        if passengers:
            adults = passengers.get('adults', 0)
            children = passengers.get('children', 0)
            infants = passengers.get('infants', 0)
            
            passenger_details = []
            if adults > 0:
                passenger_details.append(f"{adults} adult{'s' if adults > 1 else ''}")
            if children > 0:
                passenger_details.append(f"{children} child{'ren' if children > 1 else ''}")
            if infants > 0:
                passenger_details.append(f"{infants} infant{'s' if infants > 1 else ''}")
            
            if passenger_details:
                st.markdown(f"**👥 Passengers:** {', '.join(passenger_details)}")
        
        # Return date if applicable
        if info.get('return_date'):
            st.markdown(f"**📅 Return:** {info['return_date']}")
        
        # Flight type
        if info.get('flight_type'):
            flight_type = info['flight_type'].replace('_', ' ').title()
            st.markdown(f"**🎫 Type:** {flight_type}")
        
        # Class
        if info.get('flight_class'):
            st.markdown(f"**✈️ Class:** {info['flight_class'].replace('_', ' ').title()}")
        
        st.markdown('</div>', unsafe_allow_html=True)

def display_flight_results(results):
    """Display flight search results in detailed format like terminal UI"""
    if not results:
        return
    
    st.markdown('<div class="flight-results">', unsafe_allow_html=True)
    st.markdown("### ✈️ Flight Results")
    
    if isinstance(results, dict):
        total_flights = results.get('total_flights', 0)
        airlines_with_flights = results.get('airlines_with_flights', 0)
        successful_api_calls = results.get('successful_airlines', 0)
        flights = results.get('flights', [])
        errors = results.get('errors', [])
        
        if total_flights > 0:
            st.success(f"🎉 Found {total_flights} flights from {airlines_with_flights} airlines!")
            
            # Check if we have extracted flights with detailed information
            results_with_flights = results.get('results_with_flights', [])
            all_extracted_flights = []
            
            # Try to get detailed flight information
            for result in results_with_flights:
                if 'error' not in result and hasattr(st.session_state.agent, 'extract_flight_information'):
                    try:
                        extracted_flights = st.session_state.agent.extract_flight_information(result)
                        all_extracted_flights.extend(extracted_flights)
                    except:
                        pass
            
            if all_extracted_flights:
                # Display detailed flight information
                st.markdown("#### 🛫 **Flight Options Found:**")
                
                for i, flight in enumerate(all_extracted_flights[:5], 1):  # Show top 5 flights
                    with st.container():
                        st.markdown(f"##### **Flight {i}: {flight['airline']} {flight['flight_number']}**")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown(f"**📍 Route:** {flight['origin']} → {flight['destination']}")
                        with col2:
                            st.markdown(f"**🕐 Time:** {flight['departure_time']} → {flight['arrival_time']}")
                        with col3:
                            st.markdown(f"**⏱️ Duration:** {flight['duration']}")
                        
                        # Display fare options if available
                        if flight.get('fare_options'):
                            st.markdown("**💰 Fare Options:**")
                            fare_data = []
                            
                            for fare in flight['fare_options']:
                                baggage_info = f"Hand: {fare['hand_baggage_kg']}kg"
                                if fare['checked_baggage_kg'] > 0:
                                    baggage_info += f" | Checked: {fare['checked_baggage_kg']}kg"
                                else:
                                    baggage_info += " | No checked baggage"
                                
                                refund_info = ""
                                if fare['refundable_before_48h']:
                                    refund_info = f"Refund fee: PKR {fare['refund_fee_48h']}"
                                else:
                                    refund_info = "Non-refundable"
                                
                                fare_data.append({
                                    "Fare Type": fare['fare_name'],
                                    "Price": f"PKR {fare['total_fare']:,}",
                                    "Baggage": baggage_info,
                                    "Refund": refund_info
                                })
                            
                            # Display as a table for better formatting
                            import pandas as pd
                            df = pd.DataFrame(fare_data)
                            st.dataframe(df, hide_index=True, use_container_width=True)
                        
                        if i < len(all_extracted_flights[:5]):
                            st.markdown("---")
                
                if len(all_extracted_flights) > 5:
                    st.info(f"... and {len(all_extracted_flights) - 5} more options available")
            
            else:
                # Fallback to basic flight display
                if flights:
                    # Group flights by airline
                    airline_groups = {}
                    for flight in flights[:10]:
                        airline = flight.get('source_airline', flight.get('airline', 'Unknown')).replace('_', ' ').title()
                        if airline not in airline_groups:
                            airline_groups[airline] = []
                        airline_groups[airline].append(flight)
                    
                    for airline, airline_flights in airline_groups.items():
                        st.markdown(f"#### ✈️ **{airline}** ({len(airline_flights)} options)")
                        
                        for i, flight in enumerate(airline_flights[:3], 1):
                            price = flight.get('price', flight.get('totalPrice', flight.get('cost', 'N/A')))
                            departure_time = flight.get('departureTime', flight.get('departure', 'N/A'))
                            arrival_time = flight.get('arrivalTime', flight.get('arrival', 'N/A'))
                            duration = flight.get('duration', flight.get('flightDuration', 'N/A'))
                            
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.markdown(f"**💰** PKR {price}")
                            with col2:
                                st.markdown(f"**🛫** {departure_time}")
                            with col3:
                                st.markdown(f"**🛬** {arrival_time}")
                            with col4:
                                st.markdown(f"**⏱️** {duration}")
                            
                            if i < len(airline_flights[:3]):
                                st.markdown("---")
            
            # Show error information if any
            if errors and len(errors) > 0:
                st.warning(f"Note: {len(errors)} airlines had temporary connection issues")
        
        else:
            if successful_api_calls > 0:
                total_contacted = successful_api_calls + len(errors)
                st.warning(f"😔 I searched {total_contacted} airlines successfully, but unfortunately no flights are available for your specific criteria. You might want to try different dates or nearby airports.")
            else:
                st.error("😔 I wasn't able to connect to the airline systems right now. Please try again in a few minutes.")
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    """Main Streamlit application - simple chatbot interface"""
    initialize_session_state()
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>✈️ Flight Search Chatbot</h1>
        <p>Just tell me where you want to go, and I'll help you find flights!</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Display chat history
    display_chat_history()
    
    # Start conversation if not started
    if not st.session_state.conversation_started:
        welcome_msg = st.session_state.agent.reset_conversation()
        add_to_chat(welcome_msg, "assistant")
        st.session_state.conversation_started = True
        st.rerun()
    
    # Show current booking info if available
    display_current_booking_info()
    
    # Show flight results if available (disabled since results are now in chat)
    # if st.session_state.search_results:
    #     display_flight_results(st.session_state.search_results)
    
    # Chat input at the bottom
    st.markdown('<div class="input-container">', unsafe_allow_html=True)
    
    # Simple input form
    user_input = st.text_input(
        "Type your message:",
        placeholder="e.g., I want to fly from Lahore to Karachi tomorrow",
        key="chat_input"
    )
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if st.button("💬 Send", type="primary", use_container_width=True):
            if user_input:
                add_to_chat(user_input, "user")
                
                # Process conversation turn (which may include automatic search)
                search_performed = process_conversation_turn(user_input)
                
                st.rerun()
    
    with col2:
        if st.button("� Reset", use_container_width=True):
            st.session_state.conversation_history = []
            st.session_state.current_booking_info = {}
            st.session_state.conversation_started = False
            st.session_state.search_results = None
            st.session_state.awaiting_confirmation = False
            st.session_state.awaiting_modification = False
            st.session_state.agent = ConversationalTravelAgent()
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Simple help in a collapsible section
    with st.expander("💡 How it works - Click here for examples"):
        st.markdown("""
        **Just chat naturally! The assistant will:**
        1. 📝 Collect your travel details through conversation
        2. ✅ Confirm your trip details with you
        3. 🔍 **Automatically search** when you say "yes" or "okay"
        
        **Try saying things like:**
        - "I want to fly from Lahore to Karachi"
        - "Book a flight to Dubai tomorrow"  
        - "Two people from Islamabad to Multan next Monday"
        - "Business class ticket to Peshawar"
        - When asked if details are correct: **"Yes"**, **"Looks good"**, **"Search now"**
        - To make changes: **"Change the date"**, **"Actually, make it business class"**
        
        **Supported cities:** Lahore (LHE), Karachi (KHI), Islamabad (ISB), Multan (MUX), Peshawar (PEW), and more!
        
        💡 **No need to click search buttons** - just confirm when ready!
        """)

if __name__ == "__main__":
    main()
