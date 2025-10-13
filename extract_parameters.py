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

def is_valid_date(date_str, parsed_date, today):
    """
    Validate if a parsed date is reasonable and valid.
    
    Args:
        date_str: Original date string
        parsed_date: Parsed datetime object
        today: Current date
    
    Returns:
        bool: True if date is valid, False otherwise
    """
    try:
        # Check for clearly invalid dates
        if '32nd' in date_str.lower() or '31st february' in date_str.lower() or '30th february' in date_str.lower():
            return False
        
        # Check for impossible day-month combinations
        if parsed_date.month == 2 and parsed_date.day > 29:
            return False
        if parsed_date.month in [4, 6, 9, 11] and parsed_date.day > 30:
            return False
        if parsed_date.day > 31:
            return False
        
        # Check if date is too far in the past (more than 1 year ago)
        if parsed_date < today - timedelta(days=365):
            return False
        
        # Check if date is too far in the future (more than 2 years)
        if parsed_date > today + timedelta(days=730):
            return False
        
        # Check for year mismatches - if original string specifies a year, it should match
        year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
        if year_match:
            specified_year = int(year_match.group())
            # If user specified a year, it should match (allowing for reasonable range)
            if abs(specified_year - parsed_date.year) > 1:
                return False
            # Reject clearly wrong years
            if specified_year < today.year - 1 or specified_year > today.year + 2:
                return False
        
        # Check for year boundaries - if year seems wrong
        if parsed_date.year < today.year - 1 or parsed_date.year > today.year + 2:
            return False
        
        return True
    except Exception:
        return False

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
            
        relevant_text = text_lower[now_start:].strip()
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

def handle_negation_in_cities(full_query, now_part):
    """
    Handle negation patterns in modification queries for cities.
    Returns (source, destination) tuple if negation is detected, None otherwise.
    """
    # Extract cities from the original context (before "now")
    # Handle both "Now" and "now" cases
    if " Now " in full_query:
        before_now = full_query.split(" Now ")[0]
    elif " now " in full_query:
        before_now = full_query.split(" now ")[0]
    else:
        before_now = ""
    
    # Use extract_cities to get proper source/destination with directional logic
    context_source, context_dest = extract_cities(before_now) if before_now else (None, None)
    
    # FIRST: Check for swap/reverse patterns (vice versa, other way around, etc.)
    swap_patterns = [
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:the\s+)?other\s+way\s+around',  # "other way around", "no other way around", "i want other way around"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:the\s+)?vice\s+versa',  # "vice versa", "no vice versa", "i want vice versa"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:the\s+)?reverse(?:\s+(?:please|it|them|direction|way))?',  # "reverse", "reverse please", "reverse direction"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:to\s+)?swap\s+(?:them|it|cities)?',  # "swap", "swap them", "i want to swap"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:the\s+)?opposite\s+(?:way|direction)?',  # "opposite way", "opposite direction"
        r'(?:tell\s+me\s+about\s+(?:the\s+)?fares?\s+)?(?:the\s+)?other\s+way\s+around',  # "tell me about the fares other way around"
        r'(?:check\s+)?(?:the\s+)?return\s+(?:journey|trip|direction)',  # "check the return journey"
        r'(?:what\s+about\s+)?(?:going\s+)?back(?:\s+the\s+other\s+way)?',  # "what about going back", "going back the other way"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:to\s+go\s+)?(?:the\s+)?reverse\s+direction',  # "reverse direction"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:to\s+)?flip\s+(?:it|them|cities)?',  # "flip it", "flip them"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:to\s+)?invert\s+(?:it|them|cities)?',  # "invert it", "invert them"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:the\s+)?backward(?:\s+direction)?',  # "backward", "backward direction"
        r'(?:no,?\s+)?(?:i\s+want\s+)?(?:to\s+)?turn\s+(?:it\s+)?around',  # "turn it around", "turn around"
    ]
    
    for pattern in swap_patterns:
        if re.search(pattern, now_part.lower()):
            # Swap source and destination from context
            if context_source and context_dest:
                # Swap: destination becomes source, source becomes destination
                return context_dest, context_source
            elif context_source:
                # Only source in context, can't swap with nothing
                return context_source, None
            elif context_dest:
                # Only destination in context, can't swap with nothing
                return None, context_dest
    
    # SECOND: For backward compatibility, also extract using multiword for the negation patterns
    context_cities = extract_cities_multiword(before_now)
    
    # SECOND: Check for regular negation patterns for cities
    negation_patterns = [
        r'no,?\s+not\s+from\s+(\w+)\s+but\s+(\w+)',  # "no not from lhe but isb"
        r'not\s+from\s+(\w+)\s+but\s+(?:from\s+)?(\w+)',  # "not from lhe but from isb" or "not from lhe but isb"
        r'not\s+to\s+(\w+)\s+but\s+(?:to\s+)?(\w+)',  # "not to karachi but rawalpindi" or "not to khi but to isb"
        r'(?:no,?\s+)?(?:from\s+)?(\w+)\s+not\s+(\w+)',  # "isb not lhe", "from isb not lhe"
        r'(?:no,?\s+)?(?:to\s+)?(\w+)\s+not\s+(\w+)',  # "to isb not lhe", "isb not lhe"
        r'not\s+(\w+)\s+but\s+(\w+)',  # "not lhe but isb"
        r'not\s+(\w+)',  # "not lhe"
        r'no,?\s+(?:from\s+)?(\w+)',  # "no, from isb"
    ]
    
    # Look for negation patterns in the now part
    for i, pattern in enumerate(negation_patterns):
        match = re.search(pattern, now_part)
        if match:
            groups = match.groups()
            
            # Handle new patterns first
            if i == 0:  # "no not from lhe but isb"
                negated_city = groups[0].strip()  # lhe (what we're rejecting)
                new_city = groups[1].strip()      # isb (what we want)
                
                # Convert to IATA codes
                new_city_iata = city_to_iata.get(new_city.lower())
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                
                if new_city_iata:
                    # This is clearly a source change, preserve destination
                    context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                    return new_city_iata, context_dest
                    
            elif i == 1:  # "not from lhe but from isb"
                negated_city = groups[0].strip()  # lhe 
                new_city = groups[1].strip()      # isb
                
                # Convert to IATA codes
                new_city_iata = city_to_iata.get(new_city.lower())
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                
                if new_city_iata:
                    # This is clearly a source change, preserve destination
                    context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                    return new_city_iata, context_dest
                    
            elif i == 2:  # "not to karachi but rawalpindi"
                negated_city = groups[0].strip()  # karachi (what we're rejecting)
                new_city = groups[1].strip()      # rawalpindi (what we want)
                
                # Convert to IATA codes
                new_city_iata = city_to_iata.get(new_city.lower())
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                
                if new_city_iata:
                    # This is clearly a destination change, preserve source
                    context_source = context_cities[0][0] if context_cities else None
                    return context_source, new_city_iata
                    
            elif i == 3:  # "isb not lhe", "from isb not lhe" 
                new_city = groups[0].strip()      # isb (what we want)
                negated_city = groups[1].strip()  # lhe (what we're rejecting)
                
                # Convert to IATA codes
                new_city_iata = city_to_iata.get(new_city.lower())
                negated_city_iata = city_to_iata.get(negated_city.lower())
                
                # If not found as city name, check if it's already an IATA code
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                if not negated_city_iata and len(negated_city) == 3 and negated_city.upper() in iata_codes:
                    negated_city_iata = negated_city.upper()
                
                if new_city_iata and negated_city_iata:
                    context_source = context_cities[0][0] if context_cities else None
                    context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                    
                    # Check if this is a "from X not Y" pattern - source change
                    if "from" in now_part.lower():
                        return new_city_iata, context_dest  # X is source, preserve destination
                    else:
                        # Determine which position to replace based on context
                        if context_source == negated_city_iata:
                            return new_city_iata, context_dest  # Replace source
                        elif context_dest == negated_city_iata:
                            return context_source, new_city_iata  # Replace destination
                        else:
                            # Default: assume it's a source change
                            return new_city_iata, context_dest
                            
            elif i == 4:  # "to isb not lhe", "isb not lhe" for destination
                new_city = groups[0].strip()      # isb (what we want)
                negated_city = groups[1].strip()  # lhe (what we're rejecting)
                
                # Convert to IATA codes
                new_city_iata = city_to_iata.get(new_city.lower())
                negated_city_iata = city_to_iata.get(negated_city.lower())
                
                # If not found as city name, check if it's already an IATA code
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                if not negated_city_iata and len(negated_city) == 3 and negated_city.upper() in iata_codes:
                    negated_city_iata = negated_city.upper()
                
                if new_city_iata and negated_city_iata:
                    context_source = context_cities[0][0] if context_cities else None
                    context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                    
                    # Check if this is a "to X not Y" pattern - destination change
                    if "to" in now_part.lower():
                        return context_source, new_city_iata  # X is destination, preserve source
                    else:
                        # Determine which position to replace based on context
                        if context_source == negated_city_iata:
                            return new_city_iata, context_dest  # Replace source
                        elif context_dest == negated_city_iata:
                            return context_source, new_city_iata  # Replace destination
                        else:
                            # Default: assume it's a destination change for this pattern
                            return context_source, new_city_iata
                    
            elif i == 5:  # "not lhe but isb" (index shifted due to new patterns)
                negated_city = groups[0].strip()  # lhe
                new_city = groups[1].strip()      # isb
                
                # Convert to IATA codes
                new_city_iata = city_to_iata.get(new_city.lower())
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                
                if new_city_iata:
                    # Determine which position to replace based on context
                    context_source = context_cities[0][0] if context_cities else None
                    context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                    
                    # Check which city is being negated to determine replacement
                    negated_city_iata = city_to_iata.get(negated_city.lower())
                    if not negated_city_iata and len(negated_city) == 3 and negated_city.upper() in iata_codes:
                        negated_city_iata = negated_city.upper()
                    
                    if negated_city_iata:
                        if context_source == negated_city_iata:
                            return new_city_iata, context_dest  # Replace source
                        elif context_dest == negated_city_iata:
                            return context_source, new_city_iata  # Replace destination
                        else:
                            # Default: assume it's a source change
                            return new_city_iata, context_dest
                    
            elif len(groups) == 2 and groups[1]:  # Original pattern like "isb not lhe"
                new_city = groups[0].strip()
                negated_city = groups[1].strip()
                
                # Convert to IATA if possible
                new_city_iata = city_to_iata.get(new_city.lower())
                negated_city_iata = city_to_iata.get(negated_city.lower())
                
                # If not found as city name, check if it's already an IATA code
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                if not negated_city_iata and len(negated_city) == 3 and negated_city.upper() in iata_codes:
                    negated_city_iata = negated_city.upper()
                
                if new_city_iata and negated_city_iata:
                    # Find which position the negated city had in context
                    context_source = context_cities[0][0] if context_cities else None
                    context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                    
                    # The pattern "X not Y" in "from X not Y" context means:
                    # - User wants to travel FROM X (new/confirmed source)
                    # - NOT from Y (rejecting Y as source)
                    # So X becomes the source, and we preserve the original destination
                    
                    # Check if this is a "from X not Y" pattern
                    if "from" in now_part.lower():
                        return new_city_iata, context_dest  # X is source, preserve destination
                    else:
                        # General "X not Y" pattern - need to determine which one was being replaced
                        if context_source == negated_city_iata:
                            return new_city_iata, context_dest  # Replace source
                        elif context_dest == negated_city_iata:
                            return context_source, new_city_iata  # Replace destination
                        else:
                            # Default: assume it's a source change
                            return new_city_iata, context_dest
                        
            elif len(groups) >= 1 and groups[0]:  # Pattern like "not lhe" or "no, from isb"
                new_city = groups[0].strip()
                new_city_iata = city_to_iata.get(new_city.lower())
                
                # If not found as city name, check if it's already an IATA code
                if not new_city_iata and len(new_city) == 3 and new_city.upper() in iata_codes:
                    new_city_iata = new_city.upper()
                
                if new_city_iata:
                    # Check directional indicators to determine if it's source or destination
                    if any(indicator in now_part for indicator in ["from", "leaving", "departing"]):
                        # It's a source change
                        context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                        return new_city_iata, context_dest
                    elif any(indicator in now_part for indicator in ["to", "going to", "destination"]):
                        # It's a destination change
                        context_source = context_cities[0][0] if context_cities else None
                        return context_source, new_city_iata
                    else:
                        # Default behavior based on context
                        context_source = context_cities[0][0] if context_cities else None
                        context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                        
                        # If only one city in context, assume we're changing the source
                        if context_source and not context_dest:
                            return new_city_iata, None
                        else:
                            return new_city_iata, context_dest
    return None

