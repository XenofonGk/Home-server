import unittest

from bridge.config import Config, ConfigError

BASE = {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_ALLOWED_CHAT_IDS": "555"}


class TestConfigFromEnv(unittest.TestCase):
    def test_parses_a_minimal_environment(self):
        config = Config.from_env(BASE)
        self.assertEqual(config.bot_token, "123:abc")
        self.assertEqual(config.allowed_chat_ids, frozenset({555}))
        self.assertEqual(config.ollama_url, "http://127.0.0.1:11434/api/generate")

    def test_missing_token_is_fatal(self):
        env = dict(BASE)
        del env["TELEGRAM_BOT_TOKEN"]
        with self.assertRaises(ConfigError):
            Config.from_env(env)

    def test_missing_allowlist_is_fatal(self):
        # This is the security-critical case: an absent allowlist must never
        # be treated as "allow everyone".
        env = dict(BASE)
        del env["TELEGRAM_ALLOWED_CHAT_IDS"]
        with self.assertRaises(ConfigError):
            Config.from_env(env)

    def test_empty_allowlist_is_fatal(self):
        env = dict(BASE, TELEGRAM_ALLOWED_CHAT_IDS="   ")
        with self.assertRaises(ConfigError):
            Config.from_env(env)

    def test_non_numeric_allowlist_is_fatal(self):
        env = dict(BASE, TELEGRAM_ALLOWED_CHAT_IDS="not-an-id")
        with self.assertRaises(ConfigError):
            Config.from_env(env)

    def test_multiple_ids_comma_or_space_separated(self):
        self.assertEqual(
            Config.from_env(dict(BASE, TELEGRAM_ALLOWED_CHAT_IDS="1,2 3")).allowed_chat_ids,
            frozenset({1, 2, 3}),
        )

    def test_negative_chat_ids_are_valid(self):
        # Telegram group chat IDs are negative. Rejecting them would be a bug.
        config = Config.from_env(dict(BASE, TELEGRAM_ALLOWED_CHAT_IDS="-100123"))
        self.assertTrue(config.is_allowed(-100123))

    def test_is_allowed_rejects_unknown_ids(self):
        config = Config.from_env(BASE)
        self.assertTrue(config.is_allowed(555))
        self.assertFalse(config.is_allowed(556))


if __name__ == "__main__":
    unittest.main()
