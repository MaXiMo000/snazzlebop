import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./lib/theme"; // sets <html data-theme> before the first paint of the app
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
