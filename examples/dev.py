import ezmsg.core as ez
from ezmsg.util.messages.axisarray import AxisArray
from ezmsg.harvesters import HarvesterCam, HarvesterCamSettings
from ezmsg.harvesters._gui import GenicamController
from ezmsg.vispy.frontends.main_window import EzMainWindow
from ezmsg.vispy.units.application import Application, ApplicationSettings
from ezmsg.vispy.units.image_vis import ImageVis, ImageVisSettings
from qtpy import QtWidgets
from typing import Any


class GenicamFrontend(EzMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        cw = QtWidgets.QSplitter()

        self.setCentralWidget(cw)

        self.genicam = GenicamController()
        cw.addWidget(self.genicam)
        self.add_callbacks(self.genicam)
        self.plot = QtWidgets.QWidget()
        cw.addWidget(self.plot)


class GenicamApp(ez.Collection):
    # Streams for application interface
    IMAGE_INPUT = ez.InputStream(AxisArray)
    APP_INPUT = ez.InputStream(Any)
    APP_OUTPUT = ez.OutputStream(Any)

    # Application
    APP = Application()

    # Plot units
    IMAGE = ImageVis()

    def configure(self) -> None:
        # Configure plots
        self.IMAGE.apply_settings(
            ImageVisSettings(
                data_attr="data",
                clim="auto",
                cmap="viridis",
                external_timer=True,
            )
        )
        self.APP.apply_settings(
            ApplicationSettings(
                window=GenicamFrontend,
                width=640,
                height=1000,
                external_timer=True,
                external_timer_interval=33,
            )
        )

        self.APP.visuals = {
            "plot": self.IMAGE,
        }

    def network(self) -> ez.NetworkDefinition:
        return (
            (self.IMAGE_INPUT, self.IMAGE.INPUT),
            (self.APP_INPUT, self.APP.INPUT),
            (self.APP.OUTPUT, self.APP_OUTPUT),
        )


if __name__ == "__main__":
    cam = HarvesterCam(
        HarvesterCamSettings(
            # cti_file=".venv/lib/python3.10/site-packages/genicam/TLSimu.cti",
            cti_file="/Library/Application Support/Allied Vision/Vimba X/cti/VimbaGigETL.cti",
            connect_first_available=True,
            # auto_start=True,
        )
    )
    app = GenicamApp()
    ez.run(
        CAM=cam,
        APP=app,
        connections=(
            (cam.OUTPUT_SIGNAL, app.IMAGE_INPUT),
            (cam.OUTPUT_CTRL, app.APP_INPUT),
            (app.APP_OUTPUT, cam.INPUT_CTRL),
        ),
    )
