
import pandas as pd
import matplotlib.pyplot as plt
##Ev_dif_pres_sist_trans.csv
##ev_dif_presion(amortiguado).csv
##ev_dif_presion(ExtraFull_amortiguado).csv
##ev_dif_presion(Full_amortiguado).csv
##flujo_var_pp5mmhg.csv

# Read the CSV file (detects separators like space, tab, or comma)
df = pd.read_csv('tests/flujo_var_pp5mmhg.csv', sep=None, engine='python')

# Clean column names (remove quotes and spaces)
df.columns = df.columns.str.strip().str.replace('"', '')

print("Column names detected:", df.columns.tolist())
print(df.head())

# Convert Tiempo to numeric (since it looks like numeric seconds or similar)
df['Tiempo'] = pd.to_numeric(df['Tiempo'], errors='coerce')

# Plot Presion vs Tiempo
plt.figure(figsize=(10, 6))
plt.plot(df['Tiempo'], df['Presion (mmHg)'], label='Presión (mmHg)', linewidth=2)

# Add Hitos if present and non-empty
if 'Hitos' in df.columns:
    for i, row in df.dropna(subset=['Hitos']).iterrows():
        plt.axvline(x=row['Tiempo'], color='red', linestyle='--', alpha=0.7)
        plt.text(row['Tiempo'], df['Presion (mmHg)'].max()*0.95, str(row['Hitos']),
                 rotation=90, verticalalignment='top', color='red', fontsize=8)

plt.xlabel('Tiempo')
plt.ylabel('Presión (mmHg)')
plt.title('Presión vs Tiempo con Hitos')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

