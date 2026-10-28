"""End-to-end command line, parsing, diagnostics, and streaming checks."""

import re
import tempfile
import unittest
from pathlib import Path

from test_support import check_coverage, run_tool, successful


class CLITests(unittest.TestCase):
    def test_help_and_unknown_option(self):
        for option in ["-h", "--help"]:
            with self.subTest(option=option):
                proc = run_tool((), option)
                self.assertEqual(proc.returncode, 0)
                self.assertIn("Usage:", proc.stdout)
                self.assertIn("--ranges", proc.stdout)
        for option in ["-z", "--invalid", "--ranges=true"]:
            with self.subTest(option=option):
                proc = run_tool((), option)
                self.assertEqual(proc.returncode, 2)
                self.assertIn("Usage:", proc.stderr)

    def test_stdin_explicit_dash_and_file_agree(self):
        inputs = ["192.0.2.0/25", "192.0.2.128/25"]
        piped, _ = successful(inputs, "-q")
        explicit, _ = successful(inputs, "-q", "-")
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "source.txt"
            filename.write_text("\n".join(inputs) + "\n", encoding="ascii")
            from_file, _ = successful((), "-q", filename=filename)
        self.assertEqual(piped, explicit)
        self.assertEqual(piped, from_file)
        self.assertEqual(piped, ["192.0.2.0/24"])

    def test_empty_and_comments_only(self):
        for inputs in [[], ["", "# comment", "   ", "  # another comment"]]:
            for flags in [(), ("--ranges",)]:
                with self.subTest(inputs=inputs, flags=flags):
                    output, stderr = successful(inputs, *flags)
                    self.assertEqual(output, [])
                    self.assertIn("no IPv4 entries", stderr)
                    quiet_output, quiet_stderr = successful(inputs, "-q", *flags)
                    self.assertEqual(quiet_output, [])
                    self.assertEqual(quiet_stderr, "")

    def test_inline_comments_whitespace_and_eof_without_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "input.txt"
            filename.write_text(
                " # ignored\n 192.0.2.1 - 192.0.2.2 # inline\n192.0.2.3",
                encoding="ascii",
            )
            result, _ = successful((), "--ranges", "-q", filename=filename)
        self.assertEqual(result, ["192.0.2.1-192.0.2.3"])

    def test_invalid_address_prefix_and_range(self):
        bad_lines = [
            "192.0.2.256",
            "256.0.0.1",
            "192.0.2",
            "192.0.2.1.2",
            "192.0.2.1/33",
            "192.0.2.1/-1",
            "192.0.2.1/24junk",
            "192.0.2.9-192.0.2.1",
            "192.0.2.1-192.0.2.256",
            "192.0.2.1-foo",
            "hello",
            "2001:db8::1",
        ]
        for line in bad_lines:
            with self.subTest(line=line):
                result = run_tool(["# comment", "192.0.2.0/24", line], "-q")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid input at line 3", result.stderr)

    def test_invalid_percentage(self):
        for value in ["nan", "inf", "-1", "junk", "5%", "1.2bad", "1e99999"]:
            with self.subTest(value=value):
                proc = run_tool(["192.0.2.1"], "-p", value)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("invalid -p", proc.stderr)
        proc = run_tool(["192.0.2.1"], "-p")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("requires a value", proc.stderr)

    def test_missing_file_and_two_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.txt"
            second = Path(directory) / "second.txt"
            first.write_text("192.0.2.1\n", encoding="ascii")
            second.write_text("192.0.2.2\n", encoding="ascii")
            missing = run_tool((), filename=Path(directory) / "missing.txt")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("cannot open", missing.stderr)
            both = run_tool((), str(first), filename=second)
            self.assertNotEqual(both.returncode, 0)
            self.assertIn("only one input file", both.stderr)

    def test_oversized_input_line(self):
        proc = run_tool(["192.0.2.1 " + " " * 300])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("line 1 too long", proc.stderr)

    def test_quiet_mode_and_statistics_match_coverage(self):
        inputs = ["192.0.2.0/31", "192.0.2.3"]
        for flags in [(), ("-r",)]:
            with self.subTest(flags=flags):
                output, stderr = successful(inputs, "-p", "34", *flags)
                overage = check_coverage(inputs, output, "34", ranges=bool(flags))
                self.assertEqual(overage, 1)
                self.assertRegex(stderr, r"extra IPv4 covered:\s+1\b")
                self.assertRegex(stderr, r"exact IPv4 covered:\s+3\b")
                self.assertRegex(stderr, r"budget:\s+1 IPv4")
                quiet, quiet_stderr = successful(inputs, "-q", "-p", "34", *flags)
                self.assertEqual(output, quiet)
                self.assertEqual(quiet_stderr, "")
                for line in output:
                    self.assertNotRegex(line, r"\s")

    def test_many_inputs_with_duplicates_and_reverse_order(self):
        inputs = ["198.51.100.0/24"]
        inputs += [f"198.51.100.{n}" for n in reversed(range(256))]
        inputs *= 12
        for args, expected in [
            (("-q",), ["198.51.100.0/24"]),
            (("-q", "-r"), ["198.51.100.0-198.51.100.255"]),
        ]:
            with self.subTest(args=args):
                result, _ = successful(inputs, *args)
                self.assertEqual(result, expected)

    def test_no_unexpected_debug_output(self):
        lines = ["203.0.113.0/30", "203.0.113.8/30"]
        proc = run_tool(lines, "-q", "-p", "10")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        self.assertTrue(
            all(
                re.fullmatch(r"\d+\.\d+\.\d+\.\d+/\d+", line)
                for line in proc.stdout.splitlines()
            )
        )


if __name__ == "__main__":
    unittest.main()
