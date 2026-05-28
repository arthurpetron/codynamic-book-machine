import { AgentConsole } from "./AgentConsole";
import { MenuBar } from "./MenuBar";
import { Workspace } from "./Workspace";
import type { useBookStore } from "../../state/bookStore";

interface DesktopShellProps {
  store: ReturnType<typeof useBookStore>;
}

export function DesktopShell({ store }: DesktopShellProps) {
  return (
    <div id="root-shell" className="app-shell" data-chat-collapsed="false">
      <MenuBar store={store} />
      <Workspace store={store} />
      <AgentConsole store={store} />
    </div>
  );
}
