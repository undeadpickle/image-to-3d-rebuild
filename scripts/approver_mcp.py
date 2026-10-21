#!/usr/bin/env python3
"""Scoped permission-prompt MCP server for headless `claude -p` runs.

Use when a user-level "ask" rule blocks a paid generation tool in headless mode (where
nobody can click Allow) and the user has ALREADY approved a specific number of runs.
It approves ONLY the listed tools, caps real submissions, and logs every decision.
It never edits the user's settings.

WARNING: this server auto-answers "allow" to permission prompts. Only run it on a prompt
you wrote yourself, keep APPROVE_TOOLS and --allowedTools as short as the example below,
and never add broad tools (Bash(*), Write to arbitrary paths) to either list.

  APPROVE_TOOLS="mcp__higgsfield__generate_3d,mcp__higgsfield__jobs_wait,mcp__higgsfield__show_generation_by_ids,mcp__higgsfield__get_preferences" \
  SUBMIT_TOOL=mcp__higgsfield__generate_3d MAX_SUBMITS=1 \
  claude -p "$(cat gen_prompt.txt)" \
    --mcp-config approver.mcp.json --permission-prompt-tool mcp__approver__approve \
    --allowedTools "mcp__higgsfield__*,ToolSearch,Bash(curl:*),Bash(mkdir:*),Write(scan/*)"

approver.mcp.json:
  {"mcpServers": {"approver": {"type": "stdio", "command": "python3", "args": ["/abs/path/approver_mcp.py"]}}}

A call to SUBMIT_TOOL whose params contain get_cost:true (a price preflight) is free and
not counted. Keep ToolSearch allowed: MCP tool schemas are deferred and without it the run
fails with "prompt too long" or cannot load the tools.
"""
import json, os, sys

LOG = os.environ.get("APPROVER_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "approver_log.jsonl"))
MAX_SUBMITS = int(os.environ.get("MAX_SUBMITS", "1"))
SUBMIT_TOOL = os.environ.get("SUBMIT_TOOL", "mcp__higgsfield__generate_3d")
ALLOW = set(filter(None, os.environ.get("APPROVE_TOOLS", ",".join([
    "mcp__higgsfield__generate_3d", "mcp__higgsfield__jobs_wait",
    "mcp__higgsfield__show_generation_by_ids", "mcp__higgsfield__get_preferences"])).split(",")))
submits = 0


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()


def decide(args):
    global submits
    name = args.get("tool_name"); inp = args.get("input", {}) or {}
    p = inp.get("params", inp) if isinstance(inp, dict) else {}
    if isinstance(p, str):
        try: p = json.loads(p)
        except Exception: p = {}
    if name not in ALLOW:
        return {"behavior": "deny", "message": f"approver only allows: {sorted(ALLOW)}"}
    if name == SUBMIT_TOOL and not p.get("get_cost"):
        if submits >= MAX_SUBMITS or int(p.get("count", 1)) > 1:
            return {"behavior": "deny", "message": f"submission cap reached ({MAX_SUBMITS}); do not resubmit, poll the existing job"}
        submits += 1
    return {"behavior": "allow", "updatedInput": inp}


for line in sys.stdin:
    try: msg = json.loads(line)
    except Exception: continue
    mid = msg.get("id"); m = msg.get("method")
    if m == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
              "capabilities": {"tools": {}}, "serverInfo": {"name": "approver", "version": "1"}}})
    elif m == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [{"name": "approve", "description": "permission prompt",
              "inputSchema": {"type": "object", "properties": {"tool_name": {"type": "string"}, "input": {"type": "object"}, "tool_use_id": {"type": "string"}}}}]}})
    elif m == "tools/call":
        a = msg["params"].get("arguments", {})
        d = decide(a)
        with open(LOG, "a") as f:
            f.write(json.dumps({"tool": a.get("tool_name"), "input": a.get("input"), "decision": d["behavior"]}) + "\n")
        send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(d)}]}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
