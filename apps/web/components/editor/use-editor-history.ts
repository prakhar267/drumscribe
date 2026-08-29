"use client";

import { useCallback, useState } from "react";
import type { DrumEvent } from "@/lib/domain";

interface HistoryState {
  past: DrumEvent[][];
  present: DrumEvent[];
  future: DrumEvent[][];
}

export function useEditorHistory(initial: DrumEvent[]) {
  const [history, setHistory] = useState<HistoryState>({ past: [], present: initial, future: [] });

  const apply = useCallback((next: DrumEvent[] | ((events: DrumEvent[]) => DrumEvent[])) => {
    setHistory((state) => {
      const value = typeof next === "function" ? next(state.present) : next;
      if (value === state.present) return state;
      return { past: [...state.past.slice(-99), state.present], present: value, future: [] };
    });
  }, []);

  const replace = useCallback((events: DrumEvent[]) => setHistory({ past: [], present: events, future: [] }), []);
  const undo = useCallback(() => setHistory((state) => {
    const previous = state.past.at(-1);
    if (!previous) return state;
    return { past: state.past.slice(0, -1), present: previous, future: [state.present, ...state.future] };
  }), []);
  const redo = useCallback(() => setHistory((state) => {
    const next = state.future[0];
    if (!next) return state;
    return { past: [...state.past, state.present], present: next, future: state.future.slice(1) };
  }), []);

  return {
    events: history.present,
    apply,
    replace,
    undo,
    redo,
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
  };
}
