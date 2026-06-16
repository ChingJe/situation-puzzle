import type {
  AbandonGameResponse,
  ApiErrorBody,
  AskQuestionResponse,
  CreateGameResponse,
  HistoryDetail,
  HistoryListResponse,
  PublicGameResponse,
  SubmitSolutionResponse
} from "../types/api";

export class ApiError extends Error {
  code: string;
  status: number;
  requestId: string | null;

  constructor(code: string, message: string, status: number, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  const requestId = response.headers.get("X-Request-ID");
  const payload = (await response.json().catch(() => null)) as T | ApiErrorBody | null;
  if (!response.ok) {
    const errorPayload = payload as ApiErrorBody | null;
    console.warn("API request failed", {
      path,
      status: response.status,
      code: errorPayload?.error?.code,
      requestId
    });
    throw new ApiError(
      errorPayload?.error?.code ?? "UNKNOWN_ERROR",
      errorPayload?.error?.message ?? "伺服器發生錯誤",
      response.status,
      requestId
    );
  }
  console.debug("API request finished", {
    path,
    status: response.status,
    requestId
  });
  return payload as T;
}

export function createGame(topic: string): Promise<CreateGameResponse> {
  return request<CreateGameResponse>("/api/games", {
    method: "POST",
    body: JSON.stringify({ topic })
  });
}

export function getGame(gameId: string): Promise<PublicGameResponse> {
  return request<PublicGameResponse>(`/api/games/${gameId}`);
}

export function askQuestion(gameId: string, question: string): Promise<AskQuestionResponse> {
  return request<AskQuestionResponse>(`/api/games/${gameId}/questions`, {
    method: "POST",
    body: JSON.stringify({ question })
  });
}

export function submitSolution(
  gameId: string,
  solution: string
): Promise<SubmitSolutionResponse> {
  return request<SubmitSolutionResponse>(`/api/games/${gameId}/solution`, {
    method: "POST",
    body: JSON.stringify({ solution })
  });
}

export function abandonGame(gameId: string): Promise<AbandonGameResponse> {
  return request<AbandonGameResponse>(`/api/games/${gameId}/abandon`, {
    method: "POST"
  });
}

export function listHistory(): Promise<HistoryListResponse> {
  return request<HistoryListResponse>("/api/history");
}

export function getHistoryDetail(gameId: string): Promise<HistoryDetail> {
  return request<HistoryDetail>(`/api/history/${gameId}`);
}
