import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/global.css";

window.addEventListener("unhandledrejection", (event) => {
  const reason = String(event.reason?.message ?? event.reason ?? "");
  if (reason.includes("No Listener: tabs:outgoing.message.read")) {
    event.preventDefault();
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
