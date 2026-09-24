import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";
import { bootNativeShell } from "./lib/native";
import { registerServiceWorker } from "./lib/pwa";

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

bootNativeShell();
// Installable + opens offline. Data is never cached — see public/sw.js.
registerServiceWorker();
