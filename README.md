# USask AI Course Planner

A Flask-based web app that summarizes **official University of Saskatchewan course descriptions** using the USask catalogue and OpenAI.

The app:
- Scrapes the **official course catalogue**
- Uses GPT **only on official text**
- Avoids guessing prerequisites or workload
- Caches results for efficiency

---

## 🚀 Features
- Official USask course data scraping
- GPT-powered summaries (3–5 sentences)
- Cache system to reduce repeat scraping
- Clean Flask architecture

---

## 🛠️ Tech Stack
- Python 3
- Flask
- BeautifulSoup4
- Requests
- OpenAI API
- HTML / CSS

---

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/AhmadZahid-12/usask-ai-course-planner.git
cd usask-ai-course-planner