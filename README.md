# RoadsideAI

A local-first roadside-assistance prototype built with Flask and Ollama. It returns a structured, AI-assisted assessment and applies deterministic safety rules for recognized high-risk symptoms. It does not dispatch emergency services or book assistance.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- Ollama for Windows
- The local `gemma4:e2b` model

## Windows setup and run

Open PowerShell or the VS Code terminal in this project directory. Install Python from [python.org](https://www.python.org/downloads/windows/) if `py --version` does not report Python 3.10 or newer.

Create and activate a virtual environment, then install the app dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Install Ollama for Windows from [ollama.com](https://ollama.com/download/windows). Start Ollama from its app; if it is not running as a background service, open a second terminal and run `ollama serve`. In the project terminal, download the model:

```powershell
ollama pull gemma4:e2b
```

Run the automated tests (they mock Ollama and do not require a running model):

```powershell
python -m unittest discover -v
```

Start the Flask app:

```powershell
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Keep the terminal open while using the app and press **Ctrl+C** to stop it. If PowerShell blocks virtual-environment activation, run the activation command from Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

## Configuration

The defaults are `OLLAMA_URL=http://localhost:11434` and `OLLAMA_MODEL=gemma4:e2b`. To override them for a single PowerShell session:

```powershell
$env:OLLAMA_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "gemma4:e2b"
python app.py
```

The model is configured on the server; there is no model selector in the web interface. Ollama requests time out after 50 seconds. Generation is configured for concise answers without model reasoning, with schema-constrained JSON, a 2,048-token context, and a 320-token output cap to keep local CPU inference responsive. On this machine, a warm local test response took about 22 seconds; first use can take longer while the model loads.

## Online hosting

The app currently expects an Ollama server and model to be reachable from the Flask backend. Hosting only the Flask files on a free web host will not provide the model, and a typical free tier cannot run this 4.6 GB model. A public, always-on deployment needs a separate server with Ollama installed and enough RAM/CPU (or a GPU); this generally has a cost. A temporary tunnel can share a computer-hosted app while that computer is on, but should not be exposed publicly without access control.

## Safety

This is a prototype, not a professional diagnostic system. Keyword-based safety checks are conservative and not comprehensive. Follow local emergency guidance and consult qualified professionals. The app does not automatically dispatch emergency services, contact providers, or make bookings.

## Publish to GitHub

Create an empty repository on GitHub, then run these commands from the project directory, replacing the URL with your repository URL:

```powershell
git init
git add .
git commit -m "Build RoadsideAI safety-first dashboard"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/RoadsideAI.git
git push -u origin main
```

Do not commit `.venv`, secrets, API keys, or private data.
