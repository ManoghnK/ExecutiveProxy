# CLAUDE.md — Executive Proxy
> Single source of truth. Paste the "Current Status" section at the start of every Claude session.

---

## Project
- **Name:** Executive Proxy
- **Hackathon:** Amazon Nova AI Hackathon
- **Deadline:** March 16, 2026
- **Prize Targets:** Best of Agentic System, Best of UI Automation, Grand Prize ($15k)
- **Submit Under:** Agentic AI + UI Automation categories

---

## Environment
- **AWS Account:** Slalom SSO (3410-8326-2352)
- **AWS Region:** us-east-1 (N. Virginia) — ALL resources go here
- **SSO Region:** eu-central-1 (credentials only)
- **Authentication:** AWS SSO (temporary credentials, refresh every 12h)
- **Nova Portal:** nova.amazon.com/dev — logged in with Amazon.com credentials ✅
- **Nova Act API Key:** 2335ddcf-37ce-4340-97b4-d6d1f22c5de1 ✅

---

## Confirmed Model IDs (Bedrock)
| Role | Model ID |
|------|----------|
| Transcription / Voice | `amazon.nova-2-sonic-v1:0` |
| Classifier (cheap filter) | `amazon.nova-2-lite-v1:0` |
| Executor / Reasoning | `amazon.nova-pro-v1:0` |
| UI Automation | Nova Act via nova.amazon.com API |

---

## Architecture
```
[Mic Input]
    ↓
[Nova 2 Sonic] — speech-to-text, real-time streaming (Bedrock)
    ↓
[Lambda: classifier] — Nova 2 Lite filters for action intent
    ↓ (only fires on action hit)
[Lambda: executor] — Nova Pro orchestrates tool use
    ↓                        ↓
[Nova Act Agent]      [Lambda: rag_handler]
[Jira / GCal UI]      [Pinecone → Risk Matrix]
    ↓                        ↓
              [DynamoDB]
                  ↓
            [AppSync GraphQL]
                  ↓
         [Electron Frontend (React)]
```

---

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Frontend | Electron + React + AWS SDK v2 |
| Voice Ingestion | Amazon Nova 2 Sonic (Bedrock streaming) |
| Classifier | Nova 2 Lite (Bedrock) |
| Executor | Nova Pro (Bedrock) + Tool Use |
| UI Automation | Nova Act (nova.amazon.com API) |
| Vector Store | Pinecone Serverless Free Tier |
| Document Store | Amazon S3 |
| Database | Amazon DynamoDB |
| Real-time Sync | AWS AppSync (GraphQL subscriptions) |
| Compute | AWS Lambda (Python 3.12) |
| IaC | AWS CDK (Python) |

---

## Repo Structure
```
executive-proxy/
├── CLAUDE.md                  ← THIS FILE
├── cdk/                       ← All infrastructure as code
│   ├── app.py
│   ├── schema.graphql         ← AppSync GraphQL schema
│   └── stacks/
│       ├── dynamo_stack.py
│       ├── lambda_stack.py
│       └── appsync_stack.py
├── lambdas/
│   ├── transcribe_handler/    ← Nova 2 Sonic ingestion
│   │   └── handler.py
│   ├── classifier/            ← Nova 2 Lite intent filter
│   │   └── handler.py
│   ├── executor/              ← Nova Pro + tool use
│   │   └── handler.py
│   ├── rag_handler/           ← Pinecone RAG query
│   │   └── handler.py
│   └── stream_resolver/       ← DynamoDB Stream → AppSync mutations
│       └── handler.py
├── nova_act_agent/            ← Nova Act UI automation
│   ├── jira_agent.py
│   └── calendar_agent.py
├── frontend/                  ← Electron + React
│   ├── main.js                ← Electron Main process
│   ├── preload.js             ← IPC Bridge
│   ├── package.json
│   └── src/
│       ├── App.jsx            ← Main UI Layout
│       ├── appsync-client.js  ← AppSync subscriptions
│       └── components/
│           ├── TranscriptFeed.jsx
│           ├── ActionCard.jsx
│           └── RiskMatrix.jsx
├── scripts/                   ← Local test + seed scripts
│   ├── test_classifier.py
│   ├── test_executor.py
│   └── seed_pinecone.py
├── docs/
│   └── architecture.md
├── .env.example
└── requirements.txt
```

