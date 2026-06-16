import { useCallback, useEffect, useState } from "react";
import { ApiError, abandonGame, askQuestion, createGame, getGame, submitSolution } from "../api/client";
import type { PublicGameResponse } from "../types/api";

const CURRENT_GAME_KEY = "current_game_id";

type PendingAction = "restore" | "create" | "question" | "solution" | "abandon" | null;

export interface GameState {
  currentGame: PublicGameResponse | null;
  pendingAction: PendingAction;
  error: string | null;
  lastSolutionMessage: string | null;
  restoreAttempted: boolean;
  startGame: (topic: string) => Promise<void>;
  refreshGame: (gameId?: string) => Promise<void>;
  sendQuestion: (question: string) => Promise<boolean>;
  sendSolution: (solution: string) => Promise<void>;
  abandonCurrentGame: () => Promise<void>;
  clearError: () => void;
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "操作失敗";
}

export function useGameState(): GameState {
  const [currentGame, setCurrentGame] = useState<PublicGameResponse | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction>("restore");
  const [error, setError] = useState<string | null>(null);
  const [lastSolutionMessage, setLastSolutionMessage] = useState<string | null>(null);
  const [restoreAttempted, setRestoreAttempted] = useState(false);

  const refreshGame = useCallback(async (gameId?: string) => {
    const id = gameId ?? currentGame?.game_id;
    if (!id) {
      return;
    }
    const game = await getGame(id);
    setCurrentGame(game);
    localStorage.setItem(CURRENT_GAME_KEY, game.game_id);
  }, [currentGame?.game_id]);

  useEffect(() => {
    const storedGameId = localStorage.getItem(CURRENT_GAME_KEY);
    if (!storedGameId) {
      setPendingAction(null);
      setRestoreAttempted(true);
      return;
    }

    getGame(storedGameId)
      .then((game) => {
        setCurrentGame(game);
      })
      .catch(() => {
        localStorage.removeItem(CURRENT_GAME_KEY);
        setCurrentGame(null);
      })
      .finally(() => {
        setPendingAction(null);
        setRestoreAttempted(true);
      });
  }, []);

  const startGame = useCallback(async (topic: string) => {
    setPendingAction("create");
    setError(null);
    setLastSolutionMessage(null);
    try {
      const created = await createGame(topic);
      const game = await getGame(created.game_id);
      setCurrentGame(game);
      localStorage.setItem(CURRENT_GAME_KEY, game.game_id);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setPendingAction(null);
    }
  }, []);

  const sendQuestion = useCallback(async (question: string) => {
    if (!currentGame) {
      return false;
    }
    setPendingAction("question");
    setError(null);
    try {
      await askQuestion(currentGame.game_id, question);
      await refreshGame(currentGame.game_id);
      return true;
    } catch (err) {
      setError(messageFromError(err));
      return false;
    } finally {
      setPendingAction(null);
    }
  }, [currentGame, refreshGame]);

  const sendSolution = useCallback(async (solution: string) => {
    if (!currentGame) {
      return;
    }
    setPendingAction("solution");
    setError(null);
    try {
      const result = await submitSolution(currentGame.game_id, solution);
      setLastSolutionMessage(result.message);
      await refreshGame(currentGame.game_id);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setPendingAction(null);
    }
  }, [currentGame, refreshGame]);

  const abandonCurrentGame = useCallback(async () => {
    if (!currentGame) {
      return;
    }
    setPendingAction("abandon");
    setError(null);
    try {
      await abandonGame(currentGame.game_id);
      await refreshGame(currentGame.game_id);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setPendingAction(null);
    }
  }, [currentGame, refreshGame]);

  return {
    currentGame,
    pendingAction,
    error,
    lastSolutionMessage,
    restoreAttempted,
    startGame,
    refreshGame,
    sendQuestion,
    sendSolution,
    abandonCurrentGame,
    clearError: () => setError(null)
  };
}
