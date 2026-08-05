# talk-to-agent

Agent conversationnel vocal temps réel pour la conduite d'entretiens de recrutement.
Le navigateur capte le micro, l'audio transite en **WebRTC** vers un serveur **FastAPI**,
qui le relaie à l'API **Gemini Live** (audio natif) et renvoie la voix de l'agent au client.

## Architecture

```
Navigateur (WebRTC)  ──audio PCM──▶  FastAPI + fastrtc  ──▶  Gemini Live API
   script.js                          GeminiHandler            (audio + transcription)
   index.html                         agent.py
        ▲                                                            │
        └──────────────────── audio 24 kHz de l'agent ───────────────┘
```

| Élément | Rôle |
|---|---|
| `src/app/agent.py` | Serveur FastAPI, handler `fastrtc`, connexion à Gemini Live |
| `src/template/index.html` | Page de l'application (sélection de la voix, bouton d'enregistrement) |
| `src/static/script/script.js` | Négociation WebRTC, visualisation audio, mute |
| `src/static/css/styles.css` | Feuille de style |
| `src/static/prompt/*.txt` | Prompts système des deux workflows d'entretien (A et B) |
| `config.ini` | Chemins vers les fichiers de prompt |

## Prérequis

- Python **3.11**
- Une clé API Google AI Studio : <https://aistudio.google.com/apikey>
- Un certificat TLS (auto-signé suffit) : WebRTC/`getUserMedia` exige un contexte sécurisé

## Installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

### Certificat TLS local

Le dossier `ssl/` est **volontairement exclu du dépôt**. Générez le vôtre :

```bash
mkdir -p ssl
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout ssl/app.key -out ssl/app.pem -days 365 \
  -subj "/CN=localhost"
```

### Configuration

```bash
cp .env.example .env
```

puis renseignez les valeurs.

| Variable | Défaut | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Clé API Google AI Studio |
| `APP_PEM` | `ssl/app.pem` | Certificat TLS (chemin relatif à la racine du projet) |
| `APP_KEY` | `ssl/app.key` | Clé privée TLS |
| `APP_HOST` | `0.0.0.0` | Adresse d'écoute |
| `APP_PORT` | `7860` | Port d'écoute |
| `RTC_CONFIGURATION` | — | Configuration ICE/STUN (JSON), optionnelle en local |

## Lancement

```bash
python src/app/agent.py
```

Les chemins (`config.ini`, prompts, `.env`, certificats) sont résolus par rapport à la
racine du projet : le script peut être lancé depuis n'importe quel répertoire.

L'application écoute sur <https://localhost:7860>. Le certificat étant auto-signé, le
navigateur affichera un avertissement à accepter.

> Si `APP_PEM`/`APP_KEY` sont absents, le serveur démarre en **HTTP** et affiche un
> avertissement : le micro ne sera alors accessible que via `localhost`.

## Choix du workflow d'entretien

`config.ini` déclare deux prompts (`PROMPT_INTERVIEWER_A` et `PROMPT_INTERVIEWER_B`).
Seul le prompt **A** est chargé aujourd'hui (`agent.py`) ; le basculement vers B se fait
en modifiant la clé lue dans le code.

## Voix disponibles

`Zephyr`, `Charon`, `Kore`, `Autonoe`, `Alnilam` — sélectionnables dans l'interface.
La langue de synthèse est fixée à `fr-FR`.

## Sécurité

- Aucune clé API ni certificat ne doit être commité : `.env`, `ssl/`, `*.key` et `*.pem`
  sont couverts par le `.gitignore`.
- L'endpoint `/input_hook` n'est pas authentifié : ne l'exposez pas publiquement en l'état.
