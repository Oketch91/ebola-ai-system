# Putting the system online and keeping it up to date

The dashboard runs on Streamlit Community Cloud; the watcher runs on GitHub Actions,
scheduled every 3 hours. Both are free for a public repository. Your laptop is not needed.

Contents
- Part A: GitHub (code, data and the scheduled watcher), about 15 minutes, once
- Part B: Streamlit Community Cloud (the dashboard), about 5 minutes, once
- Part C: on your laptop
- Part D: updating the repository after changes
- Part E: marking the version used in the paper (GitHub release)
- Part F: a permanent DOI for the code (Zenodo)
- Before the colloquium
- Troubleshooting

---

## Part A: GitHub (code, data and the scheduled watcher)

1. Create a free account at https://github.com
2. Click **New repository**. Name: `ebola-ai-system`. Choose **Public**. Click **Create repository**.
3. Upload the project in **two batches**, using **Add file > Upload files** each time,
   in Chrome or Edge:
   - **Files:** select all the files in your `ebola_ai_system` folder (not the folders) and
     drag them onto the page. Click **Commit changes**.
   - **Folders:** select the folders `ebola`, `data`, `results` and `reports` (hold Ctrl and
     click each one) and **drag** them onto the page. Do not use the "choose your files" window:
     it cannot select folders. Wait until all files are listed, then **Commit changes**.
   - Check on the **Code** tab that the four folders appear, and that `ebola` contains about
     ten `.py` files.
   - Do not upload personal files that happen to be in the folder, such as `.Rhistory`.
4. **Check that the watcher's schedule uploaded.** Open the **Actions** tab. If
   **Update outbreak data** is listed on the left, continue. If GitHub shows a
   "Get started with GitHub Actions" page instead, follow
   **"If no workflow file exists"** below, then continue with step 5.
5. **Settings > Secrets and variables > Actions > New repository secret**
   Name: `ANTHROPIC_API_KEY`   Secret: your API key, which starts with `sk-ant-`.
   Paste the key **without** quotation marks here (unlike the Streamlit secrets in step 10).
   Click **Add secret**.

   *Optional: creating an API key.* If you do not have a key yet:
   - Go to https://console.anthropic.com and sign in (or create an account).
   - Open **API Keys** and click **Create Key**. Give it a name, e.g. `ebola-ai-system`.
   - Click the copy button. The key is shown **only once**; if you lose it, create a new one.
   - Under **Billing**, check that the account has credits. New accounts may receive a small
     free amount; this system uses only a few US cents per day.
   - Keep the key private: never put it in a file, an email or a chat. If it is ever exposed,
     delete it on the API Keys page and create a new one, then update it here and in step 10.

6. **Settings > Actions > General > Workflow permissions**: choose **Read and write permissions**, **Save**.
7. **Actions** tab > **Update outbreak data** (left) > **Run workflow** > **Run workflow**.
   The first run takes 5-10 minutes (it fills in the daily history). A green tick means it worked.
   After that it runs by itself on a 3-hour schedule; GitHub may delay scheduled runs when its
   servers are busy, so in practice runs come every 3 to 7 hours. Open a run and read the step
   "Check the official sources and refit the model": a source showing "could not read source"
   may be blocking cloud servers.

### If no workflow file exists
GitHub is showing its "Get started" page, which means it found no workflow file in your
repository. The `.github` folder didn't upload: browsers often skip folders whose names
start with a dot when you drag and drop. The easiest fix is to create the file directly
on GitHub, from that same page.

1. On that page, click **"set up a workflow yourself"**, the link near the top. An editor
   opens, with a file name box showing something like
   `ebola-ai-system / .github / workflows / main.yml`.
2. In the file name box, replace `main.yml` with **`update.yml`**.
3. Delete any text already in the editor, then paste exactly this:

