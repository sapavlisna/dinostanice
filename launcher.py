"""Vstupní bod balíku pro Windows (PyInstaller).

Dělá totéž co `start.ps1`: najde LAN adresu, vybere volný port, vypíše adresy
pro televizi i pro mobil a otevře scénu v prohlížeči. Konzolové okno je jediná
nápověda, kterou uživatel u exe má, takže se v něm ty adresy musí objevit.
"""

import ctypes
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser

DEFAULT_PORT = 8100
PORT_TRIES = 50


def console_utf8():
    # bez tohohle vypíše konzole diakritiku v hláškách jako mojibake
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def lan_ip():
    """Adresa, na které stanici uvidí mobil. Spojení se neotevírá, jen se
    routovací tabulky zeptáme, kterým rozhraním by šlo do světa."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def free_port(start):
    for port in range(start, start + PORT_TRIES):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                continue
        return port
    return start


def open_when_ready(url):
    """Scéna se otevře až server odpoví, jinak by prohlížeč ukázal chybu."""
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/api/scenes", timeout=2):
                webbrowser.open(url)
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)


def main(argv):
    console_utf8()
    no_browser = "--nobrowser" in argv or "-NoBrowser" in argv
    port = None
    for flag in ("--port", "-Port"):
        if flag in argv:
            try:
                port = int(argv[argv.index(flag) + 1])
            except (IndexError, ValueError):
                pass
    if port is None:
        port = int(os.environ.get("DINO_PORT") or DEFAULT_PORT)

    chosen = free_port(port)
    if chosen != port:
        print(f"\n  Port {port} drží něco jiného, beru {chosen}.")
    port = chosen
    # QR kód se generuje z adresy požadavku; když je scéna otevřená přes
    # localhost bez portu v URL, port musí přijít odsud
    os.environ["DINO_PORT"] = str(port)

    from dinostanice import paths

    ip = lan_ip()
    print()
    print("  DinoStanice")
    print()
    print(f"  Scéna na televizi:  http://{ip}:{port}/")
    print(f"  Mobil - fotografie: http://{ip}:{port}/pridat")
    print(f"  Šablony k tisku:    http://{ip}:{port}/sablony")
    print()
    print(f"  Úlovky se ukládají do: {paths.data_root()}")
    print("  Mobil musí být na stejné wifi. Ukončení serveru: Ctrl+C")
    print()

    if not no_browser:
        threading.Thread(target=open_when_ready,
                         args=(f"http://127.0.0.1:{port}",), daemon=True).start()

    import uvicorn

    from server import app

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    import multiprocessing

    # bez tohohle by případný spawn v balíku spustil celý launcher znovu
    multiprocessing.freeze_support()
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        # při spuštění dvojklikem by se okno s chybou zavřelo dřív, než ji kdo přečte
        input("\n  Něco se pokazilo. Enter zavře okno...")
        sys.exit(1)
