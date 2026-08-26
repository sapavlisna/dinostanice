"""Print-ready template sheets.

Rasterises every template at true scale (default 300 DPI on landscape A4) and
writes a multi-page PDF plus one PDF per creature. Nothing is ever scaled to
fit: the millimetre grid of the sheet has to survive printing, otherwise the
homography built from the corner markers puts the drawing in the wrong place.
"""

import argparse
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dinostanice import creatures, template  # noqa: E402
from dinostanice.shapes import SHEET_W_MM, SHEET_H_MM  # noqa: E402

OUT_DIR = ROOT / "data" / "templates" / "tisk"
MM_PER_INCH = 25.4

FONT_CANDIDATES = {
    False: ["segoeui.ttf", "arial.ttf", "calibri.ttf", "DejaVuSans.ttf"],
    True: ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf"],
}
FONT_DIRS = [pathlib.Path("C:/Windows/Fonts"), pathlib.Path("/usr/share/fonts/truetype/dejavu")]

MOTION_CZ = {
    "walk": "chodí po břehu",
    "swim": "plave v laguně",
    "fly": "létá nad lagunou",
    "sail": "pluje po hladině",
}

STEPS = [
    ("Vytiskni", "Každé zvíře má vlastní list A4 na šířku. V dialogu tisku zvol "
                 "„Skutečná velikost“ nebo „100 %“ — nikdy „Přizpůsobit stránce“."),
    ("Vybarvi", "Pastelky, fixy i vodovky fungují. Vybarvi celé zvíře až k obrysu; "
                "čím pestřejší, tím lépe je pak na televizi vidět."),
    ("Rohy nech být", "Čtyři černobílé čtverce v rozích nevybarvuj, nepřelepuj a "
                      "neustřihni. Podle nich počítač pozná, kde list leží a koho jsi vybarvil."),
    ("Polož a nasviť", "Dej list na rovný stůl tak, aby na něj svítilo světlo a "
                       "nepadal na něj stín tvé hlavy ani mobilu."),
    ("Vyfoť", "V mobilu otevři stránku /pridat, vyfoť celý list shora (všechny "
              "čtyři rohy musí být na fotce) a odešli."),
    ("Kouzlo", "Za pár vteřin se tvoje zvíře objeví na televizi a rozejde se "
               "po pravěké krajině mezi ostatními."),
]

PARENT_NOTE = (
    "Pro rodiče: tiskněte bez zmenšení. Na každém listu je nahoře vlevo "
    "kontrolní úsečka — po vytištění musí měřit přesně 100 mm. Pokud měří méně, "
    "tiskárna list zmenšila a rozpoznávání bude nepřesné."
)


def find_font(size_px, bold=False):
    for directory in FONT_DIRS:
        for name in FONT_CANDIDATES[bold]:
            path = directory / name
            if path.exists():
                return ImageFont.truetype(str(path), size_px)
    return ImageFont.load_default(size_px)


class Sheet:
    """Landscape A4 canvas addressed in millimetres."""

    def __init__(self, ppm, background=None):
        self.ppm = ppm
        self.w = int(round(SHEET_W_MM * ppm))
        self.h = int(round(SHEET_H_MM * ppm))
        if background is None:
            self.img = Image.new("L", (self.w, self.h), 255)
        else:
            self.img = background
        self.draw = ImageDraw.Draw(self.img)

    def px(self, mm):
        return mm * self.ppm

    def font(self, size_mm, bold=False):
        return find_font(max(6, int(round(size_mm * self.ppm))), bold)

    def text(self, x_mm, y_mm, txt, size_mm, bold=False, anchor="ls", fill=90):
        self.draw.text((self.px(x_mm), self.px(y_mm)), txt, font=self.font(size_mm, bold),
                       fill=fill, anchor=anchor)

    def wrap(self, txt, size_mm, width_mm, bold=False):
        font = self.font(size_mm, bold)
        words, lines, cur = txt.split(), [], ""
        for word in words:
            trial = (cur + " " + word).strip()
            if self.draw.textlength(trial, font=font) <= self.px(width_mm) or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def paragraph(self, x_mm, y_mm, txt, size_mm, width_mm, line_mm, bold=False, fill=70):
        for i, line in enumerate(self.wrap(txt, size_mm, width_mm, bold)):
            self.text(x_mm, y_mm + i * line_mm, line, size_mm, bold, fill=fill)
        return y_mm + len(self.wrap(txt, size_mm, width_mm, bold)) * line_mm


def scale_bar(sheet, x_mm, y_mm, length_mm=100.0):
    """Printed ruler: if this is not exactly 100 mm the sheet was rescaled."""
    d, p = sheet.draw, sheet.px
    lw = max(1, int(round(0.35 * sheet.ppm)))
    d.line([(p(x_mm), p(y_mm)), (p(x_mm + length_mm), p(y_mm))], fill=90, width=lw)
    for x in (x_mm, x_mm + length_mm / 2, x_mm + length_mm):
        tick = 2.5 if x != x_mm + length_mm / 2 else 1.5
        d.line([(p(x), p(y_mm - tick)), (p(x), p(y_mm))], fill=90, width=lw)
    sheet.text(x_mm, y_mm - 3.4, "100 mm — po vytištění změř pravítkem", 3.2)


