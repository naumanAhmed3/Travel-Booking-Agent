import json
import requests
import traceback
from datetime import datetime
from extract_parameters import extract_travel_info
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

def tool(func):
    """Decorator to mark functions as tools"""
    func.is_tool = True
    return func

class FlightSearchEngine:
    """Engine for flight search and API operations"""
    
    def __init__(self):
        self.auth_url = "https://bookmesky.com/partner/api/auth/token"
        self.api_url = "https://bookmesky.com/air/api/search"
        self.content_provider_api = "https://api.bookmesky.com/air/api/content-providers"
        self.username = os.getenv("BOOKME_SKY_USERNAME")
        self.password = os.getenv("BOOKME_SKY_PASSWORD")
        self.api_token = self.get_api_token()

        self.api_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_token}'
        }
        
        # Cache for content providers to avoid repeated API calls
        self.content_providers_cache = {}

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
                print(f"🔍 Traceback: {traceback.format_exc()[-200:]}")
            return []

    def clear_content_providers_cache(self):
        """Clear the content providers cache"""
        self.content_providers_cache = {}
        print("🔄 Content providers cache cleared")

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
        successful_with_flights = []  # Track results that actually have flights
        
        for result in results:
            airline = result.get("airline", "Unknown")
            
            # Only consider results with status code 200 as successful API calls
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
                # This airline actually returned flights
                successful_with_flights.append(result)
                for flight in extracted_flights:
                    flight["source_airline"] = airline
                    # Add a sortable price field from the lowest fare option
                    if flight.get('fare_options'):
                        lowest_fare = min(flight['fare_options'], key=lambda x: x.get('total_fare', 999999))
                        flight["sortable_price"] = lowest_fare.get('total_fare', 999999)
                    all_flights.append(flight)
                continue
            else:
                # API call was successful but no flights found
                print(f"📭 {airline}: API call successful but no flights found")
                continue
            
            # Fallback to old method if extraction fails (should rarely happen now)
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
                successful_with_flights.append(result)
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
        
        print(f"📊 Final Results: {len(successful_with_flights)} airlines with flights, {len(all_flights)} total flights")
        
        return {
            "flights": all_flights[:50],
            "total_flights": len(all_flights),
            "successful_airlines": len(successful_results),  # API calls that succeeded
            "airlines_with_flights": len(successful_with_flights),  # Airlines that actually had flights
            "successful_results": successful_results,
            "results_with_flights": successful_with_flights,  # Results that actually contain flights
            "errors": errors
        }
    
    def extract_flight_information(self, api_response):
        """Extract structured flight information from API response"""
        try:
            extracted_flights = []
            
            # Handle the response structure
            if isinstance(api_response, dict):
                itineraries = api_response.get('Itineraries', [])
                
                # Check if itineraries is empty or None
                if not itineraries:
                    print(f"📋 No itineraries found in API response for {api_response.get('airline', 'Unknown airline')}")
                    return []
                
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
                                if policy.get('Type') == 'refund':
                                    refund_fee_48h = policy.get('Charges', 0)
                                    refundable_before_48h = refund_fee_48h > 0
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
                        
                print(f"✅ Extracted {len(extracted_flights)} flights from {api_response.get('airline', 'Unknown airline')}")
            
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
                airlines_with_flights = flight_results.get('airlines_with_flights', 0)
                successful_api_calls = flight_results.get('successful_airlines', 0)
                flights = flight_results.get('flights', [])
                errors = flight_results.get('errors', [])
                
                if total_flights == 0:
                    if successful_api_calls > 0:
                        # APIs responded but no flights available
                        total_contacted = successful_api_calls + len(errors)
                        return f"I searched {total_contacted} airlines successfully, but unfortunately no flights are available for your specific criteria. You might want to try different dates or nearby airports."
                    else:
                        return "I wasn't able to connect to the airline systems right now. Please try again in a few minutes."
                
                # Try to extract structured information from results that actually have flights
                all_extracted_flights = []
                results_with_flights = flight_results.get('results_with_flights', [])
                
                for result in results_with_flights:
                    if 'error' not in result:
                        extracted_flights = self.extract_flight_information(result)
                        all_extracted_flights.extend(extracted_flights)
                
                if all_extracted_flights:
                    return self.format_extracted_flights_display(all_extracted_flights[:10])  # Show top 10
                else:
                    return self.format_multi_airline_display(flights, total_flights, airlines_with_flights, errors)
                
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

    def format_multi_airline_display(self, flights, total_flights, airlines_with_flights, errors):
        """Format multi-airline flight data for display"""
        try:
            display_text = f"Great news! I found {total_flights} flight options from {airlines_with_flights} airlines:\n\n"
            
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


