---
---
---

# Putting the system online (about 20 minutes, once)

The dashboard runs on Streamlit Community Cloud; the watcher runs on GitHub Actions every 3 hours. Both are free for a public repository. Your laptop is no longer needed.

## Part A: GitHub (code, data and the 3-hourly watcher)

1.  Create a free account at <https://github.com>

2.  Click **New repository**. Name: `ebola-ai-system`. Choose **Public**. Click **Create repository**.

3.  Upload the project in **two batches**, using **Add file \> Upload files** each time, in Chrome or Edge:

    - **Files:** select all the files in your `ebola_ai_system` folder (not the folders) and drag them onto the page. Click **Commit changes**.
    - **Folders:** select the folders `ebola`, `data`, `results` and `reports` (hold Ctrl and click each one) and **drag** them onto the page. Do not use the "choose your files" window: it cannot select folders. Wait until about 40 files are listed, then **Commit changes**.
    - Check on the **Code** tab that the four folders appear, and that `ebola` contains about ten `.py` files.
    - Do not upload personal files that happen to be in the folder, such as `.Rhistory`.

4.  **Check that the watcher's schedule uploaded.** Open the **Actions** tab. If **Update outbreak data** is listed on the left, continue. If GitHub shows a "Get started with GitHub Actions" page instead, follow **"If no workflow file exists"** below, then continue with step 5.

5.  **Settings \> Secrets and variables \> Actions \> New repository secret** Name: `ANTHROPIC_API_KEY` Secret: your API key, which starts with `sk-ant-`. Paste the key **without** quotation marks here (unlike the Streamlit secrets in step 10). Click **Add secret**.

    *Optional: creating an API key.* If you do not have a key yet:

    - Go to <https://console.anthropic.com> and sign in (or create an account).
    - Open **API Keys** and click **Create Key**. Give it a name, e.g. `ebola-ai-system`.
    - Click the copy button. The key is shown **only once**; if you lose it, create a new one.
    - Under **Billing**, check that the account has credits. New accounts may receive a small free amount; this system uses only a few US cents per day.
    - Keep the key private: never put it in a file, an email or a chat. If it is ever exposed, delete it on the API Keys page and create a new one, then update it here and in step 10.

6.  **Settings \> Actions \> General \> Workflow permissions**: choose **Read and write permissions**, **Save**.

7.  **Actions** tab \> **Update outbreak data** (left) \> **Run workflow** \> **Run workflow**. The first run takes 5-10 minutes (it fills in the daily history). A green tick means it worked. After that it runs by itself every 3 hours. Open the run and read the step "Check the official sources": a source showing "could not read source" may be blocking cloud servers.

### If no workflow file exists

GitHub is showing its "Get started" page, which means it found no workflow file in your repository. The `.github` folder didn't upload: browsers often skip folders whose names start with a dot when you drag and drop. The easiest fix is to create the file directly on GitHub, from that same page.

1.  On that page, click **"set up a workflow yourself"**, the link near the top. An editor opens, with a file name box showing something like `ebola-ai-system / .github / workflows / main.yml`.
2.  In the file name box, replace `main.yml` with **`update.yml`**.
3.  Delete any text already in the editor, then paste exactly this:

``` yaml
name: Update outbreak data

on:
  schedule:
    - cron: "0 */3 * * *"        # every 3 hours (UTC)
  workflow_dispatch:              # "Run workflow" button for a manual update

permissions:
  contents: write                 # to save the updated data back to the repository

concurrency:
  group: update-outbreak-data
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install packages
        run: pip install -r requirements.txt

      - name: Check the official sources and refit the model
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          MPLBACKEND: Agg
        run: python watch.py

      - name: Save the updated line list and estimates
        run: |
          git config user.name "outbreak-watcher"
          git config user.email "actions@users.noreply.github.com"
          git add data results
          if git diff --cached --quiet; then
            echo "No changes"
          else
            git commit -m "Automatic update $(date -u +'%Y-%m-%d %H:%M UTC')"
            git pull --rebase
            git push
          fi
```

4.  Click the green **Commit changes…** button at the top right, then **Commit changes** again in the box that appears.
5.  Go to the **Actions** tab. **Update outbreak data** now appears on the left. Click it, then **Run workflow** on the right, then the green **Run workflow** button.

### Optional: the colour theme

The `.streamlit` folder (which sets the dashboard's colour theme) is also usually skipped, because its name starts with a dot. The app works without it. To add it, click **Add file \> Create new file**, name it `.streamlit/config.toml`, paste the two lines below, and click **Commit changes**:

```         
[theme]
base = "light"
```

## Part B: Streamlit Community Cloud (the dashboard)

8.  Go to <https://share.streamlit.io> and click **Continue with GitHub**; allow access.
9.  Click **Create app \> Deploy a public app from GitHub**. Repository: `<your-username>/ebola-ai-system` Branch: `main` Main file path: `dashboard.py` App URL: choose a name, e.g. `kenya-ebola-analytics`
10. Click **Advanced settings**. Python version: **3.11**. In **Secrets**, the grey text is only an example and disappears when you type. Type these two lines with your own values, keeping the quotation marks: ANTHROPIC_API_KEY = "your-api-key" SITREP_PASSWORD = "choose-a-password" Click **Save**, then **Deploy**. Changes to secrets take about a minute to take effect.

Your links: - Live dashboard: <https://><your-app-name>.streamlit.app - Colloquium replay: <https://><your-app-name>.streamlit.app/?view=replay

## Part C: on your laptop

11. Double-click **Stop automatic updates.bat**, so that only the online system updates the data.

## Changing the dashboard later

Edit `dashboard.py` on your computer, then on GitHub use **Add file \> Upload files** to upload it again (it replaces the old one). The online app updates itself within a minute or two.

## Before the colloquium

- Open both links 10 minutes before you start: an app that has not been used for a while sleeps, and takes about a minute to wake up.
- The AI situation report asks for the password set in step 10. If it says "Could not reach the AI service", check the API key in the Streamlit secrets.
- Never paste the API key into a file, an email or a chat; it belongs only in the two secrets boxes (GitHub and Streamlit).
