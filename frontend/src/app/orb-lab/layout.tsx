import { notFound } from "next/navigation";
import type { ReactNode } from "react";

// Laboratoire d'animation des orbes : outil de développement uniquement. En production
// (`npm run build`), la route n'existe pas (404) — audit 2026-09-25, UX-7.
export default function OrbLabLayout({ children }: { children: ReactNode }) {
  if (process.env.NODE_ENV === "production") notFound();
  return <>{children}</>;
}
