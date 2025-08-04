import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from dotenv import load_dotenv
from groq import Groq


load_dotenv()  # Load environment variables from .env file

# City to IATA mapping - same as original
city_to_iata = {
    "lahore": "LHE",
    "karachi": "KHI",
    "islamabad": "ISB",
    "rawalpindi": "ISB",   # shares ISB airport
    "multan": "MUX",
    "peshawar": "PEW",
    "quetta": "UET",
    "faisalabad": "LYP",
    "sialkot": "SKT",
    "skardu": "KDU",
    "gilgit": "GIL",
    "sukkur": "SKZ",
    "gwadar": "GWD",
    "turbat": "TUK",
    "bahawalpur": "BHV",
    "dera ghazi khan": "DEA",
    "chitral": "CJL",
    "panjgur": "PJG",
    "moenjodaro": "MJD",
    "parachinar": "PAJ",
    "zhob": "PZH",
    "dalbandin": "DBA",
    "muzaffarabad": "MFG",
    "rahim yar khan": "RYK",
    "nawabshah": "WNS",
    # International cities
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "sharjah": "SHJ",
    "doha": "DOH",
    "muscat": "MCT",
    "kuwait": "KWI",
    "riyadh": "RUH",
    "jeddah": "JED",
    "dammam": "DMM",
    "manama": "BAH",
    "london": "LHR",
    "manchester": "MAN",
    "birmingham": "BHX",
    "paris": "CDG",
    "istanbul": "IST",
    "bangkok": "BKK",
    "kuala lumpur": "KUL",
    "singapore": "SIN",
    "hong kong": "HKG",
    "beijing": "PEK",
    "shanghai": "PVG",
    "tokyo": "NRT",
    "new york": "JFK",
    "toronto": "YYZ",
    "vancouver": "YVR"
}

# Create IATA codes set and city names list
city_names = list(city_to_iata.keys())
iata_codes = set(city_to_iata.values())


def get_current_date_context():
    """Get current date context for the LLM"""
    today = datetime.now()
    return {
        "current_date": today.strftime("%Y-%m-%d"),
        "current_day": today.strftime("%A"),
        "tomorrow": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
        "day_after_tomorrow": (today + timedelta(days=2)).strftime("%Y-%m-%d")
    }


def create_system_prompt():
    """Create a comprehensive system prompt for travel parameter extraction"""
    date_context = get_current_date_context()
    
    system_prompt = f"""You are an expert travel parameter extraction system. Extract flight booking information from user queries and return it in JSON format.

CURRENT DATE CONTEXT:
- Today: {date_context['current_date']} ({date_context['current_day']})
- Tomorrow: {date_context['tomorrow']}
- Day after tomorrow: {date_context['day_after_tomorrow']}

SUPPORTED CITIES AND IATA CODES:
{json.dumps(city_to_iata, indent=2)}

EXTRACTION RULES:

1. SOURCE & DESTINATION:
   - Extract departure city (source) and arrival city (destination)
   - Return exact city names from the supported list above
   - If IATA codes are mentioned, convert to city names
   - Handle "Now" modification queries (e.g., "Now Karachi to Dubai" means modify existing booking)
   - For single city mentions, determine if it's source or destination based on context

2. FLIGHT_TYPE:
   - "one_way": Single direction flight
   - "return": Round trip (return/back journey mentioned, date ranges, "between X and Y")
   - Be conservative - only return "return" with strong indicators like:
     * "return", "round trip", "back to", "between [date] and [date]"
     * Multiple dates mentioned
     * "go and come back", "there and back"

3. FLIGHT_CLASS:
   - "economy": Default, economy class, coach, standard
   - "business": Business class, executive, corporate
   - "first": First class, luxury, premium service
   - "premium_economy": Premium economy, comfort plus, extra legroom

4. DATES:
   - Format: "YYYY-MM-DD"
   - Handle relative dates: "today", "tomorrow", "day after tomorrow", "next Monday"
   - For return flights: extract both departure_date and return_date
   - For one_way flights: only departure_date (return_date should be null)
   - Handle date ranges and "between" patterns
   - Parse natural language dates intelligently

5. PASSENGERS:
   - adults: 18+ years (default 1 if not specified)
   - children: 2-17 years 
   - infants: 0-2 years
   - Handle phrases like "family of 4", "me and my wife", "our 3 children"
   - Age mentions override category labels
   - Ensure at least 1 adult if children/infants are present

6. SPECIAL HANDLING:
   - "Now" queries: Focus on modifications in the "Now" part
   - Negation: "not business class", "no return"
   - Context preservation: When modifying existing bookings

RESPONSE FORMAT (STRICT JSON):
{{
    "source": "city_name or null",
    "destination": "city_name or null", 
    "flight_type": "one_way or return",
    "flight_class": "economy or business or first or premium_economy",
    "departure_date": "YYYY-MM-DD or null",
    "return_date": "YYYY-MM-DD or null (only include this field for return flights)",
    "passengers": {{
        "adults": number,
        "children": number,
        "infants": number
    }},
    "total_passengers": number
}}

IMPORTANT:
- Always return valid JSON
- Use null for missing/unclear information
- Be conservative with flight_type (default to one_way unless clear return indicators)
- Default flight_class to "economy" if unclear
- Ensure dates are realistic and properly formatted
- Calculate total_passengers as sum of adults + children + infants"""

    return system_prompt


