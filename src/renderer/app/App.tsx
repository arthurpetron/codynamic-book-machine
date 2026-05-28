import { DesktopShell } from "./layout/DesktopShell";
import { useBookStore } from "../state/bookStore";

export function App() {
  const store = useBookStore();
  return <DesktopShell store={store} />;
}
