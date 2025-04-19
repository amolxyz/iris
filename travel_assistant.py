from typing import List, Optional, Dict, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
from agents import Agent, Runner, function_tool
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define our data models
class TravelDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Common fields
    confirmation_number: Optional[str] = Field(None, description="Booking confirmation number or ticket number")
    booking_status: Literal['confirmed', 'cancelled', 'pending'] = Field(default='confirmed', description="Status of the booking")
    price_paid: Optional[float] = Field(None, description="Amount paid for the booking")
    booking_date: Optional[str] = Field(None, description="When the booking was made")
    
    # Flight specific
    flight_number: Optional[str] = Field(None, description="Flight number (e.g., 'AA123')")
    departure_airport: Optional[str] = Field(None, description="Departure airport code")
    arrival_airport: Optional[str] = Field(None, description="Arrival airport code")
    airline: Optional[str] = Field(None, description="Airline name")
    
    # Hotel specific
    hotel_name: Optional[str] = Field(None, description="Name of the hotel")
    room_type: Optional[str] = Field(None, description="Type of room booked")
    check_in_time: Optional[str] = Field(None, description="Check-in time")
    check_out_time: Optional[str] = Field(None, description="Check-out time")
    
    # Activity specific
    activity_name: Optional[str] = Field(None, description="Name of the activity")
    location: Optional[str] = Field(None, description="Location of the activity or venue")
    ticket_type: Optional[str] = Field(None, description="Type of ticket or admission")

class TravelItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['flight', 'hotel', 'activity'] = Field(..., description="Type of travel item")
    description: str = Field(..., description="Description of the travel item")
    start_time: str = Field(..., description="Start time of the travel item")
    end_time: Optional[str] = Field(None, description="End time of the travel item")
    details: TravelDetails = Field(..., description="Specific details of the travel item")

