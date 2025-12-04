import pkgutil

def listar_modulos_pyqt():
    print("=== BUSCANDO LIBRERÍAS PyQt Y PySide INSTALADAS ===\n")

    posibles = [
        "PyQt6", "PyQt5", 
        "PySide6", "PySide2",
        "qtpy", "pyqtgraph"
    ]

    for pkg in posibles:
        try:
            __import__(pkg)
            print(f"✔ {pkg} está instalado")
        except ImportError:
            print(f"✖ {pkg} NO está instalado")

    print("\n=== MÓDULOS PyQt DETECTADOS ===")
    for module in pkgutil.iter_modules():
        if "qt" in module.name.lower() or "pyqt" in module.name.lower():
            print("•", module.name)

listar_modulos_pyqt()
