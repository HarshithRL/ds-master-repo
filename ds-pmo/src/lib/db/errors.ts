// Databricks SQL has no P2002/P2025-style error codes — uniqueness and
// existence checks happen app-side (pre-insert SELECT, pre-update lookup),
// and throw these so withHandler's catch block can map them to HTTP status
// via `instanceof` instead of an error-code switch.

export class ConflictError extends Error {
  constructor(message = "A record with this value already exists") {
    super(message);
    this.name = "ConflictError";
  }
}

export class NotFoundError extends Error {
  constructor(message = "Record not found") {
    super(message);
    this.name = "NotFoundError";
  }
}
