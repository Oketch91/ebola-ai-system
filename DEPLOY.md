---
editor_options:
  markdown:
    wrap: 72
output: pdf_document
---

# Putting the system online (about 20 minutes, once)

The dashboard runs on Streamlit Community Cloud; the watcher runs on
GitHub Actions every 3 hours. Both are free for a public repository.
Your laptop is no longer needed.

## Part A: GitHub (code, data and the 3-hourly watcher)

1.  Create a free account at <https://github.com>
2.  Click **New repository**. Name: `ebola-ai-system`. Choose
    **Public**. Click **Create repository**.
3.  On the next page click **uploading an existing file**. Open your
    `ebola_ai_system` folder, select **everything inside it** (including
    the `.github` and `.streamlit` folders) and drag it onto the page.
    Wait for the upload to finish, then click **Commit changes**.
4.  **Settings \> Secrets and variables \> Actions \> New repository
    secret** Name: `ANTHROPIC_API_KEY` Secret: your API key. Click **Add
    secret**.
5.  **Settings \> Actions \> General \> Workflow permissions**: choose
    **Read and write permissions**, **Save**.
6.  **Actions** tab \> **Update outbreak data** \> **Run workflow** \>
    **Run workflow**. The first run takes 5-10 minutes (it fills in the
    daily history). A green tick means it worked. After that it runs by
    itself every 3 hours.

## Part B: Streamlit Community Cloud (the dashboard)

7.  Go to <https://share.streamlit.io> and click **Continue with
    GitHub**; allow access.
8.  Click **Create app \> Deploy a public app from GitHub**. Repository:
    `<your-username>/ebola-ai-system` Branch: `main` Main file path:
    `dashboard.py` App URL: choose a name, e.g. `kenya-ebola-analytics`
9.  Click **Advanced settings**. Python version: **3.11**. In
    **Secrets** paste (with your own values): ANTHROPIC_API_KEY =
    "your-api-key" SITREP_PASSWORD = "choose-a-password" Click **Save**,
    then **Deploy**.

Your links: - Live dashboard:
<https://kenya-ebola-analytics.streamlit.app> - Colloquium replay:
<https://kenya-ebola-analytics.streamlit.app/?view=replay>

## Part C: on your laptop

10. Double-click **Stop automatic updates.bat**, so that only the online
    system updates the data.

## Before the colloquium

- Open both links 10 minutes before you start: an app that has not been
  used for a while sleeps, and takes about a minute to wake up.
- The AI situation report asks for the password you set in step 9.
