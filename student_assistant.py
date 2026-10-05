"""
===========================================================
COLLEGE AI ASSISTANT
===========================================================

Single-file application containing:

- FastAPI backend
- HTML/CSS/JavaScript frontend
- SQLite database
- PDF/DOCX/TXT document extraction
- OpenAI support
- Gemini support
- Hugging Face support
- LLM tool selection
- Calculator tool
- Attendance percentage tool
- Attendance marking tool
- Timetable/document analysis
- REST APIs

Run:

    pip install fastapi uvicorn python-multipart python-dotenv
    pip install pypdf python-docx openai google-genai

Then:

    uvicorn app:app --reload

Open:

    http://127.0.0.1:8000

===========================================================
ENVIRONMENT VARIABLES
===========================================================

OpenAI:

LLM_PROVIDER=openai
LLM_MODEL=gpt-5-mini
OPENAI_API_KEY=your_key

Gemini:

LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_key

Hugging Face:

LLM_PROVIDER=huggingface
LLM_MODEL=your_model
HF_TOKEN=your_token

===========================================================
"""

import os
import re
import json
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from pydantic import BaseModel

from pypdf import PdfReader
from docx import Document


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

LLM_PROVIDER = os.getenv(
    "LLM_PROVIDER",
    "openai"
).lower()

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "gpt-5-mini"
)

BASE_DIR = Path(__file__).resolve().parent

DATABASE_PATH = BASE_DIR / "college.db"


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="College AI Assistant",
    description="AI assistant for college students",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    connection = get_db()

    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            student_id TEXT NOT NULL,

            course TEXT NOT NULL,

            attendance_date TEXT NOT NULL,

            status TEXT NOT NULL,

            created_at TEXT NOT NULL,

            UNIQUE(
                student_id,
                course,
                attendance_date
            ),

            FOREIGN KEY(student_id)
            REFERENCES students(student_id)
        )
        """
    )

    connection.commit()

    connection.close()


init_database()


# =========================================================
# DATABASE FUNCTIONS
# =========================================================

def create_student(
    student_id: str,
    name: str
):

    connection = get_db()

    connection.execute(
        """
        INSERT INTO students(
            student_id,
            name
        )
        VALUES (?, ?)

        ON CONFLICT(student_id)
        DO UPDATE SET
            name = excluded.name
        """,
        (
            student_id,
            name,
        )
    )

    connection.commit()

    connection.close()


def student_exists(
    student_id: str
):

    connection = get_db()

    row = connection.execute(
        """
        SELECT student_id
        FROM students
        WHERE student_id = ?
        """,
        (
            student_id,
        )
    ).fetchone()

    connection.close()

    return row is not None


def save_attendance(
    student_id: str,
    course: str,
    attendance_date: str,
    status: str
):

    if status not in [
        "present",
        "absent"
    ]:

        raise ValueError(
            "Status must be present or absent."
        )

    connection = get_db()

    # For development, automatically create the
    # student if they don't exist.
    if not student_exists(student_id):

        connection.execute(
            """
            INSERT INTO students(
                student_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                student_id,
                student_id,
            )
        )

    connection.execute(
        """
        INSERT INTO attendance(
            student_id,
            course,
            attendance_date,
            status,
            created_at
        )

        VALUES (?, ?, ?, ?, ?)

        ON CONFLICT(
            student_id,
            course,
            attendance_date
        )

        DO UPDATE SET

            status =
                excluded.status,

            created_at =
                excluded.created_at
        """,
        (
            student_id,
            course,
            attendance_date,
            status,
            datetime.utcnow().isoformat(),
        )
    )

    connection.commit()

    connection.close()

    return {
        "student_id": student_id,
        "course": course,
        "date": attendance_date,
        "status": status,
        "message": "Attendance saved successfully."
    }


def calculate_attendance(
    student_id: str,
    course: Optional[str] = None
):

    connection = get_db()

    if course:

        rows = connection.execute(
            """
            SELECT status
            FROM attendance

            WHERE student_id = ?
            AND course = ?

            ORDER BY attendance_date
            """,
            (
                student_id,
                course,
            )
        ).fetchall()

    else:

        rows = connection.execute(
            """
            SELECT status
            FROM attendance

            WHERE student_id = ?

            ORDER BY attendance_date
            """,
            (
                student_id,
            )
        ).fetchall()

    connection.close()

    total = len(rows)

    present = sum(
        1
        for row in rows
        if row["status"] == "present"
    )

    absent = total - present

    if total == 0:

        percentage = 0

    else:

        percentage = (
            present / total
        ) * 100

    return {
        "student_id": student_id,
        "course": course,
        "total_classes": total,
        "present": present,
        "absent": absent,
        "percentage": round(
            percentage,
            2
        ),
    }


