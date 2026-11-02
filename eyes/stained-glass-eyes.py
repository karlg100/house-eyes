#!/usr/bin/env python3
"""Stained-glass eyes and Christmas tree; accepts tri-eyes.py options."""
import os
import runpy
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.argv[1:1] = ["--theme", "stained-glass", "--no-rogue"]
runpy.run_path("tri-eyes.py", run_name="__main__")
