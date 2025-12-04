m_values = [0.89413, 0.89767, 0.89799, 0.89638, 0.89606, 0.90777, 0.90833, 0.91308, 0.89254]
print(f"m_promedio: {sum(m_values)/len(m_values)}")
x_values = []
x = 0
for i in range(len(m_values)):
    print(m_values[i]*20 + 8.11912)
    x_values.append(m_values[i]*20 + 8.11912)   
    x += m_values[i]*20 + 8.11912
M = 0
for i in range(len(x_values)):
    M += (x_values[i]-(x/len(m_values)))**2
Desv = ((M/len(m_values))/len(m_values))**0.5
print(f" desviacion estandar: {Desv}")
print(f" max: {max(x_values)}")
print(f"min: {min(x_values)}")
print(f"diference: {max(x_values)-min(x_values)}")
print(F"diference_summary")
print(f"promedio {x/len(m_values)}")
