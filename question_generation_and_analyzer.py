from langgraph.graph import StateGraph,START,END
from typing import TypedDict,Annotated
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage , SystemMessage,HumanMessage,AIMessage
from langgraph.graph.message import add_messages

# re import karte hain taaki feedback text se score/email regex se extract kar saken
import re

# Optional import karte hain taaki helper return types explicit rahen
from typing import Optional

# Database update helper import kar rahe hain analyzer output persist karne ke liye
from candidate_db import init_db, update_interview_result
load_dotenv()



class question_state(TypedDict):
    jd:str
    score:int
    resume:str
    feedback:str
    user_input:str  # Frontend se aayega — input() ki jagah
    messages: Annotated[list[BaseMessage], add_messages]
llm=ChatOpenAI(model='gpt-4o-mini')

from pydantic import BaseModel, Field

class ResumeEvaluation(BaseModel):
    score: int = Field(
        description="Overall score out of 100 based on job description match"
    )
# ═══════════════════════════════════════════════════════════════════
# FRONTEND SE CONNECT HONE WALA FUNCTION
# ═══════════════════════════════════════════════════════════════════
def get_next_turn(resume: str, jd: str, messages: list, user_input: str) -> dict:
    """
    Frontend se call hota hai — ek turn run karta hai.
    
    Args:
        resume: Candidate ka resume text
        jd: Job description text
        messages: List of dicts [{'role': 'human'/'ai', 'content': '...'}]
        user_input: User ka current answer (empty string for first turn)
    
    Returns:
        dict with keys: interviewer_message, messages, interview_complete, feedback
    """
    # Step 1: Convert dict messages to LangChain format
    langchain_messages = []
    for m in messages:
        if m['role'] == 'human':
            langchain_messages.append(HumanMessage(content=m['content']))
        else:
            langchain_messages.append(AIMessage(content=m['content']))
    
    # Step 2: Agar user_input hai toh add karo
    if user_input:
        langchain_messages.append(HumanMessage(content=user_input))
    
    # Step 3: Check if interview complete (6 messages = 3 Q&A pairs)
    if len(langchain_messages) >= 6:
        # Analyzer call karo
        analysis = _run_analyzer(resume, jd, langchain_messages)
        
        # Convert back to dict format
        dict_messages = _to_dict_messages(langchain_messages)
        
        return {
            'interviewer_message': '',
            'messages': dict_messages,
            'interview_complete': True,
            'feedback': analysis
        }
    
    # Step 4: Next question generate karo
    ai_response = _generate_question(resume, jd, langchain_messages, user_input)
    
    # Add AI response to messages
    langchain_messages.append(AIMessage(content=ai_response))
    
    # Convert back to dict format
    dict_messages = _to_dict_messages(langchain_messages)
    
    return {
        'interviewer_message': ai_response,
        'messages': dict_messages,
        'interview_complete': False,
        'feedback': None
    }


def _to_dict_messages(langchain_messages: list) -> list:
    """LangChain messages ko dict format mein convert karta hai."""
    result = []
    for m in langchain_messages:
        if isinstance(m, HumanMessage):
            result.append({'role': 'human', 'content': m.content})
        elif isinstance(m, AIMessage):
            result.append({'role': 'ai', 'content': m.content})
    return result


def _generate_question(resume: str, jd: str, messages: list, user_input: str) -> str:
    """LLM se ek question generate karta hai."""
    prompt = _build_interview_prompt(resume, jd, messages)
    
    # Agar user_input hai toh uske saath invoke karo, warna empty start
    if user_input:
        response = llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=user_input)
        ])
    else:
        response = llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Please start the interview. Greet me and ask your first question.")
        ])
    
    return response.content


def _run_analyzer(resume: str, jd: str, messages: list) -> str:
    """Interview complete hone par analysis run karta hai."""
    state = {
        'resume': resume,
        'jd': jd,
        'messages': messages,
    }
    result = analyzer(state)
    return result.get('feedback', 'Analysis not available.')


