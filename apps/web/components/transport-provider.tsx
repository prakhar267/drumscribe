"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createSyntheticDemoAudioUrl } from "@/lib/audio";
import { DEMO_BPM, DEMO_DURATION } from "@/lib/demo-data";
import type { LoopRange, MixerState } from "@/lib/domain";

interface TransportContextValue {
  currentTime: number;
  duration: number;
  playing: boolean;
  countingIn: boolean;
  playbackRate: number;
  loop: LoopRange;
  mixer: MixerState;
  bpm: number;
  togglePlayback: () => void;
  playWithCountIn: (bars: 0 | 1 | 2) => void;
  seek: (time: number) => void;
  setPlaybackRate: (rate: number) => void;
  setLoop: (loop: LoopRange) => void;
  setMixer: (mixer: MixerState) => void;
  skipMeasure: (direction: -1 | 1) => void;
  loadAudioSources: (sources: { originalUrl: string; drumsUrl?: string; bpm?: number; preservePosition?: boolean }) => void;
}

const TransportContext = createContext<TransportContextValue | null>(null);

export function TransportProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stemRef = useRef<HTMLAudioElement | null>(null);
  const frameRef = useRef<number | null>(null);
  const sourceRef = useRef<string | null>(null);
  const lastBeatRef = useRef(-1);
  const countInTimersRef = useRef<number[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(DEMO_DURATION);
  const [bpm, setBpm] = useState(DEMO_BPM);
  const [playing, setPlaying] = useState(false);
  const [countingIn, setCountingIn] = useState(false);
  const [playbackRate, setRateState] = useState(1);
  const [loop, setLoopState] = useState<LoopRange>({ enabled: false, start: 0, end: 4 * 60 / DEMO_BPM });
  const [mixer, setMixerState] = useState<MixerState>({ original: 0.82, drums: 0.72, metronome: 0 });
  const mixerRef = useRef(mixer);
  const playbackRateRef = useRef(playbackRate);

  const clickMetronome = useCallback((downbeat: boolean, forcedLevel?: number) => {
    const level = forcedLevel ?? mixer.metronome;
    if (level <= 0 || typeof window === "undefined") return;
    const AudioContextClass = window.AudioContext;
    if (!AudioContextClass) return;
    const context = audioContextRef.current ?? new AudioContextClass();
    audioContextRef.current = context;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = downbeat ? 1160 : 820;
    gain.gain.setValueAtTime(level * 0.12, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.045);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.05);
  }, [mixer.metronome]);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "auto";
    audio.preservesPitch = true;
    const source = createSyntheticDemoAudioUrl(DEMO_DURATION, DEMO_BPM);
    sourceRef.current = source;
    audio.src = source;
    audio.volume = Math.min(1, (mixer.original + mixer.drums * 0.7) / 1.7);
    audio.addEventListener("loadedmetadata", () => setDuration(Number.isFinite(audio.duration) ? audio.duration : DEMO_DURATION));
    audio.addEventListener("ended", () => setPlaying(false));
    audioRef.current = audio;
    return () => {
      audio.pause();
      stemRef.current?.pause();
      if (sourceRef.current) URL.revokeObjectURL(sourceRef.current);
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      countInTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      void audioContextRef.current?.close();
      audioRef.current = null;
    };
    // The authoritative element is intentionally created once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!audioRef.current) return;
    mixerRef.current = mixer;
    audioRef.current.volume = stemRef.current ? mixer.original : Math.min(1, (mixer.original + mixer.drums * 0.7) / 1.7);
    if (stemRef.current) stemRef.current.volume = mixer.drums;
  }, [mixer]);

  useEffect(() => {
    if (!playing) {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      return;
    }
    const update = () => {
      const audio = audioRef.current;
      if (!audio) return;
      if (loop.enabled && audio.currentTime >= loop.end - 0.012) {
        audio.currentTime = loop.start;
        if (stemRef.current) stemRef.current.currentTime = loop.start;
      }
      if (stemRef.current && Math.abs(stemRef.current.currentTime - audio.currentTime) > 0.045) stemRef.current.currentTime = audio.currentTime;
      const nextTime = audio.currentTime;
      setCurrentTime(nextTime);
      const beat = Math.floor(nextTime / (60 / bpm));
      if (beat !== lastBeatRef.current) {
        lastBeatRef.current = beat;
        clickMetronome(beat % 4 === 0);
      }
      frameRef.current = requestAnimationFrame(update);
    };
    frameRef.current = requestAnimationFrame(update);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [bpm, clickMetronome, loop, playing]);

  const togglePlayback = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      if (loop.enabled && (audio.currentTime < loop.start || audio.currentTime >= loop.end)) audio.currentTime = loop.start;
      void audio.play().then(() => {
        if (stemRef.current) {
          stemRef.current.currentTime = audio.currentTime;
          void stemRef.current.play().catch(() => undefined);
        }
        setPlaying(true);
      }).catch(() => setPlaying(false));
    } else {
      audio.pause();
      stemRef.current?.pause();
      setPlaying(false);
    }
  }, [loop]);

  const seek = useCallback((time: number) => {
    const safe = Math.max(0, Math.min(duration, time));
    if (audioRef.current) audioRef.current.currentTime = safe;
    if (stemRef.current) stemRef.current.currentTime = safe;
    setCurrentTime(safe);
  }, [duration]);

  const playWithCountIn = useCallback((bars: 0 | 1 | 2) => {
    if (playing || bars === 0) {
      togglePlayback();
      return;
    }
    if (countingIn) {
      countInTimersRef.current.forEach((timer) => window.clearTimeout(timer));
      countInTimersRef.current = [];
      setCountingIn(false);
      return;
    }
    const totalBeats = bars * 4;
    const beatMilliseconds = 60_000 / bpm;
    setCountingIn(true);
    countInTimersRef.current = Array.from({ length: totalBeats }, (_, beat) => window.setTimeout(() => clickMetronome(beat % 4 === 0, .82), beat * beatMilliseconds));
    countInTimersRef.current.push(window.setTimeout(() => {
      setCountingIn(false);
      countInTimersRef.current = [];
      togglePlayback();
    }, totalBeats * beatMilliseconds));
  }, [bpm, clickMetronome, countingIn, playing, togglePlayback]);

  const setPlaybackRate = useCallback((rate: number) => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
    if (stemRef.current) stemRef.current.playbackRate = rate;
    playbackRateRef.current = rate;
    setRateState(rate);
  }, []);

  const setLoop = useCallback((value: LoopRange) => setLoopState({ ...value, end: Math.max(value.start + 0.1, value.end) }), []);
  const setMixer = useCallback((value: MixerState) => setMixerState(value), []);
  const skipMeasure = useCallback((direction: -1 | 1) => seek(currentTime + direction * 4 * 60 / bpm), [bpm, currentTime, seek]);
  const loadAudioSources = useCallback((sources: { originalUrl: string; drumsUrl?: string; bpm?: number; preservePosition?: boolean }) => {
    const audio = audioRef.current;
    if (!audio) return;
    const wasPlaying = !audio.paused;
    const resumeAt = sources.preservePosition ? audio.currentTime : 0;
    audio.pause();
    stemRef.current?.pause();
    audio.src = sources.originalUrl;
    audio.playbackRate = playbackRateRef.current;
    audio.volume = sources.drumsUrl ? mixerRef.current.original : Math.min(1, (mixerRef.current.original + mixerRef.current.drums * .7) / 1.7);
    if (sources.drumsUrl) {
      const stem = new Audio(sources.drumsUrl);
      stem.preload = "auto";
      stem.preservesPitch = true;
      stem.playbackRate = playbackRateRef.current;
      stem.volume = mixerRef.current.drums;
      stemRef.current = stem;
    } else {
      stemRef.current = null;
    }
    const resume = () => {
      const safeTime = Math.max(0, Math.min(Number.isFinite(audio.duration) ? audio.duration : resumeAt, resumeAt));
      audio.currentTime = safeTime;
      if (stemRef.current) stemRef.current.currentTime = safeTime;
      setCurrentTime(safeTime);
      if (wasPlaying) {
        void audio.play().then(() => {
          if (stemRef.current) void stemRef.current.play().catch(() => undefined);
          setPlaying(true);
        }).catch(() => setPlaying(false));
      }
    };
    audio.addEventListener("loadedmetadata", resume, { once: true });
    audio.load();
    if (sources.bpm) setBpm(sources.bpm);
    if (!sources.preservePosition) setCurrentTime(0);
    if (!wasPlaying) setPlaying(false);
    setCountingIn(false);
  }, []);

  const value = useMemo<TransportContextValue>(() => ({
    currentTime,
    duration,
    playing,
    countingIn,
    playbackRate,
    loop,
    mixer,
    bpm,
    togglePlayback,
    playWithCountIn,
    seek,
    setPlaybackRate,
    setLoop,
    setMixer,
    skipMeasure,
    loadAudioSources,
  }), [bpm, countingIn, currentTime, duration, loadAudioSources, loop, mixer, playbackRate, playWithCountIn, playing, seek, setLoop, setMixer, setPlaybackRate, skipMeasure, togglePlayback]);

  return <TransportContext.Provider value={value}>{children}</TransportContext.Provider>;
}

export function useTransport() {
  const value = useContext(TransportContext);
  if (!value) throw new Error("useTransport must be used inside TransportProvider");
  return value;
}