def get_attendance_records(
    student_id: str
):

    connection = get_db()

    rows = connection.execute(
        """
        SELECT
            course,
            attendance_date,
            status,
            created_at

        FROM attendance

        WHERE student_id = ?

        ORDER BY attendance_date DESC
        """,
        (
            student_id,
        )
    ).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


# =========================================================
# DOCUMENT PARSER
# =========================================================

def extract_pdf(
    file_path: str
):

    reader = PdfReader(
        file_path
    )

    pages = []

    for page in reader.pages:

        text = page.extract_text()

        if text:

            pages.append(
                text
            )

    return "\n\n".join(
        pages
    )


def extract_docx(
    file_path: str
):

    document = Document(
        file_path
    )

    output = []

    # Paragraphs

    for paragraph in document.paragraphs:

        text = paragraph.text.strip()

        if text:

            output.append(
                text
            )

    # Tables

    for table in document.tables:

        for row in table.rows:

            cells = []

            for cell in row.cells:

                cells.append(
                    cell.text.strip()
                )

            output.append(
                " | ".join(cells)
            )

    return "\n".join(
        output
    )


def extract_txt(
    file_path: str
):

    return Path(
        file_path
    ).read_text(
        encoding="utf-8",
        errors="ignore"
    )


def extract_document(
    file_path: str
):

    extension = Path(
        file_path
    ).suffix.lower()

    if extension == ".pdf":

        return extract_pdf(
            file_path
        )

    if extension == ".docx":

        return extract_docx(
            file_path
        )

    if extension == ".txt":

        return extract_txt(
            file_path
        )

    raise ValueError(
        "Only PDF, DOCX and TXT files are supported."
    )


# =========================================================
# CALCULATOR TOOL
# =========================================================

def calculator_tool(
    operation: str,
    a: float,
    b: Optional[float] = None
):

    if operation == "add":

        result = a + b

    elif operation == "subtract":

        result = a - b

    elif operation == "multiply":

        result = a * b

    elif operation == "divide":

        if b == 0:

            raise ValueError(
                "Cannot divide by zero."
            )

        result = a / b

    elif operation == "percentage":

        if b is None:

            raise ValueError(
                "Total value is required."
            )

        if b == 0:

            raise ValueError(
                "Total cannot be zero."
            )

        result = (
            a / b
        ) * 100

    else:

        raise ValueError(
            f"Unknown operation: {operation}"
        )

    return {
        "operation": operation,
        "a": a,
        "b": b,
        "result": round(
            result,
            4
        )
    }


# =========================================================
# ATTENDANCE TOOLS
# =========================================================

def attendance_percentage_tool(
    student_id: str,
    course: Optional[str] = None
):

    return calculate_attendance(
        student_id,
        course
    )


def attendance_marking_tool(
    student_id: str,
    course: str,
    attendance_date: str,
    status: str
):

    return save_attendance(
        student_id=student_id,
        course=course,
        attendance_date=attendance_date,
        status=status,
    )


# =========================================================
# LLM SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """

You are a College AI Assistant.

Your job is to help college students.

You have access to these tools:

-----------------------------------------------------------
TOOL 1: calculator
-----------------------------------------------------------

Use calculator when the user asks for:

- mathematical calculations
- percentage calculations
- addition
- subtraction
- multiplication
- division

Example:

User:
"What is 35 out of 40 percentage?"

Use:

calculator

with:

operation = percentage
a = 35
b = 40


-----------------------------------------------------------
TOOL 2: attendance_percentage
-----------------------------------------------------------

Use attendance_percentage when the user asks:

- What is my attendance?
- What is my attendance percentage?
- How much attendance do I have?
- How many classes have I attended?
- What is my attendance in Mathematics?

The backend database contains the real attendance.

DO NOT invent attendance data.

DO NOT calculate attendance from memory.

Use this tool.


