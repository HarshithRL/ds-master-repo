export const MAX_FILE_BYTES = 40 * 1024 * 1024;
export const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".pptx"];
export const FILE_ACCEPT = ".pdf,.docx,.xlsx,.pptx";

export function isAllowedFile(file) {
  const name = (file.name || "").toLowerCase();
  return ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export function validateStagedFile(file) {
  if (!isAllowedFile(file)) {
    return "Use PDF, DOCX, XLSX, or PPTX files.";
  }
  if (file.size > MAX_FILE_BYTES) {
    return "Each file must be 40 MB or smaller.";
  }
  return null;
}

export function addStagedFiles(current, incoming) {
  const next = [...current];
  const errors = [];

  for (const file of incoming) {
    const problem = validateStagedFile(file);
    if (problem) {
      errors.push(`${file.name}: ${problem}`);
      continue;
    }
    const already = next.some(
      (staged) => staged.name === file.name && staged.size === file.size,
    );
    if (!already) {
      next.push(file);
    }
  }

  return { files: next, errors };
}

export function formatFileSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
