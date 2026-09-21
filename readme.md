# JARVIS

JARVIS is a Python desktop voice assistant. It combines a live Gemini conversation, an animated desktop interface, microphone and speaker streaming, local memory, computer automation, and a phone command page.

Speak, type, or send a paired phone command. JARVIS sends the conversation to Gemini Live and, when needed, can use local tools for applications, browser work, files, reminders, and configured desktop tasks.

> Keep `config/api_keys.json` private. It contains your local API key and must never be uploaded to GitHub.

## Capabilities

- Real-time voice conversations through Gemini Live.
- Text commands when voice input is inconvenient.
- Holographic, audio-reactive JARVIS desktop interface.
- Desktop, browser, web-search, file, reminder, media, weather, system-monitoring, and developer tools.
- Local facts and session summaries for continuity between conversations.
- Optional wake-word and push-to-talk modes.
- Drop-in extensions from the `plugins/` directory.
- QR pairing for remote text commands from a phone.

## How the application works

```text
Voice, text, or paired phone command
                 |
                 v
           JARVIS desktop app
                 |
                 v
      Gemini Live conversation session
                 |
       +---------+---------+
       |                   |
       v                   v
UI / spoken answer    Local tool request
                            |
                            v
 Browser, files, desktop, reminders, applications, system controls
```

The application runs its interface and its live assistant worker together. The worker streams microphone audio to Gemini Live, receives voice and text responses, and updates the UI. Tools are automatically discovered from `actions/*.py`; optional plugins are loaded from `plugins/*.py`.

Read confirmation prompts carefully. This project can control parts of your computer, so do not approve an action you do not understand and never share a remote pairing link.

## What you need

- Python 3.11, 3.12, or 3.13 recommended. Later releases may work but are not fully tested.
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
- A microphone and speaker/headphones for voice conversations.
- Internet access for Gemini Live, online search, cloud voice services, and browser automation.
- Windows, macOS, or Linux. Windows provides the widest desktop-control support.

The installer also downloads the browsers needed by Playwright. That step can take a few minutes on a slow connection.

## Download and install

### Clone with Git

```bash
git clone https://github.com/navadeep-hash/1ST-PROJECT-OF-PRINCE-JARVIS-.git
cd 1ST-PROJECT-OF-PRINCE-JARVIS-
python setup.py
python main.py
```

### Download a ZIP

1. Open the repository on GitHub.
2. Choose **Code** → **Download ZIP**.
3. Extract the archive.
4. Open PowerShell or Terminal inside the extracted folder.
5. Run:

```bash
python setup.py
python main.py
```

If Windows uses a different Python version, specify one explicitly:

```powershell
py -3.13 setup.py
py -3.13 main.py
```

## First-time setup

1. Run `python main.py`.
2. Enter your Gemini API key in the welcome screen and save it.
3. Grant microphone permission if your operating system asks.
4. Wait until JARVIS reports it is online.
5. Speak normally or send a message through the text input.

Your key is stored only on this computer in `config/api_keys.json`. If you accidentally expose it, revoke it in Google AI Studio and generate another key.

## Using the interface

The main window shows JARVIS status, activity, response visuals, and shortcuts to the settings command center.

### Conversation controls

- **Voice:** speak while JARVIS is listening.
- **Text:** type a message and send it to the live conversation.
- **Interrupt:** stop an answer so you can speak again.
- **Mute:** pause microphone input.
- **Wake / sleep:** available when wake-word mode is enabled.

### Settings command center

| Section | Available controls |
| --- | --- |
| Identity | Assistant name, your name, voice, color theme, and avatar style |
| Audio | Microphone, speaker, push-to-talk, and device routing |
| Core | Gemini API key, wake-word options, and live-session preferences |
| Memory | Local facts, saved sessions, and memory management |
| Plugins | Extensions, enable/disable switches, and plugin credentials |
| Remote Access | QR pairing key and phone dashboard |
| Security | Available PIN, voice-lock, and optional face-authentication settings |

All settings are local. If your microphone or speaker is changed outside the app, reopen the audio selection page and choose the correct device.