-----------------------------------------------------------
TOOL 3: mark_attendance
-----------------------------------------------------------

Use mark_attendance when the user asks:

- Mark me present
- Mark me absent
- Record attendance
- Add attendance
- Mark today's attendance
- Mark attendance for a particular date

Required:

student_id
course
attendance_date
status

Status must be:

present

or:

absent


-----------------------------------------------------------
TOOL 4: timetable_analysis
-----------------------------------------------------------

Use timetable_analysis when the user asks about:

- timetable
- class schedule
- subject schedule
- what class they have
- classes on Monday
- classes at a particular time

The uploaded document text will be provided in context.


-----------------------------------------------------------
IMPORTANT
-----------------------------------------------------------

Never claim that attendance was marked unless the
mark_attendance tool was executed.

Never invent attendance percentages.

Never invent timetable information.

If required information is missing, ask the user for it.

Return JSON.

For a tool:

{
    "tool": "tool_name",
    "arguments": {}
}

For a normal answer:

{
    "tool": "general",
    "arguments": {},
    "response": "answer"
}

"""


# =========================================================
# JSON CLEANER
# =========================================================

def parse_json_response(
    text: str
):

    text = text.strip()

    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    try:

        return json.loads(
            text
        )

    except json.JSONDecodeError:

        start = text.find(
            "{"
        )

        end = text.rfind(
            "}"
        )

        if (
            start != -1
            and end != -1
        ):

            return json.loads(
                text[
                    start:end + 1
                ]
            )

        raise ValueError(
            "LLM returned invalid JSON."
        )


# =========================================================
# OPENAI / HUGGING FACE LLM
# =========================================================

def openai_router(
    user_message: str,
    student_id: Optional[str],
    document_text: Optional[str]
):

    from openai import OpenAI

    if LLM_PROVIDER == "openai":

        api_key = os.getenv(
            "OPENAI_API_KEY"
        )

        if not api_key:

            raise RuntimeError(
                "OPENAI_API_KEY is missing."
            )

        client = OpenAI(
            api_key=api_key
        )

    elif LLM_PROVIDER == "huggingface":

        api_key = os.getenv(
            "HF_TOKEN"
        )

        if not api_key:

            raise RuntimeError(
                "HF_TOKEN is missing."
            )

        client = OpenAI(
            base_url=(
                "https://router.huggingface.co/v1"
            ),
            api_key=api_key
        )

    else:

        raise RuntimeError(
            "Invalid OpenAI-compatible provider."
        )

    context = ""

    if student_id:

        context += (
            "\nStudent ID: "
            + student_id
        )

    if document_text:

        context += (
            "\n\nUploaded document:\n"
            + document_text[:50000]
        )

    tools = [

        {
            "type": "function",

            "function": {

                "name": "calculator",

                "description":
                    "Perform mathematical calculations.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "operation": {

                            "type": "string",

                            "enum": [
                                "add",
                                "subtract",
                                "multiply",
                                "divide",
                                "percentage"
                            ]
                        },

                        "a": {
                            "type": "number"
                        },

                        "b": {
                            "type": "number"
                        }
                    },

                    "required": [
                        "operation",
                        "a"
                    ]
                }
            }
        },

        {
            "type": "function",

            "function": {

                "name":
                    "attendance_percentage",

                "description":
                    "Get actual attendance from the database.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "student_id": {
                            "type": "string"
                        },

                        "course": {
                            "type": "string"
                        }
                    },

                    "required": [
                        "student_id"
                    ]
                }
            }
        },

        {
            "type": "function",

            "function": {

                "name":
                    "mark_attendance",

                "description":
                    "Mark attendance for a specific date.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "student_id": {
                            "type": "string"
                        },

                        "course": {
                            "type": "string"
                        },

                        "attendance_date": {
                            "type": "string"
                        },

                        "status": {

                            "type": "string",

                            "enum": [
                                "present",
                                "absent"
                            ]
                        }
                    },

                    "required": [
                        "student_id",
                        "course",
                        "attendance_date",
                        "status"
                    ]
                }
            }
        },

        {
            "type": "function",

            "function": {

                "name":
                    "timetable_analysis",

                "description":
                    "Analyze the uploaded timetable.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "question": {
                            "type": "string"
                        }
                    },

                    "required": [
                        "question"
                    ]
                }
            }
        }
    ]

    response = client.chat.completions.create(

        model=LLM_MODEL,

        messages=[

            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },

            {
                "role": "user",

                "content":
                    context
                    + "\n\nUser request:\n"
                    + user_message
            }
        ],

        tools=tools,

        tool_choice="auto",

        temperature=0
    )

    message = (
        response
        .choices[0]
        .message
    )

    if message.tool_calls:

        call = message.tool_calls[0]

        return {

            "tool":
                call.function.name,

            "arguments":
                json.loads(
                    call.function.arguments
                )
        }

    return {

        "tool": "general",

        "arguments": {},

        "response":
            message.content or ""
    }


# =========================================================
# GEMINI LLM
# =========================================================

def gemini_router(
    user_message: str,
    student_id: Optional[str],
    document_text: Optional[str]
):

    from google import genai
    from google.genai import types

    api_key = os.getenv(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    client = genai.Client(
        api_key=api_key
    )

    calculator = (
        types.FunctionDeclaration(
            name="calculator",

            description=
                "Perform mathematical calculations.",

            parameters={
                "type": "OBJECT",

                "properties": {

                    "operation": {

                        "type": "STRING",

                        "enum": [
                            "add",
                            "subtract",
                            "multiply",
                            "divide",
                            "percentage"
                        ]
                    },

                    "a": {
                        "type": "NUMBER"
                    },

                    "b": {
                        "type": "NUMBER"
                    }
                },

                "required": [
                    "operation",
                    "a"
                ]
            }
        )
    )

    attendance_percentage = (
        types.FunctionDeclaration(

            name=
                "attendance_percentage",

            description=
                "Get actual attendance from database.",

            parameters={

                "type": "OBJECT",

                "properties": {

                    "student_id": {
                        "type": "STRING"
                    },

                    "course": {
                        "type": "STRING"
                    }
                },

                "required": [
                    "student_id"
                ]
            }
        )
    )

    mark_attendance = (
        types.FunctionDeclaration(

            name=
                "mark_attendance",

            description=
                "Mark attendance for a particular day.",

            parameters={

                "type": "OBJECT",

                "properties": {

                    "student_id": {
                        "type": "STRING"
                    },

                    "course": {
                        "type": "STRING"
                    },

                    "attendance_date": {
                        "type": "STRING"
                    },

                    "status": {

                        "type": "STRING",

                        "enum": [
                            "present",
                            "absent"
                        ]
                    }
                },

                "required": [
                    "student_id",
                    "course",
                    "attendance_date",
                    "status"
                ]
            }
        )
    )

    timetable = (
        types.FunctionDeclaration(

            name=
                "timetable_analysis",

            description=
                "Analyze an uploaded timetable.",

            parameters={

                "type": "OBJECT",

                "properties": {

                    "question": {
                        "type": "STRING"
                    }
                },

                "required": [
                    "question"
                ]
            }
        )
    )

    tool = types.Tool(
        function_declarations=[
            calculator,
            attendance_percentage,
            mark_attendance,
            timetable,
        ]
    )

    context = ""

    if student_id:

        context += (
            "\nStudent ID: "
            + student_id
        )

    if document_text:

        context += (
            "\n\nUploaded document:\n"
            + document_text[:50000]
        )

    prompt = (
        SYSTEM_PROMPT
        + context
        + "\n\nUser request:\n"
        + user_message
    )

    response = (
        client.models.generate_content(

            model=LLM_MODEL,

            contents=prompt,

            config=
                types.GenerateContentConfig(

                    tools=[tool],

                    temperature=0
                )
        )
    )

    if not response.candidates:

        raise RuntimeError(
            "Gemini returned no response."
        )

    content = (
        response
        .candidates[0]
        .content
    )

    for part in content.parts:

        if getattr(
            part,
            "function_call",
            None
        ):

            call = part.function_call

            return {

                "tool":
                    call.name,

                "arguments":
                    dict(call.args)
            }

    return {

        "tool": "general",

        "arguments": {},

        "response":
            response.text or ""
    }


# =========================================================
# LLM ROUTER
# =========================================================

def choose_tool(
    user_message: str,
    student_id: Optional[str],
    document_text: Optional[str]
):

    if LLM_PROVIDER in [
        "openai",
        "huggingface"
    ]:

        return openai_router(
            user_message,
            student_id,
            document_text
        )

    if LLM_PROVIDER == "gemini":

        return gemini_router(
            user_message,
            student_id,
            document_text
        )

    raise RuntimeError(
        "Supported providers: "
        "openai, gemini, huggingface"
    )


# =========================================================
# PYDANTIC MODELS
# =========================================================

class ChatRequest(BaseModel):

    message: str

    student_id: Optional[str] = None

    document_text: Optional[str] = None


class StudentRequest(BaseModel):

    student_id: str

    name: str


class AttendanceRequest(BaseModel):

    student_id: str

    course: str

    attendance_date: str

    status: str


# =========================================================
# FRONTEND
# =========================================================

HTML = r"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<title>
College AI Assistant
</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background:
        linear-gradient(
            135deg,
            #eef2ff,
            #f8fafc
        );

    color: #111827;
}

.container {

    max-width: 1100px;

    margin:
        30px auto;

    padding:
        20px;
}

.header {

    background:
        #111827;

    color: white;

    padding:
        25px;

    border-radius:
        18px;

    margin-bottom:
        20px;
}

.header h1 {

    margin:
        0 0 8px;
}

.header p {

    color:
        #cbd5e1;

    margin:
        0;
}

.grid {

    display:
        grid;

    grid-template-columns:
        300px 1fr;

    gap:
        20px;
}

.card {

    background:
        white;

    padding:
        20px;

    border-radius:
        18px;

    box-shadow:
        0 10px 30px
        rgba(
            15,
            23,
            42,
            0.08
        );

    margin-bottom:
        20px;
}

label {

    display:
        block;

    font-weight:
        bold;

    margin-bottom:
        7px;
}

input,
textarea,
button {

    width:
        100%;

    padding:
        12px;

    border-radius:
        10px;

    border:
        1px solid
        #d1d5db;

    margin-bottom:
        12px;

    font-size:
        14px;
}

textarea {

    min-height:
        90px;

    resize:
        vertical;
}

button {

    border:
        none;

    background:
        #4f46e5;

    color:
        white;

    font-weight:
        bold;

    cursor:
        pointer;
}

button:hover {

    background:
        #4338ca;
}

.green {

    background:
        #0f766e;
}

.green:hover {

    background:
        #115e59;
}

.chat {

    height:
        500px;

    overflow-y:
        auto;

    background:
        #f8fafc;

    border-radius:
        12px;

    padding:
        15px;

    margin-bottom:
        15px;
}

.message {

    max-width:
        85%;

    padding:
        12px 15px;

    border-radius:
        15px;

    margin-bottom:
        12px;

    white-space:
        pre-wrap;
}

.user {

    background:
        #4f46e5;

    color:
        white;

    margin-left:
        auto;
}

.assistant {

    background:
        white;

    border:
        1px solid
        #e5e7eb;
}

.status {

    background:
        #f1f5f9;

    padding:
        10px;

    border-radius:
        10px;

    font-size:
        13px;

    margin-top:
        5px;
}

.document {

    background:
        #f8fafc;

    padding:
        10px;

    border-radius:
        10px;

    max-height:
        200px;

    overflow:
        auto;

    white-space:
        pre-wrap;

    font-size:
        12px;
}

.examples {

    background:
        #f8fafc;

    padding:
        15px;

    border-radius:
        10px;

    font-size:
        13px;
}

@media(max-width:800px) {

    .grid {

        grid-template-columns:
            1fr;
    }

    .chat {

        height:
            400px;
    }
}

</style>

</head>


<body>


<div class="container">


<div class="header">

<h1>
🎓 College AI Assistant
</h1>

<p>
AI assistant for timetable,
calculations and attendance
</p>

</div>


<div class="grid">


<!-- LEFT -->

<div>


<div class="card">

<h3>
Student
</h3>

<label>
Student ID
</label>

<input
id="studentId"
placeholder="STU001"
>

<label>
Student Name
</label>

<input
id="studentName"
placeholder="Your name"
>

<button
onclick="saveStudent()"
>
Save Student
</button>

<div
id="studentStatus"
class="status"
></div>

</div>


<div class="card">

<h3>
Upload Timetable / Document
</h3>

<p>
Supported:
PDF, DOCX, TXT
</p>

<input
id="file"
type="file"
accept=".pdf,.docx,.txt"
>

<button
class="green"
onclick="uploadFile()"
>
Upload Document
</button>

<div
id="uploadStatus"
class="status"
></div>

<div
id="documentPreview"
class="document"
style="display:none"
></div>

</div>


<div class="card">

<h3>
Attendance Records
</h3>

<button
onclick="viewAttendance()"
>
View Attendance
</button>

<div
id="attendance"
class="status"
></div>

</div>


</div>


<!-- RIGHT -->

<div class="card">

<h2>
AI Assistant
</h2>


<div
id="chat"
class="chat"
>

<div
class="message assistant"
>

Hello! 👋

I can help you with:

• Calculations
• Attendance percentage
• Marking attendance
• Timetable questions
• Uploaded PDF/DOCX/TXT files

</div>

</div>


<textarea
id="message"
placeholder="Ask your question..."
onkeydown="handleEnter(event)"
></textarea>


<button
onclick="sendMessage()"
>
Send
</button>


<div class="examples">

<strong>
Try:
</strong>

<ul>

<li>
What is 35 out of 40 percentage?
</li>

<li>
What is my attendance percentage?
</li>

<li>
Mark me present for Mathematics today.
</li>

<li>
What class do I have at 10 AM?
</li>

<li>
Show my attendance.
</li>

</ul>

</div>


</div>


</div>

</div>


<script>

let documentText = "";


function studentId() {

    return document
        .getElementById(
            "studentId"
        )
        .value
        .trim();
}


function addMessage(
    text,
    type
) {

    const chat =
        document.getElementById(
            "chat"
        );

    const message =
        document.createElement(
            "div"
        );

    message.className =
        "message " + type;

    message.textContent =
        text;

    chat.appendChild(
        message
    );

    chat.scrollTop =
        chat.scrollHeight;
}


function handleEnter(event) {

    if (
        event.key === "Enter"
        &&
        !event.shiftKey
    ) {

        event.preventDefault();

        sendMessage();
    }
}


async function saveStudent() {

    const id =
        studentId();

    const name =
        document
            .getElementById(
                "studentName"
            )
            .value
            .trim();


    if (!id || !name) {

        alert(
            "Enter student ID and name."
        );

        return;
    }


    const response =
        await fetch(
            "/api/students",
            {

                method:
                    "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({

                        student_id:
                            id,

                        name:
                            name
                    })
            }
        );


    const data =
        await response.json();


    document
        .getElementById(
            "studentStatus"
        )
        .textContent =
            data.message ||
            "Student saved.";
}


async function uploadFile() {

    const input =
        document.getElementById(
            "file"
        );


    if (!input.files.length) {

        alert(
            "Choose a file first."
        );

        return;
    }


    const formData =
        new FormData();


    formData.append(
        "file",
        input.files[0]
    );


    document
        .getElementById(
            "uploadStatus"
        )
        .textContent =
            "Uploading...";


    try {

        const response =
            await fetch(
                "/api/upload",
                {

                    method:
                        "POST",

                    body:
                        formData
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Upload failed."
            );
        }


        documentText =
            data.text;


        document
            .getElementById(
                "uploadStatus"
            )
            .textContent =
                "Uploaded " +
                data.filename +
                " successfully.";


        const preview =
            document.getElementById(
                "documentPreview"
            );


        preview.style.display =
            "block";


        preview.textContent =
            documentText.substring(
                0,
                10000
            );

    }

    catch(error) {

        document
            .getElementById(
                "uploadStatus"
            )
            .textContent =
                error.message;
    }
}


async function sendMessage() {

    const input =
        document.getElementById(
            "message"
        );


    const message =
        input.value.trim();


    if (!message) {

        return;
    }


    addMessage(
        message,
        "user"
    );


    input.value = "";


    addMessage(
        "Thinking...",
        "assistant"
    );


    const chat =
        document.getElementById(
            "chat"
        );


    const thinking =
        chat.lastElementChild;


    try {

        const response =
            await fetch(
                "/api/chat",
                {

                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            message:
                                message,

                            student_id:
                                studentId(),

                            document_text:
                                documentText
                        })
                }
            );


        const data =
            await response.json();


        thinking.remove();


        if (!response.ok) {

            addMessage(
                "Error: "
                +
                (
                    data.detail ||
                    "Request failed."
                ),
                "assistant"
            );

            return;
        }


        addMessage(
            data.message ||
            "No response.",
            "assistant"
        );

    }

    catch(error) {

        thinking.remove();

        addMessage(
            "Error: "
            +
            error.message,
            "assistant"
        );
    }
}


async function viewAttendance() {

    const id =
        studentId();


    if (!id) {

        alert(
            "Enter your student ID first."
        );

        return;
    }


    try {

        const response =
            await fetch(
                "/api/attendance/"
                +
                encodeURIComponent(
                    id
                )
            );


        const data =
            await response.json();


        const container =
            document.getElementById(
                "attendance"
            );


        if (!data.records.length) {

            container.textContent =
                "No attendance records.";

            return;
        }


        container.innerHTML =
            data.records
                .map(
                    record =>
                        `${record.attendance_date}
                         — ${record.course}
                         — ${record.status}`
                )
                .join("<br>");

    }

    catch(error) {

        document
            .getElementById(
                "attendance"
            )
            .textContent =
                error.message;
    }
}

</script>


</body>

</html>
"""


