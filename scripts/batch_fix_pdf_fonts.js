#!/usr/bin/env node
/**
 * Batch Fix PDF Form Font Sizes
 *
 * Downloads PDF form templates from S3, fixes font sizes, and saves to local directory.
 * Preserves the S3 folder structure in the output.
 *
 * Usage:
 *   node batch_fix_pdf_fonts.js [--output <dir>] [--font-size <size>] [--dry-run]
 *
 * Options:
 *   --output, -o    Output directory (default: ~/Downloads/fixed-pdfs)
 *   --font-size, -f Font size in points (default: 8)
 *   --dry-run, -d   List files without downloading/processing
 *
 * Requirements:
 *   - Node.js
 *   - pdf-lib package
 *   - AWS CLI configured with SSO access to production
 *
 * Note: Run from vinny directory for pdf-lib access:
 *   cd ~/src/vinny && node ~/src/dannys-scripts/scripts/batch_fix_pdf_fonts.js
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Use pdf-lib from vinny's node_modules
const pdfLibPath = `${os.homedir()}/src/vinny/node_modules/pdf-lib`;
const { PDFDocument, PDFName, PDFString, PDFDict, PDFRef, StandardFonts } = require(pdfLibPath);

const S3_BUCKET = 'marble-drafts-production';
const S3_PATHS = [
  'drafts/CA/',
  'drafts/IMMIGRATION-K1-VISA-ALL-FORMS/',
];

async function listS3Files(s3Path) {
  try {
    const cmd = `aws s3 ls s3://${S3_BUCKET}/${s3Path} --recursive`;
    const output = execSync(cmd, { encoding: 'utf-8' });

    const files = output
      .split('\n')
      .filter(line => line.trim())
      .map(line => {
        const parts = line.trim().split(/\s+/);
        return parts.slice(3).join(' '); // Get the file path (after date, time, size)
      })
      .filter(file => file.toLowerCase().endsWith('.pdf'));

    return files;
  } catch (error) {
    console.error(`Error listing ${s3Path}:`, error.message);
    return [];
  }
}

async function downloadS3File(s3Key, localPath) {
  const dir = path.dirname(localPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const cmd = `aws s3 cp "s3://${S3_BUCKET}/${s3Key}" "${localPath}"`;
  execSync(cmd, { encoding: 'utf-8', stdio: 'pipe' });
}

async function fixPdfFontSizes(inputPath, outputPath, fontSize) {
  const pdfBytes = fs.readFileSync(inputPath);
  const pdfDoc = await PDFDocument.load(pdfBytes);
  const form = pdfDoc.getForm();

  // Embed Helvetica font
  const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
  const fontName = font.name;

  const fields = form.getFields();
  let modifiedCount = 0;

  for (const field of fields) {
    const acro = field.acroField;
    const dict = acro.dict;
    const ft = dict.get(PDFName.of('FT'));

    if (ft && ft.toString() === '/Tx') {
      const newDA = `/${fontName} ${fontSize} Tf 0 g`;
      dict.set(PDFName.of('DA'), PDFString.of(newDA));
      modifiedCount++;
    }
  }

  // Remove NeedAppearances flag
  const context = pdfDoc.context;
  let acroForm = pdfDoc.catalog.get(PDFName.of('AcroForm'));
  if (acroForm instanceof PDFRef) {
    acroForm = context.lookup(acroForm);
  }
  if (acroForm instanceof PDFDict) {
    acroForm.delete(PDFName.of('NeedAppearances'));
  }

  // Save
  const dir = path.dirname(outputPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const modifiedPdfBytes = await pdfDoc.save();
  fs.writeFileSync(outputPath, modifiedPdfBytes);

  return modifiedCount;
}

function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    outputDir: path.join(os.homedir(), 'Downloads', 'fixed-pdfs'),
    fontSize: 8,
    dryRun: false,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--output' || arg === '-o') {
      options.outputDir = path.resolve(args[++i]);
    } else if (arg === '--font-size' || arg === '-f') {
      options.fontSize = parseInt(args[++i], 10);
    } else if (arg === '--dry-run' || arg === '-d') {
      options.dryRun = true;
    } else if (arg === '--help' || arg === '-h') {
      console.log(`
Usage: node batch_fix_pdf_fonts.js [options]

Options:
  --output, -o <dir>     Output directory (default: ~/Downloads/fixed-pdfs)
  --font-size, -f <size> Font size in points (default: 8)
  --dry-run, -d          List files without downloading/processing
  --help, -h             Show this help message

S3 Paths processed:
  - s3://${S3_BUCKET}/drafts/CA/
  - s3://${S3_BUCKET}/drafts/IMMIGRATION-K1-VISA-ALL-FORMS/
`);
      process.exit(0);
    }
  }

  return options;
}

async function main() {
  const options = parseArgs();

  console.log('\n=== Batch PDF Font Fixer ===');
  console.log(`Output directory: ${options.outputDir}`);
  console.log(`Font size: ${options.fontSize}pt`);
  console.log(`Dry run: ${options.dryRun}`);
  console.log('');

  // Collect all PDF files
  const allFiles = [];
  for (const s3Path of S3_PATHS) {
    console.log(`Listing files in s3://${S3_BUCKET}/${s3Path}...`);
    const files = await listS3Files(s3Path);
    console.log(`  Found ${files.length} PDF files`);
    allFiles.push(...files);
  }

  console.log(`\nTotal PDF files to process: ${allFiles.length}\n`);

  if (options.dryRun) {
    console.log('Files that would be processed:');
    allFiles.forEach(file => console.log(`  ${file}`));
    console.log('\nDry run complete. Use without --dry-run to process files.');
    return;
  }

  // Process each file
  const tempDir = path.join(os.tmpdir(), 'pdf-font-fix-' + Date.now());
  fs.mkdirSync(tempDir, { recursive: true });

  let successCount = 0;
  let errorCount = 0;
  const errors = [];

  for (let i = 0; i < allFiles.length; i++) {
    const s3Key = allFiles[i];
    const relativePath = s3Key.replace(/^drafts\//, '');
    const tempPath = path.join(tempDir, path.basename(s3Key));
    const outputPath = path.join(options.outputDir, relativePath);

    process.stdout.write(`[${i + 1}/${allFiles.length}] ${path.basename(s3Key)}... `);

    try {
      // Download
      await downloadS3File(s3Key, tempPath);

      // Fix
      const modifiedCount = await fixPdfFontSizes(tempPath, outputPath, options.fontSize);

      // Cleanup temp file
      fs.unlinkSync(tempPath);

      console.log(`OK (${modifiedCount} fields)`);
      successCount++;
    } catch (error) {
      console.log(`ERROR: ${error.message}`);
      errors.push({ file: s3Key, error: error.message });
      errorCount++;
    }
  }

  // Cleanup temp directory
  try {
    fs.rmdirSync(tempDir);
  } catch (e) {
    // Ignore if not empty
  }

  // Summary
  console.log('\n=== Summary ===');
  console.log(`Successfully processed: ${successCount}`);
  console.log(`Errors: ${errorCount}`);
  console.log(`Output directory: ${options.outputDir}`);

  if (errors.length > 0) {
    console.log('\nFiles with errors:');
    errors.forEach(e => console.log(`  ${e.file}: ${e.error}`));
  }

  console.log('\nDone!');
}

main().catch(error => {
  console.error('Fatal error:', error.message);
  process.exit(1);
});
