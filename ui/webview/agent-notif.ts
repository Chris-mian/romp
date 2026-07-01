// Parsing a harness <task-notification> — a backgrounded Agent/Task coming to rest — into the bits worth
// showing (the user 2026-06-30). It arrives folded into a user turn's `reminders` as raw inner XML:
//   <task-id>…</task-id><tool-use-id>…</tool-use-id><output-file>…</output-file>
//   <status>completed</status><summary>Agent "Ring A agent 3 rerun" came to rest</summary>
//   <note>…boilerplate…</note><result>…the agent's final message…</result>
// Dumping that under "system reminder" buried the one thing that matters — WHAT the agent did. We keep the
// agent's name + status + its final result; the internal ids + boilerplate note are dropped. render.ts owns
// the DOM (renderAgentNotif); this owns the (pure, testable) parse.

export interface AgentNotif { label: string; status: string; result: string; summary: string; }

export function parseAgentNotif(text: string): AgentNotif | null {
  // Only a task-notification (has a <task-id> or an Agent "…" summary); a plain <system-reminder> → null.
  if (!/<task-id>|<summary>\s*Agent\b/.test(text)) return null;
  const grab = (t: string) => (text.match(new RegExp("<" + t + ">([\\s\\S]*?)</" + t + ">")) || [])[1] || "";
  const summary = grab("summary").trim();
  const status = grab("status").trim();
  const result = grab("result").trim();
  if (!summary && !result) return null;
  const m = summary.match(/Agent\s+"([^"]+)"/);           // summary reads: Agent "<label>" came to rest
  const label = m ? m[1] : (summary.replace(/\s+came to rest.*$/i, "").trim() || "Agent");
  return { label, status, result, summary };
}
