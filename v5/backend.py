import time
import csv
import serial
import serial.serialutil
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QApplication


class ErrorWindow(QMessageBox):
    def __init__(self, msg):
        super().__init__()
        self.setIcon(QMessageBox.Icon.Warning)
        self.setText("Error")
        self.setInformativeText(msg)
        self.setWindowTitle("Error")


class SerialReader(QThread):
    """Reads data from a serial port in a background thread."""
    readings = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        try:
            self.serialCom = serial.Serial(port, 115200)
        except serial.serialutil.SerialException:
            ErrorWindow("Acceso denegado al puerto. Cerrando aplicación").exec()
            QApplication.quit()
        except Exception:
            ErrorWindow("Error inesperado al iniciar el puerto").exec()

        self.stop = False

    def run(self):
        self.serialCom.setDTR(False)
        time.sleep(1)
        self.serialCom.flushInput()
        self.serialCom.setDTR(True)

        while not self.stop:
            try:
                if self.serialCom.in_waiting:
                    packet = self.serialCom.readline().decode("utf-8").strip()
                    self.readings.emit(packet)
            except serial.SerialException:
                print("Serial disconnected. Trying to reconnect...")
                time.sleep(2)
                try:
                    self.serialCom.open()
                except:
                    pass

    def end_reading(self):
        self.stop = True
        try:
            if self.serialCom.is_open:
                self.serialCom.close()
        except:
            pass


class DataRecorder:
    """Handles calibration, CSV saving, and unit conversions."""

    def __init__(self, file_path, unit="mmHg"):
        self.path = file_path
        self.m = 1.0
        self.n = 0.0
        self.unit_factors = {"kPa": 1.0, "bar": 0.01, "mmHg": 7.50062}
        self.current_unit = unit
        self.hitos = []

        with open(self.path, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Time", f"Pressure ({self.current_unit})", "Temperature", "Flow", "Events"])

    def save_row(self, t, pressure, temp, flow, event=""):
        factor = self.unit_factors[self.current_unit]
        with open(self.path, "a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([t, round(pressure * factor, 3), temp, flow, event])
