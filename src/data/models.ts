export type Project = {
  id: string;
  name: string;
  description?: string;
};

export type TaskStatus = "To Do" | "In Progress" | "Blocked" | "Done";
export type TaskPriority = "Low" | "Medium" | "High" | "Critical";

export type Task = {
  id: string;
  projectId: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: TaskPriority;
  owner: string;        // Slack user ID
  dueDate?: string;     // ISO date
  lastUpdated: string;  // ISO date
  linkedRiskIds?: string[];
};

export type RiskLikelihood = "Low" | "Medium" | "High";
export type RiskImpact = "Low" | "Medium" | "High" | "Critical";
export type RiskStatus = "Open" | "Mitigated" | "Closed";

export type Risk = {
  id: string;
  projectId: string;
  title: string;
  description: string;
  likelihood: RiskLikelihood;
  impact: RiskImpact;
  owner: string;        // Slack user ID
  mitigationPlan?: string;
  status: RiskStatus;
  relatedTaskIds?: string[];
  lastUpdated: string;  // ISO date
};
