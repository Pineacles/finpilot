import { NextRequest, NextResponse } from "next/server";

// In Docker: API_URL=http://api:8000 (internal network)
// Local dev: falls back to localhost:8001
const API_URL = process.env.API_URL || "http://localhost:8001";

const TRUST_PROXY_HEADERS = ["1", "true", "yes"].includes(
  (process.env.TRUST_PROXY_HEADERS || "").toLowerCase(),
);

export async function handler(req: NextRequest) {
  const path = req.nextUrl.pathname.replace(/^\/api/, "");
  const url = `${API_URL}/api${path}${req.nextUrl.search}`;

  const contentType = req.headers.get("content-type") || "";
  const isMultipart = contentType.includes("multipart/form-data");

  const headers: Record<string, string> = {};

  // Don't set Content-Type for multipart: fetch will set it with boundary
  if (!isMultipart) {
    headers["Content-Type"] = contentType || "application/json";
  }

  const auth = req.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const apiKey = req.headers.get("x-api-key");
  if (apiKey) headers["X-API-Key"] = apiKey;

  // Forward the client address for the backend rate limiter only when the
  // operator says a trusted proxy (e.g. Cloudflare) sets these headers.
  // Otherwise a client could send its own and pick its rate-limit bucket.
  if (TRUST_PROXY_HEADERS) {
    const cfIp = req.headers.get("cf-connecting-ip");
    if (cfIp) headers["CF-Connecting-IP"] = cfIp;
    const xff = req.headers.get("x-forwarded-for");
    if (xff) headers["X-Forwarded-For"] = xff;
  }

  let body: BodyInit | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    if (isMultipart) {
      // Pass through the raw body for file uploads
      body = await req.arrayBuffer();
      // Need to set the original content-type with boundary
      headers["Content-Type"] = contentType;
    } else {
      body = await req.text();
    }
  }

  const res = await fetch(url, {
    method: req.method,
    headers,
    body,
  });

  const data = await res.text();

  return new NextResponse(data, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
