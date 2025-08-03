import spacy
from rapidfuzz import process
from datetime import datetime, timedelta
import parsedatetime
from autocorrect import Speller
import re
import json
from typing import Dict
import os
from dotenv import load_dotenv
from groq import Groq


load_dotenv()  # Load environment variables from .env file
# Load spaCy English model
nlp = spacy.load("en_core_web_sm")
spell = Speller(lang='en')

# City to IATA mapping
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


city_names = list(city_to_iata.keys())
# Create reverse mapping for IATA codes
iata_codes = set(city_to_iata.values())

def correct_spelling(text):
    return spell(text)

def detect_negation_in_modification(now_part):
    """
    Detect negation patterns in the modification part (after "now").
    
    Args:
        now_part (str): The text after "now" in a modification query
        
    Returns:
        tuple: (has_negation, cleaned_text) where:
               - has_negation: Boolean indicating if negation was detected
               - cleaned_text: The text with negation indicators removed
    """
    now_part_lower = now_part.lower()
    
    # Negation patterns to detect
    negation_patterns = [
        r'\bno\b',           # "no"
        r'\bnot\b',          # "not"
        r'\bdont?\b',        # "don't", "dont"
        r'\bdoesn\'t\b',     # "doesn't"
        r'\bwont?\b',        # "won't", "wont"
        r'\bcan\'t\b',       # "can't"
        r'\bisn\'t\b',       # "isn't"
        r'\baren\'t\b',      # "aren't"
        r'\bwasn\'t\b',      # "wasn't"
        r'\bweren\'t\b',     # "weren't"
        r'\bactually\b',     # "actually" (correction indicator)
        r'\binstead\b',      # "instead"
        r'\brather\b',       # "rather"
        r'\bchange\s+(?:it\s+)?to\b',  # "change to", "change it to"
        r'\bcorrect\s+(?:it\s+)?to\b', # "correct to", "correct it to"
        r'\bmodify\s+(?:it\s+)?to\b',  # "modify to", "modify it to"
    ]
    
    has_negation = False
    cleaned_text = now_part_lower
    
    # Check for negation patterns
    for pattern in negation_patterns:
        if re.search(pattern, now_part_lower):
            has_negation = True
            # Remove the negation word/phrase but keep the rest
            cleaned_text = re.sub(pattern, '', cleaned_text).strip()
            # Clean up extra spaces
            cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    # Handle specific negation structures with better preservation
    
    # Pattern: "no, from X to Y" or "no from X to Y"
    no_from_pattern = r'\bno\s*,?\s*from\b'
    if re.search(no_from_pattern, now_part_lower):
        has_negation = True
        cleaned_text = re.sub(no_from_pattern, 'from', cleaned_text).strip()
    
    # Pattern: "not X, Y" -> becomes just "Y"  
    not_comma_pattern = r'\bnot\s+([^,]+),\s*(.+)'
    not_match = re.search(not_comma_pattern, now_part_lower)
    if not_match:
        has_negation = True
        cleaned_text = not_match.group(2).strip()
    
    # Pattern: "no X, from Y" -> becomes "from Y" 
    no_x_from_pattern = r'\bno\s+([^,]+),\s*from\s+(.+)'
    no_from_match = re.search(no_x_from_pattern, now_part_lower)
    if no_from_match:
        has_negation = True
        cleaned_text = f"from {no_from_match.group(2)}".strip()
        
    # Pattern: "actually not X, going to Y" -> "going to Y"
    actually_not_pattern = r'\bactually\s+not\s+([^,]+),\s*(.+)'
    actually_match = re.search(actually_not_pattern, now_part_lower)
    if actually_match:
        has_negation = True
        cleaned_text = actually_match.group(2).strip()
    
    # Pattern: "no, X class from Y to Z today" -> "X class from Y to Z today"
    no_comma_complex = r'\bno,\s*(.+)'
    no_comma_match = re.search(no_comma_complex, now_part_lower)
    if no_comma_match:
        has_negation = True
        cleaned_text = no_comma_match.group(1).strip()
    
    # Handle "don't want X, prefer Y" pattern
    dont_want_pattern = r'\bdon\'t\s+want\s+([^,]+),\s*prefer\s+(.+)'
    dont_want_match = re.search(dont_want_pattern, now_part_lower)
    if dont_want_match:
        has_negation = True
        # Extract the preferred option
        preferred = dont_want_match.group(2).strip()
        cleaned_text = preferred
    
    # Handle "from X not from Y" pattern - keep only "from X"
    from_not_from_pattern = r'\bfrom\s+([^,\s]+(?:\s+[^,\s]+)*)\s+not\s+from\s+([^,\s]+(?:\s+[^,\s]+)*)'
    from_not_from_match = re.search(from_not_from_pattern, now_part_lower)
    if from_not_from_match:
        has_negation = True
        # Keep only the first "from X" part
        preferred_source = from_not_from_match.group(1).strip()
        cleaned_text = f"from {preferred_source}"
    
    return has_negation, cleaned_text

