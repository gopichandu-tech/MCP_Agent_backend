"""
Quick script to discover available tools on the anyquery MCP server.
Run once, check the output, then delete this file.
"""
import requests
import json
import threading
import queue
import os
from dotenv import load_dotenv

load_dotenv()
ANYQUERY_TOKEN = os.getenv("ANYQUERY_TOKEN")
SSE_URL = "http://127.0.0.1:8070/sse"
headers_sse = {
    "Authorization": f"Bearer {ANYQUERY_TOKEN}",
    "Accept": "text/event-stream",
}
headers_post = {
    "Authorization": f"Bearer {ANYQUERY_TOKEN}",
    "Content-Type": "application/json",
}
result_queue = queue.Queue()
message_url_holder = {}
url_ready = threading.Event()
def sse_listener():
    with requests.get(SSE_URL, headers=headers_sse, stream=True, timeout=30) as r:
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data:"):
                data = line[5:].strip()
                if not message_url_holder and "/message" in data:
                    url = data if data.startswith("http") else f"http://127.0.0.1:8070{data}"
                    message_url_holder["url"] = url
                    print(f"Session URL: {url}")
                    url_ready.set()
                    continue
                try:
                    event = json.loads(data)
                    if "result" in event:
                        result_queue.put(event["result"])
                        return
                    elif "error" in event:
                        result_queue.put({"error": event["error"]})
                        return
                except json.JSONDecodeError:
                    pass
t = threading.Thread(target=sse_listener, daemon=True)
t.start()
if not url_ready.wait(timeout=10):
    print("ERROR: Could not get session URL")
    exit(1)
# Call tools/list
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
}
resp = requests.post(message_url_holder["url"], json=payload, headers=headers_post, timeout=10)
print(f"POST status: {resp.status_code}")
try:
    result = result_queue.get(timeout=15)
    print("\n=== AVAILABLE TOOLS ===")
    tools = result.get("tools", [])
    if tools:
        for tool in tools:
            print(f"  NAME: {tool.get('name')}")
            print(f"  DESC: {tool.get('description', '')[:100]}")
            print()
    else:
        print("Raw result:", json.dumps(result, indent=2)[:2000])
except queue.Empty:
    print("ERROR: Timed out waiting for tools/list response")