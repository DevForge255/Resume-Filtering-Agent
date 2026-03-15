import streamlit as st
from PyPDF2 import PdfReader
import docx
import pandas as pd
import os
from pathlib import Path
import uuid
import hashlib

from langgraph.types import Command

# ═══════════════════════════════════════════════════════════
# IMPORT — Sirf workflow import karo
# ═══════════════════════════════════════════════════════════
from resume_filtering import workflow,jd

# MCP Client import — email bhejne ke liye client file se functions laaye hain
# send_email: ek candidate ko email bhejta hai
# send_bulk_emails: multiple candidates ko ek saath email bhejta hai
from mcp_client import send_email, send_bulk_emails

# DB helpers import kar rahe hain taaki shortlist/table data direct database se aaye
from candidate_db import init_db, get_shortlisted_candidates, get_candidates_above_score


st.set_page_config(
    page_title="AI Resume Filterer for HR",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { padding: 0rem 1rem; }
    .app-header {
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        color: white;
        padding: 1rem 2rem;
        border-radius: 8px;
        margin-bottom: 2rem;
    }
    .app-title { font-size: 1.8rem; font-weight: 700; margin: 0; }
    .summary-card {
        background: white;
        padding: 1.5rem;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        text-align: center;
    }
    .summary-value { font-size: 2rem; font-weight: 700; color: #1e293b; }
    .summary-label {
        font-size: 0.875rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.5rem;
    }
    .stButton > button {
        background-color: #3b82f6;
        color: white;
        border-radius: 6px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        border: none;
    }
    .stButton > button:hover { background-color: #2563eb; }
</style>
""", unsafe_allow_html=True)


def save_folder_of_resumes(uploaded_files, destination_folder="./resumes"):
    """Saari PDF files ko ./resumes folder mein save karta hai"""
    Path(destination_folder).mkdir(parents=True, exist_ok=True)
    saved_names = []
    for file in uploaded_files:
        if not file.name.lower().endswith('.pdf'):
            continue
        try:
            file_path = os.path.join(destination_folder, file.name)
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
            saved_names.append(file.name)
        except Exception as e:
            st.warning(f"⚠️ Could not save {file.name}: {str(e)}")
    return saved_names


def clear_resumes_folder(folder="./resumes"):
    """./resumes ke andar ki saari files delete karta hai"""
    if os.path.exists(folder):
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.isfile(file_path):
                try:
                    os.unlink(file_path)
                except Exception as e:
                    st.warning(f"⚠️ Could not delete {filename}: {str(e)}")


def extract_jd_text(jd_file):
    """JD file se plain text nikalata hai"""
    try:
        if jd_file.name.endswith('.pdf'):
            reader = PdfReader(jd_file)
            return "\n".join(page.extract_text() for page in reader.pages)
        elif jd_file.name.endswith('.docx'):
            doc = docx.Document(jd_file)
            return "\n".join(para.text for para in doc.paragraphs)
    except Exception as e:
        st.error(f"Error reading JD: {str(e)}")
        return None


# ═══════════════════════════════════════════════════════════
# FIX — Helper function to extract strings from mixed data
#
# PROBLEM:
#   st.session_state['saved_resume_names'] mein kabhi strings
#   hote hain, kabhi Document objects (galti se save ho gaye)
#
# SOLUTION:
#   Ek helper function jo safely extract kare:
#   - Agar string hai → directly return
#   - Agar Document object hai → metadata se name nikalo
#   - Agar kuch aur hai → convert to string
# ═══════════════════════════════════════════════════════════
def get_saved_resume_names():
    """
    Session state se saved resume names safely nikalata hai.
    Handle karta hai agar galti se Document objects save ho gaye.
    
    Returns:
        list[str]: PDF filenames (strings only)
    """
    saved_data = st.session_state.get('saved_resume_names', [])
    
    if not saved_data:
        return []
    
    result = []
    for item in saved_data:
        # Case 1: Already a string (correct format)
        if isinstance(item, str):
            result.append(item)
        
        # Case 2: LangChain Document object (wrong format — fix it)
        elif hasattr(item, 'metadata') and 'source' in item.metadata:
            # Document ke metadata se filename nikalo
            result.append(item.metadata['source'])
        
        # Case 3: Kuch aur hai toh string mein convert karo
        else:
            result.append(str(item))
    
    return result


def main():

    # DB table ensure karte hain taaki fetch calls safe rahen
    init_db()

    # ═══════════════════════════════════════════════════════════
    # SESSION STATE — Yahan data store hota hai
    # ═══════════════════════════════════════════════════════════
    defaults = {
        'processed':          False,
        'results':            [],
        'saved_resume_names': [],   # ← Yeh list[str] honi chahiye (PDF filenames)
        'jd_text':            '',
        'total_resumes':      0,
        'selected_count':     0,
        'awaiting_human_review': False,
        'interrupt_payload': None,
        'thread_id': '',
        'run_id': '',
        'post_review_response': '',
        'tool_called': '',
        'tool_result': '',
        'refined_tool_output': '',
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    st.markdown("""
    <div class="app-header">
        <h1 class="app-title">AI Resume Filterer for HR</h1>
    </div>
    """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════
    # SIDEBAR
    # ═══════════════════════════════════════════════════════════
    with st.sidebar:
        st.markdown("### 📄 Upload Documents")

        # ─────────────────────────────────────────────────────────
        # STEP 1 — JD Upload & Extract
        # ─────────────────────────────────────────────────────────
        st.markdown("#### 1️⃣ Job Description")
        jd_file = st.file_uploader(
            "Upload JD (PDF / DOCX)",
            type=['pdf', 'docx'],
            key="jd_upload",
        )
        
        if jd_file is not None:
            jd_text = extract_jd_text(jd_file)
            if jd_text:
                st.session_state['jd_text'] = jd_text
                st.success(f"✅ JD loaded: {jd_file.name}")

        st.markdown("---")

        # ─────────────────────────────────────────────────────────
        # STEP 2 — Resumes Upload & Save to Disk
        # ─────────────────────────────────────────────────────────
        st.markdown("#### 2️⃣ Resumes Folder")
        st.info(
            "📁 **How to upload your full resumes folder:**\n\n"
            "1. Click **'Browse files'** below\n"
            "2. Open your **resumes folder** in the dialog\n"
            "3. Press **Ctrl+A** (Windows) / **Cmd+A** (Mac) to select all\n"
            "4. Click **Open** — all PDFs will upload at once"
        )
        resume_files = st.file_uploader(
            "Select all PDFs from your resumes folder",
            type=['pdf'],
            accept_multiple_files=True,
            key="resume_upload",
            help="Folder open karo → Ctrl+A → Open"
        )
        
        # ═══════════════════════════════════════════════════════════
        # FIX APPLIED HERE — Safe string extraction + sort
        #
        # PEHLE (line 175 mein):
        #   already_saved = sorted(st.session_state.get('saved_resume_names', []))
        #   ↑ Error: Document objects ko sort nahi kar sakte
        #
        # AB:
        #   get_saved_resume_names() → safely strings nikalta hai
        #   Phir unhe sort karta hai
        # ═══════════════════════════════════════════════════════════
        if resume_files:
            current_names = sorted([f.name for f in resume_files])
            
            # FIX: Helper function use karo — safely strings nikalta hai
            already_saved_list = get_saved_resume_names()
            already_saved = sorted(already_saved_list) if already_saved_list else []

            if current_names != already_saved:
                with st.spinner("💾 Saving PDFs to ./resumes/ ..."):
                    clear_resumes_folder()
                    saved = save_folder_of_resumes(resume_files)
                    
                    # Important: Yahan STRINGS save karo, Document objects nahi
                    st.session_state['saved_resume_names'] = saved  # saved is list[str]
                    st.session_state['total_resumes']      = len(saved)
                    
                st.success(f"✅ {len(saved)} PDF(s) saved to ./resumes/")
            else:
                st.success(f"✅ {len(already_saved)} resume(s) ready in ./resumes/")

            # FIX: Helper function use karo display ke liye bhi
            with st.expander("📋 View saved files"):
                display_names = get_saved_resume_names()
                for name in display_names:
                    st.markdown(f"• `{name}`")

        st.markdown("---")

        # ═══════════════════════════════════════════════════════════
        # STEP 3 — RUN AI FILTER BUTTON
        # ═══════════════════════════════════════════════════════════
        st.markdown("#### 3️⃣ Run Filter")
        if st.button("🔍 Run AI Filter", use_container_width=True):
            if not st.session_state.get('jd_text'):
                st.error("❌ Please upload a Job Description first")
            
            elif not get_saved_resume_names():  # FIX: Helper function use karo
                st.error("❌ Please upload your resumes folder first")
            else:
                with st.spinner("🤖 AI is filtering resumes..."):
                    try:
                        # Run ID generate karo — har run ka unique tracking ID
                        run_id = str(uuid.uuid4())

                        # JD hash banao — same JD runs ko logically group karne ke liye
                        jd_hash = hashlib.md5(st.session_state['jd_text'].encode('utf-8')).hexdigest()[:10]

                        # Thread ID banao: pipeline + jd hash + run id
                        thread_id = f"resume_filter|jd_{jd_hash}|run_{run_id}"

                        # LangGraph config with thread_id
                        graph_config = {"configurable": {"thread_id": thread_id}}

                        # ← GRAPH INPUT
                        initial_state = {
                            "selected_resumes": [],
                            "n":                0,
                            "results":          [],
                            "JD":               st.session_state['jd_text'],
                            "resumes":          [],
                            "human_review_input": "",
                            "post_review_response": "",
                            "tool_called": "",
                            "tool_reason": "",
                            "tool_result": "",
                            "refined_tool_output": "",
                            "should_use_calendar": False,
                            "suggested_date": "",
                            "max_iterations": 3,
                        }
                        
                        # ← GRAPH INVOKE
                        output = workflow.invoke(initial_state, config=graph_config)

                        # NOTE:
                        # get_state() call kuch runtime sessions me "No checkpointer set" raise kar raha tha.
                        # Isliye primary source ke roop me invoke output use kar rahe hain.
                        # Agar output dict nahi ho toh safe fallback empty dict lenge.
                        state_values = output if isinstance(output, dict) else {}
                        
                        # → GRAPH OUTPUT
                        st.session_state['results']        = state_values.get('results', [])
                        st.session_state['processed']      = True
                        st.session_state['total_resumes']  = len(state_values.get('resumes', []))
                        st.session_state['selected_count'] = len(state_values.get('selected_resumes', []))

                        # selected_resumes ko session state mein save karo — email bhejte waqt resume text chahiye
                        # Yeh LangChain Document objects hain — inme .page_content mein resume text hota hai
                        st.session_state['selected_resumes_docs'] = state_values.get('selected_resumes', [])

                        # Thread/run tracking store karo
                        st.session_state['thread_id'] = thread_id
                        st.session_state['run_id'] = run_id

                        # Agar graph interrupt hua hai toh HITL input ka wait state set karo
                        if "__interrupt__" in output:
                            st.session_state['awaiting_human_review'] = True
                            interrupt_list = output.get("__interrupt__", [])
                            if interrupt_list and hasattr(interrupt_list[0], "value"):
                                st.session_state['interrupt_payload'] = interrupt_list[0].value
                            else:
                                st.session_state['interrupt_payload'] = {
                                    "heading": "Yeh finally resume h kya me age physical meeting ke liye calender check karu and free time me book karu can i do?"
                                }
                        else:
                            st.session_state['awaiting_human_review'] = False
                            st.session_state['interrupt_payload'] = None

                        # JD text bhi save karo — token generate karte waqt chahiye hoga
                        # st.session_state['jd_text'] already set hai sidebar se
                        
                        st.success("✅ Done!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Processing error: {str(e)}")

    # ═══════════════════════════════════════════════════════════
    # HUMAN-IN-THE-LOOP INPUT PANEL — interrupt ke baad HR input yahan liya jaata hai
    # ═══════════════════════════════════════════════════════════
    if st.session_state.get('awaiting_human_review'):
        st.markdown("---")

        # Interrupt payload se heading lo; fallback fixed heading rakho
        interrupt_payload = st.session_state.get('interrupt_payload') or {}
        panel_heading = interrupt_payload.get(
            "heading",
            "Yeh finally resume h kya me age physical meeting ke liye calender check karu and free time me book karu can i do?"
        )

        st.markdown(f"### {panel_heading}")

        # HR instruction input
        human_review_text = st.text_area(
            "Human instruction",
            key="human_review_input_box",
            placeholder="Example: Haan, calendar check karo aur next 3 free slots suggest karo.",
            height=120,
        )

        # Resume graph button — same thread_id ke saath Command(resume=...) pass karega
        if st.button("✅ Submit Human Input & Continue Graph", use_container_width=True):
            if not human_review_text.strip():
                st.warning("⚠️ Please enter human instruction before continuing.")
            else:
                try:
                    # Existing thread_id fetch karo
                    thread_id = st.session_state.get('thread_id', '')
                    graph_config = {"configurable": {"thread_id": thread_id}}

                    # Interrupt resume karo with human input
                    resumed_output = workflow.invoke(Command(resume=human_review_text.strip()), config=graph_config)

                    # Resume invoke output ko hi state source use karo (get_state dependency avoid)
                    state_values = resumed_output if isinstance(resumed_output, dict) else {}

                    # Post-review fields store karo UI display ke liye
                    st.session_state['post_review_response'] = state_values.get('post_review_response', '')
                    st.session_state['tool_called'] = state_values.get('tool_called', '')
                    st.session_state['tool_result'] = state_values.get('tool_result', '')
                    st.session_state['refined_tool_output'] = state_values.get('refined_tool_output', '')

                    # HITL wait state off karo
                    st.session_state['awaiting_human_review'] = False
                    st.session_state['interrupt_payload'] = None

                    st.success("✅ Human instruction processed. Graph completed.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to continue graph after human input: {str(e)}")

    # Final output panel — sirf green structured output dikhana hai
    # Raw tool logs, tool name, aur verbose execution details intentionally hide kiye gaye hain
    final_structured_output = st.session_state.get('refined_tool_output') or st.session_state.get('post_review_response')

    if final_structured_output:
        st.markdown("---")
        st.success(final_structured_output)

        st.markdown("---")
        st.checkbox("Show Explain", value=True)

        if st.button("🗑️ Clear Results", use_container_width=True):
            st.session_state['processed']          = False
            st.session_state['results']            = []
            st.session_state['saved_resume_names'] = []
            st.session_state['total_resumes']      = 0
            st.session_state['selected_count']     = 0
            st.rerun()

    # ═══════════════════════════════════════════════════════════
    # MAIN CONTENT AREA
    # ═══════════════════════════════════════════════════════════
    st.markdown("### 📊 Filters Summary")
    st.markdown("#### Summary")

    summary_cols = st.columns(4)
    total_resumes = st.session_state.get('total_resumes', 0)

    # Shortlisted count ab database se derive hoga (source of truth DB hai)
    shortlisted_rows = get_shortlisted_candidates(70)
    shortlisted = len(shortlisted_rows)

    # Final selected count bhi database se derive hoga (interview complete + score2 > 85)
    final_selected_rows = get_candidates_above_score(85)
    final_selected_count = len(final_selected_rows)

    with summary_cols[0]:
        st.markdown(f"""
        <div class="summary-card">
            <div class="summary-label">Total Resumes Uploaded</div>
            <div class="summary-value">{total_resumes}</div>
        </div>""", unsafe_allow_html=True)

    with summary_cols[1]:
        st.markdown(f"""
        <div class="summary-card">
            <div class="summary-label">Shortlisted for Interview</div>
            <div class="summary-value">{shortlisted}</div>
        </div>""", unsafe_allow_html=True)

    with summary_cols[2]:
        st.markdown(f"""
        <div class="summary-card">
            <div class="summary-label">Final Selected (Score2 &gt; 85)</div>
            <div class="summary-value">{final_selected_count}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🎯 Candidate Results")

    # Shortlist button + Bulk Email button — dono ek row mein
    btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 4])
    
    with btn_col1:
        shortlist_clicked = st.button(
            "📋 Shortlist",
            use_container_width=True,
            key="shortlist_btn"
        )

    # ──────────────────────────────────────────────────────────────
    # BULK EMAIL BUTTON — Saare selected candidates ko ek click mein email bhejta hai
    # Sirf score >= 70 wale candidates ko email jaayegi
    # ──────────────────────────────────────────────────────────────
    with btn_col2:
        bulk_email_clicked = st.button(
            "📧 Email All Selected",       # Button ka label
            use_container_width=True,       # Button poori column width le
            key="bulk_email_btn"            # Unique key — Streamlit ko har button identify karne ke liye chahiye
        )

    if shortlist_clicked:
        if not shortlisted_rows:
            st.warning("⚠️ No shortlisted candidates found in database yet")
        else:
            st.info(f"📋 {len(shortlisted_rows)} candidates shortlisted (score ≥ 70%) from database")

    # ──────────────────────────────────────────────────────────────
    # BULK EMAIL LOGIC — jab "Email All Selected" button click ho
    # Ab token generate karke interview link bhi email mein jaayegi
    # ──────────────────────────────────────────────────────────────
    if bulk_email_clicked:

        # Check karo ki results available hain ya nahi
        # Shortlisted candidates direct DB se fetch karo
        selected_candidates_rows = get_shortlisted_candidates(70)

        if not selected_candidates_rows:
            st.warning("⚠️ No shortlisted candidates found in database for email sending")
        else:

            # DB rows ko send_bulk_emails input format mein map karo
            selected_candidates = [
                {
                    'mail': row['email'],
                    'candidate_name': row['candidate_name'],
                    'resume_text': row['resume_text'] or 'Resume text not available',
                    'score': row['resume_score'] if row['resume_score'] is not None else 'N/A'
                }
                for row in selected_candidates_rows
            ]

            # Check karo ki koi selected candidate hai bhi ya nahi
            if not selected_candidates:
                st.warning("⚠️ No candidates with score ≥ 70% to send emails to.")
            else:
                # JD text session state se lo — sabke token mein same JD jaayega
                jd_text = st.session_state.get('jd_text', 'Job description not available')

                # Spinner dikhao — user ko pata chale emails bhej rahe hain
                with st.spinner(f"📧 Sending emails with interview links to {len(selected_candidates)} candidates..."):

                    # MCP Client ka bulk email function call karo — ab jd_text bhi pass karo
                    bulk_results = send_bulk_emails(selected_candidates, jd_text)

                # Har candidate ka result dikhao
                for r in bulk_results:

                    # Email successfully gayi toh green success message — interview link bhi dikhao
                    if r['status'] == 'sent':
                        st.success(f"✅ Email sent to {r['name']} ({r['email']})")
                        # Agar interview_link available hai toh dikhao
                        if 'interview_link' in r:
                            st.caption(f"🔗 Interview link: {r['interview_link']}")

                    # Email fail hui toh red error message
                    else:
                        st.error(f"❌ Failed: {r['name']} ({r['email']}): {r['response']}")

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════
    # → DATABASE OUTPUT DISPLAY: Shortlisted + Final selected tables
    # ═══════════════════════════════════════════════════════════
    # Candidate list display ab database based hai (session results par dependent nahi)
    db_shortlisted_rows = get_shortlisted_candidates(70)
    db_final_selected_rows = get_candidates_above_score(85)

    if db_shortlisted_rows:

        formatted_data = []

        # DB rows ko table-friendly dict format mein convert karo
        for r in db_shortlisted_rows:
            formatted_data.append({
                "Candidate": r['candidate_name'] or '—',
                "Email":     r['email'] or '—',
                "Status":    "✅ Selected",
                "Score":     f"{r['resume_score']}%" if r['resume_score'] is not None else "—",
                "Feedback":  "From database",
                "ResumeText": r['resume_text'] or "Resume text not available"
            })

        df = pd.DataFrame(formatted_data)
        st.markdown(f"#### 📋 Shortlisted for Interview ({len(db_shortlisted_rows)})")

        # Header — 6 columns: 5 data + 1 email button ke liye
        header = st.columns([3, 3, 2, 2, 4, 2])
        header[0].markdown("**Candidate**")
        header[1].markdown("**Email**")
        header[2].markdown("**Status**")
        header[3].markdown("**Score**")
        header[4].markdown("**Feedback**")
        header[5].markdown("**Action**")   # Naya column — email button ke liye
        st.markdown("---")

        # ──────────────────────────────────────────────────────────────
        # CANDIDATE ROWS — Har row mein individual Send Email button
        # ──────────────────────────────────────────────────────────────
        for idx, row in df.iterrows():

            # 6 columns — original 5 + 1 naya email button ke liye
            cols = st.columns([3, 3, 2, 2, 4, 2])

            # Column 1: Candidate ka naam — bold
            cols[0].markdown(f"**{row['Candidate']}**")

            # Column 2: Candidate ka email address
            cols[1].markdown(row['Email'])

            # Column 3: Selected ya Rejected status
            cols[2].markdown(row['Status'])

            # Column 4: Match score percentage — bold
            cols[3].markdown(f"**{row['Score']}**")

            # Column 5: Top feedback points
            cols[4].markdown(row['Feedback'])

            # ──────────────────────────────────────────────────────────
            # Column 6: INDIVIDUAL SEND EMAIL BUTTON WITH INTERVIEW LINK
            # Har candidate ke liye alag button — token generate karke interview link wali email bhejta hai
            # ──────────────────────────────────────────────────────────
            with cols[5]:

                # key=f"send_{idx}" — har button ka unique ID hona chahiye warna Streamlit error dega
                # help — hover karne pe tooltip dikhata hai
                if st.button("📧", key=f"send_{idx}", help=f"Send email to {row['Candidate']}"):

                    # Check karo ki email address available hai ya nahi
                    if row['Email'] == '—' or not row['Email']:
                        st.warning(f"⚠️ No email found for {row['Candidate']}")
                    else:

                        # Resume text ab direct DB table se hi aayega
                        resume_text = row['ResumeText']

                        # JD text session state se lo
                        jd_text = st.session_state.get('jd_text', 'Job description not available')

                        # Spinner dikhao jab tak token + email ja rahi hai
                        with st.spinner(f"Generating interview link & sending to {row['Candidate']}..."):

                            # MCP Client ka send_email function call karo
                            # Ab resume_text aur jd_text bhi pass ho raha hai — token generate hoga
                            result = send_email(
                                recipient_email='devforge72@gmail.com',
                                candidate_name=row['Candidate'],
                                resume_text=resume_text,    # Candidate ka resume — token mein save hoga
                                jd_text=jd_text             # JD — token mein save hoga
                            )

                        # Result text normalize karte hain taaki success/error consistently detect ho
                        result_text = str(result)

                        # Agar known failure pattern ho toh red error dikhayein, warna success
                        if result_text.startswith("Failed to send email") or result_text.startswith("Token generation failed"):
                            st.error(f"❌ Could not send interview invitation to {row['Email']}: {result_text}")
                        else:
                            st.success(f"✅ Interview invitation sent to {row['Email']}")

            # Har row ke baad horizontal separator line
            st.markdown("---")

    # Final selected table — sirf interview complete + score2 > 85 wale candidates
    if db_final_selected_rows:

        final_selected_data = []

        # DB rows ko table-friendly dict format mein convert karo
        for candidate_row in db_final_selected_rows:
            final_selected_data.append({
                "Candidate": candidate_row['candidate_name'] or '—',
                "Email": candidate_row['email'] or '—',
                "Interview Status": "✅ Completed" if candidate_row['interview_status'] == 1 else "❌ Pending",
                "Score2": f"{candidate_row['score2']}%" if candidate_row['score2'] is not None else '—',
                "Overall Feedback": candidate_row['overall_feedback'] or '—'
            })

        final_df = pd.DataFrame(final_selected_data)
        st.markdown("---")
        st.markdown(f"#### 🏆 Final Selected Resumes (Score2 > 85) ({len(db_final_selected_rows)})")

        # Header — same tabular manner mein columns render kar rahe hain
        final_header = st.columns([3, 3, 2, 2, 6])
        final_header[0].markdown("**Candidate**")
        final_header[1].markdown("**Email**")
        final_header[2].markdown("**Interview Status**")
        final_header[3].markdown("**Score2**")
        final_header[4].markdown("**Overall Feedback**")
        st.markdown("---")

        # Table rows render karte hain same row-wise style mein
        for _, final_row in final_df.iterrows():
            final_cols = st.columns([3, 3, 2, 2, 6])
            final_cols[0].markdown(f"**{final_row['Candidate']}**")
            final_cols[1].markdown(final_row['Email'])
            final_cols[2].markdown(final_row['Interview Status'])
            final_cols[3].markdown(f"**{final_row['Score2']}**")
            final_cols[4].markdown(final_row['Overall Feedback'])
            st.markdown("---")
    else:
        st.info("ℹ️ Final selected list अभी empty है — interview complete hone ke baad score2 > 85 candidates yahan dikhenge.")

    # Agar dono lists empty hain toh combined helper message dikhao
    if not db_shortlisted_rows and not db_final_selected_rows:
        st.info("👆 Upload JD + Resumes folder, then click **🔍 Run AI Filter** (sidebar mein)")


if __name__ == "__main__":
    main()


# ═══════════════════════════════════════════════════════════
# ERROR FIX SUMMARY
# ═══════════════════════════════════════════════════════════
#
# PROBLEM:
#   Line 175: already_saved = sorted(st.session_state.get('saved_resume_names', []))
#   Error: TypeError — Document objects ko sort nahi kar sakte
#
# ROOT CAUSE:
#   Kisi jagah galti se 'saved_resume_names' mein LangChain
#   Document objects save ho gaye the instead of strings
#
# FIX:
#   1. get_saved_resume_names() helper function banaya (line 105-136)
#      - Safely strings extract karta hai
#      - Document objects ko bhi handle karta hai
#      - Type-safe conversion
#
#   2. Har jagah jahan 'saved_resume_names' access ho raha tha:
#      - Line 217: already_saved_list = get_saved_resume_names()
#      - Line 228: display_names = get_saved_resume_names()
#      - Line 240: elif not get_saved_resume_names()
#
#   3. Ensure kiya ki save karte waqt sirf strings jaayein:
#      - Line 222: st.session_state['saved_resume_names'] = saved
#        (saved is list[str] from save_folder_of_resumes)
#
# RESULT:
#   Ab chahe kuch bhi ho session state mein, sort() kabhi fail
#   nahi hoga — helper function safely handle kar lega
# ═══════════════════════════════════════════════════════════