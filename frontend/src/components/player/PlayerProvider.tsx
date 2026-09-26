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
import {
  SegmentSummary,
  VoiceSummary,
  chapterAudioUrl,
  getChapterSegments,
  listChapters,
  listVoices,
} from "@/lib/api";
import { buildHueMap } from "@/lib/voiceHues";
import { saveResume } from "@/lib/resume";
import { useT } from "@/lib/i18n/LanguageContext";

export interface Track {
  title: string;
  src: string;
  bookId?: number;
  bookTitle?: string;
  coverUrl?: string;
  chapterPosition?: number;
  // Position de départ (secondes) : reprise de lecture.
  startAt?: number;
}

export type SleepMode = "off" | "chapter" | "timer";

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
  sleepMode: SleepMode;
  sleepRemaining: number | null; // secondes, mode « timer » uniquement
}

interface PlayerControls {
  play: (track: Track) => void;
  toggle: () => void;
  seek: (time: number) => void;
  setRate: (rate: number) => void;
  close: () => void;
  // Minuterie de sommeil : « off », fin du chapitre, ou un nombre de minutes.
  setSleep: (option: "off" | "chapter" | number) => void;
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
  const t = useT();

  // Refs lues par les écouteurs (créés une seule fois) : toujours la dernière valeur.
  const trackRef = useRef<Track | null>(null);
  const pendingStartRef = useRef(0);
  const lastSavedRef = useRef(0);
  const advanceRef = useRef<() => void>(() => {});
  const controlsRef = useRef<{
    toggle: () => void;
    seek: (time: number) => void;
    setRate: (rate: number) => void;
  } | null>(null);
  const currentTimeRef = useRef(0);
  const rateValueRef = useRef(1);
  const sleepModeRef = useRef<SleepMode>("off");
  const [sleepMode, setSleepMode] = useState<SleepMode>("off");
  const [sleepEndsAt, setSleepEndsAt] = useState<number | null>(null);
  const [sleepRemaining, setSleepRemaining] = useState<number | null>(null);

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

    // Enregistre la position (reprise de lecture) — au plus toutes les 5 s pendant la lecture.
    const persist = (force: boolean, at?: number) => {
      const cur = trackRef.current;
      if (!cur || cur.bookId === undefined || cur.chapterPosition === undefined) return;
      const now = Date.now();
      if (!force && now - lastSavedRef.current < 5000) return;
      lastSavedRef.current = now;
      saveResume(cur.bookId, {
        chapterPosition: cur.chapterPosition,
        time: at ?? audio.currentTime,
        updatedAt: now,
      });
    };

