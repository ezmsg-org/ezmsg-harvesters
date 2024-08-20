from typing import Optional
from genicam.genapi import EAccessMode, EVisibility
from uuid import UUID
from magicgui import widgets as mw
from qtpy import QtWidgets
from ezmsg.vispy.frontends.main_window import register_response

from ._spec import (
    BaseFeatureSpec,
    FeatureSpecs,
    IntegerFeatureSpec,
    CommandFeatureSpec,
    BooleanFeatureSpec,
    EnumFeatureSpec,
    Source,
    StringFeatureSpec,
    FloatFeatureSpec,
    CategoryFeatureSpec,
    FeatureValue,
)


def build_widgets_from_spec(
    specs: list[BaseFeatureSpec],
    cb_visibility: Optional[mw.ComboBox] = None,
    mapping={},
):
    widgets = mw.Container(labels=False, layout="vertical")

    if cb_visibility is None:
        cb_visibility = mw.ComboBox(
            choices=[
                vis for vis in EVisibility._member_names_ if not vis.startswith("_")
            ]
        )
        widgets.native_parent_changed.connect(
            lambda: cb_visibility.changed.emit(cb_visibility.value)
        )
        widgets.append(
            mw.Container(
                widgets=(mw.Label(value="Visibility"), cb_visibility),
                layout="horizontal",
            )
        )
    else:
        widgets.labels = True

    for spec in specs:
        if isinstance(spec, CategoryFeatureSpec):
            widget, _ = build_widgets_from_spec(spec.children, cb_visibility, mapping)
            category_label = mw.Label(name=spec.display_name)
            widget.insert(0, category_label)
            cb_visibility.changed.connect(
                check_container_visibility(widget, category_label),
                priority=-1,
            )
        elif isinstance(spec, IntegerFeatureSpec):
            kwargs = {
                "value": spec.value,
                "name": spec.display_name,
            }
            if spec.min is not None:
                kwargs["min"] = spec.min
            if spec.max is not None:
                kwargs["max"] = spec.max
            if spec.inc is not None:
                kwargs["step"] = spec.inc
            widget = mw.SpinBox(**kwargs)
        elif isinstance(spec, CommandFeatureSpec):
            widget = mw.PushButton(
                name=spec.display_name,
            )
        elif isinstance(spec, BooleanFeatureSpec):
            widget = mw.ComboBox(
                value=spec.value,
                choices=[True, False],
                name=spec.display_name,
            )
        elif isinstance(spec, EnumFeatureSpec):
            widget = mw.ComboBox(
                value=spec.value,
                choices=spec.items,
                name=spec.display_name,
            )
        elif isinstance(spec, StringFeatureSpec):
            widget = mw.LineEdit(
                value=spec.value,
                name=spec.display_name,
            )
        elif isinstance(spec, FloatFeatureSpec):
            widget = mw.LineEdit(
                value=spec.value,
                name=spec.display_name,
            )
        else:
            raise ValueError(f"Unexpected Feature Spec, {spec=}")

        if (
            not isinstance(spec, CategoryFeatureSpec)
            and not isinstance(spec, CommandFeatureSpec)
        ) and spec.access_mode == EAccessMode.RO:
            widget.enabled = False

        if not isinstance(widget, mw.Container):
            cb_visibility.changed.connect(check_widget_visibility(widget, spec))
            widget.changed.connect(on_value_changed(widget, spec.uuid))

        widgets.append(widget)
        mapping[spec.uuid] = widget
    return widgets, mapping


def check_widget_visibility(widget, spec):
    def inner(level):
        if spec.visibility > EVisibility[level]:
            widget.visible = False
            widget.visible_override = False
        else:
            widget.visible = True
            widget.visible_override = True

    return inner


def check_container_visibility(con: mw.Container, label: mw.Label):
    def inner(_):
        if any([each.visible_override for each in con if each != label]) is False:
            label.visible = False
        else:
            label.visible = True

    return inner


def on_value_changed(widget: mw.Widget, uuid: UUID):
    def inner(value):
        mw = widget.native.window()
        mw.command_signal.emit(FeatureValue(Source.CONTROLLER, uuid, value))

    return inner


class GenicamController(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.mapping = {}

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(self.scroll_area)

    @register_response(FeatureSpecs)
    def on_feature_specs(self, specs: FeatureSpecs):
        widgets, mapping = build_widgets_from_spec(specs)
        self.scroll_area.setWidget(widgets.native)
        self.mapping = mapping

    @register_response(FeatureValue)
    def on_feature_value(self, feature: FeatureValue):
        if feature.source != Source.CAMERA:
            return

        if feature.uuid in self.mapping:
            widget = self.mapping[feature.uuid]
            with widget.changed.blocked():
                widget.value = feature.value