def extract_cities_multiword(text):
    """Extract multi-word cities first, then single word cities, and IATA codes"""
    text_lower = text.lower()
    found_cities = []
    
    # Special handling for "Now" modification queries
    is_modification_query = " now " in text_lower or text_lower.strip().startswith("now ")
    
    if is_modification_query:
        # Focus only on the part after "now" for city extraction
        if " now " in text_lower:
            now_start = text_lower.find(" now ") + 5  # +5 to skip " now "
        else:
            now_start = 4  # Skip "now "
            
        now_part = text_lower[now_start:].strip()
        
        # NEGATION HANDLING: Check for negation in the modification part
        has_negation, cleaned_now_part = detect_negation_in_modification(now_part)
        
        if has_negation:
            # Use cleaned text for extraction
            relevant_text = cleaned_now_part
        else:
            relevant_text = now_part
    else:
        relevant_text = text_lower
    
    # First, check for IATA codes (3-letter uppercase codes)
    iata_pattern = r'\b[A-Z]{3}\b'
    iata_matches = re.finditer(iata_pattern, text.upper())
    
    for match in iata_matches:
        iata_code = match.group()
        if iata_code in iata_codes:
            start_pos = match.start()
            # For "Now" queries, only include IATA codes from the relevant part
            if is_modification_query:
                if " now " in text_lower:
                    now_start = text_lower.find(" now ") + 5
                else:
                    now_start = 4
                if start_pos >= now_start:
                    words_before = len(text[:start_pos].split())
                    found_cities.append((iata_code, words_before, start_pos))
            else:
                words_before = len(text[:start_pos].split())
                found_cities.append((iata_code, words_before, start_pos))
    
    # Also check for city names (don't return early, combine with IATA codes)
    # Sort cities by length (longest first) to match multi-word cities first
    sorted_cities = sorted(city_names, key=len, reverse=True)
    
    for city in sorted_cities:
        if city in relevant_text:
            # Find the position of the city in the relevant text
            start_pos_in_relevant = relevant_text.find(city)
            if start_pos_in_relevant != -1:
                # Check if it's a whole word match (not part of another word)
                start_char = start_pos_in_relevant == 0 or not relevant_text[start_pos_in_relevant - 1].isalnum()
                end_char = (start_pos_in_relevant + len(city) == len(relevant_text) or 
                           not relevant_text[start_pos_in_relevant + len(city)].isalnum())
                
                if start_char and end_char:
                    iata = city_to_iata[city]
                    # Calculate position in original text
                    if is_modification_query:
                        # Adjust position to account for text before "now"
                        if " now " in text_lower:
                            actual_start_pos = text_lower.find(" now ") + 5 + start_pos_in_relevant
                        else:
                            actual_start_pos = 4 + start_pos_in_relevant  # Skip "now "
                    else:
                        actual_start_pos = start_pos_in_relevant
                    
                    # Calculate approximate token position
                    words_before = len(text_lower[:actual_start_pos].split())
                    found_cities.append((iata, words_before, actual_start_pos))
                    # Remove the matched city from relevant text to avoid overlapping matches
                    relevant_text = relevant_text.replace(city, " " * len(city), 1)
    
    return found_cities

def extract_cities(query):
    """
    Extract source and destination cities from query.
    This is the simplified version used by _extract_basic_travel_info.
    """
    
    # Check for negation in modification queries
    if "now" in query.lower():
        has_negation, cleaned_text = detect_negation_in_modification(query)
        if has_negation:
            found_cities = extract_cities_multiword(cleaned_text)
        else:
            found_cities = extract_cities_multiword(query)
    else:
        # Normal extraction
        found_cities = extract_cities_multiword(query)
        
    # Convert found_cities (list of tuples) to source, destination
    if not found_cities:
        return None, None
    
    # Sort cities by their position in the text (third element in tuple is character position)
    found_cities_sorted = sorted(found_cities, key=lambda x: x[2])  # Sort by character position
    
    if len(found_cities_sorted) == 1:
        # Single city - could be source or destination based on context
        city_iata = found_cities_sorted[0][0]
        query_lower = query.lower()
        if any(word in query_lower for word in ["to", "going to", "destination"]):
            return None, city_iata  # It's a destination
        else:
            return city_iata, None  # It's a source
    else:
        # Multiple cities - need to determine source and destination based on context
        query_lower = query.lower()
        
        # Look for directional indicators
        from_indicators = ["from", "leaving", "departing", "starting"]
        to_indicators = ["to", "going to", "towards", "arriving", "destination"]
        
        source = None
        destination = None
        
        # Check for explicit "from X to Y" pattern
        from_to_pattern = r'from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+)'
        from_to_match = re.search(from_to_pattern, query_lower)
        if from_to_match:
            from_city_text = from_to_match.group(1).strip()
            to_city_text = from_to_match.group(2).strip()
            
            # Find which IATA codes correspond to these text matches
            for city_iata, _, _ in found_cities_sorted:
                city_name = [k for k, v in city_to_iata.items() if v == city_iata][0]
                if city_name in from_city_text:
                    source = city_iata
                elif city_name in to_city_text:
                    destination = city_iata
        
        # Check for "go to X from Y" pattern
        if not source or not destination:
            to_from_pattern = r'(?:go\s+)?to\s+([a-zA-Z\s]+?)\s+from\s+([a-zA-Z\s]+)'
            to_from_match = re.search(to_from_pattern, query_lower)
            if to_from_match:
                to_city_text = to_from_match.group(1).strip()
                from_city_text = to_from_match.group(2).strip()
                
                # Find which IATA codes correspond to these text matches
                for city_iata, _, _ in found_cities_sorted:
                    city_name = [k for k, v in city_to_iata.items() if v == city_iata][0]
                    if city_name in from_city_text:
                        source = city_iata
                    elif city_name in to_city_text:
                        destination = city_iata
        
        # If no explicit patterns found, use word proximity to indicators
        if not source or not destination:
            for city_iata, token_idx, char_idx in found_cities_sorted:
                # Check words around this city
                words = query_lower.split()
                city_word_idx = token_idx
                
                # Look for "from" before this city
                if city_word_idx > 0 and any(indicator in words[city_word_idx-1] for indicator in from_indicators):
                    source = city_iata
                # Look for "to" before this city
                elif city_word_idx > 0 and any(indicator in words[city_word_idx-1] for indicator in to_indicators):
                    destination = city_iata
                # Look for "to" after previous words
                elif city_word_idx > 1 and any(indicator in words[city_word_idx-2:city_word_idx] for indicator in to_indicators):
                    destination = city_iata
        
        # Fallback: if still not determined, use position but be smarter about it
        if not source and not destination:
            # Default to first city as source, second as destination
            source = found_cities_sorted[0][0]
            destination = found_cities_sorted[1][0]
        elif not source:
            # Find the other city
            for city_iata, _, _ in found_cities_sorted:
                if city_iata != destination:
                    source = city_iata
                    break
        elif not destination:
            # Find the other city
            for city_iata, _, _ in found_cities_sorted:
                if city_iata != source:
                    destination = city_iata
                    break
        
        # Ensure they're different
        if source == destination and len(found_cities_sorted) > 2:
            destination = found_cities_sorted[2][0]
        elif source == destination:
            destination = None
        
        return source, destination

