# ══════════════════════════════════════════════════════════════════════════════
# MCP CLIENT — MCP Server se connect hoke email bhejne wala client
# Ab token generation + interview link ke saath email bhejta hai
# ══════════════════════════════════════════════════════════════════════════════

# asyncio import — MCP client async hota hai, toh async functions chalane ke liye zaruri hai
import asyncio

# Client import — yeh FastMCP ka client class hai jo MCP server se connect aur tools call karta hai
from fastmcp import Client

# os import — file path handle karne ke liye (server file ka absolute path banane ke liye)
import os

# ──────────────────────────────────────────────────────────────────
# MCP SERVER KA PATH SET KARO
# ──────────────────────────────────────────────────────────────────

# Current file ka directory nikaalo — taaki server file ka path relative nahi, absolute ban sake
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# MCP server file ka full path banao — Client ko exact path chahiye server spawn karne ke liye
SERVER_PATH = os.path.join(CURRENT_DIR, "mcp_server2.py")

# ──────────────────────────────────────────────────────────────────
# MCP CLIENT INSTANCE BANAO
# ──────────────────────────────────────────────────────────────────

# Helper function — har request ke liye naya Client object banata hai
# Isse stale/closed session issues aur concurrency race conditions avoid hote hain
def _build_client() -> Client:
    return Client(SERVER_PATH)


# Helper function — CallToolResult ya plain object ko clean text response mein normalize karta hai
def _extract_tool_text(result_obj) -> str:
    # FastMCP CallToolResult mein .content list hoti hai, pehle block ka text actual response hota hai
    if hasattr(result_obj, "content") and result_obj.content:
        first_block = result_obj.content[0]
        if hasattr(first_block, "text"):
            return str(first_block.text)

    # Fallback: direct string conversion
    return str(result_obj)

# INTERVIEW_FRONTEND_BASE_URL — interview frontend ka base URL
# Jab deploy karoge toh isko apne production URL se replace karo
# Abhi localhost pe Streamlit chalta hai port 8502 pe (8501 pe dashboard hai)
INTERVIEW_FRONTEND_URL = "http://localhost:8502"

# ──────────────────────────────────────────────────────────────────
# SINGLE EMAIL WITH INTERVIEW LINK — Token generate karke link ke saath email bhejta hai
# ──────────────────────────────────────────────────────────────────

async def _send_email_async(recipient_email: str, candidate_name: str, resume_text: str, jd_text: str) -> str:
    """
    MCP server se connect hoke:
    1. Pehle resume + JD ka token generate karta hai
    2. Phir interview link ke saath email bhejta hai

    Args:
        recipient_email: Candidate ka email address jise email bhejna hai
        candidate_name: Candidate ka naam — subject line mein use hoga
        resume_text: Candidate ka full resume text — token mein save hoga
        jd_text: Job description text — token mein save hoga

    Returns:
        Server ka response — success ya error message
    """

    # Har call ke liye fresh client instance banao
    # Isse "Server session was closed unexpectedly" type intermittent errors kam hote hain
    client = _build_client()

    # "async with client" — server se connection kholta hai, kaam hone pe automatically band karta hai
    # Yeh internally mcp_server2.py ko ek subprocess ke roop mein spawn karta hai
    async with client:

        # STEP 1: Token generate karo — resume + JD ko server pe save karke unique token lo
        # generate_interview_token tool call hoga jo mcp_server2.py mein registered hai
        token_result = await client.call_tool(
            "generate_interview_token",  # mcp_server2.py mein registered tool ka naam
            {
                "resume_text": resume_text,  # Candidate ka resume text — token file mein save hoga
                "jd_text": jd_text            # Job description — token file mein save hoga
            }
        )

        # token_result se actual token string nikaalo
        # FastMCP 3.x mein call_tool() ek CallToolResult object return karta hai
        # .content attribute mein list of content blocks hoti hai
        # Pehle content block ka .text mein actual token string hota hai
        if hasattr(token_result, 'content') and token_result.content:
            token = str(token_result.content[0].text)
        else:
            token = str(token_result)

        # Check karo ki token properly generate hua ya error aaya
        # Agar "Error" se start hota hai toh token generation fail hua
        if token.startswith("Error"):
            return f"Token generation failed: {token}"

        # STEP 2: Interview link banao — frontend URL + token as query parameter
        # Jab candidate yeh link click karega, frontend token se resume + JD auto-load karega
        # Example: http://localhost:8502?token=a1b2c3d4-e5f6-7890-abcd-ef1234567890
        interview_link = f"{INTERVIEW_FRONTEND_URL}?token={token}"

        # STEP 3: Email body banao — interview link include karo
        # Yeh body candidate ko email mein dikhegi
        email_body = (
            f"Dear {candidate_name},\n\n"
            f"Congratulations! You have been shortlisted for the AI Interview round.\n\n"
            f"Please click the link below to start your interview:\n"
            f"{interview_link}\n\n"
            f"Important Instructions:\n"
            f"- The interview will be conducted by our AI system\n"
            f"- Please answer all questions honestly and in detail\n"
            f"- You will receive feedback after the interview is complete\n\n"
            f"Best regards,\nHR Team"
        )

        # STEP 4: Email bhejo — send_email tool call karo with interview link wali body
        result = await client.call_tool(
            "send_email",  # mcp_server2.py mein registered email tool
            {
                "recipient_email": recipient_email,
                "subject": f"Interview Invitation - {candidate_name}",
                "body": email_body
            }
        )

    # Server ka final response clean text mein return karo (email sent successfully / error)
    return _extract_tool_text(result)