## Things JARVIS can help with

Actual results depend on the operating system, installed applications, browser state, permissions, and enabled extensions. Typical requests include:

- Open, close, or find applications.
- Search the web, compare products, research topics, and check weather.
- Open and control supported browser sessions.
- Take screenshots, inspect the screen, type text, and perform desktop actions.
- Read, summarize, and work with supported documents.
- Create and manage reminders.
- Monitor CPU, RAM, GPU, and system information.
- Search or control YouTube.
- Find flights, assist with code, and help with game updates.
- Draft or send supported messages after the related service is configured.

The files in `actions/` provide the bundled skills. Every action describes its own inputs and handler, so new capabilities can be added without placing all logic in `main.py`.

## Wake word and push-to-talk

Wake-word activation is optional. Enable it from Settings when you want hands-free activation; the required local wake-word package is downloaded only when you select the feature.

Push-to-talk is useful in noisy spaces. JARVIS listens only while you hold the configured key, and the same key can deliberately wake it when wake-word sleep is enabled.

## Memory and privacy

| Local path | Purpose |
| --- | --- |
| `config/api_keys.json` | API key, preferences, selected devices, and extension settings |
| `memory/long_term.json` | Long-term facts and memory, created when needed |
| `plugins/` | Optional extensions |

Voice conversation data is sent to Gemini while a live session is connected. The project does not automatically publish your local files, settings, or memory. Never commit keys, tokens, browser sessions, or personal data.

## Remote control from a phone

Remote Access creates a six-digit key that expires after ten minutes. Scan the QR code, then confirm the pairing key on the phone page. A paired phone can send text commands to the running JARVIS session.

For a phone on the same Wi-Fi, a local network URL can be used. To connect through mobile data or a different Wi-Fi network, install [Cloudflare Tunnel (`cloudflared`)](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/). Restart JARVIS, wait briefly, and generate a new key. A URL containing `trycloudflare.com` is the public HTTPS link.

Do not share the QR code or key. A person with a valid pairing link can send commands to your active assistant until the key expires.

## Plugins

Place a plugin Python file inside `plugins/`. At startup, JARVIS validates it and lists it in Settings. A plugin may add a tool, its own configuration form, connection values, or a service/device integration.

If an extension is missing or has an import error, JARVIS continues running and reports the issue. Face authentication is optional and automatically disables itself when its files are not installed.

## Project structure

```text
main.py              Startup, audio flow, Gemini session, and tool routing
ui.py                PyQt interface, visuals, overlays, and settings hub
actions/             Built-in desktop, browser, file, media, and system tools
core/                Loaders, audio devices, wake word, avatar, and safety helpers
memory/              Configuration and local memory
dashboard/           FastAPI phone dashboard and QR pairing server
plugins/             Optional extensions
requirements.txt     Python dependencies
setup.py             Dependency and Playwright installer
```

## Troubleshooting

### Missing Python module

Use the same interpreter for installation and launch:

```bash
python setup.py
```

### API key error

Open Settings, enter a valid Gemini key, save it, and allow JARVIS to reconnect. Also confirm that the computer has internet access.

### No microphone or speaker audio

Open **Settings → Audio**, select the intended input/output device, and check your operating system's microphone permission.

### Browser automation is unavailable

```bash
python -m playwright install chromium firefox
```

### The QR link does not open

Restart JARVIS, wait a few seconds, and create a fresh key. An `http://192.168...` link only works on the same Wi-Fi. An `https://...trycloudflare.com` link works from another network when Cloudflare Tunnel is installed and running.

### An optional capability is unavailable

Some features require an extra package, a configured account, an installed desktop app, an operating-system tool, or a plugin. Check the relevant settings page and terminal output for the missing requirement.

## Contributing

Keep sensitive data out of commits, test changes before sharing them, and keep new actions or plugins isolated from the core application.

## Contact

For questions, suggestions, or issues with JARVIS, contact the project owner on Instagram:

[Instagram — @_.prince_nx16._](https://www.instagram.com/_.prince_nx16._?stkn=MXRxdmEyNG10Mno3NQ==)
