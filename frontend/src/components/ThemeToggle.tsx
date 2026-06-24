"use client";

import { useState } from "react";

type Theme = "light" | "dark";

export default function ThemeToggle() {
  // Initialiseur paresseux : lit le DOM déjà corrigé par le script anti-flash
  // de layout.tsx (cf. doc Next "preventing-flash-before-hydration", section
  // "Syncing with React state") -- état React et attribut data-theme restent
  // d'accord dès le premier rendu. Sombre = absence d'attribut (défaut
  // implicite de :root), pas une valeur "dark" explicite.
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof document === "undefined") return "dark";
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  });

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    if (next === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      // Retour au défaut implicite (sombre) -- pas de setAttribute("dark"),
      // même logique que le script anti-flash : jamais de littéral "dark" à
      // réconcilier.
      document.documentElement.removeAttribute("data-theme");
    }
    localStorage.setItem("theme", next);
    setTheme(next);
  }

  return (
    <button
      onClick={toggle}
      aria-label={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
      className="rounded-control p-2 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
    >
      {theme === "dark" ? (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="h-4 w-4"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
        </svg>
      )}
    </button>
  );
}
