/**
 * Compression — gzip large batch payloads before upload, using Node's
 * built-in `zlib` (no dependency needed). Tiny payloads aren't
 * compressed (the ticket's "Do not compress tiny payloads"): gzip's own
 * framing overhead can make a small payload *larger*.
 */

import { gzipSync } from "node:zlib";

export const DEFAULT_THRESHOLD_BYTES = 1024;

export interface CompressResult {
  body: Uint8Array;
  compressed: boolean;
}

export function maybeCompress(
  body: Uint8Array,
  thresholdBytes: number = DEFAULT_THRESHOLD_BYTES,
): CompressResult {
  if (body.byteLength < thresholdBytes) {
    return { body, compressed: false };
  }
  return { body: gzipSync(body), compressed: true };
}

/** 1.0 means no reduction; 0.25 means the compressed body is a quarter
 * of the original size. */
export function compressionRatio(originalBytes: number, compressedBytes: number): number {
  if (originalBytes <= 0) return 1.0;
  return compressedBytes / originalBytes;
}
