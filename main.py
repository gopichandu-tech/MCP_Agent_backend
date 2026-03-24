from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent import run_agent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# @app.post("/ask")
# async def ask_question(data: dict):

#     question = data["question"]

#     answer = run_agent(question)

#     return {"answer": answer}

@app.post("/ask")
async def ask_question(data: dict):
    print("data : ", data)
    try:
        question = data["question"]
        answer = run_agent(question)
        print("Answer:", answer)
        return {"answer": answer}
    except Exception as e:
        print("ERROR:", str(e)) 
        return {"error": str(e)}