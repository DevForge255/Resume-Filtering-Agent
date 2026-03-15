# ══════════════════════════════════════════════════════════════════════════════
# MCP SERVER 2 — Gmail API + OAuth2 (credentials.json) se email bhejne wala
# ══════════════════════════════════════════════════════════════════════════════

# FastMCP import — yeh MCP server banane ki core library hai
from fastmcp import FastMCP

# os module — file paths handle karne ke liye (credentials.json aur token.json ka path)
import os

# base64 module — Gmail API ko email base64-encoded format mein chahiye, yeh encoding/decoding karta hai
import base64

# MIMEText — email ka body (plain text ya HTML) banane ke liye use hota hai
from email.mime.text import MIMEText

# MIMEMultipart — email message ka overall structure banata hai (From, To, Subject, Body sab ek saath)
from email.mime.multipart import MIMEMultipart

# uuid module — unique token ID generate karne ke liye (har interview link ka ek unique identifier hoga)
import uuid

# json module — resume + JD data ko JSON file mein save/load karne ke liye
import json

# pathlib.Path — folders create karne ke liye (tokens/ folder banayenge)
from pathlib import Path

# datetime module — date/time handle karne ke liye (calendar free slots ke liye zaruri)
from datetime import datetime, timedelta, timezone

# dateutil.parser — flexible date string parsing ke liye (e.g., "2025-01-15" → datetime object)
# Agar installed nahi hai toh: pip install python-dateutil
from dateutil import parser as dateutil_parser

# ──────────────────────────────────────────────────────────────────
# Google API & OAuth2 Libraries
# ──────────────────────────────────────────────────────────────────

# Credentials class — saved token.json file se credentials load karne ke liye
from google.oauth2.credentials import Credentials

# InstalledAppFlow — pehli baar jab token nahi hota, toh browser open karke user se permission leta hai
from google_auth_oauthlib.flow import InstalledAppFlow

# Request — jab token expire ho jaaye toh refresh karne ke liye HTTP request bhejta hai Google ko
from google.auth.transport.requests import Request

# build — Gmail API ka service object banata hai jisse hum emails bhej sakte hain
from googleapiclient.discovery import build

# ──────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────

# SCOPES — Google APIs ko batata hai ki humein kya-kya permissions chahiye
# "gmail.send" → sirf email bhejne ki permission
# "calendar.readonly" → Google Calendar ke events read karne ki permission (free/busy check ke liye)
# "calendar.events" → Calendar events create/update karne ki permission (meeting booking ke liye)
# Agar scope change karo toh token.json delete karke dubara authorize karna padega
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",          # Email bhejne ke liye
    "https://www.googleapis.com/auth/calendar.readonly",   # Calendar se free slots nikalne ke liye
    "https://www.googleapis.com/auth/calendar.events",     # Calendar meeting create karne ke liye
]

# credentials.json ka path — yeh file Google Cloud Console se download hoti hai
# Isme Client ID, Client Secret, Redirect URIs hote hain — yeh app ki identity hai
CREDENTIALS_FILE = "credentials.json"

# token.json ka path — pehli baar authorize karne ke baad yeh file ban jaati hai
# Isme access_token aur refresh_token hota hai — dubara browser open nahi karna padta
TOKEN_FILE = "token.json"

# ──────────────────────────────────────────────────────────────────
# GMAIL API AUTHENTICATION FUNCTION
# ──────────────────────────────────────────────────────────────────