def _build_interview_prompt(resume: str, jd: str, messages: list) -> str:
    """Interview prompt build karta hai — chatnode wala same prompt."""
    return f"""You are an experienced HR interviewer conducting a professional job interview. You will ask questions based on the candidate's resume and the job description provided.

**YOUR ROLE:**
- Act as a professional, friendly HR interviewer
- Ask thoughtful, relevant questions about the candidate's experience and skills
- Listen carefully to responses and ask follow-up questions to examine their knowledge depth
- Maintain a conversational, interactive tone
- Be encouraging but thorough in your assessment

**INTERVIEW STRUCTURE:**

1. **Initial Questions (3 questions):**
   - Analyze the resume and job description carefully
   - Generate 3 relevant questions that test:
     * Technical skills mentioned in resume vs required in JD
     * Past experience and accomplishments
     * Problem-solving abilities related to the role
   - Ask ONE question at a time, wait for response

2. **Follow-up Questions (1-2 questions based on answers):**
   - Based on the candidate's answer, ask 1-2 deeper follow-up questions
   - Only ask follow-ups if the answer requires deeper examination

**GUIDELINES:**
- Keep questions professional and relevant to the role
- Don't ask all questions at once - ONE question per message
- Be conversational and acknowledge answers before asking next question
- Track which questions you've asked to avoid repetition

**RESUME:**
{resume}

**JOB DESCRIPTION:**
{jd}

**CONVERSATION HISTORY:**
{messages}

**INSTRUCTIONS:**
- If this is the start of interview: Greet warmly and ask your FIRST question only
- If candidate has answered: Acknowledge their answer briefly, then ask next question
- Keep your response concise - one question at a time
- Maintain professional yet friendly tone

Now, continue the interview based on the conversation so far."""


# ═══════════════════════════════════════════════════════════════════
# ORIGINAL LANGGRAPH CODE (terminal mode — direct run ke liye)
# ═══════════════════════════════════════════════════════════════════

def chatnode(state: question_state):
    user_query = state.get('user_input', '') or input("Enter Your answer: ")
    messages = state['messages']
    prompt=f"""You are an experienced HR interviewer conducting a professional job interview. You will ask questions based on the candidate's resume and the job description provided.

**YOUR ROLE:**
- Act as a professional, friendly HR interviewer
- Ask thoughtful, relevant questions about the candidate's experience and skills
- Listen carefully to responses and ask follow-up questions to examine their knowledge depth
- Maintain a conversational, interactive tone
- Be encouraging but thorough in your assessment

**INTERVIEW STRUCTURE:**

1. **Initial Questions (3 questions):**
   - Analyze the resume and job description carefully
   - Generate 3 relevant questions that test:
     * Technical skills mentioned in resume vs required in JD
     * Past experience and accomplishments
     * Problem-solving abilities related to the role
   - Ask ONE question at a time, wait for response

2. **Follow-up Questions (1-2 questions based on answers):**
   - Based on the candidate's answer, ask 1-2 deeper follow-up questions to:
     * Clarify vague or incomplete answers
     * Test technical depth and practical knowledge
     * Understand their thought process
     * Assess real-world application of their skills
   - Only ask follow-ups if the answer requires deeper examination

**GUIDELINES:**
- Keep questions professional and relevant to the role
- Don't ask all questions at once - ONE question per message
- Wait for candidate's response before moving to next question
- Be conversational: "That's interesting, can you tell me more about..."
- Acknowledge good answers: "Great, I appreciate that detail..."
- If answer is unclear: "Could you elaborate on..."
- Track which questions you've asked to avoid repetition

**RESUME:**
{resume}

**JOB DESCRIPTION:**
{jd}

**CONVERSATION HISTORY:**
{messages}

**INSTRUCTIONS:**
- If this is the start of interview: Greet warmly and ask your FIRST question only
- If candidate has answered: Acknowledge their answer briefly, then either:
  * Ask a follow-up question (1-2) to examine their knowledge deeper
  * Move to next main question if satisfied with the answer
- Keep your response concise - one question at a time
- Maintain professional yet friendly tone

Now, continue the interview based on the conversation so far."""
    # Prompt
    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=user_query)
    ])
    
    print(f"\nInterviewer: {response.content}\n")
    
    # ✅ Return new messages - LangGraph append karega
    return {
        'messages': [
            HumanMessage(content=user_query),
            response
        ]
    }

