"""Behaviour tests for trending-spike-check (stdlib unittest, offline)."""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import spikecheck  # noqa: E402

CLI = os.path.join(ROOT, "bin", "trending-spike-check")


def snap(date, daily, weekly=None, monthly=None):
    def rows(items):
        return [{"repo": r, "stars_period": s} for r, s in items]
    lists = {"daily": rows(daily), "weekly": rows(weekly or []), "monthly": rows(monthly or [])}
    return spikecheck.load_snapshot({"date": date, "lists": lists})


def run(*paths, flags=()):
    return subprocess.run([sys.executable, CLI, *paths, *flags], capture_output=True, text=True, timeout=60)


class ClassifyTests(unittest.TestCase):
    def test_ratio_uses_weekly_over_seven(self):
        verdict, ratio = spikecheck.classify(700, 2100)
        self.assertEqual(verdict, spikecheck.SPIKE)
        self.assertAlmostEqual(ratio, 700 / 300.0)

    def test_exactly_two_is_spike_boundary(self):
        self.assertEqual(spikecheck.classify(600, 2100)[0], spikecheck.SPIKE)

    def test_just_under_two_is_consistent(self):
        self.assertEqual(spikecheck.classify(599, 2100)[0], spikecheck.CONSISTENT)

    def test_missing_weekly_abstains(self):
        self.assertEqual(spikecheck.classify(700, None), (spikecheck.ABSTAIN, None))

    def test_zero_weekly_abstains(self):
        self.assertEqual(spikecheck.classify(700, 0)[0], spikecheck.ABSTAIN)

    def test_below_half_is_underweight(self):
        self.assertEqual(spikecheck.classify(400, 9000)[0], spikecheck.UNDERWEIGHT)


class AnalyseTests(unittest.TestCase):
    def test_weekly_basis_wins_over_self_baseline(self):
        report = spikecheck.analyse([snap("2026-11-10", [("a/x", 100)]),
                                     snap("2026-11-11", [("a/x", 900)], [("a/x", 2100)])])
        row = report["rows"][0]
        self.assertEqual(row["basis"], "weekly")
        self.assertIsNone(row["self_baseline_ratio"])

    def test_self_baseline_used_when_weekly_missing(self):
        report = spikecheck.analyse([snap("2026-11-10", [("a/x", 100)]),
                                     snap("2026-11-11", [("a/x", 700)])])
        row = report["rows"][0]
        self.assertTrue(row["basis"].startswith("self-baseline"))
        self.assertEqual(row["verdict"], spikecheck.SPIKE)

    def test_single_appearance_abstains(self):
        report = spikecheck.analyse([snap("2026-11-11", [("a/x", 500)])])
        self.assertEqual(report["rows"][0]["verdict"], spikecheck.ABSTAIN)
        self.assertEqual(report["rows"][0]["days_on_daily"], 1)

    def test_persistence_counts_appearances(self):
        report = spikecheck.analyse([snap("2026-11-10", [("a/x", 10)]),
                                     snap("2026-11-11", [("a/x", 10)]),
                                     snap("2026-11-12", [])])
        self.assertEqual(report["rows"][0]["days_on_daily"], 2)
        self.assertEqual(report["rows"][0]["snapshots"], 3)

    def test_rows_sorted_by_ratio_descending(self):
        report = spikecheck.analyse([snap("2026-11-11", [("a/low", 100), ("a/high", 700)],
                                         [("a/low", 9000), ("a/high", 2100)])])
        self.assertEqual([r["repo"] for r in report["rows"]], ["a/high", "a/low"])

    def test_duplicate_dates_rejected(self):
        with self.assertRaises(spikecheck.InputError):
            spikecheck.analyse([snap("2026-11-11", [("a/x", 1)]), snap("2026-11-11", [("a/x", 2)])])

    def test_invalid_stars_rejected(self):
        with self.assertRaises(spikecheck.InputError):
            spikecheck.load_snapshot({"date": "d", "lists": {"daily": [{"repo": "a/x", "stars_period": -1}]}})


class CliTests(unittest.TestCase):
    def test_examples_produce_all_four_verdicts(self):
        proc = run(os.path.join(ROOT, "examples/in/2026-11-10.json"),
                   os.path.join(ROOT, "examples/in/2026-11-11.json"), flags=("--json",))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["counts"], {"SPIKE": 1, "CONSISTENT": 1, "UNDERWEIGHT": 1, "ABSTAIN": 2})
        self.assertEqual(report["tool_count"], 5)

    def test_committed_expected_output_matches(self):
        proc = run(os.path.join(ROOT, "examples/in/2026-11-10.json"),
                   os.path.join(ROOT, "examples/in/2026-11-11.json"), flags=("--json",))
        with open(os.path.join(ROOT, "examples/out/report.json"), encoding="utf-8") as fh:
            self.assertEqual(json.loads(proc.stdout), json.load(fh))

    def test_fail_on_spike_returns_1_only_when_spike_present(self):
        self.assertEqual(run(os.path.join(ROOT, "examples/in/2026-11-10.json"),
                             os.path.join(ROOT, "examples/in/2026-11-11.json"),
                             flags=("--fail-on-spike",)).returncode, 1)
        quiet = os.path.join(ROOT, "tests", "_quiet.json")
        with open(quiet, "w", encoding="utf-8") as fh:
            json.dump({"date": "2026-11-11",
                       "lists": {"daily": [{"repo": "a/x", "stars_period": 300}],
                                 "weekly": [{"repo": "a/x", "stars_period": 2100}]}}, fh)
        try:
            self.assertEqual(run(quiet, flags=("--fail-on-spike",)).returncode, 0)
        finally:
            os.remove(quiet)

    def test_bad_json_exits_2(self):
        bad = os.path.join(ROOT, "tests", "_bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{nope")
        try:
            self.assertEqual(run(bad).returncode, 2)
            self.assertEqual(run(bad, flags=("--json",)).returncode, 2)
        finally:
            os.remove(bad)

    def test_missing_date_exits_2(self):
        bad = os.path.join(ROOT, "tests", "_nodate.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump({"lists": {"daily": []}}, fh)
        try:
            self.assertEqual(run(bad).returncode, 2)
        finally:
            os.remove(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
