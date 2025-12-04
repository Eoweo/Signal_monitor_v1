import os
import json
import numpy as np
import pyqtgraph as pg
from pyqtgraph import InfiniteLine, TextItem
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox
)
from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal, QTimer
from backend import SerialReader, ErrorWindow


MAX_POINTS = 10000        # buffer circular
UPDATE_INTERVAL_MS = 50   # frecuencia de refresco gráfico (5 Hz)
DISPLAY_DELAY = 0.2       # segundos de retraso visual


def timeformat(seconds):
    m = int(seconds // 60)
    h = int(m // 60)
    s_string = "{0:.1f}".format(seconds % 60)
    return f"{h:02d}:{m % 60:02d}:{s_string}"


class RecordingWindow(QWidget):
    stop_recording_signal = pyqtSignal()

    def __init__(self, port, file_path):
        super().__init__()

        # --- Buffers prealocados ---
        self.index = 0
        self.full = False
        self.time = np.zeros(MAX_POINTS)
        self.raw_pressure = np.zeros(MAX_POINTS)
        self.pressure = np.zeros(MAX_POINTS)
        self.temperature = np.zeros(MAX_POINTS)
        self.flow = np.zeros(MAX_POINTS)

        self.time_range = 7 * 24 * 60 * 60
        self.serial_reader = SerialReader(file_path, port)
        self.stop_recording_signal.connect(self.serial_reader.end_reading)
        self.serial_reader.readings.connect(self.process_new_data)
        self.serial_reader.warning_signal.connect(lambda msg: ErrorWindow(msg).exec())
        self.manual_ylim_pressure = None
        self.manual_ylim_temp = None
        self.manual_ylim_flow = None

        pg.setConfigOptions(antialias=True, background='k', foreground='w', useOpenGL=True)
        self.init_ui()

        # --- Temporizador de actualización ---
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_graphs)
        self.update_timer.start(UPDATE_INTERVAL_MS)

    def init_ui(self):
        self.setWindowTitle("Eoweo Recorder (Optimizado)")
        vbox = QVBoxLayout()

        # --- Control row ---
        self.label_t_window = QLabel("Ventana de tiempo (s)")
        self.seconds_box = QLineEdit("")
        self.seconds_box.setDisabled(True)
        self.set_button = QPushButton("Aplicar")
        self.set_button.clicked.connect(self.adjust_time)
        self.scale_drop = QComboBox()
        self.scale_drop.addItems(["Completo", "Segundos", "Minutos", "Horas"])
        self.scale_drop.currentIndexChanged.connect(self.full_mode)
        self.hito_input = QLineEdit("")
        self.hito_input.setPlaceholderText("Escribir hito")
        self.hito_button = QPushButton("Hito")
        self.hito_button.clicked.connect(self.send_hito_event)

        hbox1 = QHBoxLayout()
        for w in [self.label_t_window, self.seconds_box, self.scale_drop,
                  self.set_button, self.hito_input, self.hito_button]:
            hbox1.addWidget(w)
        vbox.addLayout(hbox1)

        # --- Gráficos ---
        def create_plot(title, color):
            glw = pg.GraphicsLayoutWidget()
            plot = glw.addPlot(title=title)
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.hideButtons()
            curve = plot.plot(pen=pg.mkPen(color, width=2))
            return glw, plot, curve

        self.pressure_widget, self.pressure_plot, self.pressure_curve = create_plot("Presión", 'r')
        self.flow_widget, self.flow_plot, self.flow_curve = create_plot("Flujo", 'g')
        self.temp_widget, self.temp_plot, self.temp_curve = create_plot("Temperatura", 'b')

        gbox = QGridLayout()
        gbox.addWidget(self.pressure_widget)
        gbox.addWidget(self.flow_widget)
        gbox.addWidget(self.temp_widget)
        vbox.addLayout(gbox)

        # --- Labels ---
        self.time_label = QLabel("Tiempo: --")
        self.current_value_label = QLabel("Valores actuales: --")
        vbox.addWidget(self.time_label)
        vbox.addWidget(self.current_value_label)

        # --- Botones ---
        self.start_button = QPushButton("Empezar")
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button = QPushButton("Parar")
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.hide()
        hbox_controls = QHBoxLayout()
        hbox_controls.addWidget(self.start_button)
        hbox_controls.addWidget(self.stop_button)
        vbox.addLayout(hbox_controls)

        self.setLayout(vbox)

    # --- Adquisición ---
    def process_new_data(self, json_data):
        """Recibe datos JSON y los guarda en buffer circular."""
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError:
            return

        t = data["time"]
        i = self.index

        self.time[i] = t
        self.raw_pressure[i] = data["raw"]
        self.pressure[i] = data["pressure"]
        self.temperature[i] = data["temp"]
        self.flow[i] = data["flow"]

        self.index = (i + 1) % MAX_POINTS
        if self.index == 0:
            self.full = True

        if data.get("event"):
            self._add_event_marker(t, data["event"])

    def _add_event_marker(self, t, label):
        """Dibuja marcador de evento."""
        for plot in [self.pressure_plot, self.temp_plot, self.flow_plot]:
            line = InfiniteLine(pos=t, angle=90,
                                pen=pg.mkPen((200, 200, 200), style=QtCore.Qt.PenStyle.DashLine))
            text = TextItem(label, anchor=(0, 1), color=(255, 255, 255))
            plot.addItem(line)
            plot.addItem(text)
            y_top = plot.viewRange()[1][1]
            text.setPos(t, y_top - 0.05 * abs(y_top))
            if not hasattr(plot, "event_markers"):
                plot.event_markers = []
            plot.event_markers.append((t, text, line))
            if len(plot.event_markers) > 50:  # limpiar exceso
                old_t, old_text, old_line = plot.event_markers.pop(0)
                plot.removeItem(old_text)
                plot.removeItem(old_line)

    # --- Actualización gráfica ---
    def update_graphs(self):
        if self.index == 0 and not self.full:
            return

        # --- datos ordenados ---
        if self.full:
            idx = self.index
            t = np.concatenate((self.time[idx:], self.time[:idx]))
            p = np.concatenate((self.pressure[idx:], self.pressure[:idx]))
            f = np.concatenate((self.flow[idx:], self.flow[:idx]))
            temp = np.concatenate((self.temperature[idx:], self.temperature[:idx]))
        else:
            t = self.time[:self.index]
            p = self.pressure[:self.index]
            f = self.flow[:self.index]
            temp = self.temperature[:self.index]

        if len(t) == 0:
            return  # nada que mostrar aún

        # --- ventana temporal ---
        t_max = t[-1] - DISPLAY_DELAY
        if t_max <= 0:
            return
        t_min = max(t_max - self.time_range, 0)
        mask = (t >= t_min) & (t <= t_max)
        t, p, f, temp = t[mask], p[mask], f[mask], temp[mask]

        if len(t) == 0:
            return  # no hay puntos en la ventana

        # --- decimación ---
        if len(t) > 5000:
            step = len(t) // 5000
            t, p, f, temp = t[::step], p[::step], f[::step], temp[::step]

        # --- ploteo ---
        factor = self.serial_reader.unit_factors[self.serial_reader.unit]
        self.pressure_curve.setData(t, p * factor)
        self.flow_curve.setData(t, f)
        self.temp_curve.setData(t, temp)

        for plot in [self.pressure_plot, self.temp_plot, self.flow_plot]:
            plot.setXRange(t_min, t_max, padding=0)

        # --- labels ---
        try:
            self.time_label.setText(f"Tiempo Actual: {timeformat(t_max)}")
            self.current_value_label.setText(
                f"Presión: {p[-1]*factor:.2f} {self.serial_reader.unit} | "
                f"Temp: {temp[-1]:.2f}°C | Flujo: {f[-1]:.2f} L/min"
            )
        except IndexError:
            pass  # seguridad adicional (en caso de que arrays estén vacíos)

    # --- Control general ---
    def send_hito_event(self):
        text = self.hito_input.text().strip()
        if text:
            self.serial_reader.add_hito(text)
            self.hito_input.clear()

    def adjust_time(self):
        idx = self.scale_drop.currentIndex()
        try:
            if idx == 0:
                self.time_range = 7 * 24 * 60 * 60
            else:
                t = float(self.seconds_box.text())
                if idx == 2:
                    t *= 60
                elif idx == 3:
                    t *= 3600
                self.time_range = t
        except:
            ErrorWindow("Ventana de tiempo debe ser numérica.").exec()
        self.update_graphs()

    def start_recording(self):
        self.serial_reader.start()
        self.start_button.hide()
        self.stop_button.show()

    def stop_recording(self):
        self.stop_recording_signal.emit()
        self.close()

    def full_mode(self, index):
        self.seconds_box.setDisabled(index == 0)

    def closeEvent(self, event):
        self.stop_recording_signal.emit()
        event.accept()
