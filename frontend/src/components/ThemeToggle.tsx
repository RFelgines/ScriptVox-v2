"use client";

import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

// Le thème vit dans l'attribut data-theme de <html> (posé avant l'hydratation par le script
// anti-flash de layout.tsx). useSyncExternalStore avec un snapshot serveur « dark » : le premier
// rendu client est identique au HTML serveur, puis React resynchronise sur l'attribut réel — plus
// d'erreur d'hydratation en thème clair (l'ancien initialiseur lisait le DOM dès le premier
// rendu : « light » côté client contre « dark » côté serveur, audit navigateur 2026-09-25).
// Sombre = absence d'attribut (défaut implicite de :root), pas une valeur "dark" explicite.
function subscribe(callback: () => void): () => void {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

function getSnapshot(): Theme {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function getServerSnapshot(): Theme {
  return "dark";
}

export default function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

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
