import type { QuestionRecord } from "../types/api";

interface Props {
  questions: QuestionRecord[];
}

export function QuestionLog({ questions }: Props) {
  if (questions.length === 0) {
    return <p className="muted">尚未提問。</p>;
  }

  return (
    <ol className="conversation">
      {questions.map((record, index) => (
        <li key={`${record.created_at}-${index}`}>
          <div className="bubble player">
            <span className="speaker">玩家</span>
            <p>{record.question}</p>
          </div>
          <div className="bubble host">
            <span className="speaker">主持人</span>
            <p>{record.display_answer}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
