export function buildHeader({ icon, title, subtitle }: { icon?: string; title: string; subtitle?: string; }) {
  return {
    type: "section",
    block_id: "hdr",
    text: { type: "mrkdwn", text: `*${icon ?? "📘"} ${title}*\n_${subtitle ?? ""}_`.trim() }
  } as const;
}