# =========================================================
# FRONTEND ROUTE
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def home():

    return HTML


# =========================================================
# HEALTH API
# =========================================================

@app.get("/api/health")
def health():

    return {

        "status": "ok",

        "application":
            "College AI Assistant",

        "llm_provider":
            LLM_PROVIDER,

        "model":
            LLM_MODEL,
    }


# =========================================================
# STUDENT API
# =========================================================

@app.post("/api/students")
def api_create_student(
    request: StudentRequest
):

    create_student(
        request.student_id,
        request.name
    )

    return {

        "success": True,

        "message":
            "Student saved successfully.",

        "student_id":
            request.student_id
    }


# =========================================================
# DOCUMENT UPLOAD API
# =========================================================

@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...)
):

    filename = (
        file.filename
        or ""
    )

    extension = Path(
        filename
    ).suffix.lower()


    allowed = {
        ".pdf",
        ".docx",
        ".txt"
    }


    if extension not in allowed:

        raise HTTPException(

            status_code=400,

            detail=
                "Only PDF, DOCX and TXT files are allowed."
        )


    contents = await file.read()


    # 10 MB maximum

    if len(contents) > (
        10 * 1024 * 1024
    ):

        raise HTTPException(

            status_code=413,

            detail= "Maximum file size is 10 MB."
        )


    temporary_file = None


    try:

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=extension
        ) as temp:

            temp.write(
                contents
            )

            temporary_file = temp.name


        text = extract_document(temporary_file)


        if not text.strip():

            raise HTTPException(

                status_code=422,

                detail=
                    "No text could be extracted."
            )


        return {

            "success":
                True,

            "filename":
                filename,

            "characters":
                len(text),

            "text":
                text
        }


    finally:

        if (
            temporary_file
            and os.path.exists(
                temporary_file
            )
        ):

            os.remove(
                temporary_file
            )


