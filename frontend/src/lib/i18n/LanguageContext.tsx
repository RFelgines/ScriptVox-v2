"use client";

import { createContext, useContext, useEffect, useSyncExternalStore, type ReactNode } from "react";
import {
  LOCALE_STORAGE_KEY,
  translations,
  type Dictionary,
  type Locale,
} from "@/lib/i18n/translations";

// Français par défaut : cohérent avec le fallback backend (resolve_profile,
// language_profiles.py) -- zéro régression pour un visiteur sans préférence.
const DEFAULT_LOCALE: Locale = "fr";

// L'event "storage" natif ne se déclenche que pour les AUTRES onglets, jamais
// celui qui vient d'écrire la valeur -- un event custom couvre le cas local
// (clic sur le toggle dans cet onglet).
const LOCALE_CHANGE_EVENT = "scriptvox:locale-change";

function subscribe(callback: () => void): () => void {
  window.addEventListener(LOCALE_CHANGE_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(LOCALE_CHANGE_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function getSnapshot(): Locale {
  return localStorage.getItem(LOCALE_STORAGE_KEY) === "en" ? "en" : DEFAULT_LOCALE;
}

function getServerSnapshot(): Locale {
  return DEFAULT_LOCALE;
}

type LanguageContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Dictionary;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  // useSyncExternalStore -- pas de setState dans un effet (évite l'anti-pattern
  // "cascading renders" signalé par eslint react-hooks) : localStorage EST la
  // source de vérité, lue directement, avec un snapshot serveur explicite (fr).
  const locale = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  function setLocale(next: Locale) {
    localStorage.setItem(LOCALE_STORAGE_KEY, next);
    window.dispatchEvent(new Event(LOCALE_CHANGE_EVENT));
  }

  return (
    <LanguageContext.Provider value={{ locale, setLocale, t: translations[locale] }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within a LanguageProvider");
  return ctx;
}

export function useT(): Dictionary {
  return useLanguage().t;
}
