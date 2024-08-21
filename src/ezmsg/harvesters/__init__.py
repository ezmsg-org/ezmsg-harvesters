import asyncio
import enum
import ezmsg.core as ez
import numpy as np
from copy import deepcopy
from uuid import UUID
from dataclasses import field
from ezmsg.util.messages.axisarray import AxisArray
from genicam.genapi import (
    IBoolean,
    ICategory,
    ICommand,
    IEnumeration,
    IFloat,
    IInteger,
    IString,
)
from harvesters.core import Harvester, ImageAcquirer, TimeoutException
from harvesters.util.pfnc import is_custom, get_bits_per_pixel, bgr_formats
from harvesters.util.pfnc import (
    mono_location_formats,
    rgb_formats,
    rgba_formats,
    bgra_formats,
    bayer_location_formats,
)
from pathlib import Path
from typing import Any, Optional, Union
from ._spec import (
    FeatureSpecs,
    FeatureValue,
    Source,
    build_feature_spec,
)


class Mode(enum.Enum):
    STOPPED = enum.auto()
    PAUSED = enum.auto()
    STARTED = enum.auto()


class HarvesterCamSettings(ez.Settings):
    cti_file: Union[Path, str]
    profile: bool = False
    connect_first_available: bool = False
    auto_start: bool = False
    cam_timeout: float = 0.0001


class HarvesterCamState(ez.State):
    mode_change_ev: asyncio.Event
    core: Harvester
    ia: Optional[ImageAcquirer] = None
    mode: Mode = Mode.STOPPED
    mapping: dict[UUID, Any] = field(default_factory=dict)


