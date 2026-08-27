import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";
import { registerServiceWorker } from "./lib/pwa";

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

// Installable + opens offline. Data is never cached — see public/sw.js.
registerServiceWorker();