def get_gmail_service():
    """
    Gmail API se authenticated connection banata hai.
    
    Flow:
    1. Pehle check karta hai ki token.json file exist karti hai ya nahi
    2. Agar hai — token load karta hai
    3. Agar token expired hai — refresh karta hai
    4. Agar token hi nahi hai — browser open karke user se permission leta hai
    5. Final mein Gmail API ka service object return karta hai
    
    Returns:
        Gmail API service object jisse emails bhej sakte hain
    """

    # creds variable mein credentials store honge — initially None hai kyunki abhi load nahi hua
    creds = None

    # Check: kya token.json file already exist karti hai? (matlab pehle se authorized hai)
    if os.path.exists(TOKEN_FILE):

        # Agar haan — toh token.json se credentials load karo
        # SCOPES pass karte hain taaki verify ho sake ki token same permissions ke liye hai
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Ab check karo: kya credentials valid hain ya nahi?
    # "not creds" → credentials exist hi nahi karte
    # "not creds.valid" → credentials expire ho gaye hain
    if not creds or not creds.valid:

        # Sub-check: kya credentials hain lekin expire ho gaye hain AUR refresh_token available hai?
        if creds and creds.expired and creds.refresh_token:

            # Haan — toh Google ko request bhejo ki naya access_token de do (browser open nahi hoga)
            creds.refresh(Request())

        else:
            # Nahi — matlab pehli baar hai ya refresh_token bhi nahi hai
            # InstalledAppFlow credentials.json padhta hai aur OAuth2 flow start karta hai
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)

            # Browser open hoga → user apna Google account choose karega → permission dega
            # port=0 matlab OS koi bhi available port assign kar dega callback ke liye
            creds = flow.run_local_server(port=0)

        # Naye/refreshed credentials ko token.json mein save karo
        # Taaki next time browser open na karna pade — directly token se authenticate ho jaaye
        with open(TOKEN_FILE, "w") as token_file:

            # credentials ko JSON format mein convert karke file mein likh do
            token_file.write(creds.to_json())

    # Gmail API ka service object build karo
    # "gmail" → service name, "v1" → API version
    # credentials pass karte hain taaki authenticated requests jaa sakein
    service = build("gmail", "v1", credentials=creds)

    # Service object return karo — isse hum emails bhej payenge
    return service


# ──────────────────────────────────────────────────────────────────
# GOOGLE CALENDAR API SERVICE FUNCTION
# Calendar se events/free-busy data read karne ke liye
# ──────────────────────────────────────────────────────────────────

def get_calendar_service():
    """
    Google Calendar API se authenticated connection banata hai.
    Same credentials (token.json) use karta hai jo Gmail ke liye bhi use hoti hain.
    SCOPES mein calendar.readonly already add hai isliye alag auth nahi chahiye.

    Returns:
        Google Calendar API service object jisse events aur freebusy query kar sakte hain
    """

    # creds variable — initially None, fir token.json se load karenge
    creds = None

    # Check: kya token.json file exist karti hai?
    if os.path.exists(TOKEN_FILE):

        # Token file se credentials load karo — same SCOPES pass karo
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Kya credentials valid hain? Nahi toh refresh ya re-authenticate karo
    if not creds or not creds.valid:

        # Agar credentials hain lekin expire ho gaye + refresh_token hai → refresh karo
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            # Pehli baar hai ya refresh_token nahi — browser se OAuth2 flow start karo
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Updated credentials save karo
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())

    # Calendar API ka service object build karo
    # "calendar" → service name, "v3" → Calendar API ki latest version
    calendar_service = build("calendar", "v3", credentials=creds)

    # Calendar service return karo — isse free/busy query karenge
    return calendar_service

# ──────────────────────────────────────────────────────────────────
# TOKEN STORAGE CONFIGURATION
# ──────────────────────────────────────────────────────────────────

# TOKENS_DIR — yeh folder tokens store karega (har token ek JSON file hogi)
# Jab generate_interview_token call hoga, yahan file save hogi
# Jab interview_frontend.py token read karega, isi folder se load karega
TOKENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")

# Agar tokens/ folder exist nahi karta toh bana do — exist_ok=True matlab agar already hai toh error nahi aayega
Path(TOKENS_DIR).mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────
# CREATE THE MCP SERVER INSTANCE
# ──────────────────────────────────────────────────────────────────

# FastMCP server ka instance banao ek descriptive name ke saath
# Yeh name MCP clients (jaise LLMs) ko dikhta hai taaki pata chale server kya karta hai
mcp = FastMCP("Gmail API Email Sender MCP Server")

# ──────────────────────────────────────────────────────────────────
# TOOL 1: GENERATE INTERVIEW TOKEN
# Resume + JD ko ek unique token mein wrap karta hai
# Yeh token interview frontend URL ke saath bheja jaayega email mein
# ──────────────────────────────────────────────────────────────────

