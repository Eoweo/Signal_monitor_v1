import pandas as pd
import time
import threading
import serial
import serial.serialutil
import json
import os
import glob
from queue import Queue, Empty
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox


MAX_QUEUE_SIZE = 5000  # protección contra sobrecarga de cola


class ErrorWindow(QMessageBox):
    def __init__(self, msg):
        super().__init__()
        self.setIcon(QMessageBox.Icon.Warning)
        self.setText("Error")
        self.setInformativeText(msg)
        self.setWindowTitle("Error")


class WriterThread(threading.Thread):
    """Hilo dedicado a escribir datos a disco (CSV o Parquet)."""

    def __init__(self, file_path, unit, data_queue, flush_interval=1.0, max_buffer_size=100,
                 file_format="csv", temp_dir="temp"):
        super().__init__(daemon=True)
        self.file_path = file_path
        self.unit = unit
        self.data_queue = data_queue
        self.flush_interval = flush_interval
        self.max_buffer_size = max_buffer_size
        self.file_format = file_format.lower()
        self.unit_factors = {"kPa": 1.0, "bar": 0.01, "mmHg": 7.50062}
        self.buffer = []
        self.last_flush = time.time()
        self.stop_flag = False
        self.header_written = False
        self.temp_dir = temp_dir
        self.block_count = 0

        if self.file_format == "parquet":
            os.makedirs(self.temp_dir, exist_ok=True)

    def run(self):
        try:
            while not self.stop_flag:
                try:
                    item = self.data_queue.get(timeout=self.flush_interval)
                    self.buffer.append(item)
                except Empty:
                    pass

                now = time.time()
                if len(self.buffer) >= self.max_buffer_size or (now - self.last_flush) >= self.flush_interval:
                    self._flush()
        except Exception as e:
            print(f"[WriterThread] Error inesperado: {e}")
        finally:
            try:
                self._flush()  # Flush final
                if self.file_format == "parquet":
                    self._merge_parquet_files()
                print("[WriterThread] Cerrado correctamente.")
            except Exception as e:
                print(f"[WriterThread] Error en cierre: {e}")

    def _flush(self):
        if not self.buffer:
            return

        try:
            df = pd.DataFrame(
                self.buffer,
                columns=["Time", f"Pressure ({self.unit})", "Temperature", "Flow", "Events"]
            )

            if self.file_format == "csv":
                df.to_csv(self.file_path, mode='a', index=False, header=not self.header_written)
                self.header_written = True

            elif self.file_format == "parquet":
                self.block_count += 1
                block_name = f"{self.temp_dir}/block_{self.block_count:04d}.parquet"
                df.to_parquet(block_name, index=False)

            self.buffer.clear()
            self.last_flush = time.time()

        except PermissionError:
            print(f"[WriterThread] Error: permiso denegado al escribir {self.file_path}.")
        except OSError as e:
            print(f"[WriterThread] Error de disco: {e}")
        except Exception as e:
            print(f"[WriterThread] Error inesperado en _flush: {e}")

    def _merge_parquet_files(self):
        """Combina todos los bloques parquet temporales en un solo archivo final."""
        files = sorted(glob.glob(f"{self.temp_dir}/block_*.parquet"))
        if not files:
            return
        try:
            dfs = [pd.read_parquet(f) for f in files]
            merged = pd.concat(dfs, ignore_index=True)
            merged.to_parquet(self.file_path, index=False)
            for f in files:
                os.remove(f)
            os.rmdir(self.temp_dir)
        except Exception as e:
            print(f"[WriterThread] Error al fusionar archivos parquet: {e}")

    def stop(self):
        self.stop_flag = True