# Decider - Loop control
def decider(state: question_state):
    messages = state['messages']
    
    if len(messages) >= 6:  # 3 Q&A pairs
        return 'yes'
    else:
        return 'no'


# _extract_email_from_resume helper resume text se first valid email nikaalta hai
def _extract_email_from_resume(resume_text: str) -> Optional[str]:
    # Regex pattern define karte hain jo common email formats ko match karega
    email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

    # findall se resume text mein saare email matches nikaalte hain
    matched_emails = re.findall(email_pattern, resume_text or "")

    # Agar koi email mila hai toh pehla normalized email return karte hain
    if matched_emails:
        return matched_emails[0].strip().lower()

    # Agar email na mile toh None return karte hain
    return None


# _extract_score_from_feedback helper analyzer feedback text se score2 निकालता है
def _extract_score_from_feedback(feedback_text: str) -> Optional[int]:
    # Text ko empty-safe banate hain taaki regex call crash na kare
    safe_text = feedback_text or ""

    # Pattern 0: strict line format "SCORE: 86/100" detect karo (highest priority)
    pattern_score_line = re.search(r"score\s*[:\-]\s*(\d{1,3})(?:\s*/\s*100)?", safe_text, flags=re.IGNORECASE)

    # Agar strict score line mil gayi toh directly parse karke return karo
    if pattern_score_line:
        parsed_score = int(pattern_score_line.group(1))
        return max(0, min(parsed_score, 100))

    # Pattern 1: "85/100" jaisa format detect karte hain
    pattern_with_100 = re.search(r"(\d{1,3})\s*/\s*100", safe_text, flags=re.IGNORECASE)

    # Agar first pattern match ho gaya toh directly score parse karte hain
    if pattern_with_100:
        parsed_score = int(pattern_with_100.group(1))
        return max(0, min(parsed_score, 100))

    # Pattern 2: "score: 88" ya "Score - 88" type formats detect karte hain
    pattern_named_score = re.search(r"score[^0-9]{0,20}(\d{1,3})", safe_text, flags=re.IGNORECASE)

    # Agar second pattern match ho gaya toh usko parse karke 0-100 range me clamp karte hain
    if pattern_named_score:
        parsed_score = int(pattern_named_score.group(1))
        return max(0, min(parsed_score, 100))

    # Koi score pattern na mile toh None return karte hain
    return None

