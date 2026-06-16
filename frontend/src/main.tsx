import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";
import { CurrentGamePage } from "./pages/CurrentGamePage";
import { HistoryPage } from "./pages/HistoryPage";

function App() {
  const [activeTab, setActiveTab] = React.useState<"current" | "history">("current");

  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>海龜湯</h1>
        <nav className="tabs" aria-label="主要分頁">
          <button
            className={activeTab === "current" ? "tab active" : "tab"}
            type="button"
            onClick={() => setActiveTab("current")}
          >
            目前遊戲
          </button>
          <button
            className={activeTab === "history" ? "tab active" : "tab"}
            type="button"
            onClick={() => setActiveTab("history")}
          >
            歷史紀錄
          </button>
        </nav>
      </header>
      {activeTab === "current" ? <CurrentGamePage /> : <HistoryPage />}
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
