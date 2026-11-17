"""Flags that keep child processes from opening a console window."""

import subprocess

# 0 off Windows, so passing it as creationflags is always safe.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