def extract_flight_type(query):
    """
    Conservative flight type extraction - only detects return when there are strong indicators.
    Returns 'return' or 'one_way'
    """
    query_lower = query.lower()
    
    # Strong explicit return flight indicators
    strong_return_keywords = [
        "return", "round trip", "round-trip", "roundtrip", "two way", "two-way",
        "return ticket", "return flight", "both ways"
    ]
    
    # Check for explicit return keywords first
    for keyword in strong_return_keywords:
        if keyword in query_lower:
            return "return"
    
    # Very specific return patterns - only strong indicators
    return_patterns = [
        # "back to [city]" patterns - must have "back"
        r'(?:and\s+)?(?:then\s+)?back\s+to\s+\w+',
        r'(?:and\s+)?(?:then\s+)?(?:come\s+)?back\s+(?:to\s+)?\w+',
        
        # "between [date] and [date]" patterns - strong date range indicator
        r'between\s+.?\s+and\s+.?(?:\d|today|tomorrow)',
        
        # Multiple cities with explicit return language
        r'(?:from\s+)?\w+\s+to\s+\w+\s+and\s+(?:then\s+)?(?:back\s+to|return\s+to)\s+\w+',
        r'(?:from\s+)?\w+\s+to\s+\w+.*?(?:and\s+)?(?:then\s+)?(?:back|return)',
        
        # Strong temporal return indicators
        r'(?:go|travel|fly)\s+.*?(?:and\s+)?(?:then\s+)?(?:come\s+)?back',
        r'(?:trip|journey)\s+(?:from\s+)?\w+\s+to\s+\w+\s+and\s+back',
    ]
    
    for pattern in return_patterns:
        if re.search(pattern, query_lower):
            return "return"
    
    # Check for "between" with locations - strong return indicator
    if "between" in query_lower:
        # Look for "between [city] and [city]" or "between [date] and [date]"
        between_pattern = r'between\s+\w+.*?and\s+\w+'
        if re.search(between_pattern, query_lower):
            return "return"
    
    # Check for specific temporal return indicators
    strong_temporal_indicators = [
        "and back", "then back", "return on", "coming back on",
        "back on", "go and come back", "there and back"
    ]
    
    for indicator in strong_temporal_indicators:
        if indicator in query_lower:
            return "return"
    
    # Check for date ranges that suggest return trips
    date_range_patterns = [
        # Clear date ranges: "from 10th to 15th", "10th and 15th", "10th until 15th"
        r'(?:from\s+)?\d+(?:st|nd|rd|th)?\s+.*?(?:to|and|until)\s+\d+(?:st|nd|rd|th)',
        r'(?:on\s+)?\d+(?:st|nd|rd|th)?\s+.*?(?:and\s+back\s+on|and\s+return\s+on)\s+\d+(?:st|nd|rd|th)',
    ]
    
    for pattern in date_range_patterns:
        if re.search(pattern, query_lower):
            return "return"
    
    # Advanced analysis - only if we have strong indicators
    try:
        doc = nlp(query_lower)
        
        # Check for city repetition (same city mentioned multiple times)
        known_cities_mentioned = []
        for city in city_names:
            if city in query_lower:
                # Count how many times this city appears
                count = query_lower.count(city)
                if count > 1:
                    return "return"
                known_cities_mentioned.append(city)
        
        # Only check for multiple unique cities if there are strong connecting words
        if len(known_cities_mentioned) >= 2:
            # Must have explicit connecting words that suggest return journey
            strong_connectors = ["and then to", "and back to", "then to", "then back"]
            for connector in strong_connectors:
                if connector in query_lower:
                    return "return"
        
    except Exception:
        pass
    
    # Final very specific return checks
    final_return_checks = [
        r'\bgo\b.*\bback\b',      # "go ... back"
        r'\bthere\b.*\bback\b',   # "there ... back" 
        r'\bfly\b.*\breturn\b',   # "fly ... return"
    ]
    
    for check in final_return_checks:
        if re.search(check, query_lower):
            return "return"
    
    # Default to one_way - be conservative
    return "one_way"