def send_email(recipient_email: str, candidate_name: str, resume_text: str, jd_text: str) -> str:
    """
    Synchronous wrapper — Streamlit jaise sync frameworks se call kar sakte ho directly.
    Internally async function ko run karta hai.

    Args:
        recipient_email: Candidate ka email address
        candidate_name: Candidate ka naam
        resume_text: Candidate ka resume text (token generate karne ke liye)
        jd_text: Job description text (token generate karne ke liye)

    Returns:
        Server ka response — success ya error message
    """

    # asyncio.run() — async function ko synchronous context mein chalata hai
    # Streamlit mein directly await nahi kar sakte, isliye yeh wrapper zaruri hai
    try:
        return asyncio.run(_send_email_async(recipient_email, candidate_name, resume_text, jd_text))
    except Exception as e:
        # Exception ko safe string response mein convert karte hain taaki UI crash na ho
        return f"Failed to send email: {str(e)}"

# ──────────────────────────────────────────────────────────────────
# GET FREE SLOTS FROM GOOGLE CALENDAR — Calendar se free time slots nikaalke return karta hai
# ──────────────────────────────────────────────────────────────────

async def _get_free_slots_async(
    date: str,
    duration_minutes: int = 30,
    work_start_hour: int = 9,
    work_end_hour: int = 18,
    timezone_str: str = "Asia/Kolkata"
) -> dict:
    """
    MCP server se connect hoke Google Calendar se free slots fetch karta hai (async version).

    Args:
        date: Jis din ke free slots chahiye (format: "YYYY-MM-DD")
        duration_minutes: Har slot kitne minutes ka hona chahiye (default: 30)
        work_start_hour: Working hours start (24-hr format, default: 9 = 9AM)
        work_end_hour: Working hours end (24-hr format, default: 18 = 6PM)
        timezone_str: Timezone (default: "Asia/Kolkata")

    Returns:
        Dict with free slots data — date, total_free_slots, free_slots list, etc.
    """

    # json import — server se aane wale JSON string ko dict mein convert karne ke liye
    import json

    # Har call ke liye fresh client instance banao
    client = _build_client()

    # Server se connect karo
    async with client:

        # get_free_slots tool call karo — mcp_server2.py mein registered hai
        result = await client.call_tool(
            "get_free_slots",  # Server mein registered tool ka naam
            {
                "date": date,                           # Konsi date ke slots chahiye
                "duration_minutes": duration_minutes,   # Slot duration
                "work_start_hour": work_start_hour,     # Working hours start
                "work_end_hour": work_end_hour,         # Working hours end
                "timezone_str": timezone_str             # Timezone
            }
        )

        # CallToolResult se actual text nikaalo
        # FastMCP 3.x mein .content[0].text mein actual response hota hai
        if hasattr(result, 'content') and result.content:
            result_text = str(result.content[0].text)
        else:
            result_text = str(result)

        # JSON string ko Python dict mein parse karo
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            # Agar JSON parse fail ho toh raw text return karo
            return {"error": result_text}


