import { FormEvent, useState } from "react";

interface Props {
  disabled: boolean;
  onSubmit: (solution: string) => Promise<void>;
}

export function SolutionForm({ disabled, onSubmit }: Props) {
  const [solution, setSolution] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = solution.trim();
    if (!normalized || disabled) {
      return;
    }
    await onSubmit(normalized);
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <textarea
        value={solution}
        onChange={(event) => setSolution(event.target.value)}
        placeholder="輸入你的完整解答"
        rows={5}
      />
      <button className="primary" type="submit" disabled={disabled || !solution.trim()}>
        {disabled ? "判定中" : "提交解答"}
      </button>
    </form>
  );
}