def extract_flight_class(query):
    """
    Extract flight class from query. Returns 'economy' by default.
    Simplified version for use with _extract_basic_travel_info.
    """
    # Check for negation in modification queries
    if "now" in query.lower():
        has_negation, cleaned_text = detect_negation_in_modification(query)
        if has_negation:
            query = cleaned_text
    
    query_lower = query.lower()
    
    # Flight class mappings - most specific first
    class_mappings = {
        # First Class variations
        "first": ["first class", "first-class", "firstclass", "1st class", "first", "f class"],
        
        # Business Class variations  
        "business": [
            "business class", "business-class", "businessclass", "biz class", "business", 
            "c class", "club class", "executive class", "executive", "j class"
        ],
        
        # Premium Economy variations
        "premium_economy": [
            "premium economy", "premium-economy", "premiumeconomy", "premium eco",
            "premium", "comfort", "comfort class", "premium class", "y+ class"
        ],
        
        # Economy variations
        "economy": [
            "economy class", "economy-class", "economyclass", "eco class", "economy", 
            "coach", "coach class", "standard", "basic", "y class", "main cabin"
        ]
    }
    
    # Check each class mapping for matches
    for flight_class, keywords in class_mappings.items():
        for keyword in keywords:
            if keyword in query_lower:
                return flight_class
    
    # Default to economy if no class found
    return "economy"

def extract_passenger_count(query: str) -> Dict[str, int]:
    """
    Extract passenger count using Groq's fast LLM models
    
    Args:
        query (str): User query about flight booking
        
    Returns:
        Dict containing passenger counts
    """
    
    # Initialize Groq client
    try:
        client = Groq(
            api_key=os.environ.get('GROQ_API_KEY')
        )
    except Exception as e:
        # Fallback to default values if API fails
        print(f"Error initializing Groq client: {e}")
        return {
            'adults': 1,
            'children': 0,
            'infants': 0
        }
    
    # Create the prompt for passenger extraction
    prompt = f"""
Extract passenger counts from this travel query. Return ONLY a JSON object, no explanations.

Query: "{query}"

RULES:
- Adults: 18+ years (speaker, wife, husband, parents, friends, child, etc)
- Children: 2-17 years (kids, son, daughter, child, etc)  
- Infants: 0-2 years (baby, infant, newborn, etc)
- "I with wife" = 2 adults total
- "our 3 children" = 3 children
- Age always overrides labels. "2 20 year old children" = 2 adults (not children)
- At least 1 adult if children/infants present

EXAMPLES:
Query: "I want to travel with my wife and our 3 children"
{{"adults": 2, "children": 3, "infants": 0}}

Query: "family of 4"  
{{"adults": 2, "children": 2, "infants": 0}}

Query: "2 adults and 1 baby"
{{"adults": 2, "children": 0, "infants": 1}}

Now extract from: "{query}"

Return only JSON:
"""

    try:
        # Use Groq's fastest model (llama3-8b-8192 or mixtral-8x7b-32768)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="meta-llama/llama-4-maverick-17b-128e-instruct",  # Fast and efficient model
            temperature=0.1,  # Low temperature for consistent results
            max_tokens=150,   # Limit response length
            top_p=0.9
        )
        
        response_text = chat_completion.choices[0].message.content.strip()
        
        # Extract and clean JSON
        passenger_data = extract_and_clean_json(response_text)
        
        # Validate and sanitize the response
        adults = max(0, int(passenger_data.get('adults', 0)))
        children = max(0, int(passenger_data.get('children', 0)))
        infants = max(0, int(passenger_data.get('infants', 0)))
        
        # Business logic validation
        adults, children, infants = validate_passenger_counts(adults, children, infants)
        
        return {
            'adults': adults,
            'children': children,
            'infants': infants
        }

    except Exception as e:
        print(f"Error with Groq API: {e}")
        return fallback_extraction(query)


def extract_and_clean_json(response_text: str) -> dict:
    """
    Extract and clean JSON object from LLM response, handling extra text and malformed JSON
    """
    try:
        # Step 1: Remove markdown code blocks
        clean_text = re.sub(r'```(?:json)?\s*|\s*```', '', response_text, flags=re.IGNORECASE).strip()
        
        # Step 2: Extract ONLY the JSON object (ignore explanation text)
        # Look for the first complete JSON object
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_match = re.search(json_pattern, clean_text, re.DOTALL)
        
        if not json_match:
            # Fallback: try to find any JSON-like structure
            json_match = re.search(r'\{.*?\}', clean_text, re.DOTALL)
        
        if not json_match:
            raise ValueError("No JSON object found in response")
        
        json_str = json_match.group().strip()
        
        # Step 3: Clean and fix common JSON issues
        json_str = json_str.replace("'", '"')  # Single to double quotes
        
        # Fix unquoted keys (but be careful not to quote already quoted keys)
        json_str = re.sub(r'(?<!")(\b\w+)(?=\s*:)', r'"\1"', json_str)
        
        # Remove trailing commas
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        
        # Remove any trailing text after the closing brace
        brace_count = 0
        end_index = 0
        for i, char in enumerate(json_str):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_index = i + 1
                    break
        
        if end_index > 0:
            json_str = json_str[:end_index]
        
        # Step 4: Parse the cleaned JSON
        return json.loads(json_str)
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing error: {e}")
        print(f"🔍 Attempted to parse: {json_str}")
        print(f"🔍 Full response: {response_text}")
        raise
    except Exception as e:
        print(f"❌ JSON extraction failed: {e}")
        print(f"🔍 Raw response: {response_text}")
        raise


