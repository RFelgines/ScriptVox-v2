"use client";

import { useLanguage } from "@/lib/i18n/LanguageContext";

export default function LanguageToggle() {
  const { locale, setLocale } = useLanguage();

  return (
    <button
      onClick={() => setLocale(locale === "fr" ? "en" : "fr")}
      aria-label={locale === "fr" ? "Switch to English" : "Passer en français"}
      className="rounded-control px-2 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
    >
      {locale === "fr" ? "EN" : "FR"}
    </button>
  );
}
