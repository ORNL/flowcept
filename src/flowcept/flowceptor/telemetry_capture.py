"""Telemetry module."""

from typing import Callable, Set, List

import platform

import os

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    TELEMETRY_CAPTURE,
    HOSTNAME,
    LOGIN_NAME,
)
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry

if TELEMETRY_CAPTURE is not None and len(TELEMETRY_CAPTURE):
    import psutil
    import cpuinfo


class GPUCapture:
    """GPU Capture class."""

    VISIBLE_GPUS: List = None
    GPU_VENDOR: str = None
    GPU_HANDLES = None
    capture_func: Callable = None

    @staticmethod
    def _initialize_nvidia():
        """Initialize NVIDIA GPU."""
        try:
            from pynvml import nvmlDeviceGetCount, nvmlInit

            visible_devices_var = os.environ.get("CUDA_VISIBLE_DEVICES")
            if visible_devices_var:
                visible_devices = [int(i) for i in visible_devices_var.split(",")]
            else:
                nvmlInit()
                visible_devices = list(range(nvmlDeviceGetCount()))

            GPUCapture.GPU_VENDOR = "nvidia"
            GPUCapture.VISIBLE_GPUS = visible_devices
            GPUCapture.GPU_HANDLES = []  # TODO: Handle GPU handles if needed
            GPUCapture.capture_func = GPUCapture.__get_gpu_info_nvidia
        except Exception as e:
            FlowceptLogger().debug(str(e))

    @staticmethod
    def _initialize_amd():
        """Initialize AMD GPU."""
        try:
            from amdsmi import (
                amdsmi_init,
                amdsmi_get_processor_handles,
            )

            visible_devices_var = os.environ.get("ROCR_VISIBLE_DEVICES")
            amdsmi_init()
            GPUCapture.GPU_HANDLES = amdsmi_get_processor_handles()

            if visible_devices_var:
                visible_devices = [int(i) for i in visible_devices_var.split(",")]
            else:
                visible_devices = list(range(len(GPUCapture.GPU_HANDLES)))

            GPUCapture.VISIBLE_GPUS = visible_devices
            GPUCapture.GPU_VENDOR = "amd"
            GPUCapture.capture_func = GPUCapture.__get_gpu_info_amd

        except Exception as e:
            FlowceptLogger().debug(str(e))

    @staticmethod
    def _init_gpu():
        if TELEMETRY_CAPTURE is not None and TELEMETRY_CAPTURE.get("gpu", None) is not None:
            if TELEMETRY_CAPTURE.get("gpu", None) is not None:
                # First, try AMD:
                GPUCapture._initialize_amd()
                # If didn't work, try Nvidia
                if not GPUCapture.GPU_VENDOR:
                    GPUCapture._initialize_nvidia()

            if not GPUCapture.VISIBLE_GPUS:
                FlowceptLogger().error("We couldn't see any GPU, but your settings have GPU telemetry capture.")
            elif len(GPUCapture.VISIBLE_GPUS):
                FlowceptLogger().debug(f"Visible GPUs in Flowcept Capture: {GPUCapture.VISIBLE_GPUS}")

    @staticmethod
    def shutdown():
        """Shutdown GPU Telemetry capture."""
        if GPUCapture.GPU_VENDOR == "nvidia":
            try:
                nvmlShutdown()
            except Exception as e:
                FlowceptLogger().exception(e)
        elif GPUCapture.GPU_VENDOR == "amd":
            try:
                amdsmi_shut_down()
            except Exception as e:
                FlowceptLogger().exception(e)
        else:
            FlowceptLogger().error("Could not end any GPU!")
        FlowceptLogger().debug("GPU capture end!")

    @staticmethod
    def __get_gpu_info_nvidia(gpu_conf: Set = None, gpu_ix: int = 0):
        device = nvmlDeviceGetHandleByIndex(gpu_ix)
        nvidia_info = nvmlDeviceGetMemoryInfo(device)
        flowcept_gpu_info = {}

        if "used" in gpu_conf:
            flowcept_gpu_info["used"] = nvidia_info.used

        if "temperature" in gpu_conf:
            flowcept_gpu_info["temperature"] = nvmlDeviceGetTemperature(device, NVML_TEMPERATURE_GPU)

        if "power" in gpu_conf:
            flowcept_gpu_info["power"] = nvmlDeviceGetPowerUsage(device)

        if "name" in gpu_conf:
            flowcept_gpu_info["name"] = nvmlDeviceGetName(device)

        if "id" in gpu_conf:
            flowcept_gpu_info["id"] = nvmlDeviceGetUUID(device)

        return flowcept_gpu_info

    @staticmethod
    def __get_gpu_info_amd(gpu_conf: Set = None, gpu_ix: int = 0):
        # See: https://rocm.docs.amd.com/projects/amdsmi/en/docs-5.7.1/py-interface_readme_link.html#api
        device = GPUCapture.GPU_HANDLES[gpu_ix]
        flowcept_gpu_info = {"gpu_ix": gpu_ix}

        if "used" in gpu_conf:
            flowcept_gpu_info["used"] = amdsmi_get_gpu_memory_usage(device, AmdSmiMemoryType.VRAM)

        if "activity" in gpu_conf:
            flowcept_gpu_info["activity"] = amdsmi_get_gpu_activity(device)

        if "power" in gpu_conf or "temperature" in gpu_conf or "others" in gpu_conf:
            all_metrics = amdsmi_get_gpu_metrics_info(device)
        else:
            return flowcept_gpu_info

        if "power" in gpu_conf:
            flowcept_gpu_info["power"] = {
                "average_socket_power": all_metrics["average_socket_power"],
                "energy_accumulator": all_metrics["energy_accumulator"],
                # "current_socket_power": all_metrics["current_socket_power"],
            }

        if "temperature" in gpu_conf:
            flowcept_gpu_info["temperature"] = {
                "edge": all_metrics["temperature_edge"],
                "hotspot": all_metrics["temperature_hotspot"],
                "mem": all_metrics["temperature_mem"],
                "vrgfx": all_metrics["temperature_vrgfx"],
                "vrmem": all_metrics["temperature_vrmem"],
                "hbm": all_metrics["temperature_hbm"],
                "fan_speed": all_metrics["current_fan_speed"],
            }
        if "others" in gpu_conf:
            flowcept_gpu_info["others"] = {
                "current_gfxclk": all_metrics["current_gfxclk"],
                "current_socclk": all_metrics["current_socclk"],
                "current_uclk": all_metrics["current_uclk"],
                "current_vclk0": all_metrics["current_vclk0"],
                "current_dclk0": all_metrics["current_dclk0"],
            }

        if "id" in gpu_conf:
            flowcept_gpu_info["id"] = amdsmi_get_gpu_device_uuid(device)

        return flowcept_gpu_info