def validate_passenger_counts(adults: int, children: int, infants: int) -> tuple:
    """Apply business logic validation to passenger counts"""
    
    # Ensure at least 1 adult if children/infants present but no adults
    if adults == 0 and (children > 0 or infants > 0):
        adults = 1
        print("⚠️  Added 1 adult to accompany children/infants")
    
    # Ensure at least 1 passenger total
    if adults == 0 and children == 0 and infants == 0:
        adults = 1
        print("⚠️  Defaulted to 1 adult (no passengers specified)")
    
    return adults, children, infants


def fallback_extraction(query: str) -> Dict[str, int]:
    """
    Enhanced fallback extraction using regex patterns
    """
    query_lower = query.lower()
    adults = 0
    children = 0
    infants = 0
    
    print("🔄 Using fallback extraction...")
    
    # Step 1: Handle explicit numbers with passenger types
    adult_patterns = [
        r'(\d+)\s+adults?',
        r'(\d+)\s+(?:people|persons?|passengers?)',
    ]
    
    child_patterns = [
        r'(\d+)\s+(?:children?|kids?|child)',
        r'our\s+(\d+)\s+children',
    ]
    
    infant_patterns = [
        r'(\d+)\s+(?:infants?|babies|baby|newborns?)',
        r'(\d+)\s+(?:month|months?)\s+(?:old|baby)',
    ]
    
    # Extract explicit counts
    for pattern in adult_patterns:
        match = re.search(pattern, query_lower)
        if match:
            adults = max(adults, int(match.group(1)))
    
    for pattern in child_patterns:
        match = re.search(pattern, query_lower)
        if match:
            children = max(children, int(match.group(1)))
    
    for pattern in infant_patterns:
        match = re.search(pattern, query_lower)
        if match:
            infants = max(infants, int(match.group(1)))
    
    # Step 2: Handle relationship-based counts
    if re.search(r'with\s+(?:my\s+)?(?:wife|husband|partner)', query_lower):
        adults = max(adults, 2)  # Speaker + spouse
    
    # Step 3: Handle family counts
    family_match = re.search(r'family of (\d+)', query_lower)
    if family_match:
        total = int(family_match.group(1))
        if adults == 0 and children == 0:  # If no specific counts found
            adults = min(2, total)  # Assume max 2 adults
            children = max(0, total - adults)
    
    # Step 4: Handle age-specific mentions
    age_matches = re.findall(r'(\d+)?\s*(\d+)\s*(?:yr|year)s?\s+old', query_lower)
    for count_str, age_str in age_matches:
        try:
            count = int(count_str) if count_str else 1
            age = int(age_str)
            
            if 0 <= age <= 2:
                infants += count
            elif 3 <= age <= 17:
                children += count
            else:
                adults += count
        except ValueError:
            continue
    
    # Step 5: Handle month-based age for infants
    month_matches = re.findall(r'(?:one|1|\d+)\s+(?:\d+\s+)?months?\s+(?:old|baby)', query_lower)
    if month_matches:
        infants += len(month_matches)
    
    # Step 6: Handle special phrases
    if 'few people' in query_lower:
        adults = max(adults, 3)
    elif 'several people' in query_lower:
        adults = max(adults, 4)
    
    # Step 7: Apply validation
    adults, children, infants = validate_passenger_counts(adults, children, infants)
    
    return {
        'adults': adults,
        'children': children,
        'infants': infants
    }