# @mcp.tool() — yeh function ko MCP tool ke roop mein register karta hai
# MCP clients (jaise mcp_client.py) is function ko call kar sakte hain
@mcp.tool()
def generate_interview_token(resume_text: str, jd_text: str) -> str:
    """
    Resume aur JD text ko ek unique token mein save karta hai.
    Yeh token interview frontend URL mein query parameter ke roop mein use hoga.

    Args:
        resume_text: Candidate ka full resume text (plain text format)
        jd_text: Job Description ka full text

    Returns:
        Generated unique token string (UUID format)
    """

    # try-except — agar file save karne mein error aaye toh server crash na ho
    try:

        # uuid4() — ek random unique ID generate karta hai (e.g., "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        # Har baar naya unique token milega — do candidates ka token kabhi same nahi hoga
        token = str(uuid.uuid4())

        # Token data — resume aur JD dono ko ek dictionary mein rakho
        # Yeh dictionary JSON file mein save hogi
        token_data = {
            "resume": resume_text,   # Candidate ka resume text
            "jd": jd_text            # Job description text
        }

        # Token file ka path banao — tokens/ folder mein {token}.json naam se save hogi
        # Example: tokens/a1b2c3d4-e5f6-7890-abcd-ef1234567890.json
        token_file_path = os.path.join(TOKENS_DIR, f"{token}.json")

        # JSON file mein data likho — "w" mode matlab nayi file banao ya purani overwrite karo
        with open(token_file_path, "w") as f:

            # json.dump() — Python dictionary ko JSON format mein convert karke file mein save karta hai
            # ensure_ascii=False — Hindi/special characters properly save hote hain
            json.dump(token_data, f, ensure_ascii=False)

        # Successfully generate hua toh token string return karo
        return token

    # Agar koi error aaye (folder permission, disk full, etc.) toh catch karo
    except Exception as e:

        # Error message return karo — MCP client ko pata chale kya galat hua
        return f"Error generating token: {str(e)}"

# ──────────────────────────────────────────────────────────────────
# TOOL 2: GET FREE SLOTS FROM GOOGLE CALENDAR
# Google Calendar se busy times nikaalke free slots calculate karta hai
# HR ko pata chalta hai ki candidate ko interview ke liye kab available hain
# ──────────────────────────────────────────────────────────────────

