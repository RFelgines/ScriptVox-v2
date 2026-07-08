"use client";

import { useRef, useState } from "react";
import { uploadBook, BookSummary } from "@/lib/api";
import { useT } from "@/lib/i18n/LanguageContext";

export default function UploadDropzone({
  onUploaded,
}: {
  onUploaded: (book: BookSummary) => void;
}) {
  const t = useT();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    if (!file.name.toLowerCase().endsWith(".epub")) {
      setError(t.upload.invalidFile);
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
        className={`group cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-300 ${
          dragging
            ? "scale-[1.01] border-primary bg-surface-2 shadow-[0_0_32px_rgba(245,243,241,0.1)]"
            : "border-border hover:border-primary/40 hover:bg-surface/60"
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
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className={`mx-auto mb-3 text-muted transition-transform duration-300 ${dragging ? "scale-110 text-primary" : "group-hover:-translate-y-0.5"}`}
        >
          <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
          <path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" />
        </svg>
        <p className="font-display text-lg font-medium text-foreground">
          {uploading ? t.upload.uploading : t.upload.dropHint}
        </p>
        <p className="mt-1 text-sm text-muted">
          {t.upload.clickHint}
        </p>
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </div>
  );
}
