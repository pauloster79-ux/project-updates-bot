import { buildHeader } from "./header";
import { buildProjectTabs, ProjectTab } from "./tabs";
import { buildProjectNav } from "./nav";
import { buildTaskList, buildRiskList } from "./cards";
import type { Project, Task, Risk } from "../data/models";

type HomeState = {
  selectedProjectId?: string;
  activeTab?: ProjectTab;
};

export function buildHomeView(params: {
  projects: Project[];
  selectedProject?: Project;
  activeTab?: ProjectTab;
  tasks?: Task[];
  risks?: Risk[];
}) {
  const { projects, selectedProject, activeTab = "summary", tasks = [], risks = [] } = params;

  const leftNav = buildProjectNav(projects, selectedProject?.id);
  const header = buildHeader({
    icon: "📘",
    title: selectedProject?.name ?? "AI Project Hub",
    subtitle: selectedProject ? "Your calm command center" : "Choose a project to begin"
  });

  const tabBar = selectedProject ? buildProjectTabs(activeTab) : null;

  const bodyBlocks: any[] = [];
  if (!selectedProject) {
    bodyBlocks.push({
      type: "section",
      block_id: "empty",
      text: { type: "mrkdwn", text: "*🧭 No project selected*\n_Select one from the left to view details._" },
      accessory: { type: "button", action_id: "new_project", text: { type: "plain_text", text: "New Project" } }
    });
  } else if (activeTab === "summary") {
    bodyBlocks.push(
      { type: "section", text: { type: "mrkdwn", text: `*Project Summary*\n${selectedProject.description ?? "_No description_"}` } },
      { type: "context", elements: [{ type: "mrkdwn", text: `*Tasks:* ${tasks.length}  •  *Risks:* ${risks.length}` }] }
    );
  } else if (activeTab === "tasks") {
    bodyBlocks.push(
      { type: "section", text: { type: "mrkdwn", text: "*Tasks*" }, accessory: { type: "button", action_id: "task_new", text: { type: "plain_text", text: "New Task" } } },
      { type: "divider" },
      ...(tasks.length ? buildTaskList(tasks) : [{
        type: "section",
        text: { type: "mrkdwn", text: "*No tasks yet*\n_Add your first task to get rolling._" },
        accessory: { type: "button", action_id: "task_new", text: { type: "plain_text", text: "Add Task" } }
      }])
    );
  } else if (activeTab === "risks") {
    bodyBlocks.push(
      { type: "section", text: { type: "mrkdwn", text: "*Risks*" }, accessory: { type: "button", action_id: "risk_new", text: { type: "plain_text", text: "New Risk" } } },
      { type: "divider" },
      ...(risks.length ? buildRiskList(risks) : [{
        type: "section",
        text: { type: "mrkdwn", text: "*No risks captured*\n_Add the first risk to start mitigation planning._" },
        accessory: { type: "button", action_id: "risk_new", text: { type: "plain_text", text: "Add Risk" } }
      }])
    );
  }

  const state: HomeState = {
    selectedProjectId: selectedProject?.id,
    activeTab
  };

  return {
    type: "home",
    private_metadata: JSON.stringify(state),
    blocks: [
      ...leftNav,
      header,
      { type: "divider" },
      ...(tabBar ? [tabBar, { type: "divider" }] : []),
      ...bodyBlocks
    ]
  };
}