def extract_dates(text, flight_type=None):
    """
    FIXED: Date extraction function that properly handles age mentions, Now modifications, and negation
    """
    original_text = text.lower()
    original_text = correct_spelling(original_text)
    today = datetime.now()
    
    # Special handling for "Now" modification queries - extract dates from the modification part
    is_modification_query = " now " in original_text or original_text.strip().startswith("now ")
    
    if is_modification_query:
        
        # Find the "Now" part and focus date extraction on it
        if " now " in original_text:
            now_start = original_text.find(" now ") + 5  # +5 to skip " now "
        else:
            now_start = 4  # Skip "now "
            
        now_part = original_text[now_start:].strip()
        
        # NEGATION HANDLING: Check for negation in the modification part
        has_negation, cleaned_now_part = detect_negation_in_modification(now_part)
        
        if has_negation:
            # Use cleaned text for extraction
            text_for_parsing = cleaned_now_part
        else:
            # Check if the "Now" part contains any date information
            # Look for common date indicators
            date_indicators = [
                'today', 'tomorrow', 'day after tomorrow', 'next', 'this', 
                'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                'january', 'february', 'march', 'april', 'may', 'june',
                'july', 'august', 'september', 'october', 'november', 'december',
                'on ', 'by ', 'at ', r'\d+', 'st', 'nd', 'rd', 'th'
            ]
            
            has_date_info = any(indicator in now_part for indicator in date_indicators[:12]) or \
                           any(re.search(pattern, now_part) for pattern in [r'\d+', r'\b(on|by|at)\b'])
            
            if has_date_info:
                # Use the "Now" part for date extraction
                text_for_parsing = now_part
            else:
                # No date info in "Now" part, use original text to preserve existing dates
                text_for_parsing = original_text
    else:
        # Use full text for normal queries
        text_for_parsing = original_text

    # FIXED: Remove age mentions before parsing dates to prevent confusion
    # Remove patterns like "10 year old", "1 year old", etc.
    text_cleaned = re.sub(r'\b\d+\s+years?\s+old\b', '', text_for_parsing)
    text_cleaned = re.sub(r'\b\d+\s+year\s+old\b', '', text_cleaned)
    
    # ADDED: Remove month age mentions like "15 month", "18 months old", etc.
    text_cleaned = re.sub(r'\b\d+\s+months?\s+(?:old)?\b', '', text_cleaned)
    text_cleaned = re.sub(r'\b\d+\s+month\s+(?:old)?\b', '', text_cleaned)
    
    # Special date mapping
    special_date_map = {
        "day after tomorrow": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
        "tomorrow": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
        "today": today.strftime("%Y-%m-%d"),
    }

    # Fix common date format issues
    text_fixed = re.sub(r'(\d+)(st|nd|rd|th)\s+of\s+', r'\1\2 ', text_cleaned)
    normalized_text = text_fixed.strip().lower()
    dates = []

    # Auto-detect flight type if not provided - use original text for flight type detection
    if flight_type is None:
        flight_type = extract_flight_type(text)  # Use original text, not the modification part

    # ---- RETURN FLIGHT HANDLING ---- #
    if flight_type == "return":
        # SPECIAL HANDLING: For "Now" modification queries, check if it's specifically for return date
        if is_modification_query and (has_date_info if not has_negation else True):
            # Check if the modification is specifically about return date
            return_change_patterns = [
                r'change\s+return\s+date\s+to\s+(.+)',
                r'return\s+date\s+to\s+(.+)',
                r'return\s+on\s+(.+)',
                r'back\s+on\s+(.+)',
                r'come\s+back\s+on\s+(.+)',
                r'returning\s+on\s+(.+)',
                r'return\s+(.+)'
            ]
            
            departure_change_patterns = [
                r'change\s+departure\s+date\s+to\s+(.+)',
                r'departure\s+date\s+to\s+(.+)',
                r'depart\s+on\s+(.+)',
                r'leave\s+on\s+(.+)',
                r'departing\s+on\s+(.+)',
                r'go\s+on\s+(.+)'
            ]
            
            # Use the appropriate text for pattern matching
            pattern_text = text_for_parsing if not has_negation else cleaned_now_part
            
            # Check for return date change
            for pattern in return_change_patterns:
                match = re.search(pattern, pattern_text)
                if match:
                    date_str = re.sub(r'\b(of|the)\b', '', match.group(1).strip().lower())
                    if date_str in special_date_map:
                        return None, special_date_map[date_str]  # departure=None, return=extracted_date
                    else:
                        try:
                            cal = parsedatetime.Calendar()
                            time_struct, parse_status = cal.parse(date_str)
                            if parse_status >= 1:
                                parsed_date = datetime(*time_struct[:6])
                                if parsed_date.year <= today.year + 2:
                                    return None, parsed_date.strftime("%Y-%m-%d")  # departure=None, return=extracted_date
                        except Exception as e:
                            print(f"❌ Error parsing return date '{date_str}': {e}")
                            pass
            
            # Check for departure date change
            for pattern in departure_change_patterns:
                match = re.search(pattern, pattern_text)
                if match:
                    date_str = re.sub(r'\b(of|the)\b', '', match.group(1).strip().lower())
                    if date_str in special_date_map:
                        return special_date_map[date_str], None  # departure=extracted_date, return=None
                    else:
                        try:
                            cal = parsedatetime.Calendar()
                            time_struct, parse_status = cal.parse(date_str)
                            if parse_status >= 1:
                                parsed_date = datetime(*time_struct[:6])
                                if parsed_date.year <= today.year + 2:
                                    return parsed_date.strftime("%Y-%m-%d"), None  # departure=extracted_date, return=None
                        except Exception as e:
                            print(f"❌ Error parsing departure date '{date_str}': {e}")
                            pass
        
        # Strategy 1: Between X and Y
        between_pattern = r'between\s+([^0-9]+?)\s+and\s+([^0-9]+?)(?:\s|$|,|\.)'
        between_matches = re.findall(between_pattern, normalized_text, re.IGNORECASE)

        if between_matches:
            for date1_text, date2_text in between_matches:
                for label, date_str in zip(['departure', 'return'], [date1_text, date2_text]):
                    date_str = re.sub(r'\b(of|the)\b', '', date_str.strip().lower())
                    if date_str in special_date_map:
                        dates.append((label, special_date_map[date_str]))
                    else:
                        try:
                            cal = parsedatetime.Calendar()
                            time_struct, parse_status = cal.parse(date_str)
                            if parse_status >= 1:
                                dates.append((label, datetime(*time_struct[:6]).strftime("%Y-%m-%d")))
                        except:
                            pass
            if len(dates) >= 2:
                return (
                    next((d for l, d in dates if l == 'departure'), None),
                    next((d for l, d in dates if l == 'return'), None)
                )

        # Strategy 2: Date pair patterns (excluding age patterns)
        date_pair_patterns = [
            r'\b(today|tomorrow|day after tomorrow)\b.*?\b(?:and\s+(?:then\s+)?|then\s+)\b.*?\b(today|tomorrow|day after tomorrow)\b',
            r'\bon\s+([^,]+?)\s+and\s+(?:then\s+)?(?:on\s+)?([^,]+?)(?:\s|$|,)',
            r'\b(\d+(?:st|nd|rd|th)?(?:\s+\w+)?)\s+(?:and\s+(?:then\s+)?|then\s+|to\s+)(?:on\s+)?(\d+(?:st|nd|rd|th)?(?:\s+\w+)?)(?:\s|$|,)',
        ]

        for pattern in date_pair_patterns:
            matches = re.findall(pattern, normalized_text)
            for match in matches:
                if len(match) == 2:
                    # Skip if this looks like an age pattern
                    if any(re.search(r'\d+.*?(year|old|month)', m) for m in match):
                        continue
                        
                    for label, date_str in zip(['departure', 'return'], match):
                        date_str = date_str.strip().lower()
                        if date_str in special_date_map:
                            dates.append((label, special_date_map[date_str]))
                        else:
                            try:
                                cal = parsedatetime.Calendar()
                                time_struct, parse_status = cal.parse(date_str)
                                if parse_status >= 1:
                                    parsed_date = datetime(*time_struct[:6])
                                    # FIXED: Ensure parsed date is not in the far future due to age confusion
                                    if parsed_date.year <= today.year + 2:
                                        dates.append((label, parsed_date.strftime("%Y-%m-%d")))
                            except:
                                pass
                if len(dates) >= 2:
                    return (
                        next((d for l, d in dates if l == 'departure'), None),
                        next((d for l, d in dates if l == 'return'), None)
                    )

        # Strategy 3 & 4: Return and Departure Indicators
        indicator_patterns = [
            ("return", [
                r'(?:come\s+back|return|back).*?(?:on\s+|must\s+on\s+|by\s+)([^,\.]+)',
                r'(?:must\s+on|need\s+to\s+(?:come\s+)?back.*?on)\s+([^,\.]+)',
                r'(?:return.*?on|back.*?on)\s+([^,\.]+)'
            ]),
            ("departure", [
                r'(?:depart|leave|going|travel).*?(?:on\s+)([^,\.]+)',
                r'(?:on\s+)([^,\.]+).*?(?:going|travel|depart|leave)'
            ])
        ]

        for label, patterns in indicator_patterns:
            for pattern in patterns:
                matches = re.findall(pattern, normalized_text)
                for match in matches:
                    # Skip age-related matches
                    if re.search(r'\d+.*?(year|old|month)', match):
                        continue
                        
                    date_str = re.sub(r'\b(of|the)\b', '', match.strip().lower())
                    if date_str in special_date_map:
                        dates.append((label, special_date_map[date_str]))
                    else:
                        try:
                            cal = parsedatetime.Calendar()
                            time_struct, parse_status = cal.parse(date_str)
                            if parse_status >= 1:
                                parsed_date = datetime(*time_struct[:6])
                                # FIXED: Ensure parsed date is reasonable
                                if parsed_date.year <= today.year + 2:
                                    dates.append((label, parsed_date.strftime("%Y-%m-%d")))
                        except:
                            pass

        # Strategy 5: Generic fallback special date match
        if not dates:
            sorted_specials = sorted(special_date_map.keys(), key=len, reverse=True)
            for word in sorted_specials:
                if word in normalized_text:
                    context_match = any(phrase in normalized_text for phrase in [
                        f"come back {word}", f"return {word}", f"back {word}", f"must {word}"
                    ])
                    label = 'return' if context_match else 'departure'
                    dates.append((label, special_date_map[word]))

        # Final return for return flight
        departure = next((d for l, d in dates if l == 'departure'), None)
        return_date = next((d for l, d in dates if l == 'return'), None)
        if departure or return_date:
            return departure, return_date
        else:
            # FIXED: Fallback parsing with age filtering
            try:
                cal = parsedatetime.Calendar()
                time_struct, parse_status = cal.parse(normalized_text)
                if parse_status >= 1:
                    departure_date = datetime(*time_struct[:6])
                    # FIXED: Check if the date is reasonable (not far future due to age)
                    if departure_date.year <= today.year + 2:
                        return departure_date.strftime("%Y-%m-%d"), None
            except:
                pass
            return None, None

    # ---- ONE-WAY FLIGHT HANDLING ---- #
    else:
        # Check special dates first
        sorted_specials = sorted(special_date_map.keys(), key=len, reverse=True)
        for word in sorted_specials:
            if word in normalized_text:
                return special_date_map[word]

        # FIXED: Parse with age filtering - also look for relative date patterns
        relative_date_patterns = [
            (r'\bnext\s+(\w+day)\b', 'next'),    # next thursday, next monday, etc.
            (r'\bthis\s+(\w+day)\b', 'this'),    # this friday, this saturday, etc.
            (r'\b(\w+day)\s+next\b', 'next'),    # thursday next, friday next, etc.
        ]
        
        for pattern, prefix in relative_date_patterns:
            matches = re.findall(pattern, normalized_text)
            for match in matches:
                try:
                    cal = parsedatetime.Calendar()
                    if isinstance(match, tuple):
                        day_name = match[0]
                    else:
                        day_name = match
                    
                    # Construct the proper date phrase based on the prefix
                    if prefix == 'this':
                        date_phrase = f"this {day_name}"
                    else:  # prefix == 'next'
                        date_phrase = f"next {day_name}"
                    
                    
                    time_struct, parse_status = cal.parse(date_phrase)
                    if parse_status >= 1:
                        parsed_date = datetime(*time_struct[:6])
                        if parsed_date.year <= today.year + 2:
                            return parsed_date.strftime("%Y-%m-%d")
                except Exception as e:
                    print(f"❌ Error parsing '{date_phrase}': {e}")
                    pass

        # FIXED: Parse with age filtering
        try:
            cal = parsedatetime.Calendar()
            time_struct, parse_status = cal.parse(normalized_text)
            if parse_status >= 1:
                parsed_date = datetime(*time_struct[:6])
                # FIXED: Ensure the parsed date is reasonable (not affected by age mentions)
                if parsed_date.year <= today.year + 2:
                    return parsed_date.strftime("%Y-%m-%d")
                else:
                    print(f"❌ Date rejected - too far in future: {parsed_date.year}")
        except Exception as e:
            print(f"❌ Final parsing failed: {e}")
            pass

        return None


