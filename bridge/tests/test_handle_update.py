"""End-to-end pipeline tests against fakes. No network, no real credentials."""

import unittest

from bridge.clients import PermanentError, TransientError
from bridge.config import Config
from bridge.main import BUSY_NOTICE, handle_update

ALLOWED = 555
STRANGER = 999


def make_config(**overrides):
    defaults = dict(
        bot_token="123:abc",
        allowed_chat_ids=frozenset({ALLOWED}),
        max_message_chars=4096,
    )
    defaults.update(overrides)
    return Config(**defaults)


def update(chat_id=ALLOWED, text="hello", update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


class FakeTelegram:
    def __init__(self, fail_sends=False):
        self.sent = []
        self.actions = []
        self.fail_sends = fail_sends

    def send_message(self, chat_id, text):
        if self.fail_sends:
            raise TransientError("simulated delivery failure")
        self.sent.append((chat_id, text))

    def send_chat_action(self, chat_id, action="typing"):
        self.actions.append((chat_id, action))


class FakeOllama:
    def __init__(self, reply="a model reply", error=None):
        self.reply = reply
        self.error = error
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply


class TestAllowlist(unittest.TestCase):
    def test_allowlisted_chat_gets_a_reply(self):
        telegram, ollama = FakeTelegram(), FakeOllama()
        status = handle_update(update(), make_config(), telegram, ollama)
        self.assertEqual(status, "ok")
        self.assertEqual(telegram.sent, [(ALLOWED, "a model reply")])

    def test_stranger_gets_no_reply_and_no_inference(self):
        telegram, ollama = FakeTelegram(), FakeOllama()
        with self.assertLogs("bridge", level="WARNING"):
            status = handle_update(update(chat_id=STRANGER), make_config(), telegram, ollama)
        self.assertEqual(status, "rejected:not_allowlisted")
        # Nothing sent back -- we do not confirm the bot exists.
        self.assertEqual(telegram.sent, [])
        # And crucially, the model was never invoked on their behalf.
        self.assertEqual(ollama.prompts, [])

    def test_stranger_does_not_even_get_a_typing_indicator(self):
        telegram, ollama = FakeTelegram(), FakeOllama()
        with self.assertLogs("bridge", level="WARNING"):
            handle_update(update(chat_id=STRANGER), make_config(), telegram, ollama)
        self.assertEqual(telegram.actions, [])


class TestMalformedUpdates(unittest.TestCase):
    def test_update_without_message_is_ignored(self):
        telegram, ollama = FakeTelegram(), FakeOllama()
        status = handle_update({"update_id": 1}, make_config(), telegram, ollama)
        self.assertEqual(status, "ignored:unusable")

    def test_non_text_message_is_ignored(self):
        telegram, ollama = FakeTelegram(), FakeOllama()
        payload = {"update_id": 1, "message": {"chat": {"id": ALLOWED}, "photo": []}}
        status = handle_update(payload, make_config(), telegram, ollama)
        self.assertEqual(status, "ignored:unusable")
        self.assertEqual(ollama.prompts, [])

    def test_whitespace_only_message_is_ignored(self):
        telegram, ollama = FakeTelegram(), FakeOllama()
        status = handle_update(update(text="   "), make_config(), telegram, ollama)
        self.assertEqual(status, "ignored:unusable")


class TestFailureHandling(unittest.TestCase):
    def test_ollama_down_tells_the_user_instead_of_hanging(self):
        telegram = FakeTelegram()
        ollama = FakeOllama(error=TransientError("connection refused"))
        with self.assertLogs("bridge", level="ERROR"):
            status = handle_update(update(), make_config(), telegram, ollama)
        self.assertEqual(status, "error:ollama")
        self.assertEqual(telegram.sent, [(ALLOWED, BUSY_NOTICE)])

    def test_ollama_permanent_error_is_also_reported(self):
        telegram = FakeTelegram()
        ollama = FakeOllama(error=PermanentError("bad model name"))
        with self.assertLogs("bridge", level="ERROR"):
            status = handle_update(update(), make_config(), telegram, ollama)
        self.assertEqual(status, "error:ollama")

    def test_telegram_failure_is_logged_not_raised(self):
        telegram = FakeTelegram(fail_sends=True)
        ollama = FakeOllama()
        with self.assertLogs("bridge", level="ERROR"):
            status = handle_update(update(), make_config(), telegram, ollama)
        self.assertEqual(status, "error:telegram")


class TestLongReplies(unittest.TestCase):
    def test_long_reply_is_split_across_messages(self):
        telegram = FakeTelegram()
        ollama = FakeOllama(reply=("word " * 3000).strip())
        status = handle_update(update(), make_config(max_message_chars=500), telegram, ollama)
        self.assertEqual(status, "ok")
        self.assertGreater(len(telegram.sent), 1)
        for _, text in telegram.sent:
            self.assertLessEqual(len(text), 500)

    def test_typing_indicator_sent_before_generating(self):
        telegram, ollama = FakeTelegram(), FakeOllama()
        handle_update(update(), make_config(), telegram, ollama)
        self.assertEqual(telegram.actions, [(ALLOWED, "typing")])


if __name__ == "__main__":
    unittest.main()
