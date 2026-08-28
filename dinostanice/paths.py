"""Kde leží data.

Z konzole i v Dockeru je všechno pod adresářem projektu. V balíku od
PyInstalleru se ale musí rozdělit dvojí: balená data (`web/`, `data/models3d`,
`data/templates`, `data/shapes3d`) leží v rozbaleném balíku v temp, který se po
vypnutí smaže, kdežto úlovky, koš a nastavení scény musí přežít vypnutí
a nechat se zkopírovat, takže patří vedle exe.
"""

import os
import sys


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> str:
    """Adresář s balenými (read-only) daty."""
    if frozen():
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root() -> str:
    """Adresář se zapisovatelnými daty (úlovky, koš, odmítnuté fotky, state.json)."""
    if frozen():
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "data")
    return os.path.join(resource_root(), "data")
