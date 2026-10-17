import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import Admin from "./views/Admin.jsx";
import { ThemeProvider } from "./context/ThemeContext.jsx";
import "./index.css";

// The admin page lives at a path that nothing in the app links to. It
// defaults to /admin; set VITE_ADMIN_PATH at build time to make it secret.
const ADMIN_PATH = (import.meta.env.VITE_ADMIN_PATH || "/admin").replace(/\/+$/, "");
const isAdmin = window.location.pathname.replace(/\/+$/, "") === ADMIN_PATH;

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider>
      {isAdmin ? <Admin /> : <App />}
    </ThemeProvider>
  </React.StrictMode>
);
