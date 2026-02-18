# Genesi Integration Test Report
Data: 2026-02-18 20:52:33
Durata totale: 89.3s

## Riepilogo
- Test eseguiti: 29
- ✅ Passati: 20
- ❌ Falliti: 9
- ⚠️ Warning: 0

## Risultati per gruppo

### GRUPPO 1 — Intent Classification

### Intent Classification
✅ Message: ciao (1978ms)
✅ Message: come stai (1982ms)
✅ Message: chi sei (1490ms)
❌ Message: che tempo fa a Roma (716ms)
   Note: Log pattern not found: INTENT_CLASSIFIED.*intent=weather
❌ Message: che ore sono (927ms)
   Note: Log pattern not found: INTENT_CLASSIFIED.*intent=date
❌ Message: dimmi una notizia (2240ms)
   Note: Log pattern not found: INTENT_CLASSIFIED.*intent=news
❌ Message: cosa è il machine learning (10602ms)
   Note: Log pattern not found: INTENT_CLASSIFIED.*intent=chat_free
❌ Message: sono triste (5271ms)
   Note: Log pattern not found: INTENT_CLASSIFIED.*intent=emotional

### TTS Routing
❌ Message: ciao (1841ms)
   Note: Log pattern not found: TTS_ROUTING.*provider=openai
❌ Message: come stai (2093ms)
   Note: Log pattern not found: TTS_ROUTING.*provider=openai
❌ Message: che tempo fa a Roma (599ms)
   Note: Log pattern not found: TTS_ROUTING.*provider=edge_tts
❌ Message: dimmi una notizia (2290ms)
   Note: Log pattern not found: TTS_ROUTING.*provider=edge_tts

### Memory and Context
✅ Message: mi chiamo Marco e sono un ingegnere (2657ms)
✅ Message: ricordi come mi chiamo? (751ms)
   Note: Nome ricordato
✅ Message: qual è il mio lavoro? (1575ms)
   Note: Lavoro ricordato

### Profile Detection
✅ Message: adoro il jazz e suono la chitarra (1983ms)

### Evolution Engine
✅ Message: sono molto stressato (2594ms)
✅ Message: non riesco a dormire (1768ms)
✅ Message: tutto mi pesa (1380ms)
✅ Message: mi sento sopraffatto (1667ms)
✅ Message: non so come andare avanti (1930ms)

### Latency
✅ Message: ciao (1586ms)
   Note: Latency: 1586ms (threshold: 3000ms)
✅ Message: che tempo fa a Roma (671ms)
   Note: Latency: 671ms (threshold: 5000ms)

### Fallback and Resilience
✅ Message:  (1554ms)
   Note: messaggio vuoto
✅ Message: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa (1446ms)
   Note: messaggio lunghissimo
✅ Message: 🎸🎵🎶 (2358ms)
   Note: solo emoji
✅ Message: hello how are you (1353ms)
   Note: inglese

### Context Continuity
✅ Message: dimmi un fatto interessante sullo spazio (2546ms)
✅ Message: dimmene un altro (2586ms)
   Note: Context maintained

## Alert
- Message: che tempo fa a Roma: Log pattern not found: INTENT_CLASSIFIED.*intent=weather
- Message: che ore sono: Log pattern not found: INTENT_CLASSIFIED.*intent=date
- Message: dimmi una notizia: Log pattern not found: INTENT_CLASSIFIED.*intent=news
- Message: cosa è il machine learning: Log pattern not found: INTENT_CLASSIFIED.*intent=chat_free
- Message: sono triste: Log pattern not found: INTENT_CLASSIFIED.*intent=emotional
- Message: ciao: Log pattern not found: TTS_ROUTING.*provider=openai
- Message: come stai: Log pattern not found: TTS_ROUTING.*provider=openai
- Message: che tempo fa a Roma: Log pattern not found: TTS_ROUTING.*provider=edge_tts
- Message: dimmi una notizia: Log pattern not found: TTS_ROUTING.*provider=edge_tts

## Performance
- Latenza media: 2153ms
- Latenza max: 10602ms
- Latenza min: 599ms
