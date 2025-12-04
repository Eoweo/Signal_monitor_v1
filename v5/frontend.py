import numpy as np
import pyqtgraph as pg
from pyqtgraph import InfiniteLine, TextItem
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox
)
from PyQt6.QtCore import pyqtSignal, QTimer
from backend import SerialReader, DataRecorder
from collections import deque
from threading import Lock

MAX_VISIBLE_POINTS = 10000
SAFE_Y_MIN_RANGE = 1e-3


class RecordingWindow(QWidget):
    stop_recording_signal = pyqtSignal()

    def __init__(self, file_path, port):
        super().__init__()

        # === Configuración de buffers ===
        self.data_buffer = deque(maxlen=2000)  # ~100 s de datos a 20 Hz
        self.buffer_lock = Lock()

        self.file_path = file_path
        self.port = port
        self.recording = False

        # Buffers circulares
        self.buffer_size = MAX_VISIBLE_POINTS
        self.index = 0
        self.buffer_full = False

        self.time = np.zeros(self.buffer_size)
        self.flow = np.zeros(self.buffer_size)
        self.pressure = np.zeros(self.buffer_size)
        self.temperature = np.zeros(self.buffer_size)
        self.hitos = []

        # Parámetros generales
        self.unit = "mmHg"
        self.display_delay = 0.5  # segundos de retraso visual
        self.time_window = 10     # segundos visibles en la ventana

        # Hilo serial y grabador
        self.serial_reader = SerialReader(port)
        self.stop_recording_signal.connect(self.serial_reader.end_reading)
        self.serial_reader.readings.connect(self.process_new_data)
        self.recorder = DataRecorder(file_path)

        # Temporizador de refresco (display loop)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_graphs)
        self.update_timer.start(100)  # refresco cada 100 ms (~10 FPS)

        self.init_ui()

    # === Interfaz ===
    def init_ui(self):
        self.setWindowTitle("Eoweo Recorder - Modo estable con delay visual")
        self.setMinimumSize(1300, 700)
        pg.setConfigOptions(antialias=True, background='#121212', foreground='w')

        # ---------- Barra superior ----------
        top_bar = QHBoxLayout()

        self.start_button = QPushButton("Start")
        self.start_button.setCheckable(True)
        self.start_button.clicked.connect(self.toggle_recording)

        self.hito_button = QPushButton("Marcar Hito")
        self.hito_button.clicked.connect(self.add_hito)

        self.unit_menu = QComboBox()
        self.unit_menu.addItems(["kPa", "bar", "mmHg"])
        self.unit_menu.currentTextChanged.connect(self.change_unit)

        for b in [self.start_button, self.hito_button]:
            b.setStyleSheet("""
                QPushButton {
                    background-color: #8E44AD;
                    color: white;
                    border-radius: 6px;
                    padding: 6px 10px;
                }
                QPushButton:checked { background-color: #2ECC71; }
                QPushButton:hover { background-color: #A569BD; }
            """)

        top_bar.addWidget(self.start_button)
        top_bar.addSpacing(10)
        top_bar.addWidget(self.hito_button)
        top_bar.addSpacing(30)
        top_bar.addWidget(QLabel("Unidad:"))
        top_bar.addWidget(self.unit_menu)
        top_bar.addStretch()

        # ---------- Gráficos ----------
        graphs_layout = QVBoxLayout()
        self.flow_plot = pg.PlotWidget(title="Flujo (L/min)")
        self.pressure_plot = pg.PlotWidget(title="Presión (mmHg)")
        self.temp_plot = pg.PlotWidget(title="Temperatura (°C)")

        for p in [self.flow_plot, self.pressure_plot, self.temp_plot]:
            p.showGrid(x=True, y=True, alpha=0.25)
            p.hideButtons()
            p.enableAutoRange('y', False)

        self.flow_curve = self.flow_plot.plot(pen=pg.mkPen('#B97AFF', width=2))
        self.pressure_curve = self.pressure_plot.plot(pen=pg.mkPen('#B97AFF', width=2))
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen('#B97AFF', width=2))

        graphs_layout.addWidget(self.flow_plot)
        graphs_layout.addWidget(self.pressure_plot)
        graphs_layout.addWidget(self.temp_plot)

        layout = QVBoxLayout()
        layout.addLayout(top_bar)
        layout.addLayout(graphs_layout)
        self.setLayout(layout)

    # ---------- Adquisición de datos ----------
    def process_new_data(self, data):
        parts = data.split(" ")
        if len(parts) < 4 or not parts[0].isdigit():
            return

        try:
            t = float(parts[0]) / 1000
            raw_p = float(parts[1])
            pres = raw_p * self.recorder.m + self.recorder.n
            temp = float(parts[2])
            flow = float(parts[3])

            # Guardar en buffer circular
            self.time[self.index] = t
            self.flow[self.index] = flow
            self.pressure[self.index] = pres
            self.temperature[self.index] = temp
            self.index = (self.index + 1) % self.buffer_size
            if self.index == 0:
                self.buffer_full = True

            # Guardar en CSV
            self.recorder.save_row(t, pres, temp, flow)

        except ValueError:
            pass

    def get_visible_data(self):
        """Devuelve los datos en orden temporal."""
        if not self.buffer_full:
            return (self.time[:self.index],
                    self.flow[:self.index],
                    self.pressure[:self.index],
                    self.temperature[:self.index])
        else:
            idx = self.index
            t = np.concatenate((self.time[idx:], self.time[:idx]))
            f = np.concatenate((self.flow[idx:], self.flow[:idx]))
            p = np.concatenate((self.pressure[idx:], self.pressure[:idx]))
            temp = np.concatenate((self.temperature[idx:], self.temperature[:idx]))
            return t, f, p, temp

    # ---------- Refresco del gráfico ----------
    def update_graphs(self):
        if self.index == 0 and not self.buffer_full:
            return

        t, flow, pres, temp = self.get_visible_data()
        if t.size == 0:
            return

        # Límite temporal visible con retraso
        t_latest = t[-1] - self.display_delay
        if t_latest <= 0:
            return

        t_min = max(t[0], t_latest - self.time_window)
        mask = (t >= t_min) & (t <= t_latest)
        t, flow, pres, temp = t[mask], flow[mask], pres[mask], temp[mask]

        self.flow_curve.setData(t, flow)
        self.pressure_curve.setData(t, pres)
        self.temp_curve.setData(t, temp)

        # Escala Y segura
        for plot in [self.flow_plot, self.pressure_plot, self.temp_plot]:
            y = plot.listDataItems()[0].yData
            if y.size > 0:
                y_min, y_max = np.min(y), np.max(y)
                y_span = y_max - y_min
                if y_span < SAFE_Y_MIN_RANGE:
                    center = (y_max + y_min) / 2
                    y_min, y_max = center - SAFE_Y_MIN_RANGE, center + SAFE_Y_MIN_RANGE
                plot.setYRange(y_min, y_max)
            plot.setXRange(t_min, t_latest)

        self._update_hitos()

    # ---------- Hitos ----------
    def add_hito(self):
        t, _, _, _ = self.get_visible_data()
        if t.size == 0:
            return
        label = f"Hito {len(self.hitos) + 1}"
        self.hitos.append((t[-1], label))
        self.recorder.save_row(t[-1], "", "", "", label)
        self._update_hitos()

    def _update_hitos(self):
        for plot in [self.flow_plot, self.pressure_plot, self.temp_plot]:
            for item in getattr(plot, "hito_items", []):
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
            plot.hito_items = []

            for t, label in self.hitos:
                line = InfiniteLine(
                    pos=t, angle=90,
                    pen=pg.mkPen((150, 150, 150), style=pg.QtCore.Qt.PenStyle.DashLine)
                )
                plot.addItem(line)

                y_top = max(plot.viewRange()[1][1], SAFE_Y_MIN_RANGE)
                text = TextItem(label, anchor=(0, 1), color=(200, 200, 200))
                text.setPos(t, y_top)
                plot.addItem(text)
                plot.hito_items.extend([line, text])

    # ---------- Control general ----------
    def change_unit(self, unit):
        self.unit = unit
        self.update_graphs()

    def toggle_recording(self):
        if not self.recording:
            self.serial_reader.start()
            self.recording = True
            self.start_button.setText("Stop")
        else:
            self.stop_recording_signal.emit()
            self.recording = False
            self.start_button.setText("Start")

    def closeEvent(self, event):
        self.stop_recording_signal.emit()
        event.accept()