---

## DynamoDB Tables
### Table 1: `MeetingState`
- PK: `meeting_id` (String)
- SK: `timestamp` (String, ISO8601)
- Attributes: `speaker`, `transcript_chunk`, `intent_label`, `action_triggered`, `ttl`
- Billing: PAY_PER_REQUEST
- Stream: NEW_AND_OLD_IMAGES (feeds AppSync)

### Table 2: `ActionLog`
- PK: `meeting_id` (String)
- SK: `action_id` (String, UUID)
- Attributes: `action_type` (JIRA_TICKET | CALENDAR_EVENT | RISK_MATRIX), `status`, `payload`, `result`, `created_at`
- Billing: PAY_PER_REQUEST

---

## Environment Variables (.env)
```
AWS_REGION=us-east-1
NOVA_ACT_API_KEY=2335ddcf-37ce-4340-97b4-d6d1f22c5de1 # from nova.amazon.com/dev
PINECONE_API_KEY=           # from pinecone.io
PINECONE_INDEX_NAME=executive-proxy-policies
JIRA_API_TOKEN=             # from Atlassian account
JIRA_BASE_URL=              # e.g. https://yourorg.atlassian.net
JIRA_PROJECT_KEY=           # e.g. EP
GOOGLE_CALENDAR_CREDENTIALS= # path to service account JSON
DYNAMODB_MEETING_TABLE=MeetingState
DYNAMODB_ACTION_TABLE=ActionLog
CLASSIFIER_LAMBDA_ARN=      # auto-set by CDK (transcribe → classifier wiring)
APPSYNC_API_URL=            # auto-set by CDK (ExecProxyAppSync stack output)
APPSYNC_API_KEY=            # auto-set by CDK (ExecProxyAppSync stack output)
TRANSCRIBE_LAMBDA_URL=      # Lambda Function URL for transcribe_handler
```

---

## Current Status
**Day:** 3
**Phase:** Frontend → Integration
**Current Task:** Integration Testing & UI Polish

## Completed
- [x] AWS account active
- [x] AWS CLI configured (us-east-1)
- [x] All Nova models accessible on Bedrock
- [x] Nova portal access confirmed (nova.amazon.com)
- [x] Repo structure defined
- [x] Deploy DynamoDB tables (ExecProxyDynamo stack)
- [x] Scaffold Lambda handler skeletons (code only)
- [x] Generate Nova Act API key
- [x] Deploy base Lambda skeletons (infrastructure)
- [x] Create Pinecone Index (used Titan Embeddings v2 due to Nova Multimodal issues)
- [x] Seed Pinecone with policy docs
- [x] Scaffold rag_handler (logic + Titan v2 + Nova Pro)
- [x] classifier Lambda — Nova 2 Lite, 4/4 intents correct
- [x] executor Lambda — Nova Pro tool use, all 3 routing paths working
- [x] rag_handler Lambda — Titan embeddings, Pinecone retrieval, risk matrix generation
- [x] transcribe_handler Lambda — Nova 2 Sonic via aws_sdk_bedrock_runtime, DynamoDB write, async classifier invoke
- [x] Nova Act Jira agent — 9-step act() workflow, act_get() ticket ID extraction, mock fallback, executor integration
- [x] Nova Act Calendar agent — 10-step act() workflow, ISO8601 parsing, mock fallback, executor integration, shared auth
- [x] AppSync + DynamoDB Streams — GraphQL API, stream resolver Lambda, real-time subscriptions, frontend client
- [x] Electron Frontend scaffold — React + AppSync subscriptions + mic capture pipeline
- [x] Refactor frontend to use AWS SDK for direct Lambda invocation (bypass SCPs)
- [x] Fix Jira Integration — Resolved 400 Bad Request by correcting JIRA_PROJECT_KEY to 'SCRUM' and validating payload
- [x] Fix Calendar Date Bug — Injected current datetime into Executor's Nova Pro system prompt to anchor relative date resolution (was defaulting to 2023)
- [x] Fix Local Executor Bridge — Resolved Python `.env` UTF-16 encoding crash, restored AWS SSO session inheritance in subprocess, and corrected Python namespace resolution (`nova_act_agent`).
- [x] Secure Workstation — Updated `.gitignore` to prevent committing local Nova Act UI profile caches (`browser_profile/`) and session logs.

