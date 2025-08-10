# Extractor Test Cases

## Test Case 1: Conversational Flight Booking

```
(knowledge_base) nouman@Bookmes-MacBook-Pro-2 knowledge_base % python terminal_ui.py

======================================================================
✈️  CONVERSATIONAL TRAVEL ASSISTANT  ✈️
======================================================================
Hey there! I'm your personal travel assistant. Let's chat about your trip!


[00:08] Travel Assistant:
  Hello! I'm your travel assistant, and I'm excited to help you find the perfect flight! ✈️ Tell me about your travel plans - where would you like to go?

 You:
➤ Lahorre to karachi tommorrow 

[00:08] You:
  Lahorre to karachi tommorrow
 Selected tool: flight_search_and_extraction_tool
debug {'source': None, 'destination': 'KHI', 'flight_type': 'one_way', 'flight_class': 'economy', 'departure_date': '2025-08-12', 'passengers': {'adults': 1, 'children': 0, 'infants': 0}, 'total_passengers': 1}

[00:08] Travel Assistant:
  So, you're looking to travel from Lahore to Karachi tomorrow. I've got your travel details here: you're heading to Karachi, departing on August 12, 2025, in economy class, and you're traveling alone.

  The only thing I need to confirm is your departure city, which I assume is Lahore, but I just want to make sure. Can you confirm that you're flying out of Lahore? 

  Once I have that, I can start searching for flights for you!


 You:
➤ come back after week 

[00:08] You:
  come back after week
 Selected tool: flight_search_and_extraction_tool
 Contextual query created: go to KHI with 1 adult departing on 2025-08-12 in economy class one way. NOW USER SAYS :come back after week
 Groq LLM simplified query: Here is the simplified travel query:

'I need a flight from KHI to KHI departing 2025-08-12 and returning after 7 days, with 1 adult, one way initially but now return is required.'
✅ Parsed 'after 7 days' relative to 2025-08-11 = 2025-08-18
✅ Parsed 'after 7 days' relative to 2025-08-11 = 2025-08-18
 Using departure date 2025-08-12 as reference for 'after 7 days'
✅ Parsed 'after 7 days' relative to 2025-08-12 = 2025-08-19
 Using departure date 2025-08-12 as reference for 'after 7 days'
✅ Parsed 'after 7 days' relative to 2025-08-12 = 2025-08-19
debug {'source': None, 'destination': None, 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-12', 'return_date': '2025-08-19', 'passengers': {'adults': 1, 'children': 0, 'infants': 0}, 'total_passengers': 1}

[00:08] Travel Assistant:
  So, you're planning to head to Karachi and then come back after a week. I've got your travel details here: you're heading to Karachi, departing on August 12, 2025, and returning on August 19, 2025, in economy class, and you're traveling alone.

  Just to confirm, you're flying out of Lahore, correct? Once I have that confirmed, I can start searching for flights for you!


 You:
➤ lahore to karachi and come back after 3 days obny  

[00:09] You:
  lahore to karachi and come back after 3 days obny
 Selected tool: flight_search_and_extraction_tool
 Contextual query created: go to KHI with 1 adult departing on 2025-08-12 returning on 2025-08-19 in economy class round trip. NOW USER SAYS :lahore to karachi and come back after 3 days obny
 Groq LLM simplified query: Here is the simplified query:

'I need a flight from Lahore to Karachi departing today and returning after 3 days, with 1 adult.'
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
 Using departure date 2025-08-11 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
 Using departure date 2025-08-11 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
debug {'source': 'LHE', 'destination': 'KHI', 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-11', 'return_date': '2025-08-14', 'passengers': {'adults': 1, 'children': 0, 'infants': 0}, 'total_passengers': 1}

[00:09] Travel Assistant:
  Here's a friendly confirmation message:

  "Great, I've got your travel details! You're all set to search for flights from LHE to KHI on Aug 11-14 in economy class. Are you ready to look for your perfect flight options?"

[00:09] Travel Assistant:
   **Quick Summary:**
  ✈️ LHE → KHI
   Round-trip • departing 2025-08-11 • returning 2025-08-14
   1 adult(s) • Economy


 You:
➤ departure tomorrow 

[00:09] You:
  departure tomorrow
 Selected tool: flight_search_and_extraction_tool
 Contextual query created: travel from LHE to KHI with 1 adult departing on 2025-08-11 returning on 2025-08-14 in economy class round trip. NOW USER SAYS :departure tomorrow
 Groq LLM simplified query: Here is the simplified query:

'I need a flight from LHE to KHI departing tomorrow and returning after 3 days, with 1 adult.'
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
 Using departure date 2025-08-12 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-12 = 2025-08-15
 Using departure date 2025-08-12 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-12 = 2025-08-15
debug {'source': 'LHE', 'destination': 'KHI', 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-12', 'return_date': '2025-08-15', 'passengers': {'adults': 1, 'children': 0, 'infants': 0}, 'total_passengers': 1}

[00:10] Travel Assistant:
  Here's a friendly confirmation message:

  "Great, I've got your travel details! You're all set to search for flights from LHE to KHI on Aug 12-15 in economy class. Are you ready to look for options and find the perfect flight for you?"


 You:
➤ change departure to week later 

[00:11] You:
  change departure to week later
 Contextual query created: travel from LHE to KHI with 1 adult departing on 2025-08-12 returning on 2025-08-15 in economy class round trip. NOW USER SAYS :change departure to week later
 Groq LLM simplified query: Here is the simplified query:

'I need a flight from LHE to KHI departing in 7 days and returning after 3 days, with 1 adult.'
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
 Using departure date 2025-08-18 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-18 = 2025-08-21
 Using departure date 2025-08-18 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-18 = 2025-08-21
debug {'source': 'LHE', 'destination': 'KHI', 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-18', 'return_date': '2025-08-21', 'passengers': {'adults': 1, 'children': 0, 'infants': 0}, 'total_passengers': 1}

[00:11] Travel Assistant:
  So, you want to change the departure to a week later. I've got your updated travel details. You're now looking to travel from LHE to KHI, departing on August 18th and returning on August 21st in economy class. Just to make sure, you're still traveling alone, right? Let's see what flight options we can find for you!


 You:
➤ change the departure to 3 days later now and also i have my wife , kid along   

[00:16] You:
  change the departure to 3 days later now and also i have my wife , kid along
 Contextual query created: travel from LHE to KHI with 1 adult departing on 2025-08-18 returning on 2025-08-21 in economy class round trip. NOW USER SAYS :change the departure to 3 days later now and also i have my wife , kid along
 Groq LLM simplified query: Here is the simplified travel query:

'I need a flight from LHE to KHI departing in 3 days (August 21, 2025) and returning after 3 days, with 2 adults, 1 child, and 0 infants.'

Let me know if you'd like me to help with anything else!
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
 Using departure date 2025-08-14 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-14 = 2025-08-17
 Using departure date 2025-08-14 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-14 = 2025-08-17
debug {'source': 'LHE', 'destination': 'KHI', 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-14', 'return_date': '2025-08-17', 'passengers': {'adults': 2, 'children': 1, 'infants': 0}, 'total_passengers': 3}

[00:16] Travel Assistant:
  I've got your updated travel details. You're looking to travel from Lahore to Karachi with your wife and kid. Just to confirm, you're departing on August 14th and returning on August 17th in economy class, right? Let's see what flight options we can find for you!


 You:
➤ 3 days later than previous departure  

[00:17] You:
  3 days later than previous departure
 Selected tool: flight_search_and_extraction_tool
 Contextual query created: travel from LHE to KHI with 2 adults and 1 child departing on 2025-08-14 returning on 2025-08-17 in economy class round trip. NOW USER SAYS :3 days later than previous departure
 Groq LLM simplified query: Here is the simplified travel query:

'I need a flight from LHE to KHI departing 3 days later than 2025-08-14 and returning after 3 days, with 2 adults, 1 child and 0 infants.'

Let me know if you need any further assistance!
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
✅ Parsed 'after 3 days' relative to 2025-08-11 = 2025-08-14
 Using departure date 2025-08-14 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-14 = 2025-08-17
 Using departure date 2025-08-14 as reference for 'after 3 days'
✅ Parsed 'after 3 days' relative to 2025-08-14 = 2025-08-17
debug {'source': 'LHE', 'destination': 'KHI', 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-14', 'return_date': '2025-08-17', 'passengers': {'adults': 2, 'children': 1, 'infants': 0}, 'total_passengers': 3}

[00:17] Travel Assistant:
  Here's a friendly confirmation message:

  "Great, I've got your travel details! You're all set to search for flights from LHE to KHI for 3 passengers, economy class, on Aug 14-17, 2025. Are you ready to look for options and find the perfect flights?"

[00:17] Travel Assistant:
   **Quick Summary:**
  ✈️ LHE → KHI
   Round-trip • departing 2025-08-14 • returning 2025-08-17
   3 passengers • Economy


 You:
➤ I mean on 17th and come back 2 days later 

[00:20] You:
  I mean on 17th and come back 2 days later
 Selected tool: flight_search_and_extraction_tool
 Contextual query created: travel from LHE to KHI with 2 adults and 1 child departing on 2025-08-14 returning on 2025-08-17 in economy class round trip. NOW USER SAYS :I mean on 17th and come back 2 days later
 Groq LLM simplified query: Here is the simplified travel query:

'I need a flight from LHE to KHI departing on August 17th and returning after 2 days, with 2 adults and 1 child.'

Let me know if you need any further assistance!
 Using departure date 2025-08-17 as reference for 'after 2 days'
✅ Parsed 'after 2 days' relative to 2025-08-17 = 2025-08-19
 Using departure date 2025-08-17 as reference for 'after 2 days'
✅ Parsed 'after 2 days' relative to 2025-08-17 = 2025-08-19
 Using departure date 2025-08-17 as reference for 'after 2 days'
✅ Parsed 'after 2 days' relative to 2025-08-17 = 2025-08-19
 Using departure date 2025-08-17 as reference for 'after 2 days'
✅ Parsed 'after 2 days' relative to 2025-08-17 = 2025-.08-19
debug {'source': 'LHE', 'destination': 'KHI', 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-17', 'return_date': '2025-08-19', 'passengers': {'adults': 2, 'children': 1, 'infants': 0}, 'total_passengers': 3}

[00:20] Travel Assistant:
  Here's a friendly confirmation message:

  "Great, I've got your travel details! You're all set to search for flights from LHE to KHI for 3 passengers on Aug 17-19 in economy. Are you ready to look for options and find the perfect flights?"


 You:
➤ change the departure to 3 days before 

[00:25] You:
  change the departure to 3 days before
 Contextual query created: travel from LHE to KHI with 2 adults and 1 child departing on 2025-08-17 returning on 2025-08-19 in economy class round trip. NOW USER SAYS :change the departure to 3 days before
 Groq LLM simplified query: Here is the simplified travel query:

'I need a flight from LHE to KHI departing 3 days before 2025-08-17 and returning after 2 days, with 2 adults and 1 child.'

Let me break it down:

* SOURCE: LHE
* DESTINATION: KHI
* DEPARTURE: 3 days before 2025-08-17 (which is 2025-08-14)
* RETURN: after 2 days (which is 2025-08-16)
* PASSENGERS: 2 adults and 1 child
✅ Parsed 'after 2 days' relative to 2025-08-11 = 2025-08-13
✅ Parsed 'after 2 days' relative to 2025-08-11 = 2025-08-13
 Using departure date 2025-08-14 as reference for 'after 2 days'
✅ Parsed 'after 2 days' relative to 2025-08-14 = 2025-08-16
 Using departure date 2025-08-14 as reference for 'after 2 days'
✅ Parsed 'after 2 days' relative to 2025-08-14 = 2025-08-16
debug {'source': 'LHE', 'destination': 'KHI', 'flight_type': 'return', 'flight_class': 'economy', 'departure_date': '2025-08-14', 'return_date': '2025-08-16', 'passengers': {'adults': 2, 'children': 1, 'infants': 0}, 'total_passengers': 3}

[00:25] Travel Assistant:
  So, I've got your travel details updated. You're looking to travel from Lahore (LHE) to Karachi (KHI) with 2 adults and 1 child in economy class. Your new travel dates are August 14th for departure and August 16th for return, 2025. 

  Shall we start looking for some great flight options for you?


 You:
➤ 
```
