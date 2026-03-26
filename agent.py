import json
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from anyquery_client import run_sql
import os
from dotenv import load_dotenv

load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=OPENAI_API_KEY
)

# llm = ChatGoogleGenerativeAI(
#     model="gemini-2.5-pro",
#     google_api_key=GEMINI_API_KEY
# )


def generate_sql(question):
    prompt = f"""
    You are an expert PostgreSQL SQL generator.

    Database schema:

    Table: students.students
    Columns:
    - user_id (integer)
    - name (text)
    - email (text)
    - phone (text)
    - city (text)

    Rules:
    1. Only generate PostgreSQL SQL.
    2. Always use FULL table name: students.students
    3. Do not invent tables or columns.
    4. Do not explain anything.
    5. Only return SQL.

    Examples:`

    Question: list all students
    SQL: SELECT * FROM students.students

    Question: show students from Bangalore
    SQL: SELECT * FROM  students.students WHERE city = 'Bangalore';

    Question: count students
    SQL: SELECT COUNT(*) FROM students.students;

    Now convert the question into SQL.

    Question: {question}
    SQL:
    """

    response = llm.invoke(prompt)
    print(f'Response : ',response)

    return response.content.strip()

def _extract_rows_columns(parsed):
    """
    Anyquery MCP returns results in one of two shapes:

    Shape A (MCP standard):
      {"result": {"content": [{"type": "text", "text": "<json string>"}]}}
      where the text is JSON like {"rows": [...], "columns": [...]}

    Shape B (legacy direct):
      {"result": {"rows": [...], "columns": [...]}}

    Returns (rows, columns) tuples.
    """
    result = parsed.get("result", {})

    # Shape A: MCP content array
    content = result.get("content", [])
    if content:
        for item in content:
            if item.get("type") == "text":
                text = item.get("text", "")
                try:
                    inner = json.loads(text)
                    rows = inner.get("rows", [])
                    columns = inner.get("columns", [])
                    if rows or columns:
                        return rows, columns
                except (json.JSONDecodeError, AttributeError):
                    # text might be plain CSV/table — return as raw message
                    return None, text  # signal raw text

    # Shape B: direct rows/columns
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    return rows, columns


def generate_natural_language_response(question, sql_query, data, rows_count):
    if rows_count == 0:
        return "No data found for your query."

    # Convert a few rows to string for context (limit to 10 rows to keep prompt size reasonable)
    data_sample = data[:10]
    
    prompt = f"""
    You are a helpful data assistant. 
    The user asked a question, and we queried our PostgreSQL database to get the answer. 
    
    User Question: {question}
    SQL Query Executed: {sql_query}
    Total Rows Returned: {rows_count}
    Sample Data (up to 10 rows):
    {json.dumps(data_sample, indent=2)}
    
    Based on the question and the data, provide a clear, concise, and natural language answer directly answering the user's question. 
    Do not explain the SQL query unless necessary. Just give the answer in a friendly tone.
    """
    
    response = llm.invoke(prompt)
    return response.content.strip()

def run_agent(question):
    print("Question:", question)

    sql_query = generate_sql(question)
    print("SQL:", sql_query)

    parsed = run_sql(sql_query)

    print("PARSED:", parsed)

    if "error" in parsed:
        return {
            "question": question,
            "sql_query": sql_query,
            "rows_count": 0,
            "data": [],
            "message": str(parsed["error"]),
            "natural_language_response": f"I encountered an error executing the query: {parsed['error']}"
        }

    rows, columns = _extract_rows_columns(parsed)

    # If columns is a string, it means the server returned raw text
    if isinstance(columns, str):
        return {
            "question": question,
            "sql_query": sql_query,
            "rows_count": 0,
            "data": [],
            "message": columns,
            "natural_language_response": f"Here is the raw response from the database: {columns}"
        }


    if not rows:
        return {
            "question": question,
            "sql_query": sql_query,
            "rows_count": 0,
            "data": [],
            "message": "No users found",
            "natural_language_response": "I couldn't find any data matching your request."
        }

    # 🔥 Convert rows → objects
    formatted_rows = [
        dict(zip(columns, row))
        for row in rows
    ]
    
    nl_response = generate_natural_language_response(question, sql_query, formatted_rows, len(formatted_rows))

    return {
        "question": question,
        "sql_query": sql_query,
        "rows_count": len(formatted_rows),
        "data": formatted_rows,
        "message": "Success",
        "natural_language_response": nl_response
    }

# def run_agent(question):

#     sql_query = generate_sql(question)

#     db_result = run_sql(sql_query)

#     final_prompt = f"""
# User question:
# {question}

# SQL executed:
# {sql_query}

# Database result:
# {db_result}

# Explain the answer clearly.
# """

#     answer = llm.invoke(final_prompt)
#     print(f'Answers : ',answer)

#     return answer.content

