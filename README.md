# Video Copy Tool

Ein Web-Tool, das Videos von YouTube, TikTok und anderen Plattformen analysiert, transkribiert und rekonstruiert.

## Features

- **Video-Download**: Unterstützt YouTube, TikTok und hunderte weitere Plattformen (via yt-dlp)
- **Transkription**: Erkennt und transkribiert jedes gesprochene Wort (via OpenAI Whisper)
- **Szenen-Extraktion**: Extrahiert automatisch Screenshots/Szenen aus dem Video
- **Rekonstruktion**: Baut das Video aus den Szenen neu zusammen
- **Untertitel**: Optionales Einbrennen von Untertiteln in verschiedenen Stilen
- **Kein Clip-Limit**: Erstellt vollständige Videos, nicht nur kurze Clips

## Voraussetzungen

- Python 3.9+
- FFmpeg
- Ausreichend Speicherplatz für Video-Downloads

## Installation

```bash
# Setup-Script ausführen
chmod +x setup.sh
./setup.sh
```

### Manuelle Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Starten

```bash
source venv/bin/activate
python app.py
```

Dann öffne **http://localhost:5000** im Browser.

## Nutzung

1. **Video-Link einfügen** – YouTube, TikTok oder andere URL einfügen
2. **Transkription** – Whisper-Modell wählen und transkribieren lassen
3. **Szenen extrahieren** – Zeitintervall oder Szenenwechsel-Erkennung nutzen
4. **Video erstellen** – Szenen auswählen, optional Untertitel aktivieren, fertiges Video herunterladen

## Whisper-Modelle

| Modell | Geschwindigkeit | Genauigkeit | VRAM |
|--------|----------------|-------------|------|
| tiny   | Sehr schnell   | Niedrig     | ~1GB |
| base   | Schnell        | Mittel      | ~1GB |
| small  | Mittel         | Gut         | ~2GB |
| medium | Langsam        | Sehr gut    | ~5GB |
| large  | Sehr langsam   | Beste       | ~10GB|

## Technologie-Stack

- **Backend**: Python, Flask
- **Video-Download**: yt-dlp
- **Transkription**: OpenAI Whisper
- **Video-Processing**: FFmpeg
- **Frontend**: HTML, CSS, JavaScript
