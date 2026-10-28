"""Independent IPv4 interval oracle and subprocess helpers for CLI tests."""

import ipaddress
import os
import subprocess
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get("CIDR_SQUASH_BIN", ROOT / "build/release/cidr-squash"))
IPV4_SIZE = 1 << 32


def address(number):
    return str(ipaddress.IPv4Address(number))


def number(value):
    return int(ipaddress.IPv4Address(value))


def union(intervals):
    """Canonicalize closed intervals without enumerating IPv4 addresses."""
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def cardinality(intervals):
    return sum(hi - lo + 1 for lo, hi in intervals)


def input_union(lines):
    intervals = []
    for raw in lines:
        item = raw.split("#", 1)[0].strip()
        if not item:
            continue
        if "-" in item:
            left, right = (part.strip() for part in item.split("-", 1))
            intervals.append((number(left), number(right)))
        elif "/" in item:
            net = ipaddress.IPv4Network(item, strict=False)
            intervals.append((int(net.network_address), int(net.broadcast_address)))
        else:
            ip = number(item)
            intervals.append((ip, ip))
    return union(intervals)


def expected_cidrs(intervals):
    networks = []
    for lo, hi in union(intervals):
        networks.extend(
            ipaddress.summarize_address_range(
                ipaddress.IPv4Address(lo), ipaddress.IPv4Address(hi)
            )
        )
    return [str(net) for net in ipaddress.collapse_addresses(networks)]


def parse_cidrs(lines):
    intervals = []
    for line in lines:
        network = ipaddress.IPv4Network(line, strict=True)
        assert line == str(network), f"noncanonical CIDR: {line}"
        lo = int(network.network_address)
        hi = int(network.broadcast_address)
        if intervals:
            assert lo > intervals[-1][1], f"overlapping/out-of-order CIDRs: {lines}"
        intervals.append((lo, hi))
    return intervals


def parse_ranges(lines):
    intervals = []
    for line in lines:
        assert line.count("-") == 1, f"malformed range: {line}"
        left, right = line.split("-")
        lo, hi = number(left), number(right)
        assert left == address(lo) and right == address(hi), line
        assert lo <= hi, f"reversed range: {line}"
        if intervals:
            assert lo > intervals[-1][1] + 1, f"unmerged ranges: {lines}"
        intervals.append((lo, hi))
    return intervals


def extra_count(expected, actual):
    """Count IPv4 addresses in actual that are absent from expected."""
    expected = union(expected)
    actual = union(actual)
    overlap = 0
    i = j = 0
    while i < len(expected) and j < len(actual):
        a, b = expected[i]
        c, d = actual[j]
        overlap += max(0, min(b, d) - max(a, c) + 1)
        if b < d:
            i += 1
        else:
            j += 1
    return cardinality(actual) - overlap


def budget_for(expected, percent):
    count = cardinality(expected)
    requested = int(Decimal(count) * Decimal(str(percent)) / 100)
    return min(requested, IPV4_SIZE - count)


def run_tool(lines=(), *args, filename=None, timeout=8):
    data = "\n".join(lines)
    if lines:
        data += "\n"
    command = [str(BINARY), *args]
    if filename is not None:
        command.append(str(filename))
    return subprocess.run(
        command,
        input=data,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def successful(lines=(), *args, filename=None):
    proc = run_tool(lines, *args, filename=filename)
    assert proc.returncode == 0, (proc.returncode, proc.stderr, proc.stdout)
    return proc.stdout.splitlines(), proc.stderr


def check_coverage(lines, result, percent, ranges):
    expected = input_union(lines)
    actual = parse_ranges(result) if ranges else parse_cidrs(result)
    assert extra_count(actual, expected) == 0, "original addresses lost"
    excess = extra_count(expected, actual)
    assert excess <= budget_for(expected, percent), (excess, percent)
    return excess
