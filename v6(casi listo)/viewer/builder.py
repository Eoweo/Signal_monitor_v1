import os
import sys
import subprocess
import glob

def build_exe(source_file):
    if not os.path.exists(source_file):
        print(f"ERROR: El archivo {source_file} no existe.")
        return

    print("Detectando imágenes para incluir...")

    # Carpeta donde está main.py
    base_dir = os.path.dirname(os.path.abspath(source_file))

    # Tipos de archivos a incluir
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico"]

    image_files = []
    for pattern in patterns:
        image_files.extend(glob.glob(os.path.join(base_dir, pattern)))

    # Construcción de argumentos --add-data
    add_data_args = []
    for img in image_files:
        # formato: ruta_origen;carpeta_destino
        arg = f"{img}{os.pathsep}."
        add_data_args.append("--add-data")
        add_data_args.append(arg)
        print("  ✔ Añadido:", img)

    # Instalar pyinstaller si no existe
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller no encontrado. Instalando...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    print("\nGenerando ejecutable...")

    # Comando PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--exclude-module", "PyQt5",
    ] + add_data_args + [source_file]

    print("\nEjecutando:")
    print(" ".join(cmd))

    subprocess.run(cmd)

    print("\n===============================")
    print("   ✔ EJECUTABLE GENERADO")
    print("===============================")
    print("Ubicación:", os.path.join(os.getcwd(), "dist"))
    print("===============================")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python build_exe.py main.py")
    else:
        build_exe(sys.argv[1])
