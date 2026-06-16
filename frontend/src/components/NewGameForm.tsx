import { FormEvent, useState } from "react";
import type { GameStatus } from "../types/api";

interface Props {
  currentStatus: GameStatus | null;
  disabled: boolean;
  onSubmit: (topic: string) => Promise<void>;
}

export function NewGameForm({ currentStatus, disabled, onSubmit }: Props) {
  const [topic, setTopic] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = topic.trim();
    if (!normalized || disabled) {
      return;
    }
    if (currentStatus === "playing") {
      const confirmed = window.confirm("目前遊戲尚未結束，是否開始新遊戲？");
      if (!confirmed) {
        return;
      }
    }
    await onSubmit(normalized);
  }

  return (
    <form className="panel stack" onSubmit={handleSubmit}>
      <div>
        <h2>新遊戲</h2>
        <p className="muted compact">輸入主題後由 AI 產生謎面與隱藏真相。</p>
      </div>
      <textarea
        value={topic}
        onChange={(event) => setTopic(event.target.value)}
        placeholder="例如：雨夜、便利商店、一張沒有人認領的發票"
        rows={6}
      />
      <button className="primary" type="submit" disabled={disabled || !topic.trim()}>
        {disabled ? "建立中" : "建立遊戲"}
      </button>
    </form>
  );
}
