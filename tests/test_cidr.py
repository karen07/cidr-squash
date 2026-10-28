"""Exact canonical CIDRs, bounded approximation, and CIDR metamorphic tests."""

import random
import unittest

from test_support import (
    address,
    check_coverage,
    expected_cidrs,
    input_union,
    parse_cidrs,
    successful,
)


class CIDRTests(unittest.TestCase):
    def test_known_exact_outputs(self):
        cases = [
            (["192.168.1.0/25", "192.168.1.128/25"], ["192.168.1.0/24"]),
            (["192.0.2.1", "192.0.2.2"], ["192.0.2.1/32", "192.0.2.2/32"]),
            (["192.0.2.9/24"], ["192.0.2.0/24"]),
            (["192.0.2.0/24", "192.0.2.128/25"], ["192.0.2.0/24"]),
            (["0.0.0.0", "255.255.255.255"], ["0.0.0.0/32", "255.255.255.255/32"]),
            (["0.0.0.0/0"], ["0.0.0.0/0"]),
            (["255.255.255.254/31"], ["255.255.255.254/31"]),
            (["0.0.0.0-0.0.0.3"], ["0.0.0.0/30"]),
        ]
        for inputs, expected in cases:
            with self.subTest(inputs=inputs):
                output, _ = successful(inputs, "-q")
                self.assertEqual(output, expected)

    def test_mixed_input_exact_oracle(self):
        inputs = [
            "192.0.2.192-192.0.3.18",
            "192.0.2.0/26",
            "192.0.2.64/27",
            "192.0.2.12",
            "192.0.2.70-192.0.2.140",
            "192.0.2.0/26",
        ]
        output, _ = successful(inputs, "-q")
        self.assertEqual(output, expected_cidrs(input_union(inputs)))

    def test_fractional_budget_boundary(self):
        inputs = ["192.0.2.0/31", "192.0.2.3"]
        for percent, expected in [
            ("0", ["192.0.2.0/31", "192.0.2.3/32"]),
            ("33", ["192.0.2.0/31", "192.0.2.3/32"]),
            ("34", ["192.0.2.0/30"]),
            ("100", ["192.0.2.0/30"]),
        ]:
            with self.subTest(percent=percent):
                output, _ = successful(inputs, "-q", "-p", percent)
                self.assertEqual(output, expected)
                check_coverage(inputs, output, percent, ranges=False)

    def test_approximate_boundary_full_space(self):
        cases = [
            (["0.0.0.0/0"], "1000000000000"),
            (["0.0.0.0", "255.255.255.255"], "1000000000000"),
            (["0.0.0.0/1", "128.0.0.0/1"], "17"),
            (["255.255.255.254", "255.255.255.255"], "1000"),
        ]
        for inputs, pct in cases:
            with self.subTest(inputs=inputs):
                output, _ = successful(inputs, "-q", "-p", pct)
                check_coverage(inputs, output, pct, ranges=False)

    def test_random_exact_against_python_ipaddress(self):
        rng = random.Random(0xC1D2)
        for case in range(130):
            inputs = [
                address(x) for x in rng.sample(range(1024), rng.randrange(1, 120))
            ]
            inputs += [f"{address(rng.randrange(1024))}/29"]
            output, _ = successful(inputs, "-q")
            with self.subTest(case=case):
                self.assertEqual(output, expected_cidrs(input_union(inputs)))

    def test_random_approximate_never_drops_or_overcovers(self):
        rng = random.Random(0xAC1D)
        percentages = ["0", "0.01", "0.1", "1", "5", "12.5", "25", "100", "300"]
        for case in range(180):
            values = rng.sample(range(2048), rng.randrange(1, 100))
            inputs = [address(n) for n in values]
            percent = rng.choice(percentages)
            output, _ = successful(inputs, "-q", "-p", percent)
            with self.subTest(case=case, percent=percent):
                check_coverage(inputs, output, percent, ranges=False)
                if percent == "0":
                    self.assertEqual(output, expected_cidrs(input_union(inputs)))

    def test_same_union_yields_same_exact_cidrs(self):
        rng = random.Random(0x51DE)
        initial = ["198.51.100.0/25", "198.51.100.128/26", "198.51.100.208"]
        variants = [
            initial,
            list(reversed(initial)) + initial,
            ["198.51.100.0-198.51.100.191", "198.51.100.208"],
            [
                "198.51.100.0/26",
                "198.51.100.64/26",
                "198.51.100.128/26",
                "198.51.100.208",
            ],
        ]
        rng.shuffle(variants)
        outputs = [successful(lines, "-q")[0] for lines in variants]
        self.assertTrue(all(result == outputs[0] for result in outputs))
        self.assertEqual(outputs[0], expected_cidrs(input_union(initial)))

    def test_exact_output_is_idempotent(self):
        original = ["0.0.0.1", "0.0.0.3", "10.0.0.0/9", "255.255.255.255"]
        result, _ = successful(original, "-q")
        again, _ = successful(result, "-q")
        self.assertEqual(again, result)

    def test_approx_output_exact_reparse_preserves_coverage(self):
        inputs = ["192.0.2.0/26", "192.0.2.66/31", "192.0.2.80", "192.0.2.100"]
        output, _ = successful(inputs, "-q", "-p", "20")
        reparsed, _ = successful(output, "-q")
        self.assertEqual(parse_cidrs(reparsed), parse_cidrs(output))


if __name__ == "__main__":
    unittest.main()