# Additional helper function to validate airline extraction
def validate_airline_extraction(query, extracted_airline):
    """
    Validate that the extracted airline makes sense in the context.
    Returns True if valid, False if likely a false positive.
    """
    if not extracted_airline:
        return True  # None is always valid
    
    query_lower = query.lower()
    
    # Check if query explicitly mentions flights or airlines
    flight_indicators = ['flight', 'airline', 'airways', 'fly with', 'book with', 
                        'travel with', 'prefer', 'carrier']
    
    has_flight_context = any(indicator in query_lower for indicator in flight_indicators)
    
    # If no flight context and it's just a route query, likely false positive
    route_only_patterns = [
        r'travel from .+ to .+$',
        r'go from .+ to .+$',
        r'.+ to .+$'
    ]
    
    is_route_only = any(re.search(pattern, query_lower) for pattern in route_only_patterns)
    
    if is_route_only and not has_flight_context:
        return False
        
    return True


def extract_travel_info(query):
    """
    Main function to extract all travel information from a query.
    Enhanced with negation handling and context preservation.
    
    Args:
        query (str): User's travel query
    
    Returns:
        dict: Dictionary containing all extracted travel information
    """
    result = {}
    
    # Check if this is a modification query with negation
    is_modification_query = " now " in query.lower() or query.lower().strip().startswith("now ")
    
    if is_modification_query:
        # Split into original context and modification parts
        query_lower = query.lower()
        if " now " in query_lower:
            original_part = query[:query_lower.find(" now ")].strip()
            modification_part = query[query_lower.find(" now "):].strip()
        else:
            original_part = ""
            modification_part = query.strip()
        
        # Extract information from original context first (if exists)
        original_info = {}
        if original_part:
            original_info = _extract_basic_travel_info(original_part)
        
        # Extract information from modification part
        modification_info = _extract_basic_travel_info(modification_part)
        
        # Merge information, giving priority to modification (negated content)
        result = original_info.copy()
        for key, value in modification_info.items():
            if value is not None and value != '' and value != 'null':
                result[key] = value
    else:
        # Normal extraction for non-modification queries
        result = _extract_basic_travel_info(query)
    
    # Set default values if not specified
    if not result.get("flight_class"):
        result["flight_class"] = "economy"
    if not result.get("flight_type"):
        result["flight_type"] = "one_way"
    if not result.get('passengers'):
        result['passengers'] = {"adults": 1, "children": 0, "infants": 0}
        
    # Also add total passenger count for convenience
    if result.get('passengers'):
        total_passengers = result["passengers"]["adults"] + result["passengers"]["children"] + result["passengers"]["infants"]
        result["total_passengers"] = total_passengers
    
    return result