# @mcp.tool() — yeh function ko MCP tool ke roop mein register karta hai
@mcp.tool()
def get_free_slots(
    date: str,
    duration_minutes: int = 30,
    work_start_hour: int = 9,
    work_end_hour: int = 18,
    timezone_str: str = "Asia/Kolkata"
) -> str:
    """
    Google Calendar se free (available) slots nikaalke return karta hai.
    Busy times check karke inverse calculate karta hai — matlab jab busy nahi ho, woh free slots hain.

    Args:
        date: Jis din ke free slots chahiye (format: "YYYY-MM-DD", e.g., "2025-07-15")
        duration_minutes: Har slot kitne minutes ka hona chahiye (default: 30 mins)
        work_start_hour: Working hours kab shuru hote hain (24-hr format, default: 9 = 9 AM)
        work_end_hour: Working hours kab khatam hote hain (24-hr format, default: 18 = 6 PM)
        timezone_str: Timezone string (default: "Asia/Kolkata" — India IST)

    Returns:
        JSON string with list of free slots — har slot mein start_time aur end_time hai
    """

    # try-except — agar calendar API call fail ho toh graceful error return ho
    try:

        # ────────────── DATE PARSING ──────────────

        # User ki di hui date string ko datetime object mein convert karo
        # dateutil_parser.parse() flexible hai — "2025-07-15", "July 15, 2025" sab samajhta hai
        target_date = dateutil_parser.parse(date).date()

        # ────────────── TIMEZONE HANDLING ──────────────

        # pytz ya zoneinfo se timezone object banao
        # Python 3.9+ mein zoneinfo built-in hai, purane versions mein pytz use hota hai
        try:
            # Python 3.9+ ke liye — built-in timezone support
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(timezone_str)
        except ImportError:
            # Agar zoneinfo nahi hai (Python < 3.9) toh pytz use karo
            import pytz
            tz = pytz.timezone(timezone_str)

        # ────────────── WORKING HOURS DEFINE KARO ──────────────

        # Working hours ka start time banao — target_date ke din work_start_hour baje
        # Example: 2025-07-15 09:00:00 IST
        work_start = datetime(
            target_date.year, target_date.month, target_date.day,
            work_start_hour, 0, 0,  # hour, minute, second
            tzinfo=tz               # timezone attach karo
        )

        # Working hours ka end time banao — same din work_end_hour baje
        # Example: 2025-07-15 18:00:00 IST
        work_end = datetime(
            target_date.year, target_date.month, target_date.day,
            work_end_hour, 0, 0,    # hour, minute, second
            tzinfo=tz               # timezone attach karo
        )

        # ────────────── GOOGLE CALENDAR FREEBUSY QUERY ──────────────

        # Calendar API ka authenticated service object lo
        calendar_service = get_calendar_service()

        # FreeBusy query ka body banao — Google ko bata rahe hain:
        # "Iss time range mein, meri primary calendar mein kab-kab busy hun?"
        freebusy_query = {
            # timeMin — search kab se shuru karo (ISO format mein chahiye Google ko)
            "timeMin": work_start.isoformat(),

            # timeMax — search kab tak karo
            "timeMax": work_end.isoformat(),

            # timeZone — response bhi isi timezone mein aayega
            "timeZone": timezone_str,

            # items — konsi calendars check karni hain
            # "primary" = user ki main/default calendar
            "items": [{"id": "primary"}]
        }

        # API call karo — Google Calendar se busy periods fetch karo
        # freebusy().query() method use hota hai FreeBusy endpoint ke liye
        freebusy_result = calendar_service.freebusy().query(body=freebusy_query).execute()

        # Response se "primary" calendar ki busy periods nikaalo
        # Yeh ek list of dicts hogi: [{"start": "...", "end": "..."}, ...]
        busy_periods = freebusy_result.get("calendars", {}).get("primary", {}).get("busy", [])

        # ────────────── BUSY PERIODS KO DATETIME OBJECTS MEIN CONVERT KARO ──────────────

        # busy_times — list of (start, end) tuples as datetime objects
        busy_times = []

        # Har busy period ko parse karo
        for period in busy_periods:

            # "start" string ko datetime object mein convert karo
            busy_start = dateutil_parser.parse(period["start"])

            # "end" string ko datetime mein convert karo
            busy_end = dateutil_parser.parse(period["end"])

            # Tuple ke roop mein list mein add karo
            busy_times.append((busy_start, busy_end))

        # Busy times ko start time ke basis pe sort karo — taaki order mein process ho
        busy_times.sort(key=lambda x: x[0])

        # ────────────── FREE SLOTS CALCULATE KARO ──────────────

        # free_slots — yahan calculated free slots store honge
        free_slots = []

        # current_time — yeh pointer hai jo working hours ke start se chalega
        # Har iteration mein aage badhega jab tak koi busy period ya work_end na aa jaaye
        current_time = work_start

        # Har busy period ke beech ka gap ek free slot hai
        for busy_start, busy_end in busy_times:

            # Agar current_time busy_start se pehle hai → beech ka time free hai
            if current_time < busy_start:

                # Iss free gap mein kitne slots fit ho sakte hain — duration_minutes ke hisaab se
                # Jab tak free gap mein ek slot fit ho raha hai, tab tak add karo
                slot_start = current_time

                # Loop: gap ke andar multiple slots ban sakte hain
                while slot_start + timedelta(minutes=duration_minutes) <= busy_start:

                    # Slot ka end time = start + duration
                    slot_end = slot_start + timedelta(minutes=duration_minutes)

                    # Slot add karo — time ko human-readable format mein (HH:MM)
                    free_slots.append({
                        "start_time": slot_start.strftime("%H:%M"),  # e.g., "09:00"
                        "end_time": slot_end.strftime("%H:%M"),      # e.g., "09:30"
                        "date": target_date.isoformat()               # e.g., "2025-07-15"
                    })

                    # Pointer ko agle slot ke start pe le jaao
                    slot_start = slot_end

            # Current time ko busy period ke end ke baad le jaao
            # Agar busy_end already current_time se pehle hai toh current_time change nahi hoga
            if busy_end > current_time:
                current_time = busy_end

        # ────────────── LAST GAP: Busy periods ke baad bhi free time ho sakta hai ──────────────

        # Agar last busy period ke baad bhi working hours baaki hain → woh bhi free slots hain
        if current_time < work_end:

            # Same logic — remaining gap mein slots fit karo
            slot_start = current_time

            while slot_start + timedelta(minutes=duration_minutes) <= work_end:

                slot_end = slot_start + timedelta(minutes=duration_minutes)

                free_slots.append({
                    "start_time": slot_start.strftime("%H:%M"),
                    "end_time": slot_end.strftime("%H:%M"),
                    "date": target_date.isoformat()
                })

                slot_start = slot_end

        # ────────────── RESULT FORMAT KARO ──────────────

        # Agar koi free slot nahi mila — matlab poora din busy hai
        if not free_slots:
            return json.dumps({
                "date": target_date.isoformat(),
                "message": f"No free slots available on {target_date.isoformat()} between {work_start_hour}:00 and {work_end_hour}:00",
                "free_slots": [],
                "total_free_slots": 0
            }, ensure_ascii=False)

        # Free slots mili — details ke saath return karo
        return json.dumps({
            "date": target_date.isoformat(),               # Kis din ke slots hain
            "timezone": timezone_str,                       # Konsa timezone
            "working_hours": f"{work_start_hour}:00 - {work_end_hour}:00",  # Working hours range
            "slot_duration_minutes": duration_minutes,      # Har slot kitne minutes ka
            "total_free_slots": len(free_slots),            # Kitne free slots mile
            "free_slots": free_slots                        # Actual slots ki list
        }, ensure_ascii=False)

    # Agar koi error aaye — API failure, network issue, invalid date, etc.
    except Exception as e:

        # Error details JSON mein return karo
        return json.dumps({
            "error": f"Failed to get free slots: {str(e)}"
        }, ensure_ascii=False)

