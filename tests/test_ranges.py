"""Exact ranges, provably minimal counts, and bounded over-coverage tests."""

import itertools
import random
import unittest

from test_support import (
    address,
    budget_for,
    check_coverage,
    input_union,
    parse_ranges,
    successful,
)


def range_count_oracle(inputs, percent):
    merged = input_union(inputs)
    gaps = sorted(merged[i + 1][0] - merged[i][1] - 1 for i in range(len(merged) - 1))
    budget = budget_for(merged, percent)
    joined = 0
    for gap in gaps:
        if gap > budget:
            break
        budget -= gap
        joined += 1
    return len(merged) - joined


def brute_force_min_count(inputs, percent):
    """Check every selection of gaps in small cases, not the greedy algorithm."""
    merged = input_union(inputs)
    gaps = [merged[i + 1][0] - merged[i][1] - 1 for i in range(len(merged) - 1)]
    budget = budget_for(merged, percent)
    return min(
        len(merged) - sum(selection)
        for selection in itertools.product((0, 1), repeat=len(gaps))
        if sum(gap for gap, chosen in zip(gaps, selection) if chosen) <= budget
    )


class RangeTests(unittest.TestCase):
    def test_exact_union_of_overlapping_and_adjacent_ranges(self):
        inputs = [
            "192.0.2.200-192.0.2.220",
            "192.0.2.0/25",
            "192.0.2.120-192.0.2.191",
            "192.0.2.200-192.0.2.205",
            "192.0.2.192-192.0.2.199",
        ]
        result, _ = successful(inputs, "-q", "--ranges")
        self.assertEqual(result, ["192.0.2.0-192.0.2.220"])

    def test_exact_ranges_various_boundaries(self):
        cases = [
            (["0.0.0.0/0"], ["0.0.0.0-255.255.255.255"]),
            (["0.0.0.0"], ["0.0.0.0-0.0.0.0"]),
            (["255.255.255.255"], ["255.255.255.255-255.255.255.255"]),
            (["255.255.255.254/31"], ["255.255.255.254-255.255.255.255"]),
            (["10.0.0.255", "10.0.1.0"], ["10.0.0.255-10.0.1.0"]),
            (
                ["198.51.100.1", "198.51.100.3"],
                ["198.51.100.1-198.51.100.1", "198.51.100.3-198.51.100.3"],
            ),
        ]
        for inputs, expected in cases:
            with self.subTest(inputs=inputs):
                result, _ = successful(inputs, "-q", "-r")
                self.assertEqual(result, expected)

    def test_known_approximate_merges(self):
        inputs = ["192.0.2.1", "192.0.2.5", "192.0.2.7"]
        cases = [
            ("0", 3),
            ("33", 3),
            ("34", 2),
            ("100", 2),
            ("134", 1),
        ]
        for percent, expected_count in cases:
            with self.subTest(percent=percent):
                output, _ = successful(inputs, "-q", "-r", "-p", percent)
                self.assertEqual(len(output), expected_count)
                check_coverage(inputs, output, percent, ranges=True)

    def test_zero_extra_budget_does_not_join_gaps(self):
        inputs = ["192.0.2.0-192.0.2.48", "192.0.2.50-192.0.2.99"]
        for percent in ["0.1", "1", "1.02"]:
            with self.subTest(percent=percent):
                output, _ = successful(inputs, "-r", "-q", "-p", percent)
                check_coverage(inputs, output, percent, ranges=True)
                expected = 1 if percent == "1.02" else 2
                self.assertEqual(len(output), expected)

    def test_large_ipv4_ranges_without_expansion(self):
        inputs = ["0.0.0.0/2", "192.0.0.0/2"]
        output, _ = successful(inputs, "-r", "-q", "-p", "200")
        check_coverage(inputs, output, "200", ranges=True)
        self.assertEqual(len(output), 1)
        self.assertEqual(output, ["0.0.0.0-255.255.255.255"])

    def test_random_exact_cover(self):
        rng = random.Random(0xA11CE)
        for case in range(120):
            values = rng.sample(range(2000), rng.randrange(1, 150))
            inputs = [address(n) for n in values]
            output, _ = successful(inputs, "-r", "-q")
            with self.subTest(case=case):
                self.assertEqual(parse_ranges(output), input_union(inputs))

    def test_random_minimal_count_against_independent_oracle(self):
        rng = random.Random(0xBEE5)
        for case in range(220):
            values = rng.sample(range(2500), rng.randrange(1, 120))
            inputs = [address(n) for n in values]
            percent = rng.choice(
                ["0", "0.01", "0.1", "1", "5", "10", "25", "50", "100"]
            )
            result, _ = successful(inputs, "-r", "-q", "-p", percent)
            with self.subTest(case=case, percent=percent):
                check_coverage(inputs, result, percent, ranges=True)
                self.assertEqual(len(result), range_count_oracle(inputs, percent))

    def test_brute_force_optimality_on_small_random_cases(self):
        rng = random.Random(0xBADA55)
        for case in range(140):
            values = rng.sample(range(40), rng.randrange(1, 10))
            inputs = [address(value) for value in values]
            percent = rng.choice(["0", "5", "20", "50", "100", "300"])
            output, _ = successful(inputs, "-r", "-q", "-p", percent)
            with self.subTest(case=case, percent=percent):
                self.assertEqual(len(output), brute_force_min_count(inputs, percent))
                check_coverage(inputs, output, percent, ranges=True)

    def test_extra_coverage_is_monotonic_with_budget(self):
        inputs = ["203.0.113.0/28", "203.0.113.17", "203.0.113.25", "203.0.113.38"]
        last_count = len(input_union(inputs))
        for percent in ["0", "1", "5", "10", "20", "30", "50", "100", "300"]:
            result, _ = successful(inputs, "-r", "-q", "-p", percent)
            self.assertLessEqual(len(result), last_count)
            last_count = len(result)
            check_coverage(inputs, result, percent, ranges=True)

    def test_idempotence_and_equivalent_input(self):
        a = ["10.0.0.0/28", "10.0.0.25", "10.0.0.30"]
        b = ["10.0.0.0-10.0.0.15", "10.0.0.30", "10.0.0.25", "10.0.0.25"]
        for percent in ["0", "10", "100"]:
            with self.subTest(percent=percent):
                first, _ = successful(a, "-r", "-q", "-p", percent)
                second, _ = successful(b, "-r", "-q", "-p", percent)
                self.assertEqual(first, second)
                reparsed, _ = successful(first, "-r", "-q")
                self.assertEqual(reparsed, first)

    def test_maximum_ipv4_budget_is_capped(self):
        inputs = ["0.0.0.0", "255.255.255.255"]
        output, _ = successful(inputs, "-r", "-q", "-p", "1000000000000")
        self.assertEqual(output, ["0.0.0.0-255.255.255.255"])
        check_coverage(inputs, output, "1000000000000", ranges=True)


if __name__ == "__main__":
    unittest.main()