# Initialize the flight search engine
flight_search_engine = FlightSearchEngine()

@tool
def search_flights_with_context(user_input: str, current_booking_info: dict) -> dict:
    """
    Search for flights using the provided booking information and user input.
    
    This tool extracts travel information from user input, combines it with existing booking context,
    searches across multiple airlines, and returns formatted flight results.
    
    Args:
        user_input (str): The user's natural language input about their travel needs
        current_booking_info (dict): Current booking information context containing:
            - source (str): Origin airport code
            - destination (str): Destination airport code  
            - departure_date (str): Departure date
            - return_date (str): Return date (for round trips)
            - flight_class (str): Travel class (economy, business, etc.)
            - flight_type (str): Trip type (one_way, return)
            - passengers (dict): Passenger counts {adults, children, infants}
            - content_provider (str): Preferred airline (optional)
    
    Returns:
        dict: Search results containing:
            - status (str): 'success', 'error', or 'missing_info'
            - message (str): Human-readable description of results
            - flight_results (dict): Detailed flight information if found
            - formatted_display (str): User-friendly formatted flight results
            - missing_info (list): List of missing required information
    """
    try:
        # Create contextual query from current booking info
        if current_booking_info:
            natural_parts = []
            
            # Base travel information
            if current_booking_info.get('source') and current_booking_info.get('destination'):
                natural_parts.append(f"travel from {current_booking_info['source']} to {current_booking_info['destination']}")
            elif current_booking_info.get('source'):
                natural_parts.append(f"travel from {current_booking_info['source']}")
            elif current_booking_info.get('destination'):
                natural_parts.append(f"go to {current_booking_info['destination']}")
            
            # Passengers information
            passengers = current_booking_info.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
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
            if current_booking_info.get('departure_date'):
                natural_parts.append(f"departing on {current_booking_info['departure_date']}")
            
            if current_booking_info.get('return_date'):
                natural_parts.append(f"returning on {current_booking_info['return_date']}")
            
            # Travel class
            if current_booking_info.get('flight_class'):
                class_name = current_booking_info['flight_class'].replace('_', ' ')
                natural_parts.append(f"in {class_name} class")
            
            # Flight type
            if current_booking_info.get('flight_type') == 'return':
                natural_parts.append("round trip")
            elif current_booking_info.get('flight_type') == 'one_way':
                natural_parts.append("one way")
            
            # Airline preference
            if current_booking_info.get('content_provider'):
                airline_name = current_booking_info['content_provider'].replace('_', ' ').title()
                natural_parts.append(f"with {airline_name}")
            
            # Create contextual query
            if natural_parts:
                base_context = " ".join(natural_parts)
                contextual_query = f"{base_context}. Now {user_input}"
            else:
                contextual_query = user_input
        else:
            contextual_query = user_input
        
        # Extract travel information from contextual query
        extracted_info = extract_travel_info(contextual_query)
        
        # Merge extracted info with current booking info
        merged_booking_info = current_booking_info.copy() if current_booking_info else {}
        
        if extracted_info:
            # Special handling for passengers to avoid resetting
            if extracted_info.get('passengers'):
                merged_booking_info['passengers'] = extracted_info['passengers']
            elif not merged_booking_info.get('passengers'):
                merged_booking_info['passengers'] = {"adults": 1, "children": 0, "infants": 0}
            
            # Update other fields - ONLY if the extracted value is not None/empty/null
            for key, value in extracted_info.items():
                if key != 'passengers' and value is not None and value != '' and value != 'null':
                    # Special handling for dates to avoid overwriting with None
                    if key in ['departure_date', 'return_date'] and not value:
                        continue
                    
                    # Special handling for location codes
                    if key in ['source', 'destination'] and (not value or len(str(value)) < 2):
                        continue
                    
                    merged_booking_info[key] = value
        
        # Set defaults if not specified
        if not merged_booking_info.get("flight_class"):
            merged_booking_info["flight_class"] = "economy"
        if not merged_booking_info.get("flight_type"):
            merged_booking_info["flight_type"] = "one_way"
        if not merged_booking_info.get('passengers'):
            merged_booking_info['passengers'] = {"adults": 1, "children": 0, "infants": 0}
        
        # Check for missing required information
        missing = []
        if not merged_booking_info.get("source"):
            missing.append("departure_city")
        if not merged_booking_info.get("destination"):
            missing.append("destination_city")
        if not merged_booking_info.get("departure_date"):
            missing.append("departure_date")
        if merged_booking_info.get("flight_type") == "return" and not merged_booking_info.get("return_date"):
            missing.append("return_date")
        
        if missing:
            return {
                "status": "missing_info",
                "message": f"Missing required information: {', '.join(missing)}",
                "missing_info": missing,
                "updated_booking_info": merged_booking_info
            }
        
        # Format API payload
        payload = flight_search_engine.format_api_payload(merged_booking_info)
        if "error" in payload:
            return {
                "status": "error",
                "message": f"Failed to format search parameters: {payload['error']}",
                "updated_booking_info": merged_booking_info
            }
        
        # Execute search
        specific_airline = merged_booking_info.get("content_provider")
        search_results = flight_search_engine.search_flights_parallel(payload, merged_booking_info, specific_airline)
        
        # Process results
        if specific_airline:
            flight_results = search_results[0] if search_results else {"error": "No results"}
            search_type = "single_airline"
        else:
            flight_results = flight_search_engine.aggregate_flight_results(search_results)
            search_type = "multi_airline"
        
        # Format results for display
        formatted_display = flight_search_engine.format_flight_results_for_display(flight_results, search_type)
        
        return {
            "status": "success",
            "message": "Flight search completed successfully",
            "flight_results": flight_results,
            "formatted_display": formatted_display,
            "search_type": search_type,
            "updated_booking_info": merged_booking_info
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Flight search failed: {str(e)}",
            "updated_booking_info": current_booking_info or {}
        }


