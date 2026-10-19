#!/usr/bin/env python3
import os
import sys
from pathlib import Path

if sys.argv[1:3] == ["api", "snapshot"]:
    print(Path(os.environ["FAKE_HERDR_SNAPSHOT"]).read_text(), end="")
else:
    with open(os.environ["FAKE_HERDR_LOG"], "a") as log:
        print(" ".join(sys.argv[1:]), file=log)