def get_free_slots(
    date: str,
    duration_minutes: int = 30,
    work_start_hour: int = 9,
    work_end_hour: int = 18,
    timezone_str: str = "Asia/Kolkata"
) -> dict:
    """
    Synchronous wrapper — Streamlit ya kisi bhi sync code se directly call kar sakte ho.
    Google Calendar se free slots nikaalke dict mein return karta hai.

    Args:
        date: Jis din ke free slots chahiye (format: "YYYY-MM-DD")
        duration_minutes: Har slot kitne minutes ka hona chahiye (default: 30)
        work_start_hour: Working hours start (default: 9)
        work_end_hour: Working hours end (default: 18)
        timezone_str: Timezone (default: "Asia/Kolkata")

    Returns:
        Dict with keys: date, timezone, working_hours, slot_duration_minutes,
        total_free_slots, free_slots (list of {start_time, end_time, date})
    """

    # Async function ko sync context mein run karo
    try:
        return asyncio.run(_get_free_slots_async(
            date, duration_minutes, work_start_hour, work_end_hour, timezone_str
        ))
    except Exception as e:
        # Exception ko dict response mein return karo taaki caller gracefully handle kare
        return {"error": f"Failed to fetch free slots: {str(e)}"}


# ──────────────────────────────────────────────────────────────────
# BOOK MEETING IN GOOGLE CALENDAR — Selected free slot me event create karta hai
# ──────────────────────────────────────────────────────────────────

async def _book_meeting_async(
    start_datetime_iso: str,
    end_datetime_iso: str,
    summary: str,
    description: str = "",
    attendees_csv: str = "",
    timezone_str: str = "Asia/Kolkata"
) -> dict:
    """
    MCP server tool `book_meeting` ko call karke Google Calendar event create karta hai.

    Returns:
        Dict with booking status/details or error
    """

    # json import — server se aane wale JSON text ko dict me parse karne ke liye
    import json

    # Har call ke liye fresh client instance banao
    client = _build_client()

    # Server connection kholke tool call karo
    async with client:
        result = await client.call_tool(
            "book_meeting",
            {
                "start_datetime_iso": start_datetime_iso,
                "end_datetime_iso": end_datetime_iso,
                "summary": summary,
                "description": description,
                "attendees_csv": attendees_csv,
                "timezone_str": timezone_str,
            }
        )

    # Tool result ko clean text me convert karo
    result_text = _extract_tool_text(result)

    # JSON parse try karo
    try:
        return json.loads(result_text)
    except json.JSONDecodeError:
        return {"error": result_text}


def book_meeting(
    start_datetime_iso: str,
    end_datetime_iso: str,
    summary: str,
    description: str = "",
    attendees_csv: str = "",
    timezone_str: str = "Asia/Kolkata"
) -> dict:
    """
    Sync wrapper for meeting booking — Streamlit/sync code se direct call ke liye.
    """

    try:
        return asyncio.run(
            _book_meeting_async(
                start_datetime_iso=start_datetime_iso,
                end_datetime_iso=end_datetime_iso,
                summary=summary,
                description=description,
                attendees_csv=attendees_csv,
                timezone_str=timezone_str,
            )
        )
    except Exception as e:
        return {"error": f"Failed to book meeting: {str(e)}"}

# ──────────────────────────────────────────────────────────────────
# BULK EMAIL WITH INTERVIEW LINKS — Multiple candidates ko token + link ke saath email
# ──────────────────────────────────────────────────────────────────

