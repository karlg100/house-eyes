#!/usr/bin/env python3
"""Thanksgiving turkey eyes and beak; accepts tri-eyes.py projection options."""
import os
import runpy
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.argv[1:1] = ["--theme", "thanksgiving", "--no-rogue"]
runpy.run_path("tri-eyes.py", run_name="__main__")
