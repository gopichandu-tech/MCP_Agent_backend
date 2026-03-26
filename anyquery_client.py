import requests
import json
import threading
import queue
import time
import os
from dotenv import load_dotenv

SSE_URL = "http://127.0.0.1:8070/sse"


def run_sql(query):
    """
    Execute SQL query on AnyQuery MCP server using correct SSE protocol:
    Step 1: Open SSE connection → capture session endpoint from server
    Step 2: POST command to the session endpoint
    Step 3: Read result from the SAME open SSE stream
    """

    print(f"\n[DEBUG] Query: {query}")
    
    # Load dynamic token on every single query to bypass uvicorn caching
    load_dotenv(override=True)
    current_token = os.getenv("ANYQUERY_TOKEN")

    headers = {
        "Authorization": f"Bearer {current_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    result_queue = queue.Queue()
    message_url_holder = {}   # shared dict to pass message URL from SSE thread
    url_ready_event = threading.Event()

    def sse_listener():
        try:
            print("[DEBUG] Opening SSE connection...")
            with requests.get(SSE_URL, headers=headers, stream=True, timeout=30) as sse_resp:
                print(f"[DEBUG] SSE Status: {sse_resp.status_code}")
                if sse_resp.status_code != 200:
                    result_queue.put({"error": f"SSE connect failed: {sse_resp.status_code}"})
                    url_ready_event.set()
                    return

                for line in sse_resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue

                    print(f"[DEBUG] SSE line: {line[:120]}")

                    # The first event from anyquery is: data: /message?sessionId=<id>
                    if line.startswith("data:"):
                        data_val = line[5:].strip()

                        # Capture the session endpoint URL
                        if not message_url_holder and "/message" in data_val:
                            # anyquery may send full URL or just the path
                            if data_val.startswith("http"):
                                full_url = data_val
                            else:
                                full_url = f"http://127.0.0.1:8070{data_val}"
                            message_url_holder["url"] = full_url
                            print(f"[DEBUG] Got session endpoint: {full_url}")
                            url_ready_event.set()   # signal main thread to POST
                            continue

                        # Parse subsequent events as JSON results
                        try:
                            event = json.loads(data_val)
                            if "result" in event:
                                print("[DEBUG] Got result from SSE!")
                                result_queue.put({"result": event["result"]})
                                return
                            elif "error" in event:
                                print(f"[DEBUG] Got error from SSE: {event['error']}")
                                result_queue.put({"error": str(event["error"])})
                                return
                        except json.JSONDecodeError:
                            pass  # not JSON, skip

        except Exception as e:
            print(f"[ERROR] SSE listener error: {e}")
            import traceback
            traceback.print_exc()
            result_queue.put({"error": str(e)})
            url_ready_event.set()

    # Start SSE listener in a background thread
    t = threading.Thread(target=sse_listener, daemon=True)
    t.start()

    # Wait for session endpoint URL (max 10 seconds)
    if not url_ready_event.wait(timeout=10):
        return {"error": "Timed out waiting for SSE session endpoint", "type": "timeout"}

    if "url" not in message_url_holder:
        return {"error": "Failed to get session endpoint from SSE", "type": "sse_error"}

    message_url = message_url_holder["url"]

    # Step 2: POST the SQL query to the session endpoint
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "executeQuery",
            "arguments": {
                "query": query
            }
        }
    }

    post_headers = {
        "Authorization": f"Bearer {current_token}",
        "Content-Type": "application/json",
    }

    try:
        print(f"[DEBUG] Posting to {message_url}...")
        resp = requests.post(message_url, json=payload, headers=post_headers, timeout=10)
        print(f"[DEBUG] POST status: {resp.status_code} | body: {resp.text[:200]}")
        if resp.status_code not in [200, 202, 204]:
            return {"error": f"POST failed: {resp.status_code} {resp.text[:200]}", "type": "post_error"}
    except Exception as e:
        print(f"[ERROR] POST failed: {e}")
        return {"error": str(e), "type": "post_error"}

    # Step 3: Wait for result from SSE stream (max 30 seconds)
    try:
        result = result_queue.get(timeout=30)
        print(f"[DEBUG] Final result type: {type(result)}")
        return result
    except queue.Empty:
        return {"error": "Query timed out waiting for result", "type": "timeout"}