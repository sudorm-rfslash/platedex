"""The iOS Shortcut that uploads original photos from the share sheet.

iPhones only import shortcuts from iCloud links or signed files, and neither can be changed per
user, so the token isn't baked in. The admin shares one copy of the Shortcut as an iCloud link
(README → "iOS Shortcut") and pastes it in More → Admin. Its import question asks for the setup
code that More → API tokens copies for each person ("<server>#<token>"); the Shortcut splits it
into the server address and the token.

`platedex build-shortcut` writes the template the admin starts from.
"""

import plistlib
import re
import uuid
from pathlib import Path
from typing import Any

SEPARATOR = "#"
OBJ = "\ufffc"  # placeholder character where a variable sits inside a text field
_ICLOUD = re.compile(r"^https://(?:www\.)?icloud\.com/shortcuts/([0-9a-f]{32})/?(?:[?#].*)?$", re.IGNORECASE)


def clean_icloud_url(url: str) -> str | None:
    """The canonical form of an iCloud Shortcut link, or None if it isn't one."""
    m = _ICLOUD.match(url.strip())
    return f"https://www.icloud.com/shortcuts/{m.group(1).lower()}" if m else None


def _id() -> str:
    return str(uuid.uuid4()).upper()


def _out(uid: str, name: str) -> dict[str, Any]:
    return {"Type": "ActionOutput", "OutputUUID": uid, "OutputName": name}


def _var(ref: dict[str, Any]) -> dict[str, Any]:
    return {"Value": ref, "WFSerializationType": "WFTextTokenAttachment"}


def _text(s: str, refs: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    """A text field; refs maps the position of each OBJ placeholder to the variable shown there."""
    value: dict[str, Any] = {"string": s}
    if refs:
        value["attachmentsByRange"] = {f"{{{pos}, 1}}": ref for pos, ref in refs.items()}
    return {"Value": value, "WFSerializationType": "WFTextTokenString"}


def _fields(items: list[tuple[int, str, dict[str, Any]]]) -> dict[str, Any]:
    """Header or form fields. Item types: 0 = text, 5 = file."""
    return {
        "Value": {
            "WFDictionaryFieldValueItems": [
                {"WFItemType": kind, "WFKey": _text(key), "WFValue": value} for kind, key, value in items
            ]
        },
        "WFSerializationType": "WFDictionaryFieldValue",
    }


def _action(ident: str, **params: Any) -> dict[str, Any]:
    return {"WFWorkflowActionIdentifier": f"is.workflow.actions.{ident}", "WFWorkflowActionParameters": params}


def build() -> dict[str, Any]:
    code, clean, parts, server, token, upload, detail = (_id() for _ in range(7))
    loop, check = _id(), _id()
    repeat_item = _var({"Type": "Variable", "VariableName": "Repeat Item"})

    actions = [
        # 0: filled in by the import question (keep it first; the question points at index 0)
        _action("gettext", UUID=code, WFTextActionText=""),
        # Pasted text often brings a trailing newline or space; tokens never contain whitespace.
        _action("text.replace", UUID=clean, WFInput=_var(_out(code, "Text")), WFReplaceTextFind=r"\s+",
                WFReplaceTextReplace="", WFReplaceTextRegularExpression=True),
        _action("text.split", UUID=parts, text=_var(_out(clean, "Updated Text")), WFTextSeparator="Custom",
                WFTextCustomSeparator=SEPARATOR),
        _action("getitemfromlist", UUID=server, WFInput=_var(_out(parts, "Split Text")),
                WFItemSpecifier="First Item"),
        _action("getitemfromlist", UUID=token, WFInput=_var(_out(parts, "Split Text")),
                WFItemSpecifier="Last Item"),
        _action("repeat.each", UUID=_id(), GroupingIdentifier=loop, WFControlFlowMode=0,
                WFInput=_var({"Type": "ExtensionInput"})),
        _action(
            "downloadurl",
            UUID=upload,
            WFURL=_text(f"{OBJ}/api/photos", {0: _out(server, "Item from List")}),
            WFHTTPMethod="POST",
            ShowHeaders=True,
            WFHTTPHeaders=_fields([(0, "Authorization", _text(f"Bearer {OBJ}", {7: _out(token, "Item from List")}))]),
            WFHTTPBodyType="Form",
            WFFormValues=_fields([(5, "file", repeat_item), (0, "capture_mode", _text("token"))]),
        ),
        # Errors come back as {"detail": "..."}: show it and stop instead of claiming success.
        _action("getvalueforkey", UUID=detail, WFInput=_var(_out(upload, "Contents of URL")),
                WFDictionaryKey="detail"),
        _action("conditional", UUID=_id(), GroupingIdentifier=check, WFControlFlowMode=0, WFCondition=100,
                WFInput={"Type": "Variable", "Variable": _var(_out(detail, "Dictionary Value"))}),
        _action("alert", UUID=_id(), WFAlertActionTitle="Platedex upload failed",
                WFAlertActionMessage=_text(OBJ, {0: _out(detail, "Dictionary Value")}),
                WFAlertActionCancelButtonShown=False),
        _action("exit", UUID=_id()),
        _action("conditional", UUID=_id(), GroupingIdentifier=check, WFControlFlowMode=2),
        _action("repeat.each", UUID=_id(), GroupingIdentifier=loop, WFControlFlowMode=2),
        _action("notification", UUID=_id(), WFNotificationActionTitle="Platedex",
                WFNotificationActionBody="Sent. Plates are read on the server; results show in Upload.",
                WFNotificationActionSound=False),
    ]
    return {
        "WFWorkflowClientVersion": "2302.0.4",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 59511},
        "WFWorkflowTypes": ["ActionExtension"],  # show in the share sheet
        "WFWorkflowInputContentItemClasses": ["WFImageContentItem", "WFPhotoMediaContentItem",
                                              "WFGenericFileContentItem"],
        "WFWorkflowHasShortcutInputVariables": True,
        # Run from the Shortcuts app or home screen: ask which photos to send.
        "WFWorkflowNoInputBehavior": {"Name": "WFWorkflowNoInputBehaviorAskForInput",
                                      "Parameters": {"ItemClass": "WFPhotoMediaContentItem"}},
        "WFWorkflowImportQuestions": [
            {"ActionIndex": 0, "Category": "Parameter", "ParameterKey": "WFTextActionText", "DefaultValue": "",
             "Text": "Paste your setup code from Platedex (More → API tokens → Set up iPhone Shortcut)"}
        ],
        "WFWorkflowActions": actions,
        "WFWorkflowOutputContentItemClasses": [],
        "WFQuickActionSurfaces": [],
    }


def write_unsigned(path: Path) -> Path:
    path.write_bytes(plistlib.dumps(build(), fmt=plistlib.FMT_BINARY))
    return path
