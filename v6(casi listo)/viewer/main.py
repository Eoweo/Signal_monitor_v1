import sys
import os
from PyQt6.QtWidgets import ( QApplication, QWidget, QPushButton, 
                             QLabel, QVBoxLayout, QFileDialog, QHBoxLayout)
from PyQt6.QtCore import Qt
import pyqtgraph as pg
import numpy as np
from PyQt6.QtGui import QPixmap
from PyQt6.QtGui import QPalette, QColor, QIcon

def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return filename


def set_dark_mode(app):
    """Applies a consistent dark theme to all widgets, including buttons."""
    dark_palette = QPalette()

    # --- General colors ---
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))

    # --- Links & highlights ---
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

    app.setPalette(dark_palette)

    app.setStyleSheet("""
        QWidget {
            background-color: #2D2D2D;
            color: #DDDDDD;
            selection-background-color: #2A82DA;
        }
        QPushButton {
            background-color: #353535;
            border: 1px solid #444;
            padding: 4px 8px;
            border-radius: 6px;
        }
        QPushButton:hover {
            background-color: #3E3E3E;
        }
        QPushButton:pressed {
            background-color: #2A82DA;
        }
        QLineEdit, QComboBox, QTextEdit {
            background-color: #3A3A3A;
            color: #FFFFFF;
            border: 1px solid #555;
            border-radius: 4px;
        }
        QComboBox QAbstractItemView {
            background-color: #2D2D2D;
            color: #FFFFFF;
            selection-background-color: #2A82DA;
        }
        QLabel {
            color: #DDDDDD;
        }
        QToolTip {
            background-color: #2A82DA;
            color: #000000;
            border: none;
        }
    """)

class PlotWindow(QWidget):

    def __init__(self, t, pressure, temp, flow, events, path):
        super().__init__()
        self.setWindowTitle(f"Visualicer -- {path}")
        self.setWindowIcon(QIcon(resource_path("ico2.png")))
        # ORDENAR POR TIEMPO → ARREGLA LÍNEAS CORTADAS
        order = np.argsort(t)
        self.t = t[order]
        self.p = pressure[order]
        self.temp = temp[order]
        self.flow = flow[order]
        self.events = [events[i] for i in order]

        self.point_A = None
        self.point_B = None

        # LAYOUT GENERAL
        layout = QHBoxLayout(self)

        # CONTENEDOR DE GRÁFICOS
        v = QVBoxLayout()
        layout.addLayout(v)

        # CREAR GRÁFICOS
        self.press_plot = self.create_plot("Presión (mmHg)", "r")
        self.flow_plot = self.create_plot("Flujo (mL/min)", "g")
        self.temp_plot = self.create_plot("Temperatura (°C)", "b")
        # Sincronizar SOLO eje X entre graficos
        self.flow_plot["plot"].setXLink(self.press_plot["plot"])
        self.temp_plot["plot"].setXLink(self.press_plot["plot"])


        v.addWidget(self.press_plot["widget"])
        v.addWidget(self.flow_plot["widget"])
        v.addWidget(self.temp_plot["widget"])

        # DIBUJAR CURVAS (YA ORDENADAS)
        self.press_plot["curve"].setData(self.t, self.p)
        self.flow_plot["curve"].setData(self.t, self.flow)
        self.temp_plot["curve"].setData(self.t, self.temp)

        # EVENTOS
        self.add_events()

    # --------------------------------------------------------
    def create_plot(self, title, color):
        glw = pg.GraphicsLayoutWidget()
        plt = glw.addPlot(title=title)
        plt.showGrid(x=True, y=True, alpha=0.3)

        # 🔥 CONNECT='all' → UNE TODOS LOS PUNTOS
        curve = plt.plot(
            pen=pg.mkPen(color, width=2),
            connect='all'
        )

        return {"widget": glw, "plot": plt, "curve": curve}

    # --------------------------------------------------------
    def add_events(self):
        for i, txt in enumerate(self.events):
            if txt and isinstance(txt, str):
                t_event = self.t[i]
                for d in [self.press_plot, self.flow_plot, self.temp_plot]:
                    line = pg.InfiniteLine(t_event, angle=90,
                                           pen=pg.mkPen((180, 180, 180), style=Qt.PenStyle.DashLine))
                    d["plot"].addItem(line)

class CSVSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(resource_path("ico2.png")))
        self.setWindowTitle("Cargar CSV con Datos")

        self.csv_path = None

        layout = QVBoxLayout()

        self.label = QLabel("Seleccionar archivo CSV")
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.button_load = QPushButton("Elegir CSV")
        self.button_load.clicked.connect(self.load_csv)
        layout.addWidget(self.button_load)

        self.button_set = QPushButton("SET")
        self.button_set.clicked.connect(self.open_plot_window)
        self.button_set.setEnabled(False)
        layout.addWidget(self.button_set)

        

                # ---- LOGO SECTION ----
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setStyleSheet("background: transparent; border: none;")

        self.logo_pixmap = None
        layout.addWidget(self.logo_label)

        # Load the logo
        logo_path = "Logo_2.png"
        if os.path.exists(logo_path):
            self.logo_pixmap = QPixmap(resource_path(logo_path))
            self._update_logo_size()
        self.setLayout(layout)
    # -------------------------------
    def load_csv(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo CSV",
            "",
            "CSV Files (*.csv)"
        )
        if file:
            self.csv_path = file
            self.label.setText(f"Archivo seleccionado:\n{file}")
            self.button_set.setEnabled(True)

    # -------------------------------
    def open_plot_window(self):
        if not self.csv_path:
            return

        t = []
        p = []
        temp = []
        flow = []
        events = []

        with open(self.csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Saltar la primera (header real)
        for line in lines[1:]:
            line = line.strip()

            # Saltar líneas vacías
            if not line:
                continue

            parts = line.split(",")

            # Saltar líneas con estructura incorrecta
            if len(parts) < 4:
                continue

            # Validar que la primera columna sea un número
            try:
                t_val = float(parts[0])
            except:
                continue  # Ignorar líneas como "Time,Pressure..."

            # Ahora sí es una línea válida
            t.append(t_val)
            p.append(float(parts[1]))
            temp.append(float(parts[2]))
            flow.append(float(parts[3]))

            # Event puede venir vacío
            events.append(parts[4] if len(parts) > 4 else "")

        t = np.array(t)
        p = np.array(p)
        temp = np.array(temp)
        flow = np.array(flow)

        # Mostrar gráfica
        self.plot_window = PlotWindow(t, p, temp, flow, events, path=self.csv_path)
        self.plot_window.show()
    def _update_logo_size(self):
        """Resize logo to a small fixed maximum size."""
        if not self.logo_pixmap:
            return

        max_width = 150  # <<< ADJUST LOGO SIZE HERE
        scaled = self.logo_pixmap.scaledToWidth( max_width, 
                                                Qt.TransformationMode.SmoothTransformation)
        self.logo_label.setPixmap(scaled)
    
    def resizeEvent(self, event):
        """Update logo size dynamically on resize."""
        super().resizeEvent(event)
        self._update_logo_size()

# ============================================================
# === Programa principal ====================================
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    set_dark_mode(app)
    win = CSVSelector()
    win.show()
    sys.exit(app.exec())
