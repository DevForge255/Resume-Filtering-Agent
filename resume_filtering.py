from langgraph.graph import StateGraph,START,END
from operator import add
from typing import TypedDict,Annotated
from typing import TypedDict,Literal
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from pydantic import BaseModel , Field
from langchain_core.documents import Document 
from langchain_chroma import Chroma 
from langchain_openai import ChatOpenAI , OpenAIEmbeddings 
from langchain_core.messages import HumanMessage ,  SystemMessage
from langchain_community.document_loaders import PyPDFLoader 
import os
from datetime import datetime, timedelta

# LangGraph checkpointer + interrupt imports
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

# json import kar rahe hain taaki feedback lists ko string format mein DB me store kar saken
import json

# Database helper functions import kar rahe hain
from candidate_db import init_db, insert_candidate_if_not_exists

# MCP Calendar client tools import — free slots + meeting booking ke liye
from mcp_client import get_free_slots, book_meeting
load_dotenv()

class ResumeResult(TypedDict):
    mail:str 
    resume_id: str
    score: int
    feedback: list[str]
    negative_feedback: list[str]
class resume_state(TypedDict):
    resumes:list[str]
    n:int
    selected_resumes: list[Document]
    JD: str
    results: Annotated[list[ResumeResult],add]
    human_review_input: str
    post_review_response: str
    tool_called: str
    tool_reason: str
    tool_result: str
    should_use_calendar: bool
    suggested_date: str
    refined_tool_output: str
    max_iterations: int

def filtering_resumes(state:resume_state):
    embedding_model=OpenAIEmbeddings(model="text-embedding-3-small")
    jd=state["JD"]
    resume=[]
    all_resumes=[]
    persistant_directory="db/chroma_db"
    if os.path.exists(persistant_directory):
        for filename in os.listdir("./resumes"):
            if filename.endswith('.pdf'):
                file_path = os.path.join("./resumes", filename)
                try:
                    # PDF load karo
                    loader = PyPDFLoader(file_path)
                    pages = loader.load()
                    full_text = "\n\n".join([page.page_content for page in pages])
                    resume_doc = Document(
                        page_content=full_text,
                        metadata={
                            'source': filename,
                            'candidate_name': filename.replace('.pdf', ''),
                            'file_path': file_path,
                            'total_pages': len(pages)
                        }
                    )
                    resume.append(full_text)
                    all_resumes.append(resume_doc)
                    
                except Exception as e:
                    print(f"✗ Error loading {filename}: {str(e)}")
        

        query=f"""Give me the candidateds which have highest similarity with this 
        Job Description {jd}"""
        # check for vector db agar h toh sirf load karo 
        vectordb=Chroma(
        embedding_function=embedding_model,
        persist_directory="db/chroma_db",
        collection_metadata={"hnsw:space":"cosine"}  )
        # Invoke the resumes then get in relavent docs
        retriever=vectordb.as_retriever(search_kwargs={"k":2})
        relavent_docs=retriever.invoke(query)

    # If the program is starting the first time then chunk it and embedd it 
    # get the resumes 
    else:
        for filename in os.listdir("./resumes"):
            if filename.endswith('.pdf'):
                file_path = os.path.join("./resumes", filename)
                print(f"Loading: {filename}")
                
                try:
                    # PDF load karo
                    loader = PyPDFLoader(file_path)
                    pages = loader.load()
                    
                    # Saare pages ko combine karo (full resume)
                    full_text = "\n\n".join([page.page_content for page in pages])
                    resumes = []

                    for resume in all_resumes:
                        resumes.append(resume.page_content)
                    # Single document banao
                    resume_doc = Document(
                        page_content=full_text,
                        metadata={
                            'source': filename,
                            'candidate_name': filename.replace('.pdf', ''),
                            'file_path': file_path,
                            'total_pages': len(pages)
                        }
                    )
                    all_resumes.append(resume_doc)
                    print(f"✓ Loaded: {filename} ({len(full_text)} characters)")
                    
                except Exception as e:
                    print(f"✗ Error loading {filename}: {str(e)}")
    

        vectordb=Chroma.from_documents(
        documents=all_resumes,
        embedding=embedding_model,
        persist_directory="db/chroma_db",
        collection_metadata={"hnsw:space":"cosine"}    )
        print("---------------------------EMBEDDINGS ARE CREATED SUCCESFULLY ------------------------------------")
        print(vectordb._collection.count())


    
    
        vectordb=Chroma(
        embedding_function=embedding_model,
        persist_directory="db/chroma_db",
        collection_metadata={"hnsw:space":"cosine"}  )
        retriever=vectordb.as_retriever(search_kwargs={"k":2})
        relavent_docs=retriever.invoke(f"""Give me the candidateds which have highest similarity with this 
        Job Description {jd}""")
    return{'selected_resumes':relavent_docs, 'resumes':resume}
     
