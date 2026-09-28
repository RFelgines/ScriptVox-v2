"use client";

import { useState } from "react";
import { getVoiceDesign, requestVoiceDesign } from "@/lib/api";
import Button from "@/components/ui/Button";
import { useT } from "@/lib/i18n/LanguageContext";

// « Prompt de voix » d'un personnage : description proposée depuis sa fiche (genre, âge,
// qualité de voix relevés par l'analyse), modifiable, puis conception par OmniVoice. La voix
// conçue est clonée à chaque réplique : même voix d'un bout à l'autre du livre.
export default function VoiceDesign({
  characterId,
  onDesigned,
}: {
  characterId: number;
  onDesigned: () => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [instruct, setInstruct] = useState("");
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) return setOpen(false);
    setOpen(true);
    try {
      const info = await getVoiceDesign(characterId);
      setInstruct(info.current_instruct ?? info.suggested_instruct);
    } catch (e) {
      setError(String(e));
    }
  }

  async function launch() {
    setStatus("running");
    setError(null);
    try {
      await requestVoiceDesign(characterId, instruct);
      // La tâche passe avant les chapitres en file ; le premier appel charge le modèle.
      for (let i = 0; i < 150; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const info = await getVoiceDesign(characterId);
        if (info.assigned && info.current_instruct === instruct.trim()) {
          setStatus("done");
          onDesigned();
          return;
        }
      }
      setStatus("error");
      setError(t.production.designNeedsServer);
    } catch (e) {
      setStatus("error");
      setError(String(e));
    }
  }

  return (
    <div className="w-full">
      <button
        onClick={toggle}
        title={t.production.designVoiceTitle}
        className="rounded-full px-2 py-0.5 text-xs text-muted hover:bg-surface-2 hover:text-foreground"
      >
        {open ? "▾" : "▸"} {t.production.designVoice}
      </button>
      {open && (
        <div className="mt-2 space-y-2 rounded-xl bg-surface-2/60 p-3">
          <label className="block text-xs font-medium">{t.production.designPromptLabel}</label>
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="min-w-64 flex-1 rounded-control border border-border bg-surface px-2 py-1 font-mono text-sm"
              value={instruct}
              onChange={(e) => setInstruct(e.target.value)}
            />
            <Button size="sm" variant="primary" onClick={launch} disabled={!instruct.trim() || status === "running"}>
              {status === "running" ? t.production.designRunning : t.production.designLaunch}
            </Button>
            {status === "done" && <span className="text-xs text-success">✓ {t.production.designDone}</span>}
          </div>
          <p className="text-xs text-muted">{t.production.designPromptHint}</p>
          {error && <p className="text-xs text-danger">{error}</p>}
        </div>
      )}
    </div>
  );
}