def extract_travel_info_groq(query: str) -> Dict:
    """
    Extract travel information using Groq's LLM models
    
    Args:
        query (str): User's travel query
        
    Returns:
        Dict containing extracted travel parameters
    """
    try:
        # Initialize Groq client
        client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
        
        # Create system prompt
        system_prompt = create_system_prompt()
        
        # Create user prompt
        user_prompt = f"""Extract travel parameters from this query:

"{query}"

Return the information in the exact JSON format specified in the system prompt."""

        # Call Groq API with JSON response format
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user", 
                    "content": user_prompt
                }
            ],
            model="meta-llama/llama-4-maverick-17b-128e-instruct",  # Same model as used in original
            temperature=0.1,  # Low temperature for consistent results
            max_tokens=1000,
            response_format={"type": "json_object"}  # Force JSON response
        )
        
        # Parse the response
        response_text = chat_completion.choices[0].message.content.strip()
        result = json.loads(response_text)
        
        # Validate and clean the result
        result = validate_and_clean_result(result, query)
        
        return result
        
    except Exception as e:
        print(f"❌ Error with Groq API: {e}")
        return get_fallback_result(query)


def validate_and_clean_result(result: Dict, query: str) -> Dict:
    """
    Validate and clean the LLM result to ensure consistency
    """
    cleaned_result = {}
    
    # Validate source and destination
    source = result.get('source')
    destination = result.get('destination')
    
    # Ensure cities are from our supported list or null
    if source and source.lower() in city_names:
        cleaned_result['source'] = source.lower()
    elif source and source.upper() in iata_codes:
        # Convert IATA to city name
        for city, iata in city_to_iata.items():
            if iata == source.upper():
                cleaned_result['source'] = city
                break
    else:
        cleaned_result['source'] = None
        
    if destination and destination.lower() in city_names:
        cleaned_result['destination'] = destination.lower()
    elif destination and destination.upper() in iata_codes:
        # Convert IATA to city name
        for city, iata in city_to_iata.items():
            if iata == destination.upper():
                cleaned_result['destination'] = city
                break
    else:
        cleaned_result['destination'] = None
    
    # Ensure source != destination
    if cleaned_result['source'] == cleaned_result['destination']:
        cleaned_result['destination'] = None
    
    # Validate flight_type
    flight_type = result.get('flight_type', 'one_way')
    if flight_type in ['one_way', 'return']:
        cleaned_result['flight_type'] = flight_type
    else:
        cleaned_result['flight_type'] = 'one_way'
    
    # Validate flight_class
    flight_class = result.get('flight_class', 'economy')
    if flight_class in ['economy', 'business', 'first', 'premium_economy']:
        cleaned_result['flight_class'] = flight_class
    else:
        cleaned_result['flight_class'] = 'economy'
    
    # Validate dates
    departure_date = result.get('departure_date')
    return_date = result.get('return_date')
    
    if departure_date and validate_date_format(departure_date):
        cleaned_result['departure_date'] = departure_date
    else:
        cleaned_result['departure_date'] = None
        
    # Only include return_date for return flights
    if cleaned_result['flight_type'] == 'return':
        if return_date and validate_date_format(return_date):
            cleaned_result['return_date'] = return_date
        else:
            cleaned_result['return_date'] = None
    # For one_way flights, omit return_date field entirely
    
    # Validate passengers
    passengers = result.get('passengers', {})
    adults = passengers.get('adults', 1)
    children = passengers.get('children', 0)
    infants = passengers.get('infants', 0)
    
    # Convert to int, handling None values
    try:
        adults = max(0, int(adults)) if adults is not None else 1
    except (ValueError, TypeError):
        adults = 1
        
    try:
        children = max(0, int(children)) if children is not None else 0
    except (ValueError, TypeError):
        children = 0
        
    try:
        infants = max(0, int(infants)) if infants is not None else 0
    except (ValueError, TypeError):
        infants = 0
    
    # Business logic: ensure at least 1 adult if children/infants present
    if adults == 0 and (children > 0 or infants > 0):
        adults = 1
    
    # Ensure at least 1 passenger total
    if adults == 0 and children == 0 and infants == 0:
        adults = 1
    
    cleaned_result['passengers'] = {
        'adults': adults,
        'children': children,
        'infants': infants
    }
    
    cleaned_result['total_passengers'] = adults + children + infants
    
    return cleaned_result


