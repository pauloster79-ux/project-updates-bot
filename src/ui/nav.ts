import type { Project } from "../data/models";

export function buildProjectNav(projects: Project[], selectedId?: string) {
  const blocks: any[] = [
    { type: "context", elements: [{ type: "mrkdwn", text: "*Projects*" }] },
  ];
  projects.forEach(p => {
    blocks.push({
      type: "section",
      block_id: `nav_${p.id}`,
      text: { type: "mrkdwn", text: `${selectedId === p.id ? "•" : "◦"} *${p.name}*` },
      accessory: {
        type: "button",
        action_id: `nav_open_${p.id}`,
        text: { type: "plain_text", text: selectedId === p.id ? "Open" : "View" },
        value: p.id
      }
    });
  });
  blocks.push({ type: "divider" });
  return blocks;
}
