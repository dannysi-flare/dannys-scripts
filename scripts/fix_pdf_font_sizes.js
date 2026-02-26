#!/usr/bin/env node
/**
 * Fix PDF Form Font Sizes
 *
 * This script fixes PDF form templates by setting consistent font sizes
 * across all text fields. It addresses issues where some form fields
 * have different font sizes embedded in their Default Appearance (DA),
 * causing inconsistent text rendering.
 *
 * What it does:
 * 1. Embeds Helvetica font into the PDF
 * 2. Sets all text fields to use the same font size (default: 9pt) in their DA
 * 3. Preserves existing appearance streams (for template visibility)
 * 4. Removes NeedAppearances flag so PDF readers use existing appearances
 *
 * Note: The new font size applies when values are filled in at runtime.
 *
 * Usage:
 *   node fix_pdf_font_sizes.js <input.pdf> <output.pdf> [fontSize]
 *
 * Arguments:
 *   input.pdf   - Path to the source PDF form template
 *   output.pdf  - Path where the fixed PDF will be saved
 *   fontSize    - (Optional) Font size in points, default is 9
 *
 * Examples:
 *   node fix_pdf_font_sizes.js fl105_clean.pdf fl105_fixed.pdf
 *   node fix_pdf_font_sizes.js fl140.pdf fl140_fixed.pdf 10
 *
 * Requirements:
 *   - Node.js
 *   - pdf-lib package (npm install pdf-lib)
 *
 * Note: Run this from the vinny directory to use its pdf-lib installation:
 *   cd ~/src/vinny && node ~/src/dannys-scripts/scripts/fix_pdf_font_sizes.js ...
 *
 * Or install pdf-lib globally:
 *   npm install -g pdf-lib
 */

const { PDFDocument, PDFName, PDFString, PDFDict, PDFRef, StandardFonts } = require('pdf-lib');
const fs = require('fs');
const path = require('path');

async function fixPDFFontSizes(inputPath, outputPath, fontSize = 9) {
  console.log(`\nFixing PDF font sizes...`);
  console.log(`  Input:  ${inputPath}`);
  console.log(`  Output: ${outputPath}`);
  console.log(`  Font size: ${fontSize}pt\n`);

  // Load the PDF
  const pdfBytes = fs.readFileSync(inputPath);
  const pdfDoc = await PDFDocument.load(pdfBytes);
  const form = pdfDoc.getForm();

  // Embed Helvetica font
  const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
  const fontName = font.name;

  console.log(`Embedded font: ${fontName}`);

  const fields = form.getFields();
  let modifiedCount = 0;
  let skippedCount = 0;

  for (const field of fields) {
    const name = field.getName();
    const acro = field.acroField;
    const dict = acro.dict;

    // Check if it's a text field (FT = /Tx)
    const ft = dict.get(PDFName.of('FT'));
    if (ft && ft.toString() === '/Tx') {
      // Get current DA for logging
      const currentDA = acro.getDefaultAppearance();

      // Set new DA with consistent font and size
      // Format: /FontName fontSize Tf colorValue g
      const newDA = `/${fontName} ${fontSize} Tf 0 g`;
      dict.set(PDFName.of('DA'), PDFString.of(newDA));

      // Note: We preserve existing appearance streams (AP) for template PDFs
      // The new DA will apply when values are filled in at runtime

      modifiedCount++;

      // Log a few examples
      if (modifiedCount <= 5) {
        console.log(`  Modified: ${name}`);
        console.log(`    Old DA: ${currentDA}`);
        console.log(`    New DA: ${newDA}`);
      }
    } else {
      skippedCount++;
    }
  }

  if (modifiedCount > 5) {
    console.log(`  ... and ${modifiedCount - 5} more text fields`);
  }

  console.log(`\nSummary:`);
  console.log(`  Text fields modified: ${modifiedCount}`);
  console.log(`  Other fields skipped: ${skippedCount}`);

  // Remove NeedAppearances flag so PDF readers use existing appearances
  // instead of trying to regenerate them (which can fail in Acrobat Reader)
  const context = pdfDoc.context;
  let acroForm = pdfDoc.catalog.get(PDFName.of('AcroForm'));
  if (acroForm instanceof PDFRef) {
    acroForm = context.lookup(acroForm);
  }
  if (acroForm instanceof PDFDict) {
    const hadNeedAppearances = acroForm.get(PDFName.of('NeedAppearances'));
    acroForm.delete(PDFName.of('NeedAppearances'));
    if (hadNeedAppearances) {
      console.log(`Removed NeedAppearances flag`);
    }
  }

  // Save the modified PDF
  const modifiedPdfBytes = await pdfDoc.save();
  fs.writeFileSync(outputPath, modifiedPdfBytes);

  console.log(`\nSaved to: ${outputPath}`);
  console.log(`Done!\n`);
}

// CLI handling
function printUsage() {
  console.log(`
Usage: node fix_pdf_font_sizes.js <input.pdf> <output.pdf> [fontSize]

Arguments:
  input.pdf   - Path to the source PDF form template
  output.pdf  - Path where the fixed PDF will be saved
  fontSize    - (Optional) Font size in points, default is 9

Examples:
  node fix_pdf_font_sizes.js fl105_clean.pdf fl105_fixed.pdf
  node fix_pdf_font_sizes.js fl140.pdf fl140_fixed.pdf 10
`);
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length < 2 || args.includes('--help') || args.includes('-h')) {
    printUsage();
    process.exit(args.includes('--help') || args.includes('-h') ? 0 : 1);
  }

  const inputPath = path.resolve(args[0]);
  const outputPath = path.resolve(args[1]);
  const fontSize = args[2] ? parseInt(args[2], 10) : 9;

  if (!fs.existsSync(inputPath)) {
    console.error(`Error: Input file not found: ${inputPath}`);
    process.exit(1);
  }

  if (isNaN(fontSize) || fontSize < 1 || fontSize > 72) {
    console.error(`Error: Invalid font size: ${args[2]}. Must be between 1 and 72.`);
    process.exit(1);
  }

  try {
    await fixPDFFontSizes(inputPath, outputPath, fontSize);
  } catch (error) {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  }
}

main();
