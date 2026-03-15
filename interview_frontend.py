"""
Interview Question Frontend
==========================
Yeh frontend question_generation_and_analyzer.py ke saath connect hota hai.

BACKEND CONNECTION GUIDE (jab backend modify karoge):
-----------------------------------------------------
Backend mein ek function chahiye jo yeh signature follow kare:

    def get_next_turn(resume: str, jd: str, messages: list, user_input: str) -> dict:
        Returns: {
            'interviewer_message': str,   # AI ka next question
            'messages': list,             # Updated conversation (HumanMessage + AIMessage)
            'interview_complete': bool,   # True when 6 messages (3 Q&A pairs)
            'feedback': str | None        # Jab complete ho, analyzer ka output
        }

Backend change: question_generation_and_analyzer.py mein
- chatnode ko user_input state se lena hoga (input() ki jagah)
- Graph ko step-by-step invoke karna hoga, ya interrupt use karna hoga

CONNECT KARNE KA TAREEKA:
1. Backend mein get_next_turn() expose karo
2. Neeche call_backend() function mein uncomment karo aur import add karo
3. Mock/Demo mode ko False karo (USE_MOCK = False)
"""

import streamlit as st

# json module — token file (JSON format) se resume + JD load karne ke liye
import json

# os module — token file ka path banane ke liye
import os

# ═══════════════════════════════════════════════════════════════════
# BACKEND CONNECTION — Ab real backend se connected hai!
# ═══════════════════════════════════════════════════════════════════
USE_MOCK = False  # True karo agar mock/demo mode chahiye

# Backend import
from question_generation_and_analyzer import get_next_turn


def call_backend(resume: str, jd: str, messages: list, user_input: str) -> dict:
    """
    Backend ko call karta hai.
    
    BACKEND SE EXPECTED RESPONSE:
    {
        'interviewer_message': str,   # AI ka question
        'messages': list,             # Updated messages (LangChain format)
        'interview_complete': bool,
        'feedback': str | None        # Final analysis (jab complete ho)
    }
    """
    if USE_MOCK:
        # Demo mode — mock responses
        return _mock_backend_call(resume, jd, messages, user_input)
    
    # ─── REAL BACKEND CONNECTION (ACTIVE) ────────────────────────
    return get_next_turn(resume=resume, jd=jd, messages=messages, user_input=user_input)


def _mock_backend_call(resume: str, jd: str, messages: list, user_input: str) -> dict:
    """Demo / mock responses — backend connect hone tak."""
    new_messages = list(messages) if messages else []
    if user_input:
        new_messages.append({'role': 'human', 'content': user_input})
    
    msg_count = len(new_messages)  # After adding user's answer
    
    mock_questions = [
        "Hello! Thanks for joining. Can you walk me through your experience with microservices and API development?",
        "That's helpful. How did you approach the database optimization that reduced response time by 40%?",
        "Great. What challenges did you face while migrating to serverless on AWS Lambda?",
    ]
    
    # 3 Q&A pairs = 6 messages total (3 AI + 3 Human)
    if msg_count >= 6 or (len(messages) >= 5 and user_input):
        return {
            'interviewer_message': '',
            'messages': new_messages,
            'interview_complete': True,
            'feedback': """
**CANDIDATE ANALYSIS REPORT**
=======================

**FINAL RECOMMENDATION:** PROCEED TO LIVE INTERVIEW

*[Backend connect karne par yahan real analyzer output aayega]*
"""
        }
    
    # Add next AI question (idx = which question: 0, 1, 2)
    idx = msg_count // 2
    if idx < len(mock_questions):
        next_q = mock_questions[idx]
        new_messages.append({'role': 'ai', 'content': next_q})
        return {
            'interviewer_message': next_q,
            'messages': new_messages,
            'interview_complete': False,
            'feedback': None
        }
    
    return {
        'interviewer_message': '',
        'messages': new_messages,
        'interview_complete': True,
        'feedback': "Interview complete. Connect backend for real analysis."
    }


