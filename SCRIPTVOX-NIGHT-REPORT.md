# ScriptVox — rapport de nuit (chantier B : multilingue)

Généré le 2026-09-28 00:02 (v2). Un seul chapitre par livre.
Moteur TTS : edgetts (basculé à chaud, réglage d'origine restauré ensuite).

## Synthèse

| langue | détectée | analyse | perso. | chapitres | génération | takes | audio | ratio | erreurs |
|---|---|---|---|---|---|---|---|---|---|
| fr | fr ✓ | ANALYZED (réutilisée) | 39 | 25/31 | DONE (25s) | 24 (702.8s) | 711.3s | 0.04x | 0 |
| en | en ✓ | ANALYZED (réutilisée) | 40 | 12/17 | DONE (26s) | 118 (927.5s) | 977.5s | 0.03x | 0 |
| es | es ✓ | ANALYZED (réutilisée) | 87 | 44/47 | DONE (53s) | 8 (533.4s) | 535.9s | 0.1x | 0 |
| de | de ✓ | ANALYZED (réutilisée) | 8 | 3/6 | DONE (117s) | 40 (2431.5s) | 2448.2s | 0.05x | 0 |
| it | it ✓ | ANALYZED (376s) | 37 | 36/39 | DONE (25s) | 42 (346.5s) | 360.2s | 0.07x | 0 |

## Détail par livre

### Daudet — Lettres de mon moulin (`fr`)

```json
{
  "langue_attendue": "fr",
  "livre": "Daudet — Lettres de mon moulin",
  "fichier": "daudet-lettres-de-mon-moulin.epub",
  "erreurs": [],
  "book_id": 1,
  "reutilise": true,
  "analyse_etat": "ANALYZED",
  "langue_detectee": "fr",
  "langue_correcte": true,
  "chapitres": 31,
  "chapitres_inclus": 25,
  "personnages": 39,
  "personnages_sans_voix": 0,
  "voix_distinctes": 8,
  "exemples_personnages": [
    {
      "nom": "AVANT-PROPOS",
      "voix": "neutral_0"
    },
    {
      "nom": "Maitre Honorat Grapazi",
      "voix": "male_2"
    },
    {
      "nom": "Le sieur Gaspard Mitifio",
      "voix": "male_0"
    },
    {
      "nom": "Vivette Cornille",
      "voix": "female_2"
    },
    {
      "nom": "Alphonse Daudet",
      "voix": "male_0"
    },
    {
      "nom": "Le rémouleur",
      "voix": "male_0"
    }
  ],
  "chapitre_genere": {
    "position": 15,
    "titre": "L'AGONIE DE LA SEMILLANTE"
  },
  "generation_etat": "DONE",
  "generation_duree_s": 25,
  "takes": {
    "nombre": 24,
    "duree_totale_s": 702.8,
    "silencieux": 0,
    "illisibles": 0,
    "vides_voulus": 0
  },
  "segments": {
    "total": 24,
    "dialogues": 15,
    "sans_duree": 0,
    "voix": [
      "male_0",
      "male_1",
      "narrator"
    ]
  },
  "audio": {
    "duree_s": 711.3,
    "hz": 24000,
    "canaux": 1,
    "pic": 29204,
    "rms": 3254.6,
    "silencieux": false,
    "fichier": "C:\\Users\\romai\\Documents\\ScriptVox-nuit-audio\\fr-1-ch15.wav",
    "ratio_temps_reel": 0.04
  },
  "duree_totale_s": 42
}
```

### Carroll — Alice in Wonderland (`en`)

```json
{
  "langue_attendue": "en",
  "livre": "Carroll — Alice in Wonderland",
  "fichier": "carroll-alice-in-wonderland.epub",
  "erreurs": [],
  "book_id": 2,
  "reutilise": true,
  "analyse_etat": "ANALYZED",
  "langue_detectee": "en",
  "langue_correcte": true,
  "chapitres": 17,
  "chapitres_inclus": 12,
  "personnages": 40,
  "personnages_sans_voix": 0,
  "voix_distinctes": 8,
  "exemples_personnages": [
    {
      "nom": "Alice",
      "voix": "female_0"
    },
    {
      "nom": "White Rabbit",
      "voix": "male_1"
    },
    {
      "nom": "Lory",
      "voix": "female_0"
    },
    {
      "nom": "Mouse",
      "voix": "female_0"
    },
    {
      "nom": "Duck",
      "voix": "female_1"
    },
    {
      "nom": "Eaglet",
      "voix": "female_0"
    }
  ],
  "chapitre_genere": {
    "position": 8,
    "titre": "CHAPTER IV. The Rabbit Sends in a Little Bill"
  },
  "generation_etat": "DONE",
  "generation_duree_s": 26,
  "takes": {
    "nombre": 118,
    "duree_totale_s": 927.5,
    "silencieux": 0,
    "illisibles": 0,
    "vides_voulus": 1
  },
  "segments": {
    "total": 118,
    "dialogues": 64,
    "sans_duree": 1,
    "voix": [
      "female_0",
      "male_1",
      "narrator"
    ]
  },
  "audio": {
    "duree_s": 977.5,
    "hz": 24000,
    "canaux": 1,
    "pic": 29204,
    "rms": 3159.8,
    "silencieux": false,
    "fichier": "C:\\Users\\romai\\Documents\\ScriptVox-nuit-audio\\en-2-ch8.wav",
    "ratio_temps_reel": 0.03
  },
  "duree_totale_s": 45
}
```

### Pardo Bazán — Cuentos de amor (`es`)

```json
{
  "langue_attendue": "es",
  "livre": "Pardo Bazán — Cuentos de amor",
  "fichier": "es-55514.epub",
  "erreurs": [],
  "book_id": 3,
  "reutilise": true,
  "analyse_etat": "ANALYZED",
  "langue_detectee": "es",
  "langue_correcte": true,
  "chapitres": 47,
  "chapitres_inclus": 44,
  "personnages": 87,
  "personnages_sans_voix": 0,
  "voix_distinctes": 8,
  "exemples_personnages": [
    {
      "nom": "Emilia Pardo Bazán",
      "voix": "female_2"
    },
    {
      "nom": "Marta",
      "voix": "female_0"
    },
    {
      "nom": "El viajero",
      "voix": "male_0"
    },
    {
      "nom": "Trifón Liliosa",
      "voix": "male_0"
    },
    {
      "nom": "Doña Leonor Cardona",
      "voix": "female_2"
    },
    {
      "nom": "Don Ramón Cardona",
      "voix": "male_0"
    }
  ],
  "chapitre_genere": {
    "position": 17,
    "titre": "Así y todo..."
  },
  "generation_etat": "DONE",
  "generation_duree_s": 53,
  "takes": {
    "nombre": 8,
    "duree_totale_s": 533.4,
    "silencieux": 0,
    "illisibles": 0,
    "vides_voulus": 1
  },
  "segments": {
    "total": 8,
    "dialogues": 4,
    "sans_duree": 1,
    "voix": [
      "male_0",
      "narrator"
    ]
  },
  "audio": {
    "duree_s": 535.9,
    "hz": 24000,
    "canaux": 1,
    "pic": 29204,
    "rms": 3258.0,
    "silencieux": false,
    "fichier": "C:\\Users\\romai\\Documents\\ScriptVox-nuit-audio\\es-3-ch17.wav",
    "ratio_temps_reel": 0.1
  },
  "duree_totale_s": 69
}
```

### Kafka — Die Verwandlung (`de`)

```json
{
  "langue_attendue": "de",
  "livre": "Kafka — Die Verwandlung",
  "fichier": "de-22367.epub",
  "erreurs": [],
  "book_id": 6,
  "reutilise": true,
  "analyse_etat": "ANALYZED",
  "langue_detectee": "de",
  "langue_correcte": true,
  "chapitres": 6,
  "chapitres_inclus": 3,
  "personnages": 8,
  "personnages_sans_voix": 0,
  "voix_distinctes": 7,
  "exemples_personnages": [
    {
      "nom": "Gregor Samsa",
      "voix": "male_0"
    },
    {
      "nom": "Mutter",
      "voix": "female_2"
    },
    {
      "nom": "Vater",
      "voix": "male_2"
    },
    {
      "nom": "Prokurist",
      "voix": "male_1"
    },
    {
      "nom": "Schwester",
      "voix": "neutral_0"
    },
    {
      "nom": "Bedienerin",
      "voix": "female_0"
    }
  ],
  "chapitre_genere": {
    "position": 4,
    "titre": "II."
  },
  "generation_etat": "DONE",
  "generation_duree_s": 117,
  "takes": {
    "nombre": 40,
    "duree_totale_s": 2431.5,
    "silencieux": 0,
    "illisibles": 0,
    "vides_voulus": 0
  },
  "segments": {
    "total": 40,
    "dialogues": 20,
    "sans_duree": 0,
    "voix": [
      "female_2",
      "male_0",
      "male_2",
      "narrator",
      "neutral_0"
    ]
  },
  "audio": {
    "duree_s": 2448.2,
    "hz": 24000,
    "canaux": 1,
    "pic": 29204,
    "rms": 3263.1,
    "silencieux": false,
    "fichier": "C:\\Users\\romai\\Documents\\ScriptVox-nuit-audio\\de-6-ch4.wav",
    "ratio_temps_reel": 0.05
  },
  "duree_totale_s": 147
}
```

### Collodi — Pinocchio (`it`)

```json
{
  "langue_attendue": "it",
  "livre": "Collodi — Pinocchio",
  "fichier": "it-52484.epub",
  "erreurs": [],
  "book_id": 7,
  "reutilise": false,
  "analyse_etat": "ANALYZED",
  "analyse_duree_s": 376,
  "analyse_trace": [
    {
      "t": 2,
      "progress": 0,
      "stage": null,
      "msg": null
    },
    {
      "t": 9,
      "progress": 10.0,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 16,
      "progress": 11.389,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 23,
      "progress": 14.167,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 30,
      "progress": 18.333,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 37,
      "progress": 21.111,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 44,
      "progress": 22.5,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 51,
      "progress": 23.889,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 58,
      "progress": 25.278,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 73,
      "progress": 26.667,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 80,
      "progress": 28.056,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 87,
      "progress": 30.833,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 94,
      "progress": 32.222,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 108,
      "progress": 33.611,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 115,
      "progress": 35.0,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 122,
      "progress": 37.778,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 129,
      "progress": 39.167,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 136,
      "progress": 40.556,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 143,
      "progress": 41.944,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 150,
      "progress": 43.333,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 164,
      "progress": 46.111,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 185,
      "progress": 47.5,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 192,
      "progress": 48.889,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 214,
      "progress": 50.278,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 242,
      "progress": 51.667,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 249,
      "progress": 53.056,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 270,
      "progress": 54.444,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 291,
      "progress": 55.833,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 319,
      "progress": 57.222,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 333,
      "progress": 58.611,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 369,
      "progress": 60.0,
      "stage": "analysis",
      "msg": null
    },
    {
      "t": 376,
      "progress": 100.0,
      "stage": null,
      "msg": null
    }
  ],
  "langue_detectee": "it",
  "langue_correcte": true,
  "chapitres": 39,
  "chapitres_inclus": 36,
  "personnages": 37,
  "personnages_sans_voix": 0,
  "voix_distinctes": 8,
  "exemples_personnages": [
    {
      "nom": "maestro Ciliegia",
      "voix": "male_2"
    },
    {
      "nom": "piccoli lettori",
      "voix": "neutral_0"
    },
    {
      "nom": "Geppetto",
      "voix": "female_1"
    },
    {
      "nom": "mastro Antonio",
      "voix": "male_0"
    },
    {
      "nom": "Pinocchio",
      "voix": "male_1"
    },
    {
      "nom": "Grillo-parlante",
      "voix": "neutral_0"
    }
  ],
  "chapitre_genere": {
    "position": 14,
    "titre": "XIII. L'osteria del «Gambero Rosso.»"
  },
  "generation_etat": "DONE",
  "generation_duree_s": 25,
  "takes": {
    "nombre": 42,
    "duree_totale_s": 346.5,
    "silencieux": 0,
    "illisibles": 0,
    "vides_voulus": 0
  },
  "segments": {
    "total": 42,
    "dialogues": 30,
    "sans_duree": 0,
    "voix": [
      "male_1",
      "male_2",
      "narrator",
      "neutral_0"
    ]
  },
  "audio": {
    "duree_s": 360.2,
    "hz": 24000,
    "canaux": 1,
    "pic": 29204,
    "rms": 3210.6,
    "silencieux": false,
    "fichier": "C:\\Users\\romai\\Documents\\ScriptVox-nuit-audio\\it-7-ch14.wav",
    "ratio_temps_reel": 0.07
  },
  "duree_totale_s": 414
}
```

## Bugs et points à trancher

- aucun échec détecté

## Diagnostic des échecs du premier passage (2026-09-27, 12:11)

| symptôme | cause | correction |
|---|---|---|
| génération « ANALYZED en 4 s » puis audio 409 (×4) | **script** : il attendait le statut du LIVRE, qui reste ANALYZED pendant la génération d'un chapitre. Les 4 chapitres étaient en réalité générés (DONE) en arrière-plan. | le script attend le statut du CHAPITRE |
| `langue_detectee = null` (×5) | **script** : il lisait `Book.language` juste après l'import, or la langue n'est renseignée qu'à l'analyse (dc:language). Les 5 livres avaient la bonne langue en base. | lecture après l'analyse |
| durées d'analyse gonflées | **script** : `POST /books` lance déjà l'analyse ; le script relançait `POST /analyze` alors que le livre était encore PENDING → une seconde analyse complète s'enfilait derrière la première, et la mesure cumulait les deux. | le script n'appelle plus `/analyze` |
| (révélé par la relance) chapitres en et es FAILED « No audio was received » | **appli** : un segment sans rien à prononcer (`)` chez Carroll, `.......` chez Pardo Bazán) était envoyé à EdgeTTS, qui ne renvoie rien ; un seul segment en échec fait échouer le chapitre. | commit 8b19d12 : silence nul, moteur non appelé. Les 2 takes de durée 0 ci-dessus sont ces segments. |
| de et it : profil français | **appli** : pas de `LanguageProfile`. En allemand (»…«), le motif français inversait dialogue et narration (128/128 répliques fausses sur Kafka) ; voix EdgeTTS françaises. | commit f71a074 : DE_PROFILE, IT_PROFILE, voix de-DE / it-IT, Qwen German/Italian |

## Point d — timeout de l'analyse italienne (5405 s)

Mesures (qwen3:1.7b, Ollama 100 % GPU, `OLLAMA_VULKAN=1`) :

| livre | chapitres inclus | tokens d'entrée | appels LLM | durée 27/09 matin | durée ce soir |
|---|---|---|---|---|---|
| Kafka (de) | 3 | ~31 000 | 3 | 3140 s | **81 s** (et 80 s pour la 2ᵉ analyse enfilée) |
| Pinocchio (it) | 36 | ~66 500 | 36 (1 par chapitre, aucun découpage) | > 5405 s (TIMEOUT) | **376 s** (pas le plus long : 36 s) |

Ce n'est donc ni la taille du livre ni le nombre d'appels : Pinocchio fait 36 appels courts (~1 850 tokens chacun), analysés en ~10 s. Deux causes, la première certaine :

1. **double analyse** (voir plus haut) : le script mesurait deux analyses complètes à la suite ;
2. **débit LLM ~15 à 40 fois plus lent ce matin-là** : même avec deux analyses, 5405 s ne s'expliquent pas (2 × 376 s ≈ 750 s ; Kafka : 3140 s contre 2 × 80 s). Même modèle dans le `.env`. Hypothèse la plus probable, non prouvable a posteriori faute de logs : Ollama tournait sur CPU ou partageait le GPU avec le chantier A (qwen3:14b / qwen3:8b), qui a fini sa vérification à 08:18, juste avant le début du chantier B.

Propositions (non implémentées) :
- **appli** : `POST /books/{id}/analyze` refuse aussi un livre PENDING qui a déjà une analyse en file (409), comme il refuse PROCESSING — sinon n'importe quel client (UI comprise, double clic) peut enfiler deux analyses ;
- **appli** : afficher dans Paramètres › Modèles le processeur réel du modèle Ollama chargé (`/api/ps` : `size_vram` / `size`), avec un avertissement si le modèle déborde sur le CPU ;
- **exploitation** : ne jamais lancer une analyse ScriptVox pendant une génération Ollama d'un autre chantier (un travail GPU à la fois) ;
- **script** : consigner `ollama ps` au début de chaque analyse, pour que la prochaine lenteur soit diagnostiquable.
