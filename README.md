
# 🛡️ PulseGuard AI

**Real-time log anomaly detection & root-cause assistant.** Paste server logs, watch anomalies light up, see incidents cluster, and get AI-powered root-cause explanations—all in one dashboard.

[🚀 Live Demo](https://your-frontend-url) · [📖 API Docs](https://your-backend-url.onrender.com/docs)

![PulseGuard AI Dashboard](./docs/screenshot.png)

## The Problem

Every company runs logs. When something breaks, on-call engineers drown in thousands of error lines, manually correlating timestamps and services. PulseGuard AI automates the first 5 minutes of incident response: it detects anomalies in real time, groups related failures into incidents, explains the likely root cause in plain English, and predicts which service will fail next.

## How It Works

Raw Logs → Drain3 Parsing → Isolation Forest Anomaly Detection → DBSCAN Incident Clustering  
↓  
Groq LLM Root-Cause Explanation  
↓  
XGBoost Failure Prediction

1. **Log Parsing** — Drain3 converts raw log lines into templates (`Payment failed reason=<*>`).
2. **Anomaly Detection** — Isolation Forest flags unusual time windows using windowed features such as error rate, template entropy, and service diversity.
3. **Incident Clustering** — `sentence-transformers` embeds anomalous messages; DBSCAN groups semantically similar failures into incidents.
4. **Root-Cause Explanation** — Groq's openai/gpt-oss-120b generates a plain-English hypothesis for each incident.
5. **Failure Prediction** — XGBoost predicts per-service failure risk for the next 3 minutes.

## Tech Stack

- **Backend:** FastAPI, SQLModel (SQLite), Drain3, scikit-learn, XGBoost, sentence-transformers
- **LLM:** Groq (`openai/gpt-oss-120b`) via OpenAI-compatible SDK
- **Frontend:** Reflex (pure Python, compiles to React), Plotly
- **Deployment:** Render (backend) + Reflex Cloud (frontend)

## Run It Locally

```bash
git clone https://github.com/your-username/pulseguard-ai.git
cd pulseguard-ai

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Add your Groq API key to .env
echo "GROQ_API_KEY=your_key_here" >> .env

# Terminal 1: Start the backend
uvicorn backend.app.main:app --reload --port 8000

# Terminal 2: Start the frontend
cd frontend/pulseguard
reflex run
```

Open http://localhost:3000, click **"Play Live Demo"**, and watch the pipeline run.

## What I'd Do Next

- Add SQLite persistence for incident history across sessions.
- Support real-time log tailing via WebSocket instead of paste-and-analyze.
- Fine-tune the failure predictor on real labeled incident data instead of synthetic proxies.
- Add alerting integrations (Slack, PagerDuty) for critical incidents.

## License

MIT
