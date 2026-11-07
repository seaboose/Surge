import React from "react";
import { createRoot } from "react-dom/client";
import App from "./case-workspace/App.jsx";
import "./luminous.css";
import "./reviewer-flow.css";
import "./landing-flow.css";
import "./canopy.css";
import "./workspace.css";

createRoot(document.getElementById("root")).render(<App />);