# ──────────────────────────────────────────────────────────────────
# TOOL 3: BOOK MEETING IN GOOGLE CALENDAR
# Free slot milne par calendar event create karta hai
# ──────────────────────────────────────────────────────────────────

# @mcp.tool() — yeh function ko MCP tool ke roop mein register karta hai
@mcp.tool()
def book_meeting(
    start_datetime_iso: str,
    end_datetime_iso: str,
    summary: str,
    description: str = "",
    attendees_csv: str = "",
    timezone_str: str = "Asia/Kolkata"
) -> str:
    """
    Google Calendar mein ek meeting event create karta hai.

    Args:
        start_datetime_iso: Meeting start datetime (ISO format), e.g. "2026-03-20T10:00:00+05:30"
        end_datetime_iso: Meeting end datetime (ISO format), e.g. "2026-03-20T10:30:00+05:30"
        summary: Meeting title/subject
        description: Meeting description/body text
        attendees_csv: Comma-separated attendee emails (optional), e.g. "a@x.com,b@y.com"
        timezone_str: Timezone string for event (default: Asia/Kolkata)

    Returns:
        JSON string with booking status, event id, and event link (or error)
    """

    # try-except — booking error aaye toh tool graceful error return kare
    try:

        # Calendar API service object lo
        calendar_service = get_calendar_service()

        # Start datetime string ko parse karo
        start_dt = dateutil_parser.parse(start_datetime_iso)

        # End datetime string ko parse karo
        end_dt = dateutil_parser.parse(end_datetime_iso)

        # Basic validation: end start se bada hona chahiye
        if end_dt <= start_dt:
            return json.dumps({"error": "end_datetime_iso must be later than start_datetime_iso"}, ensure_ascii=False)

        # attendees list banao — CSV se split karke event format me convert karo
        attendees = []
        for email in [item.strip() for item in attendees_csv.split(",") if item.strip()]:
            attendees.append({"email": email})

        # Event request body prepare karo
        event_body = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": timezone_str,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": timezone_str,
            },
            "attendees": attendees,
        }

        # Calendar event create call execute karo
        created_event = (
            calendar_service.events()
            .insert(calendarId="primary", body=event_body, sendUpdates="all")
            .execute()
        )

        # Success response JSON return karo
        return json.dumps(
            {
                "status": "booked",
                "event_id": created_event.get("id", ""),
                "event_link": created_event.get("htmlLink", ""),
                "start": created_event.get("start", {}),
                "end": created_event.get("end", {}),
            },
            ensure_ascii=False,
        )

    # Error case — details return karo
    except Exception as e:
        return json.dumps({"error": f"Failed to book meeting: {str(e)}"}, ensure_ascii=False)