# =========================================================
# MAIN AI CHAT API
# =========================================================

@app.post("/api/chat")
def api_chat(
    request: ChatRequest
):

    if not request.message.strip():

        raise HTTPException(

            status_code=400,

            detail="Message cannot be empty."
        )


    try:

        decision =choose_tool(

                request.message,

                request.student_id,

                request.document_text
            )


        tool =decision.get(
                "tool"
            )


        arguments =decision.get(
                "arguments",
                {}
            )


        # =================================================
        # CALCULATOR
        # =================================================

        if tool == "calculator":

            result =calculator_tool(

                    operation =
                        arguments[
                            "operation"
                        ],

                    a =
                        float(
                            arguments["a"]
                        ),

                    b =
                        (
                            float(
                                arguments["b"]
                            )

                            if
                            arguments.get(
                                "b"
                            )
                            is not None

                            else None
                        )
                )


            return {

                "success":
                    True,

                "tool":
                    "calculator",

                "message":
                    (
                        "The answer is "
                        +
                        str(
                            result[
                                "result"
                            ]
                        )
                    ),

                "result":
                    result
            }


        # =================================================
        # ATTENDANCE PERCENTAGE
        # =================================================

        if tool == (
            "attendance_percentage"
        ):

            sid =  arguments.get(
                    "student_id"
                ) or request.student_id


            if not sid:

                return {

                    "success":
                        False,

                    "tool":
                        "attendance_percentage",

                    "message":
                        (
                            "Please provide your "
                            "student ID."
                        )
                }


            result = attendance_percentage_tool(

                    student_id =
                        sid,

                    course =
                        arguments.get(
                            "course"
                        )
                )


            return {

                "success":
                    True,

                "tool":
                    "attendance_percentage",

                "message":
                    (
                        f"Your attendance is "
                        f"{result['percentage']}%. "
                        f"You were present for "
                        f"{result['present']} "
                        f"out of "
                        f"{result['total_classes']} "
                        f"classes."
                    ),

                "result":
                    result
            }


        # =================================================
        # MARK ATTENDANCE
        # =================================================

        if tool == (
            "mark_attendance"
        ):

            sid = arguments.get(
                    "student_id"
                ) or request.student_id


            required = [
                "course",
                "attendance_date",
                "status"
            ]


            missing = [

                field

                for field
                in required

                if not arguments.get(
                    field
                )
            ]


            if not sid:

                missing.insert(
                    0,
                    "student_id"
                )


            if missing:

                return {

                    "success":
                        False,

                    "tool":
                        "mark_attendance",

                    "message":
                        (
                            "Missing: "
                            +
                            ", ".join(
                                missing
                            )
                        )
                }


            result = attendance_marking_tool(

                    student_id =
                        sid,

                    course =
                        arguments[
                            "course"
                        ],

                    attendance_date =
                        arguments[
                            "attendance_date"
                        ],

                    status =
                        arguments[
                            "status"
                        ]
                )


            return {

                "success":
                    True,

                "tool":
                    "mark_attendance",

                "message":
                    (
                        "Attendance marked "
                        f"as {result['status']} "
                        f"for {result['course']} "
                        f"on {result['date']}."
                    ),

                "result":
                    result
            }


        # =================================================
        # TIMETABLE
        # =================================================

        if tool == (
            "timetable_analysis"
        ):

            if not request.document_text:

                return {

                    "success":
                        False,

                    "tool":
                        "timetable_analysis",

                    "message":
                        (
                            "Please upload your "
                            "timetable PDF, DOCX "
                            "or TXT file first."
                        )
                }


            # The uploaded document is already in the
            # LLM context. For this basic version,
            # return the relevant extracted text.
            #
            # A production version should store the
            # timetable as structured data.

            question = arguments.get(
                    "question",
                    request.message
                )


            return {

                "success":
                    True,

                "tool":
                    "timetable_analysis",

                "message":
                    (
                        "Timetable document was "
                        "successfully extracted. "
                        "The relevant document context "
                        "has been supplied to the AI."
                    ),

                "question":
                    question,

                "document":
                    request.document_text[:50000]
            }


        # =================================================
        # GENERAL
        # =================================================

        return {

            "success":
                True,

            "tool":
                "general",

            "message":
                decision.get(
                    "response",
                    "I could not generate a response."
                )
        }


    except Exception as error:

        raise HTTPException(

            status_code=500,

            detail=str(error)
        )


