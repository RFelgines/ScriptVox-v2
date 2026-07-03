"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { translations, type Dictionary, type Locale } from "@/lib/i18n/translations";

const STORAGE_KEY = "language";
// Français par défaut : cohérent avec le fallback backend (resolve_profile,
// language_profiles.py) -- zéro régression pour un visiteur sans préférence.
const DEFAULT_LOCALE: Locale = "fr";

type LanguageContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Dictionary;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  // Lu après hydratation seulement (pas de flash critique à éviter ici,
  // contrairement au thème : le texte n'affecte pas le layout/CSS avant
  // paint) -- corrige le SSR "fr" par défaut vers la préférence stockée.
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "fr" || stored === "en") setLocaleState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  function setLocale(next: Locale) {
    localStorage.setItem(STORAGE_KEY, next);
    setLocaleState(next);
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