from pydantic import BaseModel, Field

class ResumeEvaluation(BaseModel):
    candidate_name: str = Field(
        description="name of the candidate from the  resume"
    )

    score: int = Field(
        description="Overall score out of 100 based on job description match"
    )

    feedback: list[str] = Field(
        description="3-5 bullet points explaining why this score was given"
    )

    negative_feedback: list[str] = Field(
        description="Bullet points listing missing or weak areas compared to the job description"
    )
    mail:str=Field(
        description='Extract the mail from the resume '
    )


class ResumeEvaluationResult(BaseModel):
    results: list[ResumeEvaluation] = Field(
        description="Evaluation results for each resume provided"
    )

llm=ChatOpenAI(model="gpt-4o-mini")
structured_llm=llm.with_structured_output(ResumeEvaluationResult)

# Single resume evaluation ke liye dedicated structured model
structured_single_llm = llm.with_structured_output(ResumeEvaluation)


# Human instruction processing ke liye structured schema
class HumanInstructionDecision(BaseModel):
    should_use_calendar: bool = Field(description="True if HR instruction asks to check/book calendar slots")
    reason: str = Field(description="Why tool is needed or not needed")
    response_to_hr: str = Field(description="Direct response to HR instruction")
    suggested_date: str = Field(description="Preferred date in YYYY-MM-DD format if calendar check is required, else empty string")


# Structured model for post-review instruction node
structured_instruction_llm = llm.with_structured_output(HumanInstructionDecision)


# Tool output refinement ke liye structured schema
class ToolLoopDecision(BaseModel):
    has_free_slots: bool = Field(description="True if free slots are available in current tool response")
    should_book: bool = Field(description="True if booking should be attempted now")
    selected_start_time: str = Field(description="Selected start time in HH:MM format; empty if none")
    selected_end_time: str = Field(description="Selected end time in HH:MM format; empty if none")
    refined_message: str = Field(description="Human-friendly refined summary of tool output and next action")
    reason: str = Field(description="Short reason for selected action")


# Structured model for tool-loop decision/refinement
structured_tool_loop_llm = llm.with_structured_output(ToolLoopDecision)


def score_resumes(state:resume_state):
    # DB schema ensure karte hain taaki insert ke time table-missing error na aaye
    init_db()

    n=state['n']
    jd=state["JD"]
    resumes=state["selected_resumes"]

    # Guard: agar saare resumes process ho chuke hain toh no-op return karo
    if n >= len(resumes):
        return {"results": [], "n": n}

    # Current iteration mein sirf ek resume process karte hain
    current_resume_doc = resumes[n]

    # Resume text extract karte hain
    current_resume_text = current_resume_doc.page_content if hasattr(current_resume_doc, "page_content") else str(current_resume_doc)

    # Single resume ke liye focused prompt banate hain
    combined_input=f"""Input You Will Receive

Job Description – {jd}

Single Resume – {current_resume_text}

Your Task for this one resume:
1. Overall score out of 100
2. Positive matching points
3. Negative/missing points
4. Extract candidate email in the 'mail' field
"""

    # LLM messages banate hain
    messages=[
        SystemMessage(content=""" You are an experienced technical recruiter and hiring manager.
                            Evaluate exactly one resume against the given JD.
                            Be strict and evidence-based. """),
        HumanMessage(content=combined_input)
    ]

    # Single structured result lo
    evaluated_candidate = structured_single_llm.invoke(messages)

    # Positive feedback ko JSON text mein convert karo
    positive_feedback_text = json.dumps(evaluated_candidate.feedback, ensure_ascii=False)

    # Negative feedback ko JSON text mein convert karo
    negative_feedback_text = json.dumps(evaluated_candidate.negative_feedback, ensure_ascii=False)

    # DB insert (email dedupe protected)
    insert_candidate_if_not_exists(
        email=evaluated_candidate.mail,
        candidate_name=evaluated_candidate.candidate_name,
        resume_text=current_resume_text,
        resume_score=evaluated_candidate.score,
        resume_feedback=positive_feedback_text,
        negative_feedback=negative_feedback_text,
    )

    # Per-iteration result append ke liye list return karo
    return {
        "results": [
            {
                "candidate_name": evaluated_candidate.candidate_name,
                "score": evaluated_candidate.score,
                "feedback": evaluated_candidate.feedback,
                "negative_feedback": evaluated_candidate.negative_feedback,
                "mail": evaluated_candidate.mail,
            }
        ],
        "n": n + 1,
    }


