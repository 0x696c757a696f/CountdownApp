import unittest
from uuid import uuid4

from countdownapp.single_instance import SingleInstanceGuard


class SingleInstanceGuardTests(unittest.TestCase):
    def test_only_one_guard_can_hold_the_same_application_lock(self):
        name = f"CountdownApp-test-{uuid4()}"
        first = SingleInstanceGuard(name)
        second = SingleInstanceGuard(name)

        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
        finally:
            second.release()
            first.release()

        replacement = SingleInstanceGuard(name)
        try:
            self.assertTrue(replacement.acquire())
        finally:
            replacement.release()


if __name__ == "__main__":
    unittest.main()