# ──────────────────────────────────────────────────────────────────
# TOOL 4: SEND EMAIL
# Gmail API ke through email bhejta hai
# ──────────────────────────────────────────────────────────────────

# @mcp.tool() decorator — yeh function ko ek MCP "tool" ke roop mein register karta hai
# MCP clients (LLMs) is function ko directly call kar sakte hain
@mcp.tool()
def send_email(recipient_email: str, subject: str, body: str) -> str:
    """
    Gmail API ke through ek email bhejta hai specified recipient ko.

    Args:
        recipient_email: Jis insaan ko email bhejna hai uska email address.
        subject: Email ki subject line.
        body: Email ka main text content (body).

    Returns:
        Success message agar email chali gayi, ya error message agar kuch galat hua.
    """

    # try-except block — agar koi error aaye toh server crash na ho, gracefully handle ho
    try:

        # Gmail API ka authenticated service object le lo
        service = get_gmail_service()

        # MIMEMultipart object banao — yeh poore email ka structure represent karta hai
        message = MIMEMultipart()

        # "To" header set karo — kis email address pe bhejna hai
        message["To"] = recipient_email

        # "Subject" header set karo — email ka subject line
        message["Subject"] = subject

        # Email ka body (text) attach karo as a plain-text MIME part
        # "plain" matlab simple text hai, HTML nahi
        message.attach(MIMEText(body, "plain"))

        # Email message ko string mein convert karo (full MIME format — headers + body)
        raw_message = message.as_string()

        # String ko bytes mein encode karo (UTF-8 format — standard encoding)
        raw_bytes = raw_message.encode("utf-8")

        # Bytes ko base64url format mein encode karo — Gmail API specifically yeh format maangta hai
        # urlsafe_b64encode standard base64 se thoda different hai (+ aur / ki jagah - aur _ use karta hai)
        encoded_message = base64.urlsafe_b64encode(raw_bytes)

        # Base64 bytes ko string mein convert karo — API ko string chahiye, bytes nahi
        encoded_string = encoded_message.decode("utf-8")

        # Gmail API ke liye message body banao — "raw" key mein base64-encoded email jaati hai
        gmail_message_body = {"raw": encoded_string}

        # Gmail API call — email bhejo!
        # users() → Gmail user select karo
        # messages() → messages resource access karo
        # send() → email bhejne ka method
        # userId="me" → currently authenticated user (jisne OAuth2 se login kiya)
        # body → humara base64-encoded email message
        # execute() → API call actually execute karo (bina iske sirf request banti hai, jaati nahi)
        sent_message = (
            service.users()
            .messages()
            .send(userId="me", body=gmail_message_body)
            .execute()
        )

        # Gmail API successful response mein ek unique message "id" return karta hai
        # Isko return karo confirmation ke saath
        return f"Email sent successfully to {recipient_email}! Message ID: {sent_message['id']}"

    # Agar koi bhi error aaye (network, auth, invalid email, etc.) — catch karo
    except Exception as e:

        # Error ki details return karo taaki MCP client (ya LLM) ko pata chale kya galat hua
        return f"Failed to send email: {str(e)}"


# ──────────────────────────────────────────────────────────────────
# START THE MCP SERVER
# ──────────────────────────────────────────────────────────────────

# Yeh guard ensure karta hai ki server sirf tab chale jab yeh file directly run ho
# Agar koi doosri file isse import kare toh server start nahi hoga
if __name__ == "__main__":

    # MCP server start karo — yeh incoming tool-call requests ke liye listen karega
    # Default mein stdio transport use hota hai — MCP client isse launch karke communicate karta hai
    mcp.run()