# Human review interrupt node — scoring complete hone ke baad HR input ke liye pause
def human_review_interrupt(state: resume_state):
    # Shortlisted summary banate hain taaki HR ko quick context mile
    shortlist_summary = [
        {
            "candidate_name": r.get("candidate_name", "Unknown"),
            "mail": r.get("mail", ""),
            "score": r.get("score", 0),
        }
        for r in state.get("results", [])
    ]

    # Interrupt payload create karo — frontend isi message ko dikha sakta hai
    interrupt_payload = {
        "heading": "Yeh finally resume h kya me age physical meeting ke liye calender check karu and free time me book karu can i do?",
        "shortlisted": shortlist_summary,
    }

    # Graph yahin pause hoga; resume hone par yeh call user input value return karega
    user_input = interrupt(interrupt_payload)

    # User ka input state mein store karo
    return {"human_review_input": str(user_input)}


# Human instruction processing node — HR input ko understand karke tool usage decide karta hai
def process_human_instruction(state: resume_state):
    # HR input safely nikaalo
    hr_input = (state.get("human_review_input") or "").strip()

    # Shortlisted results context text banao
    result_context = "\n".join(
        [f"- {r.get('candidate_name','Unknown')} | {r.get('mail','')} | Score: {r.get('score',0)}" for r in state.get("results", [])]
    )

    # Structured decision prompt
    prompt = f"""You are an HR workflow assistant.
HR instruction: {hr_input}

Shortlisted candidates:
{result_context}

Decide whether calendar availability check tool is needed.
Return:
- should_use_calendar (true/false)
- reason
- response_to_hr
- suggested_date in YYYY-MM-DD (if needed), else empty string.
"""

    # LLM structured decision invoke karo
    decision = structured_instruction_llm.invoke([
        SystemMessage(content="You are a precise workflow planner."),
        HumanMessage(content=prompt),
    ])

    # Decision state mein store karo
    return {
        "should_use_calendar": bool(decision.should_use_calendar),
        "tool_reason": decision.reason,
        "post_review_response": decision.response_to_hr,
        "suggested_date": decision.suggested_date or "",
        "max_iterations": 3,
    }


