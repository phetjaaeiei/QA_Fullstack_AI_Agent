# QA Brain — AI-Powered Full Stack QA Platform
**Design Spec** · Extosoft · 2026-07-01

---

## 1. Vision & Goal

สร้าง AI Agent Platform ที่แทนที่ QA ทุกรูปแบบ 100% ด้วย AI ได้แก่ Manual QA, Automation QA, Performance QA, Security QA และ QA Analytics โดยรวมความสามารถทั้งหมดไว้ใน Agent system เดียวที่ทำงานร่วมกันผ่าน Web Dashboard แบบ real-time

**Success Criteria:**
- Generate test cases จาก Jira/Figma/OpenAPI ได้ภายใน 30 วินาที
- Auto-generate Playwright/Robot scripts พร้อม company framework
- OWASP Top 10 coverage mapping อัตโนมัติทุก feature
- Release Readiness Score 0–100 พร้อม Go/No-Go recommendation
- แทนที่งาน QA ได้ 80%+ ใน Phase 1 (Manual QA domain)

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Dashboard (React)                      │
│   [Chat with QA Brain]  [Test Cases]  [Risk Score]  [KPIs]  │
└─────────────────────┬───────────────────────────────────────┘
                      │ WebSocket / REST
┌─────────────────────▼───────────────────────────────────────┐
│                  FastAPI Backend                              │
│        Agent Runtime  ·  Session Manager  ·  API             │
└─────────────────────┬───────────────────────────────────────┘
                      │ Claude Agent SDK
┌─────────────────────▼───────────────────────────────────────┐
│             QA Orchestrator Agent  (Master)                  │
│   รับ request → วิเคราะห์ intent → route + aggregate        │
└──┬──────────┬───────────┬──────────────┬────────────────────┘
   │          │           │              │              │
   ▼          ▼           ▼              ▼              ▼
Manual    Automation  Performance    Security      Analytics
QA Agent  QA Agent    QA Agent       QA Agent      Agent
   │          │           │              │              │
   └──────────┴───────────┴──────────────┴──────────────┘
                          │
              ┌───────────▼───────────┐
              │    MCP Tool Layer     │
              │  Jira · GitHub · Figma│
              │  OpenAPI · FileSystem │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │  PostgreSQL  · Redis  │
              └───────────────────────┘
