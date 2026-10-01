#!/usr/bin/env python3
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ProjectUiTests(unittest.TestCase):
    def test_admin_explains_qwen_code_policy_precedence(self):
        app = (ROOT / "app-v2.js").read_text()
        self.assertIn("Qwen handles code generation in every profile", app)
        self.assertIn("This takes precedence over the rules below", app)

    def test_admin_uses_main_workspace_and_checks_openshell_sandboxes(self):
        index = (ROOT / "index.html").read_text()
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "enhancements.css").read_text()
        self.assertIn('id="adminWorkspace"', index)
        self.assertIn('id="adminContent"', index)
        self.assertIn('document.querySelector(".chat").hidden=adminView', app)
        self.assertIn('function renderSandboxAdmin', app)
        self.assertIn('/api/admin/sandboxes', app)
        self.assertIn('.admin-workspace{', css)

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

    def test_task_output_can_be_inspected_live_from_trace(self):
        index = (ROOT / "index.html").read_text()
        app = (ROOT / "app-v2.js").read_text()
        self.assertIn('id="taskLogDialog"', index)
        self.assertIn("row.oncontextmenu=event=>", app)
        self.assertIn("Complete output…", app)
        self.assertIn("/api/tasks/log/chunk", app)
        self.assertIn("task.silentSeconds", app)
        self.assertIn("decorateTaskTrace($(\"messages\"),liveTask||taskTrace)", app)

    def test_long_task_history_and_saved_work_log_remain_in_chat(self):
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "enhancements.css").read_text()
        self.assertIn("if(failed&&displayedSessionId===session)", app)
        self.assertIn("Showing saved conversation history while Prime works", app)
        self.assertIn("displayedMessageKeys.every", app)
        self.assertIn("function syncWorkLogCards", app)
        self.assertIn("primeLastConversation:", app)
        self.assertIn("primeActiveTask:", app)
        self.assertIn("Still working ·", app)
        self.assertIn("Connection interrupted ·", app)
        self.assertIn("setInterval(updateTaskHeartbeats,1000)", app)
        self.assertIn(".work-log-card", css)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser timeline test")
    def test_saved_work_logs_follow_their_conversation_turn(self):
        app = (ROOT / "app-v2.js").read_text()
        functions = "\n".join(line for line in app.splitlines() if line.startswith(("function timelineMillis(", "function workLogInsertionIndex(")))
        self.assertIn("function placeWorkLogCard", app)
        self.assertIn("box.insertBefore(card,messages[index]", app)
        self.assertIn("placeWorkLogCard(box,card,task)", app)
        script = functions + """
const assert = require('node:assert/strict');
const messages = [
  {dataset:{messageRole:'user',messageAt:'2026-09-30T10:00:01Z'}},
  {dataset:{messageRole:'assistant',messageAt:'2026-09-30T10:02:00Z'}},
  {dataset:{messageRole:'user',messageAt:'2026-09-30T11:00:01Z'}},
  {dataset:{messageRole:'assistant',messageAt:'2026-09-30T11:03:00Z'}}
];
assert.equal(workLogInsertionIndex(messages,{createdAt:'2026-09-30T10:00:00Z'}),1);
assert.equal(workLogInsertionIndex(messages,{createdAt:'2026-09-30T11:00:00Z'}),3);
assert.equal(workLogInsertionIndex(messages,{createdAt:'2026-09-30T09:00:00Z'}),0);
assert.equal(workLogInsertionIndex(messages,{createdAt:'2026-09-30T12:00:00Z'}),4);
assert.equal(workLogInsertionIndex(messages,{createdAt:1790762400}),1);
"""
        subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)

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

    def test_memory_graph_shows_live_used_and_free_amounts(self):
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "enhancements.css").read_text()
        self.assertIn('data?.memoryUsedBytes', app)
        self.assertIn('data?.memoryTotalBytes', app)
        self.assertIn('class="ram-used"', app)
        self.assertIn('class="ram-free"', app)
        self.assertIn('Free means MemAvailable', app)
        self.assertIn('card.querySelector(".ram-used").textContent=compactRamLabel(amounts.used)', app)
        self.assertIn('card.querySelector(".ram-free").textContent=compactRamLabel(amounts.free)', app)
        self.assertIn('card.title="G means GiB.', app)
        self.assertIn('.telemetry-card.memory-card .metric-ram-values', css)
        self.assertIn('.telemetry-card.memory-card:hover .metric-ram-values', css)
        self.assertIn('.telemetry-card.memory-card:focus-visible .metric-ram-values', css)

    def test_skills_have_user_request_admin_review_and_project_selection(self):
        index = (ROOT / "index.html").read_text()
        app = (ROOT / "app-v2.js").read_text()
        css = (ROOT / "skill-governance.css").read_text()
        installer = (ROOT / "install-static.sh").read_text()
        self.assertIn('id="skillRequestDialog"', index)
        self.assertIn("function submitSkillRequest", app)
        self.assertIn("function renderSkillAdmin", app)
        self.assertIn("/api/admin/skills/source", app)
        self.assertIn("function renderProjectSkills", app)
        self.assertIn('skillIds:', app)
        self.assertIn(".skill-admin-row", css)
        self.assertIn("skill-governance.css", installer)

    def test_project_skill_descriptions_wrap_without_clipping(self):
        css = (ROOT / "skill-governance.css").read_text()
        self.assertIn("#projectSkillList span{", css)
        self.assertIn("white-space:normal", css)
        self.assertIn("overflow-wrap:anywhere", css)
        self.assertIn("#projectSkillList input{flex:0 0 auto}", css)


if __name__ == "__main__":
    unittest.main()
