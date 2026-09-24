# JARVIS

JARVIS is a Python desktop voice assistant. It combines a live Gemini conversation, an animated desktop interface, microphone and speaker streaming, local memory, computer automation, and a phone command page.

Speak, type, or send a paired phone command. JARVIS sends the conversation to Gemini Live and, when needed, can use local tools for applications, browser work, files, reminders, and configured desktop tasks.

> Keep `config/api_keys.json` private. It contains your local API key and must never be uploaded to GitHub.

## Capabilities

- Real-time voice conversations and typed commands through Gemini Live.
- An audio-reactive desktop HUD with avatar, status, activity log, and configurable appearance.
- Optional wake word, wake/sleep, mute, interrupt, and push-to-talk controls.
- 21 discoverable built-in actions, eight assistant-integrated tools, and two included plugins.
- Local personal memory, session summaries, reminders, and background topic monitoring.
- Computer, browser, file, document, code, presentation, media, weather, flight, and location tools.
- Optional startup PIN, face authentication, voice-lock settings, and QR-paired phone commands.

Actions and plugins are discovered from their folders at startup. Their availability depends on the operating system, installed packages/apps, permissions, network access, API configuration, and plugin settings. The capabilities below describe what the code provides; they do not guarantee that an external service or device is currently reachable.

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

## Built-in skills

The following actions are registered from `actions/`:

| Skill | What it does |
| --- | --- |
| App downloads | Searches Microsoft Store and guides a confirmed, safe install; external downloads are not automatically installed. |
| Browser control | Opens websites and controls supported browser sessions: navigation, clicks, forms, typing, and screenshots. |
| Code helper | Writes, explains, edits, runs, and debugs code. |
| Computer control | Sends clicks, typing, hotkeys, scrolling, cursor movement, and screen inspection to the desktop. |
| Computer settings | Controls supported windows, tabs, zoom, screenshots, keyboard input, and selected system settings. Some consequential actions require HUD confirmation. |
| Sketch | Creates an SVG illustration or diagram from a description and opens a preview. |
| Desktop control | Changes wallpaper and manages or inspects desktop items. |
| Developer agent | Builds multi-file projects and websites, runs them, and attempts to resolve build/runtime errors. |
| File controller | Creates, reads, searches, writes, copies, moves, renames, deletes, and inspects files and folders. |
| File processor | Processes supplied files, including supported images, PDFs, documents, spreadsheets, code, audio, video, and archives. |
| Flight finder | Searches Google Flights for route options. |
| Game updater | Lists, installs, updates, or checks supported Steam and Epic games. |
| Location control | Shows device location and weather on the JARVIS globe; can turn on live ADS-B aircraft and AIS ship layers, select a contact to follow its position/trail, navigate to Earth places, or open the solar-system viewer. Location permission can be set to ask, always allow, or always block in Settings → Privacy & Permissions. AIS ship tracking requires an AISStream key. |
| Open app | Opens a requested app or website. YouTube playback uses the dedicated YouTube action. |
| Reminder | Schedules a timed reminder using the operating system's scheduler. |
| Feedback saver | Saves a JARVIS bug report or feedback locally when explicitly requested. |
| Send message | Starts a supported chat and sends user-directed messages, with confirmation for sensitive messages. It does not read/monitor incoming inboxes or answer WhatsApp calls. |
| System information | Reads available PC identity, OS, battery, CPU, memory, storage, and graphics details when asked. |
| Weather | Retrieves a weather report from the configured online source. |
| Web search | Searches current web information, news, research topics, prices, and comparisons. |
| World watch | Spoken/data workflows: aircraft lookup by location or callsign, weather/wind, USGS earthquakes, NOAA cyclones, scheduled launches, CelesTrak satellite pass times/catalog (Skyfield), NASA FIRMS fires (MAP_KEY required), OSRM driving/walking/cycling directions, OpenStreetMap mapped infrastructure/camera/ALPR locations, Radio Browser stations, and sourced area briefings. Public coverage and update delays vary. AIS ship tracking requires an AISStream key; live traffic speed, transit, and bikeshare feeds are not configured. |
| YouTube | Searches and plays videos/music, and supports available info, trending, and summary requests. |

## Assistant-integrated tools and background services

These tools are implemented in `main.py` because they share the live conversation, camera, memory, or process lifecycle:

| Tool | What it does |
| --- | --- |
| Live system status | Reports available CPU, RAM, GPU, temperature, uptime, and process metrics. |
| Screen/camera vision | Captures the requested screen or webcam image for Gemini to analyze. |
| Close camera | Stops the assistant's active camera view. |
| Background topic monitor | Adds, lists, or removes topics for periodic web checks and alerts. |
| Shutdown JARVIS | Closes the assistant when explicitly requested. |
| Save memory / recall memory | Stores and retrieves local personal facts and preferences. |
| Undo | Reverses supported recent changes made by JARVIS. |

Background services also include optional wake-word sleep/wake, system alerts, session summaries, and proactive checks. These depend on their settings and the required services/sensors being available.

## Included plugins

Plugins are shown in Settings and can be enabled or disabled there. The repository currently includes:

| Plugin | What it does | Requirements |
| --- | --- | --- |
| PowerPoint creator | Drafts a slide outline from a topic, builds a widescreen `.pptx`, and attempts to add relevant openly licensed Wikimedia Commons images and credits. | Gemini API access; `python-pptx`; internet for image lookup. |
| Hand gestures | Optional system-wide cursor, click, drag/drop, zoom, scroll, media, screenshot, speech-interrupt, minimize, and confirmation gestures. | OpenCV, MediaPipe, PyAutoGUI, the hand-landmarker model, and a working camera. Start and stop it explicitly. |

Generated presentations are saved under `downloads/presentations/`. Face authentication and voice-lock are settings/security features rather than entries in the plugin list; face support requires its optional recognition dependencies and an enrolled face. A local Master PIN is the fallback unlock method.

The files in `actions/` and `plugins/` contain the tool implementations and their descriptions. A capability may still fail when its API, device, app, permission, account, or external service is unavailable; check the action result and console log before reporting success.

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
