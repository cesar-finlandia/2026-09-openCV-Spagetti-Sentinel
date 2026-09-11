import "./node-polyfills";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./theme.css";
import "src/platform/ui/tokens.css";

createRoot(document.getElementById("root")!).render(<App />);
