from abc import ABC, abstractmethod


class BaseTTSProvider(ABC):
    """Contrat d'un moteur TTS.

    Seule `synthesise` est obligatoire. Elle peut renvoyer du WAV, MP3, FLAC ou OGG, à
    n'importe quelle fréquence : le pipeline normalise la sortie
    (app.services.audio.format.normalize_audio). Les attributs ci-dessous sont facultatifs :
    un plugin (voir docs/PLUGINS.md) n'a qu'à surcharger ceux dont il a besoin.
    """

    #: Sait synthétiser à partir d'un échantillon (reference_audio_path) : voix clonées de la
    #: bibliothèque et voix conçues par personnage. Un moteur sans clonage reçoit à la place
    #: une voix du catalogue du même genre (app.services.audio.chapter).
    supports_cloning: bool = False
    #: Nombre de synthèses simultanées tolérées (1 = séquentiel, ex. GPU local).
    supports_concurrency: int = 1
    #: Longueur max (caractères) d'un texte envoyé en un seul appel ; au-delà, le pipeline
    #: découpe aux fins de phrase et concatène (TTS-5).
    max_chars: int = 500
    #: True = le worker garde l'instance (modèle chargé) d'un chapitre à l'autre au lieu
    #: de la recréer ; `unload()` est alors appelé quand la mémoire doit être libérée.
    keep_loaded: bool = False

    @abstractmethod
    async def synthesise(
        self, text: str, voice_id: str,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
    ) -> bytes: ...

    def unload(self) -> None:
        """Libère la mémoire (VRAM) tenue par le modèle. No-op par défaut."""
        return None
