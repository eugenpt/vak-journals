export default {
  async fetch(request) {
    const allowedOrigins = new Set([
      "https://eugenpt.github.io",
      "http://localhost:8080",
    ]);
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");
    const corsOrigin = allowedOrigins.has(origin) ? origin : "https://eugenpt.github.io";
    const issn = url.searchParams.get("issn");

    if (!issn || !/^\d{4}-?\d{3}[\dXx]$/.test(issn)) {
      return new Response("Bad ISSN", {
        status: 400,
        headers: { "Access-Control-Allow-Origin": corsOrigin },
      });
    }

    const normalized = issn.includes("-")
      ? issn.toUpperCase()
      : issn.replace(/^(\d{4})(\d{3}[\dXx])$/, "$1-$2").toUpperCase();
    const upstream =
      `https://journalrank.rcsi.science/api/record-sources/${encodeURIComponent(normalized)}/level`;
    const res = await fetch(upstream, {
      headers: { Accept: "application/json" },
    });
    const body = await res.text();

    return new Response(body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") || "application/json",
        "Access-Control-Allow-Origin": corsOrigin,
        "Cache-Control": "public, max-age=86400",
      },
    });
  },
};
