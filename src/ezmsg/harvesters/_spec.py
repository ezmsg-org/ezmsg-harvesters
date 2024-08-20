import enum
from typing import Any, Protocol
from genicam.genapi import EInterfaceType, EAccessMode, EVisibility
from dataclasses import dataclass, field
from uuid import uuid4, UUID


__all__ = [
    "BaseFeatureSpec",
    "FeatureSpecs",
    "IntegerFeatureSpec",
    "CommandFeatureSpec",
    "BooleanFeatureSpec",
    "EnumFeatureSpec",
    "StringFeatureSpec",
    "FloatFeatureSpec",
    "CategoryFeatureSpec",
    "FeatureValue",
    "Source",
]


class BaseFeatureSpec(Protocol):
    uuid: UUID
    display_name: str
    interface_type: EInterfaceType
    visibility: EVisibility


@dataclass
class IntegerFeatureSpec:
    display_name: str
    visibility: EVisibility
    access_mode: EAccessMode
    value: int
    min: int | None = None
    max: int | None = None
    inc: int | None = None
    interface_type: EInterfaceType = EInterfaceType.intfIInteger
    uuid: UUID = field(default_factory=uuid4)


@dataclass
class CommandFeatureSpec:
    display_name: str
    visibility: EVisibility
    interface_type: EInterfaceType = EInterfaceType.intfICommand
    uuid: UUID = field(default_factory=uuid4)


@dataclass
class BooleanFeatureSpec:
    display_name: str
    visibility: EVisibility
    access_mode: EAccessMode
    value: bool
    interface_type: EInterfaceType = EInterfaceType.intfIBoolean
    uuid: UUID = field(default_factory=uuid4)


@dataclass
class EnumFeatureSpec:
    display_name: str
    visibility: EVisibility
    access_mode: EAccessMode
    value: str
    items: list[str]
    interface_type: EInterfaceType = EInterfaceType.intfIEnumeration
    uuid: UUID = field(default_factory=uuid4)


@dataclass
class StringFeatureSpec:
    display_name: str
    visibility: EVisibility
    access_mode: EAccessMode
    value: str
    interface_type: EInterfaceType = EInterfaceType.intfIString
    uuid: UUID = field(default_factory=uuid4)


@dataclass
class FloatFeatureSpec:
    display_name: str
    visibility: EVisibility
    access_mode: EAccessMode
    value: float
    interface_type: EInterfaceType = EInterfaceType.intfIFloat
    uuid: UUID = field(default_factory=uuid4)


@dataclass
class CategoryFeatureSpec:
    display_name: str
    visibility: EVisibility
    children: list[BaseFeatureSpec]
    interface_type: EInterfaceType = EInterfaceType.intfICategory
    uuid: UUID = field(default_factory=uuid4)


class Source(enum.Enum):
    CAMERA = enum.auto()
    CONTROLLER = enum.auto()


@dataclass
class FeatureValue:
    source: Source
    uuid: UUID
    value: Any


class FeatureSpecs(list[BaseFeatureSpec]): ...


def build_feature_spec(features, mapping: dict = {}):
    feature_specs = []
    for feature in features:
        display_name = feature.node.display_name
        visibility = feature.node.visibility
        interface_type = feature.node.principal_interface_type
        if interface_type == EInterfaceType.intfICategory:
            children, _ = build_feature_spec(feature.features, mapping)
            spec = CategoryFeatureSpec(
                display_name=feature.node.display_name,
                visibility=feature.node.get_access_mode(),
                children=children,
            )
        elif interface_type == EInterfaceType.intfIInteger:
            access_mode = feature.node.get_access_mode()
            if access_mode == EAccessMode.RW:
                spec = IntegerFeatureSpec(
                    display_name=display_name,
                    visibility=visibility,
                    access_mode=access_mode,
                    min=feature.min,
                    max=feature.max,
                    inc=feature.inc,
                    value=feature.value,
                )
            elif access_mode == EAccessMode.RO:
                spec = IntegerFeatureSpec(
                    display_name=display_name,
                    visibility=visibility,
                    access_mode=access_mode,
                    value=feature.value,
                )
            elif access_mode == EAccessMode.NA:
                # print(display_name)  # NOTE: So far, this is only Timestamp
                pass
            else:
                raise ValueError(f"Unexpected {EAccessMode(access_mode)=}")

        elif interface_type == EInterfaceType.intfICommand:
            spec = CommandFeatureSpec(
                display_name=display_name,
                visibility=visibility,
            )
        elif interface_type == EInterfaceType.intfIBoolean:
            spec = BooleanFeatureSpec(
                display_name=display_name,
                visibility=visibility,
                access_mode=feature.node.get_access_mode(),
                value=feature.value,
            )
        elif interface_type == EInterfaceType.intfIEnumeration:
            spec = EnumFeatureSpec(
                display_name=display_name,
                visibility=visibility,
                access_mode=feature.node.get_access_mode(),
                value=feature.value,
                items=[entry.symbolic for entry in feature.entries],
            )
        elif interface_type == EInterfaceType.intfIString:
            spec = StringFeatureSpec(
                display_name=display_name,
                visibility=visibility,
                access_mode=feature.node.get_access_mode(),
                value=feature.value,
            )
        elif interface_type == EInterfaceType.intfIFloat:
            spec = FloatFeatureSpec(
                display_name=display_name,
                visibility=visibility,
                access_mode=feature.node.get_access_mode(),
                value=feature.value,
            )
        else:
            raise ValueError("Unexpected interface type")

        # Precautionary
        while spec.uuid in mapping:
            spec.uuid = uuid4()

        feature_specs.append(spec)
        mapping[spec.uuid] = feature
    return feature_specs, mapping
