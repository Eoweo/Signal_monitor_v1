import os
import json
import time

import numpy as np
import pyqtgraph as pg
from pyqtgraph import InfiniteLine, TextItem
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QFrame
)
from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import pyqtSignal, QTimer, Qt
from backend import SerialReader, ErrorWindow
from PyQt6.QtGui import QIcon, QPixmap


MAX_POINTS = 5000        # buffer circular
UPDATE_INTERVAL_MS = 50   # frecuencia de refresco gráfico (5 Hz)
DISPLAY_DELAY = 0.3       # segundos de retraso visual
TIME_RANGE_DEFAULT = 4*60  # segundos en ventana por defecto
START_FULL_SCREEN = False  # iniciar en modo pantalla completa

def timeformat(seconds):
    m = int(seconds // 60)
    h = int(m // 60)
    s_string = "{0:.1f}".format(seconds % 60)
    return f"{h:02d}:{m % 60:02d}:{s_string}"


# ===========================================================
# ===   CLASE PRINCIPAL DE ADQUISICIÓN Y GRAFICADO       ===
# ===========================================================

class RecordingWindow(QWidget):
    stop_recording_signal = pyqtSignal()

    def __init__(self, port, file_path, patient_file="patient_info.txt"):
        super().__init__()
        self.setWindowIcon(QIcon("ico2.png"))
        self. file_path = file_path
        self.port = port
        # --- Buffers prealocados ---
        self.index = 0
        self.full = False
        self.y_autoscale_enabled = True
        self.time = np.zeros(MAX_POINTS)
        self.pressure = np.zeros(MAX_POINTS)
        self.temperature = np.zeros(MAX_POINTS)
        self.flow = np.zeros(MAX_POINTS)

        self.time_range = TIME_RANGE_DEFAULT
        self.serial_reader = SerialReader(file_path= file_path, port= port)
        self.stop_recording_signal.connect(self.serial_reader.end_reading)
        self.serial_reader.readings.connect(self.process_new_data)
        self.serial_reader.warning_signal.connect(lambda msg: ErrorWindow(msg).exec())

        pg.setConfigOptions(antialias=True, background='k', foreground='w', useOpenGL=True)
        self.init_ui(patient_file)

        # --- Temporizador de actualización ---
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_graphs)
        self.update_timer.start(UPDATE_INTERVAL_MS)
        
        screen = QtGui.QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry()
        
        if START_FULL_SCREEN:
            self.showFullScreen()
        else:
            # Ventana del tamaño de la pantalla disponible (maximizada visualmente)
            self.setGeometry(geometry)

            # Mostrar como maximizada (pero no fullscreen)
            self.showMaximized()



    # ----------------------------------------------------
    def init_ui(self, patient_file):
        self.setWindowTitle(f"Registro de datos -- {self.file_path} -- Puerto: {self.port}")
        vbox = QVBoxLayout()

        # --- Control row ---
        self.label_t_window = QLabel("Ventana de tiempo (s)")
        self.seconds_box = QLineEdit("")
        self.seconds_box.setDisabled(True)
        self.set_button = QPushButton("Aplicar")
        self.set_button.clicked.connect(self.adjust_time)
        self.scale_drop = QComboBox()
        self.scale_drop.addItems(["Completo     ", "Segundos    ", "Minutos     "])#addItems(["Completo", "Segundos", "Minutos", "Horas"])
        self.scale_drop.currentIndexChanged.connect(self.full_mode)
        self.hito_input = QLineEdit("")
        self.hito_input.setPlaceholderText("Escribir hito")
        self.hito_button = QPushButton("Hito")
        self.hito_button.clicked.connect(self.send_hito_event)

        self.autoscale_button = QPushButton("Set Y Axis")
        self.autoscale_button.setCheckable(True)
        self.autoscale_button.setChecked(True)
        self.autoscale_button.toggled.connect(self.toggle_autoscale_y)

        hbox1 = QHBoxLayout()
        for w in [self.label_t_window, self.seconds_box, self.scale_drop,
                  self.set_button, self.hito_input, self.hito_button, self.autoscale_button]:
            hbox1.addWidget(w)
        vbox.addLayout(hbox1)

        # --- Gráficos ---
        def create_plot(title, color_plot, color_title):
            glw = pg.GraphicsLayoutWidget()
            title_html = (
                "<span style='color:#E5E5E5; font-size:12pt; font-family:Segoe UI; "
                "font-weight:600;'><b>{}</b></span>".format(title)
            )            
            plot = glw.addPlot(title=title_html)
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.hideButtons()
            curve = plot.plot(pen=pg.mkPen(color_plot, width=2))
            return glw, plot, curve

        self.pressure_widget, self.pressure_plot, self.pressure_curve = create_plot(title = "Presión",      color_plot = "#FF4C4C", color_title= "#FF7171")
        self.flow_widget, self.flow_plot, self.flow_curve =             create_plot(title = "Flujo" ,       color_plot = "#8FD3FF", color_title= "#8FD3FF")
        self.temp_widget, self.temp_plot, self.temp_curve =             create_plot(title = "Temperatura",  color_plot = "#FFA726", color_title= "#FFCB6B")

        # --- Contenedor de gráficos + resumen ---
        graph_container = QHBoxLayout()

        gbox = QVBoxLayout()
        gbox.addWidget(self.pressure_widget)
        gbox.addWidget(self.flow_widget)
        gbox.addWidget(self.temp_widget)
        graph_container.addLayout(gbox)

        # --- Panel de resumen clínico ---
        self.summary = SummaryWidget(patient_file=patient_file)
        self.summary.set_data_source(self)
        graph_container.addWidget(self.summary)

        vbox.addLayout(graph_container)

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
    
    def toggle_autoscale_y(self, enable):

        for plot in [self.pressure_plot, self.flow_plot, self.temp_plot]:
            plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)



    # ----------------------------------------------------
    def process_new_data(self, json_data):
        """Recibe datos JSON y los guarda en buffer circular."""
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError:
            return

        t = data["time"]
        i = self.index

        self.time[i] = t
        self.pressure[i] = data["pressure"]
        self.temperature[i] = data["temp"]
        self.flow[i] = data["flow"]

        self.index = (i + 1) % MAX_POINTS
        if self.index == 0:
            self.full = True

        if data.get("event"):
            self._add_event_marker(t, data["event"])

    # ----------------------------------------------------
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
            if len(plot.event_markers) > 50:
                old_t, old_text, old_line = plot.event_markers.pop(0)
                plot.removeItem(old_text)
                plot.removeItem(old_line)

    # ----------------------------------------------------
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
            return

        t_max = t[-1] - DISPLAY_DELAY
        if t_max <= 0:
            return
        t_min = max(t_max - self.time_range, 0)
        mask = (t >= t_min) & (t <= t_max)
        t, p, f, temp = t[mask], p[mask], f[mask], temp[mask]

        if len(t) == 0:
            return

        if len(t) > 5000:
            step = len(t) // 5000
            t, p, f, temp = t[::step], p[::step], f[::step], temp[::step]

        self.pressure_curve.setData(t, p)
        self.flow_curve.setData(t, f)
        self.temp_curve.setData(t, temp)

        for plot in [self.pressure_plot, self.temp_plot, self.flow_plot]:
            plot.setXRange(t_min, t_max, padding=0)
            
    # ----------------------------------------------------
    def send_hito_event(self):
        text = self.hito_input.text().strip()
        if text:
            self.serial_reader.add_hito(text)
            self.hito_input.clear()

    # ----------------------------------------------------
    def adjust_time(self):
        idx = self.scale_drop.currentIndex()
        try:
            if idx == 0:
                self.time_range = TIME_RANGE_DEFAULT
            else:
                t = float(self.seconds_box.text())
                if idx == 2:
                    t *= 60
                #elif idx == 3:#horas
                #    t *= 3600
                self.time_range = t
            if self.time_range > TIME_RANGE_DEFAULT:
                self.time_range = TIME_RANGE_DEFAULT
        except:
            ErrorWindow("Ventana de tiempo debe ser numérica.").exec()
        self.update_graphs()

    # ----------------------------------------------------
    def start_recording(self):
        self.serial_reader.start()
        self.start_button.hide()
        self.stop_button.show()

    def stop_recording(self):
        self.stop_recording_signal.emit()
        # --- NEW: save final infuse time ---
        if hasattr(self, "summary"):
            self.summary.finalize_infuse_time()
        self.close()

    def full_mode(self, index):
        self.seconds_box.setDisabled(index == 0)

    def closeEvent(self, event):
        self.stop_recording_signal.emit()
        event.accept()