async def _send_bulk_emails_async(candidates: list, jd_text: str) -> list:
    """
    Multiple candidates ko ek saath interview link wali email bhejta hai (async version).
    Har candidate ke liye alag token generate hota hai.

    Args:
        candidates: List of dicts — har dict mein 'mail', 'candidate_name', 'resume_text' hona chahiye
                    Example: [{'mail': 'a@b.com', 'candidate_name': 'Priya', 'resume_text': '...', 'score': 85}, ...]
        jd_text: Job description text — sabhi tokens mein same JD jaayega

    Returns:
        List of results — har candidate ke liye success/error message
    """

    # Results store karne ke liye empty list
    results = []

    # Har bulk call ke liye fresh client instance banao
    client = _build_client()

    # Server se ek baar connect karo — saare emails ek hi connection mein bhejo (efficient)
    async with client:

        # Har candidate pe loop lagao
        for candidate in candidates:

            # Try-except — agar ek email fail ho toh baaki band na ho
            try:

                # STEP 1: Is candidate ke liye unique token generate karo
                # Candidate ka resume + JD dono token mein save honge
                token_result = await client.call_tool(
                    "generate_interview_token",
                    {
                        "resume_text": candidate.get("resume_text", "Resume not available"),
                        "jd_text": jd_text
                    }
                )

                # Token string nikaalo result se
                # CallToolResult object ka .content attribute mein list hoti hai
                if hasattr(token_result, 'content') and token_result.content:
                    token = str(token_result.content[0].text)
                else:
                    token = str(token_result)

                # Interview link banao is candidate ke liye
                interview_link = f"{INTERVIEW_FRONTEND_URL}?token={token}"

                # STEP 2: Email body banao with interview link
                email_body = (
                    f"Dear {candidate['candidate_name']},\n\n"
                    f"Congratulations! You have been shortlisted for the AI Interview round.\n\n"
                    f"Your resume match score: {candidate.get('score', 'N/A')}%\n\n"
                    f"Please click the link below to start your interview:\n"
                    f"{interview_link}\n\n"
                    f"Important Instructions:\n"
                    f"- The interview will be conducted by our AI system\n"
                    f"- Please answer all questions honestly and in detail\n"
                    f"- You will receive feedback after the interview is complete\n\n"
                    f"Best regards,\nHR Team"
                )

                # STEP 3: Email bhejo is candidate ko
                result = await client.call_tool(
                    "send_email",
                    {
                        "recipient_email": candidate["mail"],
                        "subject": f"Interview Invitation - {candidate['candidate_name']}",
                        "body": email_body
                    }
                )

                # Server response ko clean text mein convert karo
                result_text = _extract_tool_text(result)

                # Success result add karo list mein
                results.append({
                    "email": candidate["mail"],
                    "name": candidate["candidate_name"],
                    "status": "sent",
                    "response": result_text,
                    "interview_link": interview_link  # Link bhi return karo — dashboard mein dikha sakte hain
                })

            except Exception as e:

                # Error aaya toh error result add karo — loop continue rahe
                results.append({
                    "email": candidate["mail"],
                    "name": candidate["candidate_name"],
                    "status": "failed",
                    "response": str(e)
                })

    # Saare results return karo
    return results


def send_bulk_emails(candidates: list, jd_text: str) -> list:
    """
    Synchronous wrapper for bulk emails — dashboard se directly call kar sakte ho.

    Args:
        candidates: List of dicts with 'mail', 'candidate_name', 'resume_text', and optionally 'score'
        jd_text: Job description text — sabhi tokens mein same JD jaayega

    Returns:
        List of result dicts with 'email', 'name', 'status', 'response', 'interview_link'
    """

    # Async function ko sync context mein run karo
    try:
        return asyncio.run(_send_bulk_emails_async(candidates, jd_text))
    except Exception as e:
        # Bulk-level exception aaye toh structured failure list return karo
        return [{
            "email": "unknown",
            "name": "unknown",
            "status": "failed",
            "response": f"Bulk email failed: {str(e)}"
        }]


# ──────────────────────────────────────────────────────────────────
# DIRECT TEST — file ko seedha run karo toh test email bhejega
# ──────────────────────────────────────────────────────────────────

# Yeh guard tab chalega jab file directly run karo: python mcp_client.py
if __name__ == "__main__":

    # Test: token generate karke interview link wali email bhejo
    print("Testing single email with interview link...")
    response = send_email(
        recipient_email="test@example.com",       # ← apna test email daalo
        candidate_name="Test Candidate",
        resume_text="Sample resume text for testing...",   # Test resume
        jd_text="Sample job description for testing..."    # Test JD
    )
    print(f"Result: {response}")