@tool
def extract_travel_parameters(user_input: str, current_context: dict = None) -> dict:
    """
    Extract structured travel information from natural language user input.
    
    This tool parses user input to extract travel-related parameters like cities, dates,
    passenger counts, flight class, and trip type. It can work with or without existing context.
    
    Args:
        user_input (str): Natural language input describing travel requirements
        current_context (dict, optional): Existing booking context to enhance extraction
    
    Returns:
        dict: Extracted travel parameters containing:
            - source (str): Origin city/airport code
            - destination (str): Destination city/airport code
            - departure_date (str): Departure date in YYYY-MM-DD format
            - return_date (str): Return date for round trips
            - flight_class (str): Travel class (economy, business, first)
            - flight_type (str): Trip type (one_way, return)
            - passengers (dict): Passenger counts {adults, children, infants}
            - content_provider (str): Preferred airline if specified
    """
    try:
        # Create contextual query if context is provided - this preserves existing booking information
        contextual_query = create_contextual_query(user_input, current_context)
        
        # Extract travel information
        extracted_info = extract_travel_info(contextual_query)
        
        return {
            "status": "success",
            "extracted_info": extracted_info or {},
            "message": "Travel parameters extracted successfully"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to extract travel parameters: {str(e)}",
            "extracted_info": {}
        }

def create_contextual_query(user_input: str, current_context: dict = None) -> str:
    """
    Create a natural language contextual query that includes current booking information.
    This is crucial for preserving context when users provide incremental information.
    """
    if not current_context:
        return user_input
    
    try:
        # Build natural language context from current booking info
        natural_parts = []
        
        # Base travel information
        if current_context.get('source') and current_context.get('destination'):
            natural_parts.append(f"travel from {current_context['source']} to {current_context['destination']}")
        elif current_context.get('source'):
            natural_parts.append(f"travel from {current_context['source']}")
        elif current_context.get('destination'):
            natural_parts.append(f"go to {current_context['destination']}")
        
        # Passengers information - be specific about types
        passengers = current_context.get('passengers', {'adults': 1, 'children': 0, 'infants': 0})
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
        if current_context.get('departure_date'):
            natural_parts.append(f"departing on {current_context['departure_date']}")
        
        if current_context.get('return_date'):
            natural_parts.append(f"returning on {current_context['return_date']}")
        
        # Travel class
        if current_context.get('flight_class'):
            class_name = current_context['flight_class'].replace('_', ' ')
            natural_parts.append(f"in {class_name} class")
        
        # Flight type
        if current_context.get('flight_type') == 'return':
            natural_parts.append("round trip")
        elif current_context.get('flight_type') == 'one_way':
            natural_parts.append("one way")
        
        # Airline preference
        if current_context.get('content_provider'):
            airline_name = current_context['content_provider'].replace('_', ' ').title()
            natural_parts.append(f"with {airline_name}")
        
        # Create natural language contextual query
        if natural_parts:
            base_context = " ".join(natural_parts)
            contextual_query = f"{base_context}. Now {user_input}"
            print(f"🔍 Contextual query created: {contextual_query}")
            return contextual_query
        
    except Exception as e:
        print(f"Error creating contextual query: {e}")
    
    return user_input
