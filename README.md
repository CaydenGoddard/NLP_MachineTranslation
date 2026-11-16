# NLP_MachineTranslation

A Python tool that sends the same text to several machine translation (MT) services, shows their outputs side by side, and helps you rate each one for **adequacy** (is the meaning preserved?) and **fluency** (does it sound natural?). It then produces a report on which service did best and where each one struggled.

## Features

- **Multiple real translation APIs:** DeepL, Google Cloud Translation, Microsoft Azure Translator, and MyMemory (free, no key). Any service with a key in `.env` is used automatically.
- **Side-by-side comparison:** source sentence, optional reference translation, and every service's output, plus a rough similarity score against the reference.
- **15 test cases** (`test_cases.json`) covering simple and long sentences, ambiguity, idioms, pronouns and gender, medical and technical vocabulary, word order, and negation. They use English→Spanish, English→German, English→Japanese, Hungarian→English, and Turkish→English.
- **Built-in rating workflow:** rate every translation 1–5 for adequacy and fluency and tag error categories right in the terminal. Progress saves after each rating.
- **Automatic report** (`results/report.md`): average scores per service, the best service per test category, error counts, and every flagged translation.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Command-line interface: single translation, test runner, rating, report |
| `translator.py` | One class per translation API, all sharing the same `translate()` interface |
| `test_cases.json` | 15 test cases with reference translations and what each one tests |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for API keys (copy to `.env`) |
| `results/` | Created when you run the tool: raw translations, rating sheet, report |

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env      # Mac/Linux: cp .env.example .env
```

Then open `.env` and add keys for at least two services:

- **DeepL:** sign up for *DeepL API Free* at deepl.com/pro-api, then copy the key from your account page. Free keys end in `:fx`.
- **Google:** in the Google Cloud Console, enable the *Cloud Translation API*, then create an API key under *APIs & Services → Credentials*.
- **Microsoft (optional):** create a *Translator* resource in the Azure portal and copy its key and region.
- **MyMemory (optional):** no key needed. It's on by default.

`.env` is listed in `.gitignore`, so your keys are never pushed to GitHub.

## Usage

```bash
# Translate one sentence with every configured service
python main.py --text "It's raining cats and dogs." --source en --target es

# Interactive mode
python main.py

# 1) Run all test cases -> results/translations_*.json and results/ratings.csv
python main.py --tests test_cases.json

# 2) Rate each translation (adequacy, fluency, error categories, notes)
python main.py --rate results/ratings.csv

# 3) Generate the summary report -> results/report.md
python main.py --report results/ratings.csv
```

## Evaluation method

Each translation is rated by a human on a 1–5 scale:

| Score | Adequacy (meaning) | Fluency (naturalness) |
|---|---|---|
| 1 – poor | Meaning lost or wrong | Ungrammatical / unreadable |
| 2 – weak | Major meaning errors | Very awkward |
| 3 – acceptable | Main idea kept, some errors | Understandable but unnatural |
| 4 – good | Minor nuance lost | Mostly natural |
| 5 – excellent | Meaning fully preserved | Reads like a native speaker wrote it |

Error categories: incorrect meaning, awkward phrasing, missing information, incorrect pronoun handling, idiom failure, word order problem, bias or stereotype issue, and wrong lexical choice.

The reference similarity percentage is only a quick signal. A translation can be fully correct but worded differently from the reference, so the human ratings are the real evaluation.

## Adding a new service

Subclass `Translator` in `translator.py`, implement `is_configured()` and `translate()`, then add the class to `ALL_TRANSLATORS`.
