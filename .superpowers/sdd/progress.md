# Automation QA — Track A Demo — Progress Ledger

Branch: main (user declined worktree isolation)
Plan: docs/superpowers/plans/2026-07-03-automation-qa-demo-track-a.md

## Tasks

- [x] Task 1: generate_script_from_spec — OpenAPI spec URL support (commits 231de79..538a9d8, review clean; minor notes only: no error handling around parse_spec network failures, matches pre-existing Jira-path style; verbatim JSON-block duplication between spec_url/story branches is brief-mandated)
- [x] Task 2: Orchestrator routing for API-spec messages (commits 538a9d8..0cf3efa, review clean; minor note: message with "openapi" keyword but no URL and no story ID silently yields no event, matches pre-existing suggest_self_healing convention, not a regression)
- [x] Task 3: Add Playwright dependency (commits 0cf3efa..0b8e725, review clean; version substituted playwright==1.49.0 -> 1.61.0, controller-approved, local venv is Python 3.14.6 and 1.49.0's greenlet pin has no wheel for it — Dockerfile change unaffected, version-agnostic)
- [x] Task 4: _crawl_site helper (commits 0b8e725..54a79cc, review clean; minor plan-mandated: no exception handling around page.goto/eval_on_selector_all means browser.close() is skipped on the unhappy path (leaked browser process on a bad page) — brief's literal code, deferred to final whole-branch review triage, not fixed now)
- [x] Task 5: explore_and_generate method (commits 54a79cc..14f1ad5, review clean; reviewer statically traced mock-mode zero-crawl guarantee through __init__, not just test-passing)
- [x] Task 6: Orchestrator routing + persistence for explore_and_generate (commits 14f1ad5..fe59f18, review clean; test strategy revised mid-task — brief's WebSocket E2E test hit a pre-existing cross-loop asyncpg/httpx_ws incompatibility (existing test_chat_api.py test never actually exercised a DB write either), replaced with a same-loop direct call to _persist_automation_script that proves the identical persistence claim; chat.py and conftest.py untouched)
- [x] Task 7: automation-standards.md starter content (commits fe59f18..f5f1680, review clean; brief's guessed path was off by one directory level, implementer correctly traced _HOUSE_STYLE_PATH and used the real resolved path qa-brain/backend/docs/automation-standards.md, reviewer independently re-traced and confirmed)
- [x] Task 8: Frontend script source badge (commits f5f1680..cffc713, review clean; no automated frontend test suite exists, verified via npm run build + manual trace of all 3 story_id cases; live-browser check deferred to Task 9)

## All 8 tasks complete (Task 9 deferred, needs real staging URL from user).

Final whole-branch review (merge-base 231de79..cffc713, Opus): verified end-to-end
that "zero-change persistence/frontend" claim holds by reading the unmodified
chat.py and useAgentChat.ts directly; confirmed all protected files (chat.py,
conftest.py, security_qa.py, manual_qa.py, performance_qa.py, framework enum)
genuinely untouched; confirmed synthetic story-ID prefix convention consistent
across orchestrator and frontend; verified Task 6's WebSocket-test-to-direct-call
pivot is sound. Verdict: "With fixes" — one Important finding (browser leak on
crawl error in _crawl_site) plus bundled Minor (silent/broken routing on
URL-less explore/api-spec messages).

Fix dispatched (commit f4f6ea3): wrapped _crawl_site's while loop in
try/finally guaranteeing browser.close(); both explore and api-spec orchestrator
branches now short-circuit to the existing "unknown" fallback when no URL is
found, instead of proceeding with an empty string. 83 passed, 0 failed (up from 80).

Re-review (Opus): both findings confirmed resolved, no new issues, happy paths
and crawl logic unchanged. **Ready to merge? Yes.**

Deferred to Track B / future work (recorded, not blocking):
- Task 1: no error handling around OpenAPIClient.parse_spec network failures (matches pre-existing Jira-path style)
- Task 6: WS handler's persistence-dispatch glue (chat.py:157-162) has no live WebSocket-level test for ANY action (old or new) — pre-existing gap, surfaced but not closed by this work
- Test robustness nit: persistence test's unfiltered select(AutomationScript) relies on conftest cleanup rather than an explicit story_id filter
- Demo runbook (Task 9, not yet started) should note URLs must be space-delimited with no trailing punctuation (URL_PATTERN quirk, pre-existing, shared with suggest_self_healing)

## Track A (Tasks 1-8) complete and ready to merge. Task 9 (staging URL + rehearsal) awaits real environment info from user.
- [ ] Task 9: DEFERRED — needs real staging URL + OpenAPI spec URL from user, not executable by subagent

## Baseline

Backend test suite: 70 passed (after dropping a stale `performance_findings`
table left over from testing the unrelated worktree-performance-qa-agent
branch against the same shared local Postgres test DB — confirmed via user
before dropping).
