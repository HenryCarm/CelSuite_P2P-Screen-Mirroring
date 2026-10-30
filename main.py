#!/usr/bin/env python3
"""
ScrcpyUltimateLink — Wireless Screen Mirroring & Control Suite

This is the thin entry point. All application logic lives in the src/ package.
"""

import sys

from src.app import main

if __name__ == "__main__":
    sys.exit(main())