def validate_date_format(date_str: str) -> bool:
    """Validate date format YYYY-MM-DD"""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def get_fallback_result(query: str) -> Dict:
    """
    Fallback result when API fails
    """
    return {
        'source': None,
        'destination': None,
        'flight_type': 'one_way',
        'flight_class': 'economy',
        'departure_date': None,
        'passengers': {
            'adults': 1,
            'children': 0,
            'infants': 0
        },
        'total_passengers': 1
    }


def extract_travel_info(query: str) -> Dict:
    """
    Main function to extract travel information - maintains compatibility with original
    
    Args:
        query (str): User's travel query
        
    Returns:
        Dict containing extracted travel parameters
    """
    result =  extract_travel_info_groq(query)
    print(f"Extracted parameters: {result}")
    return result

# Test function for debugging
def test_extraction(test_queries=None):
    """Test the extraction with sample queries"""
    if test_queries is None:
        test_queries = [
            "I want to fly from Lahore to Karachi tomorrow",
            "Book a return flight from ISB to Dubai on 10th August, returning 15th August",
            "Family of 4 traveling from London to Islamabad next Monday, business class",
            "One way ticket from Karachi to Doha today with my wife and 2 children",
            "Now change to business class",
            "Now Karachi to Dubai instead",
            "Round trip between Lahore and Dubai from tomorrow to next week"
        ]
    
    print("🚀 Testing GROQ-based Travel Parameter Extraction")
    print("=" * 60)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n📝 Test {i}: {query}")
        try:
            result = extract_travel_info(query)
            print(f"✅ Result:")
            for key, value in result.items():
                print(f"   {key}: {value}")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n" + "=" * 60)


# Enhanced command-line interface
if __name__ == "__main__":
    print("🚀 GROQ-based Travel Parameter Extraction System")
    print("💡 Enhanced with LLM intelligence for better coverage")
    print("-" * 50)
    
    # Check if GROQ_API_KEY is available
    if not os.environ.get('GROQ_API_KEY'):
        print("❌ Warning: GROQ_API_KEY not found in environment variables")
        print("💡 Please set your GROQ API key in your .env file")
        print()
    
    while True:
        print("\nOptions:")
        print("1. Enter a travel query")
        print("2. Run test cases")
        print("3. Exit")
        
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == "1":
            query = input("\n📝 Enter your travel query: ").strip()
            if not query:
                continue
            try:
                result = extract_travel_info(query)
                print("\n🔍 Extracted Information:")
                print(json.dumps(result, indent=2))
            except Exception as e:
                print(f"❌ Error processing query: {e}")
                
        elif choice == "2":
            test_extraction()
            
        elif choice == "3":
            print("✈️ Safe travels! Goodbye!")
            break
            
        else:
            print("❌ Invalid option. Please select 1, 2, or 3.")
