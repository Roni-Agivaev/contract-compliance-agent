# Contract Compliance Agent

A multi-agent AI system that audits international employment contracts against **both** the
company's and the employee's local labor law, and **auto-fixes** them — returning a compliant
contract plus a plain-English log of every change.

Course project — Idea 3 (Recruiting & Talent Acquisition). Team **Maayan, Roni, Ofir** (group `3_02`).

## Architecture (presentation slide 6)

```
Draft Contract → Supervisor → (Company Law ‖ Employee Law) → Supervisor → Editor ⇄ Reflection → Compliant Contract + change log
```

- **Supervisor** — reads the two jurisdictions from the input prompt, scope-guards, plans legal
  search queries, dispatches the two law agents in parallel, then finalizes. If no breaches are
  found it **autonomously returns the original contract with a "No breaches found" message**.
- **Company Law / Employee Law** (parallel) — each retrieves its jurisdiction's statutes from
  Pinecone (+ ILO baseline), runs the **MinimumWageTool** (Supabase), and flags breaches with
  citations + fixes.
- **Editor ⇄ Reflection** — Editor rewrites flagged clauses; Reflection verifies and loops back
  up to `MAX_REFLECTION_ITERS` (2) until it passes.

Module names are identical across the architecture diagram, the `steps` trace, and the code.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/team_info` | Team + group details |
| GET | `/api/agent_info` | Description, purpose, prompt template, worked example + steps |
| GET | `/api/model_architecture` | Architecture diagram (`image/png`) |
| POST | `/api/execute` | `{ "prompt": "..." }` → `{ status, error, response, steps }` |
| GET | `/` | Minimal no-auth GUI |

**Input prompt format** (all three fields in the single `prompt` string):
```
Company country: United States
Employee country: Germany
Contract / Offer text: <the full contract text>
```

## Deploy (Vercel)
1. Push this repo to GitHub.
2. Import it in Vercel; the included `vercel.json` builds `api/index.py` with `@vercel/python`
   and routes everything to it.
3. Add the four env vars (above) in the Vercel project settings.
4. Deploy. The GUI is at `/`; `/api/execute` completes well within the 300s serverless limit.

## Jurisdiction subset
Indexed: **US** (FLSA), **UK** (ERA 1996), **Germany** (BGB), **Israel** (employment guide),
plus the **ILO** baseline and a global **minimum-wage** table. To add a country: drop its PDF in
the data folder and add one entry to `JURISDICTIONS` in `config.py`.

## Config knobs (`config.py`)
`CHAT_MODEL`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `MAX_REFLECTION_ITERS`,
`JURISDICTIONS`.