```yaml
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

4. Click the green **Commit changes…** button at the top right, then **Commit changes**
   again in the box that appears.
5. Go to the **Actions** tab. **Update outbreak data** now appears on the left. Click it,
   then **Run workflow** on the right, then the green **Run workflow** button.

### Optional: the colour theme
The `.streamlit` folder (which sets the dashboard's colour theme) is also usually skipped,
because its name starts with a dot. The app works without it. To add it, click
**Add file > Create new file**, name it `.streamlit/config.toml`, paste the two lines below,
and click **Commit changes**:

```
[theme]
base = "light"
```

---

## Part B: Streamlit Community Cloud (the dashboard)

8. Go to https://share.streamlit.io and click **Continue with GitHub**; allow access.
9. Click **Create app > Deploy a public app from GitHub**.
   Repository: `<your-username>/ebola-ai-system`   Branch: `main`   Main file path: `dashboard.py`
   App URL: choose a name, e.g. `kenya-ebola-analytics`
10. Click **Advanced settings**. Python version: **3.11**.
    In **Secrets**, the grey text is only an example and disappears when you type.
    Type these two lines with your own values, keeping the quotation marks:

        ANTHROPIC_API_KEY = "your-api-key"
        SITREP_PASSWORD = "choose-a-password"

    Click **Save**, then **Deploy**. Changes to secrets take about a minute to take effect.

Your links:
- Live dashboard:    https://<your-app-name>.streamlit.app
- Colloquium replay: https://<your-app-name>.streamlit.app/?view=replay

---

## Part C: on your laptop

11. Double-click **Stop automatic updates.bat**, so that only the online system updates the data.
    From now on, do not run `watch.py` on your laptop: it would update only the laptop's copy,
    which would then differ from the online data. For an extra update outside the schedule,
    use **Actions > Update outbreak data > Run workflow** on GitHub.

---

## Part D: updating the repository after changes

Use the **existing** repository; do not create a new one. The live system runs from it and the
paper cites its address.

To upload changed files: **Add file > Upload files**, drag the files or folders onto the page
(a file with the same name replaces the old one), then **Commit changes**. The online app picks
up changes within a minute or two.

**Upload** (when they have changed):

| Files | Why |
|---|---|
| `ebola/extraction.py`, `ebola/sources.py` and other files in `ebola/` | The system's code, including the frozen extraction instructions used in the evaluation |
| `dashboard.py` | The dashboard |
| `build_corpus.py`, `screen_corpus.py`, `build_reference.py`, `evaluate_extraction.py`, `flow_counts.py`, `deployment_stats.py` | The evaluation code, so that anyone can reproduce the paper |
| `corpus/sources_corpus.json`, `corpus/manual_reports.csv`, `corpus/reference/` | The evaluation's inputs |
| `evaluation/` folder | The AI's saved answers, the results and the review file: the paper's evidence |
| `DEPLOY.md`, `HOW TO USE.txt`, `requirements.txt` | Documentation and package list |

**Do not upload:**
- Your local **`data/`** and **`results/`** folders. The online watcher updates these every few
  hours, and the laptop's copies are older: uploading them would overwrite the live data.
- **`corpus/archive/`** and **`corpus/text/`** (the downloaded reports). They are large, some are
  PDFs that GitHub's web upload handles poorly, and they belong in the data deposit (Zenodo,
  Part F) at submission.
- Anything containing the API key, and personal files such as `.Rhistory`.

---

## Part E: marking the version used in the paper (GitHub release)

After uploading the evaluation code and results (Part D), mark this exact version, so that the
paper can cite the code that produced its results.

If you want a permanent DOI for this version (Part F), switch the repository on in Zenodo
**first** (Part F, steps 1-3), because Zenodo only archives releases published after that.

1. On the repository page, click **Releases** (right-hand side), then **Draft a new release**.
2. Click **Choose a tag**, type `v1.0-evaluation` and choose **Create new tag**.
   Title: **Version used in the evaluation (4 November 2026)**.
   Optionally, add a description, e.g. "Code, instructions (fingerprint 70edacae0b5b6875) and
   outputs of the evaluation reported in the paper."
3. Click **Publish release**.

The release is a permanent snapshot: later changes to the repository do not alter it.

---

## Part F: a permanent DOI for the code (Zenodo)

Connecting the repository to Zenodo gives each release a permanent DOI for the paper's Code
Availability statement. This is best done at submission time.

1. Go to https://zenodo.org and log in with **GitHub**.
2. Open your account menu > **GitHub**. Click **Sync now** if your repository is not listed.
3. Switch **On** the `ebola-ai-system` repository.
4. Publish a release on GitHub (Part E). If `v1.0-evaluation` was published before step 3,
   publish a new release (e.g. `v1.0.1-evaluation`) so that Zenodo archives it.
5. Within a few minutes, the release appears under **Upload** in Zenodo with its DOI.
   Put that DOI in the paper's Code Availability statement.

The downloaded reports (`corpus/archive/`, `corpus/text/`) and the corpus index can be deposited
as a separate Zenodo dataset at the same time, for the Data Availability statement.

---

## Before the colloquium

- Open both links 10 minutes before you start: an app that has not been used for a while
  sleeps, and takes about a minute to wake up.
- Check the latest run on the **Actions** tab that morning: a green tick confirms the live data
  are current.
- The AI situation report asks for the password set in step 10.
- Never paste the API key into a file, an email or a chat; it belongs only in the two
  secrets boxes (GitHub and Streamlit).

---

## Troubleshooting

| What you see | What to do |
|---|---|
| Actions shows a "Get started with GitHub Actions" page | The workflow file did not upload: see "If no workflow file exists" (Part A) |
| Folders missing on the Code tab | Drag the folders onto the upload page; the "choose your files" window cannot select folders |
| Situation report: "Could not reach the AI service: Error code: 401 ... authentication_error" | The API key is wrong or revoked. Create a new key, put it in the Streamlit secrets (with quotation marks) and in the GitHub secret (without), then **Manage app > ⋮ > Reboot app** |
| A run log shows "extraction failed ... 401" | The GitHub secret holds a wrong key: update `ANTHROPIC_API_KEY` under Settings > Secrets and variables > Actions |
| A run log shows "could not read source (ReadTimeout)" | The website was slow; the next run tries again automatically |
| Runs arrive every 4-7 hours instead of 3 | Normal: GitHub delays scheduled runs when busy. Use **Run workflow** for an immediate update |
| Dashboard shows old figures | Refresh the page; if still old, check that the latest run on Actions succeeded |
| The online app looks different from the laptop version | Upload the changed `dashboard.py` (Part D); the app updates within a minute or two |
