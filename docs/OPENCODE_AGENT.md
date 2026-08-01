# opencode agent profile

Client side only.

Default 3B/7B profile:

```bash
mkdir -p ~/.config/opencode/agents
cp opencode/opencode.local-lan.json ~/.config/opencode/opencode.json
cp agents/*.md ~/.config/opencode/agents/
```

Edit only the endpoint:
```json
"baseURL": "http://IP_SERVER:8080/v1",
"apiKey": "{env:LOCAL_AI_API_KEY}"
```

Export `LOCAL_AI_API_KEY` from a trusted secret source before starting
OpenCode. Do not write the key into JSON or pass it on a process command line.

Recommended operation:
- Use `plan-local` before edits.
- Use `build-local` for small patches.
- The dynamic Obsidian MCP is intentionally absent from the autonomous path.
- Avoid huge repositories in context.
- Exclude binaries and virtualenvs.

DS4 Intel profile:

```bash
mkdir -p ~/.config/opencode/agents
cp opencode/opencode.ds4-intel-lan.json ~/.config/opencode/opencode.json
cp agents/*.md ~/.config/opencode/agents/
```

Edit only the endpoint:

```json
"baseURL": "http://IP_SERVER:8081/v1",
"apiKey": "{env:LOCAL_AI_API_KEY}"
```

Use DS4 for long planning/build loops where latency is acceptable. Keep the same
agent discipline: small diffs, explicit tool confirmation, no binary context.
