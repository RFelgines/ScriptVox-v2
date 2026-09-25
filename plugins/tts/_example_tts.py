"""Template d'un plugin TTS. Copier ce fichier en `mon_moteur.py` (sans le `_`) puis l'adapter.

Contrat minimal :
    PROVIDER_NAME  nom affiché dans Paramètres, [a-z0-9_]+ (ne doit pas être un nom officiel)
    create(settings, options, language=None) -> provider

`options` = réglages à chaud de Paramètres (model, base_url, locale…) ; `language` = langue du livre
(« fr », « en-US »…) ou None. Le provider hérite de BaseTTSProvider et implémente `synthesise`.

`synthesise` peut renvoyer du WAV, MP3, FLAC ou OGG, à N'IMPORTE QUELLE fréquence et en mono ou
stéréo : le pipeline convertit tout en WAV mono 16 bits 24 kHz (voir app/services/audio/format.py).
Les identifiants de voix logiques sont : narrator, male_0..2, female_0..2, neutral_0..1, plus les
voix clonées créées par l'utilisateur (dans ce cas `reference_audio_path` est renseigné).
"""
from app.core.exceptions import TTSError
from app.services.audio.format import silence_wav
from app.services.tts.base import BaseTTSProvider

PROVIDER_NAME = "mon_moteur"  # <- à changer
DESCRIPTION = "Exemple de moteur TTS (silence)"  # affiché dans Paramètres

# Table des voix : identifiant logique ScriptVox -> voix de VOTRE moteur.
VOICES = {
    "narrator": "voix_narrateur",
    "male_0": "voix_homme_1", "male_1": "voix_homme_2", "male_2": "voix_homme_3",
    "female_0": "voix_femme_1", "female_1": "voix_femme_2", "female_2": "voix_femme_3",
    "neutral_0": "voix_neutre_1", "neutral_1": "voix_neutre_2",
}


def list_models(settings, options):
    """Facultatif : suggestions affichées dans la liste « Modèle » de Paramètres."""
    return ["modele-a", "modele-b"]


class MonMoteur(BaseTTSProvider):
    # Réglages facultatifs (valeurs par défaut de BaseTTSProvider) :
    supports_concurrency = 1  # synthèses simultanées (1 = séquentiel, ex. GPU local)
    max_chars = 500           # au-delà, le texte est découpé aux fins de phrase
    keep_loaded = False       # True = le worker garde l'instance (modèle chargé) entre chapitres

    def __init__(self, model: str, language: str | None):
        self.model = model
        self.language = language
        # Charger votre modèle ICI si keep_loaded=True, ou paresseusement au 1er appel.

    async def synthesise(self, text, voice_id, emotion=None, reference_audio_path=None):
        voice = VOICES.get(voice_id)
        if voice is None and reference_audio_path is None:
            raise TTSError(f"{PROVIDER_NAME}:{voice_id}", ValueError(f"voix inconnue {voice_id!r}"))
        # ... appeler votre moteur ici (dans un thread si c'est bloquant :
        #     loop = asyncio.get_running_loop(); await loop.run_in_executor(None, ...)) ...
        return silence_wav(500)  # renvoyer des octets audio

    def unload(self) -> None:
        """Facultatif : libérer la VRAM (appelé sur demande, à l'inactivité, avant une analyse LLM)."""


def create(settings, options, language=None):
    return MonMoteur(options.get("model", "modele-a"), language)