class Trip(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: str = Field(..., description="ID of the user")
    items: List[TravelItem] = Field(default_factory=list, description="List of travel items")

# Simple file-based storage
class TravelStore:
    def __init__(self, file_path="travel_data.json"):
        self.file_path = file_path
        self.data = self._load_data()

    def _load_data(self) -> dict:
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as f:
                return json.load(f)
        return {"trips": {}}

    def _save_data(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, default=str)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime, handling both naive and aware datetimes."""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.replace(tzinfo=None)  # Make naive
        except Exception:
            return datetime.now()  # Fallback to current time if parsing fails

    def _is_same_booking(self, item1: dict, item2: dict) -> bool:
        """Compare two travel items to check if they're the same booking."""
        details1 = item1.get('details', {})
        details2 = item2.get('details', {})
        
        # If both have confirmation numbers, compare those
        if details1.get('confirmation_number') and details2.get('confirmation_number'):
            return details1['confirmation_number'] == details2['confirmation_number']
        
        # Otherwise compare key details based on type
        if item1['type'] != item2['type']:
            return False
            
        if item1['type'] == 'flight':
            return (
                details1.get('flight_number') == details2.get('flight_number') and
                details1.get('departure_airport') == details2.get('departure_airport') and
                details1.get('arrival_airport') == details2.get('arrival_airport') and
                item1.get('start_time') == item2.get('start_time')
            )
        elif item1['type'] == 'hotel':
            return (
                details1.get('hotel_name') == details2.get('hotel_name') and
                item1.get('start_time') == item2.get('start_time') and
                item1.get('end_time') == item2.get('end_time')
            )
        elif item1['type'] == 'activity':
            return (
                details1.get('activity_name') == details2.get('activity_name') and
                details1.get('location') == details2.get('location') and
                item1.get('start_time') == item2.get('start_time')
            )
        return False

    def add_travel_item(self, user_id: str, item: TravelItem) -> dict:
        """Add or update a travel item, handling cancellations and updates."""
        if user_id not in self.data["trips"]:
            self.data["trips"][user_id] = []
        
        item_dict = item.model_dump()
        existing_trips = self.data["trips"][user_id]
        
        # Check for existing booking
        for i, existing_item in enumerate(existing_trips):
            if self._is_same_booking(existing_item, item_dict):
                # If new item is cancelled, update status of existing item
                if item_dict.get('details', {}).get('booking_status') == 'cancelled':
                    existing_item['details']['booking_status'] = 'cancelled'
                    self._save_data()
                    return {"status": "cancelled", "item": existing_item}
                
                # If existing item is not cancelled, update it
                if existing_item.get('details', {}).get('booking_status') != 'cancelled':
                    existing_trips[i] = item_dict
                    self._save_data()
                    return {"status": "updated", "item": item_dict}
                
                # If existing item is cancelled but new one isn't, treat as new booking
                if existing_item.get('details', {}).get('booking_status') == 'cancelled':
                    continue
        
        # Add as new item
        self.data["trips"][user_id].append(item_dict)
        self._save_data()
        return {"status": "added", "item": item_dict}

    def get_user_trips(self, user_id: str, include_past: bool = False, include_cancelled: bool = False) -> List[dict]:
        """Get user's trips, with options to include past and cancelled items."""
        try:
            all_trips = self.data["trips"].get(user_id, [])
            filtered_trips = []
            now = datetime.now().replace(tzinfo=None)  # Make naive
            
            for trip in all_trips:
                # Skip cancelled items unless specifically requested
                if not include_cancelled and trip.get('details', {}).get('booking_status') == 'cancelled':
                    continue
                    
                # Skip past items unless specifically requested
                if not include_past:
                    trip_time = self._parse_date(trip['start_time'])
                    if trip_time <= now:
                        continue
                
                filtered_trips.append(trip)
            
            return filtered_trips
            
        except Exception as e:
            print(f"Error retrieving trips: {str(e)}")
            return []

# Initialize our storage
store = TravelStore()

# Define our tools
@function_tool
def store_travel_item(
    user_id: str,
    item_type: Literal['flight', 'hotel', 'activity'],
    description: str,
    start_time: str,
    end_time: Optional[str] = None,
    confirmation_number: Optional[str] = None,
    booking_status: Literal['confirmed', 'cancelled', 'pending'] = 'confirmed',
    price_paid: Optional[float] = None,
    # Flight details
    flight_number: Optional[str] = None,
    departure_airport: Optional[str] = None,
    arrival_airport: Optional[str] = None,
    airline: Optional[str] = None,
    # Hotel details
    hotel_name: Optional[str] = None,
    room_type: Optional[str] = None,
    check_in_time: Optional[str] = None,
    check_out_time: Optional[str] = None,
    # Activity details
    activity_name: Optional[str] = None,
    location: Optional[str] = None,
    ticket_type: Optional[str] = None
) -> dict:
    """Store a travel item for a user."""
    try:
        details = TravelDetails(
            confirmation_number=confirmation_number,
            booking_status=booking_status,
            price_paid=price_paid,
            flight_number=flight_number,
            departure_airport=departure_airport,
            arrival_airport=arrival_airport,
            airline=airline,
            hotel_name=hotel_name,
            room_type=room_type,
            check_in_time=check_in_time,
            check_out_time=check_out_time,
            activity_name=activity_name,
            location=location,
            ticket_type=ticket_type
        )
        
        item = TravelItem(
            type=item_type,
            description=description,
            details=details,
            start_time=start_time,
            end_time=end_time
        )
        store.add_travel_item(user_id, item)
        return {"status": "success", "item": item.model_dump()}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

@function_tool
def get_user_itinerary(
    user_id: str = Field(..., description="ID of the user"),
    include_past: bool = Field(False, description="Whether to include past items"),
    include_cancelled: bool = Field(False, description="Whether to include cancelled items")
) -> List[dict]:
    """Get travel items for a user with options to include past and cancelled items."""
    return store.get_user_trips(user_id, include_past, include_cancelled)

# Create our specialized agents
email_parser = Agent(
    name="Email Parser",
    instructions="""You are an expert at parsing travel-related emails.
    Extract key information like flight details, hotel bookings, and activities.
    When you find travel information, use store_travel_item to save it.
    
    IMPORTANT RULES:
    1. Only process CONFIRMED bookings with a valid confirmation/ticket number
    2. Skip any promotional emails or price tracking
    3. Skip any cancelled bookings
    4. Only process future travel items
    5. For activities, only save those with actual tickets/bookings
    
    For flights, extract:
    - Flight number and airline
    - Departure/arrival airports
    - Exact times
    - Confirmation number
    - Booking status (confirmed/cancelled)
    - Price paid if available
    
    For hotels, extract:
    - Hotel name
    - Exact check-in/out dates and times
    - Confirmation number
    - Room type
    - Price paid if available
    
    For activities, ONLY extract if there's a confirmed booking:
    - Activity name
    - Exact date and time
    - Location
    - Ticket/booking reference
    - Ticket type
    - Price paid if available
    
    DO NOT process:
    - Price alerts or deals
    - Wishlists or saved items
    - Past travel items
    - Cancelled bookings
    - Activities without a booking confirmation""",
    tools=[store_travel_item]
)

itinerary_manager = Agent(
    name="Itinerary Manager",
    instructions="""You help manage and organize travel itineraries.
    You can retrieve travel information and present it in a clear, organized way.
    Consider time zones and travel duration when organizing schedules.
    
    When presenting information:
    1. Only show upcoming, confirmed travel items
    2. Group items by type (flights, hotels, activities)
    3. Sort chronologically
    4. Include confirmation numbers and important details
    5. Skip any cancelled items
    6. Highlight any scheduling conflicts
    
    Format the output in a clear, easy-to-read way with:
    - Dates and times
    - Confirmation numbers
    - Important details like flight numbers or hotel names
    - Prices when available""",
    tools=[get_user_itinerary]
)

# Main travel assistant that coordinates between agents
travel_assistant = Agent(
    name="Travel Assistant",
    instructions="""You are a helpful travel assistant that:
    1. Processes travel emails to extract important information
    2. Only saves confirmed bookings with valid confirmation numbers
    3. Skips promotional emails and unconfirmed activities
    4. Manages upcoming travel itineraries
    5. Provides helpful updates about confirmed travel plans
    
    Use the email parser agent for processing emails and the itinerary manager
    for organizing travel information.
    
    Be friendly and helpful in your responses, but be strict about only
    processing actual confirmed bookings.""",
    handoffs=[email_parser, itinerary_manager]
)

# Helper functions for common operations
async def process_travel_email(user_id: str, email_content: str):
    """Process a travel-related email and store relevant information."""
    result = await Runner.run(
        email_parser,
        f"""Process this email for user {user_id}. Remember:
        - Only extract CONFIRMED bookings with confirmation numbers
        - Skip promotional or tracking emails
        - Skip cancelled bookings
        - Only process future travel items
        - For activities, only save those with actual tickets
        
        Email content:
        {email_content}"""
    )
    return result.final_output

async def get_travel_summary(user_id: str):
    """Get a summary of upcoming travel items for a user."""
    result = await Runner.run(
        itinerary_manager,
        f"Please provide a summary of all upcoming, confirmed travel items for user {user_id}"
    )
    return result.final_output

# Example usage
async def main():
    # Example email
    email_content = """
    Confirmation of your flight booking
    
    Dear Traveler,
    
    Your flight has been confirmed:
    Flight: AA123
    From: New York (JFK)
    To: San Francisco (SFO)
    Date: June 15, 2024
    Departure: 10:00 AM EST
    Arrival: 1:30 PM PST
    
    Confirmation number: XYZ789
    """
    
    # Process the email
    user_id = "user123"
    await process_travel_email(user_id, email_content)
    
    # Get a summary of the user's travel items
    summary = await get_travel_summary(user_id)
    print("\nTravel Summary:")
    print(summary)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 