def handle_city_modifications_with_groq(full_query, now_part):
    """
    GROQ-powered city modification handler for negations and swaps.
    Returns (source, destination) tuple if modification is detected, None otherwise.
    """
    # Extract context from before "now"
    if " Now " in full_query:
        before_now = full_query.split(" Now ")[0]
    elif " now " in full_query:
        before_now = full_query.split(" now ")[0]
    else:
        before_now = ""
    
    # Get context cities using multiword extraction to avoid recursion
    context_cities = extract_cities_multiword(before_now) if before_now else []
    context_source = context_cities[0][0] if context_cities else None
    context_dest = context_cities[1][0] if len(context_cities) > 1 else None
    
    # Initialize Groq client
    try:
        client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
    except Exception as e:
        print(f"Error initializing Groq client for city modifications: {e}")
        # Fallback to original regex-based function
        return handle_negation_in_cities(full_query, now_part)
    
    # Create city list for reference
    available_cities = list(city_to_iata.keys()) + list(iata_codes)
    city_context = f"Available cities: {', '.join(sorted(city_to_iata.keys()))}"
    iata_context = f"IATA codes: {', '.join(sorted(iata_codes))}"
    
    # Build context info
    context_info = ""
    if context_source or context_dest:
        context_info = f"CURRENT BOOKING: From {context_source or 'unknown'} to {context_dest or 'unknown'}"
    
    prompt = f"""
Analyze this travel modification request and determine if it's a city change, swap, or negation.

CONTEXT:
{context_info}
{city_context}
{iata_context}

MODIFICATION REQUEST: "{now_part}"
FULL QUERY: "{full_query}"

TASK: Determine the modification type and return the new source/destination cities.

MODIFICATION TYPES:
1. SWAP/REVERSE: "vice versa", "other way around", "reverse", "swap", "flip", "opposite direction", "turn around", "backward"
2. SOURCE_CHANGE: "not from X but Y", "from Y not X", "no from Y", changing departure city
3. DESTINATION_CHANGE: "not to X but Y", "to Y not X", "no to Y", changing arrival city
4. NEGATION: "not X but Y", "X not Y", rejecting one city for another
5. CONFIRMATION/REPETITION: Same cities mentioned again with additional details (dates, passengers, etc.)
6. FLIGHT_TYPE_CHANGE: Phrases about coming back, returning, or flight type changes without city swapping

RULES:
- For SWAP: ONLY when explicitly requesting direction reversal with phrases like "vice versa", "other way around", "reverse direction"
- For SOURCE_CHANGE: Keep destination, change source
- For DESTINATION_CHANGE: Keep source, change destination
- For NEGATION: Determine which city is being replaced based on context
- For CONFIRMATION/REPETITION: If the same cities are mentioned (e.g., context "LHE to KHI" and request "go from LHE to KHI tomorrow"), return NONE
- For FLIGHT_TYPE_CHANGE: Phrases like "come back", "will return", "comeback" are FLIGHT TYPE changes, NOT city swaps - return NONE
- Always use IATA codes (3-letter airport codes)
- City names should be converted to IATA codes
- Be VERY STRICT: Only swap cities when there's explicit direction reversal language

EXAMPLES:
Input: "vice versa" with context "LHE to KHI"
Output: {{"modification_type": "SWAP", "source": "KHI", "destination": "LHE"}}

Input: "other way around" with context "LHE to KHI" 
Output: {{"modification_type": "SWAP", "source": "KHI", "destination": "LHE"}}

Input: "not from lahore but karachi" with context "LHE to ISB"  
Output: {{"modification_type": "SOURCE_CHANGE", "source": "KHI", "destination": "ISB"}}

Input: "not to islamabad but rawalpindi" with context "LHE to ISB"
Output: {{"modification_type": "DESTINATION_CHANGE", "source": "LHE", "destination": "ISB"}}

Input: "i will go from lhe to khi tomorrow" with context "LHE to KHI"
Output: {{"modification_type": "NONE"}}

Input: "i will come back" with context "LHE to KHI"
Output: {{"modification_type": "NONE"}}

Input: "i will return" with context "LHE to KHI"
Output: {{"modification_type": "NONE"}}

Input: "will comeback" with context "LHE to KHI"
Output: {{"modification_type": "NONE"}}

Input: "going back" with context "LHE to KHI"
Output: {{"modification_type": "NONE"}}

Return ONLY valid JSON without explanations:
{{"modification_type": "TYPE", "source": "XXX", "destination": "YYY"}}

If no modification detected, return: {{"modification_type": "NONE"}}
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            temperature=0.1,
            max_tokens=200,
            top_p=0.9
        )
        
        response_text = chat_completion.choices[0].message.content.strip()
        
        # Extract and clean JSON
        modification_data = extract_and_clean_json(response_text)
        
        modification_type = modification_data.get('modification_type', 'NONE')
        
        if modification_type == 'NONE':
            return None
            
        # Validate and return the cities
        source = modification_data.get('source')
        destination = modification_data.get('destination')
        
        # Convert city names to IATA if needed
        if source and len(source) != 3:
            source = city_to_iata.get(source.lower(), source)
        if destination and len(destination) != 3:
            destination = city_to_iata.get(destination.lower(), destination)
        
        # Validate IATA codes
        if source and source not in iata_codes:
            source = None
        if destination and destination not in iata_codes:
            destination = None
            
        return (source, destination)
        
    except Exception as e:
        print(f"Error with Groq API for city modifications: {e}")
        # Fallback to original regex-based function
        return handle_negation_in_cities(full_query, now_part)

def extract_cities(query):
    query_lower = query.lower()
    
    # Special case: Handle modification queries containing "Now"
    # This is for conversational modifications where the agent asks for changes
    is_modification_query = " now " in query_lower or query_lower.strip().startswith("now ")
    
    if is_modification_query:
        
        # Find the "Now" part and extract cities from it
        if " now " in query_lower:
            now_start = query_lower.find(" now ") + 1  # +1 to include the space before "now"
        else:
            now_start = 0  # If it starts with "now"
            
        now_part = query_lower[now_start:].strip()
        
        # Handle negation patterns in modification queries using GROQ
        negation_handled_cities = handle_city_modifications_with_groq(query_lower, now_part)
        if negation_handled_cities:
            return negation_handled_cities
        
        now_cities = extract_cities_multiword(now_part)
        
        if now_cities:
            # Process only the cities from the "Now" modification
            found_cities = now_cities
            # Use the "Now" part for directional analysis too
            analysis_text = now_part
            doc = nlp(now_part)
        else:
            # Fallback to full extraction if no cities found in "Now" part
            found_cities = extract_cities_multiword(query_lower)
            analysis_text = query_lower
            doc = nlp(query_lower)
    else:
        # Normal extraction process
        # First try to extract multi-word cities
        found_cities = extract_cities_multiword(query_lower)
        analysis_text = query_lower
        doc = nlp(query_lower)
    
    # If no multi-word cities found, try entity recognition and fuzzy matching
    if not found_cities:
        for ent in doc.ents:
            if ent.label_ in ("GPE", "LOC"):
                match, score, _ = process.extractOne(ent.text.lower(), city_names)
                if score > 85:
                    iata = city_to_iata[match]
                    found_cities.append((iata, ent.start, ent.start_char))
    
    # Fallback to token-based fuzzy matching if still no entities found
    if not found_cities:
        tokens = [token.text for token in doc]  # Keep original case for IATA detection
        for i, token in enumerate(tokens):
            # Check if token is an IATA code
            if len(token) == 3 and token.upper() in iata_codes:
                found_cities.append((token.upper(), i, doc[i].idx))
            else:
                # Try fuzzy matching with city names
                match, score, _ = process.extractOne(token.lower(), city_names)
                if score > 90:
                    iata = city_to_iata[match]
                    found_cities.append((iata, i, doc[i].idx))
    
    # Remove duplicates and sort by character position
    seen = set()
    unique_cities = []
    for city, token_idx, char_idx in found_cities:
        if city not in seen:
            seen.add(city)
            unique_cities.append((city, token_idx, char_idx))
    found_cities = sorted(unique_cities, key=lambda x: x[2])  # Sort by character position
    
    # Use improved logic to identify source and destination
    source = destination = None
    
    # Look for directional indicators in the analysis text (which is either full query or "Now" part)
    from_indicators = ["from", "leaving", "departing", "starting"]
    to_indicators = ["to", "towards", "going to", "arriving", "destination"]
    
    # Check for explicit directional phrases using the correct analysis text
    for token in doc:
        if token.text.lower() in from_indicators:
            for city_info in found_cities:
                city_iata, city_token_idx, city_char_idx = city_info
                # Make sure this city is before any 'to' indicator in the query
                if city_char_idx > token.idx:
                    next_to_pos = min((t.idx for t in doc if t.text.lower() in to_indicators), default=None)
                    if next_to_pos and city_char_idx > next_to_pos:
                        continue  # Skip cities that actually belong to the 'to' part
                    if not source:
                        source = city_iata
                        break

        
        elif token.text.lower() in to_indicators or (token.text.lower() == "to" and token.dep_ == "prep"):
            # Look for cities after "to" indicators
            for city_info in found_cities:
                city_iata, city_token_idx, city_char_idx = city_info
                if city_char_idx > token.idx:  # City appears after the indicator
                    if not destination:  # Take the first one found
                        destination = city_iata
                        break
    
    # Special handling for modification queries: preserve context when only one side is modified
    if is_modification_query and (source or destination) and not (source and destination):
        # Extract context from before "now" to fill in missing information
        before_now = query_lower.split(" now ")[0] if " now " in query_lower else ""
        context_cities = extract_cities_multiword(before_now)
        context_source = context_cities[0][0] if context_cities else None
        context_dest = context_cities[1][0] if len(context_cities) > 1 else None
        
        if source and not destination and context_dest:
            # We have a new source but no destination, use context destination
            destination = context_dest
        elif destination and not source and context_source:
            # We have a new destination but no source, use context source
            source = context_source
    
    # Fallback: If no clear indicators found, use position-based logic
    if not source and not destination and found_cities:
        if len(found_cities) == 1:
            # Single city - could be either source or destination
            
            # Special handling for modification queries
            if is_modification_query:
                # Extract context from before "now" to understand what we're modifying
                before_now = query_lower.split(" now ")[0] if " now " in query_lower else ""
                context_cities = extract_cities_multiword(before_now)
                context_source = context_cities[0][0] if context_cities else None
                context_dest = context_cities[1][0] if len(context_cities) > 1 else None
                
                single_city = found_cities[0][0]
                
                # Determine if we're changing source or destination based on context
                if any(indicator in analysis_text for indicator in ["from", "leaving", "departing", "starting"]):
                    # It's a source change - preserve destination from context
                    source = single_city
                    destination = context_dest
                elif any(indicator in analysis_text for indicator in to_indicators + ["going", "want to go"]):
                    # It's a destination change - preserve source from context
                    source = context_source
                    destination = single_city
                else:
                    # No clear indicators - use heuristics
                    # If context has both source and dest, and single city matches one, we're probably changing the other
                    if context_source and context_dest:
                        if single_city == context_source:
                            # Same source mentioned, might be confirming or we need more context
                            source = single_city
                            destination = context_dest
                        elif single_city == context_dest:
                            # Same destination mentioned
                            source = context_source
                            destination = single_city
                        else:
                            # New city - default to changing source
                            source = single_city
                            destination = context_dest
                    elif context_source and not context_dest:
                        # Only source in context - new city is likely destination
                        source = context_source
                        destination = single_city
                    elif context_dest and not context_source:
                        # Only destination in context - new city is likely source
                        source = single_city
                        destination = context_dest
                    else:
                        # No context - default behavior
                        source = single_city
            else:
                # Original logic for non-modification queries
                # Check context for clues in analysis text
                if any(word in analysis_text for word in to_indicators + ["going", "want to go"]):
                    destination = found_cities[0][0]
                else:
                    source = found_cities[0][0]
        else:
            # Multiple cities - first is typically source, second is destination
            source = found_cities[0][0]
            destination = found_cities[1][0]
    
    # Handle cases where we have indicators but cities were assigned to wrong slots
    if source and not destination and len(found_cities) > 1:
        # If we have a source but no destination, and there are multiple cities
        for city_info in found_cities:
            if city_info[0] != source:
                destination = city_info[0]
                break
    
    elif destination and not source and len(found_cities) > 1:
        # If we have a destination but no source, and there are multiple cities
        for city_info in found_cities:
            if city_info[0] != destination:
                source = city_info[0]
                break
    
    # Ensure source != destination
    if source == destination:
        if len(found_cities) > 1:
            # If they're the same, reassign based on position
            source = found_cities[0][0]
            destination = found_cities[1][0]
        else:
            destination = None
    
    return source, destination

def extract_flight_type(query):
    """
    Conservative flight type extraction - only detects return when there are strong indicators.
    Returns 'return' or 'one_way'
    """
    query_lower = query.lower()
    
    # Special handling for "Now" modification queries
    is_modification_query = " now " in query_lower or query_lower.strip().startswith("now ")
    
    if is_modification_query:
        # Find the "Now" part and focus flight type extraction on it
        if " now " in query_lower:
            now_start = query_lower.find(" now ") + 5  # +5 to skip " now "
        else:
            now_start = 4  # Skip "now "
            
        now_part = query_lower[now_start:].strip()
        
        # Check for explicit flight type changes in the modification
        one_way_change_patterns = [
            # Explicit one-way requests with all variations
            r'(?:no,?\s+)?(?:i\s+)?want\s+one[\s\-_]way(?:\s+flight)?',
            r'(?:no,?\s+)?(?:i\s+)?(?:want\s+)?one[\s\-_]way(?:\s+flight)?',
            r'(?:change\s+to\s+)?one[\s\-_]way',
            r'(?:make\s+it\s+)?one[\s\-_]way',
            
            # Negation patterns - explicit rejection of return trips (improved patterns)
            r'(?:i\s+)?(?:will\s+)?not\s+(?:come\s*)?back',  # "will not comeback", "not comeback"
            r'(?:i\s+)?(?:will\s+)?not\s+comeback',  # "will not comeback" as one word
            r'(?:i\s+)?(?:do\s*n\'?t|don\'?t)\s+want\s+to\s+go\s+back',  # "don't want to go back"
            r'(?:i\s+)?(?:do\s*n\'?t|don\'?t)\s+want\s+(?:to\s+)?(?:come\s*)?back',  # "don't want comeback"
            r'(?:i\s+)?(?:do\s*n\'?t|don\'?t|will\s+not|not)\s+want\s+(?:a\s+)?return',
            r'(?:i\s+)?(?:do\s*n\'?t|don\'?t|will\s+not|not)\s+want\s+(?:to\s+)?return',
            r'(?:i\s+)?(?:will\s+)?not\s+return',
            r'(?:i\s+)?(?:am\s+)?not\s+(?:coming|going)\s+back',  # "not coming back", "not going back"
            r'no\s+return',
            r'not\s+return',
            r'not\s+round\s+trip',
            r'no\s+round\s+trip',
            
            # Explicit one-way statements
            r'(?:just\s+)?one[\s\-_]way\s+(?:only|ticket|flight)',
            r'only\s+one[\s\-_]way',
            r'single\s+(?:trip|journey|flight)',
            r'just\s+(?:going|traveling)',
            r'(?:i\s+)?(?:am\s+)?not\s+coming\s+back'
        ]
        
        return_change_patterns = [
            r'(?:i\s+will\s+)?(?:come\s+)?back\s+(?:to\s+\w+\s+)?on\s+',
            r'(?:i\s+will\s+)?return\s+(?:to\s+\w+\s+)?on\s+',
            r'(?:change\s+to\s+)?(?:round\s+trip|return)',
            r'(?:make\s+it\s+)?(?:round\s+trip|return)'
        ]
        
        # Check for one-way change patterns
        for pattern in one_way_change_patterns:
            if re.search(pattern, now_part):
                return "one_way"
        
        # Check for return change patterns  
        for pattern in return_change_patterns:
            if re.search(pattern, now_part):
                return "return"
        
        # If no explicit change in modification, analyze the full query for context
        text_for_analysis = query_lower
    else:
        # Use full text for normal queries
        text_for_analysis = query_lower
    
    # Pre-emptively detect explicit one-way intents so they are not overridden by generic
    # "return" keywords that might appear as part of phrases like "returning one way".
    one_way_patterns = [
        r'\bone[\s\-_]?way\b',
        r'\bone[\s\-_]?way\s+(?:trip|journey|flight|ticket)\b',
        r'\bsingle\s+(?:trip|journey|flight|ticket)\b',
        r'\bno\s+return\b',
        r'\bwithout\s+(?:any\s+)?return\b',
        r"\bdo\s+not\s+want\s+(?:a\s+)?return\b",
        r"\bdon't\s+want\s+(?:a\s+)?return\b",
        r"\bdont\s+want\s+(?:a\s+)?return\b",
        r'\bnot\s+coming\s+back\b',
    ]
    
    for pattern in one_way_patterns:
        if re.search(pattern, text_for_analysis):
            return "one_way"
    
    # Strong explicit return flight indicators
    strong_return_keywords = [
        "return", "round trip", "round-trip", "roundtrip", "two way", "two-way",
        "return ticket", "return flight", "both ways", "comeback", "come back"
    ]
    
    # Check for explicit return keywords first
    for keyword in strong_return_keywords:
        if keyword in text_for_analysis:
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
        if re.search(pattern, text_for_analysis):
            return "return"
    
    # Check for "between" with locations - strong return indicator
    if "between" in text_for_analysis:
        # Look for "between [city] and [city]" or "between [date] and [date]"
        between_pattern = r'between\s+\w+.*?and\s+\w+'
        if re.search(between_pattern, text_for_analysis):
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
    Supported classes: economy, business, first, premium_economy
    Uses multiple strategies with fallbacks for robust extraction.
    Handles "Now" modification queries for flight class changes.
    """
    query_lower = query.lower()
    
    # Special handling for "Now" modification queries - extract class from the modification part
    is_modification_query = " now " in query_lower or query_lower.strip().startswith("now ")
    
    if is_modification_query:
        
        # Find the "Now" part and focus class extraction on it
        if " now " in query_lower:
            now_start = query_lower.find(" now ") + 5  # +5 to skip " now "
        else:
            now_start = 4  # Skip "now "
            
        now_part = query_lower[now_start:].strip()
        
        # Check if the "Now" part contains any class information
        class_indicators = [
            'class', 'first', 'business', 'economy', 'premium', 'coach', 'cabin',
            'executive', 'comfort', 'standard', 'basic', 'upgrade'
        ]
        
        has_class_info = any(indicator in now_part for indicator in class_indicators)
        
        if has_class_info:
            # Handle negation patterns first
            negation_result = handle_class_negation(now_part)
            if negation_result:
                return negation_result
            
            # Use the "Now" part for class extraction
            text_for_parsing = now_part
        else:
            # No class info in "Now" part, use original text to preserve existing class
            text_for_parsing = query_lower
    else:
        # Use full text for normal queries
        text_for_parsing = query_lower
    
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
            "premium", "w class", "comfort plus", "economy plus", "economy+", 
            "extra comfort", "preferred seating", "premium seating"
        ],
        
        # Economy variations (explicit mentions)
        "economy": [
            "economy class", "economy-class", "economyclass", "eco class", "economy", 
            "y class", "coach", "main cabin", "standard", "regular", "basic economy"
        ]
    }
    
    # Strategy 1: Direct keyword matching (longest phrases first)
    all_keywords = []
    for class_name, keywords in class_mappings.items():
        for keyword in keywords:
            all_keywords.append((keyword, class_name))
    
    # Sort by length (longest first) to match more specific phrases
    all_keywords.sort(key=lambda x: len(x[0]), reverse=True)
    
    for keyword, class_name in all_keywords:
        if keyword in text_for_parsing:
            return class_name
    
    # Strategy 2: NLP-based extraction using spaCy
    try:
        doc = nlp(text_for_parsing)
        
        # Look for class-related entities or patterns
        class_indicators = ["class", "cabin", "seat", "seating", "service"]
        
        for token in doc:
            if token.text in class_indicators:
                # Look for adjectives or descriptors before/after class indicators
                context_window = []
                
                # Get context around the class indicator (2 tokens before and after)
                start_idx = max(0, token.i - 2)
                end_idx = min(len(doc), token.i + 3)
                
                for context_token in doc[start_idx:end_idx]:
                    context_window.append(context_token.text.lower())
                
                context_text = " ".join(context_window)
                
                # Check if any class keywords appear in context
                for keyword, class_name in all_keywords:
                    if keyword in context_text:
                        return class_name
        
        # Look for luxury/comfort indicators that might suggest higher classes
        luxury_indicators = {
            "business": ["professional", "corporate", "executive", "business trip", "work travel"],
            "first": ["luxury", "luxurious", "premium service", "finest", "exclusive", "vip"],
            "premium_economy": ["comfortable", "extra space", "more room", "upgrade", "better seat"]
        }
        
        query_tokens = [token.text.lower() for token in doc]
        query_text_joined = " ".join(query_tokens)
        
        for class_name, indicators in luxury_indicators.items():
            for indicator in indicators:
                if indicator in query_text_joined:
                    return class_name
                    
    except Exception:
        pass
    
    # Strategy 3: Pattern-based extraction
    class_patterns = [
        # Patterns like "in business class", "book first class"
        (r'\b(?:in|book|reserve|want|need|prefer)\s+(\w+(?:\s+\w+)?)\s+class\b', 1),
        (r'\b(\w+(?:\s+\w+)?)\s+class\s+(?:seat|ticket|flight|fare)\b', 1),
        (r'\b(?:fly|travel)\s+(\w+(?:\s+\w+)?)\s+class\b', 1),
        
        # Patterns like "business class flight", "first class ticket"
        (r'\b(\w+(?:\s+\w+)?)\s+class\s+(?:flight|ticket|booking)\b', 1),
        
        # More flexible patterns
        (r'\b(first|business|economy|premium)\s+(?:class\s+)?(?:seat|ticket|flight|cabin)\b', 1),
        (r'\b(?:seat|ticket|flight|cabin)\s+(?:in\s+)?(\w+(?:\s+\w+)?)\s+class\b', 1),
    ]
    
    for pattern, group_idx in class_patterns:
        matches = re.findall(pattern, text_for_parsing)
        if matches:
            for match in matches:
                extracted_class = match.strip() if isinstance(match, str) else match[group_idx-1].strip()
                
                # Map extracted class to standard class names
                for class_name, keywords in class_mappings.items():
                    if extracted_class in keywords or any(keyword.startswith(extracted_class) for keyword in keywords):
                        return class_name
    
    # Strategy 4: Fuzzy matching for misspellings or variations
    try:
        # Extract potential class-related words
        class_related_words = []
        doc = nlp(text_for_parsing)
        
        for token in doc:
            if (token.pos_ in ["NOUN", "ADJ"] and 
                len(token.text) > 3 and 
                any(indicator in token.text for indicator in ["class", "eco", "biz", "prem", "first", "bus"])):
                class_related_words.append(token.text)
        
        # Check fuzzy matching against known class terms
        all_class_terms = []
        for keywords in class_mappings.values():
            all_class_terms.extend(keywords)
        
        for word in class_related_words:
            best_match, score, _ = process.extractOne(word, all_class_terms)
            if score > 75:  # High threshold for class matching
                for class_name, keywords in class_mappings.items():
                    if best_match in keywords:
                        return class_name
                        
    except Exception:
        pass
    
    # Strategy 5: Context-based inference
    # Look for price-related clues or luxury indicators
    context_clues = {
        "first": ["expensive", "costly", "luxury", "premium service", "champagne", "lie flat"],
        "business": ["work", "corporate", "meeting", "conference", "professional", "lounge access"],
        "premium_economy": ["upgrade", "extra legroom", "more space", "comfortable", "priority boarding"]
    }
    
    for class_name, clues in context_clues.items():
        for clue in clues:
            if clue in text_for_parsing:
                # Only return if there's also some flight-related context
                flight_context = ["flight", "fly", "travel", "ticket", "book", "reserve"]
                if any(context in text_for_parsing for context in flight_context):
                    return class_name
    
    # Strategy 6: Abbreviation detection
    abbreviation_map = {
        "f": "first",
        "j": "business", 
        "c": "business",
        "w": "premium_economy",
        "y": "economy"
    }
    
    # Look for single letter class codes
    single_letter_pattern = r'\b([fjcwy])\s+class\b'
    matches = re.findall(single_letter_pattern, text_for_parsing)
    if matches:
        letter = matches[0].lower()
        if letter in abbreviation_map:
            return abbreviation_map[letter]
    
    # Default fallback - return economy
    return "economy"