def render_sheet(creature, index, ppm):
    bgr = template.rasterise(creature, index, ppm=ppm, with_label=False)
    sheet = Sheet(ppm, Image.fromarray(bgr[:, :, 1]))
    scale_bar(sheet, 35.0, 19.0)
    sheet.text(SHEET_W_MM - 31.0, 19.0, creature.label, 6.0, bold=True, anchor="rs", fill=60)
    sheet.text(SHEET_W_MM - 31.0, 14.0,
               "vybarvi mě · " + MOTION_CZ.get(creature.motion, ""), 3.6, anchor="rs", fill=120)
    return sheet.img


def thumbnail(creature, index, height_px):
    small = template.rasterise(creature, index, ppm=3.0, with_markers=False, with_label=False)
    img = Image.fromarray(small[:, :, 1])
    w = int(round(height_px * SHEET_W_MM / SHEET_H_MM))
    return img.resize((w, height_px), Image.LANCZOS)


def render_cover(ppm):
    sheet = Sheet(ppm)
    d, p = sheet.draw, sheet.px

    sheet.text(SHEET_W_MM / 2, 30.0, "Dinosauří stanice", 14.0, bold=True, anchor="ms", fill=25)
    sheet.text(SHEET_W_MM / 2, 40.0, "Vybarvi zvíře, vyfoť ho a ono ti obživne na televizi.",
               5.0, anchor="ms", fill=110)
    d.line([(p(35), p(46)), (p(SHEET_W_MM - 35), p(46))], fill=190, width=max(1, int(ppm * 0.3)))

    y = 57.0
    col_x, col_w = 35.0, 108.0
    for i, (title, body) in enumerate(STEPS):
        if i == 3:
            y, col_x = 57.0, 156.0
        d.ellipse([p(col_x - 9), p(y - 5.2), p(col_x - 2), p(y + 1.8)], fill=225)
        sheet.text(col_x - 5.5, y, str(i + 1), 4.4, bold=True, anchor="ms", fill=40)
        sheet.text(col_x, y, title, 5.0, bold=True, fill=30)
        y = sheet.paragraph(col_x, y + 6.0, body, 3.9, col_w, 5.0, fill=95) + 6.5

    box_y = 132.0
    d.rectangle([p(35), p(box_y), p(SHEET_W_MM - 35), p(box_y + 20)], outline=180,
                width=max(1, int(ppm * 0.3)))
    sheet.paragraph(40.0, box_y + 7.0, PARENT_NOTE, 3.9, 217.0, 5.2, fill=80)

    sheet.text(35.0, 165.0, "Šest šablon v této sadě", 5.0, bold=True, fill=40)
    th = int(round(sheet.px(26)))
    gap = (SHEET_W_MM - 70.0) / 6.0
    for i, creature in enumerate(creatures.CATALOGUE):
        thumb = thumbnail(creature, i, th)
        cx = 35.0 + gap * (i + 0.5)
        sheet.img.paste(thumb, (int(p(cx) - thumb.width // 2), int(p(170.0))))
        sheet.text(cx, 203.0, creature.label, 3.8, bold=True, anchor="ms", fill=50)
        sheet.text(cx, 207.5, MOTION_CZ.get(creature.motion, ""), 3.2, anchor="ms", fill=130)
    return sheet.img


def save_pdf(path, pages, dpi_x, dpi_y):
    pages[0].save(path, "PDF", save_all=True, append_images=pages[1:], dpi=(dpi_x, dpi_y))


def main():
    ap = argparse.ArgumentParser(description="Vygeneruje tiskovou sadu šablon.")
    ap.add_argument("--dpi", type=float, default=300.0)
    ap.add_argument("--out", type=pathlib.Path, default=OUT_DIR)
    ap.add_argument("--png", action="store_true", help="uložit i PNG náhledy stránek")
    args = ap.parse_args()

    ppm = args.dpi / MM_PER_INCH
    args.out.mkdir(parents=True, exist_ok=True)

    cover = render_cover(ppm)
    # The rounded pixel raster is what defines the page box, so derive the
    # resolution back from it; that keeps the PDF page exactly 297 x 210 mm.
    dpi_x = cover.width / (SHEET_W_MM / MM_PER_INCH)
    dpi_y = cover.height / (SHEET_H_MM / MM_PER_INCH)

    pages = [cover]
    for i, creature in enumerate(creatures.CATALOGUE):
        page = render_sheet(creature, i, ppm)
        pages.append(page)
        single = args.out / ("%d-%s.pdf" % (i + 1, creature.key))
        save_pdf(single, [page], dpi_x, dpi_y)
        if args.png:
            page.save(args.out / ("%d-%s.png" % (i + 1, creature.key)), dpi=(args.dpi, args.dpi))

    save_pdf(args.out / "dinostanice-tisk.pdf", pages, dpi_x, dpi_y)
    if args.png:
        cover.save(args.out / "0-navod.png", dpi=(args.dpi, args.dpi))

    print("Hotovo: %s" % args.out)
    print("  dinostanice-tisk.pdf  (%d stránek, %.0f DPI, %d x %d px)"
          % (len(pages), args.dpi, cover.width, cover.height))
    print("  stránka = %.2f x %.2f mm"
          % (cover.width / dpi_x * MM_PER_INCH, cover.height / dpi_y * MM_PER_INCH))


if __name__ == "__main__":
    main()