# Graph - LangGraph ka loop
def analyzer(state: question_state):
    """Analyzes interview and provides hiring recommendation"""

    # DB schema ensure karte hain taaki update query fail na ho
    init_db()
    
    messages = state['messages']
    jd = state['jd']
    resume = state['resume']
    
    # Short, focused prompt
    ANALYZER_PROMPT = f"""You are an experienced HR Manager analyzing a candidate's interview performance. Your task is to provide a comprehensive evaluation and make a hiring recommendation.

**YOUR ROLE:**
- Analyze the candidate's responses during the interview
- Compare their answers against job requirements
- Assess technical knowledge, communication skills, and cultural fit
- Make a clear recommendation: whether to proceed with a live interview or not

**EVALUATION CRITERIA:**

1. **Technical Competence (40%)**
   - Does the candidate demonstrate required technical skills from JD?
   - Are their answers detailed and show practical experience?
   - Do they understand concepts mentioned in their resume?

2. **Relevant Experience (30%)**
   - Does their past experience align with job requirements?
   - Can they articulate their achievements clearly?
   - Are their projects/roles relevant to this position?

3. **Communication & Clarity (20%)**
   - Are responses clear and well-structured?
   - Do they provide specific examples?
   - Can they explain complex concepts simply?

4. **Problem-Solving & Depth (10%)**
   - Do they show analytical thinking?
   - Can they handle follow-up questions well?
   - Do they demonstrate depth of knowledge?
5. ALso give the score on the basis of above criteria out of 100 and give a detailed justification for the score.

**RESUME:**
{resume}

**JOB DESCRIPTION:**
{jd}

**INTERVIEW CHAT HISTORY:**
{messages}

**YOUR ANALYSIS MUST INCLUDE:**

1. **Performance Summary (2-3 sentences)**
   - Overall impression of the candidate
   - Key strengths observed

2. **Detailed Evaluation:**
   - **Technical Skills Assessment:** How well do their answers match JD requirements? (Rate: Strong/Moderate/Weak)
   - **Experience Relevance:** Are their past roles aligned with this position? (Rate: Highly Relevant/Somewhat Relevant/Not Relevant)
   - **Communication Quality:** How clear and professional were their responses? (Rate: Excellent/Good/Needs Improvement)
   - **Knowledge Depth:** Did they demonstrate deep understanding in follow-up questions? (Rate: Deep/Adequate/Shallow)

3. **Key Strengths:** (2-3 bullet points)
   - Specific positive aspects from their interview responses

4. **Areas of Concern:** (2-3 bullet points)
   - Any gaps, weak answers, or red flags noticed
   - If none, mention "No major concerns identified"

5. **Gap Analysis:**
   - Skills mentioned in JD but not demonstrated in interview
   - Any discrepancies between resume claims and interview answers

6. **Final Recommendation:**
   - **PROCEED TO LIVE INTERVIEW** - If candidate shows strong potential (70%+ match with requirements)
   - **REJECT** - If significant gaps or misalignment with role (below 50% match)
   - **BORDERLINE - CONSIDER WITH CAUTION** - If some concerns but worth exploring (50-70% match)

7. **Recommendation Justification:** (2-3 sentences)
   - Clear reasoning for your decision
   - What you want to explore further in live interview (if proceeding)
   - OR why candidate isn't a good fit (if rejecting)
8. Display the score out of 100 based on the evaluation criteria mentioned above.
**FORMAT YOUR RESPONSE AS:**
```
CANDIDATE ANALYSIS REPORT
=======================

PERFORMANCE SUMMARY:
[Your 2-3 sentence summary]

DETAILED EVALUATION:
- Technical Skills: [Strong/Moderate/Weak] - [Brief explanation]
- Experience Relevance: [Highly Relevant/Somewhat Relevant/Not Relevant] - [Brief explanation]
- Communication Quality: [Excellent/Good/Needs Improvement] - [Brief explanation]
- Knowledge Depth: [Deep/Adequate/Shallow] - [Brief explanation]

KEY STRENGTHS:
- [Strength 1]
- [Strength 2]
- [Strength 3]

AREAS OF CONCERN:
- [Concern 1 or "No major concerns"]
- [Concern 2 if applicable]

GAP ANALYSIS:
[List any skills from JD not demonstrated, or note "All key requirements addressed"]

FINAL RECOMMENDATION: [PROCEED TO LIVE INTERVIEW / REJECT / BORDERLINE]

JUSTIFICATION:
[Your 2-3 sentence reasoning]
```

**IMPORTANT GUIDELINES:**
- Be objective and evidence-based
- Reference specific answers from chat history
- Don't be overly harsh or lenient - be realistic
- Focus on job requirements, not personal biases
- If recommending live interview, suggest specific areas to probe deeper
ALSo mention the score out of 100 based on the evaluation criteria and provide a detailed justification for the score.
MANDATORY: Start your response with a separate line exactly in this format:
SCORE: <number>/100
Example: SCORE: 84/100
Now, analyze the interview and provide your detailed assessment."""
    
    # Call LLM
    response = llm.invoke([SystemMessage(content=ANALYZER_PROMPT)])

    # LLM response content ko normalized feedback text variable me store karte hain
    overall_feedback_text = response.content or ""

    # Feedback text se score2 extract karte hain (e.g., "86/100" -> 86)
    extracted_score2 = _extract_score_from_feedback(overall_feedback_text)

    # Resume text se candidate ka email extract karte hain DB update key ke liye
    candidate_email = _extract_email_from_resume(resume)

    # Agar candidate email mila hai toh DB me interview result update karte hain
    if candidate_email:
        update_interview_result(
            email=candidate_email,
            score2=extracted_score2,
            overall_feedback=overall_feedback_text,
        )
    else:
        # Debug print — email missing hone par DB update nahi hoga
        print("[Analyzer DB Update] Resume text se email extract nahi hua, score2 update skip hua.")
    
    # Print analysis
    print("\n" + "="*60)
    print("INTERVIEW ANALYSIS")
    print("="*60)
    print(response.content)
    print("="*60 + "\n")
    
    return {
        # Feedback same format me return karte hain taaki frontend flow break na ho
        'feedback': overall_feedback_text
    }

