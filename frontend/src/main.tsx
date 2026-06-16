import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>海龜湯</h1>
        <nav className="tabs" aria-label="主要分頁">
          <button className="tab active" type="button">
            目前遊戲
          </button>
          <button className="tab" type="button">
            歷史紀錄
          </button>
        </nav>
      </header>
      <section className="workspace">
        <div className="panel">
          <h2>新遊戲</h2>
          <textarea placeholder="輸入任意主題，例如：雨夜、便利商店、一張沒有人認領的發票" />
          <button className="primary" type="button">建立遊戲</button>
        </div>
        <div className="panel">
          <h2>謎面</h2>
          <p className="muted">建立遊戲後，AI 會在這裡顯示謎面。</p>
        </div>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
