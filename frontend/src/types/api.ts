export type GameStatus = "playing" | "solved" | "abandoned";
export type Answer = "yes" | "no" | "irrelevant";
export type Difficulty = "easy" | "medium" | "hard";

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

export interface QuestionRecord {
  question: string;
  answer: Answer;
  display_answer: string;
  created_at: string;
}

export interface SolutionAttempt {
  solution: string;
  solved: boolean;
  created_at: string;
}

export interface CreateGameResponse {
  game_id: string;
  surface_story: string;
  status: GameStatus;
}

export interface PublicGameResponse {
  game_id: string;
  topic: string;
  surface_story: string;
  status: GameStatus;
  questions: QuestionRecord[];
  solution_attempts: SolutionAttempt[];
  truth?: string | null;
}

export interface AskQuestionResponse {
  answer: Answer;
  display_answer: string;
}

export interface SubmitSolutionResponse {
  solved: boolean;
  message: string;
  status: GameStatus;
  truth?: string | null;
}

export interface AbandonGameResponse {
  status: GameStatus;
  truth: string;
}

export interface HistoryItem {
  game_id: string;
  title: string;
  topic: string;
  status: Exclude<GameStatus, "playing">;
  question_count: number;
  created_at: string;
  ended_at: string;
}

export interface HistoryListResponse {
  items: HistoryItem[];
}

export interface HistoryDetail {
  game_id: string;
  topic: string;
  title: string;
  surface_story: string;
  truth: string;
  key_facts: string[];
  forbidden_assumptions: string[];
  difficulty: Difficulty;
  questions: QuestionRecord[];
  solution_attempts: SolutionAttempt[];
  status: Exclude<GameStatus, "playing">;
  created_at: string;
  ended_at: string;
}