# Tool node — MCP calendar tool call karta hai jab required ho
def run_mcp_tools_node(state: resume_state):
    # Default no-tool result
    default_result = {
        "tool_called": "none",
        "tool_result": "No MCP tool call needed for this human instruction.",
        "refined_tool_output": "No tool execution required.",
    }

    # Agar calendar tool ki need nahi hai toh seedha default return karo
    if not state.get("should_use_calendar", False):
        return default_result

    # Suggested date lo; empty ho toh today use karo
    target_date = (state.get("suggested_date") or "").strip()
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    # Max iterations strict guard — infinite behavior avoid karega
    max_iterations = int(state.get("max_iterations") or 3)
    if max_iterations < 1:
        max_iterations = 1

    # Shortlisted candidate emails attendees ke liye collect karo
    shortlisted_emails = [r.get("mail", "").strip() for r in state.get("results", []) if r.get("mail", "").strip()]
    attendees_csv = ",".join(shortlisted_emails)

    # Loop output summary tracker
    loop_logs = []

    # Strict bounded loop
    for loop_index in range(max_iterations):

        # Current date ke free slots fetch karo
        calendar_result = get_free_slots(
            date=target_date,
            duration_minutes=30,
            work_start_hour=9,
            work_end_hour=18,
            timezone_str="Asia/Kolkata",
        )

        # Agar tool error aaya toh logs me add karke return karo
        if isinstance(calendar_result, dict) and calendar_result.get("error"):
            error_text = f"Iteration {loop_index + 1}: get_free_slots error on {target_date}: {calendar_result.get('error')}"
            loop_logs.append(error_text)
            return {
                "tool_called": "get_free_slots",
                "tool_result": "\n".join(loop_logs),
                "refined_tool_output": "Calendar API error aayi; booking attempt stop kiya gaya.",
            }

        # LLM refinement prompt banao
        refine_prompt = f"""You are an operations assistant.
Human instruction: {state.get('human_review_input', '')}
Iteration: {loop_index + 1} / {max_iterations}
Date checked: {target_date}
Raw tool output (JSON-like): {calendar_result}

Decide:
1) Are free slots available?
2) Should we book now?
3) If yes, choose the best slot and provide start/end in HH:MM.
4) Provide concise refined summary message.
"""

        # LLM se structured decision lo
        loop_decision = structured_tool_loop_llm.invoke([
            SystemMessage(content="You are precise and must choose one actionable path."),
            HumanMessage(content=refine_prompt),
        ])

        # Decision log add karo
        loop_logs.append(
            f"Iteration {loop_index + 1} ({target_date}): has_free_slots={loop_decision.has_free_slots}, should_book={loop_decision.should_book}, reason={loop_decision.reason}"
        )

        # Agar booking ka decision hai aur valid times aaye hain toh meeting create karo
        if loop_decision.has_free_slots and loop_decision.should_book and loop_decision.selected_start_time and loop_decision.selected_end_time:

            # HH:MM ko ISO datetime format me convert karo
            start_iso = f"{target_date}T{loop_decision.selected_start_time}:00+05:30"
            end_iso = f"{target_date}T{loop_decision.selected_end_time}:00+05:30"

            # Meeting summary banao
            meeting_summary = "HR Discussion - Shortlisted Candidates"

            # Meeting description banao
            meeting_description = (
                "Meeting auto-booked from HR human-in-the-loop workflow. "
                f"Instruction: {state.get('human_review_input', '')}"
            )

            # Book meeting tool call karo
            booking_result = book_meeting(
                start_datetime_iso=start_iso,
                end_datetime_iso=end_iso,
                summary=meeting_summary,
                description=meeting_description,
                attendees_csv=attendees_csv,
                timezone_str="Asia/Kolkata",
            )

            # Booking response log karo
            loop_logs.append(f"Iteration {loop_index + 1}: booking_result={booking_result}")

            # Agar booked status mila toh success return karo
            if isinstance(booking_result, dict) and booking_result.get("status") == "booked":
                return {
                    "tool_called": "get_free_slots -> book_meeting",
                    "tool_result": "\n".join(loop_logs),
                    "refined_tool_output": (
                        f"{loop_decision.refined_message}\n"
                        f"Meeting booked successfully. Link: {booking_result.get('event_link', '')}"
                    ),
                }

        # Agar slot nahi mila ya booking nahi hui toh next day check karo
        next_date_dt = datetime.strptime(target_date, "%Y-%m-%d")
        target_date = (next_date_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # Max iterations exhaust hone par bounded stop response
    return {
        "tool_called": "get_free_slots",
        "tool_result": "\n".join(loop_logs),
        "refined_tool_output": "Max iterations reached. No meeting booked automatically.",
    }


def decider(state:resume_state):
    n=state["n"]
    resumes=state["selected_resumes"]
    # Jab tak pending resumes hain tab tak score_resumes loop chalao
    if n < len(resumes):
        return 'yes'
        
    else:
        return 'no'



graph=StateGraph(resume_state)
graph.add_node('filtering_resumes',filtering_resumes)
graph.add_node('score_resumes',score_resumes)
graph.add_node('human_review_interrupt', human_review_interrupt)
graph.add_node('process_human_instruction', process_human_instruction)
graph.add_node('run_mcp_tools_node', run_mcp_tools_node)
graph.add_edge(START,'filtering_resumes')
graph.add_edge('filtering_resumes','score_resumes')
graph.add_conditional_edges(
    'score_resumes',
    decider,
    {'yes': 'score_resumes', 'no': 'human_review_interrupt'}
)
graph.add_edge('human_review_interrupt', 'process_human_instruction')
graph.add_edge('process_human_instruction', 'run_mcp_tools_node')
graph.add_edge('run_mcp_tools_node', END)

# Checkpointer mandatory compile — interrupt resume stable rahega thread_id ke saath
workflow=graph.compile(checkpointer=MemorySaver())
jd=""" We are hiring a Software Engineer for a fast-growing startup who can build, ship, and own features end-to-end.
                         The role requires strong hands-on experience in at least one backend language such as Python, JavaScript (Node.js), Java, or Go, with a clear understanding of data structures, algorithms, and real-world problem solving. 
                        The candidate should be comfortable building REST APIs, working with SQL databases like PostgreSQL or MySQL and NoSQL tools such as MongoDB or Redis, and using Git in collaborative environments. Basic frontend knowledge (React or similar) is a plus but not mandatory.
                         You should have experience deploying applications using Docker, understand cloud fundamentals (AWS/GCP/Azure), and be able to debug production issues without hand-holding. We value real production work, side projects, or startup experience over degrees, grades, or certificates.
                         The ideal candidate takes ownership, learns quickly, handles ambiguity, and makes practical trade-offs under time pressure. This role is not for someone looking for comfort or rigid processes; it is for engineers who want rapid growth, responsibility, and direct impact on the product. """