# ===========================================================
# ===                 PANEL DE RESUMEN                    ===
# ===========================================================

def format_hms(seconds):
    """Convierte segundos a formato HHh MMm SSs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}h {m:02d}m {s:02d}s"


class SummaryWidget(QWidget):
    """Panel lateral estilo monitor, optimizado para pantallas 16:9."""

    def __init__(self, parent=None, patient_file="patient_info.txt"):
        super().__init__(parent)

        # un poco más angosto y sin exagerar el alto
        self.data_ref = None
        self.setMinimumWidth(260)
        self.setStyleSheet("""
            SummaryWidget, QWidget {
                background-color: #141414;
                color: #EEE;
                border-left: 1px solid #2A2A2A;
            }
            QLabel {
                font-family: 'Segoe UI';
                color: #E0E0E0;
            }
            QFrame.metric-card {
                background-color: #1D1D1D;
                border-radius: 8px;
                padding: 3px 8px;
                margin-top: 0px;
            }
            QFrame.info-card {
                background-color: #1D1D1D;
                border-radius: 8px;
                padding: 3px 8px;
                margin-top: 0px;
            }
        """)

        self.patient_file = patient_file
        self.patient_info = self._load_patient_info()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(2)

        # --- PRESSURE ---
        self.press_section = self._make_metric_section(
            title="Pressure (mmHg)",
            title_color= "#FF7171")
        
        self.press_value = self._make_value_label()
        self.press_minmax = self._make_minmax_label("mmHg")
        self.press_mean = self._make_mean_label("mmHg")

        self.tare_pressure = QPushButton("Tare Pressure")
        self.tare_pressure.clicked.connect(lambda: self.on_tare("pressure"))

        self.press_section.layout().addWidget(self.press_mean)
        self.press_section.layout().addWidget(self.press_value)
        self.press_section.layout().addWidget(self.press_minmax)
        self.press_section.layout().addWidget(self.tare_pressure)
        layout.addWidget(self.press_section)

        # --- FLOW ---
        self.flow_section = self._make_metric_section(
            title="Flow (mL/min)",
            title_color="#8FD3FF")
        
        self.flow_value = self._make_value_label()
        self.flow_minmax = self._make_minmax_label("mL/min")
        self.flow_mean = self._make_mean_label("mL/min")

        self.tare_flow = QPushButton("Tare Flow")
        self.tare_flow.clicked.connect(lambda: self.on_tare("flow"))

        self.set_direction_flow = QPushButton("Change Flow Direction")
        self.set_direction_flow.clicked.connect(self.change_flow_direction)

        self.flow_section.layout().addWidget(self.flow_mean)
        self.flow_section.layout().addWidget(self.flow_value)
        self.flow_section.layout().addWidget(self.flow_minmax)
        self.flow_section.layout().addWidget(self.tare_flow)
        self.flow_section.layout().addWidget(self.set_direction_flow)
        layout.addWidget(self.flow_section)


        # --- TEMPERATURE ---
        self.temp_section = self._make_metric_section(
            title="Temperature (°C)",
            title_color="#FFCB6B")
        
        self.temp_value = self._make_value_label()
        self.temp_minmax = self._make_minmax_label("°C")
        self.temp_mean = self._make_mean_label("°C")

        self.temp_section.layout().addWidget(self.temp_mean)
        self.temp_section.layout().addWidget(self.temp_value)
        self.temp_section.layout().addWidget(self.temp_minmax)
        layout.addWidget(self.temp_section)
        
        # ---- BOTÓN REBOOT ----
        self.reboot_button = QPushButton("Reboot Min/Max")
        self.reboot_button.setStyleSheet("""
            QPushButton {
                background-color: #303030;
                color: #FFFFFF;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 0px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #3E3E3E;
            }
        """)
        self.reboot_button.clicked.connect(self.reboot_minmax)
        layout.addWidget(self.reboot_button)

        # --- PATIENT INFO ---
        self.info_section = self._make_info_section("Patient Info")
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)

        self.info_labels = {}
        info_items = [
            ("Organ ID", "id"),
            ("Blood Type", "blood"),
            ("Liver Mass", "mass"),
            ("Infuse Time", "infuse"),
        ]
        for i, (label, key) in enumerate(info_items):
            lbl_title = QLabel(label + ":")
            lbl_title.setStyleSheet("color:#AAAAAA; font-size:9pt;")
            lbl_value = QLabel(str(self.patient_info.get(key, "(not set)")))
            lbl_value.setStyleSheet("color:#FFFFFF; font-size:9pt; font-weight:bold;")
            grid.addWidget(lbl_title, i, 0)
            grid.addWidget(lbl_value, i, 1)
            self.info_labels[key] = lbl_value

        self.info_section.layout().addLayout(grid)
        layout.addWidget(self.info_section)

        layout.addStretch(1)
        
        # ---- LOGO SECTION ----
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setStyleSheet("background: transparent; border: none;")

        layout.addWidget(self.logo_label)

        # Load the logo
        logo_path = "Logo_2.png"
        if os.path.exists(logo_path):
            self.logo_pixmap = QPixmap(logo_path)
            self._update_logo_size()

        self.start_time = time.time()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_panel)
        self.timer.start(1000)
    
    # ---------- helpers de UI ----------

    def _make_metric_section(self, title, title_color):
        frame = QFrame()
        frame.setObjectName("metric-card")
        frame.setProperty("class", "metric-card")
        v = QVBoxLayout(frame)
        v.setContentsMargins(6, 4, 6, 4)
        v.setSpacing(2)

        lbl = QLabel(f"<b>{title}</b>")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"font-size:11pt; color:{title_color}; margin-bottom:2px;"
        )
        v.addWidget(lbl)
        return frame

    def _make_mean_label(self, unit):
        lbl = QLabel(f"Mean: -- {unit}")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size:9pt; color:#999;")
        return lbl

    def _make_info_section(self, title):
        frame = QFrame()
        frame.setObjectName("info-card")
        frame.setProperty("class", "info-card")
        v = QVBoxLayout(frame)
        v.setContentsMargins(6, 4, 6, 4)
        v.setSpacing(2)
        lbl = QLabel(f"<b>{title}</b>")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "font-size:11pt; color:#9B84EE; margin-bottom:2px;"
        )
        v.addWidget(lbl)
        return frame

    def _make_value_label(self):
        lbl = QLabel("--")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # un poco más pequeño para no reventar altura
        lbl.setStyleSheet("font-size:22pt; font-weight:bold; color:#FDFDFD;")
        return lbl

    def _make_minmax_label(self, unit):
        lbl = QLabel(f"Min: -- {unit} | Max: -- {unit}")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size:9pt; color:#BBBBBB;")
        return lbl

    def _load_patient_info(self):
        """Reads patient info from text file and normalizes keys."""
        data = {"id": "(not set)", "blood": "(not set)", "mass": "(not set)", "infuse": "(not set)"}
        if not os.path.exists(self.patient_file):
            return data

        with open(self.patient_file, "r") as f:
            for line in f:
                if ":" not in line:
                    continue
                key, val = line.strip().split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                val = val.strip() or "(not set)"
                # Normalize to our internal keys
                if "organ" in key:
                    data["id"] = val
                elif "blood" in key:
                    data["blood"] = val
                elif "mass" in key:
                    data["mass"] = val
                elif "infuse" in key:
                    data["infuse"] = val
        return data


    def set_data_source(self, rec_window):
        self.data_ref = rec_window

    # ---------- lógica de actualización ----------

    def update_panel(self):
        if not self.data_ref or self.data_ref.index == 0:
            return

        rw = self.data_ref
        t, p, f, temp = rw.time, rw.pressure, rw.flow, rw.temperature

        # buffer circular → ordenar
        if rw.full:
            idx = rw.index
            t = np.concatenate((t[idx:], t[:idx]))
            p = np.concatenate((p[idx:], p[:idx]))
            f = np.concatenate((f[idx:], f[:idx]))
            temp = np.concatenate((temp[idx:], temp[:idx]))
        else:
            t, p, f, temp = t[:rw.index], p[:rw.index], f[:rw.index], temp[:rw.index]

        if len(t) < 2:
            return
        
        # Si se ha hecho reboot, solo considerar datos desde ese punto
        if hasattr(self, "reset_index") and rw.full:
            t = np.concatenate((t[idx:], t[:idx]))
            start_idx = self.reset_index if self.reset_index < len(t) else 0
            t = t[start_idx:]
            p, f, temp = p[start_idx:], f[start_idx:], temp[start_idx:]
        elif hasattr(self, "reset_index"):
            t, p, f, temp = t[self.reset_index:], p[self.reset_index:], f[self.reset_index:], temp[self.reset_index:]

        # FLOW
        self.flow_value.setText(f"{f[-1]:.1f}")
        self.flow_minmax.setText(f"Min: {f.min():.1f} mL/min | Max: {f.max():.1f} mL/min")
        self.flow_mean.setText(f"Mean: {f.mean():.1f} mL/min")

        # PRESSURE
        self.press_value.setText(f"{p[-1]:.1f}")
        self.press_minmax.setText(f"Min: {p.min():.1f} mmHg | Max: {p.max():.1f} mmHg")
        self.press_mean.setText(f"Mean: {p.mean():.1f} mmHg")

        # TEMPERATURE
        self.temp_value.setText(f"{temp[-1]:.1f}")
        self.temp_minmax.setText(f"Min: {temp.min():.1f} °C | Max: {temp.max():.1f} °C")
        self.temp_mean.setText(f"Mean: {temp.mean():.1f} °C")

        # INFUSE TIME
        elapsed = time.time() - self.start_time
        self.info_labels["infuse"].setText(format_hms(elapsed))
    
    def reboot_minmax(self):
        """
        Reinicia los valores mínimos y máximos de las variables
        para que se recalculen desde los datos nuevos que lleguen.
        """
        if not self.data_ref:
            return

        rw = self.data_ref

        # Guardamos la posición actual como punto de reinicio
        self.reset_index = rw.index

        # Reiniciar valores visuales
        self.flow_minmax.setText("Min: -- mL/min | Max: -- mL/min")
        self.press_minmax.setText("Min: -- mmHg | Max: -- mmHg")
        self.temp_minmax.setText("Min: -- °C | Max: -- °C")

        self.flow_mean.setText("Mean: -- mL/min")
        self.press_mean.setText("Mean: -- mmHg")
        self.temp_mean.setText("Mean: -- °C")

        # Registrar tiempo del reinicio para depuración
        print("[SummaryWidget] Min/Max reset at index", self.reset_index)
    
    def finalize_infuse_time(self):
        """Update patient file and panel with the final infuse time."""
        elapsed = time.time() - self.start_time
        final_time = format_hms(elapsed)
        self.info_labels["infuse"].setText(final_time)

        # Persist final value into the patient info text file
        lines = []
        if os.path.exists(self.patient_file):
            with open(self.patient_file, "r") as f:
                lines = f.readlines()

        # Update or append the infuse line
        found = False
        with open(self.patient_file, "w") as f:
            for line in lines:
                if "infuse" in line.lower():
                    f.write(f"Infuse Time: {final_time}\n")
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f"Infuse Time: {final_time}\n")
    
    def _update_logo_size(self):
        """Resize logo proportionally to widget size while keeping aspect ratio."""
        if not hasattr(self, "logo_pixmap") or self.logo_pixmap is None:
            return
    
        # Available space
        available_w = self.logo_label.width()
        available_h = self.logo_label.height()
    
        if available_w <= 0 or available_h <= 0:
            return
    
        # Scale preserving aspect ratio
        scaled = self.logo_pixmap.scaled(
            available_w,
            available_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
    
        self.logo_label.setPixmap(scaled)

    
    def resizeEvent(self, event):
        """Update logo size dynamically on resize."""
        super().resizeEvent(event)
        self._update_logo_size()

    def on_tare(self, type):
        if self.data_ref:
            if type == "pressure":
                self.data_ref.serial_reader.tare("pressure", self.data_ref.pressure[self.data_ref.index - 1])
            elif type == "flow":
                self.data_ref.serial_reader.tare("flow", self.data_ref.flow[self.data_ref.index - 1])

    def change_flow_direction(self):
        if self.data_ref:
            self.data_ref.serial_reader.set_direction_flow()