def handle_class_negation(now_part):
    """
    Handle negation patterns in modification queries for flight class.
    Returns the appropriate class if negation is detected, None otherwise.
    """
    # Negation patterns for flight class
    class_negation_patterns = [
        r'economy\s+not\s+business(?:\s+class)?',  # "economy not business class"
        r'not\s+business(?:\s+class)?',            # "not business class"
        r'not\s+first(?:\s+class)?',               # "not first class"
        r'not\s+economy(?:\s+class)?',             # "not economy class"
        r'business\s+not\s+economy(?:\s+class)?',  # "business not economy class"
    ]
    
    for pattern in class_negation_patterns:
        match = re.search(pattern, now_part)
        if match:
            # Extract the positive class from the pattern
            if 'economy not business' in match.group():
                return "economy"
            elif 'business not economy' in match.group():
                return "business"
            elif 'not business' in match.group():
                # Default to economy when rejecting business
                return "economy"
            elif 'not first' in match.group():
                # Default to economy when rejecting first
                return "economy"
            elif 'not economy' in match.group():
                # Look for other class mentions in the text
                if 'business' in now_part or 'executive' in now_part:
                    return "business"
                elif 'first' in now_part:
                    return "first"
                else:
                    return "business"  # Default upgrade from economy
    
    return None


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

