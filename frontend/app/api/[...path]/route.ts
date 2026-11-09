// Server-side proxy: the browser only talks to this app; requests to /api/* are forwarded to the backend
// (BACKEND_URL, e.g. http://backend:8000 inside Docker). No CORS, and the backend address stays private.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function forward(request: Request, path: string[]): Promise<Response> {
  const url = new URL(request.url);
  const target = `${BACKEND_URL}/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const key = request.headers.get("Idempotency-Key");
  if (key) headers["Idempotency-Key"] = key;
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" ? undefined : await request.text(),
    cache: "no-store",
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, ctx: Ctx) {
  return forward(request, (await ctx.params).path);
}

export async function POST(request: Request, ctx: Ctx) {
  return forward(request, (await ctx.params).path);
}
