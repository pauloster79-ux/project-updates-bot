import type { Project, Task, Risk } from "./models";

export const projects: Project[] = [
  { id: "p1", name: "AI Project Hub", description: "Slack-native PM hub with Notion-like UI." },
  { id: "p2", name: "Website Refresh", description: "New marketing site & docs." }
];

export const tasks: Task[] = [
  {
    id: "t1", projectId: "p1", title: "Home view scaffold",
    status: "In Progress", priority: "High", owner: "U12345",
    description: "Build header, nav, tabs, and summary.",
    dueDate: "2025-10-15", lastUpdated: "2025-10-10"
  },
  {
    id: "t2", projectId: "p1", title: "Task card component",
    status: "To Do", priority: "Medium", owner: "U12345",
    description: "Reusable builder for task rows/cards.",
    lastUpdated: "2025-10-10"
  },
  {
    id: "t3", projectId: "p2", title: "Page inventory",
    status: "Blocked", priority: "High", owner: "U67890",
    description: "List current pages and target IA.", dueDate: "2025-10-20", lastUpdated: "2025-10-09"
  }
];

export const risks: Risk[] = [
  {
    id: "r1", projectId: "p1", title: "Slack rate limits",
    description: "Rapid view updates might hit rate limits.",
    likelihood: "Medium", impact: "High", owner: "U12345",
    mitigationPlan: "Batch updates; debounce actions.",
    status: "Open", lastUpdated: "2025-10-10"
  },
  {
    id: "r2", projectId: "p2", title: "Asset delays",
    description: "Design assets may arrive late.",
    likelihood: "High", impact: "Medium", owner: "U67890",
    status: "Open", lastUpdated: "2025-10-08"
  }
];