# ═══════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ═══════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="AI Interview",
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .chat-interviewer { background: #e0f2fe; color: #1e293b; padding: 1rem; border-radius: 12px; margin: 0.5rem 0; }
    .chat-candidate { background: #dcfce7; color: #1e293b; padding: 1rem; border-radius: 12px; margin: 0.5rem 0; }
    .feedback-box { background: #fef3c7; color: #1e293b; padding: 1.5rem; border-radius: 12px; border-left: 4px solid #f59e0b; }
</style>
""", unsafe_allow_html=True)

# Session state
DEFAULTS = {
    'resume': '',
    'jd': '',
    'messages': [],
    'interview_complete': False,
    'feedback': None,
    'show_feedback': False,
    'token_loaded': False,   # Naya flag — track karta hai ki token se data load hua ya nahi
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════════════
# TOKEN AUTO-LOAD — URL mein token hai toh resume + JD auto-fill karo
# ═══════════════════════════════════════════════════════════════

# TOKENS_DIR — yeh wahi folder hai jahan mcp_server2.py tokens save karta hai
# Dono files (server + frontend) same folder se read/write karti hain
TOKENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")

# st.query_params — URL ke query parameters read karta hai
# Example: http://localhost:8502?token=abc123 → query_params["token"] = "abc123"
# Yeh Streamlit 1.30+ ka feature hai (purane mein st.experimental_get_query_params tha)
query_params = st.query_params

# Check karo ki URL mein "token" parameter hai ya nahi
# Aur yeh bhi check karo ki pehle se load nahi hua ho (warna har rerun pe dubara load hoga)
if "token" in query_params and not st.session_state.get('token_loaded'):

    # Token value nikaalo query params se
    token = query_params["token"]

    # Token file ka path banao — tokens/{token}.json
    token_file_path = os.path.join(TOKENS_DIR, f"{token}.json")

    # Check karo ki token file exist karti hai ya nahi
    if os.path.exists(token_file_path):

        # Token file kholke JSON data load karo
        with open(token_file_path, "r") as f:

            # json.load() — JSON file ko Python dictionary mein convert karta hai
            token_data = json.load(f)

        # Token data se resume aur JD nikaalo aur session state mein daalo
        # Ab sidebar mein auto-filled dikhenge — candidate ko manually paste nahi karna padega
        st.session_state['resume'] = token_data.get('resume', '')
        st.session_state['jd'] = token_data.get('jd', '')

        # Flag set karo ki token load ho chuka hai — dubara load nahi hoga
        st.session_state['token_loaded'] = True

        # Success message dikhao candidate ko
        st.success("✅ Interview data auto-loaded from your invitation link!")

    else:
        # Token file nahi mili — invalid ya expired token hai
        st.error("❌ Invalid or expired interview token. Please contact HR.")

st.title("💬 AI Interview Questions")
st.caption("Backend: question_generation_and_analyzer.py se connect karo (guide neeche)")

# Sidebar — Resume & JD input
with st.sidebar:
    st.markdown("### 📄 Setup")
    resume_text = st.text_area(
        "Resume (paste text)",
        value=st.session_state.get('resume', ''),
        height=150,
        key="resume_input",
        placeholder="Yahan resume paste karo..."
    )
    jd_text = st.text_area(
        "Job Description (paste text)",
        value=st.session_state.get('jd', ''),
        height=120,
        key="jd_input",
        placeholder="Yahan job description paste karo..."
    )
    
    if st.button("📌 Set & Start Interview"):
        st.session_state['resume'] = resume_text
        st.session_state['jd'] = jd_text
        st.session_state['messages'] = []
        st.session_state['interview_complete'] = False
        st.session_state['feedback'] = None
        st.session_state['show_feedback'] = False
        st.rerun()
    
    st.markdown("---")
    if USE_MOCK:
        st.info("🔶 **Demo mode** — Mock responses. Backend connect karne ke liye USE_MOCK = False karo.")

# Main area — Chat
resume = st.session_state['resume'] or "No resume set."
jd = st.session_state['jd'] or "No JD set."

if not resume or resume == "No resume set.":
    st.info("👈 Sidebar se Resume aur JD paste karo, phir **Set & Start Interview** click karo.")
    st.stop()

# Display chat history
messages = st.session_state.get('messages', [])
for m in messages:
    role = m.get('role', 'ai')
    content = m.get('content', str(m))
    if role == 'ai':
        st.markdown(f'<div class="chat-interviewer">**Interviewer:** {content}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="chat-candidate">**You:** {content}</div>', unsafe_allow_html=True)

# If interview complete, show feedback
if st.session_state.get('interview_complete') and st.session_state.get('feedback'):
    st.markdown("---")
    st.markdown("### 📋 Interview Analysis")
    st.markdown(f'<div class="feedback-box">{st.session_state["feedback"]}</div>', unsafe_allow_html=True)
    if st.button("🔄 Restart Interview"):
        st.session_state['messages'] = []
        st.session_state['interview_complete'] = False
        st.session_state['feedback'] = None
        st.rerun()
    st.stop()

# Input for next answer
user_input = st.chat_input("Type your answer and press Enter...")

if user_input:
    with st.spinner("Getting next question..."):
        result = call_backend(
            resume=resume,
            jd=jd,
            messages=messages,
            user_input=user_input
        )
    
    st.session_state['messages'] = result.get('messages', messages)
    st.session_state['interview_complete'] = result.get('interview_complete', False)
    if result.get('feedback'):
        st.session_state['feedback'] = result['feedback']
    
    st.rerun()

# First turn — no messages yet, get first question
if not messages:
    if st.button("▶️ Start Interview"):
        with st.spinner("Preparing first question..."):
            result = call_backend(
                resume=resume,
                jd=jd,
                messages=[],
                user_input=""  # First turn: empty = "begin interview"
            )
        st.session_state['messages'] = result.get('messages', [])
        st.session_state['interview_complete'] = result.get('interview_complete', False)
        if result.get('feedback'):
            st.session_state['feedback'] = result['feedback']
        st.rerun()
    else:
        st.markdown("👆 **Start Interview** click karo pehla question lene ke liye.")

# ═══════════════════════════════════════════════════════════════════
# BACKEND CONNECTION CHEATSHEET (expand karke dekh sakte ho)
# ═══════════════════════════════════════════════════════════════════
with st.expander("📌 Backend kaise connect karein?"):
    st.markdown("""
**1. Backend mein yeh function banao (question_generation_and_analyzer.py):**

```python
def get_next_turn(resume: str, jd: str, messages: list, user_input: str) -> dict:
    # chatnode ko user_input state se dena hoga (input() ki jagah)
    # Ek step run karo, return karo:
    # - interviewer_message (AI ka response content)
    # - messages (updated list)
    # - interview_complete (True jab len(messages) >= 6)
    # - feedback (analyzer output jab complete ho)
    ...
```

**2. Frontend mein (`interview_frontend.py`):**
- Line ~21: `USE_MOCK = False` karo
- Line ~45-50: `from question_generation_and_analyzer import get_next_turn` uncomment karo
- `return get_next_turn(resume=..., jd=..., messages=..., user_input=...)` use karo

**3. Data format backend se frontend tak:**
| Key | Type | Description |
|-----|------|-------------|
| `interviewer_message` | str | AI ka next question |
| `messages` | list | Conversation history |
| `interview_complete` | bool | 3 Q&A ho gaye? |
| `feedback` | str or None | Final analysis report |
""")