def handle_date_negation(full_query, now_part):
    """
    Handle negation patterns in modification queries for dates.
    Returns the appropriate date(s) if negation is detected, None otherwise.
    """
    today = datetime.now()
    
    # Negation patterns for dates
    date_negation_patterns = [
        r'not\s+(\d+)(?:st|nd|rd|th)?\s+aug(?:ust)?',  # "not 5th aug"
        r'not\s+(today|tomorrow|day after tomorrow)',   # "not today"
        r'(\d+)(?:st|nd|rd|th)?\s+aug(?:ust)?\s+not\s+(\d+)(?:st|nd|rd|th)?\s+aug(?:ust)?',  # "6th aug not 5th aug"
    ]
    
    for pattern in date_negation_patterns:
        match = re.search(pattern, now_part)
        if match:
            groups = match.groups()
            
            if len(groups) == 2 and groups[1]:  # Pattern like "6th aug not 5th aug"
                new_date_str = groups[0].strip()
                # Try to parse the new date
                try:
                    # Construct full date string for current year
                    cal = parsedatetime.Calendar()
                    date_text = f"{new_date_str} august {today.year}"
                    time_struct, parse_status = cal.parse(date_text)
                    if parse_status >= 1:
                        parsed_date = datetime(*time_struct[:6])
                        return parsed_date.strftime("%Y-%m-%d")
                except:
                    pass
                    
            elif len(groups) >= 1 and groups[0]:  # Pattern like "not 5th aug"
                # This means we're rejecting a specific date, but we need a new date from context
                # Look for other date mentions in the now part
                date_extraction_text = re.sub(pattern, '', now_part).strip()
                if date_extraction_text:
                    try:
                        cal = parsedatetime.Calendar()
                        time_struct, parse_status = cal.parse(date_extraction_text)
                        if parse_status >= 1:
                            parsed_date = datetime(*time_struct[:6])
                            if is_valid_date(date_extraction_text, parsed_date, today):  # Reasonable year check
                                return parsed_date.strftime("%Y-%m-%d")
                    except:
                        pass
    
    return None

def parse_relative_date_with_reference(date_str, reference_date_str=None):
    """
    Parse relative date expressions that can reference either today or a specific departure date.
    
    Args:
        date_str (str): The date string to parse (e.g., "2 days after departure date")
        reference_date_str (str): The departure date to use as reference (YYYY-MM-DD format)
    
    Returns:
        str: Parsed date in YYYY-MM-DD format, or None if parsing fails
    """
    try:
        # Check if the date string references departure date
        departure_reference_patterns = [
                r'(.+?)\s+after\s+departure\s+date',
                r'(.+?)\s+after\s+departure',
                r'(.+?)\s+from\s+departure\s+date',
                r'(.+?)\s+from\s+departure',
                # NEW: handle "after N days/weeks" and "in N days/weeks"
                r'after\s+(\d+\s+(?:days?|weeks?|months?))',
                r'in\s+(\d+\s+(?:days?|weeks?|months?))',
                                    ]
        uses_departure_reference = False
        relative_part = date_str
        
        for pattern in departure_reference_patterns:
            match = re.search(pattern, date_str.lower())
            if match:
                relative_part = match.group(1).strip()
                uses_departure_reference = True
                break
        
        # If no explicit departure reference found, check if it's just a general "later" or similar
        general_time_patterns = [
            r'^\d+\s+(?:days?|weeks?|months?)\s+later$',
            r'^\d+\s+(?:days?|weeks?|months?)\s+ago$',
            r'^(?:tomorrow|today|day after tomorrow)$'
        ]
        
        is_general_time = any(re.match(pattern, date_str.lower()) for pattern in general_time_patterns)
        
        # ENHANCED: If we have a reference date (departure date) and this is a relative time expression,
        # prefer using the reference date even for "general" expressions
        should_use_reference = uses_departure_reference or (reference_date_str and is_general_time)
        
        # Determine the reference date
        if should_use_reference and reference_date_str:
            # Use departure date as reference
            try:
                reference_date = datetime.strptime(reference_date_str, "%Y-%m-%d")
                print(f"🔄 Using departure date {reference_date_str} as reference for '{date_str}'")
            except ValueError:
                print(f"❌ Invalid reference date format: {reference_date_str}")
                return None
        elif is_general_time and not reference_date_str:
            # Use today as reference for general time expressions when no departure date available
            reference_date = datetime.now()
            print(f"🔄 Using today as reference for general time expression '{date_str}'")
        else:
            # Use today as reference (default behavior)
            reference_date = datetime.now()
        
        # Parse the relative part using parsedatetime with the reference date
        cal = parsedatetime.Calendar()
        
        # Set the reference time for parsedatetime
        reference_time = reference_date.timetuple()
        
        # Parse relative expression
        time_struct, parse_status = cal.parse(relative_part, sourceTime=reference_time)
        
        if parse_status >= 1:
            parsed_date = datetime(*time_struct[:6])
            
            # Validate the parsed date using our validation function
            today = datetime.now()
            if is_valid_date(date_str, parsed_date, today):
                result = parsed_date.strftime("%Y-%m-%d")
                print(f"✅ Parsed '{date_str}' relative to {reference_date.strftime('%Y-%m-%d')} = {result}")
                return result
            else:
                print(f"❌ Invalid date detected: '{date_str}' -> {parsed_date.strftime('%Y-%m-%d')}")
                return None
        else:
            print(f"❌ Failed to parse relative date: '{relative_part}'")
            return None
            
    except Exception as e:
        print(f"❌ Error parsing relative date '{date_str}': {e}")
        return None

