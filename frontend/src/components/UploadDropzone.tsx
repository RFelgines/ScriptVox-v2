"use client";

import { useRef, useState } from "react";
import { uploadBook, BookSummary } from "@/lib/api";

export default function UploadDropzone({
  onUploaded,
}: {
  onUploaded: (book: BookSummary) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    if (!file.name.toLowerCase().endsWith(".epub")) {
      setError("Seuls les fichiers .epub sont acceptés.");
      return;
    }
    setUploading(true);
    try {
      const book = await uploadBook(file);
      onUploaded(book);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="mb-8">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-card border-2 border-dashed p-8 text-center transition-colors ${
          dragging ? "border-foreground bg-surface-2" : "border-border hover:border-muted"
        } ${uploading ? "pointer-events-none opacity-60" : ""}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".epub"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            e.target.value = "";
          }}
        />
        <p className="font-medium text-foreground">
          {uploading ? "Upload en cours…" : "Glissez un EPUB ici"}
        </p>
        <p className="mt-1 text-sm text-muted">
          ou cliquez pour choisir un fichier .epub
        </p>
      </div>
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
