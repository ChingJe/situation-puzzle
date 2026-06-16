import { NewGameForm } from "../components/NewGameForm";
import { QuestionForm } from "../components/QuestionForm";
import { QuestionLog } from "../components/QuestionLog";
import { SolutionForm } from "../components/SolutionForm";
import { useGameState } from "../state/useGameState";

export function CurrentGamePage() {
  const game = useGameState();
  const current = game.currentGame;
  const isPlaying = current?.status === "playing";

  return (
    <div className="workspace">
      <aside className="sidebar">
        <NewGameForm
          currentStatus={current?.status ?? null}
          disabled={game.pendingAction === "create"}
          onSubmit={game.startGame}
        />
        {game.error ? (
          <div className="notice error">
            <span>{game.error}</span>
            <button type="button" onClick={game.clearError}>關閉</button>
          </div>
        ) : null}
      </aside>

      <section className="main-column">
        {!game.restoreAttempted ? (
          <div className="panel">
            <p className="muted">恢復遊戲狀態中。</p>
          </div>
        ) : null}

        {!current && game.restoreAttempted ? (
          <div className="panel empty-state">
            <h2>尚未建立遊戲</h2>
            <p className="muted">建立新遊戲後，這裡會顯示謎面、問答紀錄與解答操作。</p>
          </div>
        ) : null}

        {current ? (
          <>
            <section className="panel stack">
              <div className="panel-heading">
                <div>
                  <h2>謎面</h2>
                  <p className="muted compact">狀態：{statusLabel(current.status)}</p>
                </div>
                {isPlaying ? (
                  <button
                    className="danger"
                    type="button"
                    disabled={game.pendingAction === "abandon"}
                    onClick={() => {
                      const confirmed = window.confirm("確定要放棄並查看答案？");
                      if (confirmed) {
                        void game.abandonCurrentGame();
                      }
                    }}
                  >
                    {game.pendingAction === "abandon" ? "處理中" : "放棄"}
                  </button>
                ) : null}
              </div>
              <p className="surface-story">{current.surface_story}</p>
              {!isPlaying && current.truth ? (
                <div className="truth-box">
                  <h3>真相</h3>
                  <p>{current.truth}</p>
                </div>
              ) : null}
            </section>

            <section className="panel stack">
              <h2>問答紀錄</h2>
              <QuestionLog questions={current.questions} />
              {isPlaying ? (
                <QuestionForm
                  disabled={game.pendingAction === "question"}
                  onSubmit={game.sendQuestion}
                />
              ) : null}
            </section>

            <section className="panel stack">
              <h2>提交解答</h2>
              {game.lastSolutionMessage ? (
                <p className={game.lastSolutionMessage === "尚未解開" ? "result pending" : "result solved"}>
                  {game.lastSolutionMessage}
                </p>
              ) : null}
              {isPlaying ? (
                <SolutionForm
                  disabled={game.pendingAction === "solution"}
                  onSubmit={game.sendSolution}
                />
              ) : (
                <p className="muted">本局已結束。</p>
              )}
            </section>
          </>
        ) : null}
      </section>
    </div>
  );
}

function statusLabel(status: string) {
  if (status === "solved") {
    return "已解開";
  }
  if (status === "abandoned") {
    return "已放棄";
  }
  return "進行中";
}
