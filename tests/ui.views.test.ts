import { buildHomeView } from "../src/ui/views";
import { projects } from "../src/data/seed";

describe("Home view", () => {
  it("summary tab renders", () => {
    const v = buildHomeView({
      projects,
      selectedProject: projects[0],
      activeTab: "summary",
      tasks: [],
      risks: []
    });
    expect(v).toMatchSnapshot();
  });
});
