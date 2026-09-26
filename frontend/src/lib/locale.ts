/** Drapeaux et noms de langue, partagés entre la bibliothèque (langue d'un
 *  livre, issue de dc:language) et la page Voix (locale d'une voix).
 *  Extrait de voix/page.tsx, qui ne gérait que le cas "locale complète". */

function regionToFlag(region: string): string {
  const codePoints = [...region.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65);
  return String.fromCodePoint(...codePoints);
}

/** Locale complète -> drapeau ("fr-FR" -> 🇫🇷). null si aucune région. */
export function localeToFlag(locale: string): string | null {
  const region = locale.split("-")[1];
  if (!region || region.length !== 2) return null;
  return regionToFlag(region);
}

/** Le dc:language d'un EPUB donne le plus souvent un code nu ("fr", "en"),
 *  sans région : on associe une région représentative pour pouvoir afficher
 *  un drapeau. Choix assumé pour les langues multi-pays (en -> GB, pt -> PT). */
const LANGUAGE_REGION: Record<string, string> = {
  ar: "SA", cs: "CZ", da: "DK", de: "DE", el: "GR", en: "GB", es: "ES",
  fi: "FI", fr: "FR", he: "IL", hi: "IN", hu: "HU", it: "IT", ja: "JP",
  ko: "KR", nl: "NL", no: "NO", pl: "PL", pt: "PT", ro: "RO", ru: "RU",
  sv: "SE", tr: "TR", uk: "UA", zh: "CN",
};

/** Code de langue (nu ou avec région) -> drapeau. null si inconnu. */
export function languageToFlag(language: string): string | null {
  const [base, region] = language.toLowerCase().split(/[-_]/);
  if (region && region.length === 2) return regionToFlag(region);
  const mapped = LANGUAGE_REGION[base];
  return mapped ? regionToFlag(mapped) : null;
}

/** Nom lisible de la langue, pour l'infobulle : quelqu'un qui ne reconnaît
 *  pas le drapeau lit "français" au survol. Replié sur le code en majuscules
 *  si Intl.DisplayNames ne connaît pas la langue. */
export function languageName(language: string, displayLocale = "fr"): string {
  const code = language.toLowerCase().split(/[-_]/)[0];
  try {
    const names = new Intl.DisplayNames([displayLocale], { type: "language" });
    const name = names.of(code);
    if (name && name !== code) return name.charAt(0).toUpperCase() + name.slice(1);
  } catch {
    /* Intl.DisplayNames absent ou code invalide : on retombe sur le code. */
  }
  return language.toUpperCase();
}
