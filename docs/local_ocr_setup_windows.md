# Setup OCR locale su Windows

Questa guida abilita l'OCR offline per gli export WhatsApp con immagini.
Il sistema non usa servizi cloud: legge JPG, PNG e WEBP con PIL e prova a
estrarre testo con Tesseract tramite `pytesseract`.

## Stato atteso

Il progetto usa:

- `pytesseract` come wrapper Python
- il binario Windows `tesseract.exe`
- language pack `ita` e `eng`
- variabile opzionale `TESSERACT_CMD`
- variabile opzionale `TESSERACT_LANG`

Se `pytesseract` e' installato ma `tesseract.exe` non e' raggiungibile, il
report continua a funzionare ma i media vengono solo catalogati.

## Installazione Tesseract

1. Scaricare l'installer Windows di Tesseract OCR.
2. Installarlo in una cartella stabile, preferibilmente:

```powershell
C:\Program Files\Tesseract-OCR\tesseract.exe
```

3. Durante l'installazione includere i language pack:

- `eng`
- `ita`

4. Verificare da PowerShell:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

L'output di `--list-langs` deve includere almeno:

```text
eng
ita
```

## Configurazione tramite PATH

Opzione consigliata: aggiungere la cartella di Tesseract al PATH utente:

```powershell
C:\Program Files\Tesseract-OCR
```

Dopo la modifica chiudere e riaprire PowerShell, poi verificare:

```powershell
where.exe tesseract
tesseract --version
```

## Configurazione tramite variabile TESSERACT_CMD

Se non si vuole modificare il PATH, impostare:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Per renderla persistente a livello utente:

```powershell
[Environment]::SetEnvironmentVariable(
  "TESSERACT_CMD",
  "C:\Program Files\Tesseract-OCR\tesseract.exe",
  "User"
)
```

Riaprire il terminale dopo averla salvata.

## Lingue OCR

Il default del progetto e':

```powershell
ita+eng
```

Si puo' sovrascrivere con:

```powershell
$env:TESSERACT_LANG = "ita+eng"
```

Persistente:

```powershell
[Environment]::SetEnvironmentVariable("TESSERACT_LANG", "ita+eng", "User")
```

## Verifica dal progetto

Dal repository:

```powershell
@'
from core.operational_memory.media_analyzer import dependency_status
print(dependency_status())
'@ | .\venv\Scripts\python.exe -
```

Stato corretto:

```text
'pytesseract_binary': True
'tesseract_ita': True
'tesseract_eng': True
```

## Rigenerare un report OCR

```powershell
.\venv\Scripts\python.exe scripts\run_whatsapp_export_demo.py `
  --input "C:\Users\turrisia\genesi\real_exports\WhatsApp Chat - TAB CEFLA HQ ENEL Roma_media" `
  --project-id tab-cefla-hq-enel-roma-media-ocr `
  --output "C:\Users\turrisia\genesi\output\reports\tab-cefla-hq-enel-roma-media_ocr_daily_report.md" `
  --source-name "gruppo-tab-cefla-hq-enel-roma-media-anonimizzato" `
  --timezone Europe/Rome `
  --report-format markdown
```

## Limiti attuali

- Audio e video vengono ignorati.
- I PDF richiedono un estrattore locale come `pdfplumber`, `pypdf` o PyMuPDF.
- Le immagini troppo grandi vengono saltate per evitare tempi eccessivi.
- Se OCR non produce testo, il media resta nel report ma non crea elementi
  operativi.
