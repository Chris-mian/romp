"""Background-task box (the user 2026-06-26): surface run_in_background tasks in the chat — a launch (a
tool_use with run_in_background:true) paired with its <task-notification> result. The kernel extracts them
(_bg_tasks) into structured rows {id,status,summary,command,output} for a dedicated box between the
transcript and the composer. A running task persists while in flight; a finished one self-clears once the
user sends another prompt. SYNTHETIC fixtures only (placeholder ids, no real data)."""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

TUSE = "11111111-aaaa-bbbb-cccc-222222222222"


def _launch(tid=TUSE, cmd="sleep 5 && false", desc="Restart server after test"):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": "Bash",
         "input": {"run_in_background": True, "command": cmd, "description": desc}}]}}


def _notif(tid=TUSE, status="failed", outfile="", summary='Background command "Restart server after test" failed with exit code 1'):
    body = ("<task-notification>\n<task-id>bkv4ddzb1</task-id>\n<tool-use-id>%s</tool-use-id>\n"
            "<output-file>%s</output-file>\n<status>%s</status>\n<summary>%s</summary>\n</task-notification>"
            % (tid, outfile, status, summary))
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": body}]}}


def _prompt(text="next thing please"):
    return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}}


def _write(recs):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    return path


class BgTasks(unittest.TestCase):
    def test_a_finished_background_task_is_parsed_into_a_row(self):
        path = _write([_launch(), _notif(status="failed")])
        try:
            res = km._bg_tasks(path)
        finally:
            os.unlink(path)
        self.assertEqual(res["count"], 1, "the header count")
        t = res["tasks"][0]
        self.assertEqual(t["status"], "failed")
        self.assertIn("exit code 1", t["summary"])
        self.assertEqual(t["command"], "sleep 5 && false", "the launch command is the expand-to-details body")

    def test_an_unmatched_launch_is_running(self):
        path = _write([_launch()])
        try:
            res = km._bg_tasks(path)
        finally:
            os.unlink(path)
        self.assertEqual(res["tasks"][0]["status"], "running")
        self.assertEqual(res["tasks"][0]["summary"], "Restart server after test", "running shows the launch description")

    def test_a_finished_task_self_clears_after_a_later_genuine_prompt(self):
        # completed, THEN the user sends another message → the user moved on → drop it from the box
        path = _write([_launch(), _notif(status="completed"), _prompt()])
        try:
            res = km._bg_tasks(path)
        finally:
            os.unlink(path)
        self.assertEqual(res["count"], 0, "a finished task before the last prompt is cleared")
        self.assertEqual(res["tasks"], [])

    def test_a_running_task_persists_across_a_later_prompt(self):
        # launched, no result yet, then a new prompt → still in flight → keep showing it
        path = _write([_launch(), _prompt()])
        try:
            res = km._bg_tasks(path)
        finally:
            os.unlink(path)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["tasks"][0]["status"], "running")

    def test_count_reflects_all_tasks_even_when_the_list_is_capped(self):
        # the header count is the TRUE total; the list itself is capped at 16
        recs = []
        for i in range(20):
            recs.append(_launch(tid="t%02d" % i, desc="job %d" % i))
        path = _write(recs)
        try:
            res = km._bg_tasks(path)
        finally:
            os.unlink(path)
        self.assertEqual(res["count"], 20, "count reports every surfaced task")
        self.assertEqual(len(res["tasks"]), 16, "the list is capped")

    def test_output_file_tail_is_read_for_the_details(self):
        out = tempfile.NamedTemporaryFile(mode="w", suffix=".output", delete=False)
        out.write("line one\nline two\nboom: exit 1\n")
        out.close()
        path = _write([_launch(), _notif(status="failed", outfile=out.name)])
        try:
            res = km._bg_tasks(path)
        finally:
            os.unlink(path)
            os.unlink(out.name)
        self.assertIn("boom: exit 1", res["tasks"][0]["output"], "the output file's tail is the details body")

    def test_parse_task_notification_keys_on_exact_tags(self):
        note = km._parse_task_notification("<task-notification><status>completed</status><summary>done</summary></task-notification>")
        self.assertEqual(note["status"], "completed")
        self.assertEqual(note["summary"], "done")
        self.assertIsNone(km._parse_task_notification("just some text"), "non-notification text → None")

    def test_chat_body_hosts_the_box_between_the_transcript_and_the_composer(self):
        body = km._chat_body()
        self.assertIn('id="bg-tasks"', body)
        self.assertLess(body.index('id="content"'), body.index('id="bg-tasks"'), "after the transcript")
        self.assertLess(body.index('id="bg-tasks"'), body.index('id="composer"'), "before the composer")


if __name__ == "__main__":
    unittest.main()
