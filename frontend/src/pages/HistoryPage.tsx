import { useEffect, useState } from "react";
import { ApiError, getHistoryDetail, listHistory } from "../api/client";
import { QuestionLog } from "../components/QuestionLog";
import type { HistoryDetail, HistoryItem } from "../types/api";

export function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadHistory() {
    setLoading(true);
    setError(null);
    try {
      const response = await listHistory();
      setItems(response.items);
      if (!selectedId && response.items.length > 0) {
        setSelectedId(response.items[0].game_id);
      }
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    getHistoryDetail(selectedId)
      .then(setDetail)
      .catch((err) => setError(messageFromError(err)))
      .finally(() => setLoading(false));
  }, [selectedId]);

  return (
    <div className="history-layout">
      <aside className="panel stack history-list">
        <div className="panel-heading">
          <h2>歷史紀錄</h2>
          <button type="button" onClick={() => void loadHistory()} disabled={loading}>
            更新
          </button>
        </div>
        {items.length === 0 ? <p className="muted">目前沒有已結束遊戲。</p> : null}
        <div className="history-items">
          {items.map((item) => (
            <button
              className={item.game_id === selectedId ? "history-item active" : "history-item"}
              key={item.game_id}
              type="button"
              onClick={() => setSelectedId(item.game_id)}
            >
              <span>{item.title}</span>
              <small>{statusLabel(item.status)} · {item.question_count} 問</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="main-column">
        {error ? <div className="notice error">{error}</div> : null}
        {loading && !detail ? <div className="panel"><p className="muted">讀取中。</p></div> : null}
        {detail ? (
          <article className="panel stack history-detail">
            <div>
              <h2>{detail.title}</h2>
              <p className="muted compact">{statusLabel(detail.status)} · {formatDate(detail.ended_at)}</p>
            </div>
            <section>
              <h3>謎面</h3>
              <p className="surface-story">{detail.surface_story}</p>
            </section>
            <section>
              <h3>問答紀錄</h3>
              <QuestionLog questions={detail.questions} />
            </section>
            <section>
              <h3>解答嘗試</h3>
              {detail.solution_attempts.length === 0 ? (
                <p className="muted">沒有提交解答。</p>
              ) : (
                <ol className="attempt-list">
                  {detail.solution_attempts.map((attempt, index) => (
                    <li key={`${attempt.created_at}-${index}`}>
                      <span>解答嘗試 {index + 1}：{attempt.solved ? "成功解開" : "尚未解開"}</span>
                      <p>{attempt.solution}</p>
                    </li>
                  ))}
                </ol>
              )}
            </section>
            <section className="truth-box">
              <h3>完整真相</h3>
              <p>{detail.truth}</p>
            </section>
          </article>
        ) : null}
      </section>
    </div>
  );
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "讀取失敗";
}

function statusLabel(status: string) {
  return status === "solved" ? "已解開" : "已放棄";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-TW", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}