class SerialReader(QThread):
    readings = pyqtSignal(str)
    warning_signal = pyqtSignal(str)  # <-- para mostrar popups seguros

    def __init__(self, port, file_path, unit="mmHg", flush_interval=1.0,
                 max_buffer_size=100, file_format="csv"):
        super().__init__()
        self.data_queue = Queue()
        self.port = port
        self.file_path = file_path
        self.writer = WriterThread(file_path=file_path, unit=unit,
                                   data_queue=self.data_queue,
                                   flush_interval=flush_interval,
                                   max_buffer_size=max_buffer_size,
                                   file_format=file_format)
        self.unit = unit
        self.unit_factors = {"kPa": 1.0, "bar": 0.01, "mmHg": 7.50062}
        self.m = 1.0
        self.n = 0.0
        self.pending_hito = None
        self.stop = False

        self.serialCom = None
        self._connect_with_retry(initial_wait=30)

    # -----------------------------------------------------------------
    def _connect_with_retry(self, initial_wait=30):
        """Intenta conectar al puerto serial con reintentos progresivos."""
        wait_time = initial_wait
        while not self.stop:
            try:
                print(f"[SerialReader] Intentando conectar a {self.port}...")
                self.serialCom = serial.Serial(self.port, 115200, timeout=1)
                self.serialCom.setDTR(False)
                time.sleep(1)
                self.serialCom.flushInput()
                self.serialCom.setDTR(True)
                print("[SerialReader] Conexión establecida correctamente.")
                return True
            except serial.serialutil.SerialException:
                msg = f"No se pudo conectar al puerto {self.port}. Reintentando en {wait_time} s..."
                print(f"[SerialReader] {msg}")
                self.warning_signal.emit(msg)
                time.sleep(wait_time)
                wait_time *= 2  # espera exponencial
            except Exception as e:
                msg = f"Error inesperado al conectar: {e}"
                print(f"[SerialReader] {msg}")
                self.warning_signal.emit(msg)
                time.sleep(wait_time)
                wait_time *= 2
        return False

    # -----------------------------------------------------------------
    def run(self):
        """Bucle principal de lectura con watchdog y reconexión automática."""
        if not self.serialCom:
            if not self._connect_with_retry():
                return

        self.writer.start()
        print("[SerialReader] Iniciando lectura con watchdog de 3 s...")

        last_data_time = time.time()

        while not self.stop:
            try:
                if self.serialCom.in_waiting:
                    line = self.serialCom.readline().decode("utf-8").strip()
                    data = self._process_line(line)
                    if data:
                        last_data_time = time.time()
                        self.readings.emit(json.dumps(data))

                # --- Watchdog: si no llegan datos en 3 s, reconectar ---
                if time.time() - last_data_time > 10:
                    msg = f"No se detectan datos en 10 s. Reintentando conexión en {self.port}..."
                    print(f"[SerialReader] {msg}")
                    self.warning_signal.emit(msg)
                    self._reconnect_serial()
                    last_data_time = time.time()

            except serial.SerialException:
                print("[SerialReader] Error serial. Intentando reconectar...")
                self._reconnect_serial()
                last_data_time = time.time()

        # --- Cierre seguro ---
        print("[SerialReader] Cerrando...")
        self.writer.stop()
        self.writer.join()
        try:
            if self.serialCom and self.serialCom.is_open:
                self.serialCom.close()
        except Exception as e:
            print(f"[SerialReader] Error al cerrar puerto: {e}")
        print("[SerialReader] Cerrado correctamente.")

    # -----------------------------------------------------------------
    def _reconnect_serial(self):
        """Reconecta completamente el puerto."""
        try:
            if self.serialCom and self.serialCom.is_open:
                self.serialCom.close()
        except Exception as e:
            print(f"[SerialReader] Error al cerrar durante reconexión: {e}")

        time.sleep(1)
        connected = self._connect_with_retry(initial_wait=30)
        if not connected:
            self.warning_signal.emit("Fallo persistente de conexión serial. Reintentando en segundo plano.")
        else:
            print("[SerialReader] Reconexión exitosa.")
            self.serialCom.flushInput()
            self.serialCom.setDTR(True)

    def _process_line(self, line):
        """Parsea texto y guarda en la cola."""
        if not line or not line[0].isdigit():
            return None
        parts = line.split(" ")
        if len(parts) < 4:
            return None

        try:
            t = float(parts[0]) / 1000.0
            raw = float(parts[1])
            pressure = raw * self.m + self.n
            temp = float(parts[2])
            flow = float(parts[3])

            event = ""
            if self.pending_hito:
                event = self.pending_hito
                self.pending_hito = None

            factor = self.unit_factors[self.unit]

            # --- Protección de cola: evita sobrecarga ---
            if self.data_queue.qsize() > MAX_QUEUE_SIZE:
                try:
                    self.data_queue.get_nowait()  # descarta el más antiguo
                    print("[SerialReader] Advertencia: cola saturada, descartando dato viejo.")
                except Empty:
                    pass

            self.data_queue.put([t, round(pressure * factor, 3), temp, flow, event])

            return {
                "time": t,
                "raw": raw,
                "pressure": pressure,
                "temp": temp,
                "flow": flow,
                "event": event
            }
        except ValueError:
            return None

    def add_hito(self, event_text):
        """Guarda un hito pendiente que se aplicará al próximo dato."""
        self.pending_hito = event_text

    def end_reading(self):
        """Detiene la lectura y cierra todo correctamente."""
        self.stop = True
        try:
            if self.serialCom.is_open:
                self.serialCom.close()
        except:
            pass
