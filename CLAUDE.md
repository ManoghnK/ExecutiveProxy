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
- **AWS Account:** ManoghnK (0840-4725-5317)
- **AWS Region:** us-east-1 (N. Virginia) — ALL resources go here
- **AWS CLI:** Configured ✅
- **Nova Portal:** nova.amazon.com/dev — logged in with Amazon.com credentials ✅
- **Nova Act API Key:** 2335ddcf-37ce-4340-97b4-d6d1f22c5de1 ✅
- **Pinecone:** Not yet configured

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
| Frontend | Electron + React |
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
│   └── rag_handler/           ← Pinecone RAG query
│       └── handler.py
├── nova_act_agent/            ← Nova Act UI automation
│   ├── jira_agent.py
│   └── calendar_agent.py
├── frontend/                  ← Electron + React
│   ├── src/
│   └── package.json
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
```

---

## Current Status
**Day:** 1
**Phase:** Infrastructure Setup
**Current Task:** DAY 2: Build Nova Act UI agent + transcribe_handler

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

## In Progress
- [ ] Connect DynamoDB Stream to AppSync

## Known Blockers
- None


## Known Blockers
- Pinecone account not yet created

## Decisions Made
1. Use Nova 2 Sonic over Amazon Transcribe — cleaner Nova-native story for judges
2. Nova Act called via nova.amazon.com API key (not Bedrock) — only place it's available
3. All other Nova models called via Bedrock — uses $100 AWS credits
4. PAY_PER_REQUEST on DynamoDB — zero cost at hackathon scale
5. CDK (Python) for IaC — reproducible, clean submission
6. Embedding model: amazon.titan-embed-text-v2:0 (1024-dim) — Nova multimodal 
   embeddings incompatible with account; Titan is production-grade equivalent
7. Use Nova 2 Lite Cross-Region Inference Profile (`us.amazon.nova-2-lite-v1:0`) — standard on-demand ID not supported in us-east-1.
7. Executor uses us.amazon.nova-pro-v1:0 (cross-region inference profile) — more stable than direct regional endpoint
8. Calendar integration is mocked with TODO — real Google Calendar API in Day 3
9. POLICY_RISK routes directly to rag_handler via async Lambda invoke — no double Nova Pro call
