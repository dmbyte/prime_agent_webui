#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ProjectUiTests(unittest.TestCase):
    def test_existing_chats_expose_visible_project_actions(self):
        index = (ROOT / "index.html").read_text()
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "enhancements.css").read_text()

        self.assertIn('id="projectConversation"', index)
        self.assertIn('data-action="promote"', index)
        self.assertIn('className="conversation-actions"', app)
        self.assertIn('actions.textContent="..."', app)
        self.assertIn("openMenu(event,s)", app)
        self.assertIn('$("projectConversation").onclick', app)
        self.assertIn("setConversationActions", app)
        self.assertIn("Move project…", app)
        self.assertIn("Add to project…", app)
        self.assertIn("border:1px solid var(--line)", css)

    def test_failed_task_keeps_submitted_prompt_visible(self):
        app = (ROOT / "app-v2.js").read_text()
        self.assertIn("task.submittedMessage", app)
        self.assertIn("Task failed before it could be saved", app)
        self.assertIn("pendingMessages=failedPrompt?[failedPrompt]:[]", app)

    def test_task_progress_renders_in_collapsible_conversation_trace(self):
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "enhancements.css").read_text()

        self.assertIn("taskTrace=null", app)
        self.assertIn("function appendTaskTrace", app)
        self.assertIn("prime-nemotron", app)
        self.assertIn("prime-codex", app)
        self.assertIn("prime-qwen", app)
        self.assertIn('event.kind==="reasoning"?"reasoning in progress"', app)
        self.assertIn("appendTaskTrace(box,task,true)", app)
        self.assertIn("if(taskTrace&&!liveTask)appendTaskTrace(box,taskTrace,false)", app)
        self.assertIn("taskTrace=task", app)
        self.assertNotIn('task.progress||"Working…"', app)
        self.assertNotIn('"Working…"', app)
        self.assertIn(".task-trace-message", css)
        self.assertIn(".trace-event", css)
        self.assertIn(".collapsed-trace", css)

    def test_security_prompts_can_persist_for_chat_or_project(self):
        app = (ROOT / "app-v2.js").read_text()
        self.assertIn('"confirmationMode","chat"', app)
        self.assertIn('"projectConfirmationMode","project"', app)
        self.assertIn('confirmationMode==="always"', app)
        self.assertIn("matchesSavedSecurityPolicy", app)

    def test_top_statistics_have_live_hover_sparklines(self):
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "enhancements.css").read_text()
        self.assertIn("telemetryHistory", app)
        self.assertIn("telemetryPath", app)
        self.assertIn('class="metric-graph"', app)
        self.assertIn("metric-watermark", app)
        self.assertIn("last ${history.length} seconds", app)
        self.assertIn("),1000);setInterval(()=>updateTasks", app)
        self.assertIn(".telemetry-card:hover", css)
        self.assertIn("transform:scale(1.9)", css)

    def test_skills_have_user_request_admin_review_and_project_selection(self):
        index = (ROOT / "index.html").read_text()
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "skill-governance.css").read_text()
        installer = (ROOT / "install-static.sh").read_text()
        self.assertIn('id="skillRequestDialog"', index)
        self.assertIn("function submitSkillRequest", app)
        self.assertIn("function renderSkillAdmin", app)
        self.assertIn("function renderProjectSkills", app)
        self.assertIn('skillIds:', app)
        self.assertIn(".skill-admin-row", css)
        self.assertIn("skill-governance.css", installer)


if __name__ == "__main__":
    unittest.main()