GPUCapture._init_gpu()

if GPUCapture.GPU_VENDOR == "amd":
    from amdsmi import (
        amdsmi_get_gpu_memory_usage,
        amdsmi_shut_down,
        AmdSmiMemoryType,
        amdsmi_get_gpu_activity,
        amdsmi_get_gpu_metrics_info,
        amdsmi_get_gpu_device_uuid,
    )

    FlowceptLogger().debug("Imported AMD modules!")
elif GPUCapture.GPU_VENDOR == "nvidia":
    from pynvml import (
        nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetName,
        nvmlShutdown,
        nvmlDeviceGetTemperature,
        nvmlDeviceGetPowerUsage,
        NVML_TEMPERATURE_GPU,
        nvmlDeviceGetUUID,
    )

    FlowceptLogger().debug("Imported Nvidia modules!")


class TelemetryCapture:
    """Telemetry class."""

    def __init__(self, conf=TELEMETRY_CAPTURE):
        self.logger = FlowceptLogger()
        self.conf = conf
        self._gpu_conf = None
        if self.conf is not None:
            self._gpu_conf = self.conf.get("gpu", {})
            if self._gpu_conf is not None:
                self._gpu_conf = set(self._gpu_conf)

    def capture(self) -> Telemetry:
        """Capture it."""
        if not self.conf:
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

        if self._gpu_conf is not None:  # TODO we might want to turn all tel types into lists
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
            network_info_raw = psutil.net_if_addrs()
            network_info = {ifname: [addr._asdict() for addr in addrs] for ifname, addrs in network_info_raw.items()}
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
                p.num_connections = len(psutil_p.net_connections())
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
                cpu.frequency = psutil.cpu_freq().current

            if capt_per_cpu:
                cpu.times_per_cpu = [c._asdict() for c in psutil.cpu_times(percpu=True)]
                cpu.percent_per_cpu = psutil.cpu_percent(percpu=True)
            return cpu
        except Exception as e:
            self.logger.exception(e)
            return None

    def _capture_gpu(self):
        try:
            if GPUCapture.VISIBLE_GPUS is None or self._gpu_conf is None or len(self._gpu_conf) == 0:
                return
            gpu_telemetry = {}
            for gpu_ix in GPUCapture.VISIBLE_GPUS:
                gpu_telemetry[f"gpu_{gpu_ix}"] = GPUCapture.capture_func(self._gpu_conf, gpu_ix)
            return gpu_telemetry
        except Exception as e:
            self.logger.exception(e)
            return None

    def shutdown_gpu_telemetry(self):
        """Shutdown GPU telemetry."""
        if GPUCapture.VISIBLE_GPUS is None or self._gpu_conf is None or len(self._gpu_conf) == 0:
            self.logger.debug("GPU capture is off or has never been initialized, so we won't shut down.")
            return None
        GPUCapture.shutdown()
