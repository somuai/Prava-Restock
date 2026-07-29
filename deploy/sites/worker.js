const appIndexPath = "/app/index.html";

function assetRequest(request, pathname) {
  const url = new URL(request.url);
  url.pathname = pathname;
  return new Request(url, request);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/") {
      url.pathname = "/app/";
      return Response.redirect(url, 302);
    }

    const response = await env.ASSETS.fetch(request);
    if (response.status !== 404) return response;

    const isAppRoute =
      url.pathname === "/app" ||
      (url.pathname.startsWith("/app/") &&
        !url.pathname.slice("/app/".length).includes("."));

    if (isAppRoute) {
      return env.ASSETS.fetch(assetRequest(request, appIndexPath));
    }

    return response;
  },
};
