import pandas as pd
import matplotlib.pyplot as plt
import glob
import os

# Lista de archivos a graficar
archivos = [
    "tests/Ev_dif_pres_sist_trans.csv",
    "tests/ev_dif_presion(amortiguado).csv",
    "tests/ev_dif_presion(ExtraFull_amortiguado).csv",
    "tests/ev_dif_presion(Full_amortiguado).csv",
    "tests/flujo_var_pp5mmhg.csv"
]

plt.figure(figsize=(12, 7))

for archivo in archivos:
    # Leer el CSV (autodetecta separador)
    df = pd.read_csv(archivo, sep=None, engine='python')
    
    # Limpiar nombres de columnas
    df.columns = df.columns.str.strip().str.replace('"', '')
    
    # Mostrar columnas detectadas (solo la primera vez)
    print(f"\nArchivo: {os.path.basename(archivo)}")
    print("Columnas detectadas:", df.columns.tolist())
    
    # Asegurar que Tiempo es numérico
    if 'Tiempo' in df.columns:
        df['Tiempo'] = pd.to_numeric(df['Tiempo'], errors='coerce')
    else:
        print("⚠️ No se encontró la columna 'Tiempo' en", archivo)
        continue
    
    # Asegurar que exista la columna de presión
    pres_col = next((col for col in df.columns if 'Presion' in col or 'Presión' in col), None)
    if not pres_col:
        print("⚠️ No se encontró columna de presión en", archivo)
        continue
    
    # Graficar presión vs tiempo
    nombre = os.path.splitext(os.path.basename(archivo))[0]
    plt.plot(df['Tiempo'], df[pres_col], label=nombre, linewidth=2)
    
    # Dibujar líneas verticales para Hitos (si existen)
    if 'Hitos' in df.columns:
        for _, row in df.dropna(subset=['Hitos']).iterrows():
            plt.axvline(x=row['Tiempo'], color='red', linestyle='--', alpha=0.3)
            plt.text(row['Tiempo'], df[pres_col].max()*0.95, str(row['Hitos']),
                     rotation=90, verticalalignment='top', color='red', fontsize=7)

plt.xlabel('Tiempo')
plt.ylabel('Presión (mmHg)')
plt.title('Comparación de Presión vs Tiempo entre diferentes archivos')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
