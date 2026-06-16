import { FormEvent, useState } from "react";

interface Props {
  disabled: boolean;
  onSubmit: (question: string) => Promise<boolean>;
}

export function QuestionForm({ disabled, onSubmit }: Props) {
  const [question, setQuestion] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = question.trim();
    if (!normalized || disabled) {
      return;
    }
    const accepted = await onSubmit(normalized);
    if (accepted) {
      setQuestion("");
    }
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <input
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder="輸入是非題，例如：男子還活著嗎？"
      />
      <button type="submit" disabled={disabled || !question.trim()}>
        {disabled ? "判定中" : "提問"}
      </button>
    </form>
  );
}