```

### Design Principles

| หลักการ | รายละเอียด |
|---------|-----------|
| Each agent เก่งเฉพาะด้าน | System prompt + tools ของแต่ละ agent focused 100% ในงานของตัวเอง |
| Orchestrator ไม่ทำงาน QA | หน้าที่เดียวคือ route, coordinate, aggregate ผลลัพธ์ |
| Parallel execution | หลาย agents ทำงานพร้อมกันได้เมื่อ tasks ไม่ depend กัน |
| MCP เป็น integration layer | ทุก external tool เข้าผ่าน MCP — swap ได้ไม่กระทบ agents |
| Context isolation | แต่ละ agent มี context ของตัวเอง ไม่ปนกัน |

---

## 3. Agent Specifications

### 3.1 QA Orchestrator Agent (Master)

**Role:** AI QA Lead — รับทุก request, วิเคราะห์ intent, สั่งงาน specialists, aggregate ผล

**Responsibilities:**
- Intent classification: วิเคราะห์ว่า request ต้องใช้ agent ไหน (อาจมากกว่า 1)
- Parallel routing: spawn หลาย specialist agents พร้อมกัน
- Context aggregation: รวมผลจากหลาย agents เป็น response เดียว
- Memory management: จำ project context ข้าม session ผ่าน Redis
- Release Gate decision: รวม risk scores จากทุก domain → Go/No-Go

**Model:** `claude-opus-4-8` (ต้องการ reasoning สูงสุดสำหรับ orchestration)

---

### 3.2 Manual QA Agent

**Role:** แทน Manual QA Engineer — ตั้งแต่อ่าน requirement จนถึง release decision

| Tool | Input | Output |
|------|-------|--------|
| `analyze_story` | Jira Story ID | Ambiguity list + Missing requirements |
| `generate_test_cases` | Jira / Figma / OpenAPI | Functional + Edge + Negative + E2E test cases |
| `suggest_security_cases` | Test cases | Abuse cases + Permission boundary cases |
| `build_traceability_map` | Story IDs | Requirement → Test Case matrix |
| `detect_coverage_gaps` | Sprint ID | Missing coverage graph + recommendations |
| `score_release_readiness` | Sprint ID | Score 0–100 + Go/No-Go + detailed recommendations |

**Model:** `claude-sonnet-4-6`

**Key Prompt Focus:** Test design thinking, domain analysis, requirement clarity, risk-based testing

---

### 3.3 Automation QA Agent

**Role:** แทน Automation Engineer — ตั้งแต่ generate script จนถึง fix flaky test

| Tool | Input | Output |
|------|-------|--------|
| `generate_script_from_spec` | OpenAPI / Figma / Jira | Playwright + Robot Framework skeleton |
| `explore_and_generate` | App URL | Auto-crawl UI → generate full test scripts |
| `apply_company_framework` | Raw script | Script ตาม Extosoft coding standard |
| `suggest_self_healing` | Broken locator | 3–5 alternative locators + strategy |
| `classify_failure` | Failed test log | Root cause: Bug / Data / Env / Script |
| `auto_fix_script` | Failed script + error | Fixed script + explanation |
| `generate_test_data` | Test case requirements | Test data sets + boundary variations |
| `map_script_traceability` | Script + Story ID | Script ↔ Story ↔ Test Case links |

**Model:** `claude-sonnet-4-6`

**Key Prompt Focus:** Code generation, framework patterns, locator strategy, failure analysis

---

### 3.4 Performance QA Agent

**Role:** แทน Performance Engineer — ตั้งแต่ออกแบบ workload จนถึง capacity planning

| Tool | Input | Output |
|------|-------|--------|
| `build_workload_model` | Business flow / Stories | Concurrent users, ramp-up pattern, scenarios |
| `analyze_perf_risk` | Story / Requirements | Performance risk list + priority |
| `generate_perf_script` | OpenAPI spec + workload | JMeter / k6 / Gatling script |
| `analyze_perf_result` | Test result + APM logs | Root cause + bottleneck location |
| `identify_bottleneck` | APM trace data | App / DB / API / Infra hypothesis |
| `define_sla_slo` | Business requirements | SLA thresholds + Pass/Fail criteria |
| `write_perf_defect` | Bottleneck finding | Defect report + graph evidence |
| `recommend_capacity` | Test results + load model | Infra sizing recommendation |

**Model:** `claude-sonnet-4-6`

**Key Prompt Focus:** Load modeling, APM analysis, bottleneck diagnosis, infrastructure sizing

---

### 3.5 Security QA Agent

**Role:** แทน Security QA / OWASP specialist — ครอบคลุมทุก feature ทุก OWASP category

| Tool | Input | Output |
|------|-------|--------|
| `generate_owasp_test_cases` | Story / Feature | Test cases ตาม OWASP Top 10 ทุก category |
| `map_story_to_owasp` | Story IDs | Story → OWASP Risk mapping matrix |
| `generate_rbac_matrix` | Roles + Features | Role-Based Access test matrix ทุก role |
| `generate_api_security_checklist` | OpenAPI spec | Broken Access / Injection / Auth checklist |
| `triage_vulnerabilities` | Scanner results (ZAP/etc) | Priority ranking + False positive filter |
| `write_security_defect` | Vulnerability finding | Report + Impact + CVSS score + Evidence |
| `build_owasp_dashboard` | Sprint / Release | OWASP coverage % + Traceability map |

**Model:** `claude-opus-4-8` (security analysis ต้องการ reasoning ลึก)

**Key Prompt Focus:** OWASP Top 10 expertise, threat modeling, access control, injection patterns

---

### 3.6 Analytics Agent

**Role:** Control Tower — รวมข้อมูลจากทุก agent สร้าง visibility ให้ทีมและลูกค้า

| Tool | Input | Output |
|------|-------|--------|
| `generate_release_risk_dashboard` | All agents data | Risk score per domain + overall score |
| `generate_quality_kpi_report` | Sprint ID | Defect density, coverage %, automation rate |
| `build_evidence_pack` | Sprint / Release | Audit-ready evidence bundle |
| `trend_analysis` | Historical data | Quality trend + regression detection |
| `generate_executive_summary` | Release data | 1-page executive report |

**Model:** `claude-sonnet-4-6`

**Key Prompt Focus:** Data synthesis, metric interpretation, business communication

---

## 4. MCP Tool Servers

### 4.1 Jira MCP Server
- `get_story(story_id)` — fetch story details, acceptance criteria, attachments
- `search_stories(jql)` — search by sprint, project, assignee
- `create_test_case(story_id, test_case)` — write test cases back to Jira
- `create_defect(story_id, defect)` — create bug tickets
- `get_sprint_stories(sprint_id)` — all stories in a sprint

### 4.2 GitHub/GitLab MCP Server
- `get_pr_diff(pr_id)` — code changes for review
- `trigger_pipeline(branch)` — run CI/CD
- `get_test_results(run_id)` — latest test run results
- `list_open_prs(repo)` — PRs pending test coverage

### 4.3 Figma MCP Server
- `get_components(file_id)` — UI components list
- `get_screen_details(frame_id)` — screen layout + interactions
- `export_screen(frame_id)` — screen image for visual reference

### 4.4 OpenAPI MCP Server
- `parse_spec(url_or_path)` — parse OpenAPI/Swagger file
- `list_endpoints(spec)` — all API endpoints + methods
- `get_endpoint_schema(endpoint)` — request/response schema
- `detect_security_issues(spec)` — basic security smell detection

### 4.5 FileSystem MCP Server
- `save_script(path, content)` — save generated test scripts
- `save_report(path, content)` — save test reports + evidence
- `read_file(path)` — read existing scripts for analysis

---

## 5. Database Schema

```sql
-- Core project context
projects (id, name, jira_project_key, github_repo, figma_file_id, created_at)
stories  (id, project_id, jira_id, title, description, status, sprint_id)

