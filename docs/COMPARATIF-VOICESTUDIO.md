# Comparatif VoiceStudio / ScriptVox (2026-09-28)

VoiceStudio : <https://github.com/debpalash/VoiceStudio> (~40 000 étoiles, actif).
**Licence AGPL-3.0** : on s'inspire des idées, on ne copie jamais le code. Rien de ce qui
suit ne reprend de code de VoiceStudio ; les sources consultées sont sa documentation
(README, catalogue des fonctionnalités, guide d'installation Windows, spécification
« Stories & Audiobook maturity ») et les **noms** de ses tests.

## Méthode et limites

VoiceStudio n'a **pas été installé**, pour deux raisons mesurées :

- **AMD sous Windows = CPU uniquement.** Leur guide Windows l'écrit explicitement : pas de
  ROCm Windows, les GPU Radeon tournent en CPU. ScriptVox, lui, tourne en ROCm 7.2.1 sur la
  Radeon RX 9070 XT de la machine (Qwen3-TTS, et désormais OmniVoice).
- **Disque C: à 18 Go libres**, pour ~10 Go d'application et d'environnement plus les
  modèles.

Conséquence : le banc prévu (attribution de 30 répliques, qualité audio en français,
temps de rendu sur 1-2 chapitres) n'a **pas** été mené. Les constats ci-dessous portent
sur la conception, pas sur des mesures côte à côte. Si un banc chiffré est voulu :
installation sur D: ou sur la machine Linux (ROCm y est pris en charge par VoiceStudio).

## Positionnement

| | ScriptVox | VoiceStudio |
|---|---|---|
| Cible | livre audio **multi-voix automatique** à partir d'un EPUB | studio vocal généraliste : clonage, conception de voix, doublage vidéo, dictée, transcription, livre audio |
| Moteurs TTS | EdgeTTS, Piper, Qwen3-TTS, **OmniVoice** (ajouté), HTTP OpenAI, commande, plugins | OmniVoice (défaut) + ~15 moteurs (CosyVoice 3, IndexTTS, MOSS-TTS…) |
| GPU AMD sous Windows | **oui** (ROCm) | non (CPU) |
| Licence | projet privé | AGPL-3.0 (poids OmniVoice : CC-BY-NC) |

## Attribution des répliques

| | ScriptVox | VoiceStudio |
|---|---|---|
| Livre audio | **analyse LLM de chaque chapitre** : repérage des répliques par la typographie de la langue (profils fr/en/es/de/it), attribution à un personnage par le LLM, incises rendues au narrateur, noms explicites attribués sans LLM, personnages suivis d'un chapitre à l'autre, suggestions de fusion | casting par **balises manuelles** `[voice:Nom]` associées à des profils de voix (« cast map ») |
| « Auto-cast » | attribution automatique des voix par genre, âge et importance du personnage | à règles, dans l'éditeur « Stories » ; « richer auto-cast (gender/voice matching) » figure encore dans leur feuille de route (P2) |

Sur un roman sans incises systématiques, l'approche LLM de ScriptVox est structurellement
en avance : VoiceStudio demande à l'utilisateur de baliser chaque réplique.

## Fonctions de production : état après ce lot

| Fonction | ScriptVox (avant) | ScriptVox (après ce lot) | VoiceStudio (doc) |
|---|---|---|---|
| M4B chapitré + couverture | oui | oui + **métadonnées globales** (album, narrateur, année, genre, commentaire) | oui (spec : métadonnées globales) |
| Horodatage des chapitres | non | **.txt** « HH:MM:SS Titre » | — |
| Aperçu avant rendu | une réplique par personnage | **+ extrait d'un chapitre** (~1 min, rendu final) | aperçu d'un chapitre (spec P0) |
| Reprise après échec | par chapitre | **par segment** (cache à clé de contenu) | par chapitre (cache à clé de contenu) |
| Normalisation | par segment | **+ mastering ACX du chapitre** + contrôle de conformité | `loudnorm` ffmpeg, préréglages ACX / Podcast -16 LUFS / off |
| Lexique de prononciation | non | **global + par livre**, appliqué au seul texte prononcé | dictionnaire de prononciation |
| Titres EPUB | sommaire ebooklib, puis `<h1>` | **nav EPUB3 > NCX > `<h1>`** (repli NCX quand la nav est vide) | la nav prime sur le NCX |
| Pages liminaires | noms de fichiers / titres | **+ sémantique EPUB** (repères nav, `<guide>`, `epub:type`) ; **corps du texte déclaré jamais exclu** | idem (tests « front and back matter », « body matter survives ») |
| Numéros de page | lus | **retirés** (`pagebreak`, `doc-pagebreak`, classe « pagenum ») | retirés |
| Voix conçue par description | non | **oui** (OmniVoice), conçue une fois puis clonée : même voix tout le livre | oui (moteur par défaut) |
| Émotion par réplique | Qwen3-TTS CustomVoice (`instruct`) | idem ; OmniVoice : débit seulement | « expressive » : réglages par réplique ; d'après le nom d'un test, l'émotion n'atteint jamais OmniVoice (« overrides reach model but emotion never does ») |

## Idées reprises dans ce lot

1. **Numéros de page jamais lus** (EPUB3 `pagebreak`, `role="doc-pagebreak"`, classe
   « pagenum ») — fréquents dans les éditions accessibles du commerce ; absents des 25 EPUB
   Gutenberg de test, d'où un correctif préventif.
2. **Un chapitre déclaré corps du texte** (`epub:type` chapter, bodymatter…) n'est jamais
   exclu sur la foi de son titre (« Dédicace », « Contents » peuvent être un vrai récit).
3. **Métadonnées globales du M4B** : album, narrateur (`composer`, convention des lecteurs
   de livres audio), année (date de publication du livre), genre, commentaire.

## Idées notées, non reprises (pour l'instant)

- **Préréglage « Podcast -16 LUFS »** à côté d'ACX : utile si l'on publie en podcast ; le
  mastering actuel est en RMS (critère ACX), un préréglage LUFS demanderait une mesure
  pondérée (ffmpeg `loudnorm` ou pyloudnorm).
- **MP3 chapitré (trames ID3 CHAP)** et **export par chapitre (zip)**.
- **Rognage des silences de bord** ajoutés par le moteur (OmniVoice ajoute 0,1 s de marge
  et un fondu) : le rythme entre répliques est déjà réglé par les pauses de ScriptVox.
- **Répétitions** : leur rendu déduplique les lignes identiques par défaut, avec une option
  « varier les répétitions » (graine par occurrence). À évaluer sur de vrais livres.
- **SSML allégé** (`[emphasis]`, `[slow]`, `[spell]`) : recoupe le lexique ; à voir.
- **Rendu par lots** : OmniVoice passe de RTF 0,18 à 0,028 en lot de 4 phrases sur la
  RX 9070 XT ; ScriptVox synthétise segment par segment. C'est le prochain gain de vitesse.
