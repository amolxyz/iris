from travel_assistant import process_travel_email, get_travel_summary
import asyncio

# Sample travel emails
emails = [
    # Flight confirmation
    """
    Flight Confirmation - American Airlines
    
    Dear Traveler,
    
    Your flight has been confirmed:
    Flight: AA456
    From: Los Angeles (LAX)
    To: Chicago (ORD)
    Date: July 20, 2024
    Departure: 8:15 AM PDT
    Arrival: 2:45 PM CDT
    
    Confirmation number: ABC123
    Seat: 12A
    """,
    
    # Hotel booking
    """
    Hotel Booking Confirmation
    
    Dear Guest,
    
    Thank you for choosing The Grand Hotel Chicago!
    
    Booking Details:
    - Hotel: The Grand Hotel Chicago
    - Check-in: July 20, 2024, 3:00 PM
    - Check-out: July 23, 2024, 11:00 AM
    - Room Type: Deluxe King
    - Confirmation #: HOTEL789
    - Address: 123 Michigan Avenue, Chicago, IL 60601
    
    We look forward to your stay!
    """,
    
    # Activity booking
    """
    Activity Confirmation - Chicago Architecture Tour
    
    Hello!
    
    Your booking for the Chicago Architecture River Cruise has been confirmed.
    
    Details:
    - Tour: Chicago Architecture River Cruise
    - Date: July 21, 2024
    - Time: 2:00 PM
    - Duration: 1.5 hours
    - Location: Navy Pier, Chicago
    - Booking Reference: TOUR456
    
    Please arrive 15 minutes before departure.
    """,
    
    # Car rental
    """
    Car Rental Confirmation - Enterprise
    
    Thank you for choosing Enterprise!
    
    Rental Details:
    - Pick-up Location: Chicago O'Hare Airport
    - Pick-up Date: July 20, 2024, 3:00 PM
    - Return Date: July 23, 2024, 11:00 AM
    - Vehicle: Toyota Camry
    - Confirmation #: CAR123
    
    Please bring your driver's license and credit card.
    """
]

async def test_emails():
    user_id = "test_user"
    
    print("Processing travel emails...\n")
    
    # Process each email
    for i, email in enumerate(emails, 1):
        print(f"\nProcessing Email {i}...")
        result = await process_travel_email(user_id, email)
        print(f"Result: {result}\n")
    
    # Get final summary
    print("\nGetting final travel summary...")
    summary = await get_travel_summary(user_id)
    print("\nFinal Travel Summary:")
    print(summary)

if __name__ == "__main__":
    asyncio.run(test_emails()) 