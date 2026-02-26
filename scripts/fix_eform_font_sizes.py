#!/usr/bin/env python3
"""Fix eform PDF fields where font size causes descender clipping.

Sets each field's font size to min(80% of field height, original font size).
Outputs a new PDF with '_fixed' suffix.
"""

import argparse
import math
import re
import pikepdf


FONT_TO_HEIGHT_RATIO = 0.80


def fix_font_sizes(input_path: str, output_path: str) -> list:
    pdf = pikepdf.open(input_path)
    fixes = []

    for page_num, page in enumerate(pdf.pages):
        if "/Annots" not in page:
            continue
        for annot in page["/Annots"]:
            obj = annot.resolve() if hasattr(annot, "resolve") else annot
            if str(obj.get("/Subtype", "")) != "/Widget":
                continue

            rect = obj.get("/Rect")
            da = str(obj.get("/DA", ""))
            if not rect or not da:
                continue

            coords = [float(x) for x in rect]
            height = coords[3] - coords[1]

            m = re.search(r"(/\S+)\s+(\d+(?:\.\d+)?)\s+Tf", da)
            if not m:
                continue

            font_name = m.group(1)
            original_size = float(m.group(2))

            # For multi-line fields, compute per-line height
            ff = int(obj.get("/Ff", 0))
            is_multiline = bool(ff & (1 << 12))
            if is_multiline:
                num_lines = max(1, round(height / original_size))
                effective_height = height / num_lines
            else:
                effective_height = height

            max_size = math.floor(effective_height * FONT_TO_HEIGHT_RATIO)
            new_size = min(original_size, max_size)

            if new_size < original_size:
                name = str(obj.get("/T", "(unknown)"))
                new_da = da.replace(m.group(0), f"{font_name} {new_size} Tf")
                obj["/DA"] = pikepdf.String(new_da)
                lines = num_lines if is_multiline else 1
                fixes.append((name, page_num + 1, original_size, new_size, height, lines))

    pdf.save(output_path)
    pdf.close()
    return fixes


def main():
    parser = argparse.ArgumentParser(description="Fix eform font sizes to prevent descender clipping")
    parser.add_argument("input", help="Input PDF path")
    parser.add_argument("-o", "--output", help="Output PDF path (default: <input>_fixed.pdf)")
    args = parser.parse_args()

    import os
    output = args.output or os.path.splitext(args.input)[0] + "_fixed.pdf"

    fixes = fix_font_sizes(args.input, output)

    if fixes:
        print(f"Fixed {len(fixes)} field(s) in {output}:")
        for name, pg, old, new, h, lines in fixes:
            print(f"  Page {pg}: {name}")
            line_info = f", {lines} lines, {h/lines:.2f}pt/line" if lines > 1 else ""
            print(f"    {old}pt → {new}pt (box height={h:.2f}pt{line_info})")
    else:
        print(f"No fixes needed. Saved to {output}")


if __name__ == "__main__":
    main()
