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


if __name__ == "__main__":
    unittest.main()
