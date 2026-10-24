import sys

if len(sys.argv) == 1:
    from .gui import main
else:
    from .cli import main

raise SystemExit(main())
