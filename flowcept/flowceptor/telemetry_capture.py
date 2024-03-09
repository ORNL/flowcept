import psutil
import platform
import cpuinfo
import os

try:
    import pynvml
    from pynvml import (
        nvmlDeviceGetCount,
        nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetName,
        nvmlInit,
        nvmlShutdown,
        nvmlDeviceGetTemperature,
        nvmlDeviceGetPowerUsage,
        NVML_TEMPERATURE_GPU,
    )
except:
    pass
try:
    import pyamdgpuinfo
except:
    pass
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import TELEMETRY_CAPTURE, N_GPUS, HOSTNAME, LOGIN_NAME
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry


class TelemetryCapture:
    _gpu_unsuccessful_queries = (
        dict()
    )  # TODO: refactor; I need this to avoid querying GPU stuff that is generating errors. The idea is to try once and if it fails, add this in this dictionary to avoid trying again. The mapping will be {gpu_device_id: {query_type: True or False}}; False if it found that it's unsuccessful. If it's mapping to an empty dict, the whole GPU is bad for capture.

    def __init__(self, conf=TELEMETRY_CAPTURE):
        self.conf = conf
        self.logger = FlowceptLogger()

    def capture(self) -> Telemetry:
        if self.conf is None:
            return None
        tel = Telemetry()
        if self.conf.get("process_info", False):
            tel.process = self._capture_process_info()

        capt_cpu = self.conf.get("cpu", False)
        capt_per_cpu = self.conf.get("per_cpu", False)
        if capt_cpu or capt_per_cpu:
            tel.cpu = self._capture_cpu(capt_cpu, capt_per_cpu)

        if self.conf.get("mem", False):
            tel.memory = self._capture_memory()

        if self.conf.get("network", False):
            tel.network = self._capture_network()

        if self.conf.get("disk", False):
            tel.disk = self._capture_disk()

        if self.conf.get("gpu", False):
            tel.gpu = self._capture_gpu()

        return tel

    def capture_machine_info(self):
        # TODO: add ifs for each type of telem; improve this method overall
        if self.conf is None or self.conf.get("machine_info", None) is None:
            return None

        try:
            mem = Telemetry.Memory()
            mem.virtual = psutil.virtual_memory()._asdict()
            mem.swap = psutil.swap_memory()._asdict()

            disk = Telemetry.Disk()
            disk.disk_usage = psutil.disk_usage("/")._asdict()

            platform_info = platform.uname()._asdict()
            network_info = psutil.net_if_addrs()
            processor_info = cpuinfo.get_cpu_info()

            gpu_info = None
            if self.conf.get("gpu", False):
                gpu_info = self._capture_gpu()

            info = {
                "memory": {"swap": mem.swap, "virtual": mem.virtual},
                "disk": disk.disk_usage,
                "platform": platform_info,
                "cpu": processor_info,
                "network": network_info,
                "environment": dict(os.environ),
                "hostname": HOSTNAME,
                "login_name": LOGIN_NAME,
                "process": self._capture_process_info().__dict__,
            }
            if gpu_info is not None:
                info["gpu"] = gpu_info
            return info
        except Exception as e:
            self.logger.exception(e)
            return None

    def _capture_disk(self):
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
        try:
            mem = Telemetry.Memory()
            mem.virtual = psutil.virtual_memory()._asdict()
            mem.swap = psutil.swap_memory()._asdict()
            return mem
        except Exception as e:
            self.logger.exception(e)

    def _capture_process_info(self):
        try:
            p = Telemetry.Process()
            psutil_p = psutil.Process()
            with psutil_p.oneshot():
                p.pid = psutil_p.pid
                try:
                    p.cpu_number = psutil_p.cpu_num()
                except:
                    pass
                p.memory = psutil_p.memory_info()._asdict()
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

    def _capture_cpu(self, capt_cpu, capt_per_cpu):
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

    def __get_gpu_info_nvidia(self, gpu_ix: int = 0):
        try:
            handle = nvmlDeviceGetHandleByIndex(gpu_ix)
            nvidia_info = nvmlDeviceGetMemoryInfo(handle)
        except Exception as e:
            self.logger.exception(e)
            return {}

        flowcept_gpu_info = {
            "total": nvidia_info.total,
            "used": nvidia_info.used,
            "temperature": nvmlDeviceGetTemperature(
                handle, NVML_TEMPERATURE_GPU
            ),
            "power_usage": nvmlDeviceGetPowerUsage(handle),
            "name": nvmlDeviceGetName(handle),
            "device_ix": gpu_ix,
        }
        return flowcept_gpu_info

    def __register_unsuccessful_gpu_query(self, gpu_ix, gpu_info_key):
        self.logger.error(
            f"Error to get {gpu_info_key} for the GPU device ix {gpu_ix}"
        )
        if gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries:
            TelemetryCapture._gpu_unsuccessful_queries[gpu_ix] = {}
        TelemetryCapture._gpu_unsuccessful_queries[gpu_ix][
            gpu_info_key
        ] = True

    # TODO: finish adding the else: None
    def __get_gpu_info_amd(self, gpu_ix: int = 0):
        flowcept_gpu_info = {}
        try:
            amd_info = pyamdgpuinfo.get_gpu(gpu_ix)
        except Exception as e:
            self.logger.exception(e)
            TelemetryCapture._gpu_unsuccessful_queries[gpu_ix] = {}
            return flowcept_gpu_info

        flowcept_gpu_info["device_ix"] = gpu_ix

        flowcept_gpu_info["gpu_id"] = amd_info.gpu_id
        memory_info = amd_info.memory_info.copy()
        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "total"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info["total"] = memory_info.pop("vram_size")
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "total")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "temperature"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info[
                    "temperature"
                ] = amd_info.query_temperature()
        except Exception as e:
            flowcept_gpu_info["temperature"] = None
            self.__register_unsuccessful_gpu_query(gpu_ix, "temperature")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "power_usage"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info["power_usage"] = amd_info.query_power()
        except Exception as e:
            flowcept_gpu_info["power_usage"] = None
            self.__register_unsuccessful_gpu_query(gpu_ix, "power_usage")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "used"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info["used"] = amd_info.query_vram_usage()
        except Exception as e:
            flowcept_gpu_info["used"] = None
            self.__register_unsuccessful_gpu_query(gpu_ix, "used")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "max_shader_clock"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                max_clocks = amd_info.query_max_clocks()
                flowcept_gpu_info["max_shader_clock"] = max_clocks["sclk_max"]
                flowcept_gpu_info["max_memory_clock"] = max_clocks["mclk_max"]
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "max_shader_clock")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "shader_clock"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info["shader_clock"] = amd_info.query_sclk()
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "shader_clock")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "memory_clock"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info["memory_clock"] = amd_info.query_mclk()
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "memory_clock")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "gtt_usage"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info["gtt_usage"] = amd_info.query_gtt_usage()
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "gtt_usage")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "load"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info["load"] = amd_info.query_load()
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "load")
            self.logger.exception(e)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "graphics_voltage"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                flowcept_gpu_info[
                    "graphics_voltage"
                ] = amd_info.query_graphics_voltage()
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "graphics_voltage")
            self.logger.exception(e)

        flowcept_gpu_info.update(memory_info)

        try:
            if (
                gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries
                or "name"
                not in TelemetryCapture._gpu_unsuccessful_queries[gpu_ix]
            ):
                name = amd_info.name
                if name is not None:
                    flowcept_gpu_info["name"] = name
        except Exception as e:
            self.__register_unsuccessful_gpu_query(gpu_ix, "name")
            self.logger.exception(e)

        return flowcept_gpu_info

    def _capture_gpu(self):
        try:
            self.logger.debug(
                f"These are the visible GPUs by Flowcept Capture: {N_GPUS}"
            )
            if len(N_GPUS) == 0:
                self.logger.exception(
                    "You are trying to capture telemetry GPU info, but we"
                    " couldn't detect any GPU, neither NVIDIA nor AMD."
                    " Please set GPU telemetry capture to false."
                )
                return None

            n_nvidia_gpus = N_GPUS.get("nvidia", [])
            n_amd_gpus = N_GPUS.get("amd", [])

            if len(n_nvidia_gpus) > 0:
                n_gpus = n_nvidia_gpus
                gpu_capture_func = self.__get_gpu_info_nvidia
            elif len(n_amd_gpus) > 0:
                n_gpus = n_amd_gpus
                gpu_capture_func = self.__get_gpu_info_amd
            else:
                self.logger.exception("This should never happen.")
                return None

            gpu_telemetry = {}
            for gpu_ix in n_gpus:
                gpu_telemetry[gpu_ix] = gpu_capture_func(gpu_ix)

            return gpu_telemetry
        except Exception as e:
            self.logger.exception(e)
            return None

    def init_gpu_telemetry(self):
        if self.conf is None:
            return None
        # These methods are only needed for NVIDIA GPUs
        if N_GPUS.get("nvidia", 0) > 0:
            try:
                nvmlInit()
            except Exception as e:
                self.logger.error("NVIDIA GPU NOT FOUND!")
                self.logger.exception(e)

    def shutdown_gpu_telemetry(self):
        if self.conf is None:
            return None
        # These methods are only needed for NVIDIA GPUs
        if N_GPUS.get("nvidia", 0) > 0:
            try:
                nvmlShutdown()
            except Exception as e:
                self.logger.error("NVIDIA GPU NOT FOUND!")
                self.logger.exception(e)
