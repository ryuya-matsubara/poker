"""Reproducible public entry point for the pinned 20BB solver pipeline."""
import argparse
from pathlib import Path
from upgrade_solver import upgrade

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source_dir',type=Path)
    upgrade(parser.parse_args().source_dir)
