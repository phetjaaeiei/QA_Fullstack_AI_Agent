import re
from typing import AsyncGenerator
from app.agents.manual_qa import ManualQAAgent
from app.agents.automation_qa import AutomationQAAgent

STORY_ID_PATTERN = re.compile(r"\b([A-Z]+-\d+)\b")
SPRINT_ID_PATTERN = re.compile(r"\bSPRINT[-\s]?(\d+)\b", re.IGNORECASE)
GH_RUN_URL_PATTERN = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/actions/runs/(\d+)")
URL_PATTERN = re.compile(r"https?://\S+")
CODE_BLOCK_PATTERN = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)


class QAOrchestrator:
    def __init__(self):
        self._manual_qa = ManualQAAgent()
        self._automation_qa = AutomationQAAgent()

    def _classify_intent(self, message: str) -> dict:
        msg = message.lower()
        story_ids = STORY_ID_PATTERN.findall(message)
        sprint_match = SPRINT_ID_PATTERN.search(message)
        sprint_id = f"SPRINT-{sprint_match.group(1)}" if sprint_match else None

        if any(w in msg for w in ["analyze", "ambigui", "missing", "risk"]):
            return {"action": "analyze_story", "story_ids": story_ids}
        if any(w in msg for w in ["map script", "script traceability"]):
            code_match = CODE_BLOCK_PATTERN.search(message)
            script_content = code_match.group(1).strip() if code_match else ""
            return {"action": "map_script_traceability", "story_ids": story_ids, "script_content": script_content}
        if any(w in msg for w in ["traceability", "trace", "link", "map"]):
            return {"action": "traceability", "story_ids": story_ids}
        if any(w in msg for w in ["release", "ready", "score", "readiness", "go/no-go"]):
            return {"action": "release_score", "sprint_id": sprint_id}
        if any(w in msg for w in ["gap", "missing test", "coverage gap"]):
            return {"action": "coverage_gap", "sprint_id": sprint_id}
        if any(w in msg for w in ["company standard", "house style", "apply framework", "company framework"]):
            code_match = CODE_BLOCK_PATTERN.search(message)
            script_content = code_match.group(1).strip() if code_match else ""
            return {"action": "apply_company_framework", "script_content": script_content}
        if any(w in msg for w in ["fix script", "auto fix", "แก้ script"]):
            code_match = CODE_BLOCK_PATTERN.search(message)
            script_content = code_match.group(1).strip() if code_match else ""
            error_message = CODE_BLOCK_PATTERN.sub("", message).strip()
            return {"action": "auto_fix_script", "script_content": script_content, "error_message": error_message}
        if any(w in msg for w in ["why fail", "why did this fail", "failure", "root cause", "ทำไม fail"]):
            run_match = GH_RUN_URL_PATTERN.search(message)
            if run_match:
                return {"action": "classify_failure", "repo": run_match.group(1), "run_id": run_match.group(2)}
            return {"action": "unknown"}
        if any(w in msg for w in ["locator", "self-heal", "element not found"]):
            url_match = URL_PATTERN.search(message)
            page_url = url_match.group(0) if url_match else ""
            broken_locator = URL_PATTERN.sub("", message).strip()
            return {"action": "suggest_self_healing", "broken_locator": broken_locator, "page_url": page_url}
        if any(w in msg for w in ["test data", "boundary data"]):
            return {"action": "generate_test_data", "requirements": message}
        if any(w in msg for w in ["generate script", "automation script", "playwright", "robot framework"]):
            framework = "robot" if "robot" in msg else "playwright"
            return {"action": "generate_script_from_spec", "story_ids": story_ids, "framework": framework}
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

        elif action == "generate_script_from_spec":
            story_ids = intent.get("story_ids", [])
            framework = intent.get("framework", "playwright")
            for story_id in story_ids:
                yield {"type": "agent_start", "agent": "automation_qa", "message": f"Generating {framework} script for {story_id}..."}
                script = await self._automation_qa.generate_script_from_spec(story_id, framework=framework)
                yield {"type": "agent_complete", "agent": "automation_qa", "message": f"Generated {framework} script for {story_id}"}
                yield {"type": "orchestrator_done", "data": {"script": script, "story_id": story_id}}

        elif action == "apply_company_framework":
            script_content = intent.get("script_content", "")
            yield {"type": "agent_start", "agent": "automation_qa", "message": "Applying company framework standards..."}
            formatted = await self._automation_qa.apply_company_framework(script_content)
            yield {"type": "agent_complete", "agent": "automation_qa", "message": "Script reformatted to house style"}
            yield {"type": "orchestrator_done", "data": {"formatted_script": formatted}}

        elif action == "map_script_traceability":
            story_ids = intent.get("story_ids", [])
            script_content = intent.get("script_content", "")
            for story_id in story_ids:
                yield {"type": "agent_start", "agent": "automation_qa", "message": f"Mapping script traceability for {story_id}..."}
                mapping = await self._automation_qa.map_script_traceability(story_id, script_content)
                yield {"type": "agent_complete", "agent": "automation_qa", "message": f"Traceability mapped for {story_id}"}
                yield {"type": "orchestrator_done", "data": {"traceability_mapping": mapping, "story_id": story_id}}

        elif action == "auto_fix_script":
            yield {"type": "agent_start", "agent": "automation_qa", "message": "Fixing script..."}
            fix = await self._automation_qa.auto_fix_script(intent.get("script_content", ""), intent.get("error_message", ""))
            yield {"type": "agent_complete", "agent": "automation_qa", "message": "Script fixed"}
            yield {"type": "orchestrator_done", "data": {"fix": fix}}

        elif action == "classify_failure":
            repo = intent.get("repo")
            run_id = intent.get("run_id")
            yield {"type": "agent_start", "agent": "automation_qa", "message": f"Classifying failure for {repo} run {run_id}..."}
            classification = await self._automation_qa.classify_failure(repo, run_id)
            yield {"type": "agent_complete", "agent": "automation_qa", "message": f"Failure classified: {classification.get('root_cause', 'unknown')}"}
            yield {"type": "orchestrator_done", "data": {"classification": classification}}

        elif action == "suggest_self_healing":
            broken_locator = intent.get("broken_locator", "")
            page_url = intent.get("page_url", "")
            yield {"type": "agent_start", "agent": "automation_qa", "message": "Suggesting self-healing locators..."}
            healing = await self._automation_qa.suggest_self_healing(broken_locator, page_url)
            yield {"type": "agent_complete", "agent": "automation_qa", "message": "Self-healing suggestions ready"}
            yield {"type": "orchestrator_done", "data": {"healing": healing}}

        elif action == "generate_test_data":
            requirements = intent.get("requirements", "")
            yield {"type": "agent_start", "agent": "automation_qa", "message": "Generating test data..."}
            test_data = await self._automation_qa.generate_test_data(requirements)
            yield {"type": "agent_complete", "agent": "automation_qa", "message": f"Generated {len(test_data)} test data set(s)"}
            yield {"type": "orchestrator_done", "data": {"test_data": test_data}}

        else:
            yield {
                "type": "orchestrator_done",
                "data": {"message": "ไม่เข้าใจ request กรุณาระบุ story ID (เช่น PROJ-123), sprint ID, หรือ GitHub Actions run URL"}
            }
