from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import pickle
import base64
from email.mime.text import MIMEText
import re
from typing import List, Dict, Optional, Tuple
from travel_assistant import process_travel_email, get_travel_summary
import asyncio
from datetime import datetime, timedelta
import dateutil.parser
from dateutil.tz import tzlocal
import pytz

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Travel-related keywords and patterns
TRAVEL_KEYWORDS = {
    'booking_indicators': [
        'confirmation', 'confirmed', 'e-ticket', 'electronic ticket',
        'booking reference', 'reservation number', 'itinerary', 'check-in',
        'boarding pass', 'travel document'
    ],
    'exclusion_words': [
        'deal', 'deals', 'offer', 'offers', 'sale', 'track', 'tracking',
        'price alert', 'price drop', 'newsletter', 'subscription',
        'marketing', 'promotional', 'promo', 'discount', 'past'
    ],
    'transportation': [
        'flight', 'airline', 'boarding pass',
        'train', 'rail', 'bus', 'cruise', 'ferry',
        'car rental', 'rental car', 'shuttle'
    ],
    'accommodation': [
        'hotel', 'reservation', 'check-in',
        'checkout', 'room', 'suite', 'hostel', 'bnb'
    ],
    'activities': [
        'tour', 'activity', 'excursion', 'attraction',
        'museum', 'park', 'show', 'event', 'ticket'
    ]
}

# Date patterns to look for in emails
DATE_PATTERNS = [
    # Common date formats
    r'(?:departure|arrival|check-?in|check-?out|date):\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})',
    r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s*(?:at|@)?\s*(\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?)',
    r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}',
    # ISO format
    r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?',
    # Natural language
    r'(?:tomorrow|next (?:week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday))',
]

def extract_dates(text: str) -> List[datetime]:
    """Extract all dates from text and return them as datetime objects."""
    dates = []
    now = datetime.now(tzlocal())
    
    for pattern in DATE_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                # Try to parse the date string
                date_str = match.group(0)
                
                # Handle natural language dates
                if 'tomorrow' in date_str.lower():
                    dates.append(now + timedelta(days=1))
                    continue
                elif 'next' in date_str.lower():
                    if 'week' in date_str.lower():
                        dates.append(now + timedelta(days=7))
                    elif 'month' in date_str.lower():
                        dates.append(now + timedelta(days=30))
                    else:  # next day of week
                        day = date_str.lower().split()[-1]
                        days_ahead = {'monday': 0, 'tuesday': 1, 'wednesday': 2,
                                    'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
                        today = now.weekday()
                        days_until = days_ahead[day] - today
                        if days_until <= 0:
                            days_until += 7
                        dates.append(now + timedelta(days=days_until))
                    continue
                
                # Try parsing with dateutil
                parsed_date = dateutil.parser.parse(date_str, fuzzy=True)
                
                # If year is not specified, assume it's this year or next year
                if parsed_date.year < 100:
                    parsed_date = parsed_date.replace(year=2000 + parsed_date.year)
                
                # Add timezone if not present
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=tzlocal())
                
                dates.append(parsed_date)
            except (ValueError, TypeError):
                continue
    
    return dates

def has_future_dates(email_content: Dict) -> Tuple[bool, Optional[datetime]]:
    """Check if the email contains any future dates."""
    now = datetime.now(tzlocal())
    text = f"{email_content['subject']} {email_content['body']}"
    
    dates = extract_dates(text)
    future_dates = [d for d in dates if d > now]
    
    if future_dates:
        return True, min(future_dates)  # Return the earliest future date
    return False, None

def get_gmail_service():
    """Gets valid user credentials from storage."""
    creds = None
    token_file = 'token.pickle'
    
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('gmail-oauth.json'):
                print("Error: gmail-oauth.json file not found!")
                print("Please download your OAuth 2.0 credentials from Google Cloud Console")
                print("and save them as 'gmail-oauth.json' in this directory.")
                exit(1)
                
            flow = InstalledAppFlow.from_client_secrets_file(
                'gmail-oauth.json', 
                SCOPES,
                redirect_uri='http://localhost:8080'
            )
            creds = flow.run_local_server(
                port=8080,
                success_message='Authentication successful! You can close this window.',
                authorization_prompt_message='Please visit this URL to authorize this application: '
            )
        
        # Save the credentials for the next run
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)

def get_email_content(message):
    """Extract the email content from a Gmail message."""
    if 'payload' not in message:
        return None
    
    payload = message['payload']
    headers = payload.get('headers', [])
    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    
    if 'parts' in payload:
        parts = payload['parts']
        data = parts[0]['body'].get('data', '')
    else:
        data = payload['body'].get('data', '')
    
    if not data:
        return None
    
    text = base64.urlsafe_b64decode(data).decode('utf-8')
    return {'subject': subject, 'body': text}

