export type ProjectTab = "summary" | "tasks" | "risks";

export function buildProjectTabs(active: ProjectTab) {
  const tabs = [
    { text: "Summary", value: "summary" },
    { text: "Tasks", value: "tasks" },
    { text: "Risks", value: "risks" },
  ];
  return {
    type: "actions",
    block_id: "tabs",
    elements: tabs.map(t => ({
      type: "button",
      action_id: `tab_${t.value}`,
      text: { type: "plain_text", text: t.text },
      style: active === t.value ? "primary" : undefined,
      value: t.value
    }))
  } as const;
}