-- Manual QA outputs
test_cases (
  id, story_id, title,
  type ENUM(functional, edge, negative, security, e2e, performance),
  steps JSONB, expected_result TEXT,
  source ENUM(manual, ai_generated),
  created_by_agent VARCHAR, created_at
)

-- Automation QA outputs
automation_scripts (
  id, story_id, test_case_id, framework ENUM(playwright, robot),
  content TEXT, health_status ENUM(healthy, flaky, broken),
  last_run_at, failure_root_cause VARCHAR, created_at
)

-- Performance QA outputs
perf_test_runs (
  id, story_id, tool ENUM(jmeter, k6, gatling),
  workload_model JSONB, script_content TEXT,
  result_summary JSONB, bottleneck_findings JSONB,
  sla_thresholds JSONB, created_at
)

-- Security QA outputs
security_findings (
  id, story_id, owasp_category VARCHAR,
  severity ENUM(critical, high, medium, low),
  description TEXT, evidence JSONB,
  status ENUM(open, fixed, accepted), created_at
)

-- Aggregated release decisions
release_assessments (
  id, sprint_id,
  manual_score INT, automation_score INT,
  perf_score INT, security_score INT,
  overall_score INT,
  recommendation ENUM(go, no_go, conditional),
  findings JSONB, created_at
)