def is_travel_related(email_content: Dict) -> bool:
    """Check if an email is travel-related based on subject and content."""
    if not email_content:
        return False
    
    subject = email_content['subject'].lower()
    body = email_content['body'].lower()
    
    # First check if it's a promotional or tracking email
    for exclusion in TRAVEL_KEYWORDS['exclusion_words']:
        if exclusion in subject.lower():
            print(f"Skipping promotional/tracking email: {subject}")
            return False
    
    # Check for booking confirmation indicators
    has_booking_indicator = False
    for indicator in TRAVEL_KEYWORDS['booking_indicators']:
        if indicator in subject.lower() or indicator in body.lower():
            has_booking_indicator = True
            break
    
    if not has_booking_indicator:
        print(f"Skipping email without booking indicators: {subject}")
        return False
    
    # Check if the email contains future dates
    has_future, next_date = has_future_dates(email_content)
    if not has_future:
        print(f"Skipping email with no future dates: {subject}")
        return False
    else:
        print(f"Found future date: {next_date.strftime('%Y-%m-%d %H:%M')} in: {subject}")
    
    # Now check for specific travel categories
    for category in ['transportation', 'accommodation', 'activities']:
        for keyword in TRAVEL_KEYWORDS[category]:
            if keyword in subject.lower() or keyword in body.lower():
                # Look for patterns that suggest this is a real booking
                patterns = [
                    r'booking\s*(#|number|ref|reference|confirmation)?[:. ]*[A-Z0-9]{6,}',  # Booking reference
                    r'confirmation\s*(#|number|code)?[:. ]*[A-Z0-9]{6,}',  # Confirmation number
                    r'reservation\s*(#|number)?[:. ]*[A-Z0-9]{6,}',  # Reservation number
                    r'itinerary\s*(#|number)?[:. ]*[A-Z0-9]{6,}',   # Itinerary number
                    r'\b[A-Z]{2}\d{3,4}\b',  # Flight number pattern
                    r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}.*\d{1,2}[:. ]\d{2}',  # Date and time pattern
                    r'check-?in:?\s*\d{1,2}[-/]\d{1,2}',  # Check-in date pattern
                    r'total:?\s*[\$€£]?\d+[.,]\d{2}',  # Price/total pattern
                ]
                
                for pattern in patterns:
                    if re.search(pattern, body, re.IGNORECASE):
                        print(f"Found future booking in category {category}: {subject}")
                        return True
    
    print(f"Skipping email that doesn't match booking patterns: {subject}")
    return False

async def process_gmail_emails(user_id: str, days_back: int = 90, max_results: int = 50):
    """Process recent travel-related emails from Gmail."""
    service = get_gmail_service()
    
    # Calculate date range
    after_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')
    
    # Build search query - focus on confirmation/booking emails
    query = f'after:{after_date} AND (subject:"confirmation" OR subject:"confirmed" OR subject:"booking" OR subject:"reservation" OR subject:"itinerary" OR subject:"e-ticket")'
    
    print(f"\nSearching for emails from the last {days_back} days")
    print("Looking for travel booking emails with:")
    print("- Booking indicators:", ', '.join(TRAVEL_KEYWORDS['booking_indicators']))
    print("- Excluding:", ', '.join(TRAVEL_KEYWORDS['exclusion_words']))
    print("- Only processing bookings with future dates")
    print(f"\nSearch query: {query}")
    
    # Get emails matching the query
    results = service.users().messages().list(
        userId='me',
        q=query,
        maxResults=max_results
    ).execute()
    
    messages = results.get('messages', [])
    processed_emails = []
    
    print(f"\nFound {len(messages)} potential travel emails")
    
    for message in messages:
        msg = service.users().messages().get(
            userId='me',
            id=message['id']
        ).execute()
        
        email_content = get_email_content(msg)
        if email_content and is_travel_related(email_content):
            print(f"\nProcessing future booking email: {email_content['subject']}")
            result = await process_travel_email(user_id, email_content['body'])
            processed_emails.append({
                'subject': email_content['subject'],
                'result': result
            })
        else:
            print(f"Skipping non-booking or past email: {email_content['subject'] if email_content else 'No subject'}")
    
    return processed_emails

async def main():
    user_id = "gmail_user"
    
    print("Fetching and processing travel-related emails from Gmail...")
    processed_emails = await process_gmail_emails(user_id, days_back=90)
    
    print(f"\nProcessed {len(processed_emails)} travel-related emails")
    
    print("\nGetting travel summary...")
    summary = await get_travel_summary(user_id)
    print("\nTravel Summary:")
    print(summary)

if __name__ == '__main__':
    asyncio.run(main()) 