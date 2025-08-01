import json
import requests
from datetime import datetime
from extract_parameters import extract_travel_info
from groq import Groq
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

class ConversationalTravelAgent:
    def __init__(self):
        self.auth_url = "https://bookmesky.com/partner/api/auth/token"
        self.api_url = "https://bookmesky.com/air/api/search"
        self.content_provider_api = "https://api.bookmesky.com/air/api/content-providers"
        self.username = "bookme-sky"
        self.password = "omi@work321"
        self.api_token = self.get_api_token()

        self.api_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}'
        }

        # Initialize Groq client
        try:
            self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            self.model_name = "meta-llama/llama-4-scout-17b-16e-instruct"
        except Exception as e:
            print(f"Warning: Failed to initialize Groq client: {e}")
            self.groq_client = None
            self.model_name = None
        
        # Cache for content providers to avoid repeated API calls
        self.content_providers_cache = {}
        
        # Conversation context
        self.conversation_history = []
        self.current_booking_info = {}

    def get_api_token(self):
        """Fetch API token using credentials from environment variables"""
        try:
            payload = {
                "username": self.username,
                "password": self.password
            }
            response = requests.post(
                self.auth_url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=10
            )

            if response.ok:
                token = response.json().get("Token")
                if token:
                    return token
                else:
                    raise Exception("Token not found in API response.")
            else:
                raise Exception(f"Auth failed: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"🔥 Error fetching token: {str(e)}")
            raise

    def get_content_providers(self, booking_info):
        """Fetch available content providers for given locations and travel class"""
        try:
            # Create cache key from locations and travel class
            source = booking_info.get('source', '')
            destination = booking_info.get('destination', '')
            travel_class = booking_info.get('flight_class', 'economy')
            cache_key = f"{source}-{destination}-{travel_class}"
            
            # Check cache first
            if cache_key in self.content_providers_cache:
                print(f"🔍 Using cached content providers for {source} → {destination}")
                return self.content_providers_cache[cache_key]
            
            # Build locations payload
            locations = []
            if source:
                locations.append({"IATA": source, "Type": "airport"})
            if destination:
                locations.append({"IATA": destination, "Type": "airport"})
            
            if not locations:
                print("❌ No locations provided for content provider search")
                return []
            
            payload = {
                "Locations": locations,
                "TravelClass": travel_class
            }
            
            print(f"🔍 Fetching content providers for {source} → {destination} in {travel_class} class...")
            
            response = requests.post(
                self.content_provider_api,
                headers=self.api_headers,
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract content provider names from response
                content_providers = []
                                
                if isinstance(data, dict):
                    # Handle different possible response structures
                    providers_data = data.get('data', data.get('providers', data.get('contentProviders', data)))
                    if isinstance(providers_data, list):
                        for provider in providers_data:
                            if isinstance(provider, dict):
                                # Try different possible field names, prioritizing ContentProvider
                                provider_name = provider.get('ContentProvider', provider.get('name', provider.get('code', provider.get('provider', provider.get('id')))))
                                if provider_name and isinstance(provider_name, str):
                                    content_providers.append(provider_name)
                            elif isinstance(provider, str):
                                content_providers.append(provider)
                    elif isinstance(providers_data, dict):
                        # If it's a dict, try to extract provider names from keys or values
                        for key, value in providers_data.items():
                            if isinstance(value, str):
                                content_providers.append(value)
                            elif isinstance(value, dict) and 'name' in value:
                                name = value['name']
                                if isinstance(name, str):
                                    content_providers.append(name)
                elif isinstance(data, list):
                    # Handle case where data is directly a list
                    for item in data:
                        if isinstance(item, str):
                            content_providers.append(item)
                        elif isinstance(item, dict):
                            # The API returns objects with ContentProvider field
                            provider_name = item.get('ContentProvider', item.get('name', item.get('code', item.get('provider', item.get('id')))))
                            if provider_name and isinstance(provider_name, str):
                                content_providers.append(provider_name)
                
                # Ensure all items are strings
                content_providers = [str(provider) for provider in content_providers if provider]
                
                # Cache the result
                self.content_providers_cache[cache_key] = content_providers
                
                # Safe join for printing
                provider_sample = [str(p) for p in content_providers[:5]]
                return content_providers
                
            else:
                return []
                
        except Exception as e:
            print(f"❌ Error fetching content providers: {str(e)}")
            print(f"🔍 Error details: {type(e).__name__}")
            if hasattr(e, '__traceback__'):
                import traceback
                print(f"🔍 Traceback: {traceback.format_exc()[-200:]}")
            return []

    def clear_content_providers_cache(self):
        """Clear the content providers cache"""
        self.content_providers_cache = {}
        print("🔄 Content providers cache cleared")

    def add_to_conversation(self, message, sender="user"):
        """Add message to conversation history"""
        self.conversation_history.append({
            "message": message,
            "sender": sender,
            "timestamp": datetime.now().isoformat()
        })

    def create_contextual_query(self, user_input):
        """Create a natural language contextual query that includes current booking information"""
        if not self.current_booking_info:
            return user_input
        
        try:
            # Build natural language context from current booking info
            natural_parts = []
            
            # Base travel information
            if self.current_booking_info.get('source') and self.current_booking_info.get('destination'):
                natural_parts.append(f"travel from {self.current_booking_info['source']} to {self.current_booking_info['destination']}")
            elif self.current_booking_info.get('source'):
                natural_parts.append(f"travel from {self.current_booking_info['source']}")
            elif self.current_booking_info.get('destination'):
                natural_parts.append(f"go to {self.current_booking_info['destination']}")
            
            # Passengers information - be specific about types
            passengers = self.current_booking_info.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
            passenger_parts = []
            if passengers['adults'] > 0:
                if passengers['adults'] == 1:
                    passenger_parts.append("1 adult")
                else:
                    passenger_parts.append(f"{passengers['adults']} adults")
            if passengers['children'] > 0:
                if passengers['children'] == 1:
                    passenger_parts.append("1 child")
                else:
                    passenger_parts.append(f"{passengers['children']} children")
            if passengers['infants'] > 0:
                if passengers['infants'] == 1:
                    passenger_parts.append("1 infant")
                else:
                    passenger_parts.append(f"{passengers['infants']} infants")
            
            if passenger_parts:
                natural_parts.append(f"with {' and '.join(passenger_parts)}")
            
            # Date information
            if self.current_booking_info.get('departure_date'):
                natural_parts.append(f"departing on {self.current_booking_info['departure_date']}")
            
            if self.current_booking_info.get('return_date'):
                natural_parts.append(f"returning on {self.current_booking_info['return_date']}")
            
            # Travel class
            if self.current_booking_info.get('flight_class'):
                class_name = self.current_booking_info['flight_class'].replace('_', ' ')
                natural_parts.append(f"in {class_name} class")
            
            # Flight type
            if self.current_booking_info.get('flight_type') == 'return':
                natural_parts.append("round trip")
            elif self.current_booking_info.get('flight_type') == 'one_way':
                natural_parts.append("one way")
            
            # Airline preference
            if self.current_booking_info.get('content_provider'):
                airline_name = self.current_booking_info['content_provider'].replace('_', ' ').title()
                natural_parts.append(f"with {airline_name}")
            
            # Create natural language contextual query
            if natural_parts:
                base_context = " ".join(natural_parts)
                contextual_query = f"{base_context}. Now {user_input}"
                return contextual_query
            
        except Exception as e:
            print(f"Error creating contextual query: {e}")
        
        return user_input

    def extract_with_context(self, user_input):
        """Extract travel information with booking context"""
        # Create contextual query that includes current booking information
        contextual_query = self.create_contextual_query(user_input)
        # Extract information from the contextual query
        extracted_info = extract_travel_info(contextual_query)
        
        return extracted_info

    def update_booking_info_intelligently(self, extracted_info):
        """Update booking info while preserving existing information"""
        if not extracted_info:
            return
                
        # Special handling for passengers to avoid resetting
        if extracted_info.get('passengers'):
            self.current_booking_info['passengers'] = extracted_info['passengers']
        elif not self.current_booking_info.get('passengers'):
            # If no passenger info exists, set default
            self.current_booking_info['passengers'] = {"adults": 1, "children": 0, "infants": 0}
        
        # Update other fields - ONLY if the extracted value is not None/empty/null
        for key, value in extracted_info.items():
            if key != 'passengers' and value is not None and value != '' and value != 'null':
                # Special handling for dates to avoid overwriting with None
                if key in ['departure_date', 'return_date'] and not value:
                    continue
                
                # Special handling for location codes
                if key in ['source', 'destination'] and (not value or len(str(value)) < 2):
                    continue
                
                self.current_booking_info[key] = value
        

    def generate_conversational_response(self, user_input, context_info=None):
        """Generate natural conversational responses using LLM"""
        try:
            # Build conversation context
            recent_conversation = "\n".join([
                f"{msg['sender'].title()}: {msg['message']}" 
                for msg in self.conversation_history[-4:]  # Last 4 messages for context
            ])
            
            current_info_summary = ""
            if self.current_booking_info:
                # Only show fields that have values
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
                    current_info_summary = f"Current booking info: {', '.join(info_parts)}"

            prompt = f"""
You are a friendly, helpful travel agent having a natural conversation with a traveler. Be conversational, warm, and efficient.

Recent conversation:
{recent_conversation}

{current_info_summary}

Context: {context_info if context_info else "Continue natural conversation"}

User just said: "{user_input}"

Rules:
1. Be natural and conversational - like talking to a friend
2. Don't repeat information unnecessarily 
3. If you have most details, smoothly ask for what's still needed
4. If confirming details, be concise and clear
5. Show enthusiasm but don't overdo it
6. Avoid repetitive questions about same information
7. If user changes something, acknowledge the change naturally
8. Keep responses focused and helpful
9. NEVER mention booking confirmation, payment, or ticket issuance - you are only SEARCHING for flights
10. Use terms like "search for flights", "find options", "look for flights" - NOT "book", "confirm booking", or "process payment"
11. If user confirms details, say you'll search for flights, not process a booking

Respond naturally:
"""
            
            # Use Groq instead of Gemini
            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model=self.model_name,
                    temperature=0.7,  # Slightly more creative for conversational responses
                    max_tokens=500,   # Reasonable limit for conversation
                    top_p=0.9
                )
                return chat_completion.choices[0].message.content.strip()
            else:
                # Fallback if Groq is not available
                raise Exception("Groq client not initialized")
            
        except Exception as e:
            print(f"LLM generation failed: {e}")
            # Provide better fallback responses
            if "missing" in str(context_info).lower():
                return "I just need a couple more details to find your flights. What else can you tell me about your trip?"
            return "Tell me more about your travel plans!"

    def process_user_input_conversationally(self, user_input):
        """Process user input in a conversational manner"""
        self.add_to_conversation(user_input, "user")
        
        try:
            # Extract travel information with context
            extracted_info = self.extract_with_context(user_input)
            
            # Update current booking info intelligently
            self.update_booking_info_intelligently(extracted_info)
            
            # Set default values for common fields if not specified (only if not already set)
            if not self.current_booking_info.get("flight_class"):
                self.current_booking_info["flight_class"] = "economy"
            if not self.current_booking_info.get("flight_type"):
                self.current_booking_info["flight_type"] = "one_way"
            if not self.current_booking_info.get('passengers'):
                self.current_booking_info['passengers'] = {"adults": 1, "children": 0, "infants": 0}
                            
            # Determine what's missing and generate appropriate response
            missing_info = self.identify_missing_information()
            
            if not missing_info:
                # All required information is available - move to confirmation
                response = self.generate_confirmation_summary()
                response_type = "confirmation"
            elif len(missing_info) <= 2:
                # Just a few things missing - ask conversationally
                response = self.generate_conversational_response(
                    user_input, 
                    f"Still need: {', '.join(missing_info)}"
                )
                response_type = "gathering_info"
            else:
                # Need more basic info - provide guidance
                response = self.generate_conversational_response(
                    user_input,
                    "User is providing initial travel information"
                )
                response_type = "initial_guidance"
                
            self.add_to_conversation(response, "assistant")
            
            return {
                "response": response,
                "type": response_type,
                "current_info": self.current_booking_info.copy(),
                "missing_info": missing_info
            }
            
        except Exception as e:
            error_response = "I'd love to help you with your travel plans! Could you tell me where you'd like to go and when?"
            self.add_to_conversation(error_response, "assistant")
            return {
                "response": error_response,
                "type": "error",
                "current_info": self.current_booking_info.copy(),
                "missing_info": []
            }

    def handle_modification_request(self, user_input):
        """Handle user requests to modify booking information"""
        self.add_to_conversation(user_input, "user")
        
        try:
            # Extract any new information from the modification request with context
            extracted_info = self.extract_with_context(user_input)
            
            # Store old info for comparison
            old_info = self.current_booking_info.copy()
            
            # Update current booking info intelligently
            self.update_booking_info_intelligently(extracted_info)
            
            # Generate response about what was changed
            changes_made = []
            if extracted_info:
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
            
            response = self.generate_conversational_response(user_input, context)
            self.add_to_conversation(response, "assistant")
            
            return {
                "response": response,
                "type": "modification",
                "current_info": self.current_booking_info.copy(),
                "missing_info": self.identify_missing_information()
            }
            
        except Exception as e:
            response = "I'd be happy to help you make changes! Could you tell me what you'd like to modify?"
            self.add_to_conversation(response, "assistant")
            return {
                "response": response,
                "type": "modification_error",
                "current_info": self.current_booking_info.copy(),
                "missing_info": []
            }

    def identify_missing_information(self):
        """Identify what information is still needed"""
        missing = []
        
        if not self.current_booking_info.get("source"):
            missing.append("departure_city")
        if not self.current_booking_info.get("destination"):
            missing.append("destination_city")
        if not self.current_booking_info.get("departure_date"):
            missing.append("departure_date")
        if not self.current_booking_info.get("flight_class"):
            missing.append("travel_class")
        if not self.current_booking_info.get("flight_type"):
            missing.append("trip_type")
        if self.current_booking_info.get("flight_type") == "return" and not self.current_booking_info.get("return_date"):
            missing.append("return_date")
        # Airline is now optional - removed from required fields
            
        return missing

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
            
            # Use Groq instead of Gemini
            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model=self.model_name,
                    temperature=0.6,  # Slightly creative but consistent
                    max_tokens=300,   # Shorter responses for confirmations
                    top_p=0.9
                )
                return chat_completion.choices[0].message.content.strip()
            else:
                # Fallback if Groq is not available
                raise Exception("Groq client not initialized")
            
        except Exception as e:
            # Fallback to simple confirmation
            route = f"{info.get('source', '?')} to {info.get('destination', '?')}"
            date = info.get('departure_date', 'your chosen date')
            passengers = info.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
            total = passengers['adults'] + passengers['children'] + passengers['infants']
            passenger_text = f"{total} passenger{'s' if total > 1 else ''}"
            return f"Great! I have your {route} flight for {date} with {passenger_text}. Ready to search for the best options?"

    def execute_flight_search_with_conversation(self):
        """Execute flight search with conversational feedback"""
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
            
            # Execute the actual search
            payload = self.format_api_payload(self.current_booking_info)
            if "error" in payload:
                error_response = f"Oops! There seems to be an issue with the booking details: {payload['error']}. Could you help me correct this?"
                self.add_to_conversation(error_response, "assistant")
                return {
                    "response": error_response,
                    "type": "error",
                    "status": "error"
                }
            
            # Perform the search
            specific_airline = self.current_booking_info.get("content_provider")
            search_results = self.search_flights_parallel(payload, self.current_booking_info, specific_airline)
            
            # Process results
            if specific_airline:
                flight_results = search_results[0] if search_results else {"error": "No results"}
                search_type = "single_airline"
            else:
                flight_results = self.aggregate_flight_results(search_results)
                search_type = "multi_airline"
            
            # Generate conversational results presentation
            results_response = self.generate_flight_results_response(flight_results, search_type)
            self.add_to_conversation(results_response, "assistant")
            
            return {
                "response": f"{search_start_msg}\n\n{results_response}",
                "type": "search_complete",
                "status": "complete",
                "flight_results": flight_results,
                "search_type": search_type
            }
            
        except Exception as e:
            error_response = f"I encountered an issue while searching for flights: {str(e)}. Would you like me to try again?"
            self.add_to_conversation(error_response, "assistant")
            return {
                "response": error_response,
                "type": "search_error",
                "status": "error"
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
            
            # Use Groq instead of Gemini
            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model=self.model_name,
                    temperature=0.5,  # Moderate creativity for enthusiasm
                    max_tokens=100,   # Very short messages
                    top_p=0.9
                )
                return chat_completion.choices[0].message.content.strip()
            else:
                # Fallback if Groq is not available
                raise Exception("Groq client not initialized")
            
        except Exception as e:
            return "Excellent! Let me search for the best flight options for you now!"

    def generate_flight_results_response(self, flight_results, search_type):
        """Generate a conversational response about flight results"""
        try:
            if search_type == "single_airline":
                if isinstance(flight_results, dict) and "error" in flight_results:
                    return f"I wasn't able to find flights with your preferred airline right now. {flight_results['error']} Would you like me to search across other airlines instead?"
                
                # Format single airline results
                context = f"Single airline search completed. Results type: {type(flight_results)}"
                
            else:
                # Multi-airline results
                total_flights = flight_results.get('total_flights', 0) if isinstance(flight_results, dict) else 0
                successful_airlines = flight_results.get('successful_airlines', 0) if isinstance(flight_results, dict) else 0
                
                if total_flights == 0:
                    context = f"Multi-airline search completed but no flights found. {successful_airlines} airlines responded successfully."
                else:
                    context = f"Multi-airline search completed successfully. Found {total_flights} flights across {successful_airlines} airlines."
            
            # Generate natural response about results
            prompt = f"""
Flight search has been completed. Context: {context}

Generate a conversational, helpful response that:
1. Presents the flight search results in a natural way
2. Highlights key findings or best options if available
3. Mentions any issues or alternatives if no flights found
4. Maintains a helpful, professional tone
5. Offers next steps or asks what the user would prefer
6. NEVER mentions booking, payment, or ticket confirmation - only search results

Keep it conversational and informative:
"""
            
            # Use Groq instead of Gemini
            if self.groq_client and self.model_name:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model=self.model_name,
                    temperature=0.6,  # Balanced creativity for results presentation
                    max_tokens=400,   # Reasonable length for results
                    top_p=0.9
                )
                llm_response = chat_completion.choices[0].message.content.strip()
            else:
                # Fallback if Groq is not available
                llm_response = "I've completed your flight search! Here are the results:"
            
            # Combine with formatted flight data
            formatted_results = self.format_flight_results_for_display(flight_results, search_type)
            
            return f"{llm_response}\n\n{formatted_results}"
            
        except Exception as e:
            return f"I've completed your flight search! Here are the results:\n\n{self.format_flight_results_for_display(flight_results, search_type)}"

    def reset_conversation(self):
        """Reset conversation state for new booking"""
        self.conversation_history = []
        self.current_booking_info = {}
        self.content_providers_cache = {}  # Clear cache for new conversation
        
        welcome_msg = "Hello! I'm your travel assistant, and I'm excited to help you find the perfect flight! ✈️ Tell me about your travel plans - where would you like to go?"
        self.add_to_conversation(welcome_msg, "assistant")
        return welcome_msg

    # Include all the original technical methods (search_flights_parallel, format_api_payload, etc.)
    # These remain the same as they handle the API interactions
    
    def format_api_payload(self, info, airline=None):
        """Format the extracted information into API payload"""
        try:
            # Build locations
            locations = []
            if info.get("source"):
                locations.append({"IATA": info["source"], "Type": "airport"})
            if info.get("destination"):
                locations.append({"IATA": info["destination"], "Type": "airport"})
            
            # Build traveling dates
            traveling_dates = []
            if info.get("departure_date"):
                traveling_dates.append(info["departure_date"])
            if info.get("return_date"):
                traveling_dates.append(info["return_date"])
            
            # Build travelers
            passengers = info.get("passengers", {"adults": 1, "children": 0, "infants": 0})
            travelers = []
            if passengers["adults"] > 0:
                travelers.append({"Type": "adult", "Count": passengers["adults"]})
            if passengers["children"] > 0:
                travelers.append({"Type": "child", "Count": passengers["children"]})
            if passengers["infants"] > 0:
                travelers.append({"Type": "infant", "Count": passengers["infants"]})
            
            # Build payload
            payload = {
                "Locations": locations,
                "Currency": "PKR",
                "TravelClass": info.get("flight_class", "economy"),
                "TripType": info.get("flight_type", "one_way"),
                "TravelingDates": traveling_dates,
                "Travelers": travelers
            }
            
            # Add content provider
            content_provider = airline or info.get("content_provider")
            if content_provider:
                payload["ContentProvider"] = content_provider
                
            return payload
            
        except Exception as e:
            return {"error": f"Failed to format payload: {str(e)}"}
    
    def search_single_airline(self, payload, airline_name=None):
        """Search flights for a single airline"""
        try:
            search_payload = payload.copy()
            if airline_name:
                search_payload["ContentProvider"] = airline_name
            
            response = requests.post(
                self.api_url,
                headers=self.api_headers,
                json=search_payload,
                timeout=30
            )
            
            # Only consider status code 200 as successful
            if response.status_code == 200:
                result = response.json()
                result["airline"] = airline_name or "All Airlines"
                result["search_payload"] = search_payload
                result["status_code"] = 200  # Mark as successful
                return result
            else:
                error_msg = f"API request failed with status {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        if "message" in error_data:
                            error_msg += f": {error_data['message']}"
                        elif "error" in error_data:
                            error_msg += f": {error_data['error']}"
                    except:
                        error_msg += f": {response.text[:200]}"
                
                return {
                    "error": error_msg,
                    "status_code": response.status_code,
                    "airline": airline_name or "All Airlines"
                }
                
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Network error: {str(e)}", 
                "airline": airline_name or "All Airlines",
                "status_code": 0
            }
        except Exception as e:
            return {
                "error": f"Unexpected error: {str(e)}", 
                "airline": airline_name or "All Airlines",
                "status_code": 0
            }
    
    def search_flights_parallel(self, payload, booking_info, specific_airline=None):
        """Search flights across available content providers or single airline"""
        
        if specific_airline:
            print(f"🔍 Searching flights for {specific_airline}...")
            return [self.search_single_airline(payload, specific_airline)]
        
        # Fetch available content providers for the route
        content_providers = self.get_content_providers(booking_info)
        
        if not content_providers:
            print("❌ No content providers found for this route. Using fallback search...")
            # Fallback to search without specific provider
            return [self.search_single_airline(payload, None)]
        
        print(f"🔍 Searching flights across {len(content_providers)} available providers...")
        
        results = []
        successful_searches = 0
        failed_searches = 0
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_airline = {
                executor.submit(self.search_single_airline, payload, provider): provider 
                for provider in content_providers
            }
            
            for future in as_completed(future_to_airline):
                provider = future_to_airline[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Check if this is a successful response (status code 200)
                    if "error" in result or result.get("status_code") != 200:
                        failed_searches += 1
                        error_msg = result.get('error', 'Unknown error')
                        print(f"❌ {provider}: {error_msg}")
                    else:
                        successful_searches += 1
                        # Extract flight count for logging
                        extracted_flights = self.extract_flight_information(result)
                        flight_count = len(extracted_flights)
                        
                except Exception as e:
                    failed_searches += 1
                    print(f"❌ {provider}: Exception occurred - {str(e)}")
                    results.append({
                        "error": f"Thread execution failed: {str(e)}",
                        "airline": provider,
                        "status_code": 0
                    })
        
        print(f"📊 Search Summary: {successful_searches} successful, {failed_searches} failed API calls")
        return results
    
    def aggregate_flight_results(self, results):
        """Aggregate and sort flight results from multiple airlines"""
        all_flights = []
        errors = []
        successful_results = []
        
        for result in results:
            airline = result.get("airline", "Unknown")
            
            # Only consider results with status code 200 as successful
            if "error" in result or result.get("status_code") != 200:
                errors.append({
                    "airline": airline,
                    "error": result.get("error", "API call failed"),
                    "status_code": result.get("status_code", 0)
                })
                continue
            
            successful_results.append(result)
            
            # Extract structured flight information first
            extracted_flights = self.extract_flight_information(result)
            if extracted_flights:
                for flight in extracted_flights:
                    flight["source_airline"] = airline
                    # Add a sortable price field from the lowest fare option
                    if flight.get('fare_options'):
                        lowest_fare = min(flight['fare_options'], key=lambda x: x.get('total_fare', 999999))
                        flight["sortable_price"] = lowest_fare.get('total_fare', 999999)
                    all_flights.append(flight)
                continue
            
            # Fallback to old method if extraction fails
            flights = None
            if "data" in result and result["data"]:
                flights = result["data"]
            elif "flights" in result and result["flights"]:
                flights = result["flights"]
            elif "results" in result and result["results"]:
                flights = result["results"]
            elif "itineraries" in result and result["itineraries"]:
                flights = result["itineraries"]
            else:
                if isinstance(result, dict) and any(key in result for key in ["price", "cost", "totalPrice", "fare"]):
                    flights = [result]
            
            if flights:
                if isinstance(flights, list):
                    for flight in flights:
                        if isinstance(flight, dict):
                            flight["source_airline"] = airline
                            all_flights.append(flight)
                elif isinstance(flights, dict):
                    flights["source_airline"] = airline
                    all_flights.append(flights)
        
        try:
            def get_price(flight):
                # First try the sortable_price field from extracted flights
                if 'sortable_price' in flight:
                    return flight['sortable_price']
                
                # Fallback to old price extraction
                price_fields = ["price", "totalPrice", "cost", "fare", "amount"]
                for field in price_fields:
                    if field in flight and flight[field] is not None:
                        try:
                            return float(flight[field])
                        except (ValueError, TypeError):
                            continue
                return 999999
            
            all_flights.sort(key=get_price)
        except Exception as e:
            print(f"Warning: Could not sort flights by price: {e}")
        
        return {
            "flights": all_flights[:50],
            "total_flights": len(all_flights),
            "successful_airlines": len(successful_results),
            "successful_results": successful_results,
            "errors": errors
        }
    
    def extract_flight_information(self, api_response):
        """Extract structured flight information from API response"""
        try:
            extracted_flights = []
            
            # Handle the response structure
            if isinstance(api_response, dict):
                itineraries = api_response.get('Itineraries', [])
                
                for itinerary in itineraries:
                    flights_list = itinerary.get('Flights', [])
                    
                    for flight in flights_list:
                        # Extract basic flight info
                        segments = flight.get('Segments', [])
                        if not segments:
                            continue
                            
                        # Get the first segment for main flight info
                        first_segment = segments[0]
                        
                        # Extract flight details
                        flight_info = {
                            "flight_number": f"{first_segment.get('OperatingCarrier', {}).get('iata', '')}-{first_segment.get('FlightNumber', '')}",
                            "airline": first_segment.get('OperatingCarrier', {}).get('name', 'Unknown'),
                            "origin": first_segment.get('From', {}).get('iata', ''),
                            "destination": first_segment.get('To', {}).get('iata', ''),
                            "departure_time": self.format_time(first_segment.get('DepartureAt', '')),
                            "arrival_time": self.format_time(first_segment.get('ArrivalAt', '')),
                            "duration": self.format_duration(first_segment.get('FlightTime', 0)),
                            "fare_options": []
                        }
                        
                        # Extract fare options
                        fares = flight.get('Fares', [])
                        for fare in fares:
                            # Extract baggage info
                            baggage_policy = fare.get('BaggagePolicy', [])
                            hand_baggage_kg = 0
                            checked_baggage_kg = 0
                            
                            for baggage in baggage_policy:
                                if baggage.get('Type') == 'carry':
                                    hand_baggage_kg = baggage.get('WeightLimit', 0)
                                elif baggage.get('Type') == 'checked':
                                    checked_baggage_kg = baggage.get('WeightLimit', 0)
                            
                            # Extract refund policy
                            policies = fare.get('Policies', [])
                            refund_fee_48h = 0
                            refundable_before_48h = False
                            
                            for policy in policies:
                                if policy.get('Type') == 'refund' and '48 hours' in policy.get('Description', ''):
                                    refund_fee_48h = policy.get('Charges', 0)
                                    refundable_before_48h = True
                                    break
                            
                            fare_info = {
                                "fare_name": fare.get('Name', ''),
                                "base_fare": fare.get('ChargedBasePrice', 0),
                                "total_fare": fare.get('ChargedTotalPrice', 0),
                                "refundable_before_48h": refundable_before_48h,
                                "refund_fee_48h": refund_fee_48h,
                                "hand_baggage_kg": hand_baggage_kg,
                                "checked_baggage_kg": checked_baggage_kg
                            }
                            
                            flight_info["fare_options"].append(fare_info)
                        
                        extracted_flights.append(flight_info)
            
            return extracted_flights
            
        except Exception as e:
            print(f"❌ Error extracting flight information: {str(e)}")
            return []
    
    def format_time(self, datetime_str):
        """Format datetime string to HH:MM format"""
        try:
            if datetime_str:
                # Parse the datetime string (format: 2025-08-04T17:30:00+05:00)
                from datetime import datetime
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                return dt.strftime('%H:%M')
        except:
            pass
        return 'N/A'
    
    def format_duration(self, minutes):
        """Format duration in minutes to Xh Ym format"""
        try:
            if minutes and isinstance(minutes, int):
                hours = minutes // 60
                mins = minutes % 60
                if hours > 0:
                    return f"{hours}h {mins}m"
                else:
                    return f"{mins}m"
        except:
            pass
        return 'N/A'

    def format_flight_results_for_display(self, flight_results, search_type="multi_airline"):
        """Format flight results for better display to user"""
        try:
            if search_type == "single_airline":
                if isinstance(flight_results, list) and len(flight_results) > 0:
                    result = flight_results[0]
                    if "error" in result:
                        return f"❌ Search Error: {result['error']}"
                    
                    # Extract structured flight information
                    extracted_flights = self.extract_flight_information(result)
                    if extracted_flights:
                        return self.format_extracted_flights_display(extracted_flights)
                    else:
                        flights_data = result.get('data', result.get('flights', result))
                        airline_name = result.get('airline', 'Unknown Airline')
                        
                        if not flights_data or (isinstance(flights_data, list) and len(flights_data) == 0):
                            return f"No flights found for {airline_name}."
                        
                        return self.format_single_airline_display(flights_data, airline_name)
                else:
                    return "No flight results received."
            
            else:
                if not flight_results or not isinstance(flight_results, dict):
                    return "No flight results received from the search."
                
                total_flights = flight_results.get('total_flights', 0)
                successful_airlines = flight_results.get('successful_airlines', 0)
                flights = flight_results.get('flights', [])
                errors = flight_results.get('errors', [])
                
                if total_flights == 0:
                    if successful_airlines > 0:
                        return f"I searched {successful_airlines + len(errors)} airlines successfully, but unfortunately no flights are available for your specific criteria. You might want to try different dates or nearby airports."
                    else:
                        return "I wasn't able to connect to the airline systems right now. Please try again in a few minutes."
                
                # Try to extract structured information from successful results
                all_extracted_flights = []
                successful_results = flight_results.get('successful_results', [])
                
                for result in successful_results:
                    if 'error' not in result:
                        extracted_flights = self.extract_flight_information(result)
                        all_extracted_flights.extend(extracted_flights)
                
                if all_extracted_flights:
                    return self.format_extracted_flights_display(all_extracted_flights[:10])  # Show top 10
                else:
                    return self.format_multi_airline_display(flights, total_flights, successful_airlines, errors)
                
        except Exception as e:
            return f"I found some flight options but had trouble formatting them. The search was successful though!"

    def format_extracted_flights_display(self, extracted_flights):
        """Format extracted flight information for clean display"""
        try:
            if not extracted_flights:
                return "No flight information could be extracted."
            
            display_text = "🛫 **Flight Options Found:**\n\n"
            
            for i, flight in enumerate(extracted_flights[:5], 1):  # Show top 5 flights
                display_text += f"**Flight {i}: {flight['airline']} {flight['flight_number']}**\n"
                display_text += f"📍 {flight['origin']} → {flight['destination']}\n"
                display_text += f"🕐 {flight['departure_time']} → {flight['arrival_time']} ({flight['duration']})\n"
                
                # Display fare options
                if flight.get('fare_options'):
                    display_text += f"💰 **Fare Options:**\n"
                    
                    for fare in flight['fare_options']:
                        baggage_info = f"Hand: {fare['hand_baggage_kg']}kg"
                        if fare['checked_baggage_kg'] > 0:
                            baggage_info += f" | Checked: {fare['checked_baggage_kg']}kg"
                        else:
                            baggage_info += " | No checked baggage"
                        
                        refund_info = ""
                        if fare['refundable_before_48h']:
                            refund_info = f" | Refund fee: PKR {fare['refund_fee_48h']}"
                        else:
                            refund_info = " | Non-refundable"
                        
                        display_text += f"   • **{fare['fare_name']}**: PKR {fare['total_fare']:,} ({baggage_info}{refund_info})\n"
                
                display_text += "\n"
            
            if len(extracted_flights) > 5:
                display_text += f"... and {len(extracted_flights) - 5} more options available\n"
            
            return display_text
            
        except Exception as e:
            print(f"Error formatting extracted flights: {e}")
            return "Flight information found but could not be formatted properly."

    def format_single_airline_display(self, flights_data, airline_name):
        """Format single airline flight data for display"""
        try:
            display_text = f"Here are the available flights with {airline_name}:\n\n"
            
            if isinstance(flights_data, dict):
                segments = flights_data.get('segments', flights_data.get('itineraries', [flights_data]))
            elif isinstance(flights_data, list):
                segments = flights_data
            else:
                segments = [flights_data]
            
            for i, flight in enumerate(segments[:5], 1):
                display_text += f"✈️ **Option {i}:**\n"
                
                price = flight.get('price', flight.get('totalPrice', flight.get('cost', 'N/A')))
                departure_time = flight.get('departureTime', flight.get('departure', 'N/A'))
                arrival_time = flight.get('arrivalTime', flight.get('arrival', 'N/A'))
                duration = flight.get('duration', flight.get('flightDuration', 'N/A'))
                
                display_text += f"   💰 Price: PKR {price}\n"
                display_text += f"   🛫 Departure: {departure_time}\n"
                display_text += f"   🛬 Arrival: {arrival_time}\n"
                display_text += f"   ⏱️ Duration: {duration}\n\n"
                
            return display_text
            
        except Exception as e:
            return f"Found flights with {airline_name} but couldn't display all details."

    def format_multi_airline_display(self, flights, total_flights, successful_airlines, errors):
        """Format multi-airline flight data for display"""
        try:
            display_text = f"Great news! I found {total_flights} flight options across {successful_airlines} airlines:\n\n"
            
            if not flights:
                return "I completed the search but couldn't retrieve the detailed flight information."
            
            airline_groups = {}
            for flight in flights[:10]:
                airline = flight.get('source_airline', flight.get('airline', 'Unknown'))
                if airline not in airline_groups:
                    airline_groups[airline] = []
                airline_groups[airline].append(flight)
            
            for airline, airline_flights in airline_groups.items():
                display_text += f"✈️ **{airline.upper().replace('_', ' ')}** ({len(airline_flights)} options):\n"
                
                for i, flight in enumerate(airline_flights[:3], 1):
                    price = flight.get('price', flight.get('totalPrice', flight.get('cost', 'N/A')))
                    departure_time = flight.get('departureTime', flight.get('departure', 'N/A'))
                    arrival_time = flight.get('arrivalTime', flight.get('arrival', 'N/A'))
                    duration = flight.get('duration', flight.get('flightDuration', 'N/A'))
                    
                    display_text += f"   💰 PKR {price} | 🛫 {departure_time} → 🛬 {arrival_time} | ⏱️ {duration}\n"
                
                display_text += "\n"
            
            if errors and len(errors) > 0:
                display_text += f"(Note: {len(errors)} airlines had temporary connection issues)\n"
            
            return display_text
            
        except Exception as e:
            return f"Found {total_flights} flights but had some display issues. The search was successful!"

def main_terminal_chat():
    """A simple terminal-based chat interface for the ConversationalTravelAgent."""
    print("✈️ Welcome to the Conversational Travel Agent!")
    print("Type 'quit' or 'exit' to end the chat, or 'restart' to begin a new search.")
    print("-" * 50)

    agent = ConversationalTravelAgent()

    # Initial welcome message from the agent
    welcome_message = agent.reset_conversation()
    print(f"Assistant: {welcome_message}")

    while True:
        try:
            user_input = input("You: ").strip()

            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("Assistant: Goodbye! Have a great day.")
                break

            if user_input.lower() in ['restart', 'start over']:
                welcome_message = agent.reset_conversation()
                print(f"Assistant: {welcome_message}")
                continue

            # Process the user's input conversationally
            result = agent.process_user_input_conversationally(user_input)
            
            print(f"Assistant: {result['response']}")

            # If the agent is ready for confirmation, ask the user to proceed
            if result.get("type") == "confirmation":
                print("-" * 50)
                print("Assistant: Type 'yes' to search for flights, or just tell me what you'd like to change.")
                
                confirm_input = input("You: ").strip().lower()

                if confirm_input in ['yes', 'y', 'ok', 'sure', 'go ahead', 'search']:
                    # Execute the flight search
                    search_results = agent.execute_flight_search_with_conversation()
                    
                    # The search function already generates conversational output
                    print(f"\n{search_results['response']}")
                    
                    print("-" * 50)
                    print("Assistant: What would you like to do next? You can start a 'new search' or 'quit'.")

                else:
                    # If user doesn't say 'yes', their input is treated as a modification request in the next loop iteration.
                    # We pass their input directly to the conversational processor.
                    print("Assistant: Understood. Let's update your request.")
                    modification_result = agent.process_user_input_conversationally(confirm_input)
                    print(f"Assistant: {modification_result['response']}")

        except (KeyboardInterrupt, EOFError):
            print("\nAssistant: Goodbye! Have a great day.")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}. Let's try again.")
            agent.reset_conversation()

if __name__ == "__main__":
    # This block allows the file to be used as a library by the server,
    # but also run as a standalone chat client.
    main_terminal_chat()