## In Progress
- [x] Integration Testing — End-to-end voice to action validation (Local executor pipe tested successfully)
- [ ] Polish UI — Add real-time risk visualization

## Known Blockers
- None

## Decisions Made
1. Use Nova 2 Sonic over Amazon Transcribe — cleaner Nova-native story for judges
2. Nova Act called via nova.amazon.com API key (not Bedrock) — only place it's available
3. All other Nova models called via Bedrock — uses $100 AWS credits
4. PAY_PER_REQUEST on DynamoDB — zero cost at hackathon scale
5. CDK (Python) for IaC — reproducible, clean submission
6. Embedding model: amazon.titan-embed-text-v2:0 (1024-dim) — Nova multimodal 
   embeddings incompatible with account; Titan is production-grade equivalent
7. Use Nova 2 Lite Cross-Region Inference Profile (`us.amazon.nova-2-lite-v1:0`) — standard on-demand ID not supported in us-east-1.
8. Executor uses us.amazon.nova-pro-v1:0 (cross-region inference profile) — more stable than direct regional endpoint
9. Calendar uses Nova Act UI automation with mock fallback — real Google Calendar API adds no demo value, Nova Act is the prize angle
10. POLICY_RISK routes directly to rag_handler via async Lambda invoke — no double Nova Pro call
11. Nova 2 Sonic uses `aws_sdk_bedrock_runtime` SDK (not boto3) — bidirectional streaming requires the experimental Python SDK
12. Transcribe handler uses chunked Lambda model — frontend sends 3-10s audio chunks per invocation; each creates a Nova Sonic session, transcribes, writes DynamoDB, triggers classifier
13. Nova Act cannot run inside Lambda — requires a real browser (Playwright/Chrome). Runs locally alongside Electron frontend or on EC2/ECS
14. Jira auth uses persistent `user_data_dir` — one-time `--setup-auth` saves the browser session, subsequent runs reuse it with `clone_user_data_dir=False`
14b. Ensure that `use_default_chrome_browser=True` is NOT used on Windows setups as it raises a `NotImplementedError` via Nova Act SDK since it is only currently supported on macOS.
15. Executor has `NOVA_ACT_ENABLED` toggle — when true, routes to Nova Act agent first with REST API fallback; when false (Lambda default), uses REST API only
16. Calendar and Jira agents share the same `user_data_dir` — single `--setup-auth` authenticates both services if done from the same browser profile
17. AppSync uses API_KEY auth — simplest for hackathon; IAM/Cognito for production
18. Stream resolver uses stdlib only (urllib) — zero Lambda dependencies, fast cold start
19. Frontend uses no bundler (Babel/React via CDN ESM) — simplifies local iteration and reduces build complexity
20. Frontend uses AWS SDK in Electron Main process for Lambda invocation — HTTP Function URLs blocked by AWS Organization SCPs
21. Audio chunking happens in React, sent via IPC to Main, then direct Lambda invoke — avoids CORS/SCP issues completely
22. Jira Rest API V3 implementation — requires `Atlassian Document Format` (ADF) for the descriptions; simple text is rejected with 400 Bad Request. Executor now handles this construction.
23. Local Executor Bridge (`local_executor.py`) — The frontend spawns a local Python subprocess to execute Nova Act UI agents (like Jira and Calendar) locally on the user's machine when `NOVA_ACT_ENABLED` is true. Real-time status updates are emitted via `stdout` JSON lines and displayed in the React UI, while the remote AppSync subscriptions are ignored to prevent duplicate action cards.
24. Nova Act Agent Optimizations — Complex prompts combining multiple fields (summary, description, assignees) are used in a single `nova.act()` call for reliability. The calendar agent bypasses brittle pop-ups by navigating directly to the `/r/eventedit` URL, and step limits (`max_steps`) are increased to 60.
25. Executor system prompt includes dynamic current datetime — Nova Pro requires explicit date anchoring to resolve relative references ("Thursday", "tomorrow") correctly; without it, dates default to training-era 2023.