def _extract_basic_travel_info(query):
    """
    Basic travel information extraction without modification handling.
    Used internally by extract_travel_info.
    """
    result = {}
    
    # Extract cities
    source, destination = extract_cities(query)
    
    # Ensure source and destination are different
    if source and destination and source == destination:
        destination = None
    
    if source:
        result["source"] = source
    else:
        result["source"] = None
    if destination:
        result["destination"] = destination
    else:
        result["destination"] = None
    
    # Extract flight type
    flight_type = extract_flight_type(query)
    result["flight_type"] = flight_type
    
    # Extract flight class
    flight_class = extract_flight_class(query)
    result["flight_class"] = flight_class
    
    # Extract dates based on flight type
    if flight_type == "return":
        departure_date, return_date = extract_dates(query, flight_type)
        if departure_date:
            result["departure_date"] = departure_date
        else:
            result["departure_date"] = None
        if return_date:
            result["return_date"] = return_date
        else:
            result["return_date"] = None
    else:
        date = extract_dates(query, flight_type)
        if date:
            result["departure_date"] = date
        else:
            result["departure_date"] = None
    
    # Extract passenger count
    try:
        passenger_counts = extract_passenger_count(query)
        result["passengers"] = passenger_counts
    except Exception as e:
        print(f"Warning: Passenger count extraction failed: {e}")
        # Fallback to default
        result["passengers"] = {"adults": 1, "children": 0, "infants": 0}
    return result

# Enhanced command-line interface
if __name__ == "__main__":
    print("🚀 Travel Parameter Extraction System")
    print("💡 For better experience, use: streamlit run streamlit_ui.py")
    print("-" * 50)
    
    while True:
        query = input("\n📝 Enter your travel query (or 'exit' to quit): ").strip()
        if query.lower() in ["exit", "quit"]:
            print("✈️ Safe travels! Goodbye!")
            break
        if not query:
            continue
        try:
            result = extract_travel_info(query)
            print("\n🔍 Extracted Information:")
            for key, value in result.items():
                if value:
                    print(f"  {key}: {value}")
            print()
        except Exception as e:
            print(f"❌ Error processing query: {e}")