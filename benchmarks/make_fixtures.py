"""Original synthetic drawings, CC0; no real personal information."""

import json
from pathlib import Path

from PIL import Image, ImageDraw

p = Path("tests/fixtures")
p.mkdir(exist_ok=True)
rows = []


def save(name, im, question, choices, expected):
    im.save(p / f"{name}.png")
    rows.append(
        dict(
            name=name,
            path=str(p / f"{name}.png"),
            question=question,
            choices=choices,
            expected=expected,
        )
    )


def blank():
    return Image.new("RGB", (448, 336), "white")


for kind in ["dog", "cat", "person"]:
    im = blank()
    d = ImageDraw.Draw(im)
    if kind == "person":
        d.ellipse((190, 35, 250, 95), fill="#e6b98d")
        d.rectangle((185, 98, 255, 215), fill="blue")
        d.line((195, 210, 165, 310), fill="black", width=20)
        d.line((245, 210, 275, 310), fill="black", width=20)
        d.line((185, 115, 140, 200), fill="#e6b98d", width=18)
        d.line((255, 115, 300, 200), fill="#e6b98d", width=18)
    else:
        color = "#b97942" if kind == "dog" else "#bbbbbb"
        d.ellipse((100, 135, 320, 260), fill=color)
        d.ellipse((245, 70, 365, 180), fill=color)
        for x in (120, 170, 260, 300):
            d.rectangle((x, 220, x + 18, 300), fill=color)
        if kind == "cat":
            d.polygon([(248, 108), (250, 40), (286, 78)], fill=color)
            d.polygon([(320, 78), (360, 40), (362, 110)], fill=color)
            for y in (130, 140, 150):
                d.line((300, y, 390, y - 15), fill="black", width=2)
            d.arc((40, 60, 150, 200), 50, 270, fill=color, width=16)
        else:
            d.ellipse((238, 90, 267, 181), fill="#59351a")
            d.ellipse((320, 118, 398, 165), fill=color)
            d.ellipse((382, 120, 401, 140), fill="black")
            d.line((110, 166, 52, 103), fill=color, width=20)
        d.ellipse((323, 99, 333, 109), fill="black")
    save(kind, im, "What is depicted?", ["Dog", "Cat", "Person", "Empty room"], kind.capitalize())
im = blank()
d = ImageDraw.Draw(im)
d.rectangle((20, 20, 425, 315), outline="gray", width=3)
d.line((20, 240, 425, 240), fill="gray", width=2)
d.line((20, 315, 90, 240), fill="gray", width=2)
d.line((425, 315, 360, 240), fill="gray", width=2)
save("empty_room", im, "What is depicted?", ["Dog", "Cat", "Person", "Empty room"], "Empty room")
for kind in ["login", "error", "invoice", "medical", "ambiguous"]:
    im = blank()
    d = ImageDraw.Draw(im)
    if kind == "login":
        d.text((145, 35), "Sign in", fill="black", font_size=34)
        for y, label in [(110, "Email"), (180, "Password")]:
            d.rectangle((70, y, 378, y + 48), outline="gray", width=2)
            d.text((80, y + 8), label, fill="gray", font_size=24)
        d.rectangle((150, 265, 300, 312), fill="blue")
        d.text((174, 275), "Login", fill="white", font_size=24)
    elif kind == "error":
        d.rectangle((30, 70, 420, 245), fill="#fee2e2", outline="red", width=4)
        d.text((60, 100), "Login failed", fill="black", font_size=35)
        d.text((65, 165), "Invalid password", fill="black", font_size=26)
    elif kind in ("invoice", "medical"):
        title = "INVOICE" if kind == "invoice" else "PATIENT RECORD"
        d.text((25, 25), title, fill="black", font_size=32)
        lines = (
            ["Example Store", "Invoice #1234", "Widget    $25.00", "Total     $25.00"]
            if kind == "invoice"
            else [
                "SYNTHETIC TEST DATA",
                "Name: Alex Example",
                "DOB: 01/01/1990",
                "Visit: Routine checkup",
            ]
        )
        for i, line in enumerate(lines):
            d.text((25, 95 + i * 48), line, fill="black", font_size=23)
    else:
        d.ellipse((160, 100, 280, 220), fill="gray")
    if kind in ("login", "error"):
        save(
            kind,
            im,
            "What state is the UI in?",
            ["Login page", "Error dialog", "Dashboard", "Loading"],
            "Login page" if kind == "login" else "Error dialog",
        )
    elif kind in ("invoice", "medical"):
        save(
            kind,
            im,
            "What kind of document is this?",
            ["Invoice", "Medical record", "Letter", "Other"],
            "Invoice" if kind == "invoice" else "Medical record",
        )
    else:
        save(
            kind, im, "What does this gray shape depict?", ["Ball", "Moon", "Button", "Other"], None
        )
(p / "manifest.json").write_text(json.dumps(rows, indent=2) + "\n")
(p / "LICENSE.txt").write_text(
    "These synthetic drawings were created for this project and are dedicated to the public domain under CC0 1.0. They contain no real personal information. They are smoke/regression fixtures, not a representative accuracy or calibration dataset.\n"
)
