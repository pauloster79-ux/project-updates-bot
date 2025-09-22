import type { App } from "@slack/bolt";
import { projects, tasks, risks } from "../data/seed";
import { buildHomeView } from "../ui/views";
import type { ProjectTab } from "../ui/tabs";

function getStateFromView(view?: any): { selectedProjectId?: string; activeTab?: ProjectTab } {
  try {
    return view?.private_metadata ? JSON.parse(view.private_metadata) : {};
  } catch {
    return {};
  }
}

function getProjectById(id?: string) {
  return projects.find(p => p.id === id);
}

function getTasks(projectId?: string) {
  return tasks.filter(t => t.projectId === projectId);
}

function getRisks(projectId?: string) {
  return risks.filter(r => r.projectId === projectId);
}

export function registerHomeHandlers(app: App) {
  // Open / refresh home
  app.event("app_home_opened", async ({ event, client }) => {
    const defaultProject = projects[0];
    const view = buildHomeView({
      projects,
      selectedProject: defaultProject,
      activeTab: "summary",
      tasks: getTasks(defaultProject.id),
      risks: getRisks(defaultProject.id),
    });
    await client.views.publish({ user_id: event.user, view });
  });

  // Project navigation
  app.action(/^nav_open_/, async ({ ack, body, client, action }) => {
    await ack();
    const projectId = (action as any).value;
    const selected = getProjectById(projectId);
    const view = buildHomeView({
      projects,
      selectedProject: selected,
      activeTab: "summary",
      tasks: getTasks(projectId),
      risks: getRisks(projectId),
    });
    await client.views.publish({ user_id: (body as any).user.id, view });
  });

  // Tabs switching
  app.action(/^tab_/, async ({ ack, body, client, action, view }) => {
    await ack();
    const value = (action as any).value as ProjectTab;
    const prev = getStateFromView(view);
    const projectId = prev.selectedProjectId ?? projects[0].id;
    const selected = getProjectById(projectId) ?? projects[0];

    const nextView = buildHomeView({
      projects,
      selectedProject: selected,
      activeTab: value,
      tasks: getTasks(projectId),
      risks: getRisks(projectId),
    });
    await client.views.publish({ user_id: (body as any).user.id, view: nextView });
  });
}
