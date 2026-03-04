#!/usr/bin/env python3
import os
import sys

# Ensure server/ is on sys.path
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from worker.worker import run

if __name__ == "__main__":
    run()