-- Agent conversation memory
agent_sessions (id, session_id, user_id, messages JSONB, context JSONB, created_at)
```

---

## 6. Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM — daily tasks | `claude-sonnet-4-6` |
| LLM — complex reasoning | `claude-opus-4-8` (Orchestrator + Security) |
| Agent Framework | Anthropic Claude Agent SDK + MCP Protocol |
| Backend | Python 3.12 + FastAPI + Uvicorn |
| MCP Servers | Python MCP SDK (one server per integration) |
| Frontend | React 18 + TypeScript + Vite |
| UI Components | shadcn/ui + Tailwind CSS |
| Charts | Recharts (metrics) + React Flow (traceability graph) |
| Database | PostgreSQL 16 + SQLAlchemy (async) + Alembic |
| Cache / Session | Redis 7 |
| Dev Deployment | Docker Compose |
| Prod Deployment | Docker + cloud (Phase 2027) |

---

## 7. Web Dashboard Panels

| Panel | รายละเอียด |
|-------|-----------|
| **Chat with QA Brain** | Real-time streaming chat กับ Orchestrator, แสดง agent ที่กำลังทำงาน |
| **Test Case Manager** | ดู/แก้ไข test cases พร้อม filter by type/story/coverage |
| **Traceability Graph** | React Flow graph: Story → Test Case → Script → Defect |
| **Release Risk Dashboard** | Gauge chart 0–100 per domain + overall + Go/No-Go badge |
| **OWASP Coverage** | Heat map ของ OWASP Top 10 × Features |
| **Agent Status Bar** | แสดง agent ที่ active + progress real-time |
| **KPI Report** | Charts: defect trend, coverage %, automation rate |

---

## 8. Phased Delivery Roadmap

### Phase 1 — MVP (Q3 2026, เดือน 1–2)
**Focus: Manual QA Agent + Core Infrastructure**
- FastAPI backend + WebSocket
- PostgreSQL + Redis setup
- QA Orchestrator Agent (basic routing)
- Manual QA Agent ครบทุก tool
- Jira MCP Server + OpenAPI MCP Server
- Web Dashboard: Chat Panel + Test Case Manager
- Demo: Generate test cases จาก Jira story

### Phase 2 — Automation + Security (Q4 2026, เดือน 3–5)
**Focus: Automation QA Agent + Security QA Agent**
- Automation QA Agent ครบทุก tool
- Security QA Agent ครบทุก tool
- GitHub/GitLab MCP Server + Figma MCP Server
- Release Risk Dashboard (Manual + Automation + Security scores)
- OWASP Coverage panel
- Traceability Graph

### Phase 3 — Performance + Analytics + IP (2027, เดือน 6–12)
**Focus: Performance QA Agent + Analytics + Domain IP**
- Performance QA Agent ครบทุก tool
- Analytics Agent + Executive reporting
- Full Release Risk aggregation (all 5 domains)
- Banking/Insurance domain-specific test templates
- Multi-tenant (ขาย Managed Service ให้ลูกค้า)

---

## 9. Project Structure

```
qa-brain/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── chat.py               # WebSocket chat endpoint
│   │   │   └── reports.py            # REST endpoints
│   │   ├── agents/
│   │   │   ├── orchestrator.py       # Master QA Orchestrator
│   │   │   ├── manual_qa.py          # Manual QA Agent
│   │   │   ├── automation_qa.py      # Automation QA Agent
│   │   │   ├── performance_qa.py     # Performance QA Agent
│   │   │   ├── security_qa.py        # Security QA Agent
│   │   │   └── analytics.py          # Analytics Agent
│   │   ├── mcp_servers/
│   │   │   ├── jira_mcp.py
│   │   │   ├── github_mcp.py
│   │   │   ├── figma_mcp.py
│   │   │   ├── openapi_mcp.py
│   │   │   └── filesystem_mcp.py
│   │   ├── models/                   # SQLAlchemy models
│   │   ├── database.py
│   │   └── config.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatPanel/
│   │   │   ├── TestCasePanel/
│   │   │   ├── RiskDashboard/
│   │   │   ├── TraceabilityGraph/
│   │   │   └── AgentStatusBar/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── TestCases.tsx
│   │   │   ├── Scripts.tsx
│   │   │   └── SecurityCoverage.tsx
│   │   └── hooks/
│   │       └── useAgentChat.ts
│   └── Dockerfile
├── docs/
│   └── superpowers/specs/
│       └── 2026-07-01-qa-brain-design.md
└── docker-compose.yml
```

---

## 10. Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| MCP server ล่ม → agents ทำงานไม่ได้ | Graceful fallback: agent แจ้ง user + retry logic |
| LLM hallucinate test cases | ทุก output มี confidence score + human review mode |
| Context window เกินใน complex sprint | แบ่ง batch processing + summarization |
| Jira/Figma API rate limit | Redis cache + exponential backoff |
| Script generate ผิด framework | Company framework template as system prompt anchor |

---

## 11. Authentication & Authorization

### User Authentication
- **JWT-based auth** — FastAPI + python-jose
- Login ผ่าน Web Dashboard → รับ JWT token → แนบทุก request
- Token expiry: 8 ชั่วโมง (working day) + refresh token 30 วัน

### Roles
| Role | สิทธิ์ |
|------|--------|
| `qa_engineer` | ใช้งาน chat, ดู/export test cases, scripts |
| `qa_lead` | ทุกอย่างของ qa_engineer + approve release, manage project config |
| `admin` | ทุกอย่าง + user management, API key management |

### API Key Management
- Anthropic API key, Jira token, GitHub token, Figma token เก็บใน environment variables
- ไม่เก็บใน database หรือ code
- `.env.example` ไว้เป็น template สำหรับ setup

---

## 12. WebSocket Protocol

Chat ระหว่าง Dashboard กับ Backend ใช้ WebSocket เพื่อ streaming real-time

### Message Format (Client → Server)
```json
{
  "type": "user_message",
  "session_id": "sess_abc123",
  "project_id": "proj_001",
  "content": "Generate test cases for PROJ-123"
}
```

### Message Format (Server → Client)
```json
{ "type": "agent_start",    "agent": "manual_qa",  "message": "กำลัง fetch story จาก Jira..." }
{ "type": "stream_delta",   "agent": "manual_qa",  "delta": "พบ 3 ambiguity ใน acceptance criteria..." }
{ "type": "agent_complete", "agent": "manual_qa",  "data": { "test_cases": [...] } }
{ "type": "orchestrator_done", "summary": "...",   "panels_to_update": ["test_cases", "traceability"] }
```

Dashboard อ่าน `panels_to_update` เพื่อ refresh เฉพาะ panel ที่มีข้อมูลใหม่ ไม่ reload ทั้งหน้า

---

## 13. API Cost Management

Claude API มี cost ต้องจัดการเพื่อให้ scalable ทางธุรกิจ

### Model Selection Strategy
| งาน | Model | เหตุผล |
|-----|-------|--------|
| Generate test cases (ปกติ) | `claude-sonnet-4-6` | เร็ว ถูก เพียงพอ |
| Security analysis, Orchestration | `claude-opus-4-8` | ต้องการ reasoning ลึก |
| Quick intent classification | `claude-haiku-4-5-20251001` | ถูกมาก เหมาะกับ routing |

### Caching Strategy
- Cache Jira story content ใน Redis TTL 30 นาที — ป้องกัน refetch ซ้ำ
- Cache generated test cases ต่อ story version — ถ้า story ไม่เปลี่ยน ไม่ generate ใหม่
- Prompt caching ผ่าน Anthropic API (system prompt ยาวๆ cache ได้ถึง 90%)

### Usage Tracking
- บันทึก `input_tokens`, `output_tokens`, `model` ทุก agent call ใน `agent_sessions`
- Dashboard แสดง token usage per sprint สำหรับ cost visibility

---

## 14. Observability & Monitoring

### Application Logs
- Structured JSON logging ทุก agent call: `agent_type`, `tool_called`, `duration_ms`, `tokens_used`, `status`
- FastAPI request logs: method, path, status code, latency

### Health Checks
- `GET /health` — FastAPI, DB, Redis, MCP servers status
- Agent ping ทุก 60 วินาที ตรวจว่า Claude API ตอบสนอง

### Key Metrics to Track
| Metric | เป้าหมาย |
|--------|---------|
| Test case generation time | < 30 วินาที per story |
| Agent success rate | > 95% |
| MCP tool latency | < 2 วินาที per call |
| WebSocket uptime | > 99.5% |

### Error Handling
- MCP server error → agent แจ้ง user ชัดเจน ("ไม่สามารถเชื่อมต่อ Jira ได้ กรุณาตรวจสอบ token")
- Claude API timeout (>30s) → retry 1 ครั้ง → fallback message พร้อม partial result
- DB write error → log + return result ให้ user ก่อน retry write ใน background

---

## 15. Environment Configuration

```bash
# .env.example

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Jira
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=qa@extosoft.com
JIRA_API_TOKEN=...

# GitHub
GITHUB_TOKEN=ghp_...
GITHUB_ORG=extosoft

# Figma
FIGMA_ACCESS_TOKEN=...

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/qa_brain
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET_KEY=...
JWT_ALGORITHM=HS256

# App
ENVIRONMENT=development   # development | production
LOG_LEVEL=INFO
```
