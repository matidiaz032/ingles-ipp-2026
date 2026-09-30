"""Arma mobile/ipp-mobile.zip: la app lista para correr en el celular con Termux.

    python tools/make_mobile_zip.py            # incluye una copia de tu progreso actual
    python tools/make_mobile_zip.py --sin-progreso   # genera ipp-mobile-update.zip: actualiza el código SIN pisar el progreso del celular

El zip queda en tu PC (no se sube a ningún lado). Pasalo al celular por USB, Drive, Telegram, etc."""
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "mobile"

START_SH = """#!/data/data/com.termux/files/usr/bin/bash
# Arranca la app de práctica. Después abrí Chrome en:  http://localhost:8765
cd "$(dirname "$0")"
termux-wake-lock 2>/dev/null   # evita que Android duerma Termux mientras practicás
echo ""
echo "  Práctica IPP lista. Abrí Chrome y entrá a:  http://localhost:8765"
echo "  (para cerrar la app: Ctrl + C, o deslizá la notificación de Termux)"
echo ""
python app/server.py --no-browser
"""

LEEME = """PRACTICA IPP EN EL CELULAR (Termux)
====================================

PRIMERA VEZ (unos 15-30 minutos)
1) Instalá Termux. NO uses la versión de Google Play (está desactualizada).
   - Opción simple: en el celular abrí  https://github.com/termux/termux-app/releases  y bajá el APK que
     diga "apt-android-7" y "universal" (o "arm64-v8a"). Android te va a pedir permiso para "instalar apps
     desconocidas" para tu navegador: aceptalo.
   - Alternativa: instalar F-Droid (f-droid.org) y desde ahí buscar Termux.
2) Guardá este archivo (ipp-mobile.zip) en la carpeta DESCARGAS / Download del celular
   (por USB, Google Drive, Telegram, email...).
3) Abrí Termux. Pegá estos comandos de a uno (mantené apretado en la pantalla > Pegar) y apretá Enter:

     termux-setup-storage
       -> te pide permiso de archivos: tocá "Permitir"

     pkg update -y && pkg install -y python
       -> si te hace preguntas tipo [Y/n/I/N/O/D/Z], apretá Enter para dejar la opción por defecto

     python -m zipfile -e ~/storage/downloads/ipp-mobile.zip ~

     bash ~/ipp/start.sh

4) Abrí Chrome y entrá a  http://localhost:8765  -> ya podés practicar, sin internet.
   Tip: en Chrome menú (tres puntos) > "Agregar a pantalla principal" para tener un acceso directo.

LAS PROXIMAS VECES
- Abrí Termux, escribí   bash ~/ipp/start.sh   (o tocá la flecha arriba del teclado para repetir el comando),
  y abrí Chrome en http://localhost:8765
- Para que Android no lo cierre: Ajustes > Batería > Termux > "Sin restricciones".

SINCRONIZACION AUTOMATICA (opcional, recomendada)
1) Instalá Syncthing-Fork (F-Droid) en el celular y Syncthing en la PC, y compartí UNA carpeta entre los dos.
   En el celular creala en el almacenamiento interno, por ejemplo  IPP-sync  (queda en /storage/emulated/0/IPP-sync).
2) En la app del celular: Progreso > "Sincronización automática":
     Nombre del dispositivo:  celu
     Carpeta compartida:      /data/data/com.termux/files/home/storage/shared/IPP-sync
   (es la misma carpeta vista desde Termux; hace falta haber corrido  termux-setup-storage ).  > Guardar y sincronizar.
3) En la app de la PC: mismo lugar, nombre  pc  y la ruta de esa carpeta en la PC.
Cada ~45 segundos cada dispositivo guarda sus respuestas y lee las del otro. No hace falta hacer nada más.

SINCRONIZAR EL PROGRESO A MANO (alternativa)
- En el celular: Progreso > "Exportar progreso". Se baja un archivo ipp-progreso-....json a Descargas.
- Mandate ese archivo a la PC y en la PC: Progreso > "Importar progreso".
- Y al revés (PC > celular) igual. Se puede repetir las veces que quieras: no duplica ni pierde respuestas.

Si algo falla: cerrá Termux del todo y repetí solo el último comando (bash ~/ipp/start.sh).
"""


def snapshot_db(dest: Path) -> bool:
    src = ROOT / "data" / "progress.sqlite"
    if not src.exists():
        return False
    con = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)   # solo lectura
    out = sqlite3.connect(dest)
    con.backup(out)
    out.close()
    con.close()
    return True


def main():
    with_progress = "--sin-progreso" not in sys.argv
    OUT = OUT_DIR / ("ipp-mobile.zip" if with_progress else "ipp-mobile-update.zip")
    OUT_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for base in ("app", "data"):
            for f in sorted((ROOT / base).rglob("*")):
                if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".sqlite" or f.name in ("hf_token.txt", "sync.json") or f.name.endswith(".sqlite-journal"):
                    continue
                z.write(f, Path("ipp") / f.relative_to(ROOT))
        included = False
        if with_progress:
            snap = Path(tmp) / "progress.sqlite"
            if snapshot_db(snap):
                z.write(snap, "ipp/data/progress.sqlite")
                included = True
        z.writestr("ipp/start.sh", START_SH)
        z.writestr("ipp/LEEME-CELULAR.txt", LEEME)
    print(f"Listo: {OUT}  ({OUT.stat().st_size // 1024} KB)  | progreso incluido: {'sí' if included else 'no'}")


if __name__ == "__main__":
    main()
