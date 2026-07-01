import re
from typing import AsyncGenerator
from app.agents.manual_qa import ManualQAAgent

STORY_ID_PATTERN = re.compile(r"\b([A-Z]+-\d+)\b")
SPRINT_ID_PATTERN = re.compile(r"\bSPRINT[-\s]?(\d+)\b", re.IGNORECASE)


class QAOrchestrator:
    def __init__(self):
        self._manual_qa = ManualQAAgent()

    def _classify_intent(self, message: str) -> dict:
        msg = message.lower()
        story_ids = STORY_ID_PATTERN.findall(message)
        sprint_match = SPRINT_ID_PATTERN.search(message)
        sprint_id = f"SPRINT-{sprint_match.group(1)}" if sprint_match else None

        if any(w in msg for w in ["analyze", "ambigui", "missing", "risk"]):
            return {"action": "analyze_story", "story_ids": story_ids}
        if any(w in msg for w in ["traceability", "trace", "link", "map"]):
            return {"action": "traceability", "story_ids": story_ids}
        if any(w in msg for w in ["release", "ready", "score", "readiness", "go/no-go"]):
            return {"action": "release_score", "sprint_id": sprint_id}
        if any(w in msg for w in ["gap", "missing test", "coverage gap"]):
            return {"action": "coverage_gap", "sprint_id": sprint_id}
        if story_ids:
            return {"action": "generate_test_cases", "story_ids": story_ids}
        return {"action": "unknown"}

    async def process(
        self, message: str, session_id: str, project_id: str
    ) -> AsyncGenerator[dict, None]:
        intent = self._classify_intent(message)
        action = intent["action"]

        if action == "generate_test_cases":
            story_ids = intent.get("story_ids", [])
            for story_id in story_ids:
                yield {"type": "agent_start", "agent": "manual_qa", "message": f"Generating test cases for {story_id}..."}
                test_cases = await self._manual_qa.generate_test_cases(story_id)
                yield {"type": "agent_complete", "agent": "manual_qa", "message": f"Generated {len(test_cases)} test cases for {story_id}"}
                yield {"type": "orchestrator_done", "data": {"test_cases": test_cases, "story_id": story_id}}

        elif action == "analyze_story":
            story_ids = intent.get("story_ids", [])
            for story_id in story_ids:
                yield {"type": "agent_start", "agent": "manual_qa", "message": f"Analyzing {story_id}..."}
                analysis = await self._manual_qa.analyze_story(story_id)
                yield {"type": "agent_complete", "agent": "manual_qa", "message": f"Analysis complete for {story_id}"}
                yield {"type": "orchestrator_done", "data": {"analysis": analysis, "story_id": story_id}}

        elif action == "traceability":
            story_ids = intent.get("story_ids", [])
            yield {"type": "agent_start", "agent": "manual_qa", "message": f"Building traceability map for {len(story_ids)} stories..."}
            traceability = await self._manual_qa.build_traceability_map(story_ids)
            yield {"type": "agent_complete", "agent": "manual_qa", "message": f"Traceability map built for {len(story_ids)} stories"}
            yield {"type": "orchestrator_done", "data": {"traceability": traceability}}

        elif action == "release_score":
            sprint_id = intent.get("sprint_id") or "SPRINT-1"
            yield {"type": "agent_start", "agent": "manual_qa", "message": f"Scoring release readiness for {sprint_id}..."}
            score = await self._manual_qa.score_release_readiness(sprint_id)
            yield {"type": "agent_complete", "agent": "manual_qa", "message": f"Release score calculated: {score.get('score', 0)}/100"}
            yield {"type": "orchestrator_done", "data": {"release_score": score}}

        elif action == "coverage_gap":
            sprint_id = intent.get("sprint_id") or "SPRINT-1"
            yield {"type": "agent_start", "agent": "manual_qa", "message": f"Detecting coverage gaps in {sprint_id}..."}
            gaps = await self._manual_qa.detect_coverage_gaps(sprint_id)
            yield {"type": "agent_complete", "agent": "manual_qa", "message": "Coverage gap analysis complete"}
            yield {"type": "orchestrator_done", "data": {"gaps": gaps}}

        else:
            yield {
                "type": "orchestrator_done",
                "data": {"message": "ไม่เข้าใจ request กรุณาระบุ story ID (เช่น PROJ-123) หรือ sprint ID"}
            }
