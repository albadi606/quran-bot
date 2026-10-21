import tweepy
import requests
import json
import sys
import time
from datetime import datetime
import os


TWEET_LIMIT = 280
TOTAL_SURAHS = 114


class QuranBot:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.api_secret = os.getenv("API_SECRET")
        self.access_token = os.getenv("ACCESS_TOKEN")
        self.access_token_secret = os.getenv("ACCESS_TOKEN_SECRET")

        # DRY_RUN=1 fetches and formats the verse but never touches X
        self.dry_run = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")

        if not self.dry_run:
            self.check_credentials()
            self.setup_twitter_api()

        self.quran_api_base = "https://api.alquran.cloud/v1"
        self.state_file = "quran_bot_state.json"
        self.load_state()

    def check_credentials(self):
        missing = [name for name, value in [
            ("API_KEY", self.api_key),
            ("API_SECRET", self.api_secret),
            ("ACCESS_TOKEN", self.access_token),
            ("ACCESS_TOKEN_SECRET", self.access_token_secret),
        ] if not value]
        if missing:
            print(f"Missing credentials: {', '.join(missing)}")
            print("Add them under Settings -> Secrets and variables -> Actions.")
            sys.exit(1)

    def setup_twitter_api(self):
        # wait_on_rate_limit is off on purpose: on a 429 it can sleep for
        # up to 24h, which just hangs the Actions job until it is killed.
        self.client = tweepy.Client(
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
        )
        print("Twitter client initialized")

    def load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
            else:
                self.state = self.create_initial_state()
        except Exception as e:
            print(f"Error loading state: {e}")
            self.state = self.create_initial_state()

    def create_initial_state(self):
        return {
            'current_surah': 1,
            'current_verse': 1,
            'total_verses_posted': 0
        }

    def save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")

    def get_verse(self, surah, verse):
        url = f"{self.quran_api_base}/ayah/{surah}:{verse}/editions/quran-uthmani,en.sahih"
        for attempt in range(3):
            try:
                response = requests.get(url, timeout=20)
                data = response.json()
                if data.get('code') == 200:
                    arabic, english = data['data']
                    surah_info = arabic['surah']
                    return {
                        'arabic': arabic['text'],
                        'english': english['text'],
                        'surah_name': surah_info['englishName'],
                        'surah_number': surah,
                        'ayah_number': verse,
                        'surah_verse_count': surah_info['numberOfAyahs'],
                        'reference': f"Surah {surah_info['englishName']} ({surah}:{verse})"
                    }
                print(f"Quran API returned {data.get('code')}: {data.get('data')}")
            except Exception as e:
                print(f"Error fetching verse (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(5)
        return None

    def format_tweets(self, verse_data):
        """Return a list of tweet texts: one tweet if it fits, otherwise a thread."""
        arabic = verse_data['arabic']
        english = verse_data['english']
        reference = f"— {verse_data['reference']}"

        single = f'{arabic}\n\n"{english}"\n\n{reference}'
        if len(single) <= TWEET_LIMIT:
            return [single]

        # Too long for one tweet: Arabic first, English translation as replies
        tweets = self.split_text(arabic, f"\n\n{reference}")
        tweets += self.split_text(f'"{english}"', "")
        return tweets

    def split_text(self, text, suffix):
        """Split text on word boundaries into tweet-sized chunks; suffix goes on the last chunk."""
        chunks = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if len(candidate) + len(" …") > TWEET_LIMIT:
                chunks.append(current + " …")
                current = word
            else:
                current = candidate
        if len(current) + len(suffix) > TWEET_LIMIT:
            chunks.append(current + " …")
            current = ""
        chunks.append((current + suffix).strip())
        return chunks

    def advance_to_next_verse(self, verse_count):
        surah = self.state['current_surah']
        verse = self.state['current_verse']

        if verse >= verse_count:
            if surah >= TOTAL_SURAHS:
                self.state['current_surah'] = 1
                self.state['current_verse'] = 1
                print("Completed the entire Quran! Starting over from Al-Fatiha.")
            else:
                self.state['current_surah'] = surah + 1
                self.state['current_verse'] = 1
                print(f"Finished Surah {surah}, moving to Surah {surah + 1}")
        else:
            self.state['current_verse'] = verse + 1

    def explain_twitter_error(self, e):
        """Print the full error X sent back, plus what it usually means."""
        status = e.response.status_code if getattr(e, 'response', None) is not None else None
        print(f"X API error: HTTP {status}")
        print(f"  codes: {getattr(e, 'api_codes', None)}")
        print(f"  messages: {getattr(e, 'api_messages', None)}")
        if getattr(e, 'response', None) is not None:
            print(f"  body: {e.response.text[:1000]}")

        hints = {
            401: "Keys/tokens are wrong or were regenerated. Copy all four again from the developer portal.",
            402: "Your X developer account has no API credits/plan for posting. Add credits or a plan in the developer portal.",
            403: ("Posting is forbidden. Usually the app permission is 'Read' only: set it to 'Read and write' "
                  "under User authentication settings, then REGENERATE the Access Token and Secret "
                  "(old tokens keep the old permission). Also caused by duplicate or too-long tweets."),
            429: "Rate limit / posting cap reached. Post less often (free tier allows 17 posts per 24h).",
            503: ("X returned 503. If this happens every run (not occasionally), it is usually an account/plan "
                  "problem rather than an outage. Check the app is inside a Project and the account has posting access."),
        }
        if status in hints:
            print(f"  hint: {hints[status]}")
        return status

    def send_tweet(self, text, reply_to=None):
        for attempt in range(3):
            try:
                response = self.client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
                return response.data['id']
            except tweepy.errors.TwitterServerError as e:
                self.explain_twitter_error(e)
                if attempt < 2:
                    time.sleep(15 * (attempt + 1))
            except tweepy.errors.TweepyException as e:
                # 4xx errors won't fix themselves on retry
                self.explain_twitter_error(e)
                return None
        return None

    def post_verse(self):
        surah = self.state['current_surah']
        verse = self.state['current_verse']

        print(f"Fetching Surah {surah}, Verse {verse}...")
        verse_data = self.get_verse(surah, verse)

        if not verse_data:
            print("Failed to fetch verse")
            return False

        tweets = self.format_tweets(verse_data)

        if self.dry_run:
            for i, text in enumerate(tweets, 1):
                print(f"--- tweet {i}/{len(tweets)} ({len(text)} chars) ---\n{text}")
            print("DRY_RUN: nothing posted, state not changed.")
            return True

        reply_to = None
        for i, text in enumerate(tweets):
            tweet_id = self.send_tweet(text, reply_to)
            if not tweet_id:
                if i == 0:
                    return False
                # The verse itself is already up; don't post it twice next run
                print(f"Posted the first {i} of {len(tweets)} tweets in the thread.")
                break
            print(f"Tweet ID: {tweet_id}")
            reply_to = tweet_id

        self.state['total_verses_posted'] += 1
        self.advance_to_next_verse(verse_data['surah_verse_count'])
        self.save_state()

        print(f"Posted: {verse_data['reference']}")
        print(f"Total verses posted: {self.state['total_verses_posted']}")
        return True

    def run_bot(self):
        print(f"Bot started at {datetime.now()}")
        print(f"Next: Surah {self.state['current_surah']}, Verse {self.state['current_verse']}")
        print(f"Total posted so far: {self.state['total_verses_posted']}")

        success = self.post_verse()
        print("Done!" if success else "Failed. See the error above.")
        return success


def main():
    bot = QuranBot()
    # A non-zero exit makes the Actions run show red instead of a false green
    sys.exit(0 if bot.run_bot() else 1)


if __name__ == "__main__":
    main()
