import os
import json
from pyqtgraph import PlotWidget, InfiniteLine, TextItem
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QGraphicsTextItem
)
from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal
from backend import SerialReader, ErrorWindow
from pyqtgraph import PlotWidget


def timeformat(seconds):
    m = int(seconds // 60)
    h = int(m // 60)
    s_string = "{0:.1f}".format(seconds % 60)
    h_string = "{0:02d}".format(h)
    m_string = "{0:02d}".format(m % 60)
    return h_string + ":" + m_string + ":" + s_string


class RecordingWindow(QWidget):
    stop_recording_signal = pyqtSignal()

    def __init__(self, port, file_path):
        super().__init__()
        self.time, self.raw_pressure, self.pressure, self.temperature, self.flow = [], [], [], [], []
        self.time_range = 7 * 24 * 60 * 60
        self.serial_reader = SerialReader(file_path, port)
        self.stop_recording_signal.connect(self.serial_reader.end_reading)
        self.serial_reader.readings.connect(self.process_new_data)
        
        self.manual_ylim_pressure = None
        self.manual_ylim_temp = None
        self.manual_ylim_flow = None

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Eoweo Recorder")
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
        # ⚙️ Ahora solo emite el texto, no modifica el gráfico directamente
        self.hito_button.clicked.connect(self.send_hito_event)
        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.label_t_window)
        hbox1.addWidget(self.seconds_box)
        hbox1.addWidget(self.scale_drop)
        hbox1.addWidget(self.set_button)
        hbox1.addWidget(self.hito_input)
        hbox1.addWidget(self.hito_button)
        vbox.addLayout(hbox1)

        # --- Graph setup ---
        pg.setConfigOptions(antialias=True, background='k', foreground='w')
        self.pressure_plot = PlotWidget(title="Presión")
        self.temperature_plot = PlotWidget(title="Temperatura")
        self.flow_plot = PlotWidget(title="Flujo")
        for plot in [self.pressure_plot, self.temperature_plot, self.flow_plot]:
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.hideButtons()

        self.pressure_curve = self.pressure_plot.plot(pen=pg.mkPen('r', width=2))
        self.flow_curve = self.flow_plot.plot(pen=pg.mkPen('g', width=2))
        self.temperature_curve = self.temperature_plot.plot(pen=pg.mkPen('b', width=2))

        gbox = QGridLayout()
        gbox.addWidget(self.temperature_plot)
        gbox.addWidget(self.pressure_plot)
        gbox.addWidget(self.flow_plot)
        vbox.addLayout(gbox)

        # --- Labels ---
        self.time_label = QLabel("none")
        self.time_label.hide()
        self.current_value_label = QLabel("Valor actual: --")
        vbox.addWidget(self.time_label)
        vbox.addWidget(self.current_value_label)

        # --- Buttons ---
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

    def send_hito_event(self):
        """Envia el texto del hito al backend, sin modificar gráficos."""
        text = self.hito_input.text().strip()
        if text:
            self.serial_reader.add_hito(text)
            self.hito_input.clear()

    def process_new_data(self, json_data):
        """Recibe el JSON del backend y actualiza las gráficas."""
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError:
            print("Error al parsear JSON:", json_data)
            return

        t = data["time"]
        self.time.append(t)
        self.pressure.append(data["pressure"])
        self.temperature.append(data["temp"])
        self.flow.append(data["flow"])
        self.raw_pressure.append(data["raw"])

        event_text = data.get("event")
        if event_text:
            print("Evento recibido:", event_text)
            self._add_event_marker(t, event_text)

        self.update_graphs()

    def _add_event_marker(self, t, label):
        """Agrega línea y texto sin provocar autorrango infinito."""
        for plot in [self.pressure_plot, self.temperature_plot, self.flow_plot]:
            try:
                vb = plot.getViewBox()
                # --- Congelar rango Y actual ---
                yrange = vb.viewRange()[1]
                vb.setYRange(yrange[0], yrange[1], padding=0)
                vb.enableAutoRange(axis='y', enable=False)

                # --- Añadir la línea ---
                line = InfiniteLine(
                    pos=t,
                    angle=90,
                    pen=pg.mkPen((200, 200, 200),
                                 style=QtCore.Qt.PenStyle.DashLine)
                )
                plot.addItem(line)

                # --- Añadir el texto ---
                text = pg.TextItem(label, anchor=(0, 1), color=(255, 255, 255))
                plot.addItem(text)

                # Colocar dentro del rango visible (ligeramente por debajo del borde)
                y_top = yrange[1]
                text.setPos(t, y_top - 0.05 * abs(y_top))

                # Guardar referencia
                if not hasattr(plot, "event_markers"):
                    plot.event_markers = []
                plot.event_markers.append((t, text, line))

                # --- Restaurar auto-rango después del siguiente repintado ---
                QtCore.QTimer.singleShot(50, lambda vb=vb: vb.enableAutoRange(axis='y', enable=True))

            except Exception as e:
                print(f"Error al agregar marcador de evento: {e}")



    def update_graphs(self):
        if not self.time:
            return

        factor = self.serial_reader.unit_factors[self.serial_reader.unit]
        unit = self.serial_reader.unit
        scaled_pressure = [p * factor for p in self.pressure]
        t0 = max(0, self.time[-1] - self.time_range)
        self.pressure_curve.setData(self.time, scaled_pressure)
        self.flow_curve.setData(self.time, self.flow)
        self.temperature_curve.setData(self.time, self.temperature)
        for plot in [self.pressure_plot, self.flow_plot, self.temperature_plot]:
            plot.setXRange(t0, self.time[-1])

        self.time_label.setText(f"Tiempo Actual: {timeformat(self.time[-1])}")
        self.current_value_label.setText(
            f"Presión: {scaled_pressure[-1]:.2f} {unit} | "
            f"Temp: {self.temperature[-1]:.2f}°C | Flujo: {self.flow[-1]:.2f} L/min"
        )
        # Reposicionar textos de eventos
        for plot in [self.pressure_plot, self.temperature_plot, self.flow_plot]:
            if hasattr(plot, "event_markers"):
                view = plot.viewRange()
                if not view or not view[1]:
                    continue
                y_top = view[1][1]
                for t, text, _ in plot.event_markers:
                    text.setPos(t, y_top - 0.05 * abs(y_top))



    def adjust_time(self):
        if self.scale_drop.currentIndex() == 0:
            self.time_range = 7 * 24 * 60 * 60
        else:
            try:
                t = int(self.seconds_box.text())
                if self.scale_drop.currentIndex() == 2:
                    t *= 60
                elif self.scale_drop.currentIndex() == 3:
                    t *= 3600
                self.time_range = t
            except:
                ErrorWindow("Ventana de tiempo debe ser un número").exec()
        self.update_graphs()

    def stop_recording(self):
        self.stop_recording_signal.emit()
        self.close()

    def start_recording(self):
        self.serial_reader.start()
        self.start_button.hide()
        self.stop_button.show()
        self.time_label.show()
        self.current_value_label.show()

    def full_mode(self, index):
        self.seconds_box.setDisabled(index == 0)

    def closeEvent(self, event):
        self.stop_recording_signal.emit()
        event.accept()
