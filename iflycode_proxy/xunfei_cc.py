"""xunfei-cc — CLI shortcut for iflycode-proxy serve.

Usage:
    xunfei-cc serve [-p PORT] [--service]   # Start proxy
    xunfei-cc version                        # Show version
    xunfei-cc --help                         # All options
"""
import sys
import subprocess
import shlex


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ["serve"]

    # Resolve iflycode-proxy to the right python module call
    cmd = [sys.executable, "-m", "iflycode_proxy.cli"] + args

    if "-v" in args:
        print(f"xunfei-cc 1.0.0 → {' '.join(shlex.quote(a) for a in cmd)}")
        return

    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()