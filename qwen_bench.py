import asyncio, time, wave, io, statistics
from app.config import get_settings
from app.services.tts.factory import get_tts_provider
s = get_settings(); p = get_tts_provider(s, language="en")

def analyse(wav_bytes, label):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        n, sr = w.getnframes(), w.getframerate()
        raw = w.readframes(n)
    import array
    a = array.array("h"); a.frombytes(raw)
    peak = max(abs(x) for x in a) if a else 0
    rms = (sum(x*x for x in a)/len(a))**0.5 if a else 0
    print(f"  {label}: {n/sr:.2f}s | pic {peak}/32767 | RMS {rms:.0f} | {'SILENCE !!' if peak < 100 else 'signal audio present'}")

t=time.time(); w1=asyncio.run(p.synthesise("Alice was beginning to get very tired of sitting by her sister on the bank.","narrator",emotion="curious")); c=time.time()-t
print(f"synthese 1 (a froid) : {c:.1f}s"); analyse(w1,"audio 1")
t=time.time(); w2=asyncio.run(p.synthesise("So she was considering in her own mind whether the pleasure of making a daisy-chain would be worth the trouble.","female_0",emotion="dreamy")); h=time.time()-t
print(f"synthese 2 (a chaud) : {h:.1f}s"); analyse(w2,"audio 2")
import wave as _w, io as _io
with _w.open(_io.BytesIO(w2)) as ww: dur = ww.getnframes()/ww.getframerate()
print(f"\nRATIO A CHAUD : {h/dur:.1f}x le temps reel")
