import psutil
import pynvml
from pynvml import (
    nvmlDeviceGetCount,
    nvmlDeviceGetHandleByIndex,
    nvmlDeviceGetMemoryInfo,
    nvmlInit,
    nvmlShutdown,
    nvmlDeviceGetTemperature,
    nvmlDeviceGetPowerUsage,
    NVML_TEMPERATURE_GPU,
)

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import TELEMETRY_CAPTURE
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry


class TelemetryCapture:
    def __init__(self, conf=TELEMETRY_CAPTURE):
        self.conf = conf
        self.logger = FlowceptLogger().get_logger()

    def capture(self) -> Telemetry:
        if self.conf is None:
            return None

        tel = Telemetry()
        tel.process = self._capture_process_info()
        tel.cpu = self._capture_cpu()
        tel.memory = self._capture_memory()
        tel.network = self._capture_network()
        tel.disk = self._capture_disk()
        tel.gpu = self._capture_gpu()

        return tel

    def _capture_disk(self):
        capt = self.conf.get("disk", False)
        if not capt:
            return None
        try:
            disk = Telemetry.Disk()
            disk.disk_usage = psutil.disk_usage("/")._asdict()
            disk.io_sum = psutil.disk_io_counters(perdisk=False)._asdict()
            io_perdisk = psutil.disk_io_counters(perdisk=True)
            if len(io_perdisk) > 1:
                disk.io_per_disk = {}
                for d in io_perdisk:
                    disk.io_per_disk[d] = io_perdisk[d]._asdict()

            return disk
        except Exception as e:
            self.logger.exception(e)

    def _capture_network(self):
        capt = self.conf.get("network", False)
        if not capt:
            return None
        try:
            net = Telemetry.Network()
            net.netio_sum = psutil.net_io_counters(pernic=False)._asdict()
            pernic = psutil.net_io_counters(pernic=True)
            net.netio_per_interface = {}
            for ic in pernic:
                if pernic[ic].bytes_sent and pernic[ic].bytes_recv:
                    net.netio_per_interface[ic] = pernic[ic]._asdict()
            return net
        except Exception as e:
            self.logger.exception(e)

    def _capture_memory(self):
        capt = self.conf.get("mem", False)
        if not capt:
            return None
        try:
            mem = Telemetry.Memory()
            mem.virtual = psutil.virtual_memory()._asdict()
            mem.swap = psutil.swap_memory()._asdict()
            return mem
        except Exception as e:
            self.logger.exception(e)

    def _capture_process_info(self):
        capt = self.conf.get("process_info", False)
        if not capt:
            return None
        try:
            p = Telemetry.Process()
            psutil_p = psutil.Process()
            with psutil_p.oneshot():
                p.pid = psutil_p.pid
                try:
                    p.cpu_number = psutil_p.cpu_num()
                except:
                    pass
                p.memory = psutil_p.memory_info()
                p.memory_percent = psutil_p.memory_percent()
                p.cpu_times = psutil_p.cpu_times()._asdict()
                p.cpu_percent = psutil_p.cpu_percent()
                p.executable = psutil_p.exe()
                p.cmd_line = psutil_p.cmdline()
                p.num_open_file_descriptors = psutil_p.num_fds()
                p.num_connections = len(psutil_p.connections())
                try:
                    p.io_counters = psutil_p.io_counters()._asdict()
                except:
                    pass
                p.num_open_files = len(psutil_p.open_files())
                p.num_threads = psutil_p.num_threads()
                p.num_ctx_switches = psutil_p.num_ctx_switches()._asdict()
            return p
        except Exception as e:
            self.logger.exception(e)

    def _capture_cpu(self):
        capt_cpu = self.conf.get("cpu", False)
        capt_per_cpu = self.conf.get("per_cpu", False)
        if not (capt_cpu or capt_per_cpu):
            return None
        try:
            cpu = Telemetry.CPU()
            if capt_cpu:
                cpu.times_avg = psutil.cpu_times(percpu=False)._asdict()
                cpu.percent_all = psutil.cpu_percent()
            if capt_per_cpu:
                cpu.times_per_cpu = [
                    c._asdict() for c in psutil.cpu_times(percpu=True)
                ]
                cpu.percent_per_cpu = psutil.cpu_percent(percpu=True)
            return cpu
        except Exception as e:
            self.logger.exception(e)
            return None

    def _capture_gpu(self):
        capt = self.conf.get("gpu", False)
        if not capt:
            return None

        try:
            deviceCount = nvmlDeviceGetCount()
            handle = nvmlDeviceGetHandleByIndex(0)
            info = nvmlDeviceGetMemoryInfo(handle)
            _this_gpu = {
                "total": info.total,
                "free": info.free,
                "used": info.used,
                "usage_percent": info.used / info.total * 100,
                "temperature": nvmlDeviceGetTemperature(
                    handle, NVML_TEMPERATURE_GPU
                ),
                "power_usage": nvmlDeviceGetPowerUsage(handle),
            }
            gpu = Telemetry.GPU()
            if deviceCount == 1:
                gpu.gpu_sums = gpu.GPUMetrics(**_this_gpu)
            else:
                gpu.per_gpu = {0: gpu.GPUMetrics(**_this_gpu)}
                sums = _this_gpu.copy()
                for i in range(1, deviceCount):
                    handle = nvmlDeviceGetHandleByIndex(i)
                    info = nvmlDeviceGetMemoryInfo(handle)
                    _temp = nvmlDeviceGetTemperature(
                        handle, pynvml.NVML_TEMPERATURE_GPU
                    )
                    _pow = nvmlDeviceGetPowerUsage(handle)

                    sums["total"] += info.total
                    sums["free"] += info.free
                    sums["used"] += info.used
                    sums["temperature"] += _temp
                    sums["power_usage"] += _pow

                    gpu.per_gpu[i] = gpu.GPUMetrics(
                        total=info.total,
                        free=info.free,
                        used=info.used,
                        usage_percent=info.used / info.total * 100,
                        temperature=_temp,
                        power_usage=_pow,
                    )

                sums["usage_percent"] = sums["used"] / sums["total"] * 100
                gpu.gpu_sums = gpu.GPUMetrics(**sums)

            return gpu
        except Exception as e:
            self.logger.exception(e)
            return None

    def init_gpu_telemetry(self):
        if self.conf is None:
            return None

        if self.conf.get("gpu", False):
            try:
                nvmlInit()
            except Exception as e:
                self.logger.error("NVIDIA GPU NOT FOUND!")
                self.logger.exception(e)

    def shutdown_gpu_telemetry(self):
        if self.conf is None:
            return None

        if self.conf.get("gpu", False):
            try:
                nvmlShutdown()
            except Exception as e:
                self.logger.error("NVIDIA GPU NOT FOUND!")
                self.logger.exception(e)
