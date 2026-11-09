"""Точка входа `python -m swarmlab.runner`."""

import os

from swarmlab.runner.main import main

# Выход без остановки интерпретатора: поток-читатель всё ещё ждёт stdin, и Python 3.13
# при обычном выходе падает на его буфере (`_enter_buffered_busy`). Всё, что нужно
# ядру, уже записано и сброшено (`write_frame`).
os._exit(main())