    audio.addEventListener("timeupdate", () => {
      currentTimeRef.current = audio.currentTime;
      setCurrentTime(audio.currentTime);
      persist(false);
    });
    audio.addEventListener("loadedmetadata", () => {
      setDuration(audio.duration);
      if (pendingStartRef.current > 0) {
        audio.currentTime = pendingStartRef.current;
        pendingStartRef.current = 0;
      }
    });
    audio.addEventListener("pause", () => persist(true));
    audio.addEventListener("ended", () => {
      setIsPlaying(false);
      stopMeter();
      persist(true, 0); // chapitre terminé : la reprise repartira de son début
      advanceRef.current(); // enchaîne le chapitre suivant (sauf minuterie « fin du chapitre »)
    });
    audio.addEventListener("error", () => {
      setIsPlaying(false);
      setAudioError(true);
      stopMeter();
    });
    const onPageHide = () => persist(true);
    window.addEventListener("pagehide", onPageHide);
    audioRef.current = audio;
    return () => {
      window.removeEventListener("pagehide", onPageHide);
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
    pendingStartRef.current = newTrack.startAt ?? 0;
    lastSavedRef.current = 0;
    trackRef.current = newTrack;
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
    rateValueRef.current = newRate;
    setRateState(newRate);
  }, []);

  const close = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.src = "";
    }
    stopMeter();
    trackRef.current = null;
    setTrack(null);
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
  }, [stopMeter]);

  // ── Minuterie de sommeil ────────────────────────────────────────────────────
  const setSleep = useCallback((option: "off" | "chapter" | number) => {
    if (option === "off") {
      sleepModeRef.current = "off";
      setSleepMode("off");
      setSleepEndsAt(null);
      setSleepRemaining(null);
    } else if (option === "chapter") {
      sleepModeRef.current = "chapter";
      setSleepMode("chapter");
      setSleepEndsAt(null);
      setSleepRemaining(null);
    } else {
      sleepModeRef.current = "timer";
      setSleepMode("timer");
      setSleepEndsAt(Date.now() + option * 60_000);
      setSleepRemaining(option * 60);
    }
  }, []);

  useEffect(() => {
    if (sleepEndsAt === null) return;
    const id = window.setInterval(() => {
      const remaining = Math.max(0, Math.round((sleepEndsAt - Date.now()) / 1000));
      setSleepRemaining(remaining);
      if (remaining <= 0) {
        audioRef.current?.pause();
        stopMeter();
        setIsPlaying(false);
        sleepModeRef.current = "off";
        setSleepMode("off");
        setSleepEndsAt(null);
        setSleepRemaining(null);
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [sleepEndsAt, stopMeter]);

  // ── Enchaînement des chapitres (fin d'un chapitre -> suivant DONE et inclus) ──
  const advance = useCallback(async () => {
    const cur = trackRef.current;
    if (!cur || cur.bookId === undefined || cur.chapterPosition === undefined) return;
    if (sleepModeRef.current === "chapter") {
      setSleep("off"); // minuterie « fin du chapitre » : on s'arrête là
      return;
    }
    try {
      const chapters = await listChapters(cur.bookId);
      const next = chapters
        .filter((c) => c.status === "DONE" && c.included && c.position > cur.chapterPosition!)
        .sort((a, b) => a.position - b.position)[0];
      if (!next) return;
      const label = next.title ?? t.book.chapterFallback(next.position);
      play({
        ...cur,
        title: `${cur.bookTitle ?? cur.title} — ${label}`,
        src: chapterAudioUrl(cur.bookId, next.position),
        chapterPosition: next.position,
        startAt: undefined,
      });
    } catch {
      // réseau indisponible : la lecture s'arrête simplement en fin de chapitre
    }
  }, [play, setSleep, t]);

  // Les écouteurs (audio, clavier, Media Session) lisent toujours les dernières fonctions.
  useEffect(() => {
    advanceRef.current = () => {
      void advance();
    };
    controlsRef.current = { toggle, seek, setRate };
  });

  // ── Raccourcis clavier : Espace, ← → (−15 s / +30 s), [ ] (vitesse) ────────────
  useEffect(() => {
    const RATES = [0.5, 1, 1.25, 1.5, 2];
    function onKey(e: KeyboardEvent) {
      if (!trackRef.current || e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return;
      const controls = controlsRef.current;
      if (!controls) return;
      if (e.key === " " && tag !== "BUTTON") {
        e.preventDefault();
        controls.toggle();
      } else if (e.key === "ArrowLeft") {
        controls.seek(Math.max(0, currentTimeRef.current - 15));
      } else if (e.key === "ArrowRight") {
        controls.seek(currentTimeRef.current + 30);
      } else if (e.key === "[" || e.key === "]") {
        const idx = RATES.indexOf(rateValueRef.current);
        const base = idx === -1 ? 1 : idx;
        const next = RATES[Math.max(0, Math.min(RATES.length - 1, base + (e.key === "]" ? 1 : -1)))];
        controls.setRate(next);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ── Media Session : touches multimédia, écran de verrouillage, casque ──────────
  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    if (!track) {
      navigator.mediaSession.metadata = null;
      return;
    }
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.bookTitle ?? "ScriptVox",
      album: track.bookTitle ?? "ScriptVox",
      artwork: track.coverUrl ? [{ src: track.coverUrl, sizes: "512x512" }] : [],
    });
  }, [track]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    navigator.mediaSession.playbackState = isPlaying ? "playing" : "paused";
  }, [isPlaying]);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const session = navigator.mediaSession;
    const set = (action: MediaSessionAction, handler: MediaSessionActionHandler | null) => {
      try {
        session.setActionHandler(action, handler);
      } catch {
        // action non supportée par ce navigateur
      }
    };
    set("play", () => {
      if (!audioRef.current?.paused) return;
      controlsRef.current?.toggle();
    });
    set("pause", () => {
      if (audioRef.current?.paused) return;
      controlsRef.current?.toggle();
    });
    set("seekbackward", () => controlsRef.current?.seek(Math.max(0, currentTimeRef.current - 15)));
    set("seekforward", () => controlsRef.current?.seek(currentTimeRef.current + 30));
    set("nexttrack", () => advanceRef.current());
    set("previoustrack", () => controlsRef.current?.seek(0));
    return () => {
      for (const action of ["play", "pause", "seekbackward", "seekforward", "nexttrack", "previoustrack"] as const) {
        set(action, null);
      }
    };
  }, []);

  return (
    <PlayerContext.Provider
      value={{
        track, isPlaying, audioError, currentTime, duration, rate,
        currentSegment, voiceHues, voiceNames, sleepMode, sleepRemaining,
        play, toggle, seek, setRate, close, setSleep,
      }}
    >
      {children}
    </PlayerContext.Provider>
  );
}
