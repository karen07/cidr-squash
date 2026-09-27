"""Deterministic randomized coverage tests across the entire IPv4 address space."""

import random
import unittest

from test_support import (
    IPV4_SIZE,
    address,
    check_coverage,
    expected_cidrs,
    input_union,
    successful,
)


def mixed_inputs(rng):
    """Generate mixed address, CIDR, and range inputs near tricky boundaries."""
    anchors = [0, 256, 65535, 1 << 31, IPV4_SIZE - 65536, IPV4_SIZE - 1]
    inputs = []
    for _ in range(rng.randint(1, 22)):
        anchor = rng.choice(anchors)
        value = max(0, min(IPV4_SIZE - 1, anchor + rng.randrange(-2048, 2049)))
        kind = rng.randrange(3)
        if kind == 0:
            inputs.append(address(value))
        elif kind == 1:
            prefix = rng.choice([0, 1, 8, 16, 24, 29, 30, 31, 32])
            inputs.append(f"{address(value)}/{prefix}")
        else:
            last = min(IPV4_SIZE - 1, value + rng.randrange(0, 200))
            inputs.append(f"{address(value)}-{address(last)}")
    return inputs


class PropertyTests(unittest.TestCase):
    def test_random_mixed_full_address_space(self):
        rng = random.Random(0x1F4)
        percentages = ["0", "0.01", "0.1", "1", "5", "25", "100", "500"]
        for case in range(125):
            lines = mixed_inputs(rng)
            percent = rng.choice(percentages)
            for ranges in [False, True]:
                flags = ("-r",) if ranges else ()
                output, _ = successful(lines, "-q", "-p", percent, *flags)
                with self.subTest(case=case, percent=percent, ranges=ranges):
                    check_coverage(lines, output, percent, ranges)
                    if percent == "0" and not ranges:
                        self.assertEqual(output, expected_cidrs(input_union(lines)))

    def test_random_exact_mixed_against_cidr_oracle(self):
        rng = random.Random(0xC1D)
        for case in range(65):
            lines = mixed_inputs(rng)
            output, _ = successful(lines, "-q")
            with self.subTest(case=case):
                self.assertEqual(output, expected_cidrs(input_union(lines)))
            output, _ = successful(lines, "-q", "-r")
            with self.subTest(case=case, ranges=True):
                check_coverage(lines, output, "0", ranges=True)

    def test_reordering_and_duplicates_do_not_change_results(self):
        rng = random.Random(0xD3E7)
        inputs = [
            "0.0.0.0/31",
            "0.0.0.3",
            "10.1.0.0/24",
            "10.1.1.1-10.1.1.9",
            "255.255.255.255",
        ]
        for percent in ["0", "1", "10", "100"]:
            for ranges in [False, True]:
                flags = ("-r",) if ranges else ()
                expected, _ = successful(inputs, "-q", "-p", percent, *flags)
                shuffled = inputs * 3
                rng.shuffle(shuffled)
                shuffled += ["# comment", "", "10.1.0.32"]
                actual, _ = successful(shuffled, "-q", "-p", percent, *flags)
                with self.subTest(percent=percent, ranges=ranges):
                    self.assertEqual(actual, expected)

    def test_approximate_output_reparsed_exactly_has_same_coverage(self):
        rng = random.Random(0x1D3)
        for case in range(75):
            inputs = mixed_inputs(rng)
            percent = rng.choice(["0.1", "1", "5", "25", "50", "200"])
            for ranges in [False, True]:
                flags = ("-r",) if ranges else ()
                output, _ = successful(inputs, "-q", "-p", percent, *flags)
                reparsed, _ = successful(output, "-q", *flags)
                with self.subTest(case=case, ranges=ranges):
                    self.assertEqual(reparsed, output)


if __name__ == "__main__":
    unittest.main()