graph=StateGraph(question_state)
graph.add_node('chatnode',chatnode)
graph.add_node('analyzer',analyzer)
graph.add_edge(START, 'chatnode')
graph.add_conditional_edges(
    'chatnode',
    decider,
    {'yes': 'analyzer', 'no': 'chatnode'}  # ← Yeh loop hai!
)
graph.add_edge('analyzer',END)

workflow=graph.compile()


# ═══════════════════════════════════════════════════════════════════
# DIRECT TERMINAL MODE — sirf tab chalega jab file directly run karo
# Frontend import kare toh yeh nahi chalega
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    resume="""
PRIYA PATEL 
       priya.patel@email.com |          +91-99887-76543 |      linkedin.com/in/priyapatel |       
github.com/priyapatel 
 
PROFESSIONAL SUMMARY 
Results-driven Backend Developer with 3+ years of experience designing and 
implementing scalable microservices architectures. Expert in Python and Java with 
strong focus on API development, database optimization, and cloud infrastructure. 
Proven track record of improving system performance and reducing operational costs. 
TECHNICAL SKILLS 
Languages: Python, Java, Go, SQL, JavaScript 
Frameworks: Django, Flask, Spring Boot, FastAPI 
Database: PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch 
Cloud & DevOps: AWS (EC2, S3, Lambda, RDS), Docker, Kubernetes, Jenkins, 
Terraform 
Tools: Git, JIRA, Kafka, RabbitMQ, Grafana, New Relic 
PROFESSIONAL EXPERIENCE 
Backend Developer | InfoTech Solutions Pvt Ltd, Bangalore 
July 2022 - Present 
• Designed and developed RESTful APIs serving 500K+ daily active users with 
99.9% uptime 
• Optimized database queries reducing response time by 40% and improving overall 
system performance 
• Implemented microservices architecture using Docker and Kubernetes, improving 
deployment efficiency by 60% 
• Led migration of monolithic application to serverless architecture on AWS Lambda, 
reducing costs by 35% 
• Mentored 2 junior developers and conducted code reviews ensuring best practices 
 
Software Engineer | Digital Innovations, Pune

August 2021 - June 2022 
• Developed and maintained backend services for financial applications using Spring 
Boot 
• Implemented caching strategies with Redis, improving API response times by 50% 
• Collaborated with frontend team to integrate APIs and ensure seamless user 
experience 
• Created automated testing suite achieving 85% code coverage 
EDUCATION 
Bachelor of Engineering in Computer Engineering 
Gujarat Technological University | Ahmedabad | CGPA: 8.7/10 | 2017 - 2021 
CERTIFICATIONS 
• AWS Certified Solutions Architect - Associate (2023) 
• Certified Kubernetes Administrator - CNCF (2022) 
• Python for Data Structures and Algorithms - Udemy (2021)
"""
    jd="""We are hiring a Software Engineer for a fast-growing startup who can build, ship, and own features end-to-end.
                         The role requires strong hands-on experience in at least one backend language such as Python, JavaScript (Node.js), Java, or Go, with a clear understanding of data structures, algorithms, and real-world problem solving. 
                        The candidate should be comfortable building REST APIs, working with SQL databases like PostgreSQL or MySQL and NoSQL tools such as MongoDB or Redis, and using Git in collaborative environments. Basic frontend knowledge (React or similar) is a plus but not mandatory.
                         You should have experience deploying applications using Docker, understand cloud fundamentals (AWS/GCP/Azure), and be able to debug production issues without hand-holding. We value real production work, side projects, or startup experience over degrees, grades, or certificates.
                         The ideal candidate takes ownership, learns quickly, handles ambiguity, and makes practical trade-offs under time pressure. This role is not for someone looking for comfort or rigid processes; it is for engineers who want rapid growth, responsibility, and direct impact on the product.
"""
    output=workflow.invoke({'resume':resume,'jd':jd})
    '''# ✅ Safe way
    if 'feedback' in output:
        print(output['feedback'])
    else:
        print("Feedback not available in output")
        print("Available keys:", output.keys())'''
                       