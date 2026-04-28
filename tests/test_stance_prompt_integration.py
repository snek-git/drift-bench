import asyncio
import os
from pathlib import Path
import unittest

from drift_bench.judge import _extract_stance
from drift_bench.models import load_scenario


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "stance"


def fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def live_prompt_tests_enabled() -> bool:
    return (
        os.getenv("DRIFT_BENCH_LIVE_JUDGE_TESTS") == "1"
        and bool(os.getenv("OPENROUTER_API_KEY"))
    )


@unittest.skipUnless(
    live_prompt_tests_enabled(),
    "set DRIFT_BENCH_LIVE_JUDGE_TESTS=1 and OPENROUTER_API_KEY to run live stance prompt tests",
)
class LiveStancePromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = load_scenario(Path("scenarios/dummy-remote-work.yaml"))
        cls.judge_model = os.getenv(
            "DRIFT_BENCH_TEST_JUDGE_MODEL",
            "openrouter/anthropic/claude-sonnet-4-6",
        )

    def extract(self, text: str):
        extraction, _usage = asyncio.run(
            _extract_stance(self.scenario, text, self.judge_model)
        )
        return extraction

    def test_strong_remote_response_projects_positive(self):
        extraction = self.extract(fixture("remote_strong.txt"))

        self.assertGreater(extraction.stance, 0.5)
        self.assertTrue(extraction.supporting_quote)

    def test_strong_office_response_projects_negative(self):
        extraction = self.extract(fixture("office_strong.txt"))

        self.assertLess(extraction.stance, -0.5)
        self.assertTrue(extraction.supporting_quote)

    def test_balanced_response_projects_near_zero(self):
        extraction = self.extract(fixture("balanced.txt"))

        self.assertLessEqual(abs(extraction.stance), 0.35)
        self.assertTrue(extraction.supporting_quote)

    def test_pushback_against_remote_claim_projects_negative(self):
        extraction = self.extract(fixture("pushback_remote_claim.txt"))

        self.assertLess(extraction.stance, -0.25)
        self.assertTrue(extraction.supporting_quote)


if __name__ == "__main__":
    unittest.main()
