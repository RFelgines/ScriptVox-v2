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
import { buildHueMap } from "@/lib/voiceHues";

export interface Track {
  title: string;
  src: string;
  bookId?: number;
  bookTitle?: string;
  coverUrl?: string;
  chapterPosition?: number;
}

interface PlayerState {
  track: Track | null;
  isPlaying: boolean;
  audioError: boolean;
  currentTime: number;
  duration: number;
  rate: number;
  currentSegment: SegmentSummary | null;
  voiceHues: Map<string, number>;
  voiceNames: Map<string, string>;
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
  const [audioError, setAudioError] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRateState] = useState(1);
  const rateRef = useRef(1);
  const [segments, setSegments] = useState<SegmentSummary[]>([]);
  const [voiceHues, setVoiceHues] = useState<Map<string, number>>(new Map());
  const [voiceNames, setVoiceNames] = useState<Map<string, string>>(new Map());

  // --- Amplitude audio -> var CSS --voice-amp (consommée par VoiceOrb) ---
  // Tout passe par des refs + une variable CSS sur <html> : zéro re-render
  // React à 60 fps, seules les orbes `active` (1-2 max) référencent la var.
  // Quand rien ne joue, la propriété est RETIRÉE : les consommateurs
  // retombent sur var(--voice-amp, 0.55) (intensité moyenne -- orb-lab,
  // analyse indisponible...).
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const meterDataRef = useRef<Uint8Array<ArrayBuffer> | null>(null);
  const meterRafRef = useRef(0);
  const ampRef = useRef(0);
  const lastAmpWrittenRef = useRef(-1);

  // À n'appeler que depuis un geste utilisateur (play/toggle) : l'AudioContext
  // démarre "suspended" sinon. createMediaElementSource ne peut être appelé
  // qu'une fois par élément -> création paresseuse unique, puis resume().
  const ensureAnalyser = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audioCtxRef.current) {
      audioCtxRef.current.resume().catch(() => {});
      return;
    }
    try {
      const ctx = new AudioContext();
      const source = ctx.createMediaElementSource(audio);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.5;
      source.connect(analyser);
      analyser.connect(ctx.destination);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;
      meterDataRef.current = new Uint8Array(analyser.fftSize);
      ctx.resume().catch(() => {});
    } catch {
      // Web Audio indisponible : lecture normale, orbes à intensité par défaut.
      analyserRef.current = null;
    }
  }, []);

  const stopMeter = useCallback(() => {
    if (meterRafRef.current) cancelAnimationFrame(meterRafRef.current);
    meterRafRef.current = 0;
    ampRef.current = 0;
    lastAmpWrittenRef.current = -1;
    document.documentElement.style.removeProperty("--voice-amp");
  }, []);

  const startMeter = useCallback(() => {
    const analyser = analyserRef.current;
    const data = meterDataRef.current;
    if (!analyser || !data || meterRafRef.current) return;
    const tick = () => {
      meterRafRef.current = requestAnimationFrame(tick);
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const d = (data[i] - 128) / 128;
        sum += d * d;
      }
      // RMS de parole ~0.1-0.35 -> remonté vers 0..1, puis lissage asymétrique
      // façon vumètre : attaque rapide, retombée douce.
      const target = Math.min(1, Math.sqrt(sum / data.length) * 3.2);
      const prev = ampRef.current;
      const next = prev + (target - prev) * (target > prev ? 0.45 : 0.12);
      ampRef.current = next;
      if (Math.abs(next - lastAmpWrittenRef.current) > 0.01) {
        lastAmpWrittenRef.current = next;
        document.documentElement.style.setProperty("--voice-amp", next.toFixed(3));
      }
    };
    tick();
  }, []);

  // Créer l'élément audio une seule fois côté client. crossOrigin AVANT tout
  // src : requis pour que l'AnalyserNode reçoive du signal depuis l'API
  // (autre origine) -- le backend sert déjà les en-têtes CORS à toute l'app.
  useEffect(() => {
    const audio = new Audio();
    audio.crossOrigin = "anonymous";
    audio.addEventListener("timeupdate", () => setCurrentTime(audio.currentTime));
    audio.addEventListener("loadedmetadata", () => setDuration(audio.duration));
    audio.addEventListener("ended", () => {
      setIsPlaying(false);
      stopMeter();
    });
    audio.addEventListener("error", () => {
      setIsPlaying(false);
      setAudioError(true);
      stopMeter();
    });
    audioRef.current = audio;
    return () => {
      audio.pause();
      audio.src = "";
      stopMeter();
      audioCtxRef.current?.close().catch(() => {});
      audioCtxRef.current = null;
    };
  }, [stopMeter]);

  // Charger les couleurs des orbes + les noms de voix une seule fois (correspondance
  // exacte avec /voix). Le bandeau "Lu par" affiche la voix réellement entendue
  // (ex. "Nicolas Sarkozy" pour une voix clonée), pas le personnage — qui reste
  // visible dans la transcription (audit utilisateur 2026-07-02).
  useEffect(() => {
    listVoices()
      .then((voices: VoiceSummary[]) => {
        setVoiceHues(buildHueMap(voices));
        setVoiceNames(new Map(voices.map((v) => [v.id, v.name])));
      })
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
    setAudioError(false);
    ensureAnalyser();
    audio.src = newTrack.src;
    audio.playbackRate = rateRef.current;
    audio.play().catch(() => { setIsPlaying(false); setAudioError(true); });
    startMeter();
    setTrack(newTrack);
    setIsPlaying(true);
    setCurrentTime(0);
    setDuration(0);
  }, [ensureAnalyser, startMeter]);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !track) return;
    if (isPlaying) {
      audio.pause();
      stopMeter();
      setIsPlaying(false);
    } else {
      ensureAnalyser();
      audio.play().catch(() => { setIsPlaying(false); });
      startMeter();
      setIsPlaying(true);
    }
  }, [isPlaying, track, ensureAnalyser, startMeter, stopMeter]);

  const seek = useCallback((time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = time;
    setCurrentTime(time);
  }, []);

  const setRate = useCallback((newRate: number) => {
    const audio = audioRef.current;
    if (audio) audio.playbackRate = newRate;
    rateRef.current = newRate;
    setRateState(newRate);
  }, []);

  const close = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.src = "";
    }
    stopMeter();
    setTrack(null);
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
  }, [stopMeter]);

  return (
    <PlayerContext.Provider
      value={{
        track, isPlaying, audioError, currentTime, duration, rate,
        currentSegment, voiceHues, voiceNames,
        play, toggle, seek, setRate, close,
      }}
    >
      {children}
    </PlayerContext.Provider>
  );
}
