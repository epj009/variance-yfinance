#!/usr/bin/env python3
import os
import sys

# Allow importing from src without installation (for dev convenience)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from variance.analyze_portfolio import main

if __name__ == "__main__":
    main()
