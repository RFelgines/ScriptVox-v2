"use client";

import {
  createContext,
  useContext,
  useRef,
  useState,
  useMemo,
  useCallback,
  useEffect,
  ReactNode,
} from "react";
import { SegmentSummary, VoiceSummary, getChapterSegments, listVoices } from "@/lib/api";

export interface Track {
  title: string;
  src: string;
  bookId?: number;
  bookTitle?: string;
  coverUrl?: string;
  chapterPosition?: number;
}

const GOLDEN_ANGLE = 137.5077;

function buildHueMap(voices: VoiceSummary[]): Map<string, number> {
  const sortedIds = voices.map((v) => v.id).sort();
  const map = new Map<string, number>();
  sortedIds.forEach((id, i) => map.set(id, (i * GOLDEN_ANGLE) % 360));
  return map;
}

interface PlayerState {
  track: Track | null;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  rate: number;
  currentSegment: SegmentSummary | null;
  voiceHues: Map<string, number>;
}

interface PlayerControls {
  play: (track: Track) => void;
  toggle: () => void;
  seek: (time: number) => void;
  setRate: (rate: number) => void;
  close: () => void;
}

const PlayerContext = createContext<(PlayerState & PlayerControls) | null>(null);

export function usePlayer() {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer must be used inside PlayerProvider");
  return ctx;
}

export default function PlayerProvider({ children }: { children: ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRateState] = useState(1);
  const [segments, setSegments] = useState<SegmentSummary[]>([]);
  const [voiceHues, setVoiceHues] = useState<Map<string, number>>(new Map());

  // Créer l'élément audio une seule fois côté client.
  useEffect(() => {
    const audio = new Audio();
    audio.addEventListener("timeupdate", () => setCurrentTime(audio.currentTime));
    audio.addEventListener("loadedmetadata", () => setDuration(audio.duration));
    audio.addEventListener("ended", () => setIsPlaying(false));
    audioRef.current = audio;
    return () => {
      audio.pause();
      audio.src = "";
    };
  }, []);

  // Charger les couleurs des orbes une seule fois (correspondance exacte avec /voix)
  useEffect(() => {
    listVoices()
      .then((voices) => setVoiceHues(buildHueMap(voices)))
      .catch(() => {});
  }, []);

  // Charger la timeline de segments quand le chapitre change
  useEffect(() => {
    if (!track?.bookId || track.chapterPosition === undefined) {
      Promise.resolve().then(() => setSegments([]));
      return;
    }
    let active = true;
    getChapterSegments(track.bookId, track.chapterPosition)
      .then((segs) => { if (active) setSegments(segs); })
      .catch(() => { if (active) setSegments([]); });
    return () => { active = false; };
  }, [track?.bookId, track?.chapterPosition]);

  // Segment courant dérivé de currentTime — pas de setState dans un effect
  const currentSegment = useMemo(() => {
    const ms = currentTime * 1000;
    return (
      segments.findLast(
        (s) => s.audio_offset_ms !== null && ms >= (s.audio_offset_ms ?? Infinity),
      ) ?? null
    );
  }, [segments, currentTime]);

  const play = useCallback((newTrack: Track) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.src = newTrack.src;
    audio.playbackRate = rate;
    audio.play().catch(() => {});
    setTrack(newTrack);
    setIsPlaying(true);
    setCurrentTime(0);
    setDuration(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !track) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      audio.play().catch(() => {});
      setIsPlaying(true);
    }
  }, [isPlaying, track]);

  const seek = useCallback((time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = time;
    setCurrentTime(time);
  }, []);

  const setRate = useCallback((newRate: number) => {
    const audio = audioRef.current;
    if (audio) audio.playbackRate = newRate;
    setRateState(newRate);
  }, []);

  const close = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.src = "";
    }
    setTrack(null);
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
  }, []);

  return (
    <PlayerContext.Provider
      value={{
        track, isPlaying, currentTime, duration, rate,
        currentSegment, voiceHues,
        play, toggle, seek, setRate, close,
      }}
    >
      {children}
    </PlayerContext.Provider>
  );
}
