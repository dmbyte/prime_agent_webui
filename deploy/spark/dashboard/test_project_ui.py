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


if __name__ == "__main__":
    unittest.main()
