# Quran Bot

Posts the Quran on X (Twitter) one verse at a time, from Al-Fatiha to An-Nas, then starts again. Each post has the Arabic text (Uthmani), the Sahih International translation, and a reference.

- Verses come from [alquran.cloud](https://alquran.cloud/api).
- GitHub Actions runs the bot every 2 hours (`.github/workflows/quran-bot.yml`).
- The next verse to post is stored in `quran_bot_state.json`, which the workflow commits after each post.
- A verse too long for one tweet is posted as a thread: Arabic first, then the translation as replies.

## Setup

1. In the [X developer portal](https://developer.x.com/en/portal/dashboard):
   - Put the app inside a **Project**.
   - Under *User authentication settings*, set **App permissions** to **Read and write**.
   - **Then regenerate** the Access Token and Secret. Tokens created before the permission change stay read-only and get `403`.
   - Make sure the account has posting access on its plan, or credits if it uses pay-per-use. Without either you get `402` or `503` errors.
2. In the GitHub repo, go to **Settings → Secrets and variables → Actions** and add:
   `API_KEY`, `API_SECRET`, `ACCESS_TOKEN`, `ACCESS_TOKEN_SECRET` (the consumer key/secret and the user access token/secret).
3. In **Settings → Actions → General → Workflow permissions**, allow read and write.
4. On the **Actions** tab, enable the workflow if it is disabled. GitHub turns off scheduled workflows after 60 days without a commit.

## Testing

From the Actions tab, run the workflow manually with **dry_run** ticked. It prints the tweet without posting. Locally:

```bash
pip install tweepy requests
DRY_RUN=1 python bot.py
```

If a real run fails, the job turns red and the log shows the HTTP status, X's error message, and a hint for fixing it.
