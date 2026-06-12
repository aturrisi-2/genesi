#!/usr/bin/env python3
"""
Test autonomo delle 3 skill sensoriali (immagini, video, audio).
Chiama direttamente la pipeline universale — nessun messaggio reale inviato.
"""
import asyncio, os, subprocess, sys, glob, tempfile
sys.path.insert(0, '/opt/genesi')
from dotenv import load_dotenv
load_dotenv('/opt/genesi/.env'); load_dotenv('/etc/genesi.env')

RESULTS = []
def check(name, ok, detail=''):
    RESULTS.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}  {detail[:140]}")

async def main():
    SESSION = 'sensory_test_session'

    # ════ 1. IMMAGINE (baseline + biometria) ════
    face_img = sorted(glob.glob('data/faces/alfio_*.jpg'), key=os.path.getsize)[-1]
    with open(face_img, 'rb') as f:
        img_bytes = f.read()
    from core.message_pipeline import process_incoming_photo
    pres = await process_incoming_photo(SESSION, SESSION, img_bytes, 'test')
    p_analysis = pres.get('analysis', '')
    check('IMG analisi non vuota', len(p_analysis) > 20, f'len={len(p_analysis)}')
    check('IMG riconosce Alfio', 'alfio' in p_analysis.lower(), p_analysis[:120])

    # ════ 2. VIDEO (frame + vision + biometria) ════
    vid_path = tempfile.mktemp(suffix='.mp4')
    subprocess.run(['ffmpeg', '-y', '-loop', '1', '-i', face_img, '-t', '3',
                    '-pix_fmt', 'yuv420p', vid_path],
                   capture_output=True, timeout=60)
    check('VIDEO file di test creato', os.path.getsize(vid_path) > 1000)
    with open(vid_path, 'rb') as f:
        vid_bytes = f.read()
    from core.message_pipeline import process_incoming_video
    vres = await process_incoming_video(SESSION, SESSION, vid_bytes, 'test')
    v_analysis = vres.get('analysis', '')
    check('VIDEO analisi non vuota', len(v_analysis) > 20, f'len={len(v_analysis)}')
    _names = ('alfio','sandra','rita','zoe','mariella','iolanda','katia')
    check('VIDEO biometria riconosce persone note', any(n in v_analysis.lower() for n in _names), v_analysis[:140])
    os.unlink(vid_path)

    # ════ 3. AUDIO ════
    from core.audio_analysis_service import analyze_audio
    def piper_speech(testo):
        import subprocess, tempfile as tf
        out = tf.mktemp(suffix='.wav')
        subprocess.run(['/opt/piper/piper/piper', '--model',
                        '/opt/piper/voices/it_IT-paola-medium.onnx',
                        '--output_file', out],
                       input=testo.encode(), capture_output=True, timeout=60)
        data = open(out, 'rb').read()
        os.unlink(out)
        return data

    # 3a. Parlato italiano (TTS locale Piper)
    speech_bytes = piper_speech('Ciao Genesi, domani andiamo tutti al mare a Catania con i bambini.')
    ares = await analyze_audio(speech_bytes, 'audio/wav')
    tr = (ares.get('transcription') or '').lower()
    check('AUDIO parlato IT: kind=speech', ares.get('kind') == 'speech', f"kind={ares.get('kind')}")
    check('AUDIO parlato IT: trascrizione corretta', 'mare' in tr and 'catania' in tr, tr[:120])

    # 3b. Parlato inglese (traduzione)
    en_bytes = piper_speech('Hello Genesi! Tomorrow we will go to the beach with the whole family.')
    ares_en = await analyze_audio(en_bytes, 'audio/wav')
    tr_en = (ares_en.get('transcription') or '').lower()
    trad = (ares_en.get('translation_it') or '').lower()
    desc_en = (ares_en.get('description') or '').lower()
    check('AUDIO parlato EN: trascritto', 'beach' in tr_en or 'spiaggia' in (tr_en+trad), tr_en[:100])
    check('AUDIO parlato EN: tradotto/descritto IT',
          'spiaggia' in trad or 'famiglia' in trad or len(desc_en) > 10,
          f'trad={trad[:80]} desc={desc_en[:60]}')

    # 3c. Suono puro (tono sintetico — non parlato)
    snd_path = tempfile.mktemp(suffix='.wav')
    subprocess.run(['ffmpeg', '-y', '-f', 'lavfi',
                    '-i', 'sine=frequency=440:duration=3', snd_path],
                   capture_output=True, timeout=30)
    with open(snd_path, 'rb') as f:
        snd_bytes = f.read()
    ares_snd = await analyze_audio(snd_bytes, 'audio/wav')
    desc_snd = ares_snd.get('description') or ''
    check('AUDIO suono puro: descritto senza crash',
          ares_snd.get('kind') in ('sound', 'music', 'mixed', 'speech', 'unknown') and len(desc_snd) > 5,
          f"kind={ares_snd.get('kind')} desc={desc_snd[:100]}")
    check('AUDIO suono puro: NON spacciato per parlato sensato',
          not (ares_snd.get('kind') == 'speech' and ares_snd.get('transcription')),
          f"trans={(ares_snd.get('transcription') or '')[:60]}")
    os.unlink(snd_path)

    # ════ Pipeline audio end-to-end ════
    from core.message_pipeline import process_incoming_audio
    pa = await process_incoming_audio(SESSION, SESSION, speech_bytes, 'test', 'audio/wav')
    check('PIPELINE audio: analysis costruita', len(pa.get('analysis', '')) > 10,
          pa.get('analysis', '')[:100])

    print()
    ok = sum(1 for _, o, _ in RESULTS if o)
    print(f'═══ TOTALE: {ok}/{len(RESULTS)} ═══')
    return 0 if ok == len(RESULTS) else 1

sys.exit(asyncio.run(main()))
