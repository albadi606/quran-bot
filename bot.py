import tweepy
import requests
import json
from datetime import datetime
import os


class QuranBot:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        self.api_secret = os.getenv("API_SECRET")
        self.access_token = os.getenv("ACCESS_TOKEN")
        self.access_token_secret = os.getenv("ACCESS_TOKEN_SECRET")
        self.bearer_token = os.getenv("BEARER_TOKEN")

        self.setup_twitter_api()

        self.quran_api_base = "https://api.alquran.cloud/v1"
        self.state_file = "quran_bot_state.json"
        self.load_state()

    def setup_twitter_api(self):
        try:
            self.client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True
            )
            me = self.client.get_me()
            if me.data:
                print(f"Authenticated as @{me.data.username}")
        except Exception as e:
            print(f"Authentication failed: {e}")
            raise

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

    def get_surah_verse_count(self, surah):
        try:
            url = f"{self.quran_api_base}/surah/{surah}"
            response = requests.get(url)
            data = response.json()
            if data['code'] == 200:
                return data['data']['numberOfAyahs']
        except Exception as e:
            print(f"Error getting surah info: {e}")
        return None

    def get_verse(self, surah, verse):
        try:
            arabic_url = f"{self.quran_api_base}/ayah/{surah}:{verse}"
            english_url = f"{self.quran_api_base}/ayah/{surah}:{verse}/en.sahih"

            arabic_response = requests.get(arabic_url)
            english_response = requests.get(english_url)

            arabic_data = arabic_response.json()
            english_data = english_response.json()

            if arabic_data['code'] == 200 and english_data['code'] == 200:
                surah_name = arabic_data['data']['surah']['englishName']
                return {
                    'arabic': arabic_data['data']['text'],
                    'english': english_data['data']['text'],
                    'surah_name': surah_name,
                    'surah_number': surah,
                    'ayah_number': verse,
                    'reference': f"Surah {surah_name} ({surah}:{verse})"
                }
        except Exception as e:
            print(f"Error fetching verse: {e}")
        return None

    def format_tweet(self, verse_data):
        if not verse_data:
            return None

        tweet = f"{verse_data['arabic']}\n\n"
        tweet += f'"{verse_data["english"]}"\n\n'
        tweet += f"— {verse_data['reference']}"

        if len(tweet) > 280:
            base_length = len(verse_data['arabic']) + len(verse_data['reference']) + len('\n\n""\n\n— ')
            available_chars = 280 - base_length - 3

            if available_chars > 20:
                truncated_english = verse_data['english'][:available_chars] + "..."
                tweet = f"{verse_data['arabic']}\n\n"
                tweet += f'"{truncated_english}"\n\n'
                tweet += f"— {verse_data['reference']}"

        return tweet

    def advance_to_next_verse(self):
        """Move to the next verse. If surah ends, go to next surah. After 114, loop back to 1."""
        surah = self.state['current_surah']
        verse = self.state['current_verse']

        verse_count = self.get_surah_verse_count(surah)
        if verse_count and verse >= verse_count:
            # Move to next surah
            if surah >= 114:
                # Finished the entire Quran, start over
                self.state['current_surah'] = 1
                self.state['current_verse'] = 1
                print("Completed the entire Quran! Starting over from Al-Fatiha.")
            else:
                self.state['current_surah'] = surah + 1
                self.state['current_verse'] = 1
                print(f"Finished Surah {surah}, moving to Surah {surah + 1}")
        else:
            self.state['current_verse'] = verse + 1

    def post_verse(self):
        surah = self.state['current_surah']
        verse = self.state['current_verse']

        print(f"Fetching Surah {surah}, Verse {verse}...")
        verse_data = self.get_verse(surah, verse)

        if not verse_data:
            print("Failed to fetch verse")
            return False

        tweet_text = self.format_tweet(verse_data)
        if not tweet_text:
            print("Failed to format tweet")
            return False

        response = self.client.create_tweet(text=tweet_text)
        if response.data:
            self.state['total_verses_posted'] += 1
            self.advance_to_next_verse()
            self.save_state()

            print(f"Posted: {verse_data['reference']}")
            print(f"Total verses posted: {self.state['total_verses_posted']}")
            return True
        else:
            print("Failed to post tweet")
            return False

    def run_bot(self):
        print(f"Bot started at {datetime.now()}")
        print(f"Next: Surah {self.state['current_surah']}, Verse {self.state['current_verse']}")
        print(f"Total posted so far: {self.state['total_verses_posted']}")

        success = self.post_verse()
        print("Done!" if success else "Failed!")
        return success


def main():
    bot = QuranBot()
    bot.run_bot()


if __name__ == "__main__":
    main()
