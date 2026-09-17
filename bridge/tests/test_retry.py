import unittest

from bridge.retry import retry_with_backoff


class Boom(Exception):
    pass


class TestRetryWithBackoff(unittest.TestCase):
    def setUp(self):
        self.slept = []

    def sleep(self, seconds):
        self.slept.append(seconds)

    def test_returns_immediately_on_success(self):
        result = retry_with_backoff(lambda: "ok", sleep=self.sleep)
        self.assertEqual(result, "ok")
        self.assertEqual(self.slept, [])

    def test_retries_once_then_succeeds(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise Boom("first attempt fails")
            return "recovered"

        result = retry_with_backoff(
            flaky, attempts=2, exceptions=(Boom,), sleep=self.sleep
        )
        self.assertEqual(result, "recovered")
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.slept, [2.0])

    def test_reraises_after_exhausting_attempts(self):
        def always_fails():
            raise Boom("nope")

        with self.assertRaises(Boom):
            retry_with_backoff(
                always_fails, attempts=3, exceptions=(Boom,), sleep=self.sleep
            )

    def test_delays_double(self):
        def always_fails():
            raise Boom("nope")

        with self.assertRaises(Boom):
            retry_with_backoff(
                always_fails, attempts=4, base_delay_s=2.0,
                exceptions=(Boom,), sleep=self.sleep,
            )
        # Three failures before the last -> sleeps after attempts 1, 2, 3.
        self.assertEqual(self.slept, [2.0, 4.0, 8.0])

    def test_does_not_sleep_after_final_attempt(self):
        def always_fails():
            raise Boom("nope")

        with self.assertRaises(Boom):
            retry_with_backoff(
                always_fails, attempts=2, exceptions=(Boom,), sleep=self.sleep
            )
        self.assertEqual(len(self.slept), 1)

    def test_unlisted_exception_is_not_retried(self):
        def wrong_error():
            raise ValueError("not retryable")

        with self.assertRaises(ValueError):
            retry_with_backoff(
                wrong_error, attempts=3, exceptions=(Boom,), sleep=self.sleep
            )
        self.assertEqual(self.slept, [])

    def test_zero_attempts_rejected(self):
        with self.assertRaises(ValueError):
            retry_with_backoff(lambda: "x", attempts=0, sleep=self.sleep)


if __name__ == "__main__":
    unittest.main()