# =========================================================
# DIRECT ATTENDANCE API
# =========================================================

@app.post("/api/attendance")
def api_mark_attendance(
    request: AttendanceRequest
):

    try:

        result = attendance_marking_tool(

                student_id =
                    request.student_id,

                course =
                    request.course,

                attendance_date =
                    request.attendance_date,

                status =
                    request.status
            )


        return {

            "success":
                True,

            "result":
                result
        }


    except Exception as error:

        raise HTTPException(

            status_code=400,

            detail=str(error)
        )


# =========================================================
# GET ATTENDANCE
# =========================================================

@app.get(
    "/api/attendance/{student_id}"
)
def api_get_attendance(
    student_id: str
):

    records = get_attendance_records(
            student_id
        )


    return {

        "success":
            True,

        "student_id":
            student_id,

        "records":
            records
    }


# =========================================================
# GET ATTENDANCE PERCENTAGE
# =========================================================

@app.get(
    "/api/attendance/{student_id}/percentage"
)
def api_get_percentage(

    student_id: str,

    course:
        Optional[str] = None

):

    result = attendance_percentage_tool(

            student_id,

            course
        )


    return {

        "success":
            True,

        "result":
            result
    }


# =========================================================
# RUN DIRECTLY
# =========================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(

        "app:app",

        host="0.0.0.0",

        port=8000,

        reload=True
    )