def extract_dates(text, flight_type=None):
    """
    FIXED: Date extraction function that properly handles age mentions and Now modifications
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
        
        # Check if the "Now" part contains any date information
        # Look for common date indicators
        date_indicators = [
            'today', 'tomorrow', 'day after tomorrow', 'next', 'this', 
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december',
            'on ', 'by ', 'at ', 'st', 'nd', 'rd', 'th'
        ]
        
        # Relative time indicators (written-out numbers and time units)
        relative_time_indicators = [
            'week', 'weeks', 'day', 'days', 'month', 'months', 'year', 'years',
            'later', 'ago', 'after', 'before', 'from now',
            'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
            'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 
            'eighteen', 'nineteen', 'twenty', 'thirty', 'forty', 'fifty', 'sixty'
        ]
        
        has_date_info = any(indicator in now_part for indicator in date_indicators) or \
                       any(indicator in now_part for indicator in relative_time_indicators) or \
                       any(re.search(pattern, now_part) for pattern in [r'\d+', r'\b(on|by|at)\b'])
        
        if has_date_info:
            # Use the "Now" part for date extraction
            text_for_parsing = now_part
        else:
            # No date info in "Now" part, extract date from the part before "now"
            # to preserve the existing date context
            before_now_part = original_text[:original_text.find(" now ")].strip() if " now " in original_text else original_text[:4].strip()
            
            # Extract date from the context before "now"
            if before_now_part:
                text_for_parsing = before_now_part
            else:
                # If no context before "now", return None to preserve existing dates
                return None if flight_type != "return" else (None, None)
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
    
    # ADDED: Handle negation patterns for dates
    if is_modification_query:
        negation_result = handle_date_negation(original_text, now_part)
        if negation_result:
            return negation_result
    
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
        if is_modification_query and has_date_info:
            # Check if the modification contains both departure and return information
            # Look for patterns like "travel from X to Y on [date] and return on [date]"
            combined_travel_pattern = r'travel\s+from\s+\w+\s+to\s+\w+\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+return\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)'
            combined_match = re.search(combined_travel_pattern, now_part)
            
            if combined_match:
                departure_date_str = combined_match.group(1).strip().lower()
                return_date_str = combined_match.group(2).strip().lower()
                
                # Parse departure date
                departure_result = None
                if departure_date_str in special_date_map:
                    departure_result = special_date_map[departure_date_str]
                else:
                    try:
                        cal = parsedatetime.Calendar()
                        time_struct, parse_status = cal.parse(departure_date_str)
                        if parse_status >= 1:
                            parsed_date = datetime(*time_struct[:6])
                            if is_valid_date(departure_date_str, parsed_date, today):
                                departure_result = parsed_date.strftime("%Y-%m-%d")
                            else:
                                print(f"❌ Invalid departure date detected: '{departure_date_str}'")
                    except Exception as e:
                        print(f"❌ Error parsing departure date '{departure_date_str}': {e}")
                
                # Parse return date
                return_result = None
                if return_date_str in special_date_map:
                    return_result = special_date_map[return_date_str]
                else:
                    # Try relative date parsing with departure date reference first
                    relative_result = parse_relative_date_with_reference(return_date_str, departure_result)
                    if relative_result:
                        return_result = relative_result
                    else:
                        # Fallback to normal parsedatetime parsing
                        try:
                            cal = parsedatetime.Calendar()
                            time_struct, parse_status = cal.parse(return_date_str)
                            if parse_status >= 1:
                                parsed_date = datetime(*time_struct[:6])
                                if is_valid_date(return_date_str, parsed_date, today):
                                    return_result = parsed_date.strftime("%Y-%m-%d")
                                else:
                                    print(f"❌ Invalid return date detected: '{return_date_str}'")
                        except Exception as e:
                            print(f"❌ Error parsing return date '{return_date_str}': {e}")
                
                # FIXED: Apply validation if both dates were parsed
                if departure_result and return_result:
                    departure_dt = datetime.strptime(departure_result, "%Y-%m-%d")
                    return_dt = datetime.strptime(return_result, "%Y-%m-%d")
                    
                    if return_dt < departure_dt:
                        print(f"⚠️  Return date {return_result} is before departure date {departure_result}.")
                        
                        # Check for impossible/unreasonable cases that should be rejected
                        today_date = today.strftime("%Y-%m-%d")
                        tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                        yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                        day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                        
                        # Only reject truly impossible cases - allow same-day returns
                        impossible_cases = [
                            # Basic impossible cases
                            (return_result == today_date and departure_result == tomorrow_date),
                            (return_result == yesterday_date and departure_result == today_date),
                            (return_result == yesterday_date and departure_result == tomorrow_date),
                            (return_result == yesterday_date and departure_result == day_after_tomorrow_date),
                            # Return tomorrow when departing day after tomorrow or later
                            (return_result == tomorrow_date and departure_dt >= datetime.strptime(day_after_tomorrow_date, "%Y-%m-%d")),
                            # Any return date that's more than 1 day before departure
                            (return_dt < departure_dt - timedelta(days=1)),
                            # Only reject if return is strictly before departure (not same day)
                            (return_dt < departure_dt),
                        ]
                        
                        if any(impossible_cases):
                            print(f"❌ Impossible: Cannot return on {return_result} if departing on {departure_result}. Setting return to None.")
                            return_result = None
                        else:
                            # Try to fix only very reasonable cases (day name shifts within a week)
                            original_return_day = None
                            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                            for day in day_names:
                                if day in return_date_str.lower():
                                    original_return_day = day
                                    break
                            
                            if original_return_day and return_dt < departure_dt and (departure_dt - return_dt).days <= 7:
                                # Only fix if it's within a week and has a day name
                                day_mapping = {
                                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                    'friday': 4, 'saturday': 5, 'sunday': 6
                                }
                                
                                target_weekday = day_mapping[original_return_day]
                                current_weekday = departure_dt.weekday()
                                
                                days_ahead = target_weekday - current_weekday
                                if days_ahead <= 0:
                                    days_ahead += 7
                                
                                next_occurrence = departure_dt + timedelta(days=days_ahead)
                                return_result = next_occurrence.strftime("%Y-%m-%d")
                                print(f"✅ Fixed return date to next {original_return_day}: {return_result}")
                            elif return_dt < departure_dt:
                                # Don't fix - set to None for unreasonable cases
                                print(f"❌ Cannot reasonably fix return date {return_result} before departure {departure_result}. Setting return to None.")
                                return_result = None
                
                return departure_result, return_result
            
            # Check for combined departure and return modifications
            combined_modification_patterns = [
                r'(?:i\s+)?(?:will\s+)?travel\s+([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?return\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
                r'(?:i\s+)?(?:will\s+)?depart\s+(?:on\s+)?([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?return\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
                r'(?:i\s+)?(?:will\s+)?go\s+(?:on\s+)?([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?return\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
                # ADDED: Pattern for "i will depart X days later and will come back Y days later"
                r'(?:i\s+)?(?:will\s+)?depart\s+([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?(?:come\s*back|comeback|return)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
                # ADDED: Pattern for "i will travel X days later and come back Y days later" (without "on")
                r'(?:i\s+)?(?:will\s+)?travel\s+([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?(?:come\s*back|comeback|return)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
                # ADDED: Pattern for "i will go to [place] from [place] X days later and come back Y days later"
                r'(?:i\s+)?(?:will\s+)?go\s+to\s+\w+\s+from\s+\w+\s+([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?(?:come\s*back|comeback|return)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
            ]
            
            for pattern in combined_modification_patterns:
                combined_match = re.search(pattern, now_part)
                if combined_match:
                    departure_date_str = combined_match.group(1).strip().lower()
                    return_date_str = combined_match.group(2).strip().lower()
                    
                    # Extract context from before "now" to preserve any existing dates if needed
                    before_now_part = original_text[:original_text.find(" now ")].strip() if " now " in original_text else ""
                    
                    # Get original dates from context for reference
                    context_departure = None
                    context_return = None
                    if before_now_part:
                        try:
                            context_dates = extract_dates(before_now_part, "return")
                            if isinstance(context_dates, tuple) and len(context_dates) == 2:
                                context_departure = context_dates[0]  # Original departure date
                                context_return = context_dates[1]     # Original return date
                            elif isinstance(context_dates, str):
                                context_departure = context_dates     # Single date from context
                        except:
                            pass
                    
                    # Parse departure date (use context departure as reference for relative dates)
                    new_departure_date = None
                    if departure_date_str in special_date_map:
                        new_departure_date = special_date_map[departure_date_str]
                    else:
                        # FIXED: Use original departure date as reference for relative expressions
                        relative_result = parse_relative_date_with_reference(departure_date_str, context_departure)
                        if relative_result:
                            new_departure_date = relative_result
                        else:
                            # Fallback to normal parsedatetime parsing
                            try:
                                cal = parsedatetime.Calendar()
                                time_struct, parse_status = cal.parse(departure_date_str)
                                if parse_status >= 1:
                                    parsed_date = datetime(*time_struct[:6])
                                    if is_valid_date(text, parsed_date, today):
                                        new_departure_date = parsed_date.strftime("%Y-%m-%d")
                            except Exception as e:
                                print(f"❌ Error parsing departure date '{departure_date_str}': {e}")
                    
                    # Parse return date (use new departure date as reference)
                    new_return_date = None
                    if return_date_str in special_date_map:
                        new_return_date = special_date_map[return_date_str]
                    else:
                        # Try relative date parsing with departure date reference first
                        relative_result = parse_relative_date_with_reference(return_date_str, new_departure_date)
                        if relative_result:
                            new_return_date = relative_result
                        else:
                            # Fallback to normal parsedatetime parsing
                            try:
                                cal = parsedatetime.Calendar()
                                time_struct, parse_status = cal.parse(return_date_str)
                                if parse_status >= 1:
                                    parsed_date = datetime(*time_struct[:6])
                                    if is_valid_date(text, parsed_date, today):
                                        new_return_date = parsed_date.strftime("%Y-%m-%d")
                            except Exception as e:
                                print(f"❌ Error parsing return date '{return_date_str}': {e}")
                    
                    # Apply validation if both dates were parsed
                    if new_departure_date and new_return_date:
                        departure_dt = datetime.strptime(new_departure_date, "%Y-%m-%d")
                        return_dt = datetime.strptime(new_return_date, "%Y-%m-%d")
                        
                        if return_dt < departure_dt:
                            print(f"⚠️  Return date {new_return_date} is before departure date {new_departure_date}.")
                            
                            # Check for impossible cases - allow same-day returns
                            today_date = today.strftime("%Y-%m-%d")
                            tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                            yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                            day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                            
                            impossible_cases = [
                                # Only reject if return is strictly before departure (not same day)
                                (return_dt < departure_dt),
                                # Return tomorrow when departing day after tomorrow or later  
                                (new_return_date == tomorrow_date and departure_dt >= datetime.strptime(day_after_tomorrow_date, "%Y-%m-%d")),
                            ]
                            
                            if any(impossible_cases):
                                print(f"❌ Impossible: Cannot return on {new_return_date} if departing on {new_departure_date}. Setting return to None.")
                                new_return_date = None
                            else:
                                # Only try to fix very reasonable cases (day name shifts within a week)
                                original_return_day = None
                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                for day in day_names:
                                    if day in return_date_str:
                                        original_return_day = day
                                        break
                                
                                if original_return_day:
                                    # Find the next occurrence of this day after departure date
                                    day_mapping = {
                                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                        'friday': 4, 'saturday': 5, 'sunday': 6
                                    }
                                    
                                    target_weekday = day_mapping[original_return_day]
                                    current_weekday = departure_dt.weekday()
                                    
                                    days_ahead = target_weekday - current_weekday
                                    if days_ahead <= 0:
                                        days_ahead += 7
                                    
                                    next_occurrence = departure_dt + timedelta(days=days_ahead)
                                    new_return_date = next_occurrence.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date to next {original_return_day}: {new_return_date}")
                                else:
                                    # Fallback: add 7 days
                                    next_week_return = return_dt + timedelta(days=7)
                                    new_return_date = next_week_return.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date by adding 7 days: {new_return_date}")
                    
                    return new_departure_date, new_return_date
            
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
                r'go\s+on\s+(.+)',
                r'travel\s+from\s+\w+\s+to\s+\w+\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',  # "travel from X to Y on [date]"
                r'travel\s+to\s+\w+\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',  # "travel to X on [date]"
                r'travel\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',  # "travel on [date]"
                r'(?:i\s+)?(?:will\s+)?travel\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',  # "i will travel [date]" 
                r'depart\s+(.+)',  # Added: "depart 3 days later to departure date"
                r'leave\s+(.+)'    # Added: "leave 3 days later to departure date"
            ]
            
            # Check for return date change
            for pattern in return_change_patterns:
                match = re.search(pattern, now_part)
                if match:
                    date_str = re.sub(r'\b(of|the)\b', '', match.group(1).strip().lower())
                    
                    # Extract context from before "now" to preserve departure date
                    before_now_part = original_text[:original_text.find(" now ")].strip() if " now " in original_text else ""
                    context_departure = None
                    
                    if before_now_part:
                        # Try to extract departure date from context
                        try:
                            context_dates = extract_dates(before_now_part, "return")
                            if isinstance(context_dates, tuple) and len(context_dates) == 2:
                                context_departure = context_dates[0]  # Get departure from context
                            elif isinstance(context_dates, str):
                                context_departure = context_dates  # Single date from context
                        except:
                            pass
                    
                    # Parse the new return date
                    new_return_date = None
                    if date_str in special_date_map:
                        new_return_date = special_date_map[date_str]
                    else:
                        # ADDED: Check if this is a relative date that references departure date
                        relative_result = parse_relative_date_with_reference(date_str, context_departure)
                        if relative_result:
                            new_return_date = relative_result
                        else:
                            # Fallback to normal parsedatetime parsing
                            try:
                                cal = parsedatetime.Calendar()
                                time_struct, parse_status = cal.parse(date_str)
                                if parse_status >= 1:
                                    parsed_date = datetime(*time_struct[:6])
                                    if is_valid_date(text, parsed_date, today):
                                        print(f"✅ Final parsed date: {parsed_date.strftime('%Y-%m-%d')} (today is {today.strftime('%Y-%m-%d')})")
                                        new_return_date = parsed_date.strftime("%Y-%m-%d")
                            except Exception as e:
                                print(f"❌ Error parsing return date '{date_str}': {e}")
                                pass
                    
                    # FIXED: Apply validation when modifying return date only
                    if new_return_date and context_departure:
                        departure_dt = datetime.strptime(context_departure, "%Y-%m-%d")
                        return_dt = datetime.strptime(new_return_date, "%Y-%m-%d")
                        
                        if return_dt < departure_dt:
                            print(f"⚠️  Return date {new_return_date} is before departure date {context_departure}.")
                            
                            # Check for impossible cases - allow same-day returns
                            today_date = today.strftime("%Y-%m-%d")
                            tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                            yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                            day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                            
                            impossible_cases = [
                                # Only reject if return is strictly before departure (not same day)
                                (return_dt < departure_dt),
                                # Return tomorrow when departing day after tomorrow or later  
                                (new_return_date == tomorrow_date and departure_dt >= datetime.strptime(day_after_tomorrow_date, "%Y-%m-%d")),
                            ]
                            
                            if any(impossible_cases):
                                print(f"❌ Impossible: Cannot return on {new_return_date} if departing on {context_departure}. Setting return to None.")
                                new_return_date = None
                            else:
                                # Only try to fix very reasonable cases (day name shifts within a week)
                                original_return_day = None
                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                for day in day_names:
                                    if day in date_str:
                                        original_return_day = day
                                        break
                                
                                if original_return_day:
                                    # Find the next occurrence of this day after departure date
                                    day_mapping = {
                                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                        'friday': 4, 'saturday': 5, 'sunday': 6
                                    }
                                    
                                    target_weekday = day_mapping[original_return_day]
                                    current_weekday = departure_dt.weekday()
                                    
                                    days_ahead = target_weekday - current_weekday
                                    if days_ahead <= 0:
                                        days_ahead += 7
                                    
                                    next_occurrence = departure_dt + timedelta(days=days_ahead)
                                    new_return_date = next_occurrence.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date to next {original_return_day}: {new_return_date}")
                                else:
                                    # Fallback: add 7 days
                                    next_week_return = return_dt + timedelta(days=7)
                                    new_return_date = next_week_return.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date by adding 7 days: {new_return_date}")
                    
                    return context_departure, new_return_date
            
            # Check for departure date change
            for pattern in departure_change_patterns:
                match = re.search(pattern, now_part)
                if match:
                    date_str = re.sub(r'\b(of|the)\b', '', match.group(1).strip().lower())
                    
                    # Extract context from before "now" to preserve return date
                    before_now_part = original_text[:original_text.find(" now ")].strip() if " now " in original_text else ""
                    context_return = None
                    
                    if before_now_part:
                        # Try to extract return date from context
                        try:
                            context_dates = extract_dates(before_now_part, "return")
                            if isinstance(context_dates, tuple) and len(context_dates) == 2:
                                context_return = context_dates[1]  # Get return from context
                        except:
                            pass
                    
                    # Parse the new departure date
                    new_departure_date = None
                    if date_str in special_date_map:
                        new_departure_date = special_date_map[date_str]
                    else:
                        # Get the original departure date for reference
                        original_departure = None
                        if before_now_part:
                            try:
                                context_dates = extract_dates(before_now_part, "return")
                                if isinstance(context_dates, tuple) and len(context_dates) == 2:
                                    original_departure = context_dates[0]  # Get original departure from context
                                elif isinstance(context_dates, str):
                                    original_departure = context_dates  # Single date from context
                            except:
                                pass
                        
                        # ADDED: Check if this is a relative date that references departure date
                        relative_result = parse_relative_date_with_reference(date_str, original_departure)
                        if relative_result:
                            new_departure_date = relative_result
                        else:
                            # Fallback to normal parsedatetime parsing
                            try:
                                cal = parsedatetime.Calendar()
                                time_struct, parse_status = cal.parse(date_str)
                                if parse_status >= 1:
                                    parsed_date = datetime(*time_struct[:6])
                                    if is_valid_date(text, parsed_date, today):
                                        new_departure_date = parsed_date.strftime("%Y-%m-%d")
                            except Exception as e:
                                print(f"❌ Error parsing departure date '{date_str}': {e}")
                                pass
                    
                    # FIXED: Apply validation when modifying departure date (this affects return date validation)
                    if new_departure_date and context_return:
                        departure_dt = datetime.strptime(new_departure_date, "%Y-%m-%d")
                        return_dt = datetime.strptime(context_return, "%Y-%m-%d")
                        
                        if return_dt < departure_dt:
                            print(f"⚠️  Return date {context_return} is before new departure date {new_departure_date}.")
                            
                            # Check for impossible cases - allow same-day returns
                            today_date = today.strftime("%Y-%m-%d")
                            tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                            yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                            day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                            
                            impossible_cases = [
                                # Only reject if return is strictly before departure (not same day)
                                (return_dt < departure_dt),
                                # Return tomorrow when departing day after tomorrow or later  
                                (context_return == tomorrow_date and departure_dt >= datetime.strptime(day_after_tomorrow_date, "%Y-%m-%d")),
                            ]
                            
                            if any(impossible_cases):
                                print(f"❌ Impossible: Cannot return on {context_return} if departing on {new_departure_date}. Setting return to None.")
                                context_return = None
                            elif return_dt < departure_dt and (departure_dt - return_dt).days <= 7:
                                # Only try to fix very reasonable cases (day name shifts within a week)
                                # Extract day name from original context
                                original_return_day = None
                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                for day in day_names:
                                    if day in before_now_part.lower():
                                        original_return_day = day
                                        break
                                
                                if original_return_day:
                                    # Find the next occurrence of this day after new departure date
                                    day_mapping = {
                                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                        'friday': 4, 'saturday': 5, 'sunday': 6
                                    }
                                    
                                    target_weekday = day_mapping[original_return_day]
                                    current_weekday = departure_dt.weekday()
                                    
                                    days_ahead = target_weekday - current_weekday
                                    if days_ahead <= 0:
                                        days_ahead += 7
                                    
                                    next_occurrence = departure_dt + timedelta(days=days_ahead)
                                    context_return = next_occurrence.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date to next {original_return_day}: {context_return}")
                                else:
                                    # Fallback: add 7 days to return date
                                    next_week_return = return_dt + timedelta(days=7)
                                    context_return = next_week_return.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date by adding 7 days: {context_return}")
                    
                    return new_departure_date, context_return
            
            # Fallback: Generic return date modification for "Now return [date]" patterns
            if not dates:  # Only if no specific patterns matched
                # Look for "return" or "comeback" followed by a date in the now_part - be more specific about departure references
                generic_return_pattern = r'(?:return|comeback|come\s*back)\s+(day after tomorrow|tomorrow|today|\d+(?:st|nd|rd|th)?\s*\w*|.+?\s+after\s+departure(?:\s+date)?|.+?\s+from\s+departure(?:\s+date)?|.+?\s+since\s+departure(?:\s+date)?)'
                return_match = re.search(generic_return_pattern, now_part.lower())
                
                if return_match:
                    date_str = return_match.group(1).strip()
                    
                    # Extract context from before "now" to preserve departure date
                    before_now_part = original_text[:original_text.find(" now ")].strip() if " now " in original_text else ""
                    context_departure = None
                    
                    if before_now_part:
                        try:
                            context_dates = extract_dates(before_now_part, "return")
                            if isinstance(context_dates, tuple) and len(context_dates) == 2:
                                context_departure = context_dates[0]  # Get departure from context
                            elif isinstance(context_dates, str):
                                context_departure = context_dates  # Single date from context
                        except:
                            pass
                    
                    # Parse the new return date
                    new_return_date = None
                    if date_str in special_date_map:
                        new_return_date = special_date_map[date_str]
                    else:
                        # ADDED: Check if this is a relative date that references departure date
                        relative_result = parse_relative_date_with_reference(date_str, context_departure)
                        if relative_result:
                            new_return_date = relative_result
                        else:
                            # Fallback to normal parsedatetime parsing
                            try:
                                cal = parsedatetime.Calendar()
                                time_struct, parse_status = cal.parse(date_str)
                                if parse_status >= 1:
                                    parsed_date = datetime(*time_struct[:6])
                                    if is_valid_date(text, parsed_date, today):
                                        new_return_date = parsed_date.strftime("%Y-%m-%d")
                            except:
                                pass
                    
                    # FIXED: Apply stricter validation for generic return date modification
                    if new_return_date and context_departure:
                        departure_dt = datetime.strptime(context_departure, "%Y-%m-%d")
                        return_dt = datetime.strptime(new_return_date, "%Y-%m-%d")
                        
                        if return_dt < departure_dt:
                            print(f"⚠️  Return date {new_return_date} is before departure date {context_departure}.")
                            
                            # Check for impossible cases - allow same-day returns
                            today_date = today.strftime("%Y-%m-%d")
                            tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                            yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                            day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                            
                            impossible_cases = [
                                # Only reject if return is strictly before departure (not same day)
                                (return_dt < departure_dt),
                                # Return tomorrow when departing day after tomorrow or later  
                                (new_return_date == tomorrow_date and departure_dt >= datetime.strptime(day_after_tomorrow_date, "%Y-%m-%d")),
                            ]
                            
                            if any(impossible_cases):
                                print(f"❌ Impossible: Cannot return on {new_return_date} if departing on {context_departure}. Setting return to None.")
                                new_return_date = None
                            else:
                                # Only try to fix very reasonable cases (day name shifts within a week)
                                original_return_day = None
                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                for day in day_names:
                                    if day in date_str.lower():
                                        original_return_day = day
                                        break
                                
                                if original_return_day and return_dt < departure_dt and (departure_dt - return_dt).days <= 7:
                                    # Find the next occurrence of this day after departure date
                                    day_mapping = {
                                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                        'friday': 4, 'saturday': 5, 'sunday': 6
                                    }
                                    
                                    target_weekday = day_mapping[original_return_day]
                                    current_weekday = departure_dt.weekday()
                                    
                                    days_ahead = target_weekday - current_weekday
                                    if days_ahead <= 0:
                                        days_ahead += 7
                                    
                                    next_occurrence = departure_dt + timedelta(days=days_ahead)
                                    new_return_date = next_occurrence.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date to next {original_return_day}: {new_return_date}")
                                else:
                                    # Don't fix - set to None for unreasonable cases
                                    print(f"❌ Cannot reasonably fix return date {new_return_date} before/same as departure {context_departure}. Setting return to None.")
                                    new_return_date = None
                                    # Fallback: add 7 days
                                    next_week_return = return_dt + timedelta(days=7)
                                    new_return_date = next_week_return.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date by adding 7 days: {new_return_date}")
                    
                    return context_departure, new_return_date
        
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
                departure = next((d for l, d in dates if l == 'departure'), None)
                return_date = next((d for l, d in dates if l == 'return'), None)
                
                # Apply validation before returning
                if departure and return_date:
                    departure_dt = datetime.strptime(departure, "%Y-%m-%d")
                    return_dt = datetime.strptime(return_date, "%Y-%m-%d")
                    
                    if return_dt < departure_dt:
                        # Check for impossible cases - allow same-day returns
                        today_date = today.strftime("%Y-%m-%d")
                        tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                        yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                        
                        impossible_cases = [
                            (return_date == today_date and departure == tomorrow_date),  # return today, depart tomorrow
                            (return_date == yesterday_date and departure == today_date),  # return yesterday, depart today
                            (return_date == yesterday_date and departure == tomorrow_date),  # return yesterday, depart tomorrow
                            # Only reject if return is strictly before departure (not same day)
                            (return_dt < departure_dt),
                        ]
                        
                        if any(impossible_cases):
                            print(f"❌ Impossible: Cannot return on {return_date} if departing on {departure}. Setting return to None.")
                            return_date = None
                        elif return_dt < departure_dt:
                            # Fix chronological order for weekdays
                            day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                            original_return_day = None
                            
                            for day in day_names:
                                if day in normalized_text and any(phrase in normalized_text for phrase in [
                                    f"return {day}", f"comeback {day}", f"back {day}", f"return on {day}", f"comeback on {day}"
                                ]):
                                    original_return_day = day
                                    break
                            
                            if original_return_day:
                                day_mapping = {
                                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                    'friday': 4, 'saturday': 5, 'sunday': 6
                                }
                                
                                target_weekday = day_mapping[original_return_day]
                                current_weekday = departure_dt.weekday()
                                
                                days_ahead = target_weekday - current_weekday
                                if days_ahead <= 0:
                                    days_ahead += 7
                                
                                next_occurrence = departure_dt + timedelta(days=days_ahead)
                                return_date = next_occurrence.strftime("%Y-%m-%d")
                                print(f"✅ Fixed return date to next {original_return_day}: {return_date}")
                            else:
                                # Fallback: add 7 days
                                next_week_return = return_dt + timedelta(days=7)
                                return_date = next_week_return.strftime("%Y-%m-%d")
                                print(f"✅ Fixed return date by adding 7 days: {return_date}")
                
                return departure, return_date

        # Strategy 2A: Special depart + comeback patterns with relative date support
        depart_comeback_patterns = [
            r'(?:i\s+)?(?:will\s+)?depart\s+on\s+([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?(?:come\s*back|comeback|return)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
            r'(?:i\s+)?(?:will\s+)?travel\s+(?:on\s+)?([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?(?:come\s*back|comeback|return)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
            r'(?:going|leaving)\s+(?:on\s+)?([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?(?:come\s*back|comeback|return)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
            # ADDED: Pattern for "i will go to [place] from [place] X days later and come back Y days later"
            r'(?:i\s+)?(?:will\s+)?go\s+to\s+\w+\s+from\s+\w+\s+([^,\s]+(?:\s+[^,\s]+)*?)\s+and\s+(?:will\s+)?(?:come\s*back|comeback|return)\s+([^,\s]+(?:\s+[^,\s]+)*?)(?:\s*,|\s*\.|\s*$)',
        ]
        
        for pattern in depart_comeback_patterns:
            matches = re.findall(pattern, normalized_text)
            for match in matches:
                if len(match) == 2:
                    departure_str, return_str = match
                    departure_str = departure_str.strip().lower()
                    return_str = return_str.strip().lower()
                    
                    # Skip if this looks like an age pattern
                    if any(re.search(r'\d+.*?(year|old|month)', m) for m in [departure_str, return_str]):
                        continue
                    
                    # Parse departure date
                    departure_result = None
                    if departure_str in special_date_map:
                        departure_result = special_date_map[departure_str]
                    else:
                        try:
                            cal = parsedatetime.Calendar()
                            time_struct, parse_status = cal.parse(departure_str)
                            if parse_status >= 1:
                                parsed_date = datetime(*time_struct[:6])
                                if is_valid_date(text, parsed_date, today):
                                    departure_result = parsed_date.strftime("%Y-%m-%d")
                        except:
                            pass
                    
                    # Parse return date with departure date as reference
                    return_result = None
                    if return_str in special_date_map:
                        return_result = special_date_map[return_str]
                    else:
                        # ENHANCED: Try relative date parsing with departure date reference first
                        if departure_result:
                            relative_result = parse_relative_date_with_reference(return_str, departure_result)
                            if relative_result:
                                return_result = relative_result
                        
                        # Fallback to normal parsedatetime parsing if relative parsing didn't work
                        if not return_result:
                            try:
                                cal = parsedatetime.Calendar()
                                time_struct, parse_status = cal.parse(return_str)
                                if parse_status >= 1:
                                    parsed_date = datetime(*time_struct[:6])
                                    if is_valid_date(text, parsed_date, today):
                                        return_result = parsed_date.strftime("%Y-%m-%d")
                            except:
                                pass
                    
                    # Apply stricter validation if both dates were parsed
                    if departure_result and return_result:
                        departure_dt = datetime.strptime(departure_result, "%Y-%m-%d")
                        return_dt = datetime.strptime(return_result, "%Y-%m-%d")
                        
                        if return_dt < departure_dt:
                            print(f"⚠️  Return date {return_result} is before departure date {departure_result}.")
                            
                            # Check for impossible cases - allow same-day returns
                            today_date = today.strftime("%Y-%m-%d")
                            tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                            yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                            day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                            
                            impossible_cases = [
                                # Only reject if return is strictly before departure (not same day)
                                (return_dt < departure_dt),
                                # Return tomorrow when departing day after tomorrow or later  
                                (return_result == tomorrow_date and departure_dt >= datetime.strptime(day_after_tomorrow_date, "%Y-%m-%d")),
                            ]
                            
                            if any(impossible_cases):
                                print(f"❌ Impossible: Cannot return on {return_result} if departing on {departure_result}. Setting return to None.")
                                return_result = None
                            else:
                                # Only try to fix very reasonable cases (day name shifts within a week)
                                original_return_day = None
                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                for day in day_names:
                                    if day in return_str.lower():
                                        original_return_day = day
                                        break
                                
                                if original_return_day and return_dt < departure_dt and (departure_dt - return_dt).days <= 7:
                                    # Find the next occurrence of this day after departure date
                                    day_mapping = {
                                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                        'friday': 4, 'saturday': 5, 'sunday': 6
                                    }
                                    
                                    target_weekday = day_mapping[original_return_day]
                                    current_weekday = departure_dt.weekday()
                                    
                                    days_ahead = target_weekday - current_weekday
                                    if days_ahead <= 0:
                                        days_ahead += 7
                                    
                                    next_occurrence = departure_dt + timedelta(days=days_ahead)
                                    return_result = next_occurrence.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date to next {original_return_day}: {return_result}")
                                else:
                                    # Don't fix - set to None for unreasonable cases
                                    print(f"❌ Cannot reasonably fix return date {return_result} before/same as departure {departure_result}. Setting return to None.")
                                    return_result = None
                    
                    if departure_result or return_result:
                        return departure_result, return_result

        # Strategy 2B: Date pair patterns (excluding age patterns)
        date_pair_patterns = [
            r'from\s+(\d+(?:st|nd|rd|th)?\s+\w+\s+\d{4})\s+to\s+(\d+(?:st|nd|rd|th)?\s+\w+\s+\d{4})',  # "from 1st September 2025 to 10th September 2025"
            r'from\s+(\d+(?:st|nd|rd|th)?\s+\w+)\s+to\s+(\d+(?:st|nd|rd|th)?\s+\w+)',  # "from 1st September to 10th September"
            r'\b(today|tomorrow|day after tomorrow)\b.*?\b(?:and\s+(?:then\s+)?|then\s+)\b.*?\b(today|tomorrow|day after tomorrow)\b',
            r'\bon\s+([^,]+?)\s+and\s+(?:then\s+)?(?:on\s+)?([^,]+?)(?:\s|$|,)',
            r'\b(\d+(?:st|nd|rd|th)?(?:\s+\w+)?)\s+(?:and\s+(?:then\s+)?|then\s+|to\s+)(?:on\s+)?(\d+(?:st|nd|rd|th)?(?:\s+\w+)?)(?:\s|$|,)',
            r'\b(today|tomorrow|day after tomorrow)\b.*?(?:and\s+)?back\s+on\s+([^,\.]+)',  # Fix for "tomorrow and back on [date]"
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
                                    if is_valid_date(text, parsed_date, today):
                                        dates.append((label, parsed_date.strftime("%Y-%m-%d")))
                            except:
                                pass
                if len(dates) >= 2:
                    departure = next((d for l, d in dates if l == 'departure'), None)
                    return_date = next((d for l, d in dates if l == 'return'), None)
                    
                    # Apply validation before returning
                    if departure and return_date:
                        departure_dt = datetime.strptime(departure, "%Y-%m-%d")
                        return_dt = datetime.strptime(return_date, "%Y-%m-%d")
                        
                        if return_dt < departure_dt:
                            print(f"⚠️  Return date {return_date} is before departure date {departure}.")
                            
                            # Check for clearly impossible cases that should be rejected - allow same-day returns
                            today_date = today.strftime("%Y-%m-%d")
                            tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                            yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                            day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                            
                            clearly_impossible_cases = [
                                # Return yesterday when departing today or later
                                (return_date == yesterday_date and departure_dt >= datetime.strptime(today_date, "%Y-%m-%d")),
                                # Return today when departing tomorrow or later
                                (return_date == today_date and departure_dt >= datetime.strptime(tomorrow_date, "%Y-%m-%d")),
                                # Only reject if return is strictly before departure (allow same-day returns)
                                (return_dt < departure_dt),
                            ]
                            
                            if any(clearly_impossible_cases):
                                print(f"❌ Clearly impossible: Cannot return on {return_date} if departing on {departure}. Setting return to None.")
                                return_date = None
                            elif return_dt < departure_dt:
                                # Try to fix reasonable cases - check if it's a weekday name issue
                                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                                original_return_day = None
                                
                                for day in day_names:
                                    if day in normalized_text and any(phrase in normalized_text for phrase in [
                                        f"return {day}", f"comeback {day}", f"back {day}", f"return on {day}", f"comeback on {day}"
                                    ]):
                                        original_return_day = day
                                        break
                                
                                if original_return_day:
                                    day_mapping = {
                                        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                                        'friday': 4, 'saturday': 5, 'sunday': 6
                                    }
                                    
                                    target_weekday = day_mapping[original_return_day]
                                    current_weekday = departure_dt.weekday()
                                    
                                    days_ahead = target_weekday - current_weekday
                                    if days_ahead <= 0:
                                        days_ahead += 7
                                    
                                    next_occurrence = departure_dt + timedelta(days=days_ahead)
                                    return_date = next_occurrence.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date to next {original_return_day}: {return_date}")
                                else:
                                    # Fallback: add 7 days
                                    next_week_return = return_dt + timedelta(days=7)
                                    return_date = next_week_return.strftime("%Y-%m-%d")
                                    print(f"✅ Fixed return date by adding 7 days: {return_date}")
                    
                    return departure, return_date

        # Strategy 3 & 4: Return and Departure Indicators
        indicator_patterns = [
            ("return", [
                r'(?:come\s+back|return|back).*?(?:on\s+|must\s+on\s+|by\s+)([^,\.]+)',
                r'(?:must\s+on|need\s+to\s+(?:come\s+)?back.*?on)\s+([^,\.]+)',
                r'(?:return.*?on|back.*?on)\s+([^,\.]+)',
                r'(?:returning)\s+([^,\.]+)',  # Added pattern for "returning [date]"
                r'(?:return)\s+([^,\.]+)',  # Added pattern for "return [date]" without "on"
                # ADDED: Pattern for "will return [relative time]" - these need departure date reference
                r'(?:will\s+return|returning)\s+([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s*,|\s*\.|\s*$)',
                r'(?:will\s+comeback|comeback)\s+([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s*,|\s*\.|\s*$)',  # Added pattern for "will comeback [relative time]"
            ]),
            ("departure", [
                r'(?:depart|leave|going|travel).*?(?:on\s+)([^,\.]+?)(?:\s+return|\s+and|,|\.|$)',
                r'(?:on\s+)([^,\.]+?)(?:\s+return|\s+and|,|\.|$).*?(?:going|travel|depart|leave)',
                r'(?:departing)\s+(?:on\s+)?([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+return|\s+and|\s*,|\s*\.|\s*$)',  # Stop at "return", "and", comma, period, or end
                r'(?:will\s+)?depart\s+(?:on\s+)?([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+return|\s+and|\s*,|\s*\.|\s*$)',  # Stop at "return", "and", comma, period, or end
                r'(?:i\s+)?(?:will\s+)?(?:be\s+)?departing\s+(?:on\s+)?([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+return|\s+and|\s*,|\s*\.|\s*$)',  # Stop at "return", "and", comma, period, or end
                r'(?:plan\s+to\s+)?depart\s+(?:on\s+)?([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+return|\s+and|\s*,|\s*\.|\s*$)',  # Stop at "return", "and", comma, period, or end
                # ADDED: Pattern for "travel [from] [city] [to] [city] [date]" without "on"
                r'(?:i\s+)?(?:will\s+)?travel\s+from\s+\w+\s+to\s+\w+\s+([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
                # ADDED: Pattern for "traveling [from] [city] [to] [city] [date]" (present continuous)
                r'(?:i\s+am\s+)?traveling\s+from\s+\w+\s+to\s+\w+\s+([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
                # ADDED: Pattern for "travel [to] [city] [date]" without "on"  
                r'(?:i\s+)?(?:will\s+)?travel\s+(?:to\s+)?\w+\s+([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
                # ADDED: Pattern for "traveling [to] [city] [date]" (present continuous)
                r'(?:i\s+am\s+)?traveling\s+(?:to\s+)?\w+\s+([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
                # ADDED: Pattern for general "traveling [date]" without specific cities
                r'(?:i\s+am\s+)?traveling\s+([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
                # FIXED: Added missing patterns for "go", "will go", and "fly"
                r'(?:i\s+)?(?:will\s+)?go\s+(?:from\s+\w+\s+to\s+\w+\s+)?(?:on\s+)?([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
                r'(?:i\s+)?(?:will\s+)?(?:be\s+)?going\s+(?:from\s+\w+\s+to\s+\w+\s+)?(?:on\s+)?([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
                r'(?:i\s+)?(?:will\s+)?fly\s+(?:from\s+\w+\s+to\s+\w+\s+)?(?:on\s+)?([^,\.\s]*(?:\s+[^,\.\s]*)*?)(?:\s+and|\s+return|\s*,|\s*\.|\s*$)',
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
                        # ENHANCED: For return dates, check if this is a relative expression that should use departure date as reference
                        if label == 'return':
                            # Check if we already have a departure date to use as reference
                            current_departure = next((d for l, d in dates if l == 'departure'), None)
                            
                            # Try relative date parsing with departure date reference first
                            relative_result = parse_relative_date_with_reference(date_str, current_departure)
                            if relative_result:
                                dates.append((label, relative_result))
                                continue
                        
                        # Fallback to normal parsedatetime parsing
                        try:
                            cal = parsedatetime.Calendar()
                            time_struct, parse_status = cal.parse(date_str)
                            if parse_status >= 1:
                                parsed_date = datetime(*time_struct[:6])
                                # FIXED: Ensure parsed date is reasonable
                                if is_valid_date(text, parsed_date, today):
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
        
        # ENHANCED: Second pass - if we have departure but return date seems to be relative, re-process it with departure reference
        if departure and return_date:
            # Check if we need to reprocess the return date with departure date reference
            # Look for the original return date string in the text to see if it was relative
            for label, patterns in indicator_patterns:
                if label == 'return':
                    for pattern in patterns:
                        matches = re.findall(pattern, normalized_text)
                        for match in matches:
                            if re.search(r'\d+.*?(year|old|month)', match):
                                continue
                            date_str = re.sub(r'\b(of|the)\b', '', match.strip().lower())
                            
                            # Check if this looks like a relative expression that should use departure date
                            relative_indicators = ['later', 'after', 'days', 'weeks', 'months']
                            if any(indicator in date_str for indicator in relative_indicators):
                                # Try to reparse with departure date reference
                                relative_result = parse_relative_date_with_reference(date_str, departure)
                                if relative_result and relative_result != return_date:
                                    return_date = relative_result
                                    break
        
        # ENHANCED: Validate return date logic - return must be after departure
        if departure and return_date:
            departure_dt = datetime.strptime(departure, "%Y-%m-%d")
            return_dt = datetime.strptime(return_date, "%Y-%m-%d")
            
            # Case 1: Return date is before departure date (allow same-day returns)
            if return_dt < departure_dt:
                print(f"⚠️  Return date {return_date} is before departure date {departure}.")
                
                # Check for clearly impossible cases that should be rejected - allow same-day returns
                today_date = today.strftime("%Y-%m-%d")
                tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                yesterday_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                day_after_tomorrow_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                
                clearly_impossible_cases = [
                    # Return yesterday when departing today or later
                    (return_date == yesterday_date and departure_dt >= datetime.strptime(today_date, "%Y-%m-%d")),
                    # Return today when departing tomorrow or later  
                    (return_date == today_date and departure_dt >= datetime.strptime(tomorrow_date, "%Y-%m-%d")),
                    # Only reject if return is strictly before departure (allow same-day returns)
                    (return_dt < departure_dt),
                ]
                
                if any(clearly_impossible_cases):
                    print(f"❌ Clearly impossible: Cannot return on {return_date} if departing on {departure}. Setting return to None.")
                    return_date = None
                elif return_dt < departure_dt:
                    # Try to fix reasonable cases - check if it's a weekday name issue
                    original_return_day = None
                    
                    # Look for day names in the return patterns
                    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    for day in day_names:
                        if day in normalized_text and any(phrase in normalized_text for phrase in [
                            f"return {day}", f"comeback {day}", f"back {day}", f"return on {day}", f"comeback on {day}"
                        ]):
                            original_return_day = day
                            break
                    
                    if original_return_day and (departure_dt - return_dt).days <= 7:
                        # Find the next occurrence of this day after the departure date
                        day_mapping = {
                            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                            'friday': 4, 'saturday': 5, 'sunday': 6
                        }
                        
                        target_weekday = day_mapping[original_return_day]
                        current_weekday = departure_dt.weekday()
                        
                        # Calculate days until next occurrence of target day
                        days_ahead = target_weekday - current_weekday
                        if days_ahead <= 0:  # Target day is same or before current day
                            days_ahead += 7  # Move to next week
                        
                        next_occurrence = departure_dt + timedelta(days=days_ahead)
                        return_date = next_occurrence.strftime("%Y-%m-%d")
                        print(f"✅ Fixed return date to next {original_return_day}: {return_date}")
                    else:
                        # Fallback: add 7 days to make it next week
                        next_week_return = return_dt + timedelta(days=7)
                        return_date = next_week_return.strftime("%Y-%m-%d")
                        print(f"✅ Fixed return date by adding 7 days: {return_date}")
        
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
                        if is_valid_date(text, parsed_date, today):
                            return parsed_date.strftime("%Y-%m-%d")
                except Exception as e:
                    print(f"❌ Error parsing '{date_phrase}': {e}")
                    pass

        # FIXED: Parse with age filtering - try to extract just the date part first
        # Extract specific date patterns to avoid context confusion
        specific_date_patterns = [
            r'on\s+(\d+(?:st|nd|rd|th)?\s+\w+)',  # "on 15th August"
            r'(\d+(?:st|nd|rd|th)?\s+\w+)',       # "15th August"
            r'(\w+\s+\d+(?:st|nd|rd|th)?)',       # "August 15th"
        ]
        
        date_part = None
        for pattern in specific_date_patterns:
            match = re.search(pattern, normalized_text)
            if match:
                date_part = match.group(1).strip()
                break
        
        # Try parsing the extracted date part first
        if date_part:
            try:
                cal = parsedatetime.Calendar()
                time_struct, parse_status = cal.parse(date_part)
                if parse_status >= 1:
                    parsed_date = datetime(*time_struct[:6])
                    # FIXED: Ensure the parsed date is reasonable (not affected by age mentions)
                    if is_valid_date(text, parsed_date, today):
                        return parsed_date.strftime("%Y-%m-%d")
            except Exception as e:
                print(f"❌ Date part parsing failed for '{date_part}': {e}")
                pass
        
        # Fallback to full text parsing
        try:
            cal = parsedatetime.Calendar()
            time_struct, parse_status = cal.parse(normalized_text)
            if parse_status >= 1:
                parsed_date = datetime(*time_struct[:6])
                # FIXED: Use proper validation instead of just year check
                if is_valid_date(text, parsed_date, today):
                    return parsed_date.strftime("%Y-%m-%d")
                else:
                    print(f"❌ Date rejected - invalid: {text} -> {parsed_date.strftime('%Y-%m-%d')}")
                    return None
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
    
    Args:
        query (str): User's travel query
    
    Returns:
        dict: Dictionary containing all extracted travel information
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
        # Only set to None if not a modification query - otherwise omit key to preserve existing value
        elif not (" now " in query.lower() or query.lower().strip().startswith("now ")):
            result["departure_date"] = None
        
        if return_date:
            result["return_date"] = return_date
        # Only set to None if not a modification query - otherwise omit key to preserve existing value
        elif not (" now " in query.lower() or query.lower().strip().startswith("now ")):
            result["return_date"] = None
    else:
        date = extract_dates(query, flight_type)
        if date:
            result["departure_date"] = date
        # Only set to None if not a modification query - otherwise omit key to preserve existing value
        elif not (" now " in query.lower() or query.lower().strip().startswith("now ")):
            result["departure_date"] = None
    
    # Extract passenger count
    try:
        passenger_counts = extract_passenger_count(query)
        result["passengers"] = passenger_counts
        
        # Also add total passenger count for convenience
        total_passengers = passenger_counts["adults"] + passenger_counts["children"] + passenger_counts["infants"]
        result["total_passengers"] = total_passengers
    except Exception as e:
        print(f"Warning: Passenger count extraction failed: {e}")
        # Fallback to default
        result["passengers"] = {"adults": 1, "children": 0, "infants": 0}
        result["total_passengers"] = 1
    print("debug", result)
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
