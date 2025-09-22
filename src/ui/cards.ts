import type { Task, Risk } from "../data/models";

export function buildTaskCard(t: Task) {
  return [
    {
      type: "section",
      block_id: `task_${t.id}`,
      text: { type: "mrkdwn", text: `*🗂️ ${t.title}*  _(${t.status} • ${t.priority})_\n${t.description ?? ""}` },
      accessory: {
        type: "overflow",
        action_id: `task_menu_${t.id}`,
        options: [
          { text: { type: "plain_text", text: "Open" }, value: `open_${t.id}` },
          { text: { type: "plain_text", text: "Edit" }, value: `edit_${t.id}` },
          { text: { type: "plain_text", text: "Change status" }, value: `status_${t.id}` },
          { text: { type: "plain_text", text: "Archive" }, value: `archive_${t.id}` },
        ]
      }
    },
    {
      type: "context",
      elements: [
        { type: "mrkdwn", text: `*Owner:* <@${t.owner}>  •  *Due:* ${t.dueDate ?? "—"}  •  *Updated:* ${t.lastUpdated}` }
      ]
    },
    { type: "divider" }
  ];
}

export function buildRiskCard(r: Risk) {
  return [
    {
      type: "section",
      block_id: `risk_${r.id}`,
      text: { type: "mrkdwn", text: `*⚠️ ${r.title}*  _(${r.likelihood} × ${r.impact})_\n${r.description}` },
      accessory: {
        type: "overflow",
        action_id: `risk_menu_${r.id}`,
        options: [
          { text: { type: "plain_text", text: "Open" }, value: `open_${r.id}` },
          { text: { type: "plain_text", text: "Edit" }, value: `edit_${r.id}` },
          { text: { type: "plain_text", text: "Update status" }, value: `status_${r.id}` },
          { text: { type: "plain_text", text: "Close risk" }, value: `close_${r.id}` },
        ]
      }
    },
    {
      type: "context",
      elements: [
        { type: "mrkdwn", text: `*Owner:* <@${r.owner}>  •  *Status:* ${r.status}  •  *Updated:* ${r.lastUpdated}` }
      ]
    },
    { type: "divider" }
  ];
}

export const buildTaskList = (items: Task[]) => items.flatMap(buildTaskCard);
export const buildRiskList = (items: Risk[]) => items.flatMap(buildRiskCard);