class HarvesterCam(ez.Unit):
    SETTINGS: HarvesterCamSettings
    STATE: HarvesterCamState

    INPUT_CTRL = ez.InputStream(Any)
    OUTPUT_CTRL = ez.OutputStream(Any)

    OUTPUT_SIGNAL = ez.OutputStream(AxisArray)

    async def initialize(self) -> None:
        self.STATE.mode_change_ev = asyncio.Event()
        self.STATE.core = Harvester(profile=self.SETTINGS.profile, logger=ez.logger)
        self.STATE.core.add_file(str(self.SETTINGS.cti_file))

        self.STATE.core.update()

        if (
            len(self.STATE.core.device_info_list)
            and self.SETTINGS.connect_first_available is True
        ):
            self.STATE.ia = self.STATE.core.create(0)

        if self.SETTINGS.auto_start is True and self.STATE.ia is not None:
            self.STATE.mode = Mode.STARTED
            self.STATE.ia.start()

    @ez.publisher(OUTPUT_CTRL)
    async def send_ctrl(self):
        if self.STATE.ia is not None:
            specs, mapping = build_feature_spec(
                self.STATE.ia.remote_device.node_map.Root.features
            )
            self.STATE.mapping = mapping
            yield self.OUTPUT_CTRL, FeatureSpecs(specs)

    @ez.subscriber(INPUT_CTRL)
    @ez.publisher(OUTPUT_CTRL)
    async def on_ctrl(self, message: FeatureValue):
        if message.source != Source.CONTROLLER:
            return

        if message.uuid not in self.STATE.mapping:
            ez.logger.warning(f"UUID not found in mapping! {message.uuid=}")
            return

        ez.logger.info(f"Received {message=}")
        feature = self.STATE.mapping[message.uuid]
        if isinstance(feature, ICategory):
            pass
        elif isinstance(feature, ICommand):
            feature.execute()

            display_name = feature.node.display_name
            if (
                display_name.replace(" ", "") == "AcquisitionStart"
                and self.STATE.mode is not Mode.STARTED
            ):
                if self.STATE.ia is not None:
                    self.STATE.ia.start()
                self.STATE.mode = Mode.STARTED
                specs, mapping = build_feature_spec(
                    self.STATE.ia.remote_device.node_map.Root.features
                )
                self.STATE.mapping = mapping
                self.STATE.mode_change_ev.set()
                yield self.OUTPUT_CTRL, FeatureSpecs(specs)
            elif (
                display_name.replace(" ", "") == "AcquisitionStop"
                and self.STATE.mode is not Mode.STOPPED
            ):
                if self.STATE.ia is not None:
                    self.STATE.ia.stop()
                self.STATE.mode = Mode.STOPPED
                specs, mapping = build_feature_spec(
                    self.STATE.ia.remote_device.node_map.Root.features
                )
                self.STATE.mapping = mapping
                self.STATE.mode_change_ev.set()
                yield self.OUTPUT_CTRL, FeatureSpecs(specs)

        elif (
            isinstance(feature, IInteger)
            or isinstance(feature, IFloat)
            or isinstance(feature, IBoolean)
            or isinstance(feature, IEnumeration)
            or isinstance(feature, IString)
        ):
            try:
                feature.value = message.value
            except Exception as e:
                ez.logger.warning(e)
                yield (
                    self.OUTPUT_CTRL,
                    FeatureValue(Source.CAMERA, message.uuid, feature.value),
                )
        else:
            raise ValueError("Unexpected interface type")

    @ez.publisher(OUTPUT_SIGNAL)
    async def on_image(self):
        while True:
            match self.STATE.mode:
                case Mode.STARTED:
                    if self.STATE.ia is None:
                        continue

                    try:
                        buffer = self.STATE.ia.fetch(timeout=self.SETTINGS.cam_timeout)
                    except TimeoutException:
                        print("Timed out! Sleeping...")
                        await asyncio.sleep(0.1)
                    else:
                        print("Image received!")
                        if buffer is None:
                            continue
                        payload = buffer.payload
                        component = payload.components[0]
                        width = component.width
                        height = component.height
                        data_format_value = component.data_format_value
                        if is_custom(data_format_value):
                            data_format = None
                        else:
                            data_format = component.data_format

                        bpp = get_bits_per_pixel(data_format)
                        if bpp is not None:
                            exponent = bpp - 8
                        else:
                            exponent = 0

                        if (
                            data_format in mono_location_formats
                            or data_format in bayer_location_formats
                        ):
                            content = component.data.reshape(height, width)
                        else:
                            # The image requires you to reshape it to draw it on the
                            # canvas:
                            if (
                                data_format in rgb_formats
                                or data_format in rgba_formats
                                or data_format in bgr_formats
                                or data_format in bgra_formats
                            ):
                                content = component.data.reshape(
                                    height,
                                    width,
                                    int(component.num_components_per_pixel),
                                )
                                if data_format in bgr_formats:
                                    # Swap every R and B so that VisPy can display
                                    # it as an RGB image:
                                    content = content[:, :, ::-1]
                            else:
                                raise Exception("Should not reach this.")

                            # Convert each data to an 8bit.
                            if exponent > 0:
                                # The following code may affect to the rendering
                                # performance:
                                content = content / (2**exponent)

                                # Then cast each array element to an uint8:
                                content = content.astype(np.uint8)

                        axis_arr_out = AxisArray(
                            data=deepcopy(content),
                            dims=["rows", "cols"],
                            axes={
                                "rows": AxisArray.Axis(),
                                "cols": AxisArray.Axis(),
                            },
                        )
                        yield (self.OUTPUT_SIGNAL, axis_arr_out)

                        buffer.queue()
                    await asyncio.sleep(1 / 90)
                case Mode.STOPPED:
                    await self.STATE.mode_change_ev.wait()
                    self.STATE.mode_change_ev.clear()
                case Mode.PAUSED:
                    await self.STATE.mode_change_ev.wait()
                    self.STATE.mode_change_ev.clear()

    async def shutdown(self) -> None:
        if self.STATE.ia is not None:
            self.STATE.ia.stop()
        self.STATE.core.reset()
