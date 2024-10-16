"""Telemetry module."""

import psutil
import platform
import cpuinfo
import os

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    TELEMETRY_CAPTURE,
    N_GPUS,
    GPU_HANDLES,
    GPU_TYPE,
    HOSTNAME,
    LOGIN_NAME,
)
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry

if GPU_TYPE == "nvidia":
    try:
        from pynvml import (
            nvmlDeviceGetHandleByIndex,
            nvmlDeviceGetMemoryInfo,
            nvmlDeviceGetName,
            nvmlShutdown,
            nvmlDeviceGetTemperature,
            nvmlDeviceGetPowerUsage,
            NVML_TEMPERATURE_GPU,
        )
    except Exception as e:
        print(f"We could not import NVIDIA libs: {e}")
    pass

if GPU_TYPE == "amd":
    try:
        from amdsmi import (
            amdsmi_get_gpu_memory_usage,
            amdsmi_shut_down,
            AmdSmiMemoryType,
            AmdSmiTemperatureType,
            amdsmi_get_gpu_activity,
            amdsmi_get_power_info,
            amdsmi_get_gpu_device_uuid,
            amdsmi_get_temp_metric,
            AmdSmiTemperatureMetric,
            amdsmi_get_gpu_metrics_info,
        )
    except Exception as e:
        print(f"Exception to import AMD libs! {e}")
        pass


class TelemetryCapture:
    """Telemetry class."""

    # TODO: refactor; I need this to avoid querying GPU stuff that is
    # generating errors. The idea is to try once and if it fails, add this in
    # this dictionary to avoid trying again. The mapping will be
    # {gpu_device_id:{query_type: True or False}}; False if it found that
    # it's unsuccessful. If it's mapping to an empty dict, the whole GPU is
    # bad for capture.
    _gpu_unsuccessful_queries = dict()

    def __init__(self, conf=TELEMETRY_CAPTURE):
        self.logger = FlowceptLogger()
        self.conf = conf
        if self.conf is not None:
            self._visible_gpus = None
            self._gpu_type = GPU_TYPE
            self._gpu_conf = self.conf.get("gpu", None)

            if self._gpu_conf is None:
                return

            if isinstance(self._gpu_conf, str):
                self._gpu_conf = eval(self.conf.get("gpu", "None"))

            if self._gpu_conf is None:
                return

            self._gpu_conf = set(self._gpu_conf)

            if len(self._gpu_conf):
                self.logger.info(f"These are the visible GPUs by Flowcept Capture: {N_GPUS}")
                # TODO: refactor! This below is bad coding
                nvidia = N_GPUS.get("nvidia", [])
                amd = N_GPUS.get("amd", [])
                if len(nvidia):
                    self._visible_gpus = nvidia
                    self._gpu_capture_func = self.__get_gpu_info_nvidia
                elif len(amd):
                    self._visible_gpus = amd
                    self._gpu_capture_func = self.__get_gpu_info_amd
                else:
                    self.logger.exception(
                        "No GPU found. Consider disabling GPU capture in the settings file."
                    )

    def capture(self) -> Telemetry:
        """Capture it."""
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

        if self._gpu_conf is not None and len(
            self._gpu_conf
        ):  # TODO we might want to turn all tel types into lists
            tel.gpu = self._capture_gpu()

        return tel

    def capture_machine_info(self):
        """Capture info."""
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
            if self._gpu_conf is not None and len(self._gpu_conf):
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
                except Exception:
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
                except Exception:
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
                cpu.times_per_cpu = [c._asdict() for c in psutil.cpu_times(percpu=True)]
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
            "temperature": nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU),
            "power_usage": nvmlDeviceGetPowerUsage(handle),
            "name": nvmlDeviceGetName(handle),
            "device_ix": gpu_ix,
        }
        return flowcept_gpu_info

    def __register_unsuccessful_gpu_query(self, gpu_ix, gpu_info_key):
        self.logger.error(f"Error to get {gpu_info_key} for the GPU device ix {gpu_ix}")
        if gpu_ix not in TelemetryCapture._gpu_unsuccessful_queries:
            TelemetryCapture._gpu_unsuccessful_queries[gpu_ix] = {}
        TelemetryCapture._gpu_unsuccessful_queries[gpu_ix][gpu_info_key] = True

    def __get_gpu_info_amd(self, gpu_ix: int = 0):
        # See: https://rocm.docs.amd.com/projects/amdsmi/en/docs-5.7.1/py-interface_readme_link.html#api
        device = GPU_HANDLES[gpu_ix]
        flowcept_gpu_info = {"gpu_ix": gpu_ix}

        if "used" in self._gpu_conf:
            flowcept_gpu_info["used"] = amdsmi_get_gpu_memory_usage(device, AmdSmiMemoryType.VRAM)
        if "usage" in self._gpu_conf:
            flowcept_gpu_info["usage"] = amdsmi_get_gpu_activity(device)
        if "power" in self._gpu_conf:
            flowcept_gpu_info["power"] = amdsmi_get_power_info(device)
        if "id" in self._gpu_conf:
            flowcept_gpu_info["id"] = amdsmi_get_gpu_device_uuid(device)
        if "temperature" in self._gpu_conf:
            temperature = {
                "vram": amdsmi_get_temp_metric(
                    device,
                    AmdSmiTemperatureType.VRAM,
                    AmdSmiTemperatureMetric.CURRENT,
                ),
                "hotspot": amdsmi_get_temp_metric(
                    device,
                    AmdSmiTemperatureType.HOTSPOT,
                    AmdSmiTemperatureMetric.CURRENT,
                ),
                "edge": amdsmi_get_temp_metric(
                    device,
                    AmdSmiTemperatureType.EDGE,
                    AmdSmiTemperatureMetric.CURRENT,
                ),
            }
            flowcept_gpu_info["temperature"] = temperature
        if (
            "metrics" in self._gpu_conf
        ):  # USE IT CAREFULLY because it contains redundant information
            flowcept_gpu_info["metrics"] = amdsmi_get_gpu_metrics_info(device)
        return flowcept_gpu_info

    def _capture_gpu(self):
        try:
            if self._visible_gpus is None or self._gpu_conf is None or len(self._gpu_conf) == 0:
                return
            gpu_telemetry = {}
            for gpu_ix in self._visible_gpus:
                gpu_telemetry[f"gpu_{gpu_ix}"] = self._gpu_capture_func(gpu_ix)
            return gpu_telemetry
        except Exception as e:
            self.logger.exception(e)
            return None

    def shutdown_gpu_telemetry(self):
        """Shutdown GPU telemetry."""
        if (
            self.conf is None
            or self._visible_gpus is None
            or self._gpu_conf is None
            or len(self._gpu_conf) == 0
        ):
            self.logger.debug(
                "GPU capture is off or has never been initialized, so we won't shut down."
            )
            return None
        if self._gpu_type == "nvidia":
            try:
                nvmlShutdown()
            except Exception as e:
                self.logger.error("Error to shutdown GPU capture")
                self.logger.exception(e)
        elif self._gpu_type == "amd":
            try:
                amdsmi_shut_down()
            except Exception as e:
                self.logger.error("Error to shutdown GPU capture")
                self.logger.exception(e)
        else:
            self.logger.error("Could not end any GPU!")
        self.logger.debug("GPU capture end